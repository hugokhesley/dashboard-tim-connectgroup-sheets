import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import unicodedata

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets.readonly',
    'https://www.googleapis.com/auth/drive.readonly',
]

STATUS_MAP = {
    'CANCELADO': 'CANCELADO',
    'CONCLUIDO': 'ENTRANTE', 'ENTREGA': 'ENTRANTE',
    'FIDELIZACAO': 'ENTRANTE', 'AG. IMPR. DOCS/EXPEDICAO': 'ENTRANTE',
    'INCONSISTENCIA': 'ENTRANTE', 'INSUCESSO VENDAS': 'ENTRANTE',
    'PRE-ATIVACAO-P2B': 'ENTRANTE', 'BATE/VOLTA - LOG': 'ENTRANTE',
    'BATE/VOLTA CONTROL TOWER': 'ENTRANTE', 'FATURAMENTO': 'ENTRANTE',
    'DOCUMENTACAO': 'ENTRANTE', 'REPRESAMENTO': 'ENTRANTE',
    'REPROC. CORRECAO NFE': 'ENTRANTE', 'REPROC. CRIACAO ORDENS': 'ENTRANTE',
    'APROVACAO AREA DE ATUACAO': 'ENTRANTE', 'AG. ATIVACAO': 'ENTRANTE',
    'ATIVACAO MANUAL': 'ENTRANTE', 'PRE-ATIVACAO': 'ENTRANTE',
    'AG. ANALISE ANTI-FRAUDE': 'EM ANALISE', 'EM ANALISE': 'EM ANALISE',
    'AG. NRO RADAR NO P2B': 'EM ANALISE', 'AG. STATUS P2B': 'EM ANALISE',
    'APROVACAO P2B': 'EM ANALISE', 'REABRIR P2B': 'EM ANALISE',
    'ANALISE DE CADASTRO - CREDITO': 'CREDITO',
    'AG. ANALISE DE CREDITO PELA HOLDING': 'CREDITO',
    'REANALISE APROVADA': 'CREDITO', 'REANALISE DE CREDITO': 'CREDITO',
    'REANALISE ACOMP. NAC': 'CREDITO',
    'CADASTRO': 'PRE-VENDA', 'AG. ACEITE DIGITAL': 'PRE-VENDA',
    'ACEITE DIGITAL': 'PRE-VENDA',
    'DEVOLVIDOS': 'DEVOLVIDOS', 'DEVOLVIDO': 'DEVOLVIDOS',
    'FALTA APARELHO - TERMINAIS': 'DEVOLVIDOS', 'FALTA APARELHO BOC': 'DEVOLVIDOS',
    'REANALISE REPROVADA': 'DEVOLVIDOS', 'AG. CONF. CANCELAMENTO': 'DEVOLVIDOS',
    'APROVACAO CODIGO 02': 'DEVOLVIDOS', 'AG. STATUS P2B BOC': 'DEVOLVIDOS',
    'CANCELAMENTO BOC': 'DEVOLVIDOS', 'INSUCESSO BOC': 'DEVOLVIDOS',
    'INCONSISTENCIA LOG': 'DEVOLVIDOS', 'REPROC. VIS. FINANCEIRA': 'DEVOLVIDOS',
    'TROCA CHIP INCONSISTENTE': 'DEVOLVIDOS', 'COMPROMISSO': 'META',
}

STATUS_COLORS = {
    'PRE-VENDA':  {'border': '#f59e0b', 'icon': '⏳'},
    'EM ANALISE': {'border': '#3b82f6', 'icon': '🔍'},
    'CREDITO':    {'border': '#8b5cf6', 'icon': '💳'},
    'DEVOLVIDOS': {'border': '#ef4444', 'icon': '↩️'},
    'ENTRANTE':   {'border': '#10b981', 'icon': '✅'},
    'META':       {'border': '#f97316', 'icon': '🎯'},
}


def _s(val):
    if val is None:
        return ''
    return str(val).strip()

def _normalize(val):
    s = _s(val).lower()
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')

def _sup(val):
    return _s(val).upper()

def _to_num(val):
    try:
        s = _s(val).replace(' ', '')
        if not s:
            return 0.0
        s = s.replace(',', '.')
        return float(s)
    except Exception:
        return 0.0

def _lookup_status(val):
    if val in STATUS_MAP:
        return STATUS_MAP[val]
    sem = ''.join(c for c in unicodedata.normalize('NFD', val) if unicodedata.category(c) != 'Mn')
    if sem in STATUS_MAP:
        return STATUS_MAP[sem]
    return 'ENTRANTE'

