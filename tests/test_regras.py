"""Testes da matematica de comissao e metas.

E a parte que mexe com dinheiro e com o numero que a lideranca usa para decidir.
Erro aqui nao quebra a tela: entrega um valor errado com cara de certo.

Roda sem credencial e sem streamlit — regras.py nao importa nada disso.
"""
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from regras import (
    calcular_comissao, atingimento, largura_barra, faltam, fmt_brl, fmt_comp,
)


# ── COMISSAO ─────────────────────────────────────────────────────

def test_comissao_caso_tipico():
    # 3 vendas somando 10.000, fator 5%, imposto 11% sobre o bruto
    base, bruto, desconto, liquido = calcular_comissao([5000, 3000, 2000], 0.05, 11)
    assert base == 10000
    assert bruto == 500.0
    assert round(desconto, 2) == 55.0
    assert round(liquido, 2) == 445.0


def test_imposto_incide_sobre_o_bruto_nao_sobre_a_base():
    """Erro classico: descontar o imposto da base de vendas."""
    _, bruto, desconto, liquido = calcular_comissao([10000], 0.10, 20)
    assert bruto == 1000.0
    assert desconto == 200.0        # 20% de 1000, nao de 10000
    assert liquido == 800.0


def test_comissao_sem_imposto():
    _, bruto, desconto, liquido = calcular_comissao([1000], 0.08, 0)
    assert desconto == 0
    assert liquido == bruto == 80.0


def test_comissao_sem_vendas():
    assert calcular_comissao([], 0.05, 11) == (0, 0.0, 0.0, 0.0)


def test_comissao_fator_ou_imposto_nulos_nao_quebram():
    """session_state comeca com None nesses campos."""
    assert calcular_comissao([1000], None, None) == (1000, 0.0, 0.0, 0.0)
    base, bruto, desconto, liquido = calcular_comissao([1000], 0.05, None)
    assert (bruto, desconto, liquido) == (50.0, 0.0, 50.0)


def test_comissao_liquido_nunca_maior_que_bruto():
    for imposto in (0, 1, 11, 50, 100):
        _, bruto, _, liquido = calcular_comissao([7500], 0.06, imposto)
        assert liquido <= bruto


def test_comissao_imposto_de_100_zera_o_liquido():
    _, bruto, desconto, liquido = calcular_comissao([1000], 0.05, 100)
    assert desconto == bruto
    assert liquido == 0.0


def test_comissao_com_centavos():
    base, bruto, _, liquido = calcular_comissao([139.97, 7.70], 0.05, 11)
    assert round(base, 2) == 147.67
    assert round(bruto, 4) == 7.3835
    assert round(liquido, 2) == 6.57


# ── METAS ────────────────────────────────────────────────────────

def test_atingimento_mostra_acima_de_100():
    """O ponto principal: quem superou a meta nao pode aparecer como 100%."""
    assert atingimento(145, 100) == 145
    assert atingimento(1200, 626) == 191


def test_atingimento_distingue_quem_superou_de_quem_bateu_na_trave():
    assert atingimento(100, 100) != atingimento(145, 100)


def test_atingimento_trunca_e_nao_arredonda():
    assert atingimento(99.9, 100) == 99      # 99.9% ainda nao bateu a meta
    assert atingimento(199.9, 100) == 199


def test_atingimento_meta_zero_ou_ausente():
    assert atingimento(500, 0) == 0
    assert atingimento(500, None) == 0
    assert atingimento(0, 0) == 0


def test_largura_barra_trava_em_100():
    assert largura_barra(145, 100) == 100
    assert largura_barra(50, 100) == 50
    assert largura_barra(100, 100) == 100


def test_largura_barra_nunca_negativa():
    assert largura_barra(-30, 100) == 0


def test_largura_barra_meta_zero():
    assert largura_barra(500, 0) == 0


def test_barra_e_percentual_divergem_so_acima_da_meta():
    for realizado in (0, 25, 60, 99, 100):
        assert atingimento(realizado, 100) == largura_barra(realizado, 100)
    assert atingimento(130, 100) == 130
    assert largura_barra(130, 100) == 100


def test_faltam():
    assert faltam(400, 626) == 226
    assert faltam(626, 626) == 0
    assert faltam(700, 626) == 0        # meta batida nao vira falta negativa
    assert faltam(100, 0) == 0


# ── FORMATACAO ───────────────────────────────────────────────────

def test_fmt_brl_padrao_brasileiro():
    assert fmt_brl(1234.5) == "R$ 1.234,50"
    assert fmt_brl(0) == "R$ 0,00"
    assert fmt_brl(1234567.89) == "R$ 1.234.567,89"
    assert fmt_brl(0.5) == "R$ 0,50"


def test_fmt_brl_negativo():
    assert fmt_brl(-1234.5) == "R$ -1.234,50"


def test_fmt_comp():
    assert fmt_comp("2025-05") == "Mai/2025"
    assert fmt_comp("2026-12") == "Dez/2026"


def test_fmt_comp_entrada_invalida_volta_intacta():
    assert fmt_comp("") == ""
    assert fmt_comp("2025") == "2025"
    assert fmt_comp(None) is None


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
