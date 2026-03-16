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

DESTINATARIOS_TESTE = ["hugo@connectgroup.solutions"]

DESTINATARIOS_FULL = [
    "bko2@connectbrasil.tech",
    "bko@connectbrasil.tech",
    "hugo@connectgroup.solutions",
    "angelo@connectgroup.solutions",
    "andrey.albuquerque@connectgroup.solutions",
]




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

    visao = st.radio("Visão do ranking:", ["🎯 Ativação", "🎯 + ⏳ Ativação + Pipeline"],
                     horizontal=True, key="visao_ranking")
    incluir_pipeline = visao == "🎯 + ⏳ Ativação + Pipeline"
    st.markdown("")

    medals = ["🥇","🥈","🥉"]
    df_atv_all = df[df["mes_ativacao"] == MES_ALVO]
    df_pip_all = df[df["mes_ativacao"].isna()]

    def _vend_rec(d):
        r = d[d["mes_ativacao"] == MES_ALVO]["preco_oferta"].sum()
        if incluir_pipeline:
            r += d[d["mes_ativacao"].isna()]["preco_oferta"].sum()
        return r

    c_gauge, c_eq, c_vend = st.columns([1, 2, 2])

    # Gauge
    with c_gauge:
        rec_atv = df_atv_all["preco_oferta"].sum()
        rec_pip = df_pip_all["preco_oferta"].sum()
        rec_g   = rec_atv + rec_pip if incluir_pipeline else rec_atv
        n_v     = df["vendedor_real"].nunique()
        meta    = n_v * META_VENDEDOR
        pct     = min(int(rec_g / meta * 100), 999) if meta > 0 else 0
        cor     = _cor(pct)
        sub_pip = f"<div class='gauge-sub' style='margin-top:2px'>⏳ +R$ {rec_pip:,.2f} pipeline</div>" if incluir_pipeline else "<div></div>"
        st.markdown(f"""<div class="gauge-wrap">
          <div class="vis-title">🎯 {'Ativ. + Pipeline' if incluir_pipeline else 'Atingimento Receita'}</div>
          <div class="gauge-pct" style="color:{cor}">{pct}%</div>
          <div style="margin:10px 0">{_bar(rec_g, meta, cor, 14)}</div>
          <div class="gauge-sub">R$ {rec_g:,.2f} de R$ {meta:,.2f}</div>
          {sub_pip}
          <div class="gauge-sub" style="margin-top:4px">{n_v} vendedor(es) × R$ {META_VENDEDOR:,}</div>
        </div>""", unsafe_allow_html=True)

    # Ranking equipes
    with c_eq:
        st.markdown('<div class="vis-card">', unsafe_allow_html=True)
        lbl_eq = "Ativ. + Pipeline" if incluir_pipeline else "Receita Ativada"
        st.markdown(f'<div class="vis-title">🏆 Ranking de Equipes — {lbl_eq}</div>', unsafe_allow_html=True)
        rows = []
        for l in lideres:
            dl   = df[df["lider"] == l]
            nv   = dl["vendedor_real"].nunique()
            r    = _vend_rec(dl)
            ratv = dl[dl["mes_ativacao"] == MES_ALVO]["preco_oferta"].sum()
            rpip = dl[dl["mes_ativacao"].isna()]["preco_oferta"].sum()
            rows.append({"lider":l,"rec":r,"ratv":ratv,"rpip":rpip,"meta":nv*META_VENDEDOR,"nv":nv})
        rows = sorted(rows, key=lambda x: x["rec"], reverse=True)
        mx   = max((r["rec"] for r in rows), default=1)
        html = ""
        for i, r in enumerate(rows):
            p = min(int(r["rec"]/r["meta"]*100),100) if r["meta"] > 0 else 0
            c = _cor(p)
            m = medals[i] if i < 3 else f"{i+1}º"
            pip_info = f" <span style='color:#f59e0b;font-size:0.7rem'>+R$ {r['rpip']:,.2f} pip.</span>" if incluir_pipeline else ""
            html += f"""<div class="rank-bar-wrap">
              <div class="rank-name"><span>{m} {r['lider']}</span>
              <span style="color:{c};font-weight:700">R$ {r['rec']:,.2f}{pip_info} <span style="color:#64748b">({p}%)</span></span></div>
              {_bar(r['rec'], mx, c)}
              <div class="rank-meta">{r['nv']} vendedor(es) · meta R$ {r['meta']:,.2f}</div>
            </div>"""
        st.markdown(html, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # Ranking vendedores
    with c_vend:
        st.markdown('<div class="vis-card">', unsafe_allow_html=True)
        lbl_v = f"👤 Top Vendedores{' — '+lider_sel if lider_sel != 'Todos' else ''} — {'Ativ. + Pipeline' if incluir_pipeline else 'Ativação'}"
        st.markdown(f'<div class="vis-title">{lbl_v}</div>', unsafe_allow_html=True)

        ser_atv = df_atv_all.groupby("vendedor_real")["preco_oferta"].sum()
        ser_pip = df_pip_all.groupby("vendedor_real")["preco_oferta"].sum()

        if incluir_pipeline:
            ser_tot = ser_atv.add(ser_pip, fill_value=0).sort_values(ascending=False).head(10)
        else:
            ser_tot = ser_atv.sort_values(ascending=False).head(10)

        mx_v  = ser_tot.max() if not ser_tot.empty else 1
        html_v = ""
        for i, (vend, val) in enumerate(ser_tot.items()):
            p  = min(int(val / META_VENDEDOR * 100), 100)
            c  = _cor(p)
            m  = medals[i] if i < 3 else f"{i+1}º"
            if incluir_pipeline:
                a = ser_atv.get(vend, 0)
                p2= ser_pip.get(vend, 0)
                sub = f"<div class='rank-meta'>✅ R$ {a:,.2f} · ⏳ R$ {p2:,.2f} · meta R$ {META_VENDEDOR:,}</div>"
            else:
                sub = f"<div class='rank-meta'>meta individual R$ {META_VENDEDOR:,}</div>"
            html_v += f"""<div class="rank-bar-wrap">
              <div class="rank-name"><span>{m} {vend}</span>
              <span style="color:{c};font-weight:700">R$ {val:,.2f} <span style="color:#64748b">({p}%)</span></span></div>
              {_bar(val, mx_v, c)}{sub}
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

    # ── Pendências de cadastro ──
    st.markdown('<p class="section-title">⚠️ Pendências de Cadastro no BKO</p>', unsafe_allow_html=True)

    # Reconstrói df completo sem filtro de líder para pegar todos os pedidos
    df_full = apply_filters(raw.copy(), MES_ALVO, ["NOVO","ADITIVO"], parceiro_sel)
    if not bko.empty and "pedido" in df_full.columns:
        df_full["pedido"] = df_full["pedido"].apply(_norm_pedido)
        bk2 = bko.copy()
        bk2["pedido"] = bk2["pedido"].apply(_norm_pedido)
        df_full = df_full.merge(bk2[["pedido","vendedor_real","lider"]], on="pedido", how="left")
        df_full["vendedor_real"] = df_full["vendedor_real"].fillna("")
        df_full["lider"]         = df_full["lider"].fillna("")
    else:
        df_full["vendedor_real"] = ""
        df_full["lider"]         = ""

    COLS_SHOW = [c for c in ["pedido","razao_social","fila_atual","status_dash","acessos","preco_oferta","mes_ativacao"] if c in df_full.columns]
    COL_CFG = {
        "pedido":       "Pedido",
        "razao_social": "Razão Social",
        "fila_atual":   "Fila Atual",
        "status_dash":  "Status",
        "acessos":      st.column_config.NumberColumn("Acessos", format="%d"),
        "preco_oferta": st.column_config.NumberColumn("R$", format="R$ %.2f"),
        "mes_ativacao": "Mês Ativação",
    }

    tab_nan, tab_seq = st.tabs(["❓ Não cadastrados no BKO", "👤 Sem Equipe (BKO sem Líder)"])

    with tab_nan:
        df_nan = df_full[df_full["vendedor_real"] == ""][COLS_SHOW].copy()
        if df_nan.empty:
            st.success("✅ Todos os pedidos estão cadastrados no BKO!")
        else:
            st.warning(f"**{len(df_nan)} pedido(s)** sem cadastro no BKO-VENDEDOR-REAL.")
            st.dataframe(df_nan, use_container_width=True, hide_index=True, column_config=COL_CFG)
            csv = df_nan.to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Exportar (.csv)", data=csv,
                file_name=f"sem_bko_{MES_ALVO.replace('/','_')}.csv", mime="text/csv")

    with tab_seq:
        df_seq = df_full[df_full["lider"] == "Sem Equipe"][COLS_SHOW + ["vendedor_real"]].copy() if "Sem Equipe" in df_full["lider"].values else pd.DataFrame()
        if df_seq.empty:
            st.success("✅ Todos os pedidos cadastrados no BKO têm equipe definida!")
        else:
            st.warning(f"**{len(df_seq)} pedido(s)** com vendedor no BKO mas sem líder definido.")
            st.dataframe(df_seq, use_container_width=True, hide_index=True,
                column_config={**COL_CFG, "vendedor_real": "Vendedor Real"})
            csv2 = df_seq.to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Exportar (.csv)", data=csv2,
                file_name=f"sem_equipe_{MES_ALVO.replace('/','_')}.csv", mime="text/csv")

    # ── Botão de envio de e-mail ──
    st.markdown("")
    total_pend = len(df_nan) + len(df_seq) if 'df_nan' in dir() and 'df_seq' in dir() else 0
    st.markdown("---")
    if total_pend > 0:
        c_toggle, c_btn, c_info = st.columns([1, 1, 3])
        with c_toggle:
            modo_teste = st.toggle("🧪 Só para mim", value=True,
                help="Ativado = envia só para hugo@connectgroup.solutions | Desativado = envia para toda a lista")
        with c_btn:
            enviar = st.button("📧 Notificar por E-mail", type="primary", use_container_width=True)
        with c_info:
            dest_lista = DESTINATARIOS_TESTE if modo_teste else DESTINATARIOS_FULL
            st.markdown(f"""<div style="padding:8px 0;color:#94a3b8;font-size:0.8rem">
              {'🧪 Modo teste — ' if modo_teste else '📢 Envio completo — '}
              <strong style="color:#e2e8f0">{' · '.join(dest_lista)}</strong><br>
              <span style="color:#64748b">Inclui tabelas HTML e CSVs em anexo.</span>
            </div>""", unsafe_allow_html=True)
        if enviar:
            with st.spinner("Enviando e-mail..."):
                df_nan_e = df_nan if not df_nan.empty else pd.DataFrame()
                df_seq_e = df_seq if not df_seq.empty else pd.DataFrame()
                try:
                    import requests as _req
                    cfg = st.secrets["email"]

                    def _tab(df, titulo, cor):
                        if df.empty:
                            return f"<h3 style='color:{cor}'>{titulo}</h3><p>✅ Nenhuma pendência.</p>"
                        lns = "".join(f"<tr>{''.join(f'<td style=padding:6px 10px;border:1px solid #ddd>{v}</td>' for v in r)}</tr>" for r in df.values)
                        ths = "".join(f"<th style='padding:8px 10px;background:{cor};color:#fff;text-align:left'>{c}</th>" for c in df.columns)
                        return f"<h3 style='color:{cor};margin-top:24px'>{titulo} ({len(df)})</h3><table style='border-collapse:collapse;width:100%;font-size:13px'><tr>{ths}</tr>{lns}</table>"

                    from datetime import datetime as _dt
                    agora = _dt.now().strftime("%d/%m/%Y às %H:%M")

                    BKO_URL = "https://docs.google.com/spreadsheets/d/1HmtEFf2Akh7NLR2prxDh9S4gmioKYw419B4bkx4yBLg/edit?gid=2090275960#gid=2090275960"

                    # Monta lista de vendedores sem cadastro
                    vendedores_nan = ""
                    if not df_nan_e.empty and "razao_social" in df_nan_e.columns:
                        itens = "".join(
                            f"<li><strong>{row.get('pedido','')}</strong> — {row.get('razao_social','')}</li>"
                            for row in df_nan_e.to_dict("records")
                        )
                        vendedores_nan = f"<ul style='margin:8px 0 0 0;font-size:13px'>{itens}</ul>"

                    html = f"""<html><body style="font-family:Arial,sans-serif;color:#333;max-width:900px">
                      <div style="background:linear-gradient(135deg,#0d2b1a,#15803d);padding:20px 30px;border-radius:10px;margin-bottom:24px">
                        <h2 style="color:#fff;margin:0">⚠️ Pendências BKO — Connect Group</h2>
                        <p style="color:rgba(255,255,255,0.75);margin:6px 0 0">{MES_ALVO} · Gerado em {agora}</p>
                      </div>
                      <p style="font-size:15px">Olá, identificamos <strong>pendência de nome do VENDEDOR REAL</strong> na planilha online em <strong>{agora}</strong>:</p>
                      <ul>
                        <li><strong>{len(df_nan_e)}</strong> pedido(s) aguardando cadastro do Vendedor Real no BKO</li>
                        <li><strong>{len(df_seq_e)}</strong> pedido(s) com vendedor cadastrado mas sem líder definido</li>
                      </ul>
                      {_tab(df_nan_e,"❓ Pedidos sem Vendedor Real no BKO","#dc2626")}
                      {_tab(df_seq_e,"👤 Pedidos sem Líder definido","#d97706")}
                      <br>
                      <div style="background:#f0fdf4;border:1px solid #86efac;border-radius:8px;padding:16px 20px;margin:24px 0">
                        <p style="margin:0;font-size:14px">
                          📋 <strong>Acesse a planilha BKO diretamente para preencher:</strong><br><br>
                          <a href="{BKO_URL}" style="color:#15803d;font-weight:bold;font-size:14px">
                            👉 Clique aqui para abrir o BKO-VENDEDOR-REAL
                          </a>
                        </p>
                      </div>
                      <hr><p style="font-size:11px;color:#999">Mensagem automática — dashboard Connect Group</p>
                    </body></html>"""

                    # Titan SMTP via SSL
                    import smtplib
                    from email.mime.multipart import MIMEMultipart as _MM
                    from email.mime.text import MIMEText as _MT

                    cfg = st.secrets["email"]
                    msg = _MM("alternative")
                    msg["Subject"] = f"[Connect Group] Pendências BKO — {MES_ALVO} ({total_pend} itens)"
                    msg["From"]    = cfg.get("from", cfg["user"])
                    msg["To"]      = ", ".join(dest_lista)
                    msg.attach(_MT(html, "html"))

                    with smtplib.SMTP_SSL(cfg["host"], int(cfg["port"]), timeout=20) as sv:
                        sv.login(cfg["user"], cfg["password"])
                        sv.sendmail(cfg["user"], dest_lista, msg.as_string())

                    st.success(f"✅ E-mail enviado para: {', '.join(dest_lista)}")

                except Exception as e:
                    st.error(f"❌ Erro ao enviar: {e}")
    else:
        st.success("✅ Sem pendências — nenhum e-mail necessário.")


main()
