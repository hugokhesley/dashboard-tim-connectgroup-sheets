"""
09_Atualizacao_Bases.py — Atualização automática da base DadosRadar
Connect Group | Dashboard TIM Empresas
Acesso restrito: hugo
"""

import streamlit as st
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

username = require_login("atualizacao_bases")
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
  section[data-testid="stSidebar"] { background: #111827 !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="header-res">
  <div>
    <p class="header-title">🔄 Atualização de Bases</p>
    <p class="header-sub">Solicita relatórios no Radar TIM e atualiza o DadosRadar automaticamente</p>
  </div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# SECRETS
# ─────────────────────────────────────────────
EMAIL_1         = st.secrets["email"]["EMAIL_1"]
SENHA_1         = st.secrets["email"]["SENHA_1"]
EMAIL_2         = st.secrets["email"]["EMAIL_2"]
SENHA_2         = st.secrets["email"]["SENHA_2"]
IMAP_HOST       = st.secrets["email"].get("IMAP_HOST", "imap.titan.email")
IMAP_PORT       = int(st.secrets["email"].get("IMAP_PORT", 993))
REMETENTE_RADAR = st.secrets["email"].get("REMETENTE_RADAR", "noreply-radartim@timbrasil.com.br")
ASSUNTO_RADAR   = "O Radar já terminou de gerar o relatório"

SPREADSHEET_ID  = "1HmtEFf2Akh7NLR2prxDh9S4gmioKYw419B4bkx4yBLg"
ABA_DESTINO     = "DadosRadar"
JANELA_MINUTOS  = 40
INTERVALO_IMAP  = 300

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


# Monkey-patch para ignorar MAC check
def _verify_mac_ignorar(self, kind, str0, str1, node, section, key1, iv):
    pass
SdtidFile.verify_mac = _verify_mac_ignorar


def gerar_token_rsa(sdtid_secret_key: str, pin: int = 1234) -> str:
    sdtid_b64   = st.secrets["email"][sdtid_secret_key]
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
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(email_conta, senha)

        # Lista todas as pastas disponíveis para buscar na certa
        _, pastas_raw = mail.list()
        pastas = []
        for p in pastas_raw:
            if p:
                nome = p.decode(errors="ignore").split('"/"')[-1].strip().strip('"')
                pastas.append(nome)

        # Prioriza INBOX e qualquer pasta que contenha o Gmail vinculado
        caixas_buscar = ["INBOX"]
        for p in pastas:
            if "gmail" in p.lower() or "totodecasa" in p.lower() or "google" in p.lower() or "@gmail" in p.lower():
                if p not in caixas_buscar:
                    caixas_buscar.append(p)

        desde_utc = desde.astimezone(timezone.utc)
        data_imap = desde_utc.strftime("%d-%b-%Y")

        for caixa in caixas_buscar:
            try:
                # Sempre usa aspas para pastas com caracteres especiais (@, espaços)
                status_sel, _ = mail.select(f'"{caixa}"')
                if status_sel != "OK":
                    continue
            except Exception:
                continue

            status, msgs = mail.search(None, f'SINCE "{data_imap}"')
            if status != "OK" or not msgs[0]:
                continue

            ids = msgs[0].split()

            for uid in reversed(ids):
                status, dados = mail.fetch(uid, "(RFC822)")
                msg = email.message_from_bytes(dados[0][1])

                # Verifica data
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

                # Filtra por assunto no Python
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

                # Extrai o link do corpo
                for parte in msg.walk():
                    if parte.get_content_type() in ("text/plain", "text/html"):
                        corpo = parte.get_payload(decode=True).decode(errors="ignore")
                        match = re.search(r'https://radar\.timbrasil\.com\.br/[^\s"<>\)]+', corpo)
                        if match:
                            mail.logout()
                            return match.group(0).strip()

        mail.logout()
        return None
    except Exception:
        return None


def baixar_xlsx(link: str) -> bytes:
    r = requests.get(link, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    r.raise_for_status()
    return r.content


def subir_para_sheets(df: pd.DataFrame):
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
    return len(df)


def fazer_login_radar(driver, login, nome, token):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    driver.get("https://radar.timbrasil.com.br/")
    time.sleep(5)

    try:
        campo = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "identifierInput"))
        )
        campo.clear()
        campo.send_keys(login)
        btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.ID, "signOnButton")))
        driver.execute_script("arguments[0].click()", btn)
        time.sleep(4)
    except Exception:
        pass

    try:
        WebDriverWait(driver, 20).until(
            lambda d: "iam-pf" in d.current_url or "authorization" in d.current_url
        )
        time.sleep(3)
    except Exception:
        pass

    campo_token = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.ID, "password"))
    )
    campo_token.clear()
    campo_token.send_keys(token)
    time.sleep(1)
    btn_entrar = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "signOnButton")))
    driver.execute_script("arguments[0].click()", btn_entrar)
    time.sleep(8)

    if driver.execute_script("return document.body.innerHTML.trim()") == "":
        driver.get(driver.current_url)
        time.sleep(5)


