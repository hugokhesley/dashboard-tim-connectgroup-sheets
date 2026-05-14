"""
=====================================================================
  ACTIONS RUNNER — Roda no GitHub Actions
=====================================================================
  Fluxo:
  1. Login RSA + solicitar relatório para cada conta
  2. IMAP monitora email como gatilho (sem usar o link)
  3. Novo login RSA + baixa o relatório mais recente da fila
  4. Concat + upload para o Google Sheets
=====================================================================
"""

import os
import io
import time
import imaplib
import email
import re
import requests
import pandas as pd
import gspread
from datetime import datetime, timezone, timedelta
from email.header import decode_header
from email.utils import parsedate_to_datetime
from google.oauth2.service_account import Credentials
from securid.sdtid import SdtidFile

# ─────────────────────────────────────────────────────────────────
#  ⚙️  CONFIGURAÇÕES
# ─────────────────────────────────────────────────────────────────

EMAIL_1         = os.environ["IMAP_EMAIL_1"]
SENHA_1         = os.environ["IMAP_SENHA_1"]
EMAIL_2         = os.environ["IMAP_EMAIL_2"]
SENHA_2         = os.environ["IMAP_SENHA_2"]
EMAIL_3         = os.environ["IMAP_EMAIL_3"]
SENHA_3         = os.environ["IMAP_SENHA_3"]
SPREADSHEET_ID  = os.environ["SPREADSHEET_ID"]
POSICAO_FILA    = int(os.environ.get("POSICAO_FILA", "3"))

IMAP_HOST       = "imap.titan.email"
IMAP_PORT       = 993
JANELA_MINUTOS  = 40
INTERVALO_IMAP  = 300
ABA_DESTINO     = "DadosRadar"

CONTAS = [
    {"login": "t3729525", "sdtid": "T3729525_001938489117.sdtid", "email": EMAIL_1, "senha": SENHA_1},
    {"login": "t3761125", "sdtid": "T3761125_001938495598.sdtid", "email": EMAIL_2, "senha": SENHA_2},
    {"login": "t3748937", "sdtid": "T3748937_001938491397.sdtid", "email": EMAIL_3, "senha": SENHA_3},
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


def calcular_datas():
    hoje = datetime.today()
    mes  = hoje.month - 2
    ano  = hoje.year
    if mes <= 0:
        mes += 12
        ano -= 1
    return f"01/{mes:02d}/{ano}", hoje.strftime("%d/%m/%Y")


# ─────────────────────────────────────────────────────────────────
#  SELENIUM — criação do driver
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

    driver.get("https://radar.timbrasil.com.br/")
    time.sleep(5)

    # Username
    try:
        campo = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "identifierInput")))
        campo.clear()
        campo.send_keys(login)
        btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.ID, "signOnButton")))
        driver.execute_script("arguments[0].click()", btn)
        time.sleep(4)
    except Exception as e:
        print(f"  ⚠️ Username: {e}")

    # SmartID
    try:
        WebDriverWait(driver, 20).until(lambda d: "iam-pf" in d.current_url)
        time.sleep(3)
    except Exception:
        pass

    # Token RSA
    campo_token = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "password")))
    campo_token.send_keys(token)
    time.sleep(1)
    btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "signOnButton")))
    driver.execute_script("arguments[0].click()", btn)
    time.sleep(8)
    print(f"  ✅ Login OK — {driver.current_url[:60]}")

    # Fecha popup se aparecer
    try:
        fechar = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//*[contains(@class,'close') or contains(@aria-label,'lose')]"))
        )
        driver.execute_script("arguments[0].click()", fechar)
        time.sleep(1)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────
#  ETAPA 1 — Solicitar relatório
# ─────────────────────────────────────────────────────────────────

