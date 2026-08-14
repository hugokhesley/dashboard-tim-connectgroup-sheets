import streamlit as st
from datetime import datetime

MESES_PT = {
    '01':'Janeiro','02':'Fevereiro','03':'Março','04':'Abril',
    '05':'Maio','06':'Junho','07':'Julho','08':'Agosto',
    '09':'Setembro','10':'Outubro','11':'Novembro','12':'Dezembro'
}
import pandas as pd
from data_loader import (
    load_data, apply_filters, get_parceiros,
    STATUS_COLORS,
    registrar_acesso
)
from auth import require_login
from ui import aplicar_estilo_base

st.set_page_config(
    page_title="Connect Group | Pós Venda",
    page_icon="🔄",
    layout="wide",
    initial_sidebar_state="expanded"
)

username = require_login("pos_venda")
aplicar_estilo_base()
registrar_acesso("pos_venda", username=username)

MES_ATUAL = datetime.now().strftime("%m/%Y")
META_RENEG = 751

st.markdown("""
<style>
  .header-reneg {
    background: linear-gradient(135deg, #064e3b 0%, #065f46 40%, #059669 70%, #10b981 100%);
    border-radius: 16px; padding: 28px 36px; margin-bottom: 28px;
    box-shadow: 0 8px 32px rgba(16,185,129,0.3);
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
  .kpi-card.green::before  { background: linear-gradient(90deg, #10b981, #059669); }
  .kpi-card.teal::before   { background: linear-gradient(90deg, #14b8a6, #0d9488); }
  .kpi-card.amber::before  { background: linear-gradient(90deg, #f59e0b, #d97706); }
  .kpi-card.red::before    { background: linear-gradient(90deg, #ef4444, #dc2626); }
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
  .header-logo { height:44px;width:auto;object-fit:contain;mix-blend-mode:multiply;border-radius:6px; }
  .header-right { display:flex;align-items:center;gap:14px; }
  .section-title { font-size:0.75rem; text-transform:uppercase; letter-spacing:1.5px; color:#64748b; font-weight:600; margin:24px 0 12px 0; }
</style>
""", unsafe_allow_html=True)



def get_vendedores(df: pd.DataFrame) -> list:
    """Retorna lista de vendedores únicos do DadosRadar."""
    from data_loader import normalize_columns, _s
    df_n = normalize_columns(df[df["_aba"] == "DadosRadar"].copy()) if "_aba" in df.columns else normalize_columns(df.copy())
    if "vendedor" in df_n.columns:
        vals = sorted([v for v in df_n["vendedor"].dropna().unique() if _s(v)])
        return ["Todos"] + vals
    return ["Todos"]

def progress_html(value, total, color="#10b981"):
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


