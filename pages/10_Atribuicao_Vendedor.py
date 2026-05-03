"""
=====================================================================
  10_Atribuicao_Vendedor.py
  Página de atribuição de vendedor real para pedidos pendentes.
  Lê a aba BKO-VENDEDOR-REAL, filtra os sem vendedor_real,
  e permite ao líder atribuir direto aqui.
=====================================================================
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from data_loader import load_colaboradores, get_gspread_client, _s, _norm_pedido
from auth import require_login

st.set_page_config(
    page_title="Connect Group | Atribuição de Vendedores",
    page_icon="👤",
    layout="centered",
    initial_sidebar_state="collapsed"
)

username = require_login("atribuicao_vendedor")

SPREADSHEET_ID = "1HmtEFf2Akh7NLR2prxDh9S4gmioKYw419B4bkx4yBLg"
ABA_BKO        = "BKO-VENDEDOR-REAL"

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
  html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
  .stApp { background-color: #0f1117; color: #e2e8f0; }
  .header {
    background: linear-gradient(135deg, #064e3b, #059669);
    border-radius: 14px; padding: 22px 28px; margin-bottom: 24px;
    border: 1px solid rgba(255,255,255,0.08);
  }
  .header-title { font-size: 1.4rem; font-weight: 700; color: #fff; margin: 0; }
  .header-sub   { font-size: 0.82rem; color: rgba(255,255,255,0.65); margin: 4px 0 0; }
  .pedido-card {
    background: #1a1f2e; border: 1px solid #2d3748;
    border-radius: 12px; padding: 16px 18px; margin-bottom: 4px;
  }
  .pedido-num  { font-size: 0.78rem; color: #64748b; font-weight: 600; letter-spacing: 0.5px; }
  .pedido-nome { font-size: 1rem; font-weight: 600; color: #f1f5f9; margin: 4px 0 2px; }
  .pedido-info { font-size: 0.78rem; color: #94a3b8; }
  section[data-testid="stSidebar"] { display: none; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────
#  FUNÇÕES
# ─────────────────────────────────────────────────────────────────

@st.cache_data(ttl=120, show_spinner=False)
def carregar_pendentes():
    """
    Lê BKO-VENDEDOR-REAL e retorna pedidos sem vendedor_real
    nos últimos 30 dias, excluindo CANCELADO e RENEGOCIAÇÃO.
    """
    gc       = get_gspread_client()
    planilha = gc.open_by_key(SPREADSHEET_ID)
    ws       = planilha.worksheet(ABA_BKO)

    all_values = ws.get_all_values()
    if not all_values or len(all_values) < 3:
        return pd.DataFrame(), ws

    # Linha 2 = cabeçalho (índice 1)
    headers = all_values[1]
    rows    = all_values[2:]

    df = pd.DataFrame(rows, columns=headers)
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # Guarda índice real da linha no sheets (+3: linha 1 vazia + header + 1-indexed)
    df["_row_idx"] = [i + 3 for i in range(len(df))]

    # Descobre colunas relevantes
    col_pedido   = next((c for c in df.columns if "pedido" in c), None)
    col_razao    = next((c for c in df.columns if "raz" in c and "social" in c), None)
    col_vendedor = next((c for c in df.columns if "vendedor" in c and "real" in c), None)
    col_safra    = next((c for c in df.columns if "safra" in c), None)
    col_tipo     = next((c for c in df.columns if "tipo" in c and "contrat" in c), None)
    col_fila     = next((c for c in df.columns if "fila" in c), None)

    if not col_pedido or not col_vendedor:
        return pd.DataFrame(), ws

    # Filtra só os sem vendedor_real
    df_pend = df[df[col_vendedor].apply(lambda x: _s(x) == "")].copy()
    df_pend = df_pend[df_pend[col_pedido].apply(lambda x: _norm_pedido(x) != "")].copy()

    # Exclui RENEGOCIAÇÃO pelo tipo_contratacao
    if col_tipo:
        df_pend = df_pend[~df_pend[col_tipo].apply(
            lambda x: "RENEGOCI" in _s(x).upper()
        )]

    # Exclui CANCELADO pelo fila_atual
    if col_fila:
        df_pend = df_pend[~df_pend[col_fila].apply(
            lambda x: "CANCELAD" in _s(x).upper()
        )]

    # Filtra últimos 30 dias pela safra (MM/YYYY)
    if col_safra:
        limite = datetime.today() - timedelta(days=30)
        def _parse_safra(v):
            try:
                return datetime.strptime(_s(v).strip(), "%m/%Y")
            except Exception:
                return None
        df_pend["_dt_safra"] = df_pend[col_safra].apply(_parse_safra)
        df_pend = df_pend[df_pend["_dt_safra"].apply(
            lambda d: d is not None and d >= limite.replace(day=1)
        )]

    # Renomeia para nomes padronizados
    rename = {}
    if col_pedido:   rename[col_pedido]   = "pedido"
    if col_razao:    rename[col_razao]    = "razao_social"
    if col_safra:    rename[col_safra]    = "safra"
    if col_vendedor: rename[col_vendedor] = "vendedor_real"
    if col_tipo:     rename[col_tipo]     = "tipo_contratacao"

    df_pend = df_pend.rename(columns=rename)
    df_pend["pedido"] = df_pend["pedido"].apply(_norm_pedido)
    df_pend = df_pend.drop_duplicates("pedido").reset_index(drop=True)

    # Índice da coluna vendedor_real no sheets (1-indexed)
    try:
        col_vendedor_idx = headers.index(
            next(h for h in headers if "vendedor" in h.lower() and "real" in h.lower())
        ) + 1
    except Exception:
        col_vendedor_idx = 4

    df_pend["_col_vendedor_idx"] = col_vendedor_idx

    colunas = [c for c in ["pedido", "razao_social", "safra", "_row_idx", "_col_vendedor_idx"] if c in df_pend.columns]
    return df_pend[colunas], ws


@st.cache_data(ttl=300, show_spinner=False)
def carregar_vendedores():
    """Retorna lista de vendedores ativos da aba Colaboradores."""
    colab = load_colaboradores()
    if colab is None or colab.empty:
        return []
    col = next((c for c in colab.columns if "vendedor" in c.lower() and "real" not in c.lower()), None)
    if not col:
        return []
    return sorted([v for v in colab[col].dropna().unique() if _s(v)])


def salvar_atribuicoes(ws, atribuicoes: list):
    """Atualiza célula a célula na aba BKO-VENDEDOR-REAL."""
    salvos = 0
    for item in atribuicoes:
        try:
            ws.update_cell(item["row_idx"], item["col_idx"], item["vendedor"])
            salvos += 1
        except Exception as e:
            st.warning(f"Erro ao salvar pedido {item.get('pedido','')}: {e}")
    return salvos


# ─────────────────────────────────────────────────────────────────
#  INTERFACE
# ─────────────────────────────────────────────────────────────────

def main():
    hoje = datetime.now().strftime("%d/%m/%Y %H:%M")
    st.markdown(f"""
    <div class="header">
      <p class="header-title">👤 Atribuição de Vendedores</p>
      <p class="header-sub">Connect Group · TIM Corporate · {hoje}</p>
    </div>
    """, unsafe_allow_html=True)

    with st.spinner("Carregando pedidos pendentes..."):
        df_pend, ws = carregar_pendentes()
        vendedores  = carregar_vendedores()

    if df_pend.empty:
        st.success("✅ Nenhum pedido pendente de atribuição nos últimos 30 dias!")
        st.stop()

    total = len(df_pend)
    st.markdown(f"**{total} pedido(s) sem vendedor** nos últimos 30 dias. Preencha os do seu time e salve.")
    st.markdown("---")

    vendedores_opts = ["— não é meu —"] + vendedores
    atribuicoes = []

    for _, row in df_pend.iterrows():
        pedido  = _s(row.get("pedido", ""))
        cliente = _s(row.get("razao_social", "—"))
        safra   = _s(row.get("safra", "—"))
        row_idx = int(row.get("_row_idx", 0))
        col_idx = int(row.get("_col_vendedor_idx", 4))

        col1, col2 = st.columns([3, 2])
        with col1:
            st.markdown(f"""
            <div class="pedido-card">
              <div class="pedido-num">Pedido {pedido} · {safra}</div>
              <div class="pedido-nome">{cliente}</div>
            </div>
            """, unsafe_allow_html=True)
        with col2:
            sel = st.selectbox(
                " ",
                vendedores_opts,
                key=f"sel_{pedido}",
                label_visibility="collapsed"
            )
            if sel and sel != "— não é meu —":
                atribuicoes.append({
                    "pedido":   pedido,
                    "row_idx":  row_idx,
                    "col_idx":  col_idx,
                    "vendedor": sel,
                })

    st.markdown("---")

    n_attr = len(atribuicoes)
    if n_attr > 0:
        st.info(f"**{n_attr}** pedido(s) atribuído(s). Clique em salvar quando terminar.")
        if st.button("💾 Salvar atribuições", type="primary", use_container_width=True):
            with st.spinner("Salvando no BKO..."):
                salvos = salvar_atribuicoes(ws, atribuicoes)
                st.cache_data.clear()
            st.success(f"✅ {salvos} atribuição(ões) salva(s) com sucesso!")
            st.rerun()
    else:
        st.button("💾 Salvar atribuições", disabled=True, use_container_width=True)
        st.caption("Selecione ao menos um vendedor para habilitar o salvamento.")

    if st.button("🔄 Atualizar lista", use_container_width=True):
        st.cache_data.clear()
        st.rerun()


main()
