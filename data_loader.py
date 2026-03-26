import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import unicodedata

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
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
        s = _s(val).strip()
        if not s:
            return 0.0
        # Remove prefixo R$, espacos e non-breaking spaces
        s = s.replace("R$", "").replace("r$", "").strip()
        s = s.replace(" ", "").replace(" ", "")
        # Trata separador de milhar BR: 1.234,56 -> 1234.56
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", ".")
        return float(s)
    except Exception:
        return 0.0

def _soma_valor(val):
    """
    Converte valor R$ com multiplos valores separados por ' / '
    ex: '139,97 / 7,70'  -> 147.67
    ex: 'R$ 219,95'      -> 219.95
    ex: '1.234,56'       -> 1234.56
    """
    s = _s(val).strip()
    if not s:
        return 0.0
    if " / " in s:
        return sum(_to_num(p.strip()) for p in s.split(" / "))
    return _to_num(s)


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
        elif n == 'cnpj':                rename[col] = 'cnpj'
    df = df.rename(columns=rename)
    df = _dedup_columns(df)
    for col in ['parceiro', 'tipo_contratacao', 'fila_atual', 'razao_social']:
        if col in df.columns:
            df[col] = df[col].apply(_s)
    if 'pedido' in df.columns:
        df['pedido'] = df['pedido'].apply(_norm_pedido)
    return df


def _limpar_data(v):
    """Remove hora de datas que vêm com timestamp: '22/02/2026 08:30' → '22/02/2026'."""
    s = _s(v).strip()
    if not s:
        return s
    return s.split(" ")[0] if " " in s else s


def parse_month(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series.apply(_limpar_data), dayfirst=True, errors='coerce')
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


def _norm_pedido(val):
    """Normaliza pedido: remove .0 de floats, strip de espaços."""
    s = _s(val).strip()
    if s.endswith('.0'):
        s = s[:-2]
    return s


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
        if not all_values or len(all_values) < 3:
            return pd.DataFrame(columns=['pedido', 'vendedor_real', 'lider'])
        # Linha 1 é vazia/aviso — header real está na linha 2 (índice 1)
        headers = all_values[1]
        rows = all_values[2:]
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
        df['pedido']        = df['pedido'].apply(_norm_pedido)
        df['vendedor_real'] = df['vendedor_real'].apply(_s)
        df['lider']         = df['lider'].apply(lambda x: _s(x) if _s(x) else 'Sem Equipe')
        # Remove linhas sem pedido
        df = df[df['pedido'] != ''].reset_index(drop=True)
        return df[['pedido', 'vendedor_real', 'lider']]
    except Exception as e:
        st.warning(f'BKO não carregado: {e}')
        return pd.DataFrame(columns=['pedido', 'vendedor_real', 'lider'])


def inserir_pendentes_bko(df_pendentes: pd.DataFrame, safra: str) -> tuple:
    """
    Insere na aba BKO-VENDEDOR-REAL os pedidos que estão no DadosRadar
    mas ainda não foram cadastrados. Evita duplicatas comparando pedidos.
    
    df_pendentes: DataFrame com colunas pedido, razao_social
    safra: ex '03/2026'
    Retorna (sucesso: bool, mensagem: str)
    """
    try:
        client = get_gspread_client()
        sheet_url = st.secrets['sheets']['url']
        spreadsheet = client.open_by_url(sheet_url)
        ws = spreadsheet.worksheet('BKO-VENDEDOR-REAL')

        # Lê o que já existe no BKO para evitar duplicatas
        all_values = ws.get_all_values()
        pedidos_existentes = set()
        if all_values and len(all_values) >= 3:
            headers = all_values[1]
            rows    = all_values[2:]
            # Descobre índice da coluna pedido
            idx_pedido = None
            for i, h in enumerate(headers):
                if _normalize(h) == 'pedido':
                    idx_pedido = i
                    break
            if idx_pedido is not None:
                for row in rows:
                    if idx_pedido < len(row):
                        v = _norm_pedido(row[idx_pedido])
                        if v:
                            pedidos_existentes.add(v)

        # Filtra apenas os que realmente faltam e remove duplicatas pelo pedido
        df_inserir = df_pendentes[
            ~df_pendentes['pedido'].apply(_norm_pedido).isin(pedidos_existentes)
        ].copy()

        # Remove duplicatas — mantém apenas a primeira ocorrência de cada pedido
        df_inserir['_pedido_norm'] = df_inserir['pedido'].apply(_norm_pedido)
        df_inserir = df_inserir.drop_duplicates(subset='_pedido_norm').drop(columns='_pedido_norm')

        if df_inserir.empty:
            return True, "Nenhum pedido novo para inserir — todos já estavam no BKO."

        # Monta as linhas para inserir
        # Estrutura BKO colunas não protegidas: SAFRA | PEDIDO | RAZÃO SOCIAL | VENDEDOR REAL
        # Colunas E em diante (LÍDER, TBP) são protegidas — não incluir
        novas_linhas = []
        for _, row in df_inserir.iterrows():
            novas_linhas.append([
                safra,
                _norm_pedido(row.get('pedido', '')),
                _s(row.get('razao_social', '')),
                '',   # VENDEDOR REAL — preencher manualmente
            ])

        # Encontra a primeira linha onde B (pedido) E C (razão social) estão vazios
        # Ignora colunas A, D, E, F — só olha B e C
        primeira_vazia = len(rows) + 3  # fallback: após todos os dados existentes
        for i, row in enumerate(rows):
            col_b = _s(row[1]) if len(row) > 1 else ""
            col_c = _s(row[2]) if len(row) > 2 else ""
            if not col_b and not col_c:
                primeira_vazia = i + 3  # +3: linha 1 vazia + linha 2 header + 1-indexed
                break

        # Insere a partir da primeira linha vazia em B e C
        range_notation = f"A{primeira_vazia}:F{primeira_vazia + len(novas_linhas) - 1}"
        ws.update(range_notation, novas_linhas, value_input_option='USER_ENTERED')

        return True, f"{len(novas_linhas)} pedido(s) inserido(s) no BKO com sucesso."

    except Exception as e:
        return False, f"Erro ao inserir no BKO: {e}"


