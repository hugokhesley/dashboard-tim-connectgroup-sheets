"""
=====================================================================
  10_Atribuicao_Vendedor.py
  Página de atribuição de vendedor real para pedidos pendentes.
  Link fixo — líderes abrem quando quiserem.
=====================================================================
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from data_loader import load_colaboradores, get_gspread_client, _s
from auth import require_login

st.set_page_config(
    page_title="Connect Group | Atribuição de Vendedores",
    page_icon="👤",
    layout="centered",
    initial_sidebar_state="collapsed"
)

username = require_login("atribuicao_vendedor")

SPREADSHEET_ID = "1HmtEFf2Akh7NLR2prxDh9S4gmioKYw419B4bkx4yBLg"
ABA_DEPARA     = "DePara"
ABA_RADAR      = "DadosRadar"

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
    border-radius: 12px; padding: 16px 18px; margin-bottom: 12px;
  }
  .pedido-card.done { border-color: #10b981; }
  .pedido-num   { font-size: 0.78rem; color: #64748b; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
  .pedido-nome  { font-size: 1rem; font-weight: 600; color: #f1f5f9; margin: 4px 0 2px; }
  .pedido-info  { font-size: 0.78rem; color: #94a3b8; }
  .badge-pend   { display:inline-block; background:#7f1d1d; color:#fca5a5; font-size:0.7rem; font-weight:600; border-radius:6px; padding:2px 8px; margin-left:8px; }
  .badge-ok     { display:inline-block; background:#064e3b; color:#6ee7b7; font-size:0.7rem; font-weight:600; border-radius:6px; padding:2px 8px; margin-left:8px; }
  section[data-testid="stSidebar"] { display: none; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────
#  FUNÇÕES
# ─────────────────────────────────────────────────────────────────

@st.cache_data(ttl=120, show_spinner=False)
def carregar_pendentes():
    """Carrega pedidos do DadosRadar sem vendedor_real na aba DePara."""
    gc = get_gspread_client()
    planilha = gc.open_by_key(SPREADSHEET_ID)

    # Carrega radar
    aba_radar = planilha.worksheet(ABA_RADAR)
    df_radar  = pd.DataFrame(aba_radar.get_all_records())
    if df_radar.empty:
        return pd.DataFrame()

    # Normaliza colunas
    df_radar.columns = [c.strip().lower().replace(" ", "_") for c in df_radar.columns]

    # Carrega de-para existente
    try:
        aba_dp  = planilha.worksheet(ABA_DEPARA)
        df_dp   = pd.DataFrame(aba_dp.get_all_records())
        if not df_dp.empty:
            df_dp.columns = [c.strip().lower().replace(" ", "_") for c in df_dp.columns]
            pedidos_com_vendedor = set(
                df_dp[df_dp["vendedor_real"].apply(lambda x: _s(x) != "")]["pedido"].apply(_s)
            )
        else:
            pedidos_com_vendedor = set()
    except Exception:
        pedidos_com_vendedor = set()

    # Filtra pendentes
    if "pedido" not in df_radar.columns:
        return pd.DataFrame()

    df_radar["_pedido_norm"] = df_radar["pedido"].apply(_s)
    df_pend = df_radar[~df_radar["_pedido_norm"].isin(pedidos_com_vendedor)].copy()
    df_pend = df_pend[df_pend["_pedido_norm"] != ""].drop_duplicates("_pedido_norm")

    colunas = ["pedido", "razao_social", "acessos", "status_dash", "mes_input"]
    colunas = [c for c in colunas if c in df_pend.columns]
    return df_pend[colunas].reset_index(drop=True)


@st.cache_data(ttl=300, show_spinner=False)
def carregar_vendedores():
    """Retorna lista de vendedores ativos da aba Colaboradores."""
    colab = load_colaboradores()
    if colab is None or colab.empty:
        return []
    col = next((c for c in colab.columns if "vendedor" in c.lower()), None)
    if not col:
        return []
    vendedores = sorted([v for v in colab[col].dropna().unique() if _s(v)])
    return vendedores


def salvar_atribuicoes(atribuicoes: dict):
    """Grava atribuições na aba DePara do Sheets."""
    if not atribuicoes:
        return 0
    gc = get_gspread_client()
    planilha = gc.open_by_key(SPREADSHEET_ID)
    try:
        aba = planilha.worksheet(ABA_DEPARA)
        dados_existentes = aba.get_all_records()
        df_existente = pd.DataFrame(dados_existentes) if dados_existentes else pd.DataFrame()
    except Exception:
        aba = planilha.add_worksheet(title=ABA_DEPARA, rows=1, cols=4)
        df_existente = pd.DataFrame()

    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    novas_linhas = []
    for pedido, vendedor in atribuicoes.items():
        novas_linhas.append([str(pedido), str(vendedor), username, agora])

    if df_existente.empty:
        aba.update([["pedido", "vendedor_real", "atribuido_por", "data_hora"]] + novas_linhas,
                   value_input_option="USER_ENTERED")
    else:
        aba.append_rows(novas_linhas, value_input_option="USER_ENTERED")

    return len(novas_linhas)


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
        df_pend    = carregar_pendentes()
        vendedores = carregar_vendedores()

    if df_pend.empty:
        st.success("✅ Nenhum pedido pendente de atribuição!")
        st.stop()

    total = len(df_pend)
    st.markdown(f"**{total} pedido(s) sem vendedor atribuído.** Preencha os que são do seu time e salve.")
    st.markdown("---")

    vendedores_opts = ["— não é meu —"] + vendedores
    atribuicoes = {}

    for _, row in df_pend.iterrows():
        pedido     = _s(row.get("pedido", ""))
        cliente    = _s(row.get("razao_social", "—"))
        acessos    = row.get("acessos", "—")
        status     = _s(row.get("status_dash", "—"))
        mes_input  = _s(row.get("mes_input", "—"))

        col1, col2 = st.columns([3, 2])
        with col1:
            st.markdown(f"""
            <div class="pedido-card">
              <div class="pedido-num">Pedido {pedido} · {mes_input}</div>
              <div class="pedido-nome">{cliente}</div>
              <div class="pedido-info">{acessos} acessos · {status}</div>
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
                atribuicoes[pedido] = sel

    st.markdown("---")

    n_attr = len(atribuicoes)
    if n_attr > 0:
        st.info(f"**{n_attr}** pedido(s) atribuído(s). Clique em salvar quando terminar.")
        if st.button("💾 Salvar atribuições", type="primary", use_container_width=True):
            with st.spinner("Salvando..."):
                salvos = salvar_atribuicoes(atribuicoes)
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
