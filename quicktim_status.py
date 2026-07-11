"""
=====================================================================
  QUICKTIM STATUS — Roda no GitHub Actions (3x/dia)
=====================================================================
  Objetivo ÚNICO: atualizar o status atual dos pedidos abertos.

  Fluxo:
  1. Lê a aba DadosRadar (output da base das 7h) e monta a lista de
     pedidos a consultar POR PARCEIRO:
       - tipo ∈ {NOVO, ADITIVO}
       - SEM 'data de ativação' (já ativou => terminal, não consulta)
       - roteamento pela coluna 'parceiro' (NUNCA pelo cEscritorio do CRM)
  2. Para cada parceiro: login RSA headless (mesmo esquema do
     actions_runner) + consulta o QuickTIM (chatUser.asp) pedido a pedido.
  3. Normaliza:
       - descarta 'PEDIDOS EM ANDAMENTO' (consulta sem retorno de status)
       - corta o sufixo de área ("ENTREGA - LOGÍSTICA" -> "ENTREGA")
         p/ bater com o formato que a base das 7h grava em cFilaAtual
       - se o mesmo pedido vier de +1 parceiro, vence o encaminhamento
         mais recente
  4. Grava na aba StatusQuickTIM: pedido | fila | encaminhado_em | parceiro
     (o n8n QuickTIMSync, na LAN, lê essa aba e escreve no CRM + move o card)

  SEM Telegram, SEM estado local, SEM alerta. Roda uma vez e sai.
=====================================================================
"""

import os
import re
import sys
import time
import unicodedata

import requests
import gspread
from datetime import datetime
from google.oauth2.service_account import Credentials
from securid.sdtid import SdtidFile

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ─────────────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────────────
SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
ABA_ORIGEM     = "DadosRadar"       # lista de pedidos (output da base das 7h)
ABA_DESTINO    = "StatusQuickTIM"   # o n8n QuickTIMSync consome daqui
SERVICE_ACCOUNT = os.environ.get("GOOGLE_CREDENTIALS_FILE", "credentials.json")

URL_RADAR    = "https://radar.timbrasil.com.br/"
URL_QUICKTIM = "https://radar.timbrasil.com.br/radar-blue/sistema/chatUser.asp"
TERMOS_LOGIN_URL = ("iam-pf", "signon", "login", "authn")

TIPOS_OK = {"NOVO", "ADITIVO"}      # renegociação fica de fora (decisão Hugo)

# Roteamento: palavra_chave casada por SUBSTRING (uppercased) contra a
# coluna 'parceiro' da planilha. Define QUAL conta consulta o pedido.
PARCEIROS = [
    {"nome": "Serra",   "palavra_chave": "SERRA",   "login": "t3761125", "sdtid": "T3761125_001938495598.sdtid"},
    {"nome": "Campina", "palavra_chave": "CAMPINA", "login": "t3729525", "sdtid": "T3729525_001938489117.sdtid"},
    {"nome": "Alagoas", "palavra_chave": "ALAGOAS", "login": "t3748937", "sdtid": "T3748937_001938491397.sdtid"},
]

# ─────────────────────────────────────────────────────────────────
#  RSA (idêntico ao actions_runner — login headless automático)
# ─────────────────────────────────────────────────────────────────
def _verify_mac_ignorar(self, *a, **k):
    pass
SdtidFile.verify_mac = _verify_mac_ignorar

def gerar_token(sdtid_path, pin=1234):
    tok = SdtidFile(sdtid_path).get_token()
    tok.pin = pin
    return tok.now()

def criar_driver():
    import shutil
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    chrome = shutil.which("google-chrome") or shutil.which("chromium-browser") or shutil.which("chromium")
    if chrome:
        opts.binary_location = chrome
    chromedriver = shutil.which("chromedriver")
    if chromedriver:
        return webdriver.Chrome(service=Service(chromedriver), options=opts)
    from webdriver_manager.chrome import ChromeDriverManager
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

def fazer_login(driver, login, sdtid_path):
    token = gerar_token(sdtid_path)
    print(f"  🔐 Token gerado para {login.upper()}")
    try:
        driver.delete_all_cookies()
    except Exception:
        pass
    driver.get(URL_RADAR)
    time.sleep(5)
    campo = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "identifierInput")))
    campo.clear(); campo.send_keys(login)
    btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.ID, "signOnButton")))
    driver.execute_script("arguments[0].click()", btn); time.sleep(4)
    try:
        WebDriverWait(driver, 20).until(lambda d: "iam-pf" in d.current_url); time.sleep(3)
    except Exception:
        pass
    campo_token = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "password")))
    campo_token.send_keys(token); time.sleep(1)
    btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "signOnButton")))
    driver.execute_script("arguments[0].click()", btn); time.sleep(8)
    print(f"  ✅ Login OK — {driver.current_url[:60]}")

