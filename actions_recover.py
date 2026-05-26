"""
=====================================================================
  ACTIONS RECOVER — Recupera relatórios JÁ PRONTOS no Radar
=====================================================================
  Diferente do actions_runner.py:
    - NÃO solicita relatório novo
    - NÃO espera nada
    - Vai DIRETO na fila do Radar
    - Pega o relatório mais recente PRONTO de cada conta
    - Baixa, junta e sobe pro Sheets

  Use quando você já sabe que os relatórios foram gerados
  (ex: solicitou manual e quer só consolidar).
=====================================================================
"""

import os
import io
import sys
import time
import unicodedata
import requests
import pandas as pd
import gspread
from datetime import datetime
from google.oauth2.service_account import Credentials
from securid.sdtid import SdtidFile

# ─────────────────────────────────────────────────────────────────
#  ⚙️  CONFIGURAÇÕES
# ─────────────────────────────────────────────────────────────────

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]

ABA_DESTINO = "DadosRadar"

URL_RADAR = "https://radar.timbrasil.com.br/"
URL_FILA  = "https://radar.timbrasil.com.br/radar-blue/sistema/report-queue.asp"

PALAVRAS_PRONTO = ("concluido", "concluida", "pronto", "disponivel", "finalizado", "ok")

CONTAS = [
    {"login": "t3729525", "sdtid": "T3729525_001938489117.sdtid"},
    {"login": "t3761125", "sdtid": "T3761125_001938495598.sdtid"},
    {"login": "t3748937", "sdtid": "T3748937_001938491397.sdtid"},
]


# ─────────────────────────────────────────────────────────────────
#  MONKEY-PATCH RSA (ignora MAC check)
# ─────────────────────────────────────────────────────────────────

def _verify_mac_ignorar(self, *args, **kwargs):
    pass
SdtidFile.verify_mac = _verify_mac_ignorar


def gerar_token(sdtid_path: str, pin: int = 1234) -> str:
    token_obj = SdtidFile(sdtid_path).get_token()
    token_obj.pin = pin
    return token_obj.now()


def _normalizar(texto: str) -> str:
    nfd = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn").lower()


def esta_pronto(texto_linha: str) -> bool:
    n = _normalizar(texto_linha)
    return any(p in n for p in PALAVRAS_PRONTO)


# ─────────────────────────────────────────────────────────────────
#  SELENIUM — driver
# ─────────────────────────────────────────────────────────────────

def criar_driver():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    import shutil
    chromedriver = shutil.which("chromedriver")
    chrome = shutil.which("google-chrome") or shutil.which("chromium-browser") or shutil.which("chromium")
    if chrome:
        options.binary_location = chrome

    if chromedriver:
        return webdriver.Chrome(service=Service(chromedriver), options=options)
    else:
        from webdriver_manager.chrome import ChromeDriverManager
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)


# ─────────────────────────────────────────────────────────────────
#  SELENIUM — login RSA
# ─────────────────────────────────────────────────────────────────

def fazer_login(driver, login, sdtid_path):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    token = gerar_token(sdtid_path)
    print(f"  🔐 Token gerado para {login.upper()}")

    try:
        driver.delete_all_cookies()
    except Exception:
        pass

    driver.get(URL_RADAR)
    time.sleep(5)

    try:
        campo = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "identifierInput")))
        campo.clear()
        campo.send_keys(login)
        btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.ID, "signOnButton")))
        driver.execute_script("arguments[0].click()", btn)
        time.sleep(4)
    except Exception as e:
        raise RuntimeError(f"Login falhou para {login.upper()}: campo de username não interagível ({e})")

    try:
        WebDriverWait(driver, 20).until(lambda d: "iam-pf" in d.current_url)
        time.sleep(3)
    except Exception:
        pass

    campo_token = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "password")))
    campo_token.send_keys(token)
    time.sleep(1)
    btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "signOnButton")))
    driver.execute_script("arguments[0].click()", btn)
    time.sleep(8)
    print(f"  ✅ Login OK — {driver.current_url[:60]}")

    try:
        fechar = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//*[contains(@class,'close') or contains(@aria-label,'lose')]"))
        )
        driver.execute_script("arguments[0].click()", fechar)
        time.sleep(1)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────
#  BAIXAR RELATÓRIO MAIS RECENTE DA FILA
# ─────────────────────────────────────────────────────────────────

