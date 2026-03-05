import streamlit as st
import pandas as pd
import unicodedata
from data_loader import _s, _to_num, _normalize, _dedup_columns, get_gspread_client

st.set_page_config(
    page_title="Connect Group | Qualidade",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
  html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
  .stApp { background-color: #0f1117; color: #e2e8f0; }
  .header-qual {
    background: linear-gradient(135deg, #1a0533 0%, #4a1272 50%, #7c3aed 100%);
    border-radius: 16px; padding: 28px 36px; margin-bottom: 28px;
    box-shadow: 0 8px 32px rgba(124,58,237,0.35);
    border: 1px solid rgba(255,255,255,0.08);
    display: flex; align-items: center; justify-content: space-between;
  }
  .header-title { font-size: 1.9rem; font-weight: 800; color: #fff; margin: 0; }
  .header-sub   { font-size: 0.85rem; color: rgba(255,255,255,0.65); margin: 4px 0 0 0; }
  .header-badge {
    background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.25);
    border-radius: 20px; padding: 6px 16px; font-size: 0.8rem; color: #fff; font-weight: 600;
  }
  .kpi-card {
    background: #1a1230; border-radius: 14px; padding: 22px 24px;
    border: 1px solid #2d1f4e; position: relative; overflow: hidden; margin-bottom: 4px;
  }
  .kpi-card::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; }
  .kpi-card.purple::before { background: linear-gradient(90deg, #7c3aed, #6d28d9); }
  .kpi-card.green::before  { background: linear-gradient(90deg, #10b981, #059669); }
  .kpi-card.red::before    { background: linear-gradient(90deg, #ef4444, #dc2626); }
  .kpi-card.amber::before  { background: linear-gradient(90deg, #f59e0b, #d97706); }
  .kpi-label { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 1px; color: #a78bfa; font-weight: 600; margin-bottom: 8px; }
  .kpi-value { font-size: 2.1rem; font-weight: 800; color: #f1f5f9; line-height: 1; }
  .kpi-sub   { font-size: 0.78rem; color: #64748b; margin-top: 6px; }
  .section-title { font-size:0.75rem; text-transform:uppercase; letter-spacing:1.5px; color:#7c3aed; font-weight:700; margin:24px 0 12px 0; border-left: 3px solid #7c3aed; padding-left: 10px; }
  .safra-badge {
    display:inline-block; background:#2d1f4e; border:1px solid #7c3aed;
    border-radius:8px; padding:4px 12px; font-size:0.8rem; color:#a78bfa; font-weight:600; margin:2px;
  }
  .inadimplente-row { background: rgba(239,68,68,0.08) !important; }
  section[data-testid="stSidebar"] { background: #130d24 !important; }
  .stDataFrame { border-radius: 10px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)

MES_COLS = ["jan", "fev", "mar", "abr", "mai", "jun",
            "jul", "ago", "set", "out", "nov", "dez"]


@st.cache_data(ttl=180)
def load_qualidade():
    """Lê todas as abas da planilha de qualidade e retorna dict {safra: df}."""
    try:
        client = get_gspread_client()
        sheet_url = st.secrets["sheets_qualidade"]["url"]
        spreadsheet = client.open_by_url(sheet_url)
        safras = {}
        for ws in spreadsheet.worksheets():
            try:
                all_values = ws.get_all_values()
                if not all_values or len(all_values) < 2:
                    continue
                headers = all_values[0]
                rows = all_values[1:]
                df = pd.DataFrame(rows, columns=headers)
                df = _dedup_columns(df)
                df["_safra"] = ws.title.strip()
                safras[ws.title.strip()] = df
            except Exception as e:
                st.warning(f"Aba '{ws.title}' ignorada: {e}")
        return safras
    except Exception as e:
        st.error(f"Erro ao conectar planilha de qualidade: {e}")
        return {}


def normalize_qual(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza nomes de colunas para padrão interno."""
    df = _dedup_columns(df)
    rename = {}
    for col in df.columns:
        n = _normalize(col)
        if "parceiro" in n:                              rename[col] = "parceiro"
        elif "custcode" in n:                            rename[col] = "custcode"
        elif "cnpj" in n:                                rename[col] = "cnpj"
        elif "cliente" in n and "contato" not in n:      rename[col] = "cliente"
        elif n == "venda":                               rename[col] = "venda"
        elif "consultor" in n:                           rename[col] = "consultor"
        elif "fatura" in n and "atraso" in n:            rename[col] = "fatura_atraso"
        elif n == "debito" or "d\u00e9bito" in n or "debito" in n: rename[col] = "debito"
        elif "contato" in n and "cliente" in n:          rename[col] = "contato_cliente"
        elif "fatura" in n and "enviada" in n:           rename[col] = "fatura_enviada"
        elif "observa" in n:                             rename[col] = "observacoes"
    df = df.rename(columns=rename)
    df = _dedup_columns(df)
    # Normaliza valores booleanos
    for col in ["fatura_atraso", "contato_cliente", "fatura_enviada"]:
        if col in df.columns:
            df[col] = df[col].apply(_s)
    if "venda" in df.columns:
        df["venda"] = df["venda"].apply(_to_num)
    return df


def _bool_icon(val):
    v = _s(val).upper()
    if v.startswith("SIM"):  return "✅"
    if v.startswith("NÃO") or v.startswith("NAO"): return "❌"
    return "—"


def _mes_icon(val):
    v = _s(val).upper()
    if v == "OK":     return "✅"
    if v == "ATRASO": return "🔴"
    if v:             return v
    return "—"


def render_safra_summary(safras_data: dict):
    """Painel geral com resumo de todas as safras."""
    st.markdown('<p class="section-title">📊 Visão Geral por Safra</p>', unsafe_allow_html=True)

    rows = []
    for safra, df in safras_data.items():
        df_n = normalize_qual(df.copy())
        total = len(df_n)
        if total == 0:
            continue
        inadim = df_n[df_n.get("fatura_atraso", pd.Series(dtype=str)).apply(
            lambda x: _s(x).upper().startswith("SIM")
        )].shape[0] if "fatura_atraso" in df_n.columns else 0
        adim = total - inadim
        pct_adim = round(adim / total * 100, 1) if total > 0 else 0
        total_debito = 0
        rows.append({
            "Safra": safra,
            "Total Clientes": total,
            "Adimplentes": adim,
            "Inadimplentes": inadim,
            "% Adimplência": pct_adim,
        })

    if not rows:
        st.info("Nenhuma safra com dados encontrada.")
        return

    df_resumo = pd.DataFrame(rows)
    st.dataframe(
        df_resumo,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Safra":           st.column_config.TextColumn("Safra"),
            "Total Clientes":  st.column_config.NumberColumn("Total", format="%d"),
            "Adimplentes":     st.column_config.NumberColumn("✅ Adimplentes", format="%d"),
            "Inadimplentes":   st.column_config.NumberColumn("🔴 Inadimplentes", format="%d"),
            "% Adimplência":   st.column_config.ProgressColumn("% Adimplência", min_value=0, max_value=100, format="%.1f%%"),
        }
    )


def render_safra_detalhe(df_raw: pd.DataFrame, safra: str):
    """Detalhe de uma safra específica."""
    df = normalize_qual(df_raw.copy())

    # Detecta colunas de mês (datetime ou strings tipo 'OK')
    mes_cols_raw = [c for c in df_raw.columns if c not in [
        "PARCEIRO","CUSTCODE","CNPJ","CLIENTE","VENDA","CONSULTOR",
        "FATURA EM ATRASO?","DÉBITO","CONTATO COM CLIENTE?","FATURA ENVIADA?","OBSERVAÇÕES","_safra"
    ] and c not in df.columns.tolist()]

    # Também pega colunas que sobraram após normalização (são os meses)
    cols_base = {"parceiro","custcode","cnpj","cliente","venda","consultor",
                 "fatura_atraso","debito","contato_cliente","fatura_enviada","observacoes","_safra"}
    mes_cols_norm = [c for c in df.columns if c not in cols_base]

    total = len(df)
    inadim_mask = df["fatura_atraso"].apply(lambda x: _s(x).upper().startswith("SIM")) if "fatura_atraso" in df.columns else pd.Series([False]*total)
    inadim = inadim_mask.sum()
    adim   = total - inadim
    pct    = round(adim / total * 100, 1) if total > 0 else 0

    # KPIs
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""<div class="kpi-card purple">
          <div class="kpi-label">👥 Total de Clientes</div>
          <div class="kpi-value">{total}</div>
          <div class="kpi-sub">na safra {safra}</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class="kpi-card green">
          <div class="kpi-label">✅ Adimplentes</div>
          <div class="kpi-value">{adim}</div>
          <div class="kpi-sub">{pct}% da safra</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""<div class="kpi-card red">
          <div class="kpi-label">🔴 Inadimplentes</div>
          <div class="kpi-value">{inadim}</div>
          <div class="kpi-sub">{round(100-pct,1)}% da safra</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        sem_contato = df[inadim_mask & df["contato_cliente"].apply(
            lambda x: not _s(x).upper().startswith("SIM")
        )].shape[0] if "contato_cliente" in df.columns else 0
        st.markdown(f"""<div class="kpi-card amber">
          <div class="kpi-label">📵 Sem Contato</div>
          <div class="kpi-value">{sem_contato}</div>
          <div class="kpi-sub">inadimplentes sem contato</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("")

    # Tabs: Todos / Inadimplentes / Acompanhamento mensal
    tab1, tab2, tab3 = st.tabs(["📋 Todos os Clientes", "🔴 Inadimplentes", "📅 Acompanhamento Mensal"])

    with tab1:
        cols_show = [c for c in ["parceiro","cliente","cnpj","consultor","venda","fatura_atraso","debito","contato_cliente","fatura_enviada","observacoes"] if c in df.columns]
        df_show = df[cols_show].copy()
        # Aplica ícones
        for col in ["fatura_atraso","contato_cliente","fatura_enviada"]:
            if col in df_show.columns:
                df_show[col] = df_show[col].apply(_bool_icon)
        st.dataframe(df_show, use_container_width=True, hide_index=True,
            column_config={
                "parceiro":        "Parceiro",
                "cliente":         "Cliente",
                "cnpj":            "CNPJ",
                "consultor":       "Consultor",
                "venda":           st.column_config.NumberColumn("Venda", format="%d"),
                "fatura_atraso":   "Fatura Atraso?",
                "debito":          "Débito",
                "contato_cliente": "Contato?",
                "fatura_enviada":  "Fatura Enviada?",
                "observacoes":     "Observações",
            })

    with tab2:
        df_inadim = df[inadim_mask].copy() if inadim > 0 else pd.DataFrame()
        if df_inadim.empty:
            st.success("🎉 Nenhum cliente inadimplente nesta safra!")
        else:
            cols_show = [c for c in ["parceiro","cliente","cnpj","consultor","debito","contato_cliente","fatura_enviada","observacoes"] if c in df_inadim.columns]
            df_show = df_inadim[cols_show].copy()
            for col in ["contato_cliente","fatura_enviada"]:
                if col in df_show.columns:
                    df_show[col] = df_show[col].apply(_bool_icon)
            st.dataframe(df_show, use_container_width=True, hide_index=True,
                column_config={
                    "parceiro":        "Parceiro",
                    "cliente":         "Cliente",
                    "cnpj":            "CNPJ",
                    "consultor":       "Consultor",
                    "debito":          "Débito",
                    "contato_cliente": "Contato?",
                    "fatura_enviada":  "Fatura Enviada?",
                    "observacoes":     "Observações",
                })

            # Botão exportar CSV
            csv = df_inadim.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="⬇️ Exportar inadimplentes (.csv)",
                data=csv,
                file_name=f"inadimplentes_safra_{safra.replace('/','_')}.csv",
                mime="text/csv"
            )

    with tab3:
        if not mes_cols_norm:
            st.info("Nenhuma coluna de acompanhamento mensal encontrada.")
        else:
            cols_id = [c for c in ["parceiro","cliente"] if c in df.columns]
            df_mes = df[cols_id + mes_cols_norm].copy()
            for col in mes_cols_norm:
                df_mes[col] = df_mes[col].apply(_mes_icon)
            st.dataframe(df_mes, use_container_width=True, hide_index=True)


def main():
    st.markdown("""
    <div class="header-qual">
      <div>
        <p class="header-title">🔍 QUALIDADE — CONNECT GROUP</p>
        <p class="header-sub">TIM Corporate · Acompanhamento de Adimplência · 6 Meses por Safra</p>
      </div>
      <div class="header-badge">🟣 QUALIDADE</div>
    </div>""", unsafe_allow_html=True)

    with st.spinner("Carregando planilha de qualidade..."):
        safras = load_qualidade()

    if not safras:
        st.warning("""
        ⚠️ Nenhuma dado encontrado. Verifique:
        - Se a URL da planilha de qualidade está nos secrets: `[sheets_qualidade] url = ...`
        - Se a planilha tem pelo menos uma aba com dados
        """)
        st.stop()

    safras_disponiveis = sorted(safras.keys())

    # Sidebar
    with st.sidebar:
        st.markdown("### 🔧 Filtros")
        visao = st.radio("Visão", ["Painel Geral", "Safra Específica"], horizontal=False)

        if visao == "Safra Específica":
            safra_sel = st.selectbox("Selecionar Safra", safras_disponiveis,
                                      index=len(safras_disponiveis)-1)

        # Filtro parceiro (global)
        todos_parceiros = ["Todos"]
        for df in safras.values():
            df_n = normalize_qual(df.copy())
            if "parceiro" in df_n.columns:
                todos_parceiros += [_s(v) for v in df_n["parceiro"].unique() if _s(v)]
        todos_parceiros = ["Todos"] + sorted(set(todos_parceiros) - {"Todos"})
        parceiro_sel = st.selectbox("Parceiro", todos_parceiros)

        st.markdown("---")
        if st.button("🔄 Atualizar dados"):
            st.cache_data.clear()
            st.rerun()
        st.markdown("---")
        st.caption(f"**{len(safras_disponiveis)} safras** carregadas")
        for s in safras_disponiveis:
            st.markdown(f'<span class="safra-badge">{s}</span>', unsafe_allow_html=True)
        st.caption("Dados via Google Sheets · cache 3 min")

    # Aplica filtro de parceiro
    if parceiro_sel != "Todos":
        safras_filtradas = {}
        for safra, df in safras.items():
            df_n = normalize_qual(df.copy())
            if "parceiro" in df_n.columns:
                df_f = df[df_n["parceiro"].apply(lambda x: _s(x) == parceiro_sel)]
                if not df_f.empty:
                    safras_filtradas[safra] = df_f
        safras = safras_filtradas

    if not safras:
        st.warning("Nenhum dado para o parceiro selecionado.")
        st.stop()

    if visao == "Painel Geral":
        render_safra_summary(safras)

        # Mini KPIs globais
        st.markdown('<p class="section-title">📈 KPIs Consolidados</p>', unsafe_allow_html=True)
        total_global = sum(len(df) for df in safras.values())
        inadim_global = 0
        for df in safras.values():
            df_n = normalize_qual(df.copy())
            if "fatura_atraso" in df_n.columns:
                inadim_global += df_n["fatura_atraso"].apply(
                    lambda x: _s(x).upper().startswith("SIM")).sum()
        adim_global = total_global - inadim_global
        pct_global  = round(adim_global / total_global * 100, 1) if total_global > 0 else 0

        g1, g2, g3, g4 = st.columns(4)
        with g1:
            st.markdown(f"""<div class="kpi-card purple">
              <div class="kpi-label">👥 Total Geral</div>
              <div class="kpi-value">{total_global}</div>
              <div class="kpi-sub">em {len(safras)} safras</div>
            </div>""", unsafe_allow_html=True)
        with g2:
            st.markdown(f"""<div class="kpi-card green">
              <div class="kpi-label">✅ Total Adimplentes</div>
              <div class="kpi-value">{adim_global}</div>
              <div class="kpi-sub">{pct_global}% do total</div>
            </div>""", unsafe_allow_html=True)
        with g3:
            st.markdown(f"""<div class="kpi-card red">
              <div class="kpi-label">🔴 Total Inadimplentes</div>
              <div class="kpi-value">{inadim_global}</div>
              <div class="kpi-sub">{round(100-pct_global,1)}% do total</div>
            </div>""", unsafe_allow_html=True)
        with g4:
            st.markdown(f"""<div class="kpi-card amber">
              <div class="kpi-label">📅 Safras Ativas</div>
              <div class="kpi-value">{len(safras)}</div>
              <div class="kpi-sub">em acompanhamento</div>
            </div>""", unsafe_allow_html=True)

    else:
        st.markdown(f'<p class="section-title">🗓️ Safra: {safra_sel}</p>', unsafe_allow_html=True)
        if safra_sel in safras:
            render_safra_detalhe(safras[safra_sel], safra_sel)
        else:
            st.warning("Safra não encontrada após filtro de parceiro.")


main()