def solicitar_relatorio(login, sdtid_path, data_inicio, data_fim):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    driver = criar_driver()
    try:
        fazer_login(driver, login, sdtid_path)

        # Vai direto para a lista de relatórios
        driver.get("https://radar.timbrasil.com.br/radar-tim/relatorios/lista2.asp")
        time.sleep(5)

        # Seleciona especificamente "Base Geral - Após 01/05/2009"
        base = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(text(),'Após 01/05/2009')]"))
        )
        driver.execute_script("arguments[0].click()", base)
        time.sleep(5)

        # Preenche datas
        campo_de = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.NAME, "a.dt_precadastro_de")))
        driver.execute_script("arguments[0].removeAttribute('readonly')", campo_de)
        driver.execute_script(f"arguments[0].value = '{data_inicio}'", campo_de)
        campo_ate = driver.find_element(By.NAME, "a.dt_precadastro_ate")
        driver.execute_script("arguments[0].removeAttribute('readonly')", campo_ate)
        driver.execute_script(f"arguments[0].value = '{data_fim}'", campo_ate)

        # Checkboxes
        for valor in ["1", "2", "3"]:
            try:
                cb = driver.find_element(By.XPATH, f"//input[@type='checkbox' and @name='g.idtipocontrata' and @value='{valor}']")
                if not cb.is_selected():
                    driver.execute_script("arguments[0].click()", cb)
            except Exception:
                pass

        # Gerar
        gerar = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//input[@value='Gerar Relatório']")))
        driver.execute_script("arguments[0].click()", gerar)
        time.sleep(5)
        print(f"  ✓ Relatório solicitado!")

        # Posição na fila
        posicao = POSICAO_FILA
        try:
            driver.get("https://radar.timbrasil.com.br/radar-blue/sistema/report-queue.asp")
            time.sleep(3)
            linhas = driver.find_elements(By.XPATH, "//table//tr[contains(.,'pendente')]")
            if linhas:
                pos = linhas[0].find_element(By.XPATH, ".//td[last()]")
                posicao = int(pos.text.strip()) if pos.text.strip().isdigit() else len(linhas)
        except Exception:
            pass

        print(f"  📊 Posição na fila: {posicao}")
        return posicao

    finally:
        driver.quit()


# ─────────────────────────────────────────────────────────────────
#  ETAPA 3 — Baixar relatório mais recente
# ─────────────────────────────────────────────────────────────────

