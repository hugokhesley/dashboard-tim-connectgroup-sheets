"""
=====================================================================
  ACTIONS RUNNER — Roda no GitHub Actions
=====================================================================
  Fluxo 100% via Radar (sem IMAP/email):
  1. Login RSA + solicitar relatório para cada conta (lista2.asp)
  2. Para cada conta: abre 1 driver, faz login e fica em polling
     em report-queue.asp a cada 60s até achar linha
     "Após 01/05/2009" com status de pronto.
     - Relogin RSA automático se a sessão cair durante o poll.
     - Timeout 90 min por conta.
  3. Download via cookies do Selenium.
  4. Concat + upload para a aba DadosRadar.
=====================================================================
"""

import os
import io
import sys
import time
import unicodedata
import requests
import pandas as pd
import gspread
from datetime import datetime
from google.oauth2.service_account import Credentials
from securid.sdtid import SdtidFile

# ─────────────────────────────────────────────────────────────────
#  ⚙️  CONFIGURAÇÕES
# ─────────────────────────────────────────────────────────────────

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]

ABA_DESTINO       = "DadosRadar"
INTERVALO_POLL    = 60          # segundos entre cada checagem
TIMEOUT_POLL_MIN  = 90          # timeout por conta

URL_RADAR         = "https://radar.timbrasil.com.br/"
URL_LISTA         = "https://radar.timbrasil.com.br/radar-tim/relatorios/lista2.asp"
URL_FILA          = "https://radar.timbrasil.com.br/radar-blue/sistema/report-queue.asp"

# Palavras que indicam relatório pronto (comparadas sem acento e em minúsculo)
PALAVRAS_PRONTO   = ("concluido", "concluida", "pronto", "disponivel", "finalizado", "ok")

# Palavras que indicam relatório ainda na fila / em processamento
PALAVRAS_PENDENTE = ("pendente", "processando", "fila", "aguardando", "executando", "em andamento")

# Termos na URL que indicam que a sessão caiu e a página voltou pro login
TERMOS_LOGIN_URL  = ("iam-pf", "signon", "login", "authn")

CONTAS = [
    {"login": "t3729525", "sdtid": "T3729525_001938489117.sdtid"},
    {"login": "t3761125", "sdtid": "T3761125_001938495598.sdtid"},
    {"login": "t3748937", "sdtid": "T3748937_001938491397.sdtid"},
]

# Cache de links de download já vistos prontos, por login. Sobrevive entre polls
# para o caso de o ID sair da view padrão (paginação/separação pendente vs concluído).
links_capturados: dict = {}

# ─────────────────────────────────────────────────────────────────
#  MONKEY-PATCH RSA
# ─────────────────────────────────────────────────────────────────

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


def _normalizar(texto: str) -> str:
    nfd = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn").lower()


def esta_pronto(texto_linha: str) -> bool:
    n = _normalizar(texto_linha)
    return any(p in n for p in PALAVRAS_PRONTO)


def esta_pendente(texto_linha: str) -> bool:
    n = _normalizar(texto_linha)
    return any(p in n for p in PALAVRAS_PENDENTE)


def sessao_caiu(driver) -> bool:
    url = (driver.current_url or "").lower()
    return any(t in url for t in TERMOS_LOGIN_URL)


# ─────────────────────────────────────────────────────────────────
#  SELENIUM — criação do driver
# ─────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────
#  SELENIUM — login RSA
# ─────────────────────────────────────────────────────────────────

def fazer_login(driver, login, sdtid_path):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    token = gerar_token(sdtid_path)
    print(f"  🔐 Token gerado para {login.upper()}")

    # Garante que um relogin parte de um estado limpo (cookies/sessão antiga zerados)
    try:
        driver.delete_all_cookies()
    except Exception:
        pass

    driver.get(URL_RADAR)
    time.sleep(5)

    # Username — falha rápido se o campo não estiver interagível
    try:
        campo = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "identifierInput")))
        campo.clear()
        campo.send_keys(login)
        btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.ID, "signOnButton")))
        driver.execute_script("arguments[0].click()", btn)
        time.sleep(4)
    except Exception as e:
        raise RuntimeError(f"Login falhou para {login.upper()}: campo de username não interagível, sessão possivelmente corrompida ({e})")

    # SmartID
    try:
        WebDriverWait(driver, 20).until(lambda d: "iam-pf" in d.current_url)
        time.sleep(3)
    except Exception:
        pass

    # Token RSA
    campo_token = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "password")))
    campo_token.send_keys(token)
    time.sleep(1)
    btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "signOnButton")))
    driver.execute_script("arguments[0].click()", btn)
    time.sleep(8)
    print(f"  ✅ Login OK — {driver.current_url[:60]}")

    # Fecha popup se aparecer
    try:
        fechar = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//*[contains(@class,'close') or contains(@aria-label,'lose')]"))
        )
        driver.execute_script("arguments[0].click()", fechar)
        time.sleep(1)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────
