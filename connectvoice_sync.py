"""
connectvoice_sync.py
Extrai o log de ligações do Connect Voice usando Selenium (browser real),
somente atendidas, saintes, do dia 01 do mês até hoje.
Sincroniza com a aba "Discador" do Google Sheets.
"""

import os
import re
import sys
import time
import logging
import gspread
from datetime import date
from google.oauth2.service_account import Credentials

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

CONFIG = {
    "cv_base_url":       "https://voice.connectgroup.solutions",
    "cv_usuario":        os.getenv("CV_USUARIO", "hugonobrega@conectserra"),
    "cv_senha":          os.getenv("CV_SENHA",   "Timbrasil@3477"),
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


def criar_driver():
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=opts)


def periodo_mes_atual():
    hoje   = date.today()
    inicio = hoje.replace(day=1)
    return inicio.strftime("%d/%m/%Y"), hoje.strftime("%d/%m/%Y")


def buscar_extrato_via_selenium() -> list[dict]:
    driver = criar_driver()
    wait   = WebDriverWait(driver, 30)
    dados  = []

    try:
        # ── Login ──────────────────────────────────────────────────
        log.info("Abrindo página de login...")
        driver.get(CONFIG["cv_base_url"])
        time.sleep(3)
        log.info(f"URL após GET: {driver.current_url}")

        # Preenche usuário
        campo_usuario = wait.until(EC.presence_of_element_located((By.NAME, "txtusuario")))
        campo_usuario.clear()
        campo_usuario.send_keys(CONFIG["cv_usuario"])
        log.info("Usuário preenchido")

        # Preenche senha
        campo_senha = driver.find_element(By.NAME, "pwSenha")
        campo_senha.clear()
        campo_senha.send_keys(CONFIG["cv_senha"])
        log.info("Senha preenchida")

        # Clica no botão de login
        try:
            btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        except Exception:
            btn = driver.find_element(By.CSS_SELECTOR, ".btn")
        btn.click()
        log.info("Botão de login clicado")

        time.sleep(4)
        log.info(f"URL pós-login: {driver.current_url}")

        # Verifica se logou
        if "login" in driver.current_url.lower() or driver.current_url.rstrip("/") == CONFIG["cv_base_url"].rstrip("/"):
            # Tenta verificar pelo conteúdo da página
            page_text = driver.find_element(By.TAG_NAME, "body").text
            if "logout" not in page_text.lower() and "sair" not in page_text.lower():
                log.error("Login pode ter falhado. Conteúdo da página:")
                log.error(page_text[:300])

        # ── Injeta interceptor XHR ─────────────────────────────────
        log.info("Injetando interceptor XHR...")
        driver.execute_script("""
            window._cv_dados = null;
            const origOpen = XMLHttpRequest.prototype.open;
            const origSend = XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.open = function(method, url, ...args) {
                this._url = url;
                return origOpen.apply(this, [method, url, ...args]);
            };
            XMLHttpRequest.prototype.send = function(body) {
                this.addEventListener('load', function() {
                    if (this._url && this._url.includes('buscaLog_chamadas')) {
                        try {
                            window._cv_dados = JSON.parse(this.responseText);
                        } catch(e) {
                            window._cv_dados = {'_raw': this.responseText.substring(0, 500)};
                        }
                    }
                });
                return origSend.apply(this, [body]);
            };
        """)

        # ── Navega para Extrato de Ligações ────────────────────────
        log.info("Navegando para Extrato de Ligações...")
        driver.get(f"{CONFIG['cv_base_url']}/Relatorios/log_chamadas")
        time.sleep(3)
        log.info(f"URL extrato: {driver.current_url}")

        # Re-injeta interceptor (nova página)
        driver.execute_script("""
            window._cv_dados = null;
            const origOpen = XMLHttpRequest.prototype.open;
            const origSend = XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.open = function(method, url, ...args) {
                this._url = url;
                return origOpen.apply(this, [method, url, ...args]);
            };
            XMLHttpRequest.prototype.send = function(body) {
                this.addEventListener('load', function() {
                    if (this._url && this._url.includes('buscaLog_chamadas')) {
                        try {
                            window._cv_dados = JSON.parse(this.responseText);
                        } catch(e) {
                            window._cv_dados = {'_raw': this.responseText.substring(0, 500)};
                        }
                    }
                });
                return origSend.apply(this, [body]);
            };
        """)

        # ── Preenche filtros ───────────────────────────────────────
        inicio, fim = periodo_mes_atual()
        periodo_str = f"{inicio} - {fim}"
        log.info(f"Preenchendo filtros: {periodo_str}")

        # Data via JavaScript (daterangepicker não aceita send_keys)
        driver.execute_script(f"""
            var campos = document.querySelectorAll('input');
            for (var i = 0; i < campos.length; i++) {{
                var n = campos[i].name || '';
                var p = campos[i].placeholder || '';
                if (n === 'reservation' || n.includes('data') || p.includes('/')) {{
                    campos[i].value = '{periodo_str}';
                    campos[i].dispatchEvent(new Event('change', {{bubbles: true}}));
                    campos[i].dispatchEvent(new Event('input', {{bubbles: true}}));
                    break;
                }}
            }}
        """)
        log.info("Data definida via JS")

        # Sentido = Sainte
        try:
            sel = Select(wait.until(EC.presence_of_element_located((By.NAME, "sentido"))))
            sel.select_by_visible_text("Sainte")
            log.info("Sentido: Sainte")
        except Exception as e:
            log.warning(f"Select sentido: {e}")

        # Radio: Somente atendidas (valor ANSWER)
        try:
            driver.execute_script("""
                var radios = document.querySelectorAll('input[type=radio]');
                for (var r of radios) {
                    if (r.value === 'ANSWER' || r.value.toUpperCase().includes('ANSWER')) {
                        r.click();
                        break;
                    }
                }
            """)
            log.info("Radio ANSWER selecionado")
        except Exception as e:
            log.warning(f"Radio: {e}")

        # ── Clica Pesquisar ────────────────────────────────────────
        log.info("Clicando em Pesquisar...")
        try:
            btn_pesq = wait.until(EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button[type='submit'], input[type='submit'], .btn-pesquisar")
            ))
            btn_pesq.click()
        except Exception:
            driver.execute_script(
                "document.querySelector('button[type=submit], input[type=submit]').click();"
            )

        # ── Aguarda dados ──────────────────────────────────────────
        log.info("Aguardando resposta do servidor...")
        for i in range(30):
            time.sleep(1)
            resultado = driver.execute_script("return window._cv_dados;")
            if resultado is not None:
                log.info(f"Dados interceptados após {i+1}s")
                break
        else:
            log.warning("Timeout — lendo tabela do DOM diretamente")
            resultado = None

        # ── Parse ──────────────────────────────────────────────────
        if resultado is not None:
            if "_raw" in resultado:
                log.warning(f"Resposta não é JSON: {resultado['_raw']}")
                dados = _parse_tabela_dom(driver)
            else:
                dados = _parse_json(resultado)
        else:
            dados = _parse_tabela_dom(driver)

    except Exception as e:
        log.error(f"Erro Selenium: {e}")
        import traceback
        log.error(traceback.format_exc())
    finally:
        driver.quit()

    return dados


