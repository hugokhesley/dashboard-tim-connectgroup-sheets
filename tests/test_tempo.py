"""Testes do relogio da operacao.

O bug que originou o modulo: em 31/08/2026 as 22h47 de Brasilia o servidor
(UTC) ja marcava 01/09, e a Tramitacao Atual — que filtra pelo mes vigente —
foi olhar setembro e perdeu as ativacoes de agosto.

Roda sem credencial e sem streamlit.
"""
import sys, os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tempo import agora, em_brasilia, hoje, mes_atual


def _utc(ano, mes, dia, hora, minuto=0):
    return datetime(ano, mes, dia, hora, minuto, tzinfo=timezone.utc)


def test_noite_do_ultimo_dia_do_mes_nao_vira_o_mes():
    # 31/08/2026 22h47 em Brasilia = 01/09/2026 01h47 em UTC.
    local = em_brasilia(_utc(2026, 9, 1, 1, 47))
    assert local.day   == 31
    assert local.month == 8
    assert local.strftime("%m/%Y") == "08/2026"


def test_diferenca_de_tres_horas():
    assert em_brasilia(_utc(2026, 8, 31, 15, 0)) == datetime(2026, 8, 31, 12, 0)


def test_virada_do_ano_tambem_espera():
    # 31/12 as 23h em Brasilia ainda e dezembro, mesmo com o UTC em janeiro.
    local = em_brasilia(_utc(2027, 1, 1, 2, 0))
    assert (local.day, local.month, local.year) == (31, 12, 2026)


def test_helpers_sao_naive_e_coerentes():
    a = agora()
    assert a.tzinfo is None          # substituto direto de datetime.now()
    assert hoje() == a.date()
    assert mes_atual() == a.strftime("%m/%Y")