def baixar_relatorio(login, sdtid_path):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    driver = criar_driver()
    try:
        fazer_login(driver, login, sdtid_path)

        # Vai direto para a fila de relatórios
        driver.get("https://radar.timbrasil.com.br/radar-blue/sistema/report-queue.asp")
        time.sleep(3)
        print(f"  📋 Fila de relatórios aberta")

        # Aguarda aparecer linha "concluído" com "Após 01/05/2009"
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, "//tr[contains(.,'Após 01/05/2009') and contains(.,'concluído')]//a"))
        )
        time.sleep(2)

        # Pega todas as linhas concluídas com "Após 01/05/2009"
        linhas = driver.find_elements(By.XPATH, "//tr[contains(.,'Após 01/05/2009') and contains(.,'concluído')]")

        if not linhas:
            raise Exception("Nenhum relatório concluído encontrado na fila.")

        # Pega o link da linha com maior ID (mais recente)
        melhor_link = None
        melhor_id   = -1
        for linha in linhas:
            try:
                link_el = linha.find_element(By.XPATH, ".//a[contains(@href,'report-queue-download')]")
                href    = link_el.get_attribute("href")
                match   = re.search(r"idreport=(\d+)", href)
                if match:
                    id_rel = int(match.group(1))
                    if id_rel > melhor_id:
                        melhor_id   = id_rel
                        melhor_link = href
            except Exception:
                continue

        if not melhor_link:
            raise Exception("Não foi possível extrair o link de download.")

        print(f"  🔗 Baixando relatório ID {melhor_id}...")

        # Extrai cookies da sessão do Selenium
        cookies_selenium = driver.get_cookies()
        sessao = requests.Session()
        for c in cookies_selenium:
            sessao.cookies.set(c["name"], c["value"])

        resp    = sessao.get(melhor_link, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        content = resp.content

        # Lê o arquivo
        try:
            df = pd.read_excel(io.BytesIO(content), engine="openpyxl", header=0)
        except Exception:
            df = pd.read_excel(io.BytesIO(content), engine="xlrd", header=0)

        print(f"  ✅ {len(df)} linhas baixadas para {login.upper()}")
        return df

    finally:
        driver.quit()


# ─────────────────────────────────────────────────────────────────
#  IMAP — monitora email como gatilho
# ─────────────────────────────────────────────────────────────────

def verificar_email(email_conta, senha, desde):
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(email_conta, senha)

        _, pastas_raw = mail.list()
        caixas = ["INBOX"]
        for p in pastas_raw:
            if p:
                nome = p.decode(errors="ignore").split('"/"')[-1].strip().strip('"')
                if "gmail" in nome.lower() or "totodecasa" in nome.lower() or "@gmail" in nome.lower():
                    caixas.append(nome)

        desde_utc = desde.astimezone(timezone.utc)
        data_imap = desde_utc.strftime("%d-%b-%Y")

        for caixa in caixas:
            try:
                status_sel, _ = mail.select(f'"{caixa}"')
                if status_sel != "OK":
                    continue
            except Exception:
                continue

            status, msgs = mail.search(None, f'SINCE "{data_imap}"')
            if status != "OK" or not msgs[0]:
                continue

            for uid in reversed(msgs[0].split()):
                _, dados = mail.fetch(uid, "(RFC822)")
                msg = email.message_from_bytes(dados[0][1])

                data_str = msg.get("Date")
                if not data_str:
                    continue
                try:
                    data_email = parsedate_to_datetime(data_str)
                    if data_email.tzinfo is None:
                        data_email = data_email.replace(tzinfo=timezone.utc)
                    else:
                        data_email = data_email.astimezone(timezone.utc)
                except Exception:
                    continue

                if data_email <= desde_utc:
                    continue

                assunto_raw = msg.get("Subject", "")
                try:
                    partes = decode_header(assunto_raw)
                    assunto = ""
                    for parte, enc in partes:
                        if isinstance(parte, bytes):
                            assunto += parte.decode(enc or "utf-8", errors="ignore")
                        else:
                            assunto += parte
                except Exception:
                    assunto = assunto_raw

                if "Radar" not in assunto and "radar" not in assunto:
                    continue

                mail.logout()
                return True  # só gatilho, sem usar o link

        mail.logout()
        return False
    except Exception as e:
        print(f"  ⚠️ Erro IMAP {email_conta}: {e}")
        return False


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
    print("  ACTIONS RUNNER — ATUALIZAÇÃO DADOSRADAR")
    print("=" * 55)

    data_inicio, data_fim = calcular_datas()
    print(f"📅 Período: {data_inicio} → {data_fim}")

    # ── ETAPA 1: Solicitar relatórios ─────────────────────────
    contas_ok = []
    posicoes  = []
    for conta in CONTAS:
        print(f"\n🌐 Processando {conta['login'].upper()}...")
        try:
            posicao = solicitar_relatorio(conta["login"], conta["sdtid"], data_inicio, data_fim)
            posicoes.append(posicao)
            contas_ok.append(conta)
        except Exception as e:
            print(f"  ❌ FALHA em {conta['login'].upper()}, pulando: {e}")
            continue

    if not contas_ok:
        print("❌ Nenhuma conta processada. Abortando.")
        exit(1)

    # Calcula espera baseada na maior posição na fila
    maior        = max(posicoes)
    primeira_min = ((maior * 7) + 2) // 2
    print(f"\n✅ Contas OK: {', '.join(c['login'].upper() for c in contas_ok)}")
    print(f"⏳ Aguardando {primeira_min} min antes de verificar emails...")
    time.sleep(primeira_min * 60)

    # ── ETAPA 2: Monitora emails como gatilho ─────────────────
    desde     = datetime.now().astimezone() - timedelta(minutes=JANELA_MINUTOS)
    gatilhos  = {c["login"]: False for c in contas_ok}
    tentativa = 0

    while tentativa < 12:
        tentativa += 1
        print(f"\n🔍 Verificação de email #{tentativa}...")

        for conta in contas_ok:
            if not gatilhos[conta["login"]]:
                chegou = verificar_email(conta["email"], conta["senha"], desde)
                gatilhos[conta["login"]] = chegou
                status = "✅ recebido" if chegou else "⏸ aguardando"
                print(f"  {conta['login'].upper()}: {status}")

        if all(gatilhos.values()):
            print("✅ Todos os emails recebidos!")
            break

        # Se pelo menos metade chegou e já são 6 tentativas, segue
        recebidos = sum(gatilhos.values())
        if recebidos > 0 and tentativa >= 6:
            print(f"⚠️ {recebidos}/{len(contas_ok)} emails recebidos. Prosseguindo com os disponíveis...")
            break

        print(f"  ⏳ Aguardando {INTERVALO_IMAP // 60} min...")
        time.sleep(INTERVALO_IMAP)

    # ── ETAPA 3: Baixar relatórios via novo login ─────────────
    print("\n⬇️ Baixando relatórios...")
    dfs = []
    for conta in contas_ok:
        if not gatilhos[conta["login"]]:
            print(f"  ⚠️ {conta['login'].upper()}: email não chegou, pulando download.")
            continue
        try:
            df = baixar_relatorio(conta["login"], conta["sdtid"])
            dfs.append(df)
        except Exception as e:
            print(f"  ❌ Erro ao baixar {conta['login'].upper()}: {e}")

    if not dfs:
        print("❌ Nenhum arquivo baixado. Abortando.")
        exit(1)

    # ── ETAPA 4: Concat + Upload ──────────────────────────────
    df_final = pd.concat(dfs, ignore_index=True)
    print(f"\n📋 Total consolidado: {len(df_final)} linhas")
    subir_para_sheets(df_final)

    print("\n🎉 DadosRadar atualizado com sucesso!")
    print("=" * 55)


if __name__ == "__main__":
    main()
