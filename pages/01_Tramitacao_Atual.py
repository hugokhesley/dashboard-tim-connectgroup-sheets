import streamlit as st
import pandas as pd
from data_loader import (load_metas,
    load_data, apply_filters, get_parceiros,
    STATUS_COLORS,
    registrar_acesso
)
from auth import require_login

st.set_page_config(
    page_title="Connect Group | Tramitação Atual",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

username = require_login("tramitacao")
registrar_acesso("tramitacao", username=username)

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

  .pedidos-table { width:100%; border-collapse:collapse; font-size:0.83rem; }
  .pedidos-table th { background:#1e293b; color:#94a3b8; font-weight:600;
    font-size:0.7rem; text-transform:uppercase; letter-spacing:1px;
    padding:10px 14px; text-align:left; border-bottom:2px solid #2d3748; }
  .pedidos-table td { padding:9px 14px; border-bottom:1px solid #1e293b;
    color:#e2e8f0; vertical-align:middle; }
  .pedidos-table tr:hover td { background:#1a1f2e; }
  .status-pill { display:inline-block; border-radius:99px; padding:3px 10px;
    font-size:0.7rem; font-weight:700; letter-spacing:0.5px; }

</style>
""", unsafe_allow_html=True)


def progress_html(value, total, color="#3b82f6"):
    pct = min(int(value / total * 100), 100) if total > 0 else 0
    return f"""<div class="progress-wrap">
      <div class="progress-label"><span>Atingimento</span><span>{pct}%</span></div>
      <div class="progress-bar-bg"><div class="progress-bar-fill" style="width:{pct}%;background:{color}"></div></div>
    </div>"""


def kanban_column(df_col, status, col_obj, label=None):
    display = label if label else status
    cfg     = STATUS_COLORS.get(status, STATUS_COLORS["ENTRANTE"])
    vol     = int(df_col["acessos"].sum())    if not df_col.empty else 0
    receita = df_col["preco_oferta"].sum()     if not df_col.empty else 0
    with col_obj:
        st.markdown(f"""
        <div class="kanban-header" style="background:{cfg['border']}22;border-top:3px solid {cfg['border']};">
          <span class="kanban-title">{cfg['icon']} {display}</span>
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



STATUS_PILL = {
    "PRE-VENDA":  {"bg": "#78350f22", "border": "#f59e0b", "color": "#f59e0b", "icon": "⏳"},
    "EM ANALISE": {"bg": "#1e3a5f22", "border": "#3b82f6", "color": "#60a5fa", "icon": "🔍"},
    "CREDITO":    {"bg": "#2e1065aa", "border": "#8b5cf6", "color": "#a78bfa", "icon": "💳"},
    "DEVOLVIDOS": {"bg": "#7f1d1d22", "border": "#ef4444", "color": "#f87171", "icon": "↩️"},
    "ENTRANTE":   {"bg": "#05472a22", "border": "#10b981", "color": "#34d399", "icon": "✅"},
}

def render_pedidos_tramitacao(df: pd.DataFrame, raw: pd.DataFrame):
    """Tabela de pedidos em tramitação com Razão Social, Pedido e Phoenix."""
    st.markdown('<p class="section-title">📌 Pedidos em Tramitação</p>', unsafe_allow_html=True)

    # Pega colunas necessárias direto do raw (antes do apply_filters)
    # para ter acesso à coluna phoenix que pode ter nome variado
    from data_loader import normalize_columns, _dedup_columns, _s, _norm_pedido

    # Busca coluna phoenix no raw (nome pode variar em case)
    raw_norm = raw.copy()
    phoenix_col = None
    for c in raw_norm.columns:
        if _s(c).lower().strip() == "phoenix":
            phoenix_col = c
            break

    # Usa o df já filtrado por apply_filters
    df_tram = df[df["status_dash"].isin(["PRE-VENDA", "EM ANALISE", "CREDITO", "DEVOLVIDOS"])].copy()
    df_tram = df_tram[df_tram["mes_ativacao"].isna()].copy()

    if df_tram.empty:
        st.info("Nenhum pedido em tramitação no momento.")
        return

    # Tenta trazer phoenix do raw pelo índice original
    if phoenix_col and phoenix_col in raw.columns:
        # Junta pelo pedido
        raw_phoenix = raw[[phoenix_col, "pedido"]].copy() if "pedido" in raw.columns else pd.DataFrame()
        if not raw_phoenix.empty:
            raw_phoenix.columns = ["phoenix", "pedido"]
            raw_phoenix["pedido"] = raw_phoenix["pedido"].apply(_norm_pedido)
            df_tram["pedido"] = df_tram["pedido"].apply(_norm_pedido) if "pedido" in df_tram.columns else ""
            df_tram = df_tram.merge(raw_phoenix.drop_duplicates("pedido"), on="pedido", how="left")
    elif "phoenix" in df_tram.columns:
        pass  # já veio pelo apply_filters
    else:
        df_tram["phoenix"] = ""

    # Filtro por status
    status_disp = [s for s in ["PRE-VENDA", "EM ANALISE", "CREDITO", "DEVOLVIDOS"]
                   if s in df_tram["status_dash"].values]
    col_f1, col_f2 = st.columns([3, 1])
    with col_f1:
        busca = st.text_input("🔎 Buscar por cliente ou pedido",
                              placeholder="Ex: CONSIGBOT ou 123456",
                              key="busca_tramitacao", label_visibility="collapsed")
    with col_f2:
        status_sel = st.multiselect("Status", status_disp, default=status_disp,
                                    key="status_tram", label_visibility="collapsed",
                                    placeholder="Filtrar status...")

    df_show = df_tram[df_tram["status_dash"].isin(status_sel)].copy() if status_sel else df_tram.copy()

    if busca and len(busca.strip()) >= 2:
        termo = busca.strip().lower()
        mask = pd.Series([False] * len(df_show), index=df_show.index)
        if "razao_social" in df_show.columns:
            mask |= df_show["razao_social"].apply(lambda x: termo in _s(x).lower())
        if "pedido" in df_show.columns:
            mask |= df_show["pedido"].apply(lambda x: termo in _s(x).lower())
        df_show = df_show[mask]

    total_show = len(df_show)
    st.caption(f"{total_show} pedido(s) em tramitação")

    if df_show.empty:
        st.info("Nenhum pedido para o filtro selecionado.")
        return

    # Monta tabela HTML
    linhas = ""
    for _, row in df_show.sort_values("status_dash").iterrows():
        status  = _s(row.get("status_dash", ""))
        pill    = STATUS_PILL.get(status, {"bg":"#1e293b","border":"#64748b","color":"#94a3b8","icon":"•"})
        cliente = _s(row.get("razao_social", "—"))
        pedido  = _s(row.get("pedido", "—"))
        phoenix = _s(row.get("phoenix", "—"))
        acessos = int(row.get("acessos", 0))
        linhas += f"""<tr>
          <td><span class="status-pill" style="background:{pill["bg"]};border:1px solid {pill["border"]};color:{pill["color"]}">{pill["icon"]} {status}</span></td>
          <td style="font-weight:600">{cliente}</td>
          <td style="font-family:monospace;color:#60a5fa">{pedido}</td>
          <td style="font-family:monospace;color:#a78bfa">{phoenix}</td>
          <td style="text-align:center;color:#94a3b8">{acessos}</td>
        </tr>"""

    html = f"""<div style="background:#1a1f2e;border-radius:12px;border:1px solid #2d3748;overflow:hidden;margin-top:8px">
    <table class="pedidos-table">
      <thead><tr>
        <th style="width:140px">Status</th>
        <th>Razão Social</th>
        <th>Nº Pedido</th>
        <th>Phoenix</th>
        <th style="text-align:center">Acessos</th>
      </tr></thead>
      <tbody>{linhas}</tbody>
    </table></div>"""

    st.markdown(html, unsafe_allow_html=True)

def main():
    st.markdown("""
    <div class="header-vendas">
      <div>
        <p class="header-title">📋 TRAMITAÇÃO ATUAL — CONNECT GROUP</p>
        <p class="header-sub">TIM Corporate · Novos e Aditivos · Março/2026</p>
      </div>
      <div class="header-badge">🔵 TRAMITAÇÃO</div>
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
    kanban_column(df[df["status_dash"] == "PRE-VENDA"],  "PRE-VENDA",  k1)
    kanban_column(df[df["status_dash"] == "EM ANALISE"], "EM ANALISE", k2)
    kanban_column(df[df["status_dash"] == "CREDITO"],    "CREDITO",    k3)
    kanban_column(df[df["status_dash"] == "DEVOLVIDOS"], "DEVOLVIDOS", k4)
    kanban_column(
        df[(df["status_dash"] == "ENTRANTE") & df["mes_ativacao"].isna()],
        "ENTRANTE", k5, label="ENTRANTE NÃO ATIVO"
    )

    render_pedidos_tramitacao(df, raw)

    st.markdown('<p class="section-title">📋 Dados Completos</p>', unsafe_allow_html=True)
    with st.expander("Ver todos os registros filtrados"):
        cols = [c for c in ["razao_social","parceiro","tipo_contratacao","fila_atual",
                             "status_dash","acessos","preco_oferta","mes_ativacao","mes_input"]
                if c in df.columns]
        st.dataframe(df[cols], use_container_width=True, hide_index=True)

main()
