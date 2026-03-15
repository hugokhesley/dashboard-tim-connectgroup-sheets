import streamlit as st
import pandas as pd
from data_loader import (
    load_data, load_bko, apply_filters, get_parceiros,
    STATUS_COLORS, _s, _to_num, _normalize
)
from auth import require_password

st.set_page_config(
    page_title="Connect Group | Performance",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="expanded"
)

require_password("performance", "Performance — Connect Group")

MES_ALVO = "03/2026"

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
  html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
  .stApp { background-color: #0f1117; color: #e2e8f0; }
  .header-perf {
    background: linear-gradient(135deg, #0d2b1a 0%, #14532d 40%, #15803d 70%, #22c55e 100%);
    border-radius: 16px; padding: 28px 36px; margin-bottom: 28px;
    box-shadow: 0 8px 32px rgba(34,197,94,0.25);
    border: 1px solid rgba(255,255,255,0.08);
    display: flex; align-items: center; justify-content: space-between;
  }
  .header-title { font-size: 1.9rem; font-weight: 800; color: #fff; letter-spacing: -0.5px; margin: 0; }
  .header-sub   { font-size: 0.85rem; color: rgba(255,255,255,0.65); margin: 4px 0 0 0; }
  .header-badge {
    background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.25);
    border-radius: 20px; padding: 6px 16px; font-size: 0.8rem; color: #fff; font-weight: 600;
  }
  .equipe-header {
    background: linear-gradient(90deg, #1a2e1a, #1e3a2e);
    border-left: 4px solid #22c55e;
    border-radius: 10px; padding: 14px 20px; margin: 28px 0 16px 0;
    display: flex; align-items: center; justify-content: space-between;
  }
  .equipe-nome { font-size: 1.1rem; font-weight: 800; color: #86efac; }
  .equipe-total { font-size: 0.85rem; color: #64748b; }
  .kpi-mini {
    background: #1a1f2e; border-radius: 12px; padding: 16px 18px;
    border: 1px solid #2d3748; position: relative; overflow: hidden; margin-bottom: 4px;
  }
  .kpi-mini::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; }
  .kpi-mini.blue::before   { background: linear-gradient(90deg, #3b82f6, #1d4ed8); }
  .kpi-mini.green::before  { background: linear-gradient(90deg, #22c55e, #15803d); }
  .kpi-mini.red::before    { background: linear-gradient(90deg, #ef4444, #dc2626); }
  .kpi-mini.amber::before  { background: linear-gradient(90deg, #f59e0b, #d97706); }
  .kpi-label { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 1px; color: #94a3b8; font-weight: 600; margin-bottom: 6px; }
  .kpi-value { font-size: 1.7rem; font-weight: 800; color: #f1f5f9; line-height: 1; }
  .kpi-sub   { font-size: 0.72rem; color: #64748b; margin-top: 4px; }
  .kanban-header { border-radius: 10px 10px 0 0; padding: 10px 14px; display:flex; align-items:center; justify-content:space-between; }
  .kanban-title  { font-weight: 700; font-size: 0.82rem; color: #fff; }
  .kanban-count  { font-size: 0.72rem; font-weight: 600; color: rgba(255,255,255,0.8); }
  .section-title { font-size:0.75rem; text-transform:uppercase; letter-spacing:1.5px; color:#22c55e; font-weight:700; margin:24px 0 12px 0; border-left: 3px solid #22c55e; padding-left: 10px; }
  section[data-testid="stSidebar"] { background: #0d1a0f !important; }
  details { background:#1a1f2e !important; border:1px solid #2d3748 !important; border-radius:0 0 10px 10px !important; }
  details summary { color:#e2e8f0 !important; font-weight:600 !important; }
  .divider { border: none; border-top: 1px solid #1e293b; margin: 24px 0; }
</style>
""", unsafe_allow_html=True)


def kanban_col(df_col, status, col_obj, label=None):
    display = label if label else status
    cfg     = STATUS_COLORS.get(status, STATUS_COLORS["ENTRANTE"])
    vol     = int(df_col["acessos"].sum()) if not df_col.empty else 0
    receita = df_col["preco_oferta"].sum() if not df_col.empty else 0
    with col_obj:
        st.markdown(f"""
        <div class="kanban-header" style="background:{cfg['border']}22;border-top:3px solid {cfg['border']};">
          <span class="kanban-title">{cfg['icon']} {display}</span>
          <span class="kanban-count">{vol} ac.</span>
        </div>""", unsafe_allow_html=True)
        with st.expander(f"Σ {vol} · R$ {receita:,.2f}", expanded=False):
            if df_col.empty:
                st.info("Nenhum registro.")
            else:
                grouped = (df_col.groupby("vendedor_real", as_index=False)
                           .agg(GROSS=("acessos","sum"), **{"R$":("preco_oferta","sum")})
                           .sort_values("GROSS", ascending=False))
                st.dataframe(grouped, use_container_width=True, hide_index=True,
                    column_config={
                        "vendedor_real": "Vendedor",
                        "GROSS": st.column_config.NumberColumn("GROSS", format="%d"),
                        "R$":    st.column_config.NumberColumn("R$",    format="R$ %.2f"),
                    })


def render_equipe(df_eq: pd.DataFrame, lider: str):
    total_ac  = int(df_eq["acessos"].sum())
    total_rec = df_eq["preco_oferta"].sum()
    ativados  = df_eq[df_eq["mes_ativacao"] == MES_ALVO]
    ac_ativ   = int(ativados["acessos"].sum())
    rec_ativ  = ativados["preco_oferta"].sum()
    pipeline  = int(df_eq[df_eq["mes_ativacao"].isna()]["acessos"].sum())
    vendedores = df_eq["vendedor_real"].nunique() if "vendedor_real" in df_eq.columns else 0

    st.markdown(f"""
    <div class="equipe-header">
      <div>
        <span class="equipe-nome">👤 {lider}</span>
      </div>
      <span class="equipe-total">{vendedores} vendedor(es) · {total_ac} acessos · R$ {total_rec:,.2f}</span>
    </div>""", unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""<div class="kpi-mini blue">
          <div class="kpi-label">🎯 Ativados no Mês</div>
          <div class="kpi-value">{ac_ativ:,}</div>
          <div class="kpi-sub">acessos ativados</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class="kpi-mini green">
          <div class="kpi-label">💰 Receita Ativada</div>
          <div class="kpi-value">R$ {rec_ativ:,.2f}</div>
          <div class="kpi-sub">no mês</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""<div class="kpi-mini amber">
          <div class="kpi-label">⏳ Pipeline</div>
          <div class="kpi-value">{pipeline:,}</div>
          <div class="kpi-sub">acessos em tramitação</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""<div class="kpi-mini red">
          <div class="kpi-label">👥 Vendedores</div>
          <div class="kpi-value">{vendedores}</div>
          <div class="kpi-sub">na equipe</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("")

    # Kanban da equipe
    k1, k2, k3, k4, k5 = st.columns(5)
    kanban_col(df_eq[df_eq["status_dash"] == "PRE-VENDA"],  "PRE-VENDA",  k1)
    kanban_col(df_eq[df_eq["status_dash"] == "EM ANALISE"], "EM ANALISE", k2)
    kanban_col(df_eq[df_eq["status_dash"] == "CREDITO"],    "CREDITO",    k3)
    kanban_col(df_eq[df_eq["status_dash"] == "DEVOLVIDOS"], "DEVOLVIDOS", k4)
    kanban_col(
        df_eq[(df_eq["status_dash"] == "ENTRANTE") & df_eq["mes_ativacao"].isna()],
        "ENTRANTE", k5, label="ENTRANTE NÃO ATIVO"
    )

    # Ranking de vendedores da equipe
    with st.expander("📋 Ver ranking de vendedores", expanded=False):
        if "vendedor_real" in df_eq.columns:
            rank = (df_eq.groupby("vendedor_real", as_index=False)
                    .agg(
                        Ativados=("acessos", lambda x: int(x[df_eq.loc[x.index, "mes_ativacao"] == MES_ALVO].sum())),
                        Pipeline=("acessos", lambda x: int(x[df_eq.loc[x.index, "mes_ativacao"].isna()].sum())),
                        Total=("acessos", lambda x: int(x.sum())),
                        Receita=("preco_oferta", "sum"),
                    )
                    .sort_values("Ativados", ascending=False))
            st.dataframe(rank, use_container_width=True, hide_index=True,
                column_config={
                    "vendedor_real": "Vendedor",
                    "Ativados":  st.column_config.NumberColumn("✅ Ativados", format="%d"),
                    "Pipeline":  st.column_config.NumberColumn("⏳ Pipeline", format="%d"),
                    "Total":     st.column_config.NumberColumn("Total", format="%d"),
                    "Receita":   st.column_config.NumberColumn("R$", format="R$ %.2f"),
                })

    st.markdown('<hr class="divider">', unsafe_allow_html=True)


def main():
    st.markdown("""
    <div class="header-perf">
      <div>
        <p class="header-title">🏆 PERFORMANCE — CONNECT GROUP</p>
        <p class="header-sub">TIM Corporate · Visão por Equipe · Março/2026</p>
      </div>
      <div class="header-badge">🟢 PERFORMANCE</div>
    </div>""", unsafe_allow_html=True)

    with st.spinner("Carregando dados..."):
        raw = load_data()
        bko = load_bko()

    if raw.empty:
        st.warning("⚠️ Nenhum dado encontrado.")
        st.stop()

    # Sidebar
    with st.sidebar:
        st.markdown("### 🔧 Filtros")
        parceiro_sel = st.selectbox("Parceiro / Aba", get_parceiros(raw))
        lider_options = ["Todos"] + sorted(bko["lider"].unique().tolist()) if not bko.empty else ["Todos"]
        lider_sel = st.selectbox("Equipe / Líder", lider_options)
        st.markdown("---")
        if st.button("🔄 Atualizar dados"):
            st.cache_data.clear()
            st.rerun()
        st.markdown("---")
        st.markdown(f"**Mês:** `{MES_ALVO}`")
        st.caption("Dados via Google Sheets · cache 3 min")

    # Aplica filtros base
    df = apply_filters(raw.copy(), MES_ALVO, ["NOVO", "ADITIVO"], parceiro_sel)

    # Join com BKO pelo pedido
    if not bko.empty and "pedido" in df.columns:
        df["pedido"] = df["pedido"].apply(_s)
        df = df.merge(bko[["pedido", "vendedor_real", "lider"]], on="pedido", how="left")
        df["vendedor_real"] = df["vendedor_real"].apply(lambda x: _s(x) if _s(x) else "Sem Vendedor")
        df["lider"]         = df["lider"].apply(lambda x: _s(x) if _s(x) else "Sem Equipe")
    else:
        df["vendedor_real"] = "Sem Vendedor"
        df["lider"]         = "Sem Equipe"

    # Filtro por líder
    if lider_sel != "Todos":
        df = df[df["lider"] == lider_sel]

    if df.empty:
        st.info("Nenhum dado para os filtros selecionados.")
        st.stop()

    # KPIs globais
    st.markdown('<p class="section-title">📈 Visão Consolidada</p>', unsafe_allow_html=True)
    ativados_g  = df[df["mes_ativacao"] == MES_ALVO]
    ac_g        = int(ativados_g["acessos"].sum())
    rec_g       = ativados_g["preco_oferta"].sum()
    pipeline_g  = int(df[df["mes_ativacao"].isna()]["acessos"].sum())
    equipes_g   = df["lider"].nunique()

    g1, g2, g3, g4 = st.columns(4)
    with g1:
        st.markdown(f"""<div class="kpi-mini blue">
          <div class="kpi-label">🎯 Total Ativado</div>
          <div class="kpi-value">{ac_g:,}</div>
          <div class="kpi-sub">acessos no mês</div>
        </div>""", unsafe_allow_html=True)
    with g2:
        st.markdown(f"""<div class="kpi-mini green">
          <div class="kpi-label">💰 Receita Total</div>
          <div class="kpi-value">R$ {rec_g:,.2f}</div>
          <div class="kpi-sub">ativada no mês</div>
        </div>""", unsafe_allow_html=True)
    with g3:
        st.markdown(f"""<div class="kpi-mini amber">
          <div class="kpi-label">⏳ Pipeline Total</div>
          <div class="kpi-value">{pipeline_g:,}</div>
          <div class="kpi-sub">em tramitação</div>
        </div>""", unsafe_allow_html=True)
    with g4:
        st.markdown(f"""<div class="kpi-mini red">
          <div class="kpi-label">👥 Equipes</div>
          <div class="kpi-value">{equipes_g}</div>
          <div class="kpi-sub">em exibição</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("")

    # Renderiza por equipe
    st.markdown('<p class="section-title">👤 Desempenho por Equipe</p>', unsafe_allow_html=True)
    lideres = sorted(df["lider"].unique().tolist())
    # Coloca "Sem Equipe" por último
    if "Sem Equipe" in lideres:
        lideres = [l for l in lideres if l != "Sem Equipe"] + ["Sem Equipe"]

    for lider in lideres:
        df_eq = df[df["lider"] == lider].copy()
        render_equipe(df_eq, lider)


main()
