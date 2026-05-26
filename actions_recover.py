"""
=====================================================================
  RECUPERAR RELATÓRIOS DO RADAR TIM (já gerados)
=====================================================================
"""

import os
import sys
import time
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
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


CONTAS = [
    {"login": "t3729525", "nome": "Conta 1", "sdtid": "T3729525_001938489117.sdtid"},
    {"login": "t3761125", "nome": "Conta 2", "sdtid": "T3761125_001938495598.sdtid"},
    {"login": "t3748937", "nome": "Conta 3", "sdtid": "T3748937_001938491397.sdtid"},
]

PIN_RSA = "1234"
URL_LOGIN = "https://iam-pf.timbrasil.com.br"
URL_FILA  = "https://radar.timbrasil.com.br/radar-blue/sistema/report-queue.asp"

SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "1HmtEFf2Akh7NLR2prxDh9S4gmioKYw419B4bkx4yBLg")
ABA_DESTINO = "DadosRadar"
GOOGLE_CREDENTIALS_JSON = "credentials.json"

PASTA_TEMP  = Path(tempfile.mkdtemp(prefix="radar_recover_"))
PASTA_DEBUG = Path("debug_artifacts")
PASTA_DEBUG.mkdir(exist_ok=True)


def gerar_token_rsa(sdtid_path: str) -> str:
    token = StokenFile(sdtid_path).get_token()
    return PIN_RSA + token.now()


def criar_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
    
    prefs = {
        "download.default_directory": str(PASTA_TEMP),
        "download.prompt_for_download": False,
        "safebrowsing.enabled": True,
    }
    options.add_experimental_option("prefs", prefs)
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(60)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    return driver


def debug_dump(driver, nome_arquivo: str):
    """Salva screenshot + HTML para análise."""
    try:
        screenshot_path = PASTA_DEBUG / f"{nome_arquivo}.png"
        driver.save_screenshot(str(screenshot_path))
        html_path = PASTA_DEBUG / f"{nome_arquivo}.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        print(f"     📸 Debug salvo: {nome_arquivo}.png e .html")
    except Exception as e:
        print(f"     ⚠️  Erro ao salvar debug: {e}")


def listar_elementos_login(driver):
    """Lista todos os elementos clicáveis visíveis na tela para debug."""
    print(f"     🔍 URL atual: {driver.current_url}")
    print(f"     🔍 Título da página: {driver.title}")
    
    # Lista todos os links e botões
    try:
        elementos = driver.find_elements(By.XPATH, "//a | //button | //input[@type='submit'] | //div[@onclick] | //span[@onclick]")
        print(f"     🔍 Total de elementos interativos: {len(elementos)}")
        for i, el in enumerate(elementos[:20]):
            try:
                texto = el.text.strip()[:60] if el.text else ""
                tag = el.tag_name
                id_attr = el.get_attribute("id") or ""
                href = (el.get_attribute("href") or "")[:50]
                if texto or id_attr:
                    print(f"        [{i}] <{tag}> id='{id_attr}' texto='{texto}' href='{href}'")
            except Exception:
                pass
    except Exception as e:
        print(f"     ⚠️  Erro ao listar elementos: {e}")