def sessao_ok(driver):
    url = (driver.current_url or "").lower()
    return not any(t in url for t in TERMOS_LOGIN_URL)

# ─────────────────────────────────────────────────────────────────
#  QUICKTIM — consulta 1 pedido (portado do monitor_radar, sem Telegram/estado)
# ─────────────────────────────────────────────────────────────────
def consultar_pedido(driver, numero_pedido):
    try:
        wait = WebDriverWait(driver, 15)
        driver.get(URL_QUICKTIM)
        time.sleep(3)

        campo_init = wait.until(EC.presence_of_element_located((By.ID, "messageTextBox-quicktim")))
        campo_init.clear(); campo_init.send_keys("oi"); campo_init.send_keys(Keys.RETURN)
        time.sleep(3)

        btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Pedidos em andamento')]")))
        btn.click(); time.sleep(2)
        try:
            wait.until(EC.presence_of_element_located((By.XPATH, "//span[contains(text(), 'Informe o número')]")))
            time.sleep(1)
        except Exception:
            time.sleep(2)

        campo = wait.until(EC.presence_of_element_located((By.ID, "messageTextBox-quicktim")))
        campo.clear(); campo.send_keys(numero_pedido); campo.send_keys(Keys.RETURN)

        ERROS_SERVIDOR = ["NO MOMENTO NAO CONSEGUIMOS", "FAVOR TENTAR NOVAMENTE"]
        MAX_RETRIES = 2
        for tentativa_retry in range(MAX_RETRIES):
            texto_anterior = ""
            tentativas = 0
            while tentativas < 15:
                time.sleep(2)
                respostas = driver.find_elements(By.CSS_SELECTOR, "span#msgbot.chat-quick-tim.pull-left")
                if not respostas:
                    tentativas += 1; continue
                texto_valido = None
                for resp in reversed(respostas):
                    t = resp.text.strip()
                    if numero_pedido in t and not any(inv in t.upper() for inv in ["GOSTARIA DE FALAR", "CONSULTAR"]):
                        texto_valido = t; break
                if not texto_valido:
                    tentativas += 1; continue
                tu = texto_valido.upper()
                if "PROCESSANDO" in tu or "AGUARDE" in tu:
                    tentativas += 1; continue
                if any(e in tu for e in ERROS_SERVIDOR):
                    print(f"    [retry {tentativa_retry+1}/{MAX_RETRIES}] erro servidor, aguardando 5s"); time.sleep(5); break
                if texto_valido == texto_anterior:
                    return texto_valido
                texto_anterior = texto_valido
                tentativas += 1
            else:
                respostas = driver.find_elements(By.CSS_SELECTOR, "span#msgbot.chat-quick-tim.pull-left")
                for resp in reversed(respostas):
                    t = resp.text.strip()
                    if numero_pedido in t and not any(e in t.upper() for e in ERROS_SERVIDOR):
                        return t
                continue
            # reenviar após erro de servidor
            if tentativa_retry < MAX_RETRIES - 1:
                try:
                    c = driver.find_element(By.ID, "messageTextBox-quicktim")
                    c.clear(); c.send_keys("oi"); c.send_keys(Keys.RETURN); time.sleep(2)
                    b = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Pedidos em andamento')]")))
                    b.click(); time.sleep(1.5)
                    c = wait.until(EC.presence_of_element_located((By.ID, "messageTextBox-quicktim")))
                    c.clear(); c.send_keys(numero_pedido); c.send_keys(Keys.RETURN)
                except Exception as e:
                    print(f"    erro ao reenviar: {e}")
        return None
    except Exception as e:
        print(f"  [selenium] erro {numero_pedido}: {e}")
        return None

# ─────────────────────────────────────────────────────────────────
#  LISTA DE PEDIDOS (da aba DadosRadar, por parceiro)
# ─────────────────────────────────────────────────────────────────
def _norm(s):
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().strip().lower()

def get_gspread():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT, scopes=scopes)
    return gspread.authorize(creds)

def carregar_dados():
    gc = get_gspread()
    ws = gc.open_by_key(SPREADSHEET_ID).worksheet(ABA_ORIGEM)
    return ws.get_all_values()

