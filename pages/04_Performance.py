import streamlit as st
import pandas as pd
from data_loader import (
    load_data, load_bko, apply_filters, get_parceiros,
    STATUS_COLORS, _s, _norm_pedido
)
from auth import require_password

st.set_page_config(
    page_title="Connect Group | Performance",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="expanded"
)

require_password("performance", "Performance — Connect Group")

MES_ALVO      = "03/2026"
META_VENDEDOR = 850

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
  .header-badge { background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.25); border-radius: 20px; padding: 6px 16px; font-size: 0.8rem; color: #fff; font-weight: 600; }
  .equipe-header { background: linear-gradient(90deg, #1a2e1a, #1e3a2e); border-left: 4px solid #22c55e; border-radius: 10px; padding: 14px 20px; margin: 28px 0 16px 0; display: flex; align-items: center; justify-content: space-between; }
  .equipe-nome  { font-size: 1.1rem; font-weight: 800; color: #86efac; }
  .equipe-total { font-size: 0.85rem; color: #64748b; }
  .kpi-mini { background: #1a1f2e; border-radius: 12px; padding: 16px 18px; border: 1px solid #2d3748; position: relative; overflow: hidden; margin-bottom: 4px; }
  .kpi-mini::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; }
  .kpi-mini.blue::before   { background: linear-gradient(90deg, #3b82f6, #1d4ed8); }
  .kpi-mini.green::before  { background: linear-gradient(90deg, #22c55e, #15803d); }
  .kpi-mini.red::before    { background: linear-gradient(90deg, #ef4444, #dc2626); }
  .kpi-mini.amber::before  { background: linear-gradient(90deg, #f59e0b, #d97706); }
  .kpi-mini.purple::before { background: linear-gradient(90deg, #8b5cf6, #6d28d9); }
  .kpi-label { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 1px; color: #94a3b8; font-weight: 600; margin-bottom: 6px; }
  .kpi-value { font-size: 1.7rem; font-weight: 800; color: #f1f5f9; line-height: 1; }
  .kpi-sub   { font-size: 0.72rem; color: #64748b; margin-top: 4px; }
  .rank-bar-wrap { margin: 4px 0 10px 0; }
  .rank-name  { font-size: 0.8rem; font-weight: 600; color: #e2e8f0; margin-bottom: 3px; display:flex; justify-content:space-between; }
  .rank-bg    { background: #2d3748; border-radius: 99px; height: 10px; }
  .rank-fill  { height: 10px; border-radius: 99px; }
  .rank-meta  { font-size: 0.68rem; color: #64748b; margin-top: 2px; }
  .gauge-wrap { background: #1a1f2e; border-radius: 14px; padding: 20px 24px; border: 1px solid #2d3748; text-align: center; }
  .gauge-pct  { font-size: 3rem; font-weight: 800; line-height: 1; margin: 8px 0 4px; }
  .gauge-sub  { font-size: 0.75rem; color: #64748b; }
  .kanban-header { border-radius: 10px 10px 0 0; padding: 10px 14px; display:flex; align-items:center; justify-content:space-between; }
  .kanban-title  { font-weight: 700; font-size: 0.82rem; color: #fff; }
  .kanban-count  { font-size: 0.72rem; font-weight: 600; color: rgba(255,255,255,0.8); }
  .section-title { font-size:0.75rem; text-transform:uppercase; letter-spacing:1.5px; color:#22c55e; font-weight:700; margin:24px 0 12px 0; border-left: 3px solid #22c55e; padding-left: 10px; }
  section[data-testid="stSidebar"] { background: #0d1a0f !important; }
  details { background:#1a1f2e !important; border:1px solid #2d3748 !important; border-radius:0 0 10px 10px !important; }
  details summary { color:#e2e8f0 !important; font-weight:600 !important; }
  .divider { border: none; border-top: 1px solid #1e293b; margin: 28px 0; }
  .vis-card { background: #1a1f2e; border-radius: 14px; padding: 20px 24px; border: 1px solid #2d3748; }
  .vis-title { font-size: 0.78rem; text-transform: uppercase; letter-spacing: 1px; color: #94a3b8; font-weight: 600; margin-bottom: 16px; }
</style>
""", unsafe_allow_html=True)


def _bar(valor, maximo, cor="#22c55e", h=10):
    pct = min(int(valor / maximo * 100), 100) if maximo > 0 else 0
    return f'<div class="rank-bg"><div class="rank-fill" style="width:{pct}%;background:{cor};height:{h}px"></div></div>'

def _cor(pct):
    if pct >= 100: return "#22c55e"
    if pct >= 70:  return "#f59e0b"
    return "#ef4444"


def kanban_col(df_col, status, col_obj, label=None):
    display = label if label else status
    cfg = STATUS_COLORS.get(status, STATUS_COLORS["ENTRANTE"])
    vol = int(df_col["acessos"].sum()) if not df_col.empty else 0
    rec = df_col["preco_oferta"].sum() if not df_col.empty else 0
    with col_obj:
        st.markdown(f"""<div class="kanban-header" style="background:{cfg['border']}22;border-top:3px solid {cfg['border']};">
          <span class="kanban-title">{cfg['icon']} {display}</span>
          <span class="kanban-count">{vol} ac.</span></div>""", unsafe_allow_html=True)
        with st.expander(f"Σ {vol} · R$ {rec:,.2f}", expanded=False):
            if df_col.empty:
                st.info("Nenhum registro.")
            else:
                g = (df_col.groupby("vendedor_real", as_index=False)
                     .agg(GROSS=("acessos","sum"), **{"R$":("preco_oferta","sum")})
                     .sort_values("GROSS", ascending=False))
                st.dataframe(g, use_container_width=True, hide_index=True,
                    column_config={"vendedor_real":"Vendedor",
                        "GROSS":st.column_config.NumberColumn("GROSS",format="%d"),
                        "R$":st.column_config.NumberColumn("R$",format="R$ %.2f")})


def render_visual(df, lideres, lider_sel):
    st.markdown('<p class="section-title">📊 Painel de Performance</p>', unsafe_allow_html=True)

    c_gauge, c_eq, c_vend = st.columns([1, 2, 2])

    # Gauge
    with c_gauge:
        rec = df[df["mes_ativacao"] == MES_ALVO]["preco_oferta"].sum()
        n_v = df["vendedor_real"].nunique()
        meta = n_v * META_VENDEDOR
        pct = min(int(rec / meta * 100), 999) if meta > 0 else 0
        cor = _cor(pct)
        st.markdown(f"""<div class="gauge-wrap">
          <div class="vis-title">🎯 Atingimento Receita</div>
          <div class="gauge-pct" style="color:{cor}">{pct}%</div>
          <div style="margin:10px 0">{_bar(rec, meta, cor, 14)}</div>
          <div class="gauge-sub">R$ {rec:,.2f} de R$ {meta:,.2f}</div>
          <div class="gauge-sub" style="margin-top:4px">{n_v} vendedor(es) × R$ {META_VENDEDOR:,}</div>
        </div>""", unsafe_allow_html=True)

    # Ranking equipes
    with c_eq:
        st.markdown('<div class="vis-card">', unsafe_allow_html=True)
        st.markdown('<div class="vis-title">🏆 Ranking de Equipes — Receita Ativada</div>', unsafe_allow_html=True)
        rows = []
        for l in lideres:
            dl = df[df["lider"] == l]
            nv = dl["vendedor_real"].nunique()
            r  = dl[dl["mes_ativacao"] == MES_ALVO]["preco_oferta"].sum()
            rows.append({"lider": l, "rec": r, "meta": nv * META_VENDEDOR, "nv": nv})
        rows = sorted(rows, key=lambda x: x["rec"], reverse=True)
        mx = max((r["rec"] for r in rows), default=1)
        medals = ["🥇","🥈","🥉"]
        html = ""
        for i, r in enumerate(rows):
            p = min(int(r["rec"]/r["meta"]*100),100) if r["meta"] > 0 else 0
            c = _cor(p)
            m = medals[i] if i < 3 else f"{i+1}º"
            html += f"""<div class="rank-bar-wrap">
              <div class="rank-name"><span>{m} {r['lider']}</span>
              <span style="color:{c};font-weight:700">R$ {r['rec']:,.2f} <span style="color:#64748b">({p}%)</span></span></div>
              {_bar(r['rec'], mx, c)}
              <div class="rank-meta">{r['nv']} vendedor(es) · meta R$ {r['meta']:,.2f}</div>
            </div>"""
        st.markdown(html, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # Ranking vendedores
    with c_vend:
        st.markdown('<div class="vis-card">', unsafe_allow_html=True)
        titulo = f"👤 Top Vendedores{' — '+lider_sel if lider_sel != 'Todos' else ''}"
        st.markdown(f'<div class="vis-title">{titulo} — Receita Ativada</div>', unsafe_allow_html=True)
        vr = (df[df["mes_ativacao"] == MES_ALVO]
              .groupby("vendedor_real")["preco_oferta"].sum()
              .reset_index().sort_values("preco_oferta", ascending=False).head(10))
        mx_v = vr["preco_oferta"].max() if not vr.empty else 1
        html_v = ""
        for i, row in enumerate(vr.itertuples()):
            p = min(int(row.preco_oferta / META_VENDEDOR * 100), 100)
            c = _cor(p)
            m = medals[i] if i < 3 else f"{i+1}º"
            html_v += f"""<div class="rank-bar-wrap">
              <div class="rank-name"><span>{m} {row.vendedor_real}</span>
              <span style="color:{c};font-weight:700">R$ {row.preco_oferta:,.2f} <span style="color:#64748b">({p}%)</span></span></div>
              {_bar(row.preco_oferta, mx_v, c)}
              <div class="rank-meta">meta individual R$ {META_VENDEDOR:,}</div>
            </div>"""
        if not html_v:
            html_v = '<p style="color:#64748b;font-size:0.8rem">Nenhuma ativação no período.</p>'
        st.markdown(html_v, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # Segunda linha — distribuição pipeline
    st.markdown("")
    c_status, c_pip_vend = st.columns(2)

    with c_status:
        st.markdown('<div class="vis-card">', unsafe_allow_html=True)
        st.markdown('<div class="vis-title">📌 Pipeline por Status</div>', unsafe_allow_html=True)
        pip = df[df["mes_ativacao"].isna()]
        if not pip.empty and "status_dash" in pip.columns:
            sc = (pip.groupby("status_dash").agg(acessos=("acessos","sum"))
                  .reset_index().sort_values("acessos", ascending=False))
            tot = sc["acessos"].sum()
            html_s = ""
            for _, row in sc.iterrows():
                cfg = STATUS_COLORS.get(row["status_dash"], {"border":"#64748b","icon":"▪️"})
                p = round(row["acessos"]/tot*100, 1) if tot > 0 else 0
                html_s += f"""<div class="rank-bar-wrap">
                  <div class="rank-name"><span>{cfg['icon']} {row['status_dash']}</span>
                  <span style="color:#e2e8f0">{int(row['acessos'])} ac. <span style="color:#64748b">({p}%)</span></span></div>
                  {_bar(row['acessos'], tot, cfg['border'])}
                </div>"""
            st.markdown(html_s, unsafe_allow_html=True)
        else:
            st.info("Nenhum pipeline.")
        st.markdown('</div>', unsafe_allow_html=True)

    with c_pip_vend:
        st.markdown('<div class="vis-card">', unsafe_allow_html=True)
        st.markdown('<div class="vis-title">⚡ Pipeline por Vendedor — Top 10</div>', unsafe_allow_html=True)
        pv = (df[df["mes_ativacao"].isna()].groupby("vendedor_real")["acessos"].sum()
              .reset_index().sort_values("acessos", ascending=False).head(10))
        if not pv.empty:
            mx_pv = pv["acessos"].max()
            html_pv = ""
            for i, row in enumerate(pv.itertuples()):
                html_pv += f"""<div class="rank-bar-wrap">
                  <div class="rank-name"><span>{i+1}º {row.vendedor_real}</span>
                  <span style="color:#f59e0b;font-weight:700">{int(row.acessos)} ac.</span></div>
                  {_bar(row.acessos, mx_pv, "#f59e0b")}
                </div>"""
            st.markdown(html_pv, unsafe_allow_html=True)
        else:
            st.info("Nenhum pipeline.")
        st.markdown('</div>', unsafe_allow_html=True)


def render_equipe(df_eq, lider):
    ac_ativ  = int(df_eq[df_eq["mes_ativacao"] == MES_ALVO]["acessos"].sum())
    rec_ativ = df_eq[df_eq["mes_ativacao"] == MES_ALVO]["preco_oferta"].sum()
    pipeline = int(df_eq[df_eq["mes_ativacao"].isna()]["acessos"].sum())
    n_vend   = df_eq["vendedor_real"].nunique()
    meta_eq  = n_vend * META_VENDEDOR
    pct      = min(int(rec_ativ / meta_eq * 100), 100) if meta_eq > 0 else 0
    cor      = _cor(pct)
    icon     = "✅" if pct >= 100 else "⚠️" if pct >= 70 else "🔴"

    st.markdown(f"""<div class="equipe-header">
      <span class="equipe-nome">👤 {lider}</span>
      <span class="equipe-total">{n_vend} vendedor(es) · meta {pct}% <span style="color:{cor}">{icon}</span></span>
    </div>""", unsafe_allow_html=True)

    c1,c2,c3,c4 = st.columns(4)
    with c1:
        st.markdown(f"""<div class="kpi-mini blue"><div class="kpi-label">🎯 Ativados</div>
          <div class="kpi-value">{ac_ativ:,}</div><div class="kpi-sub">acessos no mês</div></div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class="kpi-mini green"><div class="kpi-label">💰 Receita</div>
          <div class="kpi-value">R$ {rec_ativ:,.2f}</div>
          <div class="kpi-sub">{pct}% · meta R$ {meta_eq:,.2f}</div></div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""<div class="kpi-mini amber"><div class="kpi-label">⏳ Pipeline</div>
          <div class="kpi-value">{pipeline:,}</div><div class="kpi-sub">em tramitação</div></div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""<div class="kpi-mini purple"><div class="kpi-label">👥 Vendedores</div>
          <div class="kpi-value">{n_vend}</div><div class="kpi-sub">na equipe</div></div>""", unsafe_allow_html=True)

    st.markdown("")
    k1,k2,k3,k4,k5 = st.columns(5)
    kanban_col(df_eq[df_eq["status_dash"]=="PRE-VENDA"],  "PRE-VENDA",  k1)
    kanban_col(df_eq[df_eq["status_dash"]=="EM ANALISE"], "EM ANALISE", k2)
    kanban_col(df_eq[df_eq["status_dash"]=="CREDITO"],    "CREDITO",    k3)
    kanban_col(df_eq[df_eq["status_dash"]=="DEVOLVIDOS"], "DEVOLVIDOS", k4)
    kanban_col(df_eq[(df_eq["status_dash"]=="ENTRANTE") & df_eq["mes_ativacao"].isna()],
               "ENTRANTE", k5, label="ENTRANTE NÃO ATIVO")

    with st.expander("📋 Ranking de vendedores", expanded=False):
        rank = (df_eq.groupby("vendedor_real", as_index=False)
                .agg(
                    Ativados=("acessos", lambda x: int(x[df_eq.loc[x.index,"mes_ativacao"]==MES_ALVO].sum())),
                    Pipeline=("acessos", lambda x: int(x[df_eq.loc[x.index,"mes_ativacao"].isna()].sum())),
                    Receita=("preco_oferta","sum"),
                ).sort_values("Receita", ascending=False))
        rank["% Meta"] = rank["Receita"].apply(lambda r: f"{min(int(r/META_VENDEDOR*100),100)}%")
        st.dataframe(rank, use_container_width=True, hide_index=True,
            column_config={"vendedor_real":"Vendedor",
                "Ativados":st.column_config.NumberColumn("✅ Ativados",format="%d"),
                "Pipeline":st.column_config.NumberColumn("⏳ Pipeline",format="%d"),
                "Receita":st.column_config.NumberColumn("R$ Receita",format="R$ %.2f"),
                "% Meta":"% Meta"})

    st.markdown('<hr class="divider">', unsafe_allow_html=True)


def main():
    st.markdown("""<div class="header-perf">
      <div><p class="header-title">🏆 PERFORMANCE — CONNECT GROUP</p>
      <p class="header-sub">TIM Corporate · Visão por Equipe · Março/2026</p></div>
      <div class="header-badge">🟢 PERFORMANCE</div></div>""", unsafe_allow_html=True)

    with st.spinner("Carregando dados..."):
        raw = load_data()
        bko = load_bko()

    if raw.empty:
        st.warning("⚠️ Nenhum dado encontrado.")
        st.stop()

    with st.sidebar:
        st.markdown("### 🔧 Filtros")
        parceiro_sel = st.selectbox("Parceiro / Aba", get_parceiros(raw))
        lider_opts = ["Todos"] + sorted([l for l in bko["lider"].unique() if l and l != "Sem Equipe"]) if not bko.empty else ["Todos"]
        lider_sel  = st.selectbox("Equipe / Líder", lider_opts)
        st.markdown("---")
        if st.button("🔄 Atualizar dados"):
            st.cache_data.clear()
            st.rerun()
        st.markdown("---")
        st.markdown(f"**Mês:** `{MES_ALVO}`")
        st.markdown(f"**Meta/Vendedor:** `R$ {META_VENDEDOR:,}`")
        st.caption("Dados via Google Sheets · cache 3 min")

    df = apply_filters(raw.copy(), MES_ALVO, ["NOVO","ADITIVO"], parceiro_sel)

    if not bko.empty and "pedido" in df.columns:
        df["pedido"] = df["pedido"].apply(_norm_pedido)
        bk = bko.copy()
        bk["pedido"] = bk["pedido"].apply(_norm_pedido)
        df = df.merge(bk[["pedido","vendedor_real","lider"]], on="pedido", how="left")
        df["vendedor_real"] = df["vendedor_real"].apply(lambda x: _s(x) if _s(x) else "Sem Vendedor")
        df["lider"]         = df["lider"].apply(lambda x: _s(x) if _s(x) else "Sem Equipe")
    else:
        df["vendedor_real"] = "Sem Vendedor"
        df["lider"]         = "Sem Equipe"

    if lider_sel != "Todos":
        df = df[df["lider"] == lider_sel]

    if df.empty:
        st.info("Nenhum dado para os filtros selecionados.")
        st.stop()

    lideres = sorted([l for l in df["lider"].unique() if l != "Sem Equipe"])
    if "Sem Equipe" in df["lider"].unique():
        lideres += ["Sem Equipe"]

    # KPIs globais
    st.markdown('<p class="section-title">📈 Visão Consolidada</p>', unsafe_allow_html=True)
    atv_g  = df[df["mes_ativacao"] == MES_ALVO]
    ac_g   = int(atv_g["acessos"].sum())
    rec_g  = atv_g["preco_oferta"].sum()
    pip_g  = int(df[df["mes_ativacao"].isna()]["acessos"].sum())
    nv_g   = df["vendedor_real"].nunique()
    meta_g = nv_g * META_VENDEDOR
    pct_g  = min(int(rec_g / meta_g * 100), 999) if meta_g > 0 else 0

    g1,g2,g3,g4,g5 = st.columns(5)
    with g1:
        st.markdown(f"""<div class="kpi-mini blue"><div class="kpi-label">🎯 Acessos Ativados</div>
          <div class="kpi-value">{ac_g:,}</div><div class="kpi-sub">no mês</div></div>""", unsafe_allow_html=True)
    with g2:
        st.markdown(f"""<div class="kpi-mini green"><div class="kpi-label">💰 Receita Ativada</div>
          <div class="kpi-value">R$ {rec_g:,.2f}</div><div class="kpi-sub">{pct_g}% da meta</div></div>""", unsafe_allow_html=True)
    with g3:
        st.markdown(f"""<div class="kpi-mini amber"><div class="kpi-label">⏳ Pipeline</div>
          <div class="kpi-value">{pip_g:,}</div><div class="kpi-sub">em tramitação</div></div>""", unsafe_allow_html=True)
    with g4:
        st.markdown(f"""<div class="kpi-mini purple"><div class="kpi-label">👥 Vendedores</div>
          <div class="kpi-value">{nv_g}</div><div class="kpi-sub">meta R$ {meta_g:,.2f}</div></div>""", unsafe_allow_html=True)
    with g5:
        neq = len([l for l in lideres if l != "Sem Equipe"])
        st.markdown(f"""<div class="kpi-mini red"><div class="kpi-label">🏆 Equipes</div>
          <div class="kpi-value">{neq}</div><div class="kpi-sub">em exibição</div></div>""", unsafe_allow_html=True)

    st.markdown("")
    render_visual(df, lideres, lider_sel)

    st.markdown('<p class="section-title">👤 Desempenho por Equipe — Kanban</p>', unsafe_allow_html=True)
    for lider in lideres:
        render_equipe(df[df["lider"] == lider].copy(), lider)


main()
