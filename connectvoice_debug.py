"""
connectvoice_debug.py
Script de diagnóstico — mostra exatamente o que o Connect Voice retorna.
Rode UMA VEZ para entender a estrutura da resposta.
"""

import requests
import os
import json
from datetime import date

CONFIG = {
    "cv_login_url":   "https://voice.connectgroup.solutions",
    "cv_extrato_url": "https://voice.connectgroup.solutions/Relatorios/buscaLog_chamadas",
    "cv_usuario":     os.getenv("CV_USUARIO", "hugonobrega@conectserra"),
    "cv_senha":       os.getenv("CV_SENHA",   "Timbrasil@3477"),
}

def periodo_mes_atual():
    hoje   = date.today()
    inicio = hoje.replace(day=1)
    return f"{inicio.strftime('%d/%m/%Y')} - {hoje.strftime('%d/%m/%Y')}"

session = requests.Session()

# LOGIN
print(">>> Fazendo login...")
r_login = session.post(
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
print(f"    Status: {r_login.status_code} | URL final: {r_login.url}")
print(f"    Cookies: {dict(session.cookies)}")

# EXTRATO
print("\n>>> Buscando extrato...")
periodo = periodo_mes_atual()
r = session.post(
    CONFIG["cv_extrato_url"],
    data={
        "usuario":         "todos",
        "sentido":         "Sainte",
        "reservation":     periodo,
        "numero_entrante": "",
        "numero":          "",
        "resultado":       "ANSWER",
        "campanha":        "",
        "protocolo":       "",
        "acao":            "0",
    },
    headers={
        "User-Agent":       "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Content-Type":     "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer":          "https://voice.connectgroup.solutions/Relatorios/log_chamadas",
        "Origin":           "https://voice.connectgroup.solutions",
        "Accept":           "*/*",
    },
    timeout=60,
)

print(f"    Status:       {r.status_code}")
print(f"    Content-Type: {r.headers.get('Content-Type', 'N/A')}")
print(f"    Tamanho:      {len(r.content)} bytes")
print(f"\n--- Primeiros 2000 chars da resposta ---")
print(r.text[:2000])
print("--- Fim ---")

# Tenta parse JSON
try:
    data = r.json()
    print(f"\n>>> É JSON válido! Chaves: {list(data.keys())}")
    # mostra primeiros registros
    for key in ["data", "aaData", "rows", "records"]:
        if key in data:
            print(f"    data['{key}'] tem {len(data[key])} itens")
            if data[key]:
                print(f"    Primeiro item: {json.dumps(data[key][0], ensure_ascii=False)[:300]}")
except Exception as e:
    print(f"\n>>> Não é JSON: {e}")
    print(">>> Salvando resposta em debug_response.html para análise...")
    with open("debug_response.html", "w", encoding="utf-8") as f:
        f.write(r.text)
    print("    Arquivo salvo: debug_response.html")
