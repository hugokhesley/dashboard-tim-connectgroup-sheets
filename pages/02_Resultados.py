import streamlit as st
import pandas as pd
import unicodedata
from data_loader import get_gspread_client, _s, _to_num, _normalize, _dedup_columns

st.set_page_config(
    page_title="Connect Group | Resultados",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
  html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
  .stApp { background-color: #0f1117; color: #e2e8f0; }
  .header-res {
    background: linear-gradient(135deg, #1e1b4b 0%, #3730a3 50%, #6366f1 100%);
    border-radius: 16px; padding: 28px 36px; margin-bottom: 28px;
    box-shadow: 0 8px 32px rgba(99,102,241,0.3);
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
    background: #1a1f2e; border-radius: 14px; padding: 22px 24px;
    border: 1px solid #2d3748; position: relative; overflow: hidden; margin-bottom: 4px;
  }
  .kpi-card::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; }
  .kpi-card.indigo::before { background: linear-gradient(90deg, #6366f1, #4f46e5); }
  .kpi-card.green::before  { background: linear-gradient(90deg, #10b981, #059669); }
  .kpi-card.amber::before  { background: linear-gradient(90deg, #f59e0b, #d97706); }
  .kpi-card.purple::before { background: linear-gradient(90deg, #8b5cf6, #7c3aed); }
  .kpi-label { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 1px; color: #94a3b8; font-weight: 600; margin-bottom: 8px; }
  .kpi-value { font-size: 2.1rem; font-weight: 800; color: #f1f5f9; line-height: 1; }
  .kpi-sub   { font-size: 0.78rem; color: #64748b; margin-top: 6px; }
  section[data-testid="stSidebar"] { background: #111827 !important; }
  .section-title { font-size:0.75rem; text-transform:uppercase; letter-spacing:1.5px; color:#64748b; font-weight:600; margin:24px 0 12px 0; }
</style>
""", unsafe_allow_html=True)


TIPOS_DISPONIVEIS = ["NOVO", "ADITIVO", "RENEGOCIACAO"]


@st.cache_data(ttl=180)
def load_resultados():
    try:
        client = get_gspread_client()
        sheet_url = st.secrets["sheets"]["url"]
        spreadsheet = client.open_by_url(sheet_url)
        ws = spreadsheet.worksheet("resultados")
        all_values = ws.get_all_values()
        if not all_values or len(all_values) < 2:
            return pd.DataFrame()
        headers = all_values[0]
        rows = all_values[1:]
        df = pd.DataFrame(rows, columns=headers)
        df = _dedup_columns(df)
        df.columns = [_s(c).lower() for c in df.columns]
        df = _dedup_columns(df)
        return df
    except Exception as e:
        st.error(f"Erro ao carregar aba resultados: {e}")
        return pd.DataFrame()


def normalize_resultados(df):
    df = _dedup_columns(df)
    rename = {}
    for col in df.columns:
        n = _normalize(col)
        if n == "data de ativacao":    rename[col] = "data_ativacao"
        elif n == "razao social":      rename[col] = "razao_social"
        elif n == "tipo de contratacao": rename[col] = "tipo_contratacao"
        elif n == "acessos":           rename[col] = "acessos"
        elif n == "preco oferta":      rename[col] = "preco_oferta"
        elif n == "parceiro":          rename[col] = "parceiro"
        elif n == "fila atual":        rename[col] = "fila_atual"
    df = df.rename(columns=rename)
    df = _dedup_columns(df)
    for col in ["razao_social", "tipo_contratacao", "parceiro"]:
        if col in df.columns:
            df[col] = df[col].apply(_s)
    if "acessos" in df.columns:
        df["acessos"] = df["acessos"].apply(_to_num)
    if "preco_oferta" in df.columns:
        df["preco_oferta"] = df["preco_oferta"].apply(_to_num)
    if "data_ativacao" in df.columns:
        df["mes_ativacao"] = pd.to_datetime(
            df["data_ativacao"].apply(_s), dayfirst=True, errors="coerce"
        ).dt.strftime("%m/%Y")
    return df


def main():
    st.markdown("""
    <div class="header-res">
      <div>
        <p class="header-title">📊 RESULTADOS — CONNECT GROUP</p>
        <p class="header-sub">TIM Corporate · Análise Mensal de Ativações</p>
      </div>
      <div class="header-badge">📈 RESULTADOS</div>
    </div>""", unsafe_allow_html=True)

    with st.spinner("Carregando aba resultados..."):
        raw = load_resultados()

    if raw.empty:
        st.warning("Nenhum dado encontrado na aba 'resultados'. Verifique se a aba existe na planilha.")
        st.stop()

    df = normalize_resultados(raw.copy())

    # ── Sidebar filtros ──────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 🔧 Filtros")

        # Tipo de contratação
        tipos_norm = []
        if "tipo_contratacao" in df.columns:
            tipos_raw = sorted(df["tipo_contratacao"].apply(lambda x: _s(x).upper()).unique().tolist())
            tipos_raw = [t for t in tipos_raw if t]
        else:
            tipos_raw = TIPOS_DISPONIVEIS

        tipos_sel = st.multiselect(
            "Tipo de Contratação",
            options=tipos_raw,
            default=tipos_raw
        )

        # Parceiro
        parceiros = ["Todos"]
        if "parceiro" in df.columns:
            parceiros += sorted([_s(v) for v in df["parceiro"].unique() if _s(v)])
        parceiro_sel = st.selectbox("Parceiro", parceiros)

        # Mês
        meses = ["Todos"]
        if "mes_ativacao" in df.columns:
            meses_validos = sorted([m for m in df["mes_ativacao"].dropna().unique() if m != "NaT"])
            meses += meses_validos
        mes_sel = st.selectbox("Mês de Ativação", meses, index=len(meses)-1 if len(meses) > 1 else 0)

        st.markdown("---")
        if st.button("🔄 Atualizar dados"):
            st.cache_data.clear()
            st.rerun()
        st.caption("Dados via Google Sheets · cache 3 min")

    # ── Aplicar filtros ──────────────────────────────────────────────────
    dff = df.copy()

    if tipos_sel and "tipo_contratacao" in dff.columns:
        dff = dff[dff["tipo_contratacao"].apply(lambda x: _s(x).upper() in tipos_sel)]

    if parceiro_sel != "Todos" and "parceiro" in dff.columns:
        dff = dff[dff["parceiro"].apply(lambda x: _s(x) == parceiro_sel)]

    if mes_sel != "Todos" and "mes_ativacao" in dff.columns:
        dff = dff[dff["mes_ativacao"] == mes_sel]

    dff = _dedup_columns(dff.reset_index(drop=True))

    # ── KPIs ─────────────────────────────────────────────────────────────
    total_acessos  = int(dff["acessos"].sum())     if "acessos"      in dff.columns else 0
    total_receita  = dff["preco_oferta"].sum()      if "preco_oferta" in dff.columns else 0
    ticket_medio   = (total_receita / total_acessos) if total_acessos > 0 else 0
    total_clientes = dff["razao_social"].nunique()  if "razao_social" in dff.columns else 0

    st.markdown('<p class="section-title">📈 KPIs do Período</p>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""<div class="kpi-card indigo">
          <div class="kpi-label">🎯 Total de Acessos</div>
          <div class="kpi-value">{total_acessos:,}</div>
          <div class="kpi-sub">acessos ativados</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class="kpi-card green">
          <div class="kpi-label">💰 Receita Total</div>
          <div class="kpi-value">R$ {total_receita:,.2f}</div>
          <div class="kpi-sub">receita contratada</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""<div class="kpi-card amber">
          <div class="kpi-label">🎫 Ticket Médio</div>
          <div class="kpi-value">R$ {ticket_medio:,.2f}</div>
          <div class="kpi-sub">por acesso</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""<div class="kpi-card purple">
          <div class="kpi-label">🏢 Clientes</div>
          <div class="kpi-value">{total_clientes:,}</div>
          <div class="kpi-sub">razões sociais únicas</div>
        </div>""", unsafe_allow_html=True)

    # ── Gráfico evolução mensal ───────────────────────────────────────────
    if "mes_ativacao" in df.columns:
        st.markdown('<p class="section-title">📊 Evolução Mensal</p>', unsafe_allow_html=True)

        # Flag para escolher o que exibir
        metrica_graf = st.radio(
            "Exibir no gráfico:",
            ["Acessos", "Receita", "Ambos"],
            horizontal=True,
            label_visibility="collapsed"
        )

        # Agrupa por mês considerando filtros de tipo e parceiro (mas não de mês)
        df_graf = df.copy()
        if tipos_sel and "tipo_contratacao" in df_graf.columns:
            df_graf = df_graf[df_graf["tipo_contratacao"].apply(lambda x: _s(x).upper() in tipos_sel)]
        if parceiro_sel != "Todos" and "parceiro" in df_graf.columns:
            df_graf = df_graf[df_graf["parceiro"].apply(lambda x: _s(x) == parceiro_sel)]

        mensal = (df_graf.groupby("mes_ativacao", as_index=False)
                  .agg(Acessos=("acessos","sum"), Receita=("preco_oferta","sum"))
                  .dropna(subset=["mes_ativacao"]))

        # Ordena cronologicamente
        try:
            mensal["_dt"] = pd.to_datetime(mensal["mes_ativacao"], format="%m/%Y")
            mensal = mensal.sort_values("_dt").drop(columns=["_dt"])
        except Exception:
            mensal = mensal.sort_values("mes_ativacao")

        if not mensal.empty:
            import altair as alt

            if metrica_graf == "Acessos":
                chart = alt.Chart(mensal).mark_bar(color="#6366f1", cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                    x=alt.X("mes_ativacao:O", title="Mês", sort=None),
                    y=alt.Y("Acessos:Q", title="Acessos"),
                    tooltip=["mes_ativacao", "Acessos"]
                ).properties(height=280)

            elif metrica_graf == "Receita":
                chart = alt.Chart(mensal).mark_bar(color="#10b981", cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                    x=alt.X("mes_ativacao:O", title="Mês", sort=None),
                    y=alt.Y("Receita:Q", title="Receita (R$)"),
                    tooltip=["mes_ativacao", "Receita"]
                ).properties(height=280)

            else:  # Ambos
                base = alt.Chart(mensal).encode(x=alt.X("mes_ativacao:O", title="Mês", sort=None))
                bars = base.mark_bar(color="#6366f1", opacity=0.85, cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                    y=alt.Y("Acessos:Q", title="Acessos", axis=alt.Axis(titleColor="#6366f1")),
                    tooltip=["mes_ativacao","Acessos","Receita"]
                )
                line = base.mark_line(color="#10b981", strokeWidth=3, point=alt.OverlayMarkDef(color="#10b981", size=60)).encode(
                    y=alt.Y("Receita:Q", title="Receita (R$)", axis=alt.Axis(titleColor="#10b981"))
                )
                chart = alt.layer(bars, line).resolve_scale(y="independent").properties(height=280)

            st.altair_chart(
                chart.configure_view(fill="#1a1f2e")
                     .configure_axis(labelColor="#94a3b8", titleColor="#64748b", gridColor="#2d3748", domainColor="#2d3748"),
                use_container_width=True
            )
        else:
            st.info("Sem dados para exibir no gráfico.")

    # ── Tabela detalhada ──────────────────────────────────────────────────
    st.markdown('<p class="section-title">📋 Registros Ativados</p>', unsafe_allow_html=True)

    # Agrupado por parceiro
    col_tab1, col_tab2 = st.columns([1, 2])

    with col_tab1:
        st.caption("Por Parceiro")
        if "parceiro" in dff.columns:
            por_parceiro = (dff.groupby("parceiro", as_index=False)
                            .agg(Acessos=("acessos","sum"), Receita=("preco_oferta","sum"))
                            .sort_values("Acessos", ascending=False))
            st.dataframe(por_parceiro, use_container_width=True, hide_index=True,
                column_config={
                    "parceiro": "Parceiro",
                    "Acessos": st.column_config.NumberColumn("Acessos", format="%d"),
                    "Receita": st.column_config.NumberColumn("Receita", format="R$ %.2f"),
                })

    with col_tab2:
        st.caption("Detalhe por Cliente")
        cols_show = [c for c in ["razao_social","parceiro","tipo_contratacao","mes_ativacao","acessos","preco_oferta"]
                     if c in dff.columns]
        st.dataframe(dff[cols_show].sort_values("acessos", ascending=False) if "acessos" in dff.columns else dff[cols_show],
                     use_container_width=True, hide_index=True,
                     column_config={
                         "razao_social":     "Razão Social",
                         "parceiro":         "Parceiro",
                         "tipo_contratacao": "Tipo",
                         "mes_ativacao":     "Mês",
                         "acessos":          st.column_config.NumberColumn("Acessos", format="%d"),
                         "preco_oferta":     st.column_config.NumberColumn("Receita", format="R$ %.2f"),
                     })

main()