def baixar_via_cookies(driver, link):
    cookies = driver.get_cookies()
    sessao  = requests.Session()
    for c in cookies:
        sessao.cookies.set(c["name"], c["value"])
    resp    = sessao.get(link, headers={"User-Agent": "Mozilla/5.0"}, timeout=120)
    content = resp.content
    try:
        df = pd.read_excel(io.BytesIO(content), engine="openpyxl", header=0)
    except Exception:
        df = pd.read_excel(io.BytesIO(content), engine="xlrd", header=0)
    return df


def pegar_relatorio_mais_recente(driver, login: str):
    from selenium.webdriver.common.by import By

    driver.get(URL_FILA)
    time.sleep(5)

    linhas = driver.find_elements(By.XPATH, "//tr[contains(., 'Após 01/05/2009')]")
    print(f"  📊 Linhas 'Após 01/05/2009' encontradas: {len(linhas)}")

    melhor_id = -1
    melhor_link = None

    for linha in linhas:
        try:
            texto = linha.text or ""
            if not esta_pronto(texto):
                continue

            celulas = linha.find_elements(By.XPATH, ".//td")
            id_rel = None
            for cel in celulas:
                t = (cel.text or "").strip()
                if t.isdigit():
                    id_rel = int(t)
                    break
            if id_rel is None:
                continue

            try:
                link_el = linha.find_element(By.XPATH, ".//a[contains(@href,'report-queue-download')]")
                link = link_el.get_attribute("href")
            except Exception:
                continue

            if id_rel > melhor_id:
                melhor_id = id_rel
                melhor_link = link
        except Exception:
            continue

    if melhor_id < 0 or not melhor_link:
        print(f"  ⚠️ Nenhum relatório PRONTO encontrado para {login.upper()}")
        return None

    print(f"  ✅ [{login.upper()}] Relatório mais recente: ID {melhor_id}")
    df = baixar_via_cookies(driver, melhor_link)
    print(f"  📦 [{login.upper()}] {len(df)} linhas baixadas")
    return df


def processar_conta(login, sdtid_path):
    driver = criar_driver()
    try:
        fazer_login(driver, login, sdtid_path)
        return pegar_relatorio_mais_recente(driver, login)
    finally:
        driver.quit()


# ─────────────────────────────────────────────────────────────────
#  SHEETS
# ─────────────────────────────────────────────────────────────────

def subir_para_sheets(df):
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
    gc = gspread.authorize(creds)
    planilha = gc.open_by_key(SPREADSHEET_ID)
    try:
        aba = planilha.worksheet(ABA_DESTINO)
    except gspread.WorksheetNotFound:
        aba = planilha.add_worksheet(title=ABA_DESTINO, rows=1, cols=1)
    aba.clear()
    df = df.fillna("")
    dados = [df.columns.tolist()] + df.values.tolist()
    dados = [[str(v) for v in linha] for linha in dados]
    aba.update(dados, value_input_option="USER_ENTERED")
    print(f"  ✅ {len(df)} linhas gravadas em '{ABA_DESTINO}'!")


# ─────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  ACTIONS RECOVER — RELATÓRIOS JÁ PRONTOS")
    print(f"  Início: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 55)

    dfs = []
    logins_ok = []
    logins_fail = []

    for conta in CONTAS:
        login = conta["login"]
        sdtid = conta["sdtid"]

        print(f"\n🌐 Processando {login.upper()}...")

        if not os.path.exists(sdtid):
            print(f"  ⚠️ SDTID não encontrado: {sdtid} — pulando")
            logins_fail.append(login)
            continue

        try:
            df = processar_conta(login, sdtid)
            if df is not None and not df.empty:
                dfs.append(df)
                logins_ok.append(login)
            else:
                logins_fail.append(login)
        except Exception as e:
            print(f"  ❌ Erro em {login.upper()}: {e}")
            logins_fail.append(login)

    print(f"\n{'=' * 55}")
    print(f"  Resumo:")
    print(f"  ✅ OK:    {len(logins_ok)}/{len(CONTAS)} — {', '.join(l.upper() for l in logins_ok)}")
    if logins_fail:
        print(f"  ❌ Falha: {len(logins_fail)}/{len(CONTAS)} — {', '.join(l.upper() for l in logins_fail)}")
    print(f"{'=' * 55}")

    if not dfs:
        print("\n❌ Nenhum relatório baixado. Abortando.")
        sys.exit(1)

    df_final = pd.concat(dfs, ignore_index=True)
    print(f"\n📋 Total consolidado: {len(df_final)} linhas")
    subir_para_sheets(df_final)

    print(f"\n🎉 DadosRadar atualizado com sucesso!")
    print("=" * 55)

    if logins_fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