@st.cache_data(ttl=180)
def load_colaboradores() -> pd.DataFrame:
    """
    Carrega aba Colaboradores e retorna vendedores ATIVOS (com META preenchida).
    Colunas retornadas: vendedor, lider, meta
    """
    try:
        client = get_gspread_client()
        sheet_url = st.secrets['sheets']['url']
        spreadsheet = client.open_by_url(sheet_url)
        ws = spreadsheet.worksheet('Colaboradores')
        all_values = ws.get_all_values()
        if not all_values or len(all_values) < 3:
            return pd.DataFrame(columns=['vendedor', 'lider', 'meta'])

        # Header na linha 2 (índice 1)
        headers = all_values[1]
        rows    = all_values[2:]
        df = pd.DataFrame(rows, columns=headers)
        df = _dedup_columns(df)

        # Normaliza nomes de colunas
        rename = {}
        for col in df.columns:
            n = _normalize(col)
            if 'vendedor' in n and 'real' not in n: rename[col] = 'vendedor'
            elif n in ('lider', 'líder'):            rename[col] = 'lider'
            elif n == 'meta':                        rename[col] = 'meta'
            elif n == 'cargo':                       rename[col] = 'cargo'
        df = df.rename(columns=rename)

        for c in ['vendedor', 'lider', 'meta', 'cargo']:
            if c not in df.columns:
                df[c] = ''

        df['vendedor'] = df['vendedor'].apply(_s)
        df['lider']    = df['lider'].apply(_s)
        df['meta']     = df['meta'].apply(_to_num)

        # Apenas vendedores ativos (META > 0) e cargo VENDEDOR
        df = df[
            (df['meta'] > 0) &
            (df['vendedor'] != '') &
            (df['cargo'].apply(lambda x: _normalize(x) == 'vendedor'))
        ].reset_index(drop=True)

        return df[['vendedor', 'lider', 'meta']]

    except Exception as e:
        st.warning(f'Colaboradores não carregado: {e}')
        return pd.DataFrame(columns=['vendedor', 'lider', 'meta'])


def registrar_acesso(pagina: str, username: str = "") -> None:
    """
    Registra acesso na aba 'Logs' da planilha principal.
    Colunas: timestamp | pagina | username
    Cria a aba automaticamente se não existir.
    Falhas silenciosas — nunca interrompe o fluxo da página.
    """
    import datetime
    try:
        client = get_gspread_client()
        sheet_url = st.secrets['sheets']['url']
        spreadsheet = client.open_by_url(sheet_url)

        # Tenta abrir aba Logs; cria se não existir
        try:
            ws = spreadsheet.worksheet('Logs')
        except Exception:
            ws = spreadsheet.add_worksheet(title='Logs', rows=5000, cols=4)
            ws.update('A1:C1', [['timestamp', 'pagina', 'username']])

        # Timestamp no fuso de Brasília (UTC-3)
        agora = datetime.datetime.utcnow() - datetime.timedelta(hours=3)
        ts = agora.strftime('%d/%m/%Y %H:%M:%S')

        user = username if username else "desconhecido"

        # Append na próxima linha disponível
        ws.append_row([ts, pagina, user], value_input_option='USER_ENTERED')

    except Exception:
        pass  # Falha silenciosa — log não deve quebrar a página
