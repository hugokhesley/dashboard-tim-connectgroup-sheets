"""Testes do data_loader: conversao vetorizada e montagem da base.

Cobre as duas mudancas de risco:
  1. _to_num_series / parse_month / apply_filters passaram de .apply() linha a
     linha para operacao vetorizada — precisam dar EXATAMENTE o mesmo resultado.
  2. load_data() passou a ler as abas em lote (values_batch_get), que corta
     celulas vazias no fim da linha — o padding tem que reconstruir a largura.
"""
import sys, types, os

# ── stubs de dependencias que so existem no Streamlit Cloud ──────────
_st = types.ModuleType("streamlit")


def _cache_data(*args, **kwargs):
    """@st.cache_data e @st.cache_data(ttl=...) viram no-op nos testes."""
    if args and callable(args[0]):
        return args[0]
    return lambda fn: fn


_st.cache_data = _cache_data
_st.secrets = {}
_st.warning = lambda *a, **k: None
_st.error = lambda *a, **k: None
sys.modules.setdefault("streamlit", _st)

for mod in ("gspread", "google", "google.oauth2", "google.oauth2.service_account"):
    sys.modules.setdefault(mod, types.ModuleType(mod))
sys.modules["google.oauth2.service_account"].Credentials = object

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import data_loader as D


# ── 1. conversao numerica ────────────────────────────────────────────

VALORES = [
    "R$ 219,95", "r$219,95", "1.234,56", "139,97", "7.70", "0",
    "", "   ", "abc", "1.000", "12", "-45,5", "R$ 1.234.567,89",
    "219.95", "1 234,56", None,
]


def test_to_num_series_bate_com_to_num():
    esperado = [D._to_num(v) for v in VALORES]
    obtido = D._to_num_series(pd.Series(VALORES)).tolist()
    assert obtido == esperado, f"\nesperado: {esperado}\nobtido:   {obtido}"


def test_to_num_series_vazia():
    assert D._to_num_series(pd.Series([], dtype=object)).tolist() == []


# ── 2. parse de mes ──────────────────────────────────────────────────

DATAS = [
    "22/02/2026", "22/02/2026 08:30", "01/12/2025 23:59:59",
    "", "   ", "nao e data", "5/3/2026", None,
]


def test_parse_month_bate_com_versao_escalar():
    esperado = pd.to_datetime(
        pd.Series([D._limpar_data(v) for v in DATAS]), dayfirst=True, errors="coerce"
    ).dt.strftime("%m/%Y").tolist()
    obtido = D.parse_month(pd.Series(DATAS)).tolist()
    # NaN != NaN, entao compara pela representacao
    assert [str(x) for x in obtido] == [str(x) for x in esperado]


def test_parse_month_vazia():
    assert D.parse_month(pd.Series([], dtype=object)).tolist() == []


# ── 3. apply_filters ─────────────────────────────────────────────────

def _base_exemplo():
    return pd.DataFrame({
        "parceiro":            ["Alfa", "Beta", "Alfa", "Alfa", "Gama"],
        "tipo de contratação": ["NOVO", "novo", "RENEGOCIAÇÃO", "NOVO", "NOVO"],
        "fila atual":          ["AG. ATIVACAO", "CADASTRO", "CADASTRO", "CANCELADO", "EM ANALISE"],
        "data de ativação":    ["10/03/2026", "", "10/03/2026", "10/03/2026", "10/01/2026"],
        "data de input":       ["01/03/2026", "02/03/2026", "01/03/2026", "01/03/2026", "05/01/2026"],
        "acessos":             ["10", "5", "3", "8", "2"],
        "preço oferta":        ["R$ 1.234,56", "99,90", "50", "10", "20"],
    })


def test_apply_filters_seleciona_e_converte():
    df = D.apply_filters(_base_exemplo(), "03/2026", ["NOVO"], parceiro="Todos")
    # Alfa/AG.ATIVACAO (ativado no mes) e Beta/CADASTRO (pipeline, sem ativacao).
    # Fora: RENEGOCIAÇÃO (tipo), CANCELADO (fila), Gama (ativado em 01/2026).
    assert len(df) == 2
    assert sorted(df["parceiro"].tolist()) == ["Alfa", "Beta"]
    assert df["acessos"].tolist() == [10.0, 5.0]
    assert df["preco_oferta"].tolist() == [1234.56, 99.90]
    assert sorted(df["status_dash"].tolist()) == ["ENTRANTE", "PRE-VENDA"]


def test_apply_filters_respeita_parceiro():
    df = D.apply_filters(_base_exemplo(), "03/2026", ["NOVO"], parceiro="Alfa")
    assert df["parceiro"].tolist() == ["Alfa"]