def solicitar_relatorio_radar(driver, data_inicio, data_fim, log_fn=None):
    def _log(msg):
        if log_fn:
            log_fn(msg)

    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    _log(f"  → Navegando para lista de relatórios...")
    driver.get("https://radar.timbrasil.com.br/radar-tim/relatorios/lista2.asp")
    time.sleep(6)
    _log(f"  → URL: {driver.current_url[:70]}")

    try:
        fechar = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(@class,'close')]"))
        )
        fechar.click()
    except Exception:
        pass

    _log(f"  → Buscando link Base Geral...")
    base = WebDriverWait(driver, 25).until(
        EC.element_to_be_clickable((By.XPATH, "//a[contains(text(),'Base Geral - Após 01/05/2009')]"))
    )
    driver.execute_script("arguments[0].click()", base)
    time.sleep(5)
    _log(f"  → Clicou Base Geral. URL: {driver.current_url[:70]}")

    _log(f"  → Aguardando campo data...")
    campo_de = WebDriverWait(driver, 25).until(
        EC.presence_of_element_located((By.NAME, "a.dt_precadastro_de"))
    )
    driver.execute_script("arguments[0].removeAttribute('readonly')", campo_de)
    driver.execute_script(f"arguments[0].value = '{data_inicio}'", campo_de)
    campo_ate = driver.find_element(By.NAME, "a.dt_precadastro_ate")
    driver.execute_script("arguments[0].removeAttribute('readonly')", campo_ate)
    driver.execute_script(f"arguments[0].value = '{data_fim}'", campo_ate)
    _log(f"  → Datas: {data_inicio} → {data_fim}")

    for valor in ["1", "2", "3"]:
        try:
            cb = driver.find_element(By.XPATH,
                f"//input[@type='checkbox' and @name='g.idtipocontrata' and @value='{valor}']")
            if not cb.is_selected():
                driver.execute_script("arguments[0].click()", cb)
        except Exception:
            pass
    _log(f"  → Checkboxes marcados")

    _log(f"  → Clicando Gerar Relatório...")
    gerar = WebDriverWait(driver, 15).until(
        EC.element_to_be_clickable((By.XPATH, "//input[@value='Gerar Relatório']"))
    )
    driver.execute_script("arguments[0].click()", gerar)
    time.sleep(5)
    _log(f"  → Enviado! URL: {driver.current_url[:70]}")

    posicao = 1
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
        _log(f"  → Posição na fila: {posicao}")
    except Exception:
        _log(f"  ⚠️ Não leu fila")

    return posicao


# ─────────────────────────────────────────────
# INTERFACE
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
# SEÇÃO: ACESSO RÁPIDO AO RADAR
# ─────────────────────────────────────────────

st.markdown("### 🌐 Acesso Rápido aos Sistemas TIM")
st.caption("Clique para abrir o sistema já logado na conta desejada (requer script local instalado no PC)")

# Sistemas disponíveis
SISTEMAS_DISPONIVEIS = {
    "radar":   {"label": "📡 Radar TIM",  "emoji": "📡"},
    "phoenix": {"label": "🔥 Phoenix",    "emoji": "🔥"},
}

