"""
connectvoice_sync.py
Extrai o log de ligações do Connect Voice (somente atendidas, saintes,
do dia 01 do mês corrente até hoje) e sincroniza com a aba "Discador"
do Google Sheets da Connect Group.
"""

import requests
import gspread
import sys
import os
import re
import logging
from datetime import date
from google.oauth2.service_account import Credentials
from html.parser import HTMLParser

CONFIG = {
    "cv_base_url":       "https://voice.connectgroup.solutions",
    "cv_login_url":      "https://voice.connectgroup.solutions",
    "cv_extrato_url":    "https://voice.connectgroup.solutions/Relatorios/buscaLog_chamadas",
    "cv_usuario":        os.getenv("CV_USUARIO", "hugonobrega@conectserra"),
    "cv_senha":          os.getenv("CV_SENHA",   "Timbrasil@3477"),
    "cv_sentido":        "Sainte",
    "cv_resultado":      "ANSWER",
    "cv_usuario_filtro": "todos",
    "cv_campanha":       "",
    "sheets_id":         os.getenv("SPREADSHEET_ID", "1HmtEFf2Akh7NLR2prxDh9S4gmioKYw419B4bkx4yBLg"),
    "sheets_aba":        "Discador",
    "google_creds":      "credentials.json",
}

COLUNAS_SHEETS = [
    "Data / Hora", "Usuário", "Telefone", "Resultado",
    "Duração", "Campanha", "Operadora", "Modo Disc."
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%d/%m/%Y %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
#  EXTRAI CSRF DO FORMULÁRIO DE LOGIN
# ─────────────────────────────────────────────────────────────────

class FormParser(HTMLParser):
    """Extrai campos hidden de formulários HTML."""
    def __init__(self):
        super().__init__()
        self.hidden = {}

    def handle_starttag(self, tag, attrs):
        if tag == "input":
            d = dict(attrs)
            if d.get("type", "").lower() == "hidden" and d.get("name"):
                self.hidden[d["name"]] = d.get("value", "")


def cv_login(session: requests.Session) -> bool:
    """
    Login em 2 passos:
    1. GET na página de login → captura cookies iniciais + campos hidden (CSRF)
    2. POST com credenciais + campos hidden
    """
    headers_base = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }

    # Passo 1: GET para pegar cookies e token CSRF
    log.info("Passo 1: GET na página de login...")
    r_get = session.get(
        CONFIG["cv_login_url"],
        headers=headers_base,
        timeout=30,
    )
    log.info(f"GET login: status={r_get.status_code} cookies={dict(session.cookies)}")

    # Extrai campos hidden do formulário
    parser = FormParser()
    parser.feed(r_get.text)
    log.info(f"Campos hidden encontrados: {parser.hidden}")

    # Monta payload com campos hidden + credenciais
    payload = {
        "txtAcao": "",
        "url":     "",
        "txtusuario": CONFIG["cv_usuario"],
        "pwSenha":    CONFIG["cv_senha"],
    }
    # Adiciona campos CSRF se existirem
    payload.update(parser.hidden)

    # Passo 2: POST com credenciais
    log.info("Passo 2: POST com credenciais...")
    r_post = session.post(
        CONFIG["cv_login_url"],
        data=payload,
        headers={
            **headers_base,
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer":      CONFIG["cv_login_url"],
            "Origin":       CONFIG["cv_base_url"],
        },
        allow_redirects=True,
        timeout=30,
    )
    log.info(f"POST login: status={r_post.status_code} url={r_post.url}")
    log.info(f"Cookies pós-login: {dict(session.cookies)}")

    # Verifica se está autenticado — página logada tem "logout" ou "Inicio"
    autenticado = (
        "logout" in r_post.text.lower() or
        "/Inicio" in r_post.url or
        "Inicio" in r_post.text or
        r_post.url.rstrip("/") != CONFIG["cv_base_url"].rstrip("/")
    )

    if autenticado:
        log.info("Login bem-sucedido!")
        return True

    # Tenta verificar acessando página protegida
    log.info("Verificando acesso a página protegida...")
    r_check = session.get(
        f"{CONFIG['cv_base_url']}/Inicio",
        headers=headers_base,
        timeout=20,
    )
    log.info(f"Check /Inicio: status={r_check.status_code} url={r_check.url}")

    if "login" not in r_check.url.lower() and r_check.status_code == 200:
        log.info("Acesso confirmado via /Inicio")
        return True

    log.error("Login falhou — servidor retornou página de login")
    # Salva preview para diagnóstico
    log.info(f"Preview resposta login: {r_post.text[:800]}")
    return False

# ─────────────────────────────────────────────────────────────────
#  EXTRATO
# ─────────────────────────────────────────────────────────────────

def periodo_mes_atual() -> str:
    hoje   = date.today()
    inicio = hoje.replace(day=1)
    return f"{inicio.strftime('%d/%m/%Y')} - {hoje.strftime('%d/%m/%Y')}"