def main():
    mes_str = MESES_PT.get(datetime.now().strftime("%m"), "") + "/" + datetime.now().strftime("%Y")
    st.markdown("""
    <div class="header-reneg">
      <div>
        <p class="header-title">🔄 GESTÃO DE RENEGOCIAÇÕES — CONNECT GROUP</p>
        <p class="header-sub">TIM Corporate · Retenção & Renegociação · {mes_str}</p>
      </div>
      <div class="header-right">
        <img src="https://raw.githubusercontent.com/hugokhesley/dashboard-tim-connectgroup-sheets/main/logo.png" class="header-logo" onerror="this.style.display='none'">
        <span class="header-badge">🟢 RENEGOCIAÇÃO</span>
      </div>
    </div>
    </div>""", unsafe_allow_html=True)

    with st.spinner("Carregando dados do Google Sheets..."):
        raw = load_data()

    if raw.empty:
        st.warning("⚠️ Nenhum dado encontrado. Verifique a conexão com o Google Sheets.")
        st.stop()

    def gerar_meses_opcoes():
        hoje = datetime.now()
        meses = []
        for i in range(6):
            m = hoje.month - i
            a = hoje.year
            while m <= 0:
                m += 12
                a -= 1
            meses.append(f"{m:02d}/{a}")
        return meses

    with st.sidebar:
        st.markdown("### 🔧 Filtros")

        meses_opcoes = gerar_meses_opcoes()
        mes_labels   = [MESES_PT.get(m[:2], m[:2]) + "/" + m[3:] for m in meses_opcoes]
        mes_idx      = st.selectbox("📅 Mês de referência", range(len(meses_opcoes)),
                                    format_func=lambda i: mes_labels[i], index=0)
        MES_ALVO = meses_opcoes[mes_idx]

        parceiro_sel = st.selectbox("Parceiro / Aba", get_parceiros(raw))
        vendedor_sel = st.selectbox("Vendedor", st.session_state.get("vendedores_disp", ["Todos"]))
        st.markdown("---")
        if st.button("🔄 Atualizar dados"):
            st.cache_data.clear()
            st.rerun()
        st.markdown("---")
        st.markdown(f"**Mês:** `{MES_ALVO}`")
        st.markdown(f"**Meta Reneg:** `{META_RENEG}` acessos")
        st.caption("Dados via Google Sheets · cache 3 min")

    df = apply_filters(raw.copy(), MES_ALVO, ["RENEGOCIAÇÃO", "RENEGOCIACAO"], parceiro_sel)

    # Lista de vendedores apenas com renegociações no mês (exclui zerados)
    from data_loader import _s
    if "vendedor" in df.columns:
        vendedores_disp = ["Todos"] + sorted([
            v for v in df["vendedor"].dropna().unique() if _s(v)
        ])
    else:
        vendedores_disp = ["Todos"]
    st.session_state["vendedores_disp"] = vendedores_disp

    if vendedor_sel != "Todos" and "vendedor" in df.columns:
        df = df[df["vendedor"].apply(lambda x: _s(x).upper()) == vendedor_sel.upper()]

    ativados    = df[df["mes_ativacao"] == MES_ALVO]
    vol_ativado = int(ativados["acessos"].sum())
    receita     = ativados["preco_oferta"].sum()
    pipeline    = int(df[df["mes_ativacao"].isna()]["acessos"].sum())
    faltam      = max(META_RENEG - vol_ativado, 0)
    pct         = min(int(vol_ativado / META_RENEG * 100), 100) if META_RENEG else 0

    st.markdown('<p class="section-title">📈 KPIs do Mês</p>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""<div class="kpi-card green">
          <div class="kpi-label">Volume Ativado</div>
          <div class="kpi-value">{vol_ativado:,}</div>
          <div class="kpi-sub">Meta: {META_RENEG} acessos</div>
          {progress_html(vol_ativado, META_RENEG)}
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class="kpi-card teal">
          <div class="kpi-label">Receita Ativa</div>
          <div class="kpi-value">R$ {receita:,.2f}</div>
          <div class="kpi-sub">{pct}% da meta atingida</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""<div class="kpi-card amber">
          <div class="kpi-label">Em Pipeline</div>
          <div class="kpi-value">{pipeline:,}</div>
          <div class="kpi-sub">sem data de ativação</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""<div class="kpi-card red">
          <div class="kpi-label">Faltam p/ Meta</div>
          <div class="kpi-value">{faltam:,}</div>
          <div class="kpi-sub">120% da meta de vendas</div>
        </div>""", unsafe_allow_html=True)

    st.markdown('<p class="section-title">🗂️ Kanban de Tramitação</p>', unsafe_allow_html=True)
    k1, k2, k3, k4, k5 = st.columns(5)
    kanban_column(df[df["status_dash"] == "PRE-VENDA"],   "PRE-VENDA",   k1)
    kanban_column(df[df["status_dash"] == "EM ANALISE"], "EM ANALISE", k2)
    kanban_column(df[df["status_dash"] == "CREDITO"],    "CREDITO",    k3)
    kanban_column(df[df["status_dash"] == "DEVOLVIDOS"], "DEVOLVIDOS", k4)
    kanban_column(
        df[(df["status_dash"] == "ENTRANTE") & df["mes_ativacao"].isna()],
        "ENTRANTE", k5, label="ENTRANTE NÃO ATIVO"
    )

    st.markdown('<p class="section-title">📋 Dados Completos</p>', unsafe_allow_html=True)
    with st.expander("Ver todos os registros filtrados"):
        cols = [c for c in ["razao_social","parceiro","tipo_contratacao","fila_atual",
                             "status_dash","acessos","preco_oferta","mes_ativacao","mes_input"]
                if c in df.columns]
        st.dataframe(df[cols], use_container_width=True, hide_index=True)

main()