def _dedup_columns(df):
    cols = []
    seen = {}
    for c in df.columns:
        if c in seen:
            seen[c] += 1
            cols.append(f'{c}_{seen[c]}')
        else:
            seen[c] = 0
            cols.append(c)
    df.columns = cols
    df = df.loc[:, ~df.columns.duplicated()]
    return df.reset_index(drop=True)


def get_gspread_client():
    creds_dict = dict(st.secrets['gcp_service_account'])
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)


@st.cache_data(ttl=180)
def load_data() -> pd.DataFrame:
    try:
        client = get_gspread_client()
        sheet_url = st.secrets['sheets']['url']
        spreadsheet = client.open_by_url(sheet_url)
        IGNORE_TABS = {'metas'}
        dfs = []
        for worksheet in spreadsheet.worksheets():
            if worksheet.title.strip().lower() in IGNORE_TABS:
                continue
            try:
                all_values = worksheet.get_all_values()
                if not all_values or len(all_values) < 2:
                    continue
                headers = all_values[0]
                rows = all_values[1:]
                df = pd.DataFrame(rows, columns=headers)
                df = _dedup_columns(df)
                df.columns = [_s(c).lower() for c in df.columns]
                df = _dedup_columns(df)
                df['_aba'] = worksheet.title
                dfs.append(df)
            except Exception as e:
                st.warning(f'Aba ignorada: {e}')
                continue
        if not dfs:
            return pd.DataFrame()
        all_cols = list(dict.fromkeys(col for df in dfs for col in df.columns))
        dfs_aligned = [df.reindex(columns=all_cols) for df in dfs]
        combined = pd.concat(dfs_aligned, ignore_index=True)
        combined = _dedup_columns(combined)
        return combined
    except Exception as e:
        st.error(f'Erro ao conectar: {e}')
        return pd.DataFrame()


@st.cache_data(ttl=180)
def load_metas() -> dict:
    """Retorna metas do mes atual (linha sem coluna mes ou primeira linha)."""
    defaults = {
        'vendas_acessos': 626, 'vendas_receita': 0,
        'renegociacao_acessos': 751, 'renegociacao_receita': 0,
    }
    try:
        todas = load_metas_historico()
        if not todas:
            return defaults
        # pega a ultima entrada como meta corrente
        ultima = list(todas.values())[-1]
        return ultima
    except Exception:
        return defaults


@st.cache_data(ttl=180)
def load_metas_historico() -> dict:
    """Retorna dict {mes: {vendas_acessos, vendas_receita}} para todos os meses da aba metas.
    Estrutura da planilha:
      mes | vendas_acessos | vendas_receita | renegociacao_acessos | renegociacao_receita
    """
    try:
        client = get_gspread_client()
        sheet_url = st.secrets['sheets']['url']
        spreadsheet = client.open_by_url(sheet_url)
        try:
            ws = spreadsheet.worksheet('metas')
        except Exception:
            return {}
        all_values = ws.get_all_values()
        if not all_values or len(all_values) < 2:
            return {}
        headers = [_s(h).lower() for h in all_values[0]]
        resultado = {}
        for row in all_values[1:]:
            if not row or not _s(row[0]):
                continue
            mes = _s(row[0])  # ex: 03/2026
            def _v(i): return _to_num(row[i]) if len(row) > i else 0
            # tenta ler por posicao: mes | vendas_acessos | vendas_receita | reneg_acessos | reneg_receita
            resultado[mes] = {
                'vendas_acessos':       _v(1),
                'vendas_receita':       _v(2),
                'renegociacao_acessos': _v(3),
                'renegociacao_receita': _v(4),
            }
        return resultado
    except Exception as e:
        st.warning(f'Erro ao carregar metas historico: {e}')
        return {}


def get_meta_mes(mes: str) -> dict:
    """Retorna metas para um mes especifico. Fallback zeros se nao encontrar."""
    historico = load_metas_historico()
    if mes in historico:
        return historico[mes]
    return {'vendas_acessos': 0, 'vendas_receita': 0, 'renegociacao_acessos': 0, 'renegociacao_receita': 0}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = _dedup_columns(df)
    rename = {}
    for col in df.columns:
        n = _normalize(col)
        if n == 'data de input':         rename[col] = 'data_input'
        elif n == 'data de ativacao':    rename[col] = 'data_ativacao'
        elif n == 'razao social':        rename[col] = 'razao_social'
        elif n == 'tipo de contratacao': rename[col] = 'tipo_contratacao'
        elif n == 'fila atual':          rename[col] = 'fila_atual'
        elif n == 'acessos':             rename[col] = 'acessos'
        elif n == 'preco oferta':        rename[col] = 'preco_oferta'
        elif n == 'parceiro':            rename[col] = 'parceiro'
        elif n == 'pedido':              rename[col] = 'pedido'
    df = df.rename(columns=rename)
    df = _dedup_columns(df)
    for col in ['parceiro', 'tipo_contratacao', 'fila_atual', 'razao_social', 'pedido']:
        if col in df.columns:
            df[col] = df[col].apply(_s)
    return df