def cv_buscar_extrato(session: requests.Session) -> list[dict]:
    periodo = periodo_mes_atual()

    # Visita a página do relatório antes de chamar o endpoint
    log.info("Acessando página de relatórios...")
    session.get(
        f"{CONFIG['cv_base_url']}/Relatorios/log_chamadas",
        headers={"User-Agent": "Mozilla/5.0", "Referer": f"{CONFIG['cv_base_url']}/Inicio"},
        timeout=20,
    )

    payload = {
        "usuario":         CONFIG["cv_usuario_filtro"],
        "sentido":         CONFIG["cv_sentido"],
        "reservation":     periodo,
        "numero_entrante": "",
        "numero":          "",
        "resultado":       CONFIG["cv_resultado"],
        "campanha":        CONFIG["cv_campanha"],
        "protocolo":       "",
        "acao":            "0",
    }
    headers = {
        "User-Agent":       "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Content-Type":     "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer":          f"{CONFIG['cv_base_url']}/Relatorios/log_chamadas",
        "Origin":           CONFIG["cv_base_url"],
        "Accept":           "application/json, text/javascript, */*; q=0.01",
    }

    log.info(f"Buscando extrato: {periodo}")
    r = session.post(CONFIG["cv_extrato_url"], data=payload, headers=headers, timeout=60)
    r.raise_for_status()

    log.info(f"Resposta: status={r.status_code} content-type={r.headers.get('Content-Type')} tamanho={len(r.content)} bytes")
    log.info(f"Preview: {r.text[:300].replace(chr(10), ' ')}")

    # Tenta JSON
    try:
        data = r.json()
        log.info(f"JSON válido. Tipo={type(data)} Chaves={list(data.keys()) if isinstance(data, dict) else 'lista'}")
        return _parse_json(data)
    except Exception:
        pass

    # Fallback HTML
    log.info("Não é JSON — tentando parse HTML...")
    return _parse_html(r.text)


def _limpar(valor) -> str:
    return re.sub(r"<[^>]+>", "", str(valor)).strip()


def _parse_json(data) -> list[dict]:
    campos = COLUNAS_SHEETS
    rows = []
    registros = (
        data.get("data", data.get("aaData", data.get("rows", [])))
        if isinstance(data, dict) else data
    )
    log.info(f"JSON: {len(registros)} registros brutos")
    if registros:
        log.info(f"Primeiro item: {str(registros[0])[:200]}")

    for item in registros:
        if isinstance(item, list):
            row = {campos[i]: _limpar(item[i]) for i in range(min(len(campos), len(item)))}
        elif isinstance(item, dict):
            row = {c: _limpar(item.get(c, "")) for c in campos}
        else:
            continue
        rows.append(row)

    log.info(f"Parse JSON: {len(rows)} registros")
    return rows


def _parse_html(html: str) -> list[dict]:
    try:
        class TableParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.in_tbody = self.in_tr = self.in_td = False
                self.rows, self.current, self.cell = [], [], ""

            def handle_starttag(self, tag, attrs):
                tag = tag.lower()
                if tag == "tbody": self.in_tbody = True
                if tag == "tr" and self.in_tbody: self.in_tr = True; self.current = []
                if tag in ("td", "th") and self.in_tr: self.in_td = True; self.cell = ""

            def handle_endtag(self, tag):
                tag = tag.lower()
                if tag == "tbody": self.in_tbody = False
                if tag == "tr" and self.in_tbody:
                    self.in_tr = False
                    if self.current: self.rows.append(self.current[:])
                if tag in ("td", "th") and self.in_tr:
                    self.in_td = False; self.current.append(self.cell.strip())

            def handle_data(self, data):
                if self.in_td: self.cell += data

        p = TableParser()
        p.feed(html)
        log.info(f"HTML: {len(p.rows)} linhas na tabela")

        campos = COLUNAS_SHEETS
        rows = []
        for cols in p.rows:
            if len(cols) >= 4:
                row = {campos[i]: _limpar(cols[i]) for i in range(min(len(campos), len(cols)))}
                rows.append(row)
        log.info(f"Parse HTML: {len(rows)} registros válidos")
        return rows
    except Exception as e:
        log.error(f"Erro parse HTML: {e}")
        return []

# ─────────────────────────────────────────────────────────────────
#  GOOGLE SHEETS
# ─────────────────────────────────────────────────────────────────

def sincronizar_sheets(registros: list[dict]):
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(CONFIG["google_creds"], scopes=scopes)
    gc    = gspread.authorize(creds)
    sh    = gc.open_by_key(CONFIG["sheets_id"])
    aba   = sh.worksheet(CONFIG["sheets_aba"])

    linhas = [COLUNAS_SHEETS]
    for r in registros:
        linhas.append([r.get(c, "") for c in COLUNAS_SHEETS])

    aba.clear()
    aba.update("A1", linhas, value_input_option="USER_ENTERED")
    log.info(f"Sheets atualizado: {len(registros)} registros → aba '{CONFIG['sheets_aba']}'")

# ─────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────

def main():
    log.info("=" * 55)
    log.info("Connect Voice → Google Sheets | Discador Sync")
    log.info(f"Período: {periodo_mes_atual()}")
    log.info("=" * 55)

    session = requests.Session()

    if not cv_login(session):
        log.error("Falha no login.")
        sys.exit(1)

    try:
        registros = cv_buscar_extrato(session)
    except Exception as e:
        log.error(f"Erro ao buscar extrato: {e}")
        sys.exit(1)

    if not registros:
        log.warning("Extrato vazio — nenhum dado atualizado.")
        sys.exit(0)

    try:
        sincronizar_sheets(registros)
    except Exception as e:
        log.error(f"Erro ao atualizar Sheets: {e}")
        sys.exit(1)

    log.info("Sincronizacao concluida com sucesso.")


if __name__ == "__main__":
    main()
