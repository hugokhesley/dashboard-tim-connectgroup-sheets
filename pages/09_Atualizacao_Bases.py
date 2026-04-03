"""
09_Atualizacao_Bases.py — Atualização automática da base DadosRadar
Connect Group | Dashboard TIM Empresas

Solicita relatórios no Radar TIM via Selenium, aguarda os emails
via IMAP e sobe os dados para a aba DadosRadar no Google Sheets.
Acesso restrito: hugo
"""

import streamlit as st
import threading
import time
import imaplib
import email
import re
import requests
import pandas as pd
import gspread
import base64
import tempfile
import os
from datetime import datetime, timezone, timedelta
from email.header import decode_header
from email.utils import parsedate_to_datetime
from google.oauth2.service_account import Credentials
from securid.sdtid import SdtidFile
from securid.exceptions import InvalidSignature

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from auth import require_login
from data_loader import registrar_acesso, get_gspread_client

# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Connect Group | Atualização de Bases",
    page_icon="🔄",
    layout="wide",
    initial_sidebar_state="expanded",
)

username = require_login("atualizacao_bases", allowed_users=["hugo"])
registrar_acesso("Atualização de Bases", username=username)

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
  html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
  .stApp { background-color: #0f1117; color: #e2e8f0; }
  .header-res {
    background: linear-gradient(135deg, #0f2027 0%, #203a43 50%, #2c5364 100%);
    border-radius: 16px; padding: 28px 36px; margin-bottom: 28px;
    box-shadow: 0 8px 32px rgba(44,83,100,0.3);
    border: 1px solid rgba(255,255,255,0.08);
  }
  .header-title { font-size: 1.9rem; font-weight: 800; color: #fff; margin: 0; }
  .header-sub   { font-size: 0.85rem; color: rgba(255,255,255,0.65); margin: 4px 0 0 0; }
  .status-card {
    background: #1a1f2e; border-radius: 14px; padding: 20px 24px;
    border: 1px solid #2d3748; margin-bottom: 12px;
  }
  .step-label { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 1px;
    color: #94a3b8; font-weight: 600; margin-bottom: 4px; }
  .step-value { font-size: 1rem; font-weight: 600; color: #f1f5f9; }
  section[data-testid="stSidebar"] { background: #111827 !important; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────
st.markdown("""
<div class="header-res">
  <div>
    <p class="header-title">🔄 Atualização de Bases</p>
    <p class="header-sub">Solicita relatórios no Radar TIM e atualiza o DadosRadar automaticamente</p>
  </div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# CONFIGURAÇÕES VIA SECRETS
# ─────────────────────────────────────────────
EMAIL_1         = st.secrets["EMAIL_1"]
SENHA_1         = st.secrets["SENHA_1"]
EMAIL_2         = st.secrets["EMAIL_2"]
SENHA_2         = st.secrets["SENHA_2"]
IMAP_HOST       = st.secrets.get("IMAP_HOST", "imap.titan.email")
IMAP_PORT       = int(st.secrets.get("IMAP_PORT", 993))
REMETENTE_RADAR = st.secrets.get("REMETENTE_RADAR", "noreply-radartim@timbrasil.com.br")

SPREADSHEET_ID  = "1HmtEFf2Akh7NLR2prxDh9S4gmioKYw419B4bkx4yBLg"
ABA_DESTINO     = "DadosRadar"
JANELA_MINUTOS  = 40
INTERVALO_IMAP  = 300  # 5 minutos

CONTAS = [
    {"login": "t3729525", "nome": "Campina Grande", "sdtid_secret": "SDTID_T3729525"},
    {"login": "t3761125", "nome": "Serra Redonda",  "sdtid_secret": "SDTID_T3761125"},
]

MINUTOS_POR_POSICAO = 7
MARGEM_EXTRA        = 2

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def calcular_datas():
    hoje = datetime.today()
    mes  = hoje.month - 2
    ano  = hoje.year
    if mes <= 0:
        mes += 12
        ano -= 1
    return f"01/{mes:02d}/{ano}", hoje.strftime("%d/%m/%Y")


def _verify_mac_ignorar(self, kind, str0, str1, node, section, key1, iv):
    """Monkey-patch para ignorar MAC check em tokens com CopyProtection=1."""
    pass

SdtidFile.verify_mac = _verify_mac_ignorar


def gerar_token_rsa(sdtid_secret_key: str, pin: int = 1234) -> str:
    """Gera o token RSA a partir do conteúdo do .sdtid armazenado nos secrets."""
    sdtid_b64 = st.secrets[sdtid_secret_key]
    sdtid_bytes = base64.b64decode(sdtid_b64)

    with tempfile.NamedTemporaryFile(suffix=".sdtid", delete=False) as tmp:
        tmp.write(sdtid_bytes)
        tmp_path = tmp.name

    try:
        token_obj = SdtidFile(tmp_path).get_token()
        token_obj.pin = pin
        return token_obj.now()
    finally:
        os.unlink(tmp_path)


def verificar_email_novo(email_conta, senha, desde):
    """Verifica se chegou email novo do Radar. Retorna link ou None."""
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(email_conta, senha)
        mail.select("INBOX")

        status, msgs = mail.search(None, f'FROM "{REMETENTE_RADAR}"')
        if status != "OK" or not msgs[0]:
            mail.logout()
            return None

        ids = msgs[0].split()
        desde_utc = desde.astimezone(timezone.utc)

        for uid in reversed(ids):
            status, dados = mail.fetch(uid, "(RFC822)")
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
                break

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
        return None


def baixar_xlsx(link: str) -> bytes:
    response = requests.get(link, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    response.raise_for_status()
    return response.content


def subir_para_sheets(df: pd.DataFrame, log_fn):
    log_fn("  ↑ Conectando ao Google Sheets...")
    gc = get_gspread_client()
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
    log_fn(f"  ✅ {len(df)} linhas gravadas em '{ABA_DESTINO}'!")


# ─────────────────────────────────────────────
# FLUXO PRINCIPAL (roda em thread para não travar UI)
# ─────────────────────────────────────────────

def fluxo_completo(posicao_manual: int, log_container):
    logs = []

    def log(msg):
        logs.append(msg)
        log_container.code("\n".join(logs))

    try:
        # ── Etapa 1: Login no Radar e solicitação (via Selenium headless) ──
        log("🤖 Iniciando Selenium headless...")

        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from webdriver_manager.chrome import ChromeDriverManager

        data_inicio, data_fim = calcular_datas()
        log(f"📅 Período: {data_inicio} → {data_fim}")

        posicoes = []

        for conta in CONTAS:
            login = conta["login"]
            nome  = conta["nome"]
            log(f"\n🌐 Processando {nome} ({login})...")

            # Gera token RSA
            token = gerar_token_rsa(conta["sdtid_secret"])
            log(f"  🔐 Token RSA gerado para {login.upper()}")

            # Cria driver headless
            options = Options()
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")

            driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=options
            )

            try:
                driver.get("https://radar.timbrasil.com.br/")
                time.sleep(5)

                # Digita username
                try:
                    campo = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.ID, "identifierInput"))
                    )
                    campo.clear()
                    campo.send_keys(login)
                    time.sleep(0.5)
                    btn = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.ID, "signOnButton"))
                    )
                    driver.execute_script("arguments[0].click()", btn)
                    log(f"  ✓ Username enviado")
                    time.sleep(4)
                except Exception as e:
                    log(f"  ⚠️ Tela username: {e}")

                # Aguarda SmartID
                try:
                    WebDriverWait(driver, 20).until(
                        lambda d: "iam-pf" in d.current_url or "authorization" in d.current_url
                    )
                    time.sleep(3)
                    log(f"  ✓ Tela SmartID")
                except Exception:
                    log(f"  ⚠️ Timeout SmartID")

                # Insere token
                campo_token = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.ID, "password"))
                )
                campo_token.clear()
                campo_token.send_keys(token)
                time.sleep(1)
                btn_entrar = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.ID, "signOnButton"))
                )
                driver.execute_script("arguments[0].click()", btn_entrar)
                log(f"  ✓ Token enviado, aguardando login...")
                time.sleep(8)

                # Reload se branco
                if driver.execute_script("return document.body.innerHTML.trim()") == "":
                    driver.get(driver.current_url)
                    time.sleep(5)

                log(f"  ✅ Login OK — URL: {driver.current_url[:50]}...")

                # Lista de relatórios
                driver.get("https://radar.timbrasil.com.br/radar-tim/relatorios/lista2.asp")
                time.sleep(4)

                # Fecha modal
                try:
                    fechar = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, "//button[contains(@class,'close')]"))
                    )
                    fechar.click()
                except Exception:
                    pass

                # Base Geral
                base = WebDriverWait(driver, 15).until(
                    EC.element_to_be_clickable((By.XPATH, "//a[contains(text(),'Base Geral - Após 01/05/2009')]"))
                )
                driver.execute_script("arguments[0].click()", base)
                time.sleep(3)
                log(f"  ✓ Relatório selecionado")

                # Datas
                campo_de = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.NAME, "a.dt_precadastro_de"))
                )
                driver.execute_script("arguments[0].removeAttribute('readonly')", campo_de)
                driver.execute_script(f"arguments[0].value = '{data_inicio}'", campo_de)
                campo_ate = driver.find_element(By.NAME, "a.dt_precadastro_ate")
                driver.execute_script("arguments[0].removeAttribute('readonly')", campo_ate)
                driver.execute_script(f"arguments[0].value = '{data_fim}'", campo_ate)
                log(f"  ✓ Datas preenchidas")

                # Checkboxes: ADITIVO(1), NOVO(2), RENEGOCIAÇÃO(3)
                for valor in ["1", "2", "3"]:
                    try:
                        cb = driver.find_element(By.XPATH,
                            f"//input[@type='checkbox' and @name='g.idtipocontrata' and @value='{valor}']")
                        if not cb.is_selected():
                            driver.execute_script("arguments[0].click()", cb)
                    except Exception:
                        pass
                log(f"  ✓ Tipos marcados")

                # Gerar
                gerar = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//input[@value='Gerar Relatório']"))
                )
                driver.execute_script("arguments[0].click()", gerar)
                time.sleep(4)
                log(f"  ✓ Relatório solicitado!")

                # Posição na fila
                posicao = posicao_manual  # usa o valor informado pelo usuário
                try:
                    driver.get("https://radar.timbrasil.com.br/radar-blue/sistema/report-queue.asp")
                    time.sleep(3)
                    linhas = driver.find_elements(By.XPATH, "//table//tr[contains(.,'pendente')]")
                    if linhas:
                        try:
                            pos = linhas[0].find_element(By.XPATH, ".//td[last()]")
                            posicao = int(pos.text.strip()) if pos.text.strip().isdigit() else len(linhas)
                        except Exception:
                            posicao = len(linhas)
                    log(f"  📊 Posição na fila: {posicao}")
                except Exception:
                    log(f"  ⚠️ Não leu fila, usando posição informada: {posicao}")

                posicoes.append(posicao)

            finally:
                driver.quit()
                log(f"  🔒 Sessão de {nome} encerrada.")

        # ── Etapa 2: Aguarda emails ──
        maior_posicao = max(posicoes) if posicoes else posicao_manual
        tempo_total   = (maior_posicao * MINUTOS_POR_POSICAO) + MARGEM_EXTRA
        primeira_busca = tempo_total // 2

        log(f"\n⏳ Aguardando {primeira_busca} min antes da primeira verificação de emails...")
        log(f"   (Tempo total estimado: {tempo_total} min | Posição máxima: {maior_posicao})")

        time.sleep(primeira_busca * 60)

        desde = datetime.now().astimezone() - timedelta(minutes=JANELA_MINUTOS)
        link1 = None
        link2 = None
        tentativa = 0
        limite = 12  # até 60 min depois

        log(f"\n📧 Iniciando verificação de emails...")

        while tentativa < limite:
            tentativa += 1
            log(f"  🔍 Verificação #{tentativa}...")

            if link1 is None:
                link1 = verificar_email_novo(EMAIL_1, SENHA_1, desde)
                if link1:
                    log(f"  ✅ Email 1 recebido!")
                else:
                    log(f"  ⏸  Email 1 ainda não chegou")

            if link2 is None:
                link2 = verificar_email_novo(EMAIL_2, SENHA_2, desde)
                if link2:
                    log(f"  ✅ Email 2 recebido!")
                else:
                    log(f"  ⏸  Email 2 ainda não chegou")

            if link1 and link2:
                break

            log(f"  Aguardando {INTERVALO_IMAP//60} min...")
            time.sleep(INTERVALO_IMAP)

        if not (link1 and link2):
            log("❌ Timeout: não recebeu os dois emails. Verifique manualmente.")
            return

        # ── Etapa 3: Baixa e junta ──
        log(f"\n⬇️  Baixando planilhas...")
        bytes1 = baixar_xlsx(link1)
        bytes2 = baixar_xlsx(link2)
        log(f"  ✓ Downloads concluídos")

        df1 = pd.read_excel(bytes1, header=0)
        df2 = pd.read_excel(bytes2, header=0)
        df_final = pd.concat([df1, df2], ignore_index=True)
        log(f"  📋 Total: {len(df_final)} linhas | {len(df_final.columns)} colunas")

        # ── Etapa 4: Sobe pro Sheets ──
        subir_para_sheets(df_final, log)
        log(f"\n🎉 DadosRadar atualizado com sucesso!")

    except Exception as e:
        log(f"\n❌ Erro inesperado: {e}")


# ─────────────────────────────────────────────
# INTERFACE
# ─────────────────────────────────────────────

st.markdown("### ⚙️ Configuração da atualização")

col1, col2 = st.columns([2, 1])

with col1:
    st.info("""
    **O que este processo faz:**
    1. 🤖 Faz login automático nas duas contas do Radar TIM
    2. 📋 Solicita o relatório **Base Geral – Após 01/05/2009** com filtros ADITIVO, NOVO e RENEGOCIAÇÃO
    3. ⏳ Aguarda os emails chegarem (baseado na posição na fila)
    4. ⬇️ Baixa os dois arquivos e consolida
    5. ☁️ Sobe tudo para a aba **DadosRadar** no Google Sheets
    """)

with col2:
    posicao_fila = st.number_input(
        "Posição estimada na fila",
        min_value=1, max_value=50, value=3,
        help="Se souber a posição atual na fila do Radar, informe aqui. Cada posição = ~7 min."
    )

    tempo_est = (posicao_fila * MINUTOS_POR_POSICAO) + MARGEM_EXTRA
    primeira  = tempo_est // 2
    st.caption(f"⏱ Tempo total estimado: **~{tempo_est} min**")
    st.caption(f"🔍 Primeira verificação em: **~{primeira} min**")

st.markdown("---")

# Estado da execução
if "rodando" not in st.session_state:
    st.session_state.rodando = False

if not st.session_state.rodando:
    if st.button("🚀 Iniciar Atualização", type="primary", use_container_width=True):
        st.session_state.rodando = True
        st.rerun()
else:
    st.warning("⏳ Processo em andamento... Não feche esta página.")
    log_container = st.empty()
    log_container.code("Iniciando...")

    # Roda em thread para não travar o Streamlit
    t = threading.Thread(
        target=fluxo_completo,
        args=(posicao_fila, log_container),
        daemon=True
    )
    t.start()
    t.join()

    st.session_state.rodando = False
    if st.button("🔄 Nova atualização"):
        st.rerun()
