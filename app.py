import streamlit as st
import pandas as pd
from data_loader import (load_metas,
    load_data, apply_filters, get_parceiros,
    STATUS_COLORS
)

st.set_page_config(
    page_title="Connect Group | Vendas",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

MES_ALVO = "03/2026"

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
  html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
  .stApp { background-color: #0f1117; color: #e2e8f0; }
  .header-vendas {
    background: linear-gradient(135deg, #0a2463 0%, #1e3a8a 40%, #1d4ed8 70%, #3b82f6 100%);
    border-radius: 16px; padding: 28px 36px; margin-bottom: 28px;
    box-shadow: 0 8px 32px rgba(59,130,246,0.3);
    border: 1px solid rgba(255,255,255,0.08);
    display: flex; align-items: center; justify-content: space-between;
  }
  .header-title { font-size: 1.9rem; font-weight: 800; color: #fff; letter-spacing: -0.5px; margin: 0; }
  .header-sub   { font-size: 0.85rem; color: rgba(255,255,255,0.65); margin: 4px 0 0 0; }
  .header-badge {
    background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.25);
    border-radius: 20px; padding: 6px 16px; font-size: 0.8rem; color: #fff; font-weight: 600;
  }
  .kpi-card {
    background: #1a1f2e; border-radius: 14px; padding: 22px 24px;
    border: 1px solid #2d3748; position: relative; overflow: hidden; margin-bottom: 4px;
  }
  .kpi-card::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; }
  .kpi-card.blue::before   { background: linear-gradient(90deg, #3b82f6, #1d4ed8); }
  .kpi-card.green::before  { background: linear-gradient(90deg, #10b981, #059669); }
  .kpi-card.amber::before  { background: linear-gradient(90deg, #f59e0b, #d97706); }
  .kpi-card.purple::before { background: linear-gradient(90deg, #8b5cf6, #6d28d9); }
  .kpi-label { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 1px; color: #94a3b8; font-weight: 600; margin-bottom: 8px; }
  .kpi-value { font-size: 2.1rem; font-weight: 800; color: #f1f5f9; line-height: 1; }
  .kpi-sub   { font-size: 0.78rem; color: #64748b; margin-top: 6px; }
  .progress-wrap { margin-top: 12px; }
  .progress-label { display:flex; justify-content:space-between; font-size:0.72rem; color:#64748b; margin-bottom:5px; }
  .progress-bar-bg   { background:#2d3748; border-radius:99px; height:8px; }
  .progress-bar-fill { height:8px; border-radius:99px; }
  .kanban-header { border-radius:10px 10px 0 0; padding:12px 16px; display:flex; align-items:center; justify-content:space-between; }
  .kanban-title { font-weight:700; font-size:0.9rem; color:#fff; }
  .kanban-count { font-size:0.78rem; font-weight:600; color:rgba(255,255,255,0.8); }
  section[data-testid="stSidebar"] { background: #111827 !important; }
  details { background:#1a1f2e !important; border:1px solid #2d3748 !important; border-radius:0 0 10px 10px !important; }
  details summary { color:#e2e8f0 !important; font-weight:600 !important; }
  .section-title { font-size:0.75rem; text-transform:uppercase; letter-spacing:1.5px; color:#64748b; font-weight:600; margin:24px 0 12px 0; }
</style>
""", unsafe_allow_html=True)


def progress_html(value, total, color="#3b82f6"):
    pct = min(int(value / total * 100), 100) if total > 0 else 0
    return f"""<div class="progress-wrap">
      <div class="progress-label"><span>Atingimento</span><span>{pct}%</span></div>
      <div class="progress-bar-bg"><div class="progress-bar-fill" style="width:{pct}%;background:{color}"></div></div>
    </div>"""


def kanban_column(df_col, status, col_obj):
    cfg     = STATUS_COLORS.get(status, STATUS_COLORS["ENTRANTE"])
    vol     = int(df_col["acessos"].sum())    if not df_col.empty else 0
    receita = df_col["preco_oferta"].sum()     if not df_col.empty else 0
    with col_obj:
        st.markdown(f"""
        <div class="kanban-header" style="background:{cfg['border']}22;border-top:3px solid {cfg['border']};">
          <span class="kanban-title">{cfg['icon']} {status}</span>
          <span class="kanban-count">{vol} acessos</span>
        </div>""", unsafe_allow_html=True)
        with st.expander(f"Σ {vol} · R$ {receita:,.2f}", expanded=False):
            if df_col.empty:
                st.info("Nenhum registro.")
            else:
                grouped = (df_col.groupby("razao_social", as_index=False)
                           .agg(GROSS=("acessos","sum"), **{"R$":("preco_oferta","sum")})
                           .sort_values("GROSS", ascending=False))
                st.dataframe(grouped, use_container_width=True, hide_index=True,
                    column_config={
                        "razao_social": "Razão Social",
                        "GROSS": st.column_config.NumberColumn("GROSS", format="%d"),
                        "R$":    st.column_config.NumberColumn("R$",    format="R$ %.2f"),
                    })


def main():
    st.markdown("""
    <div class="header-vendas">
      <div>
        <p class="header-title">📊 PAINEL DE VENDAS — CONNECT GROUP</p>
        <p class="header-sub">TIM Corporate · Novos e Aditivos · Março/2026</p>
      </div>
      <div class="header-badge">🔵 VENDAS</div>
    </div>""", unsafe_allow_html=True)

    with st.spinner("Carregando dados do Google Sheets..."):
        raw   = load_data()
        metas = load_metas()

    META_VENDAS  = int(metas["vendas_acessos"])
    META_RECEITA = metas["vendas_receita"]

    if raw.empty:
        st.warning("⚠️ Nenhum dado encontrado. Verifique a conexão com o Google Sheets.")
        st.stop()

    with st.sidebar:
        st.markdown("### 🔧 Filtros")
        parceiro_sel = st.selectbox("Parceiro / Aba", get_parceiros(raw))
        st.markdown("---")
        if st.button("🔄 Atualizar dados"):
            st.cache_data.clear()
            st.rerun()
        st.markdown("---")
        st.markdown(f"**Mês:** `{MES_ALVO}`")
        st.markdown(f"**Meta Acessos:** `{META_VENDAS:,}`")
        st.markdown(f"**Meta Receita:** `R$ {META_RECEITA:,.2f}`")
        st.caption("Dados via Google Sheets · cache 3 min")

    df = apply_filters(raw.copy(), MES_ALVO, ["NOVO", "ADITIVO"], parceiro_sel)
    if "status_dash" in df.columns:
        st.sidebar.caption("STATUS: " + str(df["status_dash"].value_counts().to_dict()))
    if "fila_atual" in df.columns:
        st.sidebar.caption("FILA: " + str(df["fila_atual"].unique().tolist()[:8]))

    ativados    = df[df["mes_ativacao"] == MES_ALVO]
    vol_ativado = int(ativados["acessos"].sum())
    receita     = ativados["preco_oferta"].sum()
    pipeline    = int(df[df["mes_ativacao"].isna()]["acessos"].sum())

    pct_acessos = min(int(vol_ativado / META_VENDAS * 100), 100) if META_VENDAS else 0
    pct_receita = min(int(receita / META_RECEITA * 100), 100) if META_RECEITA else 0
    faltam_acessos = max(META_VENDAS - vol_ativado, 0)
    faltam_receita = max(META_RECEITA - receita, 0)

    st.markdown('<p class="section-title">📈 KPIs do Mês</p>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"""<div class="kpi-card blue">
          <div class="kpi-label">🎯 Volume de Acessos</div>
          <div style="display:flex;align-items:baseline;gap:12px;margin:8px 0">
            <span style="font-size:2.1rem;font-weight:800;color:#f1f5f9">{vol_ativado:,}</span>
            <span style="font-size:1rem;color:#94a3b8">de <b style="color:#e2e8f0">{META_VENDAS:,}</b> meta</span>
          </div>
          <div style="display:flex;justify-content:space-between;font-size:0.78rem;color:#64748b;margin-bottom:4px">
            <span>Faltam: <b style="color:#f59e0b">{faltam_acessos:,} acessos</b></span>
            <span>Em pipeline: <b style="color:#3b82f6">{pipeline:,}</b></span>
          </div>
          {progress_html(vol_ativado, META_VENDAS, "#3b82f6")}
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class="kpi-card green">
          <div class="kpi-label">💰 Receita Contratada</div>
          <div style="display:flex;align-items:baseline;gap:12px;margin:8px 0">
            <span style="font-size:2.1rem;font-weight:800;color:#f1f5f9">R$ {receita:,.2f}</span>
            <span style="font-size:1rem;color:#94a3b8">de <b style="color:#e2e8f0">R$ {META_RECEITA:,.2f}</b> meta</span>
          </div>
          <div style="display:flex;justify-content:space-between;font-size:0.78rem;color:#64748b;margin-bottom:4px">
            <span>Faltam: <b style="color:#f59e0b">R$ {faltam_receita:,.2f}</b></span>
            <span>Atingimento: <b style="color:#10b981">{pct_receita}%</b></span>
          </div>
          {progress_html(receita, META_RECEITA, "#10b981")}
        </div>""", unsafe_allow_html=True)

    st.markdown('<p class="section-title">🗂️ Kanban de Tramitação</p>', unsafe_allow_html=True)
    k1, k2, k3, k4, k5 = st.columns(5)
    kanban_column(df[df["status_dash"] == "PRÉ-VENDA"],   "PRÉ-VENDA",   k1)
    kanban_column(df[df["status_dash"] == "EM ANÁLISE"], "EM ANÁLISE", k2)
    kanban_column(df[df["status_dash"] == "CRÉDITO"],    "CRÉDITO",    k3)
    kanban_column(df[df["status_dash"] == "DEVOLVIDOS"], "DEVOLVIDOS", k4)
    kanban_column(df[df["status_dash"] == "ENTRANTE"],   "ENTRANTE",   k5)

    st.markdown('<p class="section-title">📋 Dados Completos</p>', unsafe_allow_html=True)
    with st.expander("Ver todos os registros filtrados"):
        cols = [c for c in ["razao_social","parceiro","tipo_contratacao","fila_atual",
                             "status_dash","acessos","preco_oferta","mes_ativacao","mes_input"]
                if c in df.columns]
        st.dataframe(df[cols], use_container_width=True, hide_index=True)

main()
