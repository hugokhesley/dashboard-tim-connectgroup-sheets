"""
=====================================================================
  ACTIONS RUNNER — Roda no GitHub Actions
=====================================================================
  Fluxo 100% via Radar (sem IMAP/email):
  1. Login RSA (verificado pela URL final, com retry de token) + solicitar
     relatório para as 3 contas EM PARALELO (lista2.asp).
  2. Poll das contas EM PARALELO (1 driver cada) em report-queue.asp a cada 60s,
     DESDE O INÍCIO (sem espera cega), varrendo as páginas da fila até achar a
     linha "Após 01/05/2009" pronta.
     - Relogin RSA automático se a sessão cair durante o poll.
     - Timeout 145 min por conta + DEADLINE GLOBAL de 160 min: ao bater, para de
       esperar e grava o que já baixou (nunca mais "cancelado = zero gravado").
  3. Download via cookies do Selenium.
  4. Concat + upload para a aba DadosRadar (preserva contas que faltaram).
  5. Heartbeat na aba RadarRunStatus p/ o n8n avisar no sino se a base secar.
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
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from google.oauth2.service_account import Credentials
from securid.sdtid import SdtidFile

# Logs em tempo real: no Actions o stdout é block-buffered (não é TTY), então os
# prints ficavam presos no buffer e eram PERDIDOS quando o job era cancelado no
# timeout — 3h de silêncio. line_buffering força flush a cada linha.
try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass

# ─────────────────────────────────────────────────────────────────
#  ⚙️  CONFIGURAÇÕES
# ─────────────────────────────────────────────────────────────────

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]

ABA_DESTINO       = "DadosRadar"
ABA_STATUS        = "RadarRunStatus"   # heartbeat lido pelo n8n p/ avisar base velha/parcial no sino
INTERVALO_POLL    = 60          # segundos entre cada checagem
# Timeout por conta (as contas rodam em PARALELO). Era 90 min quando ainda havia
# espera cega antes do 1º poll; agora o poll começa na hora e o limite real é o
# deadline global — 145 dá folga para o relatório lento da T3729525 (a maior
# conta) sem nunca passar dos 160.
TIMEOUT_POLL_MIN  = 145

# Deadline global de wall-clock. O job do Actions morre em 180 min (timeout-minutes).
# Antes: 3 contas em SÉRIE × 90 min = até 270 min → estourava os 180 e o job era
# CANCELADO no meio do polling, sem gravar NADA (base congelava). Agora as contas
# rodam em paralelo (pior caso ~90 min) e, se ainda assim algo arrastar, este
# deadline faz o script PARAR e gravar o que já baixou antes de o Actions matar.
GLOBAL_DEADLINE_MIN = 160

URL_RADAR         = "https://radar.timbrasil.com.br/"
URL_LISTA         = "https://radar.timbrasil.com.br/radar-tim/relatorios/lista2.asp"
URL_FILA          = "https://radar.timbrasil.com.br/radar-blue/sistema/report-queue.asp"
URL_START         = "https://radar.timbrasil.com.br/radar-blue/sistema/start.asp"

# Login só conta como OK se a URL final estiver DENTRO do Radar (ver _login_confirmado).
URLS_RADAR_OK     = ("radar-blue", "radar-tim")
ESPERA_POS_LOGIN_S = 60         # quanto esperar o resume do OAuth2 do SmartID concluir

# Quantas páginas da fila varrer procurando o ID. Antes só a página 2 era olhada:
# em 27/jul/2026 a fila da TIM estava com 16 relatórios, o alvo caiu na página 3+
# e o poll reportou "sumiu" até o deadline, com 2 de 3 contas perdidas.
PAGINAS_MAX       = 8

# Palavras que indicam relatório pronto (comparadas sem acento e em minúsculo)
PALAVRAS_PRONTO   = ("concluido", "concluida", "pronto", "disponivel", "finalizado", "ok")

# Palavras que indicam relatório ainda na fila / em processamento
PALAVRAS_PENDENTE = ("pendente", "processando", "fila", "aguardando", "executando", "em andamento")

# Termos na URL que indicam que a sessão caiu e a página voltou pro login
TERMOS_LOGIN_URL  = ("iam-pf", "signon", "login", "authn")

# "dias": em que dias da semana a conta roda (0=segunda ... 6=domingo).
# None/ausente = todo dia. Conta fora de escala NAO e falha: as linhas dela ficam
# preservadas na aba (ver `preservar` no main), entao o dado do ultimo dia em que
# ela rodou continua valendo ate a proxima vez.
CONTAS = [
    {"login": "t3729525", "sdtid": "T3729525_001938489117.sdtid", "dias": None},
    {"login": "t3761125", "sdtid": "T3761125_001938495598.sdtid", "dias": None},
    {"login": "t3748937", "sdtid": "T3748937_001938491397.sdtid", "dias": None},
]


def contas_do_dia(agora_utc=None):
    """Contas em escala para hoje, pelo dia da semana em Brasilia (UTC-3).

    O Actions roda em UTC: as 22h de domingo em Brasilia ja e segunda em UTC, e
    uma conta "so na segunda" rodaria no dia errado se olhassemos o relogio do
    runner. Recebe o instante em UTC para o teste conseguir fixar a data.
    """
    if agora_utc is None:
        agora_utc = datetime.now(timezone.utc)
    dia = (agora_utc - timedelta(hours=3)).weekday()
    return [c for c in CONTAS if not c.get("dias") or dia in c["dias"]]

# Cache de links de download já vistos prontos, por login. Sobrevive entre polls
# para o caso de o ID sair da view padrão (paginação/separação pendente vs concluído).
links_capturados: dict = {}

# Nome do parâmetro de paginação que a fila do Radar honra, por login (descoberto
# no 1º poll que precisou paginar). Evita testar 4 nomes a cada checagem.
paginacao_param: dict = {}

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

def _token_diferente(sdtid_path, token_anterior=None, espera_max_s=75):
    """Gera um token RSA garantindo que NÃO é o mesmo da tentativa anterior.

    O SecurID troca de código a cada 60s e o servidor rejeita reuso do mesmo
    código — repetir o login imediatamente com o token velho falharia de novo
    sem motivo. Espera a janela virar (no máx. ~75s)."""
    token = gerar_token(sdtid_path)
    if token_anterior and token == token_anterior:
        fim = time.time() + espera_max_s
        while token == token_anterior and time.time() < fim:
            time.sleep(5)
            token = gerar_token(sdtid_path)
    return token


def _login_confirmado(driver, timeout_s=ESPERA_POS_LOGIN_S) -> bool:
    """Só considera logado quem chegou de fato no Radar.

    O resume do OAuth2 do SmartID (iam-pf) às vezes emperra — a conta T3729525
    é a mais propensa. Antes o script imprimia '✅ Login OK' INCONDICIONALMENTE
    e seguia com uma sessão morta: a conta 'falhava' silenciosamente e, no
    recover, a base era truncada. Agora a URL é a prova."""
    fim = time.time() + timeout_s
    ultima = ""
    while time.time() < fim:
        ultima = (driver.current_url or "").lower()
        if any(t in ultima for t in URLS_RADAR_OK):
            return True
        # Empurra o resume: às vezes basta pedir a home do Radar de novo.
        try:
            driver.get(URL_START)
        except Exception:
            pass
        time.sleep(4)
    print(f"     ↳ login não saiu do provedor de identidade (URL: {ultima[:70]})")
    return False


def fazer_login(driver, login, sdtid_path, tentativas=2):
    """Login RSA com verificação real + retry com token novo."""
    ultimo_erro = None
    token_usado = None
    for tentativa in range(1, tentativas + 1):
        try:
            # Token gerado AQUI (e não lá dentro) para que uma tentativa que
            # exploda no meio não faça a seguinte reusar o mesmo código RSA.
            token_usado = _token_diferente(sdtid_path, token_usado)
            _fazer_login_uma_vez(driver, login, token_usado)
            if _login_confirmado(driver):
                print(f"  ✅ Login OK — {driver.current_url[:60]}")
                _fechar_popup(driver)
                return
            ultimo_erro = "sessão não chegou no radar-blue"
        except Exception as e:
            ultimo_erro = str(e)
        print(f"  ⚠️ [{login.upper()}] login tentativa {tentativa}/{tentativas} falhou: {ultimo_erro}")
    raise RuntimeError(f"Login falhou para {login.upper()}: {ultimo_erro}")


def _fechar_popup(driver):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    try:
        fechar = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//*[contains(@class,'close') or contains(@aria-label,'lose')]"))
        )
        driver.execute_script("arguments[0].click()", fechar)
        time.sleep(1)
    except Exception:
        pass


def _fazer_login_uma_vez(driver, login, token):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

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
    # Quem declara sucesso é o `_login_confirmado` (URL do Radar), não este passo.


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


def _assinatura_pagina(driver):
    """Conjunto de IDs de relatório visíveis na página atual.

    Serve só para saber se a paginação avançou de verdade: se a assinatura
    repetir, o ASP ignorou o parâmetro (ou a lista acabou)."""
    from selenium.webdriver.common.by import By
    ids = set()
    try:
        for linha in driver.find_elements(By.XPATH, "//tr[contains(., 'Após 01/05/2009')]"):
            try:
                for cel in linha.find_elements(By.XPATH, ".//td"):
                    t = (cel.text or "").strip()
                    if t.isdigit():
                        ids.add(t)
                        break
            except Exception:
                continue
    except Exception:
        return frozenset()
    return frozenset(ids)


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

    # (2) paginação via query string — varre da página 2 até PAGINAS_MAX.
    #     A assinatura (conjunto de IDs da página) diz se o parâmetro foi honrado:
    #     se a página repetir, o parâmetro é ignorado por esse ASP e passamos ao
    #     próximo nome. Isso evita o falso "sumiu" quando a fila tem 3+ páginas.
    vistas = {_assinatura_pagina(driver)}
    params = ("pag", "pagina", "p", "page")
    preferido = paginacao_param.get(login)
    if preferido:   # já descobrimos qual nome esse ASP honra — não redescobrir a cada poll
        params = (preferido,) + tuple(p for p in params if p != preferido)
    for param in params:
        for n in range(2, PAGINAS_MAX + 1):
            try:
                driver.get(f"{URL_FILA}?{param}={n}")
                time.sleep(2)
                if sessao_caiu(driver):
                    return None, None, None
                assinatura = _assinatura_pagina(driver)
                if not assinatura or assinatura in vistas:
                    break   # página vazia, repetida ou parâmetro ignorado
                vistas.add(assinatura)
                paginacao_param[login] = param
                texto, link = _buscar_na_pagina_atual(driver, id_alvo)
                if texto is not None:
                    if link:
                        links_capturados[login] = link
                    return texto, link, f"?{param}={n}"
            except Exception:
                break

    # (3) navegação por link "Próxima/Próximo/Next/»", clicando página a página
    try:
        driver.get(URL_FILA)
        time.sleep(2)
        proximo_xpath = ("//a[contains(text(),'Próxima') or contains(text(),'Próximo') "
                         "or contains(text(),'Next') or contains(text(),'»')]")
        for _ in range(PAGINAS_MAX):
            if sessao_caiu(driver):
                return None, None, None
            proximos = driver.find_elements(By.XPATH, proximo_xpath)
            if not proximos:
                break
            driver.execute_script("arguments[0].click()", proximos[0])
            time.sleep(2)
            if sessao_caiu(driver):
                return None, None, None
            assinatura = _assinatura_pagina(driver)
            if not assinatura or assinatura in vistas:
                break
            vistas.add(assinatura)
            texto, link = _buscar_na_pagina_atual(driver, id_alvo)
            if texto is not None:
                if link:
                    links_capturados[login] = link
                return texto, link, "proxima"
    except Exception as e:
        # Sem este print, falha de Selenium/sessao aqui vira "relatorio sumiu"
        # la em cima — foi o sintoma que confundiu o diagnostico em 27/jul.
        print(f"     ↳ erro na varredura da fila: {type(e).__name__}: {e}")

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


def monitorar_e_baixar(login, sdtid_path, id_alvo, posicao=1, timeout_min=TIMEOUT_POLL_MIN, deadline_ts=None):
    driver = criar_driver()
    try:
        fazer_login(driver, login, sdtid_path)

        # Sem espera cega antes do 1º poll. O código antigo dormia 7 min × posição
        # na fila (em 27/jul: 91, 98 e 105 min!) fazendo keep-alive na MESMA página
        # que o poll consulta — ou seja, gastava a janela inteira ignorando a
        # resposta que já tinha em mãos: a conta que esperou 105 min achou o
        # relatório em "0 min, tent #1". Poll de 60s é barato; começa agora.
        print(f"  ⏱  [{login.upper()}] Posição {posicao} na fila — polling desde já (sem espera cega)")

        inicio = time.time()
        fim_conta = inicio + timeout_min * 60
        tentativa = 0
        while time.time() < fim_conta and (deadline_ts is None or time.time() < deadline_ts):
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

        motivo = "deadline global" if (deadline_ts is not None and time.time() >= deadline_ts) else f"timeout de {timeout_min} min"
        raise TimeoutError(f"{motivo} atingido para {login.upper()} (ID {id_alvo})")

    finally:
        driver.quit()


# ─────────────────────────────────────────────────────────────────
#  SHEETS
# ─────────────────────────────────────────────────────────────────

def subir_para_sheets(df, preservar_existentes=False):
    """Grava o df na aba DadosRadar.

    `preservar_existentes=True` (usado quando ALGUMA conta falhou): em vez de
    limpar a aba, mantém as linhas que já estavam lá e cujo `pedido` NÃO veio
    nesta rodada. Sem isso, uma falha parcial de login apaga a base inteira das
    contas que não baixaram — foi o que aconteceu em 19/jul/2026 (1765 → 15
    linhas), secando QuickTIM e o sync do CRM por 2 dias.
    """
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
    gc = gspread.authorize(creds)
    planilha = gc.open_by_key(SPREADSHEET_ID)
    try:
        aba = planilha.worksheet(ABA_DESTINO)
    except gspread.WorksheetNotFound:
        aba = planilha.add_worksheet(title=ABA_DESTINO, rows=1, cols=1)

    df = df.fillna("")
    dados = [df.columns.tolist()] + df.values.tolist()
    dados = [[str(v) for v in linha] for linha in dados]

    if preservar_existentes:
        col_pedido  = dados[0].index("pedido") if "pedido" in dados[0] else 0
        pedidos_novos = {_num(linha[col_pedido]) for linha in dados[1:]}
        preservadas = _linhas_a_preservar(aba, dados[0], pedidos_novos)
        if preservadas is None:
            print("  ⛔ Não consegui ler a aba atual para preservar as linhas das contas que falharam.")
            print("     ABORTANDO a gravação — melhor base velha que base truncada.")
            sys.exit(1)
        print(f"  🛟 Preservando {len(preservadas)} linha(s) já existentes (contas que falharam nesta rodada)")
        dados += preservadas

    aba.clear()
    aba.update(dados, value_input_option="USER_ENTERED")
    print(f"  ✅ {len(dados) - 1} linhas gravadas em '{ABA_DESTINO}'!")


def _num(valor: str) -> str:
    """Normaliza pedido para comparação: o pandas manda float ('6418984.0')."""
    s = str(valor).strip()
    return s[:-2] if s.endswith(".0") else s


def _linhas_a_preservar(aba, header_novo, pedidos_novos):
    """Linhas já na aba cujo `pedido` não veio nesta rodada, realinhadas ao header novo.

    Retorna None se a aba não puder ser lida/alinhada (aí o chamador aborta).
    """
    try:
        atual = aba.get_all_values()
    except Exception as e:
        print(f"  ⚠️ Falha ao ler a aba atual: {e}")
        return None
    if len(atual) < 2:
        return []

    header_antigo = atual[0]
    if "pedido" not in header_antigo:
        print("  ⚠️ Aba atual sem coluna 'pedido' — não dá para casar com o download novo.")
        return None

    idx_pedido = header_antigo.index("pedido")
    # Mapeia cada coluna do header NOVO para a posição dela no header ANTIGO.
    pos = {col: header_antigo.index(col) if col in header_antigo else None for col in header_novo}

    preservadas = []
    for linha in atual[1:]:
        if idx_pedido >= len(linha) or not linha[idx_pedido] or _num(linha[idx_pedido]) in pedidos_novos:
            continue
        preservadas.append([
            linha[pos[col]] if pos[col] is not None and pos[col] < len(linha) else ""
            for col in header_novo
        ])
    return preservadas


def registrar_status(status, linhas, contas_ok, contas_falhas, detalhe=""):
    """Grava 1 linha de heartbeat na aba RadarRunStatus (sempre, mesmo em falha).

    O n8n (na LAN, alcança o CRM) lê essa aba: se `run_em_utc` ficar velho ou
    `status != ok`, avisa o Hugo no sino. É assim que a base contorna o fato de o
    Actions (nuvem) não conseguir falar direto com o CRM LAN-only. NUNCA derruba o
    run — o marcador é observabilidade, não caminho crítico.
    """
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
        gc = gspread.authorize(creds)
        planilha = gc.open_by_key(SPREADSHEET_ID)
        try:
            aba = planilha.worksheet(ABA_STATUS)
        except gspread.WorksheetNotFound:
            aba = planilha.add_worksheet(title=ABA_STATUS, rows=2, cols=6)
        agora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        header = ["run_em_utc", "status", "linhas", "contas_ok", "contas_falhas", "detalhe"]
        row    = [agora, status, str(linhas),
                  ",".join(c.upper() for c in contas_ok),
                  ",".join(c.upper() for c in contas_falhas), detalhe]
        aba.update([header, row], value_input_option="USER_ENTERED")
        print(f"  🩺 Status registrado: {status} | {linhas} linhas | ok={row[3]} | falhas={row[4]}")
    except Exception as e:
        print(f"  ⚠️ Falha ao registrar status (não crítico): {e}")


def _solicitar_conta(conta, data_inicio, data_fim):
    """Etapa 1 de UMA conta, com 1 retry. Retorna (login, id, posicao) ou levanta."""
    login = conta["login"]
    ultimo_erro = None
    # 1 retry: a falha mais comum é read timeout do webdriver, que costuma passar na 2ª.
    for tentativa in (1, 2):
        try:
            id_solicitado, pos = solicitar_relatorio(login, conta["sdtid"], data_inicio, data_fim)
            print(f"  ✓ [{login.upper()}] solicitado: ID {id_solicitado}, posição {pos}")
            return login, id_solicitado, pos
        except Exception as e:
            ultimo_erro = e
            if tentativa == 1:
                print(f"  ⚠️ [{login.upper()}] tentativa 1 falhou: {e} — repetindo em 30s")
                time.sleep(30)
    raise RuntimeError(f"{login.upper()} falhou na solicitação: {ultimo_erro}")


# ─────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  ACTIONS RUNNER — ATUALIZAÇÃO DADOSRADAR")
    print("=" * 55)

    deadline_ts = time.time() + GLOBAL_DEADLINE_MIN * 60
    print(f"⏳ Deadline global: {GLOBAL_DEADLINE_MIN} min — grava o que tiver antes de o Actions matar o job (180 min)")

    data_inicio, data_fim = calcular_datas()
    print(f"📅 Período: {data_inicio} → {data_fim}")

    contas = contas_do_dia()
    fora_de_escala = [c["login"] for c in CONTAS if c not in contas]
    if fora_de_escala:
        print(f"📆 Fora de escala hoje: {', '.join(l.upper() for l in fora_de_escala)} "
              f"— as linhas delas ficam preservadas na aba")

    # ── ETAPA 1: Solicitar relatórios (contas do dia EM PARALELO) ─
    print(f"\n🌐 Solicitando relatórios das {len(contas)} contas em paralelo...")
    solicitacoes = {}   # login -> (id_alvo, posicao)
    with ThreadPoolExecutor(max_workers=len(contas)) as ex:
        futuros = {ex.submit(_solicitar_conta, c, data_inicio, data_fim): c for c in contas}
        for fut in as_completed(futuros):
            conta = futuros[fut]
            try:
                login, id_alvo, pos = fut.result()
                solicitacoes[login] = (id_alvo, pos)
            except Exception as e:
                print(f"  ❌ {conta['login'].upper()}: {e}")

    if not solicitacoes:
        print("❌ Nenhum relatório solicitado. Base preservada (nada gravado).")
        registrar_status("falha", 0, [], [c["login"] for c in contas], "nenhuma solicitação OK")
        sys.exit(1)

    print(f"\n✅ Solicitações OK: {', '.join(l.upper() for l in solicitacoes)}")

    # ── ETAPA 2: Polling + download (EM PARALELO, com deadline) ─
    print(f"\n⬇️  Polling paralelo (intervalo {INTERVALO_POLL}s, {TIMEOUT_POLL_MIN} min/conta, deadline global {GLOBAL_DEADLINE_MIN} min)")
    dfs = {}   # login -> df
    with ThreadPoolExecutor(max_workers=len(solicitacoes)) as ex:
        futuros = {}
        for login, (id_alvo, pos) in solicitacoes.items():
            conta = next(c for c in contas if c["login"] == login)
            print(f"  🔄 Monitorando {login.upper()} (ID {id_alvo}, posição {pos})...")
            futuros[ex.submit(monitorar_e_baixar, login, conta["sdtid"], id_alvo, pos, TIMEOUT_POLL_MIN, deadline_ts)] = login
        for fut in as_completed(futuros):
            login = futuros[fut]
            try:
                dfs[login] = fut.result()
            except Exception as e:
                print(f"  ❌ [{login.upper()}] {e}")

    logins_ok = set(dfs)
    # Falha = conta que ESTAVA em escala hoje e mesmo assim não rendeu df.
    # Conta fora de escala não é falha — não pode pintar o run de vermelho todo
    # dia nem bloquear o notify_pendentes.
    falhadas  = [c["login"] for c in contas if c["login"] not in logins_ok]
    parcial   = bool(falhadas)

    if not dfs:
        print("❌ Nenhum arquivo baixado. Base preservada (nada gravado).")
        registrar_status("falha", 0, [], [c["login"] for c in contas], "nenhum download")
        sys.exit(1)

    # ── ETAPA 3: Concat + Upload ──────────────────────────────
    # Preservar é mais amplo que "deu falha": vale para QUALQUER conta cujas linhas
    # não vieram nesta rodada — falhou OU está fora de escala. Sem isso, a rodada
    # de terça daria aba.clear() e apagaria o que a conta de segunda trouxe.
    preservar = bool(falhadas) or bool(fora_de_escala)
    df_final = pd.concat(list(dfs.values()), ignore_index=True)
    print(f"\n📋 Total consolidado: {len(df_final)} linhas ({len(logins_ok)}/{len(contas)} contas do dia)")
    if parcial:
        print(f"⚠️ RODADA PARCIAL — contas sem dados: {', '.join(l.upper() for l in falhadas)}")
    if preservar:
        print("🛟 Gravando em modo preservar — linhas das contas ausentes ficam na aba")
    subir_para_sheets(df_final, preservar_existentes=preservar)

    if parcial:
        detalhe = f"faltaram {len(falhadas)} de {len(contas)} contas do dia"
    elif fora_de_escala:
        detalhe = f"fora de escala: {', '.join(fora_de_escala)}"
    else:
        detalhe = ""
    registrar_status(
        "parcial" if parcial else "ok",
        len(df_final), sorted(logins_ok), falhadas, detalhe,
    )

    print("\n🎉 DadosRadar atualizado!")
    print("=" * 55)

    # Marca o run como falha para a rodada parcial ficar visível no Actions (+ e-mail nativo do GitHub)
    if parcial:
        print(f"\n⚠️ ATENÇÃO: {len(falhadas)} de {len(contas)} contas falharam: {', '.join(l.upper() for l in falhadas)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
