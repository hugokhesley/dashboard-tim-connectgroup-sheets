"""
=====================================================================
  ACTIONS RECOVER — Recupera relatórios JÁ PRONTOS no Radar
=====================================================================
  Diferente do actions_runner.py:
    - NÃO solicita relatório novo
    - NÃO espera nada
    - Vai DIRETO na fila do Radar
    - Pega o relatório mais recente PRONTO de cada conta
    - Baixa, junta e sobe pro Sheets

  Use quando você já sabe que os relatórios foram gerados
  (ex: solicitou manual e quer só consolidar).

  ⚠️ Este script COMPARTILHA login, download e gravação com o
  actions_runner.py de propósito. Antes ele tinha cópias próprias e
  desatualizadas: em 25/jul/2026 o runner já preservava as linhas das
  contas que falhavam, mas o recover ainda fazia clear()+update cego e
  TRUNCOU a base de 2006 → 565 linhas quando a conta T3729525 emperrou
  no login. Não recriar essas funções aqui — importar.
=====================================================================
"""

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd

from actions_runner import (
    CONTAS,
    contas_do_dia,        # respeita conta que só roda em certos dias
    PAGINAS_MAX,
    URL_FILA,
    _assinatura_pagina,
    baixar_via_cookies,
    criar_driver,
    esta_pronto,
    fazer_login,          # verifica a URL final e faz retry com token novo
    registrar_status,     # heartbeat lido pelo n8n
    subir_para_sheets,    # sabe preservar as linhas das contas que faltaram
)

try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass


# ─────────────────────────────────────────────────────────────────
#  BAIXAR RELATÓRIO MAIS RECENTE DA FILA
# ─────────────────────────────────────────────────────────────────

def _melhor_pronto_na_pagina(driver):
    """(id, link) do maior ID PRONTO com link de download na página atual."""
    from selenium.webdriver.common.by import By

    melhor_id, melhor_link = -1, None
    for linha in driver.find_elements(By.XPATH, "//tr[contains(., 'Após 01/05/2009')]"):
        try:
            if not esta_pronto(linha.text or ""):
                continue
            id_rel = None
            for cel in linha.find_elements(By.XPATH, ".//td"):
                t = (cel.text or "").strip()
                if t.isdigit():
                    id_rel = int(t)
                    break
            if id_rel is None or id_rel <= melhor_id:
                continue
            try:
                link_el = linha.find_element(By.XPATH, ".//a[contains(@href,'report-queue-download')]")
            except Exception:
                continue
            melhor_id, melhor_link = id_rel, link_el.get_attribute("href")
        except Exception:
            continue
    return melhor_id, melhor_link


def pegar_relatorio_mais_recente(driver, login: str):
    driver.get(URL_FILA)
    time.sleep(5)

    melhor_id, melhor_link = _melhor_pronto_na_pagina(driver)
    print(f"  📊 [{login.upper()}] página 1 — melhor pronto: {melhor_id if melhor_id > 0 else 'nenhum'}")

    # Fila cheia empurra o relatório pronto para as páginas seguintes (foi o que
    # aconteceu no runner em 27/jul, com 16 relatórios na fila).
    if melhor_id < 0:
        vistas = {_assinatura_pagina(driver)}
        for param in ("pag", "pagina", "p", "page"):
            for n in range(2, PAGINAS_MAX + 1):
                try:
                    driver.get(f"{URL_FILA}?{param}={n}")
                    time.sleep(2)
                    assinatura = _assinatura_pagina(driver)
                    if not assinatura or assinatura in vistas:
                        break
                    vistas.add(assinatura)
                    id_pag, link_pag = _melhor_pronto_na_pagina(driver)
                    if id_pag > melhor_id:
                        melhor_id, melhor_link = id_pag, link_pag
                        print(f"  📊 [{login.upper()}] achado na ?{param}={n}: ID {melhor_id}")
                except Exception:
                    break
            if melhor_id > 0:
                break

    if melhor_id < 0 or not melhor_link:
        print(f"  ⚠️ Nenhum relatório PRONTO encontrado para {login.upper()}")
        return None

    print(f"  ✅ [{login.upper()}] Relatório mais recente: ID {melhor_id}")
    df = baixar_via_cookies(driver, melhor_link)
    print(f"  📦 [{login.upper()}] {len(df)} linhas baixadas")
    return df