def fazer_login(driver, conta: dict) -> bool:
    login = conta["login"]
    nome  = conta["nome"]
    
    print(f"\n  🌐 [{nome}] Acessando {URL_LOGIN}...")
    driver.get(URL_LOGIN)
    time.sleep(8)  # Aguarda JS carregar mais tempo
    
    print(f"     ⏳ Aguardando página carregar completamente...")
    try:
        WebDriverWait(driver, 30).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
    except Exception:
        pass
    
    time.sleep(3)
    debug_dump(driver, f"01_login_{login}")
    listar_elementos_login(driver)
    
    # ── Estratégia 1: Tenta clicar diretamente em elemento com o login ────
    sucesso_conta = False
    seletores_conta = [
        (By.ID, login),
        (By.XPATH, f"//*[@id='{login}']"),
        (By.XPATH, f"//div[contains(@class,'username') and contains(text(),'{login}')]"),
        (By.XPATH, f"//button[contains(text(),'{login}')]"),
        (By.XPATH, f"//a[contains(text(),'{login}')]"),
        (By.XPATH, f"//*[contains(text(),'{login}')]"),
        (By.XPATH, f"//*[@title='{login}']"),
        (By.XPATH, f"//*[@data-username='{login}']"),
        (By.XPATH, f"//*[@data-user='{login}']"),
    ]
    
    for by, seletor in seletores_conta:
        try:
            elem = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((by, seletor))
            )
            driver.execute_script("arguments[0].click()", elem)
            print(f"     ✓ Conta {login} clicada via: {by}={seletor}")
            sucesso_conta = True
            break
        except Exception:
            continue
    
    # ── Estratégia 2: Procura campo de input direto ────────────────────────
    if not sucesso_conta:
        print(f"     🔄 Conta não encontrada por seletor direto, procurando campo de input...")
        seletores_input = [
            (By.ID, "identifierField"),
            (By.ID, "identifier"),
            (By.ID, "username"),
            (By.NAME, "username"),
            (By.NAME, "identifier"),
            (By.XPATH, "//input[@type='text']"),
            (By.XPATH, "//input[@type='email']"),
        ]
        
        for by, seletor in seletores_input:
            try:
                campo = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((by, seletor))
                )
                campo.clear()
                campo.send_keys(login)
                print(f"     ✓ Login {login} digitado no campo: {by}={seletor}")
                
                # Tenta clicar no botão submit
                botoes = [
                    (By.ID, "postButton"),
                    (By.ID, "submitButton"),
                    (By.XPATH, "//button[@type='submit']"),
                    (By.XPATH, "//input[@type='submit']"),
                    (By.XPATH, "//button[contains(text(),'Continuar')]"),
                    (By.XPATH, "//button[contains(text(),'Next')]"),
                    (By.XPATH, "//button[contains(text(),'Entrar')]"),
                ]
                for by_btn, sel_btn in botoes:
                    try:
                        btn = driver.find_element(by_btn, sel_btn)
                        driver.execute_script("arguments[0].click()", btn)
                        print(f"     ✓ Botão submit clicado: {by_btn}={sel_btn}")
                        sucesso_conta = True
                        break
                    except Exception:
                        continue
                
                if not sucesso_conta:
                    # Tenta enviar com ENTER
                    from selenium.webdriver.common.keys import Keys
                    campo.send_keys(Keys.RETURN)
                    print(f"     ✓ ENTER enviado no campo")
                    sucesso_conta = True
                
                break
            except Exception:
                continue
    
    if not sucesso_conta:
        print(f"     ❌ Não foi possível selecionar a conta nem encontrar campo de input")
        debug_dump(driver, f"02_falha_conta_{login}")
        return False
    
    time.sleep(5)
    debug_dump(driver, f"03_pos_conta_{login}")
    print(f"     📍 URL após seleção: {driver.current_url}")
    
    # ── Aguarda tela SmartID/Token ───────────────────────────────────────
    print(f"     ⏳ Aguardando tela de token RSA...")
    try:
        WebDriverWait(driver, 25).until(
            lambda d: "iam-pf" in d.current_url 
                  or "authorization" in d.current_url 
                  or "password" in d.page_source.lower()
                  or d.find_elements(By.ID, "password")
        )
        time.sleep(3)
        print(f"     ✓ Tela de token detectada")
    except Exception:
        print(f"     ⚠️  Timeout aguardando token, tentando continuar...")
    
    debug_dump(driver, f"04_pre_token_{login}")
    
    # ── Tela do token RSA ────────────────────────────────────────────────
    try:
        token = gerar_token_rsa(conta["sdtid"])
        print(f"     🔑 Token RSA gerado")
        
        campo_token = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "password"))
        )
        campo_token.clear()
        campo_token.send_keys(token)
        time.sleep(1)
        
        # Tenta múltiplos seletores para o botão Entrar
        seletores_entrar = [
            (By.ID, "signOnButton"),
            (By.ID, "submitButton"),
            (By.XPATH, "//button[@type='submit']"),
            (By.XPATH, "//a[contains(text(),'Entrar')]"),
            (By.XPATH, "//button[contains(text(),'Entrar')]"),
            (By.XPATH, "//input[@value='Entrar']"),
        ]
        
        clicado = False
        for by, sel in seletores_entrar:
            try:
                btn = driver.find_element(by, sel)
                driver.execute_script("arguments[0].click()", btn)
                print(f"     ✓ Botão Entrar clicado: {by}={sel}")
                clicado = True
                break
            except Exception:
                continue
        
        if not clicado:
            # ENTER no campo
            from selenium.webdriver.common.keys import Keys
            campo_token.send_keys(Keys.RETURN)
            print(f"     ✓ ENTER enviado")
        
        time.sleep(10)
        debug_dump(driver, f"05_pos_token_{login}")
        print(f"     📍 URL após token: {driver.current_url}")
        
        if "radar" in driver.current_url.lower() or "iam-pf" not in driver.current_url:
            print(f"     ✅ Login OK em {nome}")
            return True
        else:
            print(f"     ⚠️  Login pode ter falhado. URL: {driver.current_url}")
            return True  # tenta continuar
    
    except Exception as e:
        print(f"     ❌ Erro no token: {e}")
        debug_dump(driver, f"05_erro_token_{login}")
        return False