def test_apply_filters_base_vazia():
    vazio = pd.DataFrame(columns=["parceiro", "tipo de contratação", "fila atual"])
    df = D.apply_filters(vazio, "03/2026", ["NOVO"])
    assert df.empty


# ── 4. montagem da base a partir da leitura em lote ──────────────────

class _AbaFalsa:
    def __init__(self, title):
        self.title = title


class _PlanilhaFalsa:
    """Simula values_batch_get: corta as celulas vazias no fim de cada linha."""

    def __init__(self, abas: dict):
        self._abas = abas
        self.chamadas_batch = 0

    def worksheets(self):
        return [_AbaFalsa(t) for t in self._abas]

    def values_batch_get(self, ranges):
        self.chamadas_batch += 1
        faixas = []
        for r in ranges:
            titulo = r.strip("'").replace("''", "'")
            linhas = [list(linha) for linha in self._abas[titulo]]
            for linha in linhas:                       # corta vazios do fim
                while linha and linha[-1] == "":
                    linha.pop()
            faixas.append({"values": linhas})
        return {"valueRanges": faixas}


def _rodar_load_data(monkey_planilha):
    """Chama load_data com a planilha falsa no lugar do gspread."""
    D.st.secrets = {"sheets": {"url": "http://fake"}}
    original_client = D.get_gspread_client
    D.get_gspread_client = lambda: types.SimpleNamespace(
        open_by_url=lambda _url: monkey_planilha
    )
    try:
        return D.load_data()
    finally:
        D.get_gspread_client = original_client
        D.st.secrets = {}


def test_load_data_pula_abas_operacionais():
    planilha = _PlanilhaFalsa({
        "MAR/2026":   [["parceiro", "acessos"], ["Alfa", "10"]],
        "ABR/2026":   [["parceiro", "acessos"], ["Beta", "20"]],
        "Logs":       [["timestamp", "pagina"], ["x", "y"]],
        "DadosRadar": [["pedido"], ["123"]],
        "metas":      [["mes"], ["03/2026"]],
        "Colaboradores": [["vendedor"], ["Fulano"]],
    })
    df = _rodar_load_data(planilha)
    assert sorted(df["_aba"].unique().tolist()) == ["ABR/2026", "MAR/2026"]
    assert len(df) == 2
    assert planilha.chamadas_batch == 1, "deve ler tudo numa unica chamada"


def test_load_data_repoe_celulas_cortadas_no_fim():
    # A ultima linha vem curta do batch_get porque as celulas finais sao vazias.
    planilha = _PlanilhaFalsa({
        "MAR/2026": [
            ["parceiro", "acessos", "preço oferta"],
            ["Alfa", "10", "99,90"],
            ["Beta", "", ""],          # vira ["Beta"] no batch
        ],
    })
    df = _rodar_load_data(planilha)
    assert len(df) == 2
    assert df.loc[1, "parceiro"] == "Beta"
    assert df.loc[1, "acessos"] == ""
    assert df.loc[1, "preço oferta"] == ""


def test_load_data_alinha_colunas_diferentes_entre_abas():
    planilha = _PlanilhaFalsa({
        "MAR/2026": [["parceiro", "acessos"], ["Alfa", "10"]],
        "ABR/2026": [["parceiro", "cnpj"], ["Beta", "123"]],
    })
    df = _rodar_load_data(planilha)
    assert set(["parceiro", "acessos", "cnpj", "_aba"]).issubset(df.columns)
    assert len(df) == 2


def test_load_data_ignora_aba_so_com_cabecalho():
    planilha = _PlanilhaFalsa({
        "MAR/2026": [["parceiro", "acessos"], ["Alfa", "10"]],
        "ABR/2026": [["parceiro", "acessos"]],       # sem dados
    })
    df = _rodar_load_data(planilha)
    assert df["_aba"].unique().tolist() == ["MAR/2026"]


def test_load_data_cai_no_sequencial_se_batch_falhar():
    class _PlanilhaSemBatch(_PlanilhaFalsa):
        def values_batch_get(self, ranges):
            raise RuntimeError("cota estourada")

        def worksheets(self):
            abas = []
            for titulo, linhas in self._abas.items():
                aba = _AbaFalsa(titulo)
                aba.get_all_values = (lambda l=linhas: [list(x) for x in l])
                abas.append(aba)
            return abas

    D.time.sleep = lambda _s: None      # nao esperar de verdade no teste
    planilha = _PlanilhaSemBatch({
        "MAR/2026": [["parceiro", "acessos"], ["Alfa", "10"]],
        "Logs":     [["timestamp"], ["x"]],
    })
    df = _rodar_load_data(planilha)
    assert df["_aba"].unique().tolist() == ["MAR/2026"]


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
