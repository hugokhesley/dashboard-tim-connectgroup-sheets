"""
=====================================================================
  ACTIONS RUNNER - Roda no GitHub Actions
=====================================================================
  Versao do script adaptada para rodar em servidor Linux headless.
  Usa variaveis de ambiente em vez de st.secrets.
=====================================================================
"""

import os
import time
import imaplib
import email
import re
import requests
import pandas as pd
import gspread
import base64
import tempfile
from datetime import datetime, timezone, timedelta
from email.header import decode_header
from email.utils import parsedate_to_datetime
from google.oauth2.service_account import Credentials
from securid.sdtid import SdtidFile

# ---------------------------------------------------------------------
# CONFIGURACOES (via variaveis de ambiente)
# ---------------------------------------------------------------------

EMAIL_1         = os.environ["EMAIL_1"]
SENHA_1         = os.environ["SENHA_1"]
EMAIL_2         = os.environ["EMAIL_2"]
SENHA_2         = os.environ["SENHA_2"]
EMAIL_3         = os.environ["EMAIL_3"]
SENHA_3         = os.environ["SENHA_3"]
SPREADSHEET_ID  = os.environ["SPREADSHEET_ID"]
POSICAO_FILA    = int(os.environ.get("POSICAO_FILA", "3"))

IMAP_HOST       = "imap.titan.email"
IMAP_PORT       = 993
JANELA_MINUTOS  = 40
INTERVALO_IMAP  = 300
ABA_DESTINO     = "DadosRadar"

CONTAS = [
    {"login": "t3729525", "sdtid": "T3729525_001938489117.sdtid"},
    {"login": "t3761125", "sdtid": "T3761125_001938495598.sdtid"},
    {"login": "t3748937", "sdtid": "T3748937_001938491397.sdtid"},
]

# ---------------------------------------------------------------------
# MONKEY-PATCH RSA
# ---------------------------------------------------------------------

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


# ---------------------------------------------------------------------
# SELENIUM
# ---------------------------------------------------------------------

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


def fazer_login_e_solicitar(login, sdtid_path, data_inicio, data_fim):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    token = gerar_token(sdtid_path)
    print(f"  Token gerado para {login.upper()}")

    driver = criar_driver()
    try:
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
            print(f"  Aviso Username: {e}")

        # SmartID
        try:
            WebDriverWait(driver, 20).until(lambda d: "iam-pf" in d.current_url)
            time.sleep(3)
        except Exception:
            pass

        # Token
        campo_token = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "password")))
        campo_token.send_keys(token)
        time.sleep(1)
        btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "signOnButton")))
        driver.execute_script("arguments[0].click()", btn)
        time.sleep(8)
        print(f"  Login OK - {driver.current_url[:60]}")

        # Lista relatorios
        driver.get("https://radar.timbrasil.com.br/radar-tim/relatorios/lista2.asp")
        time.sleep(5)

        base = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(text(),'Base Geral - Apos 01/05/2009')]"))
        )
        driver.execute_script("arguments[0].click()", base)
        time.sleep(5)

        # Datas
        campo_de = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.NAME, "a.dt_precadastro_de")))
        driver.execute_script("arguments[0].removeAttribute('readonly')", campo_de)
        driver.execute_script(f"arguments[0].value = '{data_inicio}'", campo_de)
        campo_ate = driver.find_element(By.NAME, "a.dt_precadastro_ate")
        driver.execute_script("arguments[0].removeAttribute('readonly')", campo_ate)
        driver.execute_script(f"arguments[0].value = '{data_fim}'", campo_ate)

        for valor in ["1", "2", "3"]:
            try:
                cb = driver.find_element(By.XPATH, f"//input[@type='checkbox' and @name='g.idtipocontrata' and @value='{valor}']")
                if not cb.is_selected():
                    driver.execute_script("arguments[0].click()", cb)
            except Exception:
                pass

        gerar = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//input[@value='Gerar Relatorio']")))
        driver.execute_script("arguments[0].click()", gerar)
        time.sleep(5)
        print(f"  Relatorio solicitado!")

        # Posicao na fila
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

        print(f"  Posicao na fila: {posicao}")
        return posicao

    finally:
        driver.quit()


