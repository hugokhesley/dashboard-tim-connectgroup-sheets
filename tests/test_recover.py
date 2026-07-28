"""Prova que o recover NÃO trunca mais a base quando uma conta falha.

Cenário do incidente de 25/jul: T3729525 emperra no login, as outras 2 baixam.
Antes: aba.clear() + update com 2 contas → base 2006 → 565 linhas.
Agora: subir_para_sheets(preservar_existentes=True) + heartbeat + exit 1.
"""
import sys, types, os

for mod in ("requests", "gspread", "securid", "securid.sdtid",
            "google", "google.oauth2", "google.oauth2.service_account",
            "selenium", "selenium.webdriver", "selenium.webdriver.common",
            "selenium.webdriver.common.by", "selenium.webdriver.support",
            "selenium.webdriver.support.ui", "selenium.webdriver.chrome",
            "selenium.webdriver.chrome.options", "selenium.webdriver.chrome.service"):
    sys.modules.setdefault(mod, types.ModuleType(mod))
sys.modules["selenium.webdriver.support.expected_conditions"] = types.ModuleType("ec")
sys.modules["selenium.webdriver.common.by"].By = type("By", (), {"XPATH": "xpath", "ID": "id", "NAME": "name"})
sys.modules["selenium.webdriver.support.ui"].WebDriverWait = object
sys.modules["securid.sdtid"].SdtidFile = type("SdtidFile", (), {"verify_mac": lambda *a, **k: None})
sys.modules["google.oauth2.service_account"].Credentials = object
os.environ.setdefault("SPREADSHEET_ID", "fake")
# roda de qualquer lugar: o script sob teste está na raiz do repo
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import actions_recover as REC

chamadas = {}


def falso_subir(df, preservar_existentes=False):
    chamadas["subir"] = {"linhas": len(df), "preservar": preservar_existentes}


def falso_status(status, linhas, ok, falhas, detalhe=""):
    chamadas["status"] = {"status": status, "linhas": linhas, "ok": list(ok),
                          "falhas": list(falhas), "detalhe": detalhe}


def conta_fake(conta):
    login = conta["login"]
    if login == "t3729525":                       # a conta flaky do incidente
        raise RuntimeError("Login falhou para T3729525: sessão não chegou no radar-blue")
    return login, pd.DataFrame({"pedido": [1, 2, 3], "x": ["a", "b", "c"]})


REC.subir_para_sheets = falso_subir
REC.registrar_status = falso_status
REC.processar_conta = conta_fake

try:
    REC.main()
    codigo = 0
except SystemExit as e:
    codigo = e.code

print("chamadas:", chamadas)
assert chamadas["subir"]["preservar"] is True, "PERIGO: gravaria sem preservar → base truncada"
assert chamadas["subir"]["linhas"] == 6, chamadas["subir"]
assert chamadas["status"]["status"] == "parcial", chamadas["status"]
assert chamadas["status"]["falhas"] == ["t3729525"], chamadas["status"]
assert codigo == 1, f"rodada parcial deveria sair com exit 1 (saiu {codigo})"
print("\nparcial: preserva + heartbeat 'parcial' + exit 1 → OK")

# ── e o caso 3/3 contas: grava limpo, status ok, exit 0 ──────────────
chamadas.clear()
REC.processar_conta = lambda c: (c["login"], pd.DataFrame({"pedido": [1], "x": ["a"]}))
try:
    REC.main()
    codigo = 0
except SystemExit as e:
    codigo = e.code
assert chamadas["subir"]["preservar"] is False, chamadas
assert chamadas["status"]["status"] == "ok", chamadas
assert codigo == 0, codigo
print("completo: grava limpo + status 'ok' + exit 0 → OK")

# ── e o caso 0/3: não grava NADA (base velha > base vazia) ───────────
chamadas.clear()


def todas_falham(c):
    raise RuntimeError("boom")


REC.processar_conta = todas_falham
try:
    REC.main()
    codigo = 0
except SystemExit as e:
    codigo = e.code
assert "subir" not in chamadas, "NÃO pode gravar quando nenhuma conta baixou"
assert chamadas["status"]["status"] == "falha", chamadas
assert codigo == 1
print("nenhuma conta: não grava nada + status 'falha' + exit 1 → OK")

print("\nTODOS OS CENÁRIOS PASSARAM")