# Carrega contas do Google Sheets
@st.cache_data(ttl=30, show_spinner=False)
def carregar_contas_radar():
    try:
        gc = get_gspread_client()
        planilha = gc.open_by_key(SPREADSHEET_ID)
        try:
            aba = planilha.worksheet("ContasRadar")
            dados = aba.get_all_records()
            return dados
        except gspread.WorksheetNotFound:
            aba = planilha.add_worksheet(title="ContasRadar", rows=20, cols=3)
            aba.update([
                ["login", "nome"],
                ["t3729525", "Campina Grande"],
                ["t3761125", "Serra Redonda"],
            ])
            return [
                {"login": "t3729525", "nome": "Campina Grande"},
                {"login": "t3761125", "nome": "Serra Redonda"},
            ]
    except Exception as e:
        st.warning(f"Não foi possível carregar contas: {e}")
        return []

def salvar_contas_radar(contas: list):
    gc = get_gspread_client()
    planilha = gc.open_by_key(SPREADSHEET_ID)
    try:
        aba = planilha.worksheet("ContasRadar")
    except gspread.WorksheetNotFound:
        aba = planilha.add_worksheet(title="ContasRadar", rows=20, cols=3)
    aba.clear()
    dados = [["login", "nome"]] + [[c["login"], c["nome"]] for c in contas]
    aba.update(dados)
    st.cache_data.clear()

contas_radar = carregar_contas_radar()

# Tabs por sistema
tabs_sistemas = st.tabs([info["label"] for info in SISTEMAS_DISPONIVEIS.values()])

for tab, (sistema, info) in zip(tabs_sistemas, SISTEMAS_DISPONIVEIS.items()):
    with tab:
        if contas_radar:
            cols = st.columns(min(len(contas_radar), 4))
            for i, conta in enumerate(contas_radar):
                with cols[i % 4]:
                    login = conta.get("login", "")
                    nome  = conta.get("nome", login)
                    url_protocolo = f"radar-login://{sistema}/{login}"
                    st.link_button(
                        f"{info['emoji']} {nome}\n`{login}`",
                        url=url_protocolo,
                        use_container_width=True,
                    )
        else:
            st.info("Nenhuma conta cadastrada ainda.")

# Gerenciamento de contas
with st.expander("⚙️ Gerenciar contas"):
    st.caption("Adicione ou remova logins — valem para todos os sistemas")

    col_a, col_b, col_c = st.columns([2, 3, 1])
    with col_a:
        novo_login = st.text_input("Login (ex: t3729525)", key="novo_login_input").strip().lower()
    with col_b:
        novo_nome  = st.text_input("Nome da cidade/regional", key="novo_nome_input").strip()
    with col_c:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("➕ Adicionar", use_container_width=True):
            if novo_login and novo_nome:
                logins_existentes = [c["login"] for c in contas_radar]
                if novo_login in logins_existentes:
                    st.warning(f"Login `{novo_login}` já existe.")
                else:
                    contas_radar.append({"login": novo_login, "nome": novo_nome})
                    salvar_contas_radar(contas_radar)
                    st.success(f"✅ `{novo_login}` adicionado!")
                    st.rerun()
            else:
                st.warning("Preencha o login e o nome.")

    if contas_radar:
        st.markdown("**Remover conta:**")
        opcoes = {f"{c['nome']} ({c['login']})": c["login"] for c in contas_radar}
        remover_sel = st.selectbox("Selecione para remover", ["—"] + list(opcoes.keys()), key="remover_sel")
        if remover_sel != "—":
            if st.button("🗑️ Remover conta selecionada", type="secondary"):
                login_rem = opcoes[remover_sel]
                contas_radar = [c for c in contas_radar if c["login"] != login_rem]
                salvar_contas_radar(contas_radar)
                st.success(f"✅ Conta `{login_rem}` removida!")
                st.rerun()

st.markdown("""
<div style="background:#1a1f2e;border-radius:10px;padding:12px 16px;margin:8px 0 20px 0;
    border:1px solid #2d3748;font-size:0.78rem;color:#64748b;">
    💡 <b>Como funciona:</b> Clique em qualquer botão → Chrome abre e faz login automático no sistema escolhido.
    Requer o <code>radar_login_handler.py</code> instalado localmente
    (execute <code>registrar_protocolo.bat</code> como Administrador uma vez).
</div>
""", unsafe_allow_html=True)

st.markdown("---")
st.markdown("### ⚙️ Configuração da Atualização Automática")