#  ETAPA 1 — Solicitar relatório
# ─────────────────────────────────────────────────────────────────

def solicitar_relatorio(login, sdtid_path, data_inicio, data_fim):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    driver = criar_driver()
    try:
        fazer_login(driver, login, sdtid_path)

        driver.get(URL_LISTA)
        time.sleep(5)

        # Seleciona "Base Geral - Após 01/05/2009"
        base = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(text(),'Após 01/05/2009')]"))
        )
        driver.execute_script("arguments[0].click()", base)
        time.sleep(5)

        # Preenche datas
        campo_de = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.NAME, "a.dt_precadastro_de")))
        driver.execute_script("arguments[0].removeAttribute('readonly')", campo_de)
        driver.execute_script(f"arguments[0].value = '{data_inicio}'", campo_de)
        campo_ate = driver.find_element(By.NAME, "a.dt_precadastro_ate")
        driver.execute_script("arguments[0].removeAttribute('readonly')", campo_ate)
        driver.execute_script(f"arguments[0].value = '{data_fim}'", campo_ate)

        # Checkboxes
        for valor in ["1", "2", "3"]:
            try:
                cb = driver.find_element(By.XPATH, f"//input[@type='checkbox' and @name='g.idtipocontrata' and @value='{valor}']")
                if not cb.is_selected():
                    driver.execute_script("arguments[0].click()", cb)
            except Exception:
                pass

        # Gerar
        gerar = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//input[@value='Gerar Relatório']")))
        driver.execute_script("arguments[0].click()", gerar)
        time.sleep(5)
        print(f"  ✓ Relatório solicitado para {login.upper()}")

        # Captura ID e posição do relatório recém-solicitado
        driver.get(URL_FILA)
        time.sleep(3)
        id_solicitado, posicao = capturar_id_e_posicao(driver, login)
        print(f"  📊 ID solicitado: {id_solicitado}, posição: {posicao}")
        return id_solicitado, posicao

    finally:
        driver.quit()


def capturar_id_e_posicao(driver, login: str):
    """Procura entre as linhas pendentes a mais recente (maior ID) para 'Após 01/05/2009'
    e devolve (id, posicao). Levanta RuntimeError se nenhuma linha for parseável."""
    from selenium.webdriver.common.by import By
    linhas = driver.find_elements(By.XPATH, "//tr[contains(., 'Após 01/05/2009')]")
    melhor_id = -1
    posicao   = 1
    for linha in linhas:
        try:
            if not esta_pendente(linha.text):
                continue
            celulas = linha.find_elements(By.XPATH, ".//td")
            id_rel = None
            for cel in celulas:
                t = (cel.text or "").strip()
                if t.isdigit():
                    id_rel = int(t)
                    break
            if id_rel is None:
                continue
            pos_local = 1
            for cel in reversed(celulas):
                t = (cel.text or "").strip()
                if t.isdigit():
                    pos_local = int(t)
                    break
            if id_rel > melhor_id:
                melhor_id = id_rel
                posicao   = pos_local
        except Exception:
            continue
    if melhor_id < 0:
        raise RuntimeError(f"Não foi possível capturar o ID do relatório recém-solicitado para {login.upper()}")
    return melhor_id, posicao


# ─────────────────────────────────────────────────────────────────
#  ETAPA 2 — Polling no report-queue + download
# ─────────────────────────────────────────────────────────────────

def _buscar_na_pagina_atual(driver, id_alvo: int):
    """Varre o DOM atual procurando linha cujo primeiro td numérico == id_alvo.
    Devolve (texto_linha, href_download_ou_None) ou (None, None)."""
    from selenium.webdriver.common.by import By
    linhas = driver.find_elements(By.XPATH, "//tr[contains(., 'Após 01/05/2009')]")
    for linha in linhas:
        try:
            celulas = linha.find_elements(By.XPATH, ".//td")
            id_rel = None
            for cel in celulas:
                t = (cel.text or "").strip()
                if t.isdigit():
                    id_rel = int(t)
                    break
            if id_rel != id_alvo:
                continue
            link = None
            try:
                link_el = linha.find_element(By.XPATH, ".//a[contains(@href,'report-queue-download')]")
                link = link_el.get_attribute("href")
            except Exception:
                pass
            return linha.text, link
        except Exception:
            continue
    return None, None