def baixar_relatorio_mais_recente(driver, conta: dict):
    nome = conta["nome"]
    login = conta["login"]
    
    print(f"\n  📥 [{nome}] Buscando relatório pronto na fila...")
    
    try:
        driver.get(URL_FILA)
        time.sleep(6)
        debug_dump(driver, f"06_fila_{login}")
    except Exception as e:
        print(f"     ❌ Erro ao acessar fila: {e}")
        return None
    
    try:
        links_download = driver.find_elements(
            By.XPATH, 
            "//a[contains(@href, 'report-queue-download')]"
        )
        
        if not links_download:
            print(f"     ⚠️  Nenhum relatório pronto encontrado na fila")
            print(f"     📍 URL da fila: {driver.current_url}")
            print(f"     📍 Título: {driver.title}")
            return None
        
        link_elem = links_download[0]
        url_download = link_elem.get_attribute("href")
        print(f"     ✓ Link encontrado")
        
        cookies = {c['name']: c['value'] for c in driver.get_cookies()}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": URL_FILA,
        }
        
        print(f"     ⬇️  Baixando arquivo...")
        response = requests.get(url_download, headers=headers, cookies=cookies, timeout=120, stream=True)
        response.raise_for_status()
        
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


def ler_e_juntar(caminhos):
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


def subir_para_sheets(df):
    print(f"\n  ↑ Conectando ao Google Sheets...")
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_JSON, scopes=scopes)
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
    print(f"  ✅ {len(df)} linhas gravadas na aba '{ABA_DESTINO}'!")


def main():
    print("=" * 60)
    print("  RECUPERAR RELATÓRIOS DO RADAR TIM (já prontos)")
    print(f"  Início: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 60)
    
    caminhos_baixados = []
    
    for conta in CONTAS:
        print(f"\n{'─' * 60}")
        print(f"  Processando: {conta['nome']} ({conta['login']})")
        print(f"{'─' * 60}")
        
        if not Path(conta["sdtid"]).exists():
            print(f"  ⚠️  Arquivo SDTID não encontrado: {conta['sdtid']} — pulando")
            continue
        
        driver = None
        try:
            driver = criar_driver()
            if fazer_login(driver, conta):
                caminho = baixar_relatorio_mais_recente(driver, conta)
                if caminho:
                    caminhos_baixados.append(caminho)
        except Exception as e:
            print(f"  ❌ Erro fatal em {conta['nome']}: {e}")
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
            print(f"  🔒 Sessão encerrada")
    
    print(f"\n{'=' * 60}")
    print(f"  Resumo: {len(caminhos_baixados)}/{len(CONTAS)} relatórios baixados")
    print(f"{'=' * 60}")
    
    if not caminhos_baixados:
        print("\n  ❌ Nenhum relatório baixado.")
        print(f"  📂 Artefatos de debug salvos em: {PASTA_DEBUG}")
        print(f"     Baixe-os do GitHub Actions para análise.")
        sys.exit(1)
    
    df_final = ler_e_juntar(caminhos_baixados)
    if df_final.empty:
        sys.exit(1)
    
    subir_para_sheets(df_final)
    print(f"\n  🎉 Concluído!")


if __name__ == "__main__":
    main()