# ── Modo de execução ──────────────────────────────────────────────
modo = st.radio(
    "Modo de execução:",
    ["🚀 GitHub Actions (recomendado — roda na nuvem, pode fechar a aba)",
     "🖥️ Streamlit (roda aqui — mantenha a aba aberta)"],
    key="modo_execucao"
)

usa_github_actions = "GitHub Actions" in modo

if usa_github_actions:
    st.success("✅ **Modo recomendado!** O processo roda no servidor do GitHub — você pode fechar esta aba tranquilamente.")

    def disparar_github_actions(posicao: int) -> bool:
        """Dispara o workflow via API do GitHub."""
        try:
            github_token = st.secrets.get("GITHUB_PAT", "")
            github_repo  = st.secrets.get("GITHUB_REPO", "hugokhesley/dashboard-tim-connectgroup-sheets")
            workflow_id  = "atualizar_dados_radar.yml"

            if not github_token:
                st.error("❌ Secret `GITHUB_PAT` não encontrado ou vazio no Streamlit.")
                return False

            url = f"https://api.github.com/repos/{github_repo}/actions/workflows/{workflow_id}/dispatches"
            headers = {
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28"
            }
            payload = {
                "ref": "main",
                "inputs": {"posicao_fila": str(posicao)}
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=15)

            if resp.status_code != 204:
                st.error(f"❌ GitHub API retornou status {resp.status_code}: {resp.text}")
                return False

            return True
        except Exception as e:
            st.error(f"Erro ao disparar workflow: {e}")
            return False

    col1, col2 = st.columns([2, 1])
    with col1:
        st.info("""
        **O que este processo faz:**
        1. 🤖 Login automático nas duas contas do Radar TIM
        2. 📋 Solicita **Base Geral – Após 01/05/2009** com filtros ADITIVO, NOVO e RENEGOCIAÇÃO
        3. ⏳ Aguarda os emails chegarem automaticamente
        4. ⬇️ Baixa os dois arquivos e consolida
        5. ☁️ Sobe para a aba **DadosRadar** no Google Sheets
        """)
    with col2:
        posicao_fila = st.number_input(
            "Posição estimada na fila",
            min_value=1, max_value=100, value=3,
            help="Cada posição ≈ 7 min"
        )
        tempo_est = (posicao_fila * MINUTOS_POR_POSICAO) + MARGEM_EXTRA
        st.caption(f"⏱ Tempo total: **~{tempo_est} min**")

    st.markdown("---")

    if st.button("🚀 Iniciar Atualização via GitHub Actions", type="primary", use_container_width=True):
        with st.spinner("Disparando workflow..."):
            ok = disparar_github_actions(posicao_fila)
        if ok:
            st.success("""
            ✅ **Workflow iniciado com sucesso!**

            O processo está rodando no servidor do GitHub.
            Você pode **fechar esta aba** — o DadosRadar será atualizado automaticamente.

            Acompanhe o progresso em:
            [github.com/hugokhesley/dashboard-tim-connectgroup-sheets/actions](https://github.com/hugokhesley/dashboard-tim-connectgroup-sheets/actions)
            """)
        else:
            st.error("❌ Falha ao disparar o workflow. Verifique o secret `GITHUB_PAT` no Streamlit.")

    st.markdown("---")

# ── Modo Streamlit (aba aberta) ──────────────────────────────────
if not usa_github_actions:
    col1, col2 = st.columns([2, 1])
    with col1:
        st.info("""
        **O que este processo faz:**
        1. 🤖 Login automático nas duas contas do Radar TIM (headless)
        2. 📋 Solicita **Base Geral – Após 01/05/2009** com filtros ADITIVO, NOVO e RENEGOCIAÇÃO
        3. ⏳ Aguarda os emails chegarem
        4. ⬇️ Baixa os dois arquivos e consolida
        5. ☁️ Sobe para a aba **DadosRadar** no Google Sheets
        """)
        st.warning("⚠️ Mantenha esta aba aberta durante todo o processo.")
    with col2:
        posicao_fila = st.number_input(
            "Posição estimada na fila",
            min_value=1, max_value=50, value=3,
            help="Cada posição ≈ 7 min"
        )
        tempo_est = (posicao_fila * MINUTOS_POR_POSICAO) + MARGEM_EXTRA
        primeira  = tempo_est // 2
        st.caption(f"⏱ Tempo total: **~{tempo_est} min**")
        st.caption(f"🔍 Primeira verificação: **~{primeira} min**")

    st.markdown("---")

