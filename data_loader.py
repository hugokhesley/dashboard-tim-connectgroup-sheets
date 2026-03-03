import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

STATUS_MAP = {
    "CONCLUÍDO": "ENTRANTE", "CONCLUIDO": "ENTRANTE",
    "ENTREGA": "ENTRANTE", "FIDELIZAÇÃO": "ENTRANTE", "FIDELIZACAO": "ENTRANTE",
    "AG. IMPR. DOCs/EXPEDIÇÃO": "ENTRANTE", "AG. IMPR. DOCS/EXPEDICAO": "ENTRANTE",
    "INCONSISTENCIA": "ENTRANTE", "INCONSISTÊNCIA": "ENTRANTE",
    "INSUCESSO VENDAS": "ENTRANTE", "PRÉ-ATIVAÇÃO-P2B": "ENTRANTE",
    "PRE-ATIVACAO-P2B": "ENTRANTE",
    "BATE/VOLTA - LOG": "ENTRANTE", "BATE/VOLTA CONTROL TOWER": "ENTRANTE",
    "FATURAMENTO": "ENTRANTE", "DOCUMENTAÇÃO": "ENTRANTE", "DOCUMENTACAO": "ENTRANTE",
    "REPRESAMENTO": "ENTRANTE", "REPROC. CORREÇÃO NFE": "ENTRANTE",
    "REPROC. CORRECAO NFE": "ENTRANTE", "REPROC. CRIAÇÃO ORDENS": "ENTRANTE",
    "REPROC. CRIACAO ORDENS": "ENTRANTE", "APROVAÇÃO ÁREA DE ATUAÇÃO": "ENTRANTE",
    "APROVACAO AREA DE ATUACAO": "ENTRANTE", "AG. ATIVAÇÃO": "ENTRANTE",
    "AG. ATIVACAO": "ENTRANTE", "ATIVAÇÃO MANUAL": "ENTRANTE",
    "ATIVACAO MANUAL": "ENTRANTE", "PRÉ-ATIVAÇÃO": "ENTRANTE",
    "PRE-ATIVACAO": "ENTRANTE",
    "AG. ANALISE ANTI-FRAUDE": "ANÁLISE", "EM ANÁLISE": "ANÁLISE",
    "EM ANALISE": "ANÁLISE", "CRÉDITO": "ANÁLISE", "CREDITO": "ANÁLISE",
    "ANTI-FRAUDE": "ANÁLISE",
    "CADASTRO": "PENDENTE", "PRÉ-VENDA": "PENDENTE", "PRE-VENDA": "PENDENTE",
    "ACEITE DIGITAL": "PENDENTE",
    "DEVOLVIDOS": "DEVOLVIDOS", "DEVOLVIDO": "DEVOLVIDOS",
}

STATUS_COLORS = {
    "PENDENTE":   {"border": "#f59e0b", "icon": "⏳"},
    "ANÁLISE":    {"border": "#3b82f6", "icon": "🔍"},
    "DEVOLVIDOS": {"border": "#ef4444", "icon": "↩️"},
    "ENTRANTE":   {"border": "#10b981", "icon": "✅"},
}

def _s(val):
    """Converte qualquer valor para string limpa."""
    if val is None:
        return ""
    return str(val).strip()

def _normalize(val):
    """Remove acentos e converte para lowercase para comparação."""
    import unicodedata
    s = _s(val).lower()
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def _sup(val):
    return _s(val).upper()

def _to_num(val):
    try:
        s = _s(val).replace(" ", "")
        if not s:
            return 0.0
        # se vier sem separador decimal (ex: 6499 no lugar de 64,99)
        # o gspread remove vírgulas — detectamos pela ausência de . ou ,
        # Não fazemos divisão automática pois pode ser valor inteiro legítimo
        s = s.replace(",", ".")
        return float(s)
    except Exception:
        return 0.0

def _dedup_columns(df):
    """Remove colunas duplicadas e garante índice limpo."""
    # Renomeia colunas duplicadas adicionando sufixo
    cols = []
    seen = {}
    for c in df.columns:
        if c in seen:
            seen[c] += 1
            cols.append(f"{c}_{seen[c]}")
        else:
            seen[c] = 0
            cols.append(c)
    df.columns = cols
    # Mantém só a primeira ocorrência de cada nome base
    df = df.loc[:, ~df.columns.duplicated()]
    return df.reset_index(drop=True)


def get_gspread_client():
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)