def processar_conta(conta):
    """Baixa o relatório pronto de UMA conta. Devolve (login, df) ou levanta."""
    login, sdtid = conta["login"], conta["sdtid"]
    if not os.path.exists(sdtid):
        raise RuntimeError(f"SDTID não encontrado: {sdtid}")
    driver = criar_driver()
    try:
        fazer_login(driver, login, sdtid)
        df = pegar_relatorio_mais_recente(driver, login)
        if df is None or df.empty:
            raise RuntimeError("nenhum relatório pronto na fila")
        return login, df
    finally:
        driver.quit()


# ─────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  ACTIONS RECOVER — RELATÓRIOS JÁ PRONTOS")
    print(f"  Início: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 55)

    contas = contas_do_dia()
    fora_de_escala = [c["login"] for c in CONTAS if c not in contas]
    if fora_de_escala:
        print(f"📆 Fora de escala hoje: {', '.join(l.upper() for l in fora_de_escala)} "
              f"— as linhas delas ficam preservadas na aba")

    dfs = {}
    with ThreadPoolExecutor(max_workers=len(contas)) as ex:
        futuros = {ex.submit(processar_conta, c): c["login"] for c in contas}
        for fut in as_completed(futuros):
            login = futuros[fut]
            try:
                _, df = fut.result()
                dfs[login] = df
            except Exception as e:
                print(f"  ❌ [{login.upper()}] {e}")

    logins_ok = sorted(dfs)
    falhadas  = [c["login"] for c in contas if c["login"] not in dfs]
    parcial   = bool(falhadas)

    print(f"\n{'=' * 55}")
    print(f"  ✅ OK:    {len(logins_ok)}/{len(contas)} — {', '.join(l.upper() for l in logins_ok)}")
    if falhadas:
        print(f"  ❌ Falha: {len(falhadas)}/{len(contas)} — {', '.join(l.upper() for l in falhadas)}")
    print(f"{'=' * 55}")

    if not dfs:
        print("\n❌ Nenhum relatório baixado. Base preservada (nada gravado).")
        registrar_status("falha", 0, [], [c["login"] for c in contas], "recover: nenhum download")
        sys.exit(1)

    df_final = pd.concat(list(dfs.values()), ignore_index=True)
    print(f"\n📋 Total consolidado: {len(df_final)} linhas ({len(logins_ok)}/{len(contas)} contas do dia)")
    if parcial:
        print(f"⚠️ RODADA PARCIAL — contas sem dados: {', '.join(l.upper() for l in falhadas)}")

    # preservar_existentes: mantém as linhas das contas que faltaram em vez de
    # truncar a base (incidente 25/jul, 2006 → 565 linhas). Vale também para
    # conta fora de escala, que não é falha mas também não trouxe linha nenhuma.
    preservar = bool(falhadas) or bool(fora_de_escala)
    if preservar:
        print("🛟 Gravando em modo preservar — linhas das contas ausentes ficam na aba")
    subir_para_sheets(df_final, preservar_existentes=preservar)

    if parcial:
        detalhe = f"recover: faltaram {len(falhadas)} de {len(contas)} contas do dia"
    elif fora_de_escala:
        detalhe = f"recover — fora de escala: {', '.join(fora_de_escala)}"
    else:
        detalhe = "recover"
    registrar_status(
        "parcial" if parcial else "ok",
        len(df_final), logins_ok, falhadas, detalhe,
    )

    print("\n🎉 DadosRadar atualizado!")
    print("=" * 55)

    if parcial:
        print(f"\n⚠️ ATENÇÃO: {len(falhadas)} de {len(contas)} conta(s) falharam: "
              f"{', '.join(l.upper() for l in falhadas)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
