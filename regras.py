"""Regras de negocio puras: comissao, metas e formatacao.

Sem streamlit, sem gspread, sem I/O. E de proposito: e a parte que mexe com
dinheiro e com o numero que a lideranca olha, entao precisa rodar em teste sem
credencial e sem subir o app.

Quem precisar de dado da planilha faz a leitura na pagina e passa numero puro
para ca.
"""


# ─────────────────────────────────────────────────────────────────
#  COMISSAO
# ─────────────────────────────────────────────────────────────────

def calcular_comissao(valores, fator, imposto_pct):
    """(base, bruto, desconto, liquido) da comissao de um parceiro.

    valores      -- valores das vendas que entram na apuracao
    fator        -- multiplicador acordado com o parceiro (0.05 = 5%)
    imposto_pct  -- imposto retido, em pontos percentuais (11 = 11%)

    O imposto incide sobre o BRUTO, nao sobre a base de vendas.
    """
    base     = sum(valores)
    fator    = fator or 0.0
    imposto  = imposto_pct or 0.0
    bruto    = base * fator
    desconto = bruto * (imposto / 100)
    liquido  = bruto - desconto
    return base, bruto, desconto, liquido


# ─────────────────────────────────────────────────────────────────
#  METAS
# ─────────────────────────────────────────────────────────────────

def atingimento(realizado, meta) -> int:
    """Percentual atingido da meta, SEM teto — 145% aparece como 145.

    Use este para numero exibido (card, coluna de tabela, ranking). Travar em
    100 faz quem superou a meta ficar igual a quem bateu na trave, o que
    esconde justamente o que a lideranca quer enxergar.

    Para a largura da barra de progresso use `largura_barra`.
    """
    if not meta or meta <= 0:
        return 0
    return int(realizado / meta * 100)


def largura_barra(realizado, meta) -> int:
    """Percentual para largura de barra de progresso: preso entre 0 e 100.

    Aqui o teto existe por limitacao visual — barra nao passa do fim da barra.
    """
    if not meta or meta <= 0:
        return 0
    return max(0, min(int(realizado / meta * 100), 100))


def faltam(realizado, meta):
    """Quanto ainda falta para a meta. Nunca negativo: meta batida = 0."""
    if not meta or meta <= 0:
        return 0
    return max(meta - realizado, 0)


# ─────────────────────────────────────────────────────────────────
#  FORMATACAO
# ─────────────────────────────────────────────────────────────────

MESES_PT = {
    "01": "Jan", "02": "Fev", "03": "Mar", "04": "Abr",
    "05": "Mai", "06": "Jun", "07": "Jul", "08": "Ago",
    "09": "Set", "10": "Out", "11": "Nov", "12": "Dez",
}


def fmt_brl(v) -> str:
    """1234.5 -> 'R$ 1.234,50' (separadores no padrao BR)."""
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_comp(ym: str) -> str:
    """'2025-05' -> 'Mai/2025'. Devolve a entrada intacta se nao reconhecer."""
    if not ym or len(ym) < 7:
        return ym
    ano, mes = ym[:4], ym[5:7]
    return f"{MESES_PT.get(mes, mes)}/{ano}"
