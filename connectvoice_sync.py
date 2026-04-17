"""
connectvoice_sync.py
Extrai o log de ligações do Connect Voice (somente atendidas, saintes,
do dia 01 do mês corrente até hoje) e sincroniza com a aba "Discador"
do Google Sheets da Connect Group.

Roda via GitHub Actions a cada 2 horas.
Credenciais lidas de variáveis de ambiente / arquivo credentials.json.
"""

import requests
import gspread
import sys
import os
import re
import logging
from datetime import date
from google.oauth2.service_account import Credentials

# ─────────────────────────────────────────────────────────────────
#  CONFIG — lê de variáveis de ambiente (GitHub Secrets)
# ─────────────────────────────────────────────────────────────────

CONFIG = {
    "cv_login_url":       "https://voice.connectgroup.solutions",
    "cv_extrato_url":     "https://voice.connectgroup.solutions/Relatorios/buscaLog_chamadas",
    "cv_usuario":         os.getenv("CV_USUARIO", "hugonobrega@conectserra"),
    "cv_senha":           os.getenv("CV_SENHA",   "Timbrasil@3477"),
    "cv_sentido":         "Sainte",
    "cv_resultado":       "ANSWER",   # somente atendidas
    "cv_usuario_filtro":  "todos",
    "cv_campanha":        "",
    "sheets_id":          os.getenv("SPREADSHEET_ID", "1HmtEFf2Akh7NLR2prxDh9S4gmioKYw419B4bkx4yBLg"),
    "sheets_aba":         "Discador",
    "google_creds":       "credentials.json",
}

COLUNAS_SHEETS = [
    "Data / Hora", "Usuário", "Telefone", "Resultado",
    "Duração", "Campanha", "Operadora", "Modo Disc."
]

# ─────────────────────────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%d/%m/%Y %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
#  AUTENTICAÇÃO NO CONNECT VOICE
# ─────────────────────────────────────────────────────────────────

def cv_login(session: requests.Session) -> bool:
    try:
        payload = {
            "txtAcao":    "",
            "url":        "",
            "txtusuario": CONFIG["cv_usuario"],
            "pwSenha":    CONFIG["cv_senha"],
        }
        headers = {
            "User-Agent":   "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer":      CONFIG["cv_login_url"],
            "Origin":       CONFIG["cv_login_url"],
        }
        r = session.post(
            CONFIG["cv_login_url"],
            data=payload,
            headers=headers,
            allow_redirects=True,
            timeout=30,
        )
        if r.status_code == 200:
            log.info(f"Login Connect Voice: OK (URL final: {r.url})")
            return True
        log.warning(f"Login retornou status {r.status_code}")
        return False
    except Exception as e:
        log.error(f"Erro no login: {e}")
        return False

# ─────────────────────────────────────────────────────────────────
#  BUSCA DO EXTRATO
# ─────────────────────────────────────────────────────────────────

def periodo_mes_atual() -> str:
    hoje   = date.today()
    inicio = hoje.replace(day=1)
    return f"{inicio.strftime('%d/%m/%Y')} - {hoje.strftime('%d/%m/%Y')}"


def cv_buscar_extrato(session: requests.Session) -> list[dict]:
    periodo = periodo_mes_atual()
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
        "Referer":          "https://voice.connectgroup.solutions/Relatorios/log_chamadas",
        "Origin":           "https://voice.connectgroup.solutions",
        "Accept":           "*/*",
    }
    log.info(f"Buscando extrato: {periodo} | sentido=Sainte | somente atendidas")
    r = session.post(CONFIG["cv_extrato_url"], data=payload, headers=headers, timeout=60)
    r.raise_for_status()

    content_type = r.headers.get("Content-Type", "")
    if "json" in content_type:
        return _parse_json(r.json())
    else:
        return _parse_html(r.text)


def _limpar(valor: str) -> str:
    return re.sub(r"<[^>]+>", "", str(valor)).strip()


def _parse_json(data: dict) -> list[dict]:
    campos = COLUNAS_SHEETS
    rows = []
    registros = data.get("data", data.get("aaData", []))
    for item in registros:
        if isinstance(item, list):
            row = {campos[i]: _limpar(item[i]) for i in range(min(len(campos), len(item)))}
            rows.append(row)
        elif isinstance(item, dict):
            rows.append(item)
    log.info(f"Parse JSON: {len(rows)} registros")
    return rows


def _parse_html(html: str) -> list[dict]:
    try:
        from html.parser import HTMLParser

        class TableParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.in_tbody = self.in_tr = self.in_td = False
                self.rows, self.current, self.cell = [], [], ""

            def handle_starttag(self, tag, attrs):
                if tag == "tbody": self.in_tbody = True
                if tag == "tr"  and self.in_tbody: self.in_tr = True; self.current = []
                if tag == "td"  and self.in_tr:    self.in_td = True; self.cell = ""

            def handle_endtag(self, tag):
                if tag == "tbody": self.in_tbody = False
                if tag == "tr"  and self.in_tbody:
                    self.in_tr = False
                    if self.current: self.rows.append(self.current[:])
                if tag == "td"  and self.in_tr:
                    self.in_td = False
                    self.current.append(self.cell.strip())

            def handle_data(self, data):
                if self.in_td: self.cell += data

        parser = TableParser()
        parser.feed(html)

        campos = COLUNAS_SHEETS
        rows = []
        for cols in parser.rows:
            if len(cols) >= 4:
                row = {campos[i]: _limpar(cols[i]) for i in range(min(len(campos), len(cols)))}
                rows.append(row)

        log.info(f"Parse HTML: {len(rows)} registros")
        return rows
    except Exception as e:
        log.error(f"Erro no parse HTML: {e}")
        return []

# ─────────────────────────────────────────────────────────────────
#  GOOGLE SHEETS
# ─────────────────────────────────────────────────────────────────

def sincronizar_sheets(registros: list[dict]):
    if not registros:
        log.warning("Nenhum registro para sincronizar.")
        return

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
        log.error("Falha no login. Abortando.")
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
