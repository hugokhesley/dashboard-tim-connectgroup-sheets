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
import json
import logging
from datetime import date
from google.oauth2.service_account import Credentials

# ─────────────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────────────

CONFIG = {
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
#  LOGIN
# ─────────────────────────────────────────────────────────────────

def cv_login(session: requests.Session) -> bool:
    try:
        r = session.post(
            CONFIG["cv_login_url"],
            data={
                "txtAcao":    "",
                "url":        "",
                "txtusuario": CONFIG["cv_usuario"],
                "pwSenha":    CONFIG["cv_senha"],
            },
            headers={
                "User-Agent":   "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer":      CONFIG["cv_login_url"],
                "Origin":       CONFIG["cv_login_url"],
            },
            allow_redirects=True,
            timeout=30,
        )
        log.info(f"Login: status={r.status_code} url={r.url}")
        log.info(f"Cookies: {dict(session.cookies)}")
        return r.status_code == 200
    except Exception as e:
        log.error(f"Erro no login: {e}")
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
        "Accept":           "application/json, text/javascript, */*; q=0.01",
    }
    log.info(f"Buscando extrato: {periodo}")
    r = session.post(CONFIG["cv_extrato_url"], data=payload, headers=headers, timeout=60)
    r.raise_for_status()

    log.info(f"Resposta: status={r.status_code} content-type={r.headers.get('Content-Type')} tamanho={len(r.content)} bytes")

    # Mostra primeiros 500 chars para diagnóstico
    preview = r.text[:500].replace("\n", " ").replace("\r", "")
    log.info(f"Preview resposta: {preview}")

    # Tenta JSON primeiro (independente do Content-Type)
    try:
        data = r.json()
        log.info(f"Resposta é JSON. Chaves: {list(data.keys()) if isinstance(data, dict) else type(data)}")
        return _parse_json(data)
    except Exception:
        pass

    # Fallback: HTML
    log.info("Resposta não é JSON, tentando parse HTML...")
    return _parse_html(r.text)


def _limpar(valor) -> str:
    return re.sub(r"<[^>]+>", "", str(valor)).strip()


def _parse_json(data) -> list[dict]:
    campos = COLUNAS_SHEETS
    rows = []

    # Estrutura DataTables: {"data": [[...], [...]]}
    if isinstance(data, dict):
        registros = data.get("data", data.get("aaData", data.get("rows", [])))
    elif isinstance(data, list):
        registros = data
    else:
        log.warning(f"Estrutura JSON inesperada: {type(data)}")
        return []

    log.info(f"JSON: {len(registros)} registros brutos encontrados")

    for item in registros:
        if isinstance(item, list):
            row = {}
            for i, campo in enumerate(campos):
                row[campo] = _limpar(item[i]) if i < len(item) else ""
            rows.append(row)
        elif isinstance(item, dict):
            # tenta mapear pelas chaves mais comuns
            row = {
                "Data / Hora": _limpar(item.get("data_hora", item.get("data", item.get("DT_RowId", "")))),
                "Usuário":     _limpar(item.get("usuario",   item.get("agente", ""))),
                "Telefone":    _limpar(item.get("telefone",  item.get("numero", ""))),
                "Resultado":   _limpar(item.get("resultado", item.get("status", ""))),
                "Duração":     _limpar(item.get("duracao",   item.get("tempo",  ""))),
                "Campanha":    _limpar(item.get("campanha",  "")),
                "Operadora":   _limpar(item.get("operadora", "")),
                "Modo Disc.":  _limpar(item.get("modo",      "")),
            }
            rows.append(row)

    log.info(f"Parse JSON: {len(rows)} registros processados")
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
                tag = tag.lower()
                if tag == "tbody":
                    self.in_tbody = True
                if tag == "tr" and self.in_tbody:
                    self.in_tr = True
                    self.current = []
                if tag in ("td", "th") and self.in_tr:
                    self.in_td = True
                    self.cell = ""

            def handle_endtag(self, tag):
                tag = tag.lower()
                if tag == "tbody":
                    self.in_tbody = False
                if tag == "tr" and self.in_tbody:
                    self.in_tr = False
                    if self.current:
                        self.rows.append(self.current[:])
                if tag in ("td", "th") and self.in_tr:
                    self.in_td = False
                    self.current.append(self.cell.strip())

            def handle_data(self, data):
                if self.in_td:
                    self.cell += data

        parser = TableParser()
        parser.feed(html)

        log.info(f"HTML: {len(parser.rows)} linhas encontradas na tabela")

        campos = COLUNAS_SHEETS
        rows = []
        for cols in parser.rows:
            if len(cols) >= 4:
                row = {campos[i]: _limpar(cols[i]) for i in range(min(len(campos), len(cols)))}
                rows.append(row)

        log.info(f"Parse HTML: {len(rows)} registros válidos")
        return rows
    except Exception as e:
        log.error(f"Erro no parse HTML: {e}")
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