@st.cache_data(ttl=180)
def load_data() -> pd.DataFrame:
    try:
        client = get_gspread_client()
        sheet_url = st.secrets["sheets"]["url"]
        spreadsheet = client.open_by_url(sheet_url)

        dfs = []
        for worksheet in spreadsheet.worksheets():
            try:
                # get_all_values preserva vírgulas decimais que get_all_records remove
                all_values = worksheet.get_all_values()
                if not all_values or len(all_values) < 2:
                    continue
                headers = all_values[0]
                rows = all_values[1:]
                df = pd.DataFrame(rows, columns=headers)
                df = _dedup_columns(df)
                # normaliza nomes de colunas
                df.columns = [_s(c).lower() for c in df.columns]
                df = _dedup_columns(df)
                df["_aba"] = worksheet.title
                dfs.append(df)
            except Exception as e:
                st.warning(f"Aba '{worksheet.title}' ignorada: {e}")
                continue

        if not dfs:
            return pd.DataFrame()

        # Alinha colunas antes do concat para evitar conflitos
        all_cols = list(dict.fromkeys(col for df in dfs for col in df.columns))
        dfs_aligned = [df.reindex(columns=all_cols) for df in dfs]
        combined = pd.concat(dfs_aligned, ignore_index=True)
        combined = _dedup_columns(combined)
        return combined

    except Exception as e:
        st.error(f"❌ Erro ao conectar ao Google Sheets: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=180)
def load_metas() -> dict:
    """Lê a aba 'metas' do Sheets e retorna dicionário com os valores."""
    defaults = {
        "vendas_acessos": 626,
        "vendas_receita": 0,
        "renegociacao_acessos": 751,
        "renegociacao_receita": 0,
    }
    try:
        client = get_gspread_client()
        sheet_url = st.secrets["sheets"]["url"]
        spreadsheet = client.open_by_url(sheet_url)

        try:
            ws = spreadsheet.worksheet("metas")
        except Exception:
            return defaults

        all_values = ws.get_all_values()
        if not all_values or len(all_values) < 2:
            return defaults

        headers = [_s(h).lower() for h in all_values[0]]
        result = defaults.copy()
        for row in all_values[1:]:
            if not row:
                continue
            indicador = _s(row[0]).lower()
            vendas_val    = _to_num(row[1]) if len(row) > 1 else 0
            reneg_val     = _to_num(row[2]) if len(row) > 2 else 0
            if "acesso" in indicador:
                result["vendas_acessos"]        = vendas_val
                result["renegociacao_acessos"]  = reneg_val
            elif "receita" in indicador or "valor" in indicador:
                result["vendas_receita"]        = vendas_val
                result["renegociacao_receita"]  = reneg_val
        return result

    except Exception as e:
        st.warning(f"Não foi possível carregar metas: {e}")
        return defaults


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = _dedup_columns(df)
    rename = {}
    for col in df.columns:
        c = _normalize(col)
        if "parceiro" in c:                        rename[col] = "parceiro"
        elif "tipo" in c and "contrata" in c:      rename[col] = "tipo_contratacao"
        elif "fila" in c:                          rename[col] = "fila_atual"
        elif "ativa" in c and "data" in c:         rename[col] = "data_ativacao"
        elif "input" in c and "data" in c:         rename[col] = "data_input"
        elif "acesso" in c:                        rename[col] = "acessos"
        elif "preco" in c and "oferta" in c:                  rename[col] = "preco_oferta"
        elif "raz" in c and "social" in c:         rename[col] = "razao_social"

    df = df.rename(columns=rename)
    df = _dedup_columns(df)

    for col in ["parceiro", "tipo_contratacao", "fila_atual", "razao_social"]:
        if col in df.columns:
            df[col] = df[col].apply(_s)

    return df


def parse_month(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series.apply(_s), dayfirst=True, errors="coerce")
    return parsed.dt.strftime("%m/%Y")


def apply_filters(df: pd.DataFrame, mes_alvo: str, tipo_list: list, parceiro: str = "Todos") -> pd.DataFrame:
    df = normalize_columns(df)
    df = _dedup_columns(df)


    for col in ["tipo_contratacao", "fila_atual", "acessos", "preco_oferta"]:
        if col not in df.columns:
            df[col] = ""

    # Numérico - get_all_values preserva vírgulas, _to_num converte 64,99 → 64.99
    df["acessos"] = df["acessos"].apply(_to_num)
    df["preco_oferta"] = df["preco_oferta"].apply(_to_num)

    # Tipo de contratação
    tipos_alvo = [t.upper() for t in tipo_list]
    mask_tipo = df["tipo_contratacao"].apply(lambda x: _sup(x) in tipos_alvo)
    df = df[mask_tipo].copy()
    df = _dedup_columns(df)

    # Remove CANCELADO
    df["fila_atual_upper"] = df["fila_atual"].apply(_sup)
    df = df[df["fila_atual_upper"] != "CANCELADO"].copy()
    df = _dedup_columns(df)

    # Filtro parceiro
    if parceiro and parceiro != "Todos":
        df = df[df["parceiro"].apply(lambda x: _sup(x) == parceiro.upper())].copy()
        df = _dedup_columns(df)

    # Datas
    df["mes_ativacao"] = parse_month(df["data_ativacao"]) if "data_ativacao" in df.columns else pd.NA
    df["mes_input"]    = parse_month(df["data_input"])    if "data_input"    in df.columns else pd.NA

    # Regra: ativado no mês OU sem ativação (tramitando, qualquer data de input)
    mask_ativado  = df["mes_ativacao"] == mes_alvo
    mask_pipeline = df["mes_ativacao"].isna()
    df = df[mask_ativado | mask_pipeline].copy()
    df = _dedup_columns(df)

    # Status gerencial
    df["status_dash"] = df["fila_atual_upper"].apply(lambda x: STATUS_MAP.get(x, "ENTRANTE"))

    return df


def get_parceiros(df: pd.DataFrame) -> list:
    df_norm = normalize_columns(df.copy())
    parceiros = ["Todos"]
    if "parceiro" in df_norm.columns:
        vals = [_s(v) for v in df_norm["parceiro"].values if _s(v)]
        parceiros += sorted(set(vals))
    return parceiros