def encontrar_relatorio_alvo(driver, id_alvo: int, login: str):
    """Localiza a linha do id_alvo em camadas, para tolerar paginação ou
    separação visual entre pendente e concluído.

    Devolve (texto, link, estrategia) — estrategia ∈
    {'cache', 'padrao', '?pag=2', '?pagina=2', '?p=2', '?page=2', 'proxima'}.
    (None, None, None) se nenhuma camada localizou."""
    from selenium.webdriver.common.by import By

    # (0) cache — link já capturado em poll anterior é prova suficiente
    if login in links_capturados:
        return "[cache]", links_capturados[login], "cache"

    # (1) página padrão (URL_FILA já foi carregada pelo loop antes dessa chamada)
    texto, link = _buscar_na_pagina_atual(driver, id_alvo)
    if texto is not None:
        if link:
            links_capturados[login] = link
        return texto, link, "padrao"

    # (2) variações de paginação via query string
    for param in ("pag", "pagina", "p", "page"):
        try:
            driver.get(f"{URL_FILA}?{param}=2")
            time.sleep(2)
            if sessao_caiu(driver):
                return None, None, None
            texto, link = _buscar_na_pagina_atual(driver, id_alvo)
            if texto is not None:
                estrategia = f"?{param}=2"
                if link:
                    links_capturados[login] = link
                return texto, link, estrategia
        except Exception:
            continue

    # (3) tenta clicar em link "Próxima/Próximo/Next/»"
    try:
        driver.get(URL_FILA)
        time.sleep(2)
        if sessao_caiu(driver):
            return None, None, None
        proximo_xpath = "//a[contains(text(),'Próxima') or contains(text(),'Próximo') or contains(text(),'Next') or contains(text(),'»')]"
        proximos = driver.find_elements(By.XPATH, proximo_xpath)
        if proximos:
            driver.execute_script("arguments[0].click()", proximos[0])
            time.sleep(2)
            if sessao_caiu(driver):
                return None, None, None
            texto, link = _buscar_na_pagina_atual(driver, id_alvo)
            if texto is not None:
                if link:
                    links_capturados[login] = link
                return texto, link, "proxima"
    except Exception:
        pass

    return None, None, None


def baixar_via_cookies(driver, link):
    cookies = driver.get_cookies()
    sessao  = requests.Session()
    for c in cookies:
        sessao.cookies.set(c["name"], c["value"])
    resp    = sessao.get(link, headers={"User-Agent": "Mozilla/5.0"}, timeout=120)
    content = resp.content
    try:
        df = pd.read_excel(io.BytesIO(content), engine="openpyxl", header=0)
    except Exception:
        df = pd.read_excel(io.BytesIO(content), engine="xlrd", header=0)
    return df


def monitorar_e_baixar(login, sdtid_path, id_alvo, posicao=1, timeout_min=TIMEOUT_POLL_MIN):
    driver = criar_driver()
    try:
        fazer_login(driver, login, sdtid_path)

        espera_inicial_min = max(0, (posicao - 1) * 7)
        if espera_inicial_min > 0:
            print(f"  ⏱  [{login.upper()}] Posição {posicao}, aguardando {espera_inicial_min} min antes do primeiro poll")
            restante = espera_inicial_min
            while restante > 0:
                chunk = min(4, restante)
                time.sleep(chunk * 60)
                restante -= chunk
                decorrido = espera_inicial_min - restante
                if restante > 0:
                    try:
                        driver.get(URL_FILA)
                    except Exception:
                        pass
                    print(f"  ⏱  [{login.upper()}] keep-alive durante espera inicial ({decorrido}/{espera_inicial_min} min)")
        else:
            print(f"  ⏱  [{login.upper()}] Posição {posicao}, sem espera inicial")

        inicio = time.time()
        tentativa = 0
        while time.time() - inicio < timeout_min * 60:
            tentativa += 1
            try:
                driver.get(URL_FILA)
                time.sleep(3)

                if sessao_caiu(driver):
                    print(f"  ⚠️ [{login.upper()}] sessão caiu — refazendo login RSA")
                    fazer_login(driver, login, sdtid_path)
                    continue

                texto, link, estrategia = encontrar_relatorio_alvo(driver, id_alvo, login)

                # Fallback (cache, ?pag=N, proxima): link é prova suficiente
                if estrategia and estrategia != "padrao" and link:
                    decorrido = int((time.time() - inicio) / 60)
                    print(f"  ✅ [{login.upper()}] ID {id_alvo} encontrado via {estrategia} ({decorrido} min, tent #{tentativa})")
                    df = baixar_via_cookies(driver, link)
                    print(f"  📦 [{login.upper()}] {len(df)} linhas baixadas")
                    return df

                # Página padrão: precisa ter status pronto + link
                if estrategia == "padrao" and texto is not None and esta_pronto(texto) and link:
                    decorrido = int((time.time() - inicio) / 60)
                    print(f"  ✅ [{login.upper()}] ID {id_alvo} pronto ({decorrido} min, tent #{tentativa})")
                    df = baixar_via_cookies(driver, link)
                    print(f"  📦 [{login.upper()}] {len(df)} linhas baixadas")
                    return df

                if tentativa % 5 == 0:
                    if texto is None:
                        status = "sumiu (não achou em padrão, ?pag=2 nem 'Próxima')"
                    elif esta_pronto(texto):
                        status = "pronto (sem link ainda)"
                    elif esta_pendente(texto):
                        status = "pendente/processando"
                    else:
                        status = "desconhecido"
                    print(f"  [{login.upper()}] aguardando ID {id_alvo}... status atual: {status} (poll #{tentativa})")

                time.sleep(INTERVALO_POLL)

            except Exception as e:
                print(f"  ⚠️ [{login.upper()}] erro no poll #{tentativa}: {e}")
                time.sleep(INTERVALO_POLL)

        raise TimeoutError(f"Timeout de {timeout_min} min atingido para {login.upper()} (ID {id_alvo})")

    finally:
        driver.quit()