def _limpar(v) -> str:
    return re.sub(r"<[^>]+>", "", str(v)).strip()


def _parse_json(data) -> list[dict]:
    campos = COLUNAS_SHEETS
    rows   = []
    if isinstance(data, dict):
        registros = data.get("data", data.get("aaData", data.get("rows", [])))
    elif isinstance(data, list):
        registros = data
    else:
        return []

    log.info(f"JSON: {len(registros)} registros brutos")
    if registros:
        log.info(f"Exemplo item[0]: {str(registros[0])[:300]}")

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


def _parse_tabela_dom(driver) -> list[dict]:
    log.info("Lendo tabela do DOM...")
    rows = []
    try:
        linhas = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
        log.info(f"Linhas no DOM: {len(linhas)}")
        campos = COLUNAS_SHEETS
        for linha in linhas:
            cels = linha.find_elements(By.TAG_NAME, "td")
            if len(cels) >= 4:
                row = {campos[i]: _limpar(cels[i].text) for i in range(min(len(campos), len(cels)))}
                rows.append(row)
        log.info(f"Parse DOM: {len(rows)} registros")
    except Exception as e:
        log.error(f"Erro parse DOM: {e}")
    return rows


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


def main():
    inicio, fim = periodo_mes_atual()
    log.info("=" * 55)
    log.info("Connect Voice → Google Sheets | Discador Sync")
    log.info(f"Período: {inicio} - {fim}")
    log.info("=" * 55)

    registros = buscar_extrato_via_selenium()

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