# Para o modo GitHub Actions aqui — não mostra o fluxo Streamlit
if usa_github_actions:
    st.stop()

if "etapa" not in st.session_state:
    st.session_state.etapa = "idle"
if "logs" not in st.session_state:
    st.session_state.logs = []
if "posicoes" not in st.session_state:
    st.session_state.posicoes = []
if "conta_idx" not in st.session_state:
    st.session_state.conta_idx = 0
if "link1" not in st.session_state:
    st.session_state.link1 = None
if "link2" not in st.session_state:
    st.session_state.link2 = None
if "desde" not in st.session_state:
    st.session_state.desde = None
if "tentativa_imap" not in st.session_state:
    st.session_state.tentativa_imap = 0
if "posicao_fila_val" not in st.session_state:
    st.session_state.posicao_fila_val = 3


def add_log(msg):
    st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def mostrar_logs():
    if st.session_state.logs:
        st.code("\n".join(st.session_state.logs), language=None)


# ── Botão de início ──
if st.session_state.etapa == "idle":
    if st.button("🚀 Iniciar Atualização", type="primary", use_container_width=True):
        st.session_state.etapa = "selenium"
        st.session_state.logs = []
        st.session_state.posicoes = []
        st.session_state.conta_idx = 0
        st.session_state.link1 = None
        st.session_state.link2 = None
        st.session_state.desde = datetime.now().astimezone() - timedelta(minutes=JANELA_MINUTOS)
        st.session_state.tentativa_imap = 0
        st.session_state.posicao_fila_val = posicao_fila
        add_log("🚀 Processo iniciado!")
        st.rerun()

# ── Etapa: Selenium ──
elif st.session_state.etapa == "selenium":
    st.warning("⏳ Fazendo login e solicitando relatórios no Radar TIM...")
    mostrar_logs()

    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager

        data_inicio, data_fim = calcular_datas()
        add_log(f"📅 Período: {data_inicio} → {data_fim}")

        for i, conta in enumerate(CONTAS):
            login = conta["login"]
            nome  = conta["nome"]
            add_log(f"🌐 Processando {nome} ({login})...")

            token = gerar_token_rsa(conta["sdtid_secret"])
            add_log(f"  🔐 Token RSA gerado")

            options = Options()
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")

            import shutil
            chromium = shutil.which("chromium") or shutil.which("chromium-browser")
            chromedriver = shutil.which("chromedriver")

            if chromium and chromedriver:
                options.binary_location = chromium
                driver = webdriver.Chrome(
                    service=Service(chromedriver),
                    options=options
                )
            else:
                from webdriver_manager.chrome import ChromeDriverManager
                from webdriver_manager.core.os_manager import ChromeType
                driver = webdriver.Chrome(
                    service=Service(
                        ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install()
                    ),
                    options=options
                )

            try:
                fazer_login_radar(driver, login, nome, token)
                add_log(f"  ✅ Login OK")
                posicao = solicitar_relatorio_radar(driver, data_inicio, data_fim, log_fn=add_log)
                add_log(f"  ✓ Relatório solicitado! Posição na fila: {posicao}")
                st.session_state.posicoes.append(posicao)
            except Exception as e:
                add_log(f"  ❌ Erro: {e}")
                st.session_state.posicoes.append(st.session_state.posicao_fila_val)
            finally:
                driver.quit()
                add_log(f"  🔒 Sessão encerrada")

        # Calcula espera
        maior = max(st.session_state.posicoes) if st.session_state.posicoes else st.session_state.posicao_fila_val
        tempo_total  = (maior * MINUTOS_POR_POSICAO) + MARGEM_EXTRA
        primeira_min = tempo_total // 2

        add_log(f"📊 Posição máxima: {maior} | Espera total: ~{tempo_total} min")
        add_log(f"⏳ Aguardando {primeira_min} min antes da primeira verificação de email...")

        st.session_state.espera_ate = (datetime.now() + timedelta(minutes=primeira_min)).isoformat()
        st.session_state.etapa = "aguardando"

    except Exception as e:
        add_log(f"❌ Erro no Selenium: {e}")
        st.session_state.etapa = "erro"

    st.rerun()