# ─────────────────────────────────────────────────────────────────
#  SHEETS
# ─────────────────────────────────────────────────────────────────

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
    print(f"  ✅ {len(df)} linhas gravadas em '{ABA_DESTINO}'!")


# ─────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  ACTIONS RUNNER — ATUALIZAÇÃO DADOSRADAR")
    print("=" * 55)

    data_inicio, data_fim = calcular_datas()
    print(f"📅 Período: {data_inicio} → {data_fim}")

    # ── ETAPA 1: Solicitar relatórios ─────────────────────────
    contas_ok = []
    ids       = {}
    posicoes  = {}
    for conta in CONTAS:
        print(f"\n🌐 Solicitando relatório — {conta['login'].upper()}")
        try:
            id_solicitado, pos = solicitar_relatorio(conta["login"], conta["sdtid"], data_inicio, data_fim)
            ids[conta["login"]]      = id_solicitado
            posicoes[conta["login"]] = pos
            contas_ok.append(conta)
        except Exception as e:
            print(f"  ❌ FALHA em {conta['login'].upper()}, pulando: {e}")

    if not contas_ok:
        print("❌ Nenhum relatório solicitado. Abortando.")
        exit(1)

    print(f"\n✅ Contas com solicitação OK: {', '.join(c['login'].upper() for c in contas_ok)}")

    # ── ETAPA 2: Polling + download por conta ─────────────────
    print(f"\n⬇️  Polling em report-queue.asp (intervalo {INTERVALO_POLL}s, timeout {TIMEOUT_POLL_MIN} min/conta)")
    dfs = []
    logins_ok = set()
    for conta in contas_ok:
        pos      = posicoes[conta["login"]]
        id_alvo  = ids[conta["login"]]
        print(f"\n🔄 Monitorando {conta['login'].upper()} (ID {id_alvo}, posição {pos})...")
        try:
            df = monitorar_e_baixar(conta["login"], conta["sdtid"], id_alvo=id_alvo, posicao=pos)
            dfs.append(df)
            logins_ok.add(conta["login"])
        except Exception as e:
            print(f"  ❌ {conta['login'].upper()}: {e}")

    if not dfs:
        print("❌ Nenhum arquivo baixado. Abortando.")
        exit(1)

    # ── ETAPA 3: Concat + Upload ──────────────────────────────
    df_final = pd.concat(dfs, ignore_index=True)
    print(f"\n📋 Total consolidado: {len(df_final)} linhas")
    subir_para_sheets(df_final)

    print("\n🎉 DadosRadar atualizado com sucesso!")
    print("=" * 55)

    # Marca o run como falha se alguma conta solicitada não rendeu df
    if len(dfs) < len(contas_ok):
        falhadas = [c["login"].upper() for c in contas_ok if c["login"] not in logins_ok]
        print(f"\n⚠️ ATENÇÃO: {len(falhadas)} de {len(contas_ok)} contas falharam: {', '.join(falhadas)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
