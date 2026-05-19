"""
=====================================================================
  ACTIONS RECOVER — Recuperação pós-timeout
=====================================================================
  Roda quando o actions_runner.py já solicitou os relatórios em uma
  rodada anterior mas o download não foi concluído. Faz a mesma
  lógica de monitoramento + download via Radar, sem solicitar de
  novo. 100% via Radar (sem IMAP/email).
=====================================================================
"""

import os
import io
import re
import time
import unicodedata
import requests
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from securid.sdtid import SdtidFile

# ─────────────────────────────────────────────────────────────────
#  ⚙️  CONFIGURAÇÕES
# ─────────────────────────────────────────────────────────────────

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]

ABA_DESTINO       = "DadosRadar"
INTERVALO_POLL    = 60
TIMEOUT_POLL_MIN  = 90

URL_RADAR         = "https://radar.timbrasil.com.br/"
URL_FILA          = "https://radar.timbrasil.com.br/radar-blue/sistema/report-queue.asp"

PALAVRAS_PRONTO   = ("concluido", "concluida", "pronto", "disponivel", "finalizado", "ok")
TERMOS_LOGIN_URL  = ("iam-pf", "signon", "login", "authn")

CONTAS = [
    {"login": "t3729525", "sdtid": "T3729525_001938489117.sdtid"},
    {"login": "t3761125", "sdtid": "T3761125_001938495598.sdtid"},
    {"login": "t3748937", "sdtid": "T3748937_001938491397.sdtid"},
]

# ─────────────────────────────────────────────────────────────────
#  MONKEY-PATCH RSA
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


def sessao_caiu(driver) -> bool:
    url = (driver.current_url or "").lower()
    return any(t in url for t in TERMOS_LOGIN_URL)


# ─────────────────────────────────────────────────────────────────
#  SELENIUM — driver + login
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


def fazer_login(driver, login, sdtid_path):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    token = gerar_token(sdtid_path)
    print(f"  🔐 Token gerado para {login.upper()}")

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
        print(f"  ⚠️ Username: {e}")

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
#  POLLING + DOWNLOAD
# ─────────────────────────────────────────────────────────────────

def buscar_linha_pronta(driver):
    from selenium.webdriver.common.by import By

    melhor_link = None
    melhor_id   = -1
    linhas = driver.find_elements(By.XPATH, "//tr[contains(., 'Após 01/05/2009')]")
    for linha in linhas:
        try:
            if not esta_pronto(linha.text):
                continue
            link_el = linha.find_element(By.XPATH, ".//a[contains(@href,'report-queue-download')]")
            href    = link_el.get_attribute("href")
            m       = re.search(r"idreport=(\d+)", href)
            if m:
                id_rel = int(m.group(1))
                if id_rel > melhor_id:
                    melhor_id   = id_rel
                    melhor_link = href
        except Exception:
            continue
    return melhor_link, melhor_id


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


def monitorar_e_baixar(login, sdtid_path, timeout_min=TIMEOUT_POLL_MIN):
    driver = criar_driver()
    try:
        fazer_login(driver, login, sdtid_path)

        inicio    = time.time()
        tentativa = 0
        while time.time() - inicio < timeout_min * 60:
            tentativa += 1
            try:
                driver.get(URL_FILA)
                time.sleep(3)

                if sessao_caiu(driver):
                    print(f"  ⚠️ [{login.upper()}] sessão caiu — refazendo login RSA")
                    fazer_login(driver, login, sdtid_path)
                    continue

                link, id_rel = buscar_linha_pronta(driver)
                if link:
                    decorrido = int((time.time() - inicio) / 60)
                    print(f"  ✅ [{login.upper()}] relatório pronto (id {id_rel}, {decorrido} min, tent #{tentativa})")
                    df = baixar_via_cookies(driver, link)
                    print(f"  📦 [{login.upper()}] {len(df)} linhas baixadas")
                    return df

                decorrido = int((time.time() - inicio) / 60)
                print(f"  ⏳ [{login.upper()}] aguardando... ({decorrido}/{timeout_min} min, tent #{tentativa})")
                time.sleep(INTERVALO_POLL)

            except Exception as e:
                print(f"  ⚠️ [{login.upper()}] erro no poll #{tentativa}: {e}")
                time.sleep(INTERVALO_POLL)

        raise TimeoutError(f"Timeout de {timeout_min} min atingido para {login.upper()}")

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
    print("  ACTIONS RECOVER — DOWNLOAD VIA RADAR")
    print("=" * 55)
    print(f"⬇️  Polling em report-queue.asp (intervalo {INTERVALO_POLL}s, timeout {TIMEOUT_POLL_MIN} min/conta)")
    print("    (Assume que as solicitações já saíram em rodada anterior.)")

    dfs = []
    for conta in CONTAS:
        print(f"\n🔄 Monitorando {conta['login'].upper()}...")
        try:
            df = monitorar_e_baixar(conta["login"], conta["sdtid"])
            dfs.append(df)
        except Exception as e:
            print(f"  ❌ {conta['login'].upper()}: {e}")

    if not dfs:
        print("\n❌ Nenhum arquivo baixado. Abortando.")
        exit(1)

    df_final = pd.concat(dfs, ignore_index=True)
    print(f"\n📋 Total consolidado: {len(df_final)} linhas")
    subir_para_sheets(df_final)

    print("\n🎉 Recuperação concluída com sucesso!")
    print("=" * 55)


if __name__ == "__main__":
    main()