# ---------------------------------------------------------------------
# IMAP
# ---------------------------------------------------------------------

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
                status_sel, _ = mail.select('"' + caixa + '"')
                if status_sel != "OK":
                    continue
            except Exception:
                continue

            status, msgs = mail.search(None, 'SINCE "' + data_imap + '"')
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

                for parte in msg.walk():
                    if parte.get_content_type() in ("text/plain", "text/html"):
                        corpo = parte.get_payload(decode=True).decode(errors="ignore")
                        match = re.search(r'https://radar\.timbrasil\.com\.br/[^\s"<>\)]+', corpo)
                        if match:
                            mail.logout()
                            return match.group(0).strip()

        mail.logout()
        return None
    except Exception as e:
        print("  Erro IMAP " + email_conta + ": " + str(e))
        return None


# ---------------------------------------------------------------------
# SHEETS
# ---------------------------------------------------------------------

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
    print("  OK: " + str(len(df)) + " linhas gravadas em '" + ABA_DESTINO + "'!")


# ---------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------

def main():
    print("=" * 55)
    print("  ACTIONS RUNNER - ATUALIZACAO DADOSRADAR")
    print("=" * 55)

    data_inicio, data_fim = calcular_datas()
    print("Periodo: " + data_inicio + " -> " + data_fim)

    # Etapa 1: Solicitar relatorios
    contas_ok = []
    posicoes = []
    for conta in CONTAS:
        print("\nProcessando " + conta["login"].upper() + "...")
        try:
            posicao = fazer_login_e_solicitar(conta["login"], conta["sdtid"], data_inicio, data_fim)
            posicoes.append(posicao)
            contas_ok.append(conta["login"])
        except Exception as e:
            print("  FALHA em " + conta["login"].upper() + ", pulando: " + str(e))
            continue

    if not posicoes:
        print("Nenhuma conta processada com sucesso. Abortando.")
        exit(1)

    # Calcula espera
    maior = max(posicoes)
    tempo_total  = (maior * 7) + 2
    primeira_min = tempo_total // 2

    print("\nContas OK: " + ", ".join(contas_ok))
    print("Aguardando " + str(primeira_min) + " min antes da verificacao de emails...")
    time.sleep(primeira_min * 60)

    # Etapa 2: Aguarda emails
    desde = datetime.now().astimezone() - timedelta(minutes=JANELA_MINUTOS)

    emails_contas = []
    if "t3729525" in contas_ok:
        emails_contas.append({"nome": "Email 1", "email": EMAIL_1, "senha": SENHA_1})
    if "t3761125" in contas_ok:
        emails_contas.append({"nome": "Email 2", "email": EMAIL_2, "senha": SENHA_2})
    if "t3748937" in contas_ok:
        emails_contas.append({"nome": "Email 3", "email": EMAIL_3, "senha": SENHA_3})

    links = [None] * len(emails_contas)
    tentativa = 0

    while tentativa < 12:
        tentativa += 1
        print("\nVerificacao #" + str(tentativa) + "...")

        for i, ec in enumerate(emails_contas):
            if not links[i]:
                links[i] = verificar_email(ec["email"], ec["senha"], desde)
                status = "recebido" if links[i] else "aguardando"
                print("  " + ec["nome"] + ": " + status)

        if all(links):
            break

        print("  Aguardando " + str(INTERVALO_IMAP // 60) + " min...")
        time.sleep(INTERVALO_IMAP)

    links_validos = [l for l in links if l]
    if not links_validos:
        print("Timeout: nenhum email chegou. Abortando.")
        exit(1)

    if len(links_validos) < len(emails_contas):
        print("Aviso: apenas " + str(len(links_validos)) + " de " + str(len(emails_contas)) + " emails chegaram. Prosseguindo...")

    # Etapa 3: Download e upload
    print("\nBaixando planilhas...")
    import io
    dfs = []
    for i, link in enumerate(links_validos):
        try:
            content = requests.get(link, headers={"User-Agent": "Mozilla/5.0"}, timeout=60).content
            try:
                df = pd.read_excel(io.BytesIO(content), engine="openpyxl", header=0)
            except Exception:
                df = pd.read_excel(io.BytesIO(content), engine="xlrd", header=0)
            print("  Arquivo " + str(i+1) + ": " + str(len(df)) + " linhas")
            dfs.append(df)
        except Exception as e:
            print("  Erro no download " + str(i+1) + ": " + str(e))

    if not dfs:
        print("Nenhum arquivo baixado. Abortando.")
        exit(1)

    df_final = pd.concat(dfs, ignore_index=True)
    print("  Total: " + str(len(df_final)) + " linhas")

    subir_para_sheets(df_final)

    print("\nDadosRadar atualizado com sucesso!")
    print("=" * 55)


if __name__ == "__main__":
    main()