def parse_month(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series.apply(_s), dayfirst=True, errors='coerce')
    return parsed.dt.strftime('%m/%Y')


def apply_filters(df: pd.DataFrame, mes_alvo: str, tipo_list: list, parceiro: str = 'Todos') -> pd.DataFrame:
    df = normalize_columns(df)
    df = _dedup_columns(df)
    for col in ['tipo_contratacao', 'fila_atual', 'acessos', 'preco_oferta']:
        if col not in df.columns:
            df[col] = ''
    df['acessos']      = df['acessos'].apply(_to_num)
    df['preco_oferta'] = df['preco_oferta'].apply(_to_num)
    tipos_alvo = [t.upper() for t in tipo_list]
    df = df[df['tipo_contratacao'].apply(lambda x: _sup(x) in tipos_alvo)].copy()
    df = _dedup_columns(df)
    df['fila_atual_upper'] = df['fila_atual'].apply(_sup)
    df = df[df['fila_atual_upper'] != 'CANCELADO'].copy()
    df = _dedup_columns(df)
    if parceiro and parceiro != 'Todos':
        df = df[df['parceiro'].apply(lambda x: _sup(x) == parceiro.upper())].copy()
        df = _dedup_columns(df)
    df['mes_ativacao'] = parse_month(df['data_ativacao']) if 'data_ativacao' in df.columns else pd.NA
    df['mes_input']    = parse_month(df['data_input'])    if 'data_input'    in df.columns else pd.NA
    mask_ativado  = df['mes_ativacao'] == mes_alvo
    mask_pipeline = df['mes_ativacao'].isna()
    df = df[mask_ativado | mask_pipeline].copy()
    df = _dedup_columns(df)
    df['status_dash'] = df['fila_atual_upper'].apply(_lookup_status)
    return df


def get_parceiros(df: pd.DataFrame) -> list:
    df_norm = normalize_columns(df.copy())
    parceiros = ['Todos']
    if 'parceiro' in df_norm.columns:
        vals = [_s(v) for v in df_norm['parceiro'].values if _s(v)]
        parceiros += sorted(set(vals))
    return parceiros


@st.cache_data(ttl=180)
def load_bko() -> pd.DataFrame:
    """Carrega aba BKO-VENDEDOR-REAL e retorna df com pedido, vendedor_real, lider."""
    try:
        client = get_gspread_client()
        sheet_url = st.secrets['sheets']['url']
        spreadsheet = client.open_by_url(sheet_url)
        ws = spreadsheet.worksheet('BKO-VENDEDOR-REAL')
        all_values = ws.get_all_values()
        if not all_values or len(all_values) < 2:
            return pd.DataFrame(columns=['pedido', 'vendedor_real', 'lider'])
        headers = all_values[0]
        rows = all_values[1:]
        df = pd.DataFrame(rows, columns=headers)
        df = _dedup_columns(df)
        # Normaliza nomes de colunas
        rename = {}
        for col in df.columns:
            n = _normalize(col)
            if n == 'pedido':                          rename[col] = 'pedido'
            elif 'vendedor' in n and 'real' in n:      rename[col] = 'vendedor_real'
            elif n == 'lider' or n == 'líder':         rename[col] = 'lider'
        df = df.rename(columns=rename)
        # Garante colunas mínimas
        for c in ['pedido', 'vendedor_real', 'lider']:
            if c not in df.columns:
                df[c] = ''
        df['pedido']        = df['pedido'].apply(_s)
        df['vendedor_real'] = df['vendedor_real'].apply(_s)
        df['lider']         = df['lider'].apply(lambda x: _s(x) if _s(x) else 'Sem Equipe')
        # Remove linhas sem pedido
        df = df[df['pedido'] != ''].reset_index(drop=True)
        return df[['pedido', 'vendedor_real', 'lider']]
    except Exception as e:
        st.warning(f'BKO não carregado: {e}')
        return pd.DataFrame(columns=['pedido', 'vendedor_real', 'lider'])
