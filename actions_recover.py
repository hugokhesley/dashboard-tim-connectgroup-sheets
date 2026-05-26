"""
=====================================================================
  RECUPERAR RELATÓRIOS DO RADAR TIM (já gerados)
=====================================================================
  Para uso manual via GitHub Actions (workflow_dispatch).
  
  Diferente do actions_runner.py:
    - NÃO solicita relatório novo
    - NÃO espera email chegar
    - Vai DIRETO na fila de relatórios do Radar
    - Pega o relatório mais recente já PRONTO de cada conta
    - Baixa, junta e sobe para o Google Sheets
  
  Use quando você já sabe que os relatórios foram gerados.
=====================================================================
"""

import os
import sys
import time
import base64
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import gspread
import requests
from google.oauth2.service_account import Credentials

import securid
from securid.stoken import StokenFile

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ─────────────────────────────────────────────────────────────────
#  CONFIGURAÇÕES
# ─────────────────────────────────────────────────────────────────

# Contas — cada uma com seu arquivo .sdtid correspondente
CONTAS = [
    {"login": "t3729525", "nome": "Conta 1", "sdtid": "T3729525_001938489117.sdtid"},
    {"login": "t3761125", "nome": "Conta 2", "sdtid": "T3761125_001938495598.sdtid"},
    {"login": "t3748937", "nome": "Conta 3", "sdtid": "T3748937_001938491397.sdtid"},
]

PIN_RSA = "1234"

# URLs do Radar
URL_LOGIN = "https://iam-pf.timbrasil.com.br"
URL_FILA  = "https://radar.timbrasil.com.br/radar-blue/sistema/report-queue.asp"

# Google Sheets
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "1HmtEFf2Akh7NLR2prxDh9S4gmioKYw419B4bkx4yBLg")
ABA_DESTINO    = "DadosRadar"
GOOGLE_CREDENTIALS_JSON = "credentials.json"

# Pasta temporária para downloads
PASTA_TEMP = Path(tempfile.mkdtemp(prefix="radar_recover_"))


# ─────────────────────────────────────────────────────────────────
#  RSA TOKEN
# ─────────────────────────────────────────────────────────────────

def gerar_token_rsa(sdtid_path: str) -> str:
    """Gera token RSA SecurID a partir do arquivo .sdtid."""
    token = StokenFile(sdtid_path).get_token()
    return PIN_RSA + token.now()


# ─────────────────────────────────────────────────────────────────
#  SELENIUM
# ─────────────────────────────────────────────────────────────────

