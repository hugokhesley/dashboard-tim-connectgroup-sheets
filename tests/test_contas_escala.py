"""Escala de contas do Radar: conta que so roda em certos dias da semana.

A falha aqui e silenciosa e cara: se uma conta que roda so na segunda for
tratada como "falhou" nos outros dias, ou se a gravacao nao entrar em modo
preservar, a rodada de terca da aba.clear() e apaga o que a segunda trouxe.
"""
import sys, types, os
from datetime import datetime, timezone

# ── stubs das dependencias pesadas (mesmo padrao dos outros testes) ──
for mod in ("requests", "pandas", "gspread", "securid", "securid.sdtid",
            "google", "google.oauth2", "google.oauth2.service_account",
            "selenium", "selenium.webdriver", "selenium.webdriver.common",
            "selenium.webdriver.common.by", "selenium.webdriver.support",
            "selenium.webdriver.support.ui", "selenium.webdriver.chrome",
            "selenium.webdriver.chrome.options", "selenium.webdriver.chrome.service"):
    sys.modules.setdefault(mod, types.ModuleType(mod))
sys.modules["selenium.webdriver.support"].expected_conditions = types.ModuleType("ec")
sys.modules["selenium.webdriver.support.expected_conditions"] = types.ModuleType("ec")
sys.modules["selenium.webdriver.common.by"].By = type("By", (), {"XPATH": "xpath", "ID": "id", "NAME": "name"})
sys.modules["selenium.webdriver.support.ui"].WebDriverWait = object
sys.modules["securid.sdtid"].SdtidFile = type("SdtidFile", (), {"verify_mac": lambda *a, **k: None})
sys.modules["google.oauth2.service_account"].Credentials = object
os.environ.setdefault("SPREADSHEET_ID", "fake")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import actions_runner as R


def _utc(ano, mes, dia, hora=12):
    return datetime(ano, mes, dia, hora, tzinfo=timezone.utc)


# Calendario de referencia: 17/08/2026 e uma SEGUNDA-feira.
SEGUNDA = _utc(2026, 8, 17)
TERCA   = _utc(2026, 8, 18)
DOMINGO = _utc(2026, 8, 16)


def _restaurar(original):
    R.CONTAS = original


CONTAS_TESTE = [
    {"login": "diaria_a", "sdtid": "a.sdtid", "dias": None},
    {"login": "diaria_b", "sdtid": "b.sdtid"},              # sem a chave = todo dia
    {"login": "piuai",    "sdtid": "p.sdtid", "dias": [0]},  # so segunda
]


def test_segunda_inclui_conta_semanal():
    original = R.CONTAS
    R.CONTAS = CONTAS_TESTE
    try:
        logins = [c["login"] for c in R.contas_do_dia(SEGUNDA)]
        assert logins == ["diaria_a", "diaria_b", "piuai"]
    finally:
        _restaurar(original)


def test_terca_exclui_conta_semanal():
    original = R.CONTAS
    R.CONTAS = CONTAS_TESTE
    try:
        logins = [c["login"] for c in R.contas_do_dia(TERCA)]
        assert logins == ["diaria_a", "diaria_b"]
        assert "piuai" not in logins
    finally:
        _restaurar(original)


def test_domingo_exclui_conta_semanal():
    original = R.CONTAS
    R.CONTAS = CONTAS_TESTE
    try:
        logins = [c["login"] for c in R.contas_do_dia(DOMINGO)]
        assert "piuai" not in logins
    finally:
        _restaurar(original)


def test_conta_sem_chave_dias_roda_sempre():
    original = R.CONTAS
    R.CONTAS = CONTAS_TESTE
    try:
        for quando in (SEGUNDA, TERCA, DOMINGO):
            logins = [c["login"] for c in R.contas_do_dia(quando)]
            assert "diaria_b" in logins, f"faltou em {quando}"
    finally:
        _restaurar(original)


def test_usa_dia_de_brasilia_nao_do_runner():
    """Domingo 22h BRT ja e segunda em UTC — vale o dia de Brasilia.

    Sem a conversao, a conta 'so segunda' rodaria no domingo a noite e ficaria
    de fora na segunda de manha, que e justamente quando ela importa.
    """
    original = R.CONTAS
    R.CONTAS = CONTAS_TESTE
    try:
        # 2026-08-17T01:00Z = domingo 16/08 as 22h em Brasilia
        domingo_a_noite = _utc(2026, 8, 17, 1)
        assert "piuai" not in [c["login"] for c in R.contas_do_dia(domingo_a_noite)]

        # 2026-08-17T12:00Z = segunda 17/08 as 09h em Brasilia
        segunda_de_manha = _utc(2026, 8, 17, 12)
        assert "piuai" in [c["login"] for c in R.contas_do_dia(segunda_de_manha)]

        # 2026-08-18T02:00Z = segunda 17/08 as 23h em Brasilia — ainda segunda
        segunda_tarde_da_noite = _utc(2026, 8, 18, 2)
        assert "piuai" in [c["login"] for c in R.contas_do_dia(segunda_tarde_da_noite)]
    finally:
        _restaurar(original)


def test_contas_reais_do_projeto_rodam_todo_dia():
    """As 3 contas atuais nao tem restricao — nenhuma regressao acidental."""
    for quando in (SEGUNDA, TERCA, DOMINGO):
        assert len(R.contas_do_dia(quando)) == len(R.CONTAS)


if __name__ == "__main__":
    falhas = 0
    for nome, fn in sorted(globals().items()):
        if nome.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok   {nome}")
            except AssertionError as e:
                falhas += 1
                print(f"  FALHOU {nome}: {e}")
            except Exception as e:
                falhas += 1
                print(f"  ERRO {nome}: {type(e).__name__}: {e}")
    print("\nTODOS OS TESTES PASSARAM" if not falhas else f"\n{falhas} teste(s) com problema")
    sys.exit(1 if falhas else 0)
