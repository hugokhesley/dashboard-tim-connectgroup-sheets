"""Teste: logado pelo RADAR, o Chrome do GitHub entra no Phoenix (P2B)?

O caminho do Hugo (14/10/2026): login no RADAR (iam-pf + RSA), e na mesma
sessao trocar o endereco para https://phoenix2businesspcs.timbrasil.com.br/.
Um `curl` sozinho foi barrado (403 Incapsula, run 38666393675), mas curl nao
roda o desafio em JavaScript do Imperva nem leva a sessao do login.

Chrome COMUM, sem headless e sem disfarce, numa tela virtual (xvfb-run).
O repositorio e PUBLICO: o log so mostra host, titulo e sim/nao - nenhuma
URL com parametro, nenhum dado de cliente, nenhuma captura de tela.
"""
import sys
import time
from urllib.parse import urlparse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from actions_runner import CONTAS, fazer_login

PHOENIX = "https://phoenix2businesspcs.timbrasil.com.br/"
LOGIN = sys.argv[1] if len(sys.argv) > 1 else "t3761125"


def resumo(driver, etapa):
    url = driver.current_url or ""
    p = urlparse(url)
    fonte = (driver.page_source or "")
    incapsula = "_Incapsula_Resource" in fonte or "Request unsuccessful" in fonte
    print(f"[{etapa}] host={p.hostname} caminho={p.path[:40]} titulo={driver.title[:60]!r} "
          f"incapsula={'SIM' if incapsula else 'nao'} tamanho={len(fonte)}")
    return p.hostname or "", incapsula


def main():
    conta = next(c for c in CONTAS if c["login"] == LOGIN)
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1366,900")
    driver = webdriver.Chrome(options=options)
    try:
        fazer_login(driver, conta["login"], conta["sdtid"])
        resumo(driver, "radar")
        driver.get(PHOENIX)
        time.sleep(20)
        host, bloqueado = resumo(driver, "phoenix 20s")
        time.sleep(20)
        host, bloqueado = resumo(driver, "phoenix 40s")
        if bloqueado:
            print("RESULTADO: BARRADO pelo Imperva mesmo logado no Chrome")
            sys.exit(1)
        if host.endswith("timbrasil.com.br") and "iam-pf" not in host:
            print("RESULTADO: PASSA - o Chrome logado entrou no Phoenix")
        else:
            print("RESULTADO: DIFERENTE - parou fora do Phoenix (ver host acima)")
            sys.exit(1)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