def criar_driver() -> webdriver.Chrome:
    """Cria Chrome em headless para GitHub Actions."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36")
    
    # Pasta de download
    prefs = {
        "download.default_directory": str(PASTA_TEMP),
        "download.prompt_for_download": False,
        "safebrowsing.enabled": True,
    }
    options.add_experimental_option("prefs", prefs)
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(60)
    return driver


def esperar(driver, by, valor, timeout=20):
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((by, valor))
    )


def fazer_login(driver, conta: dict) -> bool:
    """Login no Radar TIM com RSA SecurID."""
    login = conta["login"]
    nome  = conta["nome"]
    
    print(f"\n  🌐 [{nome}] Acessando {URL_LOGIN}...")
    driver.get(URL_LOGIN)
    time.sleep(5)
    
    # ── Tela 1: Selecionar conta ──────────────────────────────────
    try:
        # Tenta clicar na conta direto pelo ID
        try:
            conta_elem = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((By.ID, login))
            )
            conta_elem.click()
            print(f"     ✓ Conta {login} clicada (ID)")
        except Exception:
            # Tenta por texto
            conta_elem = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, f"//*[contains(text(),'{login}')]"))
            )
            conta_elem.click()
            print(f"     ✓ Conta {login} clicada (texto)")
        
        time.sleep(4)
    except Exception as e:
        # Tenta "Use another account"
        try:
            outro = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//*[contains(text(),'Use another account') or contains(text(),'Usar outra conta')]"))
            )
            outro.click()
            time.sleep(2)
            campo = esperar(driver, By.XPATH, "//input[@type='text' or @id='identifier' or @id='identifierField']")
            campo.send_keys(login)
            esperar(driver, By.XPATH, "//button[@type='submit'] | //*[@id='postButton']").click()
            print(f"     ✓ Login {login} digitado manualmente")
            time.sleep(4)
        except Exception as e2:
            print(f"     ❌ Erro ao selecionar conta: {e2}")
            return False
    
    # ── Aguarda redirect para SmartID ─────────────────────────────
    try:
        WebDriverWait(driver, 20).until(
            lambda d: "iam-pf" in d.current_url or "authorization" in d.current_url or "password" in d.page_source.lower()
        )
        time.sleep(2)
    except Exception:
        print(f"     ⚠️  Não detectou tela SmartID, tentando continuar...")
    
    # ── Tela 2: Token RSA ─────────────────────────────────────────
    try:
        token = gerar_token_rsa(conta["sdtid"])
        print(f"     🔑 Token RSA gerado para {login}")
        
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
        print(f"     ✓ Token enviado, aguardando login...")
        time.sleep(8)
        
        if "radar" in driver.current_url.lower():
            print(f"     ✅ Login OK em {nome}")
            return True
        else:
            print(f"     ⚠️  URL após login: {driver.current_url}")
            return True  # tenta continuar mesmo assim
    
    except Exception as e:
        print(f"     ❌ Erro no token: {e}")
        return False


# ─────────────────────────────────────────────────────────────────
#  BUSCAR E BAIXAR RELATÓRIO DA FILA
# ─────────────────────────────────────────────────────────────────

def baixar_relatorio_mais_recente(driver, conta: dict) -> Path | None:
    """Vai na fila de relatórios e baixa o mais recente já pronto."""
    nome = conta["nome"]
    login = conta["login"]
    
    print(f"\n  📥 [{nome}] Buscando relatório pronto na fila...")
    
    try:
        driver.get(URL_FILA)
        time.sleep(5)
    except Exception as e:
        print(f"     ❌ Erro ao acessar fila: {e}")
        return None
    
    # ── Encontra o link de download mais recente ─────────────────
    try:
        # Tenta encontrar links que contêm "report-queue-download" 
        # — esses são os relatórios prontos
        links_download = driver.find_elements(
            By.XPATH, 
            "//a[contains(@href, 'report-queue-download')]"
        )
        
        if not links_download:
            print(f"     ⚠️  Nenhum relatório pronto encontrado na fila")
            return None
        
        # Pega o primeiro (mais recente — a fila lista do mais novo ao mais antigo)
        link_elem = links_download[0]
        url_download = link_elem.get_attribute("href")
        print(f"     ✓ Link encontrado: ...{url_download[-80:]}")
        
        # ── Baixa via requests (mais confiável que clicar) ───────
        # Passa os cookies da sessão Selenium para o requests
        cookies = {c['name']: c['value'] for c in driver.get_cookies()}
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "Referer": URL_FILA,
        }
        
        print(f"     ⬇️  Baixando arquivo...")
        response = requests.get(
            url_download,
            headers=headers,
            cookies=cookies,
            timeout=120,
            stream=True
        )
        response.raise_for_status()
        
        # Salva
        nome_arquivo = f"radar_{login}.xlsx"
        caminho = PASTA_TEMP / nome_arquivo
        with open(caminho, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        tamanho_kb = caminho.stat().st_size / 1024
        print(f"     ✅ Salvo: {nome_arquivo} ({tamanho_kb:.1f} KB)")
        return caminho
    
    except Exception as e:
        print(f"     ❌ Erro ao baixar: {e}")
        return None


# ─────────────────────────────────────────────────────────────────
#  PROCESSAMENTO E SHEETS
# ─────────────────────────────────────────────────────────────────

def ler_e_juntar(caminhos: list[Path]) -> pd.DataFrame:
    """Lê todos os .xlsx baixados e junta em um DataFrame."""
    dfs = []
    for caminho in caminhos:
        if caminho is None or not caminho.exists():
            continue
        try:
            df = pd.read_excel(caminho, header=0)
            print(f"     ✓ {caminho.name}: {len(df)} linhas")
            dfs.append(df)
        except Exception as e:
            print(f"     ⚠️  Erro ao ler {caminho.name}: {e}")
    
    if not dfs:
        return pd.DataFrame()
    
    df_final = pd.concat(dfs, ignore_index=True)
    print(f"\n  📋 Total após junção: {len(df_final)} linhas | {len(df_final.columns)} colunas")
    return df_final


def subir_para_sheets(df: pd.DataFrame):
    """Sobrescreve a aba DadosRadar no Google Sheets."""
    print(f"\n  ↑ Conectando ao Google Sheets...")
    
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_JSON, scopes=scopes)
    gc = gspread.authorize(creds)
    
    planilha = gc.open_by_key(SPREADSHEET_ID)
    
    try:
        aba = planilha.worksheet(ABA_DESTINO)
    except gspread.WorksheetNotFound:
        aba = planilha.add_worksheet(title=ABA_DESTINO, rows=1, cols=1)
        print(f"     + Aba '{ABA_DESTINO}' criada.")
    
    aba.clear()
    print(f"  🧹 Aba '{ABA_DESTINO}' limpa.")
    
    df = df.fillna("")
    dados = [df.columns.tolist()] + df.values.tolist()
    dados = [[str(v) for v in linha] for linha in dados]
    
    aba.update(dados, value_input_option="USER_ENTERED")
    print(f"  ✅ {len(df)} linhas gravadas na aba '{ABA_DESTINO}'!")
    print(f"\n  🔗 https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}")


# ─────────────────────────────────────────────────────────────────
#  EXECUÇÃO PRINCIPAL
# ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  RECUPERAR RELATÓRIOS DO RADAR TIM (já prontos)")
    print(f"  Início: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 60)
    
    caminhos_baixados = []
    
    for conta in CONTAS:
        login = conta["login"]
        nome  = conta["nome"]
        sdtid = conta["sdtid"]
        
        print(f"\n{'─' * 60}")
        print(f"  Processando: {nome} ({login})")
        print(f"{'─' * 60}")
        
        # Verifica se o arquivo SDTID existe
        if not Path(sdtid).exists():
            print(f"  ⚠️  Arquivo SDTID não encontrado: {sdtid} — pulando")
            continue
        
        driver = None
        try:
            driver = criar_driver()
            
            if fazer_login(driver, conta):
                caminho = baixar_relatorio_mais_recente(driver, conta)
                if caminho:
                    caminhos_baixados.append(caminho)
        except Exception as e:
            print(f"  ❌ Erro fatal em {nome}: {e}")
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
            print(f"  🔒 Sessão {nome} encerrada")
    
    # ── Processa e sobe ─────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"  Resumo: {len(caminhos_baixados)}/{len(CONTAS)} relatórios baixados")
    print(f"{'=' * 60}")
    
    if not caminhos_baixados:
        print("\n  ❌ Nenhum relatório baixado. Encerrando.")
        sys.exit(1)
    
    print(f"\n  📖 Lendo arquivos baixados...")
    df_final = ler_e_juntar(caminhos_baixados)
    
    if df_final.empty:
        print("\n  ❌ DataFrame vazio. Encerrando.")
        sys.exit(1)
    
    subir_para_sheets(df_final)
    
    print(f"\n{'=' * 60}")
    print(f"  🎉 Concluído com sucesso!")
    print(f"  Fim: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