# ── Etapa: Aguardando ──
elif st.session_state.etapa == "aguardando":
    espera_ate = datetime.fromisoformat(st.session_state.espera_ate)
    restante   = int((espera_ate - datetime.now()).total_seconds())

    if restante > 0:
        mins = restante // 60
        segs = restante % 60
        st.warning(f"⏳ Aguardando... {mins}m {segs}s para primeira verificação de email")
        mostrar_logs()

        # Botão para pular o countdown
        if st.button("⚡ Já chegou! Verificar emails agora", type="primary", use_container_width=True):
            add_log("⚡ Verificação antecipada solicitada!")
            st.session_state.etapa = "imap"
            st.rerun()

        time.sleep(30)
        st.rerun()
    else:
        add_log("🔍 Iniciando verificação de emails...")
        st.session_state.etapa = "imap"
        st.rerun()

# ── Etapa: IMAP ──
elif st.session_state.etapa == "imap":
    st.warning("📧 Verificando emails...")
    mostrar_logs()

    st.session_state.tentativa_imap += 1
    add_log(f"🔍 Verificação #{st.session_state.tentativa_imap}...")

    if st.session_state.link1 is None:
        link = verificar_email_novo(EMAIL_1, SENHA_1, st.session_state.desde)
        if link:
            st.session_state.link1 = link
            add_log("  ✅ Email 1 recebido!")
        else:
            add_log(f"  ⏸  Email 1 ainda não chegou ({EMAIL_1})")

    if st.session_state.link2 is None:
        link = verificar_email_novo(EMAIL_2, SENHA_2, st.session_state.desde)
        if link:
            st.session_state.link2 = link
            add_log("  ✅ Email 2 recebido!")
        else:
            add_log(f"  ⏸  Email 2 ainda não chegou ({EMAIL_2})")

    if st.session_state.link1 and st.session_state.link2:
        add_log("🎯 Ambos os emails recebidos!")
        st.session_state.etapa = "download"
        st.rerun()
    elif st.session_state.tentativa_imap >= 12:
        add_log("❌ Timeout: emails não chegaram em 60 min.")
        st.session_state.etapa = "erro"
        st.rerun()
    else:
        add_log(f"  Próxima verificação em {INTERVALO_IMAP//60} min...")
        time.sleep(INTERVALO_IMAP)
        st.rerun()

# ── Etapa: Download e Upload ──
elif st.session_state.etapa == "download":
    st.warning("⬇️ Baixando planilhas e subindo para o Sheets...")
    mostrar_logs()

    try:
        add_log("⬇️ Baixando planilha 1...")
        bytes1 = baixar_xlsx(st.session_state.link1)
        add_log("⬇️ Baixando planilha 2...")
        bytes2 = baixar_xlsx(st.session_state.link2)

        import io
        df1 = pd.read_excel(io.BytesIO(bytes1), header=0)
        df2 = pd.read_excel(io.BytesIO(bytes2), header=0)
        df_final = pd.concat([df1, df2], ignore_index=True)
        add_log(f"📋 Total: {len(df_final)} linhas | {len(df_final.columns)} colunas")

        add_log("☁️ Subindo para o Google Sheets...")
        total = subir_para_sheets(df_final)
        add_log(f"✅ {total} linhas gravadas em '{ABA_DESTINO}'!")

        st.session_state.etapa = "concluido"
    except Exception as e:
        add_log(f"❌ Erro: {e}")
        st.session_state.etapa = "erro"

    st.rerun()

# ── Concluído ──
elif st.session_state.etapa == "concluido":
    st.success("🎉 DadosRadar atualizado com sucesso!")
    mostrar_logs()
    if st.button("🔄 Nova atualização", use_container_width=True):
        st.session_state.etapa = "idle"
        st.session_state.logs = []
        st.rerun()

# ── Erro ──
elif st.session_state.etapa == "erro":
    st.error("❌ Processo encerrado com erro. Veja os logs abaixo.")
    mostrar_logs()
    if st.button("🔄 Tentar novamente", use_container_width=True):
        st.session_state.etapa = "idle"
        st.session_state.logs = []
        st.rerun()