def pedidos_por_parceiro(dados, palavra_chave):
    if not dados or len(dados) < 2:
        return []
    headers = [_norm(h) for h in dados[0]]
    def col(pred):
        return next((i for i, h in enumerate(headers) if pred(h)), None)
    idx_pedido   = col(lambda h: h == "pedido")
    idx_fila     = col(lambda h: "fila" in h and "atual" in h)
    idx_tipo     = col(lambda h: "tipo" in h and "contrat" in h)
    idx_parceiro = col(lambda h: "parceiro" in h)          # pega 'parceiro (bd)' também
    idx_ativa    = col(lambda h: "ativa" in h)             # 'data de ativação'
    if idx_pedido is None or idx_parceiro is None:
        print("  [sheet] header pedido/parceiro não encontrado"); return []

    pk = palavra_chave.upper()
    out, vistos = [], set()
    for row in dados[1:]:
        def cell(i):
            return row[i].strip() if (i is not None and i < len(row)) else ""
        parceiro = cell(idx_parceiro).upper()
        if pk not in parceiro:
            continue
        tipo = cell(idx_tipo).upper()
        if idx_tipo is not None and tipo not in TIPOS_OK:
            continue
        if cell(idx_ativa):                    # tem data de ativação => já ativou, não consulta
            continue
        pedido = cell(idx_pedido)
        if pedido.endswith(".0"):
            pedido = pedido[:-2]
        if pedido and pedido not in vistos:
            vistos.add(pedido); out.append(pedido)
    return out

# ─────────────────────────────────────────────────────────────────
#  NORMALIZAÇÃO (gotchas: sufixo / andamento / merge)
# ─────────────────────────────────────────────────────────────────
SENTINEL = "PEDIDOS EM ANDAMENTO"
ROUTE_RE = re.compile(r"encaminhado para (.+?) em (\d{2})/(\d{2})/(\d{4}) às (\d{2}):(\d{2})", re.IGNORECASE)

def canonical_fila(fila):
    return fila.rsplit(" - ", 1)[0].strip() if " - " in fila else fila.strip()

def parse_resposta(texto):
    """Do texto do chat -> (fila_canonica, encaminhado_em_iso, dt) ou None se sem status."""
    if not texto:
        return None
    m = ROUTE_RE.search(texto)
    if not m:
        return None                         # sem 'encaminhado para' => sentinel/erro, descarta
    fila, d, mo, y, h, mi = m.groups()
    fila = fila.strip().upper()
    if fila == SENTINEL or not fila:
        return None
    dt = datetime(int(y), int(mo), int(d), int(h), int(mi))
    return canonical_fila(fila), dt.strftime("%Y-%m-%d %H:%M:00"), dt

# ─────────────────────────────────────────────────────────────────
#  ESCRITA na aba StatusQuickTIM
# ─────────────────────────────────────────────────────────────────
def subir_status(linhas):
    gc = get_gspread()
    sh = gc.open_by_key(SPREADSHEET_ID)
    try:
        aba = sh.worksheet(ABA_DESTINO)
    except gspread.WorksheetNotFound:
        aba = sh.add_worksheet(title=ABA_DESTINO, rows=1, cols=1)
    aba.clear()
    header = ["pedido", "fila", "encaminhado_em", "parceiro", "run_em"]
    aba.update([header] + linhas, value_input_option="USER_ENTERED")
    print(f"  ✅ {len(linhas)} status gravados em '{ABA_DESTINO}'")

# ─────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────
def main():
    run_em = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("=" * 55); print("  QUICKTIM STATUS — consulta 3x/dia"); print("=" * 55)

    dados = carregar_dados()
    resolvido = {}   # pedido -> {"fila","em","dt","parceiro"}

    for p in PARCEIROS:
        pedidos = pedidos_por_parceiro(dados, p["palavra_chave"])
        print(f"\n🌐 {p['nome']} ({p['login']}) — {len(pedidos)} pedido(s)")
        if not pedidos:
            continue
        driver = criar_driver()
        try:
            fazer_login(driver, p["login"], p["sdtid"])
            if not sessao_ok(driver):
                print(f"  ⚠️ sessão não logou para {p['nome']}, pulando"); continue
            for ped in pedidos:
                texto = consultar_pedido(driver, ped)
                parsed = parse_resposta(texto)
                if not parsed:
                    print(f"    {ped}: sem status"); continue
                fila, em, dt = parsed
                # merge: vence o encaminhamento mais recente
                if ped not in resolvido or dt > resolvido[ped]["dt"]:
                    resolvido[ped] = {"fila": fila, "em": em, "dt": dt, "parceiro": p["nome"]}
                print(f"    {ped}: {fila} (em {em})")
        finally:
            driver.quit()

    linhas = [[ped, v["fila"], v["em"], v["parceiro"], run_em] for ped, v in sorted(resolvido.items())]
    print(f"\n📋 {len(linhas)} pedidos com status")
    subir_status(linhas)
    print("\n🎉 QuickTIM status atualizado!")

if __name__ == "__main__":
    main()
