import streamlit as st
import pandas as pd
from datetime import datetime, date
from data_loader import (
    load_data, apply_filters, get_parceiros,
    load_bko, _s, _to_num, _norm_pedido
)
from auth import require_password

st.set_page_config(
    page_title="Connect Group | Atividade Comercial",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded"
)

require_password("atividade", "Atividade Comercial — Connect Group")

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
  html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
  .stApp { background-color: #0f1117; color: #e2e8f0; }
  .header-atv {
    background: linear-gradient(135deg, #1e1b4b 0%, #3730a3 50%, #6366f1 100%);
    border-radius: 16px; padding: 28px 36px; margin-bottom: 28px;
    box-shadow: 0 8px 32px rgba(99,102,241,0.3);
    border: 1px solid rgba(255,255,255,0.08);
    display: flex; align-items: center; justify-content: space-between;
  }
  .header-title { font-size: 1.9rem; font-weight: 800; color: #fff; letter-spacing: -0.5px; margin: 0; }
  .header-sub   { font-size: 0.85rem; color: rgba(255,255,255,0.65); margin: 4px 0 0 0; }
  .header-badge { background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.25); border-radius: 20px; padding: 6px 16px; font-size: 0.8rem; color: #fff; font-weight: 600; }
  .kpi-card { background: #1a1f2e; border-radius: 14px; padding: 22px 24px; border: 1px solid #2d3748; position: relative; overflow: hidden; margin-bottom: 4px; }
  .kpi-card::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; }
  .kpi-card.indigo::before { background: linear-gradient(90deg, #6366f1, #4f46e5); }
  .kpi-card.green::before  { background: linear-gradient(90deg, #10b981, #059669); }
  .kpi-card.amber::before  { background: linear-gradient(90deg, #f59e0b, #d97706); }
  .kpi-card.blue::before   { background: linear-gradient(90deg, #3b82f6, #1d4ed8); }
  .kpi-card.red::before    { background: linear-gradient(90deg, #ef4444, #dc2626); }
  .kpi-label { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 1px; color: #94a3b8; font-weight: 600; margin-bottom: 8px; }
  .kpi-value { font-size: 2.1rem; font-weight: 800; color: #f1f5f9; line-height: 1; }
  .kpi-sub   { font-size: 0.78rem; color: #64748b; margin-top: 6px; }
  .section-title { font-size:0.75rem; text-transform:uppercase; letter-spacing:1.5px; color:#6366f1; font-weight:700; margin:24px 0 12px 0; border-left: 3px solid #6366f1; padding-left: 10px; }
  .day-bar-wrap { margin: 3px 0 8px 0; }
  .day-label { font-size: 0.78rem; color: #e2e8f0; margin-bottom: 3px; display:flex; justify-content:space-between; }
  .day-bg    { background: #2d3748; border-radius: 99px; height: 12px; }
  .day-fill  { height: 12px; border-radius: 99px; }
  .hoje-badge { background: #6366f1; color: #fff; font-size: 0.65rem; font-weight: 700; padding: 1px 6px; border-radius: 4px; margin-left: 6px; }
  section[data-testid="stSidebar"] { background: #0d0e1f !important; }
  details { background:#1a1f2e !important; border:1px solid #2d3748 !important; border-radius:0 0 10px 10px !important; }
  details summary { color:#e2e8f0 !important; font-weight:600 !important; }
</style>
""", unsafe_allow_html=True)


def _parse_dates(df: pd.DataFrame, col: str) -> pd.Series:
    """Converte coluna de data para datetime."""
    return pd.to_datetime(df[col].apply(_s), dayfirst=True, errors="coerce")


def _bar(valor, maximo, cor="#6366f1", h=12):
    pct = min(int(valor / maximo * 100), 100) if maximo > 0 else 0
    return f'<div class="day-bg"><div class="day-fill" style="width:{pct}%;background:{cor};height:{h}px"></div></div>'


def main():
    st.markdown("""
    <div class="header-atv">
      <div>
        <p class="header-title">📅 ATIVIDADE COMERCIAL DIÁRIA</p>
        <p class="header-sub">TIM Corporate · Input e Ativação · Novos e Aditivos</p>
      </div>
      <div class="header-badge">🟣 ATIVIDADE</div>
    </div>""", unsafe_allow_html=True)

    with st.spinner("Carregando dados..."):
        raw = load_data()
        bko = load_bko()

    if raw.empty:
        st.warning("⚠️ Nenhum dado encontrado.")
        st.stop()

    # ── Sidebar ──────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 🔧 Filtros")
        parceiro_sel = st.selectbox("Parceiro / Aba", get_parceiros(raw))

        # Seletor de mês
        hoje = date.today()
        meses_disp = []
        for ano in [2025, 2026]:
            for mes in range(1, 13):
                meses_disp.append(f"{mes:02d}/{ano}")
        mes_atual = f"{hoje.month:02d}/{hoje.year}"
        idx_mes = meses_disp.index(mes_atual) if mes_atual in meses_disp else 0
        mes_sel = st.selectbox("Mês", meses_disp, index=idx_mes)

        st.markdown("---")
        if st.button("🔄 Atualizar dados"):
            st.cache_data.clear()
            st.rerun()
        st.markdown("---")
        st.caption("Dados via Google Sheets · cache 3 min")

    # ── Prepara dados ─────────────────────────────────────────────────────────
    # Filtra NOVO e ADITIVO sem filtro de mês (apply_filters filtra por ativação,
    # aqui precisamos também dos sem ativação para o input)
    from data_loader import normalize_columns, _dedup_columns
    df_base = normalize_columns(raw.copy())
    df_base = _dedup_columns(df_base)

    # Filtra parceiro
    if parceiro_sel != "Todos" and "parceiro" in df_base.columns:
        df_base = df_base[df_base["parceiro"].apply(lambda x: _s(x).upper() == parceiro_sel.upper())]

    # Filtra tipo
    if "tipo_contratacao" in df_base.columns:
        df_base = df_base[df_base["tipo_contratacao"].apply(lambda x: _s(x).upper() in ["NOVO", "ADITIVO"])]

    # Exclui cancelados
    if "fila_atual" in df_base.columns:
        df_base = df_base[~df_base["fila_atual"].apply(lambda x: _s(x).upper() == "CANCELADO")]

    for col in ["acessos", "preco_oferta"]:
        if col in df_base.columns:
            df_base[col] = df_base[col].apply(_to_num)

    # Parse datas
    mes_num, ano_num = int(mes_sel[:2]), int(mes_sel[3:])
    hoje_dt = pd.Timestamp(hoje)

    if "data_input" in df_base.columns:
        df_base["dt_input"] = _parse_dates(df_base, "data_input")
    else:
        df_base["dt_input"] = pd.NaT

    if "data_ativacao" in df_base.columns:
        df_base["dt_ativacao"] = _parse_dates(df_base, "data_ativacao")
    else:
        df_base["dt_ativacao"] = pd.NaT

    # Filtra pelo mês selecionado para input
    df_mes_input = df_base[
        (df_base["dt_input"].dt.month == mes_num) &
        (df_base["dt_input"].dt.year  == ano_num)
    ].copy()

    # Filtra pelo mês selecionado para ativação
    df_mes_atv = df_base[
        (df_base["dt_ativacao"].dt.month == mes_num) &
        (df_base["dt_ativacao"].dt.year  == ano_num)
    ].copy()

    # Join com BKO para ter vendedor real
    if not bko.empty and "pedido" in df_base.columns:
        df_base["pedido"]     = df_base["pedido"].apply(_norm_pedido)
        bk = bko.copy()
        bk["pedido"] = bk["pedido"].apply(_norm_pedido)
        df_mes_input = df_mes_input.merge(bk[["pedido","vendedor_real","lider"]], on="pedido", how="left")
        df_mes_atv   = df_mes_atv.merge(bk[["pedido","vendedor_real","lider"]], on="pedido", how="left")
        df_base      = df_base.merge(bk[["pedido","vendedor_real","lider"]], on="pedido", how="left")
        for d in [df_mes_input, df_mes_atv, df_base]:
            d["vendedor_real"] = d["vendedor_real"].apply(lambda x: _s(x) if _s(x) else "Sem Vendedor")
            d["lider"]         = d["lider"].apply(lambda x: _s(x) if _s(x) else "Sem Equipe")

    # ── KPIs do dia ───────────────────────────────────────────────────────────
    eh_mes_atual = (mes_num == hoje.month and ano_num == hoje.year)

    st.markdown('<p class="section-title">📊 KPIs do Dia</p>', unsafe_allow_html=True)

    if eh_mes_atual:
        df_hoje_input = df_mes_input[df_mes_input["dt_input"].dt.date == hoje]
        df_hoje_atv   = df_mes_atv[df_mes_atv["dt_ativacao"].dt.date == hoje]

        input_hoje_ac  = int(df_hoje_input["acessos"].sum())
        input_hoje_rec = df_hoje_input["preco_oferta"].sum()
        atv_hoje_ac    = int(df_hoje_atv["acessos"].sum())
        atv_hoje_rec   = df_hoje_atv["preco_oferta"].sum()
        input_hoje_ped = df_hoje_input["pedido"].nunique() if "pedido" in df_hoje_input.columns else 0

        k1, k2, k3, k4, k5 = st.columns(5)
        with k1:
            st.markdown(f"""<div class="kpi-card indigo">
              <div class="kpi-label">📥 Input Hoje — Pedidos</div>
              <div class="kpi-value">{input_hoje_ped}</div>
              <div class="kpi-sub">pedidos inseridos hoje</div>
            </div>""", unsafe_allow_html=True)
        with k2:
            st.markdown(f"""<div class="kpi-card indigo">
              <div class="kpi-label">📥 Input Hoje — Acessos</div>
              <div class="kpi-value">{input_hoje_ac:,}</div>
              <div class="kpi-sub">R$ {input_hoje_rec:,.2f}</div>
            </div>""", unsafe_allow_html=True)
        with k3:
            st.markdown(f"""<div class="kpi-card green">
              <div class="kpi-label">✅ Ativados Hoje</div>
              <div class="kpi-value">{atv_hoje_ac:,}</div>
              <div class="kpi-sub">R$ {atv_hoje_rec:,.2f}</div>
            </div>""", unsafe_allow_html=True)
        with k4:
            input_mes_ac = int(df_mes_input["acessos"].sum())
            st.markdown(f"""<div class="kpi-card blue">
              <div class="kpi-label">📥 Input Acumulado</div>
              <div class="kpi-value">{input_mes_ac:,}</div>
              <div class="kpi-sub">acessos no mês até hoje</div>
            </div>""", unsafe_allow_html=True)
        with k5:
            atv_mes_ac = int(df_mes_atv["acessos"].sum())
            st.markdown(f"""<div class="kpi-card amber">
              <div class="kpi-label">✅ Ativado Acumulado</div>
              <div class="kpi-value">{atv_mes_ac:,}</div>
              <div class="kpi-sub">acessos no mês até hoje</div>
            </div>""", unsafe_allow_html=True)
    else:
        # Mês histórico — só acumulado
        input_mes_ac  = int(df_mes_input["acessos"].sum())
        input_mes_rec = df_mes_input["preco_oferta"].sum()
        atv_mes_ac    = int(df_mes_atv["acessos"].sum())
        atv_mes_rec   = df_mes_atv["preco_oferta"].sum()
        input_mes_ped = df_mes_input["pedido"].nunique() if "pedido" in df_mes_input.columns else 0

        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.markdown(f"""<div class="kpi-card indigo">
              <div class="kpi-label">📥 Total Input — Pedidos</div>
              <div class="kpi-value">{input_mes_ped}</div>
              <div class="kpi-sub">pedidos no mês</div>
            </div>""", unsafe_allow_html=True)
        with k2:
            st.markdown(f"""<div class="kpi-card indigo">
              <div class="kpi-label">📥 Total Input — Acessos</div>
              <div class="kpi-value">{input_mes_ac:,}</div>
              <div class="kpi-sub">R$ {input_mes_rec:,.2f}</div>
            </div>""", unsafe_allow_html=True)
        with k3:
            st.markdown(f"""<div class="kpi-card green">
              <div class="kpi-label">✅ Total Ativado — Acessos</div>
              <div class="kpi-value">{atv_mes_ac:,}</div>
              <div class="kpi-sub">R$ {atv_mes_rec:,.2f}</div>
            </div>""", unsafe_allow_html=True)
        with k4:
            backlog = int(df_base[df_base["dt_ativacao"].isna()]["acessos"].sum())
            st.markdown(f"""<div class="kpi-card red">
              <div class="kpi-label">⏳ Backlog</div>
              <div class="kpi-value">{backlog:,}</div>
              <div class="kpi-sub">sem ativação ainda</div>
            </div>""", unsafe_allow_html=True)

    st.markdown("")

    # ── Tabs principais ───────────────────────────────────────────────────────
    st.markdown('<p class="section-title">📊 Análise Diária</p>', unsafe_allow_html=True)

    tab_input, tab_atv, tab_backlog = st.tabs([
        "📥 Input Diário", "✅ Ativação Diária", "⏳ Backlog (meses anteriores)"
    ])

    def _render_diario(df_d, col_data, cor_bar, cor_hoje, label):
        """Renderiza visão diária com toggle barras/tabela e linha de média."""
        if df_d.empty:
            st.info(f"Nenhum {label} encontrado para o período.")
            return

        diario = (df_d.groupby(df_d[col_data].dt.day)
                  .agg(acessos=("acessos","sum"), receita=("preco_oferta","sum"),
                       pedidos=("pedido","nunique") if "pedido" in df_d.columns else ("acessos","count"))
                  .reset_index().rename(columns={col_data:"dia"}))
        diario = diario.sort_values("dia")
        diario["acumulado"] = diario["acessos"].cumsum()

        n_dias     = len(diario)
        media_ac   = diario["acessos"].mean()
        media_rec  = diario["receita"].mean()
        total_ac   = int(diario["acessos"].sum())
        total_rec  = diario["receita"].sum()

        # Médias em destaque
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.markdown(f"""<div style="background:#1a1f2e;border-radius:10px;padding:12px 16px;border:1px solid #2d3748">
              <div style="font-size:0.68rem;color:#94a3b8;text-transform:uppercase;margin-bottom:4px">📊 Média/dia — Acessos</div>
              <div style="font-size:1.4rem;font-weight:800;color:{cor_bar}">{media_ac:.1f}</div>
              <div style="font-size:0.7rem;color:#64748b">{n_dias} dia(s) com {label}</div>
            </div>""", unsafe_allow_html=True)
        with m2:
            st.markdown(f"""<div style="background:#1a1f2e;border-radius:10px;padding:12px 16px;border:1px solid #2d3748">
              <div style="font-size:0.68rem;color:#94a3b8;text-transform:uppercase;margin-bottom:4px">💰 Média/dia — Receita</div>
              <div style="font-size:1.4rem;font-weight:800;color:{cor_bar}">R$ {media_rec:,.2f}</div>
              <div style="font-size:0.7rem;color:#64748b">por dia útil</div>
            </div>""", unsafe_allow_html=True)
        with m3:
            st.markdown(f"""<div style="background:#1a1f2e;border-radius:10px;padding:12px 16px;border:1px solid #2d3748">
              <div style="font-size:0.68rem;color:#94a3b8;text-transform:uppercase;margin-bottom:4px">📈 Total Acessos</div>
              <div style="font-size:1.4rem;font-weight:800;color:#e2e8f0">{total_ac:,}</div>
              <div style="font-size:0.7rem;color:#64748b">no período</div>
            </div>""", unsafe_allow_html=True)
        with m4:
            st.markdown(f"""<div style="background:#1a1f2e;border-radius:10px;padding:12px 16px;border:1px solid #2d3748">
              <div style="font-size:0.68rem;color:#94a3b8;text-transform:uppercase;margin-bottom:4px">💰 Total Receita</div>
              <div style="font-size:1.4rem;font-weight:800;color:#e2e8f0">R$ {total_rec:,.2f}</div>
              <div style="font-size:0.7rem;color:#64748b">no período</div>
            </div>""", unsafe_allow_html=True)

        st.markdown("")

        # Toggle de visualização
        viz = st.radio("Visualização:", ["📊 Barras", "📋 Tabela"],
                       horizontal=True, key=f"viz_{label}")

        max_ac = diario["acessos"].max()

        if viz == "📊 Barras":
            html_dias = ""
            for _, row in diario.iterrows():
                dia     = int(row["dia"])
                eh_hj   = (eh_mes_atual and dia == hoje.day)
                badge   = '<span class="hoje-badge">HOJE</span>' if eh_hj else ""
                cor     = cor_hoje if eh_hj else cor_bar
                # Linha de média como referência visual
                pct_med = min(int(media_ac / max_ac * 100), 100) if max_ac > 0 else 0
                acima   = "▲" if row["acessos"] >= media_ac else "▼"
                cor_cmp = "#10b981" if row["acessos"] >= media_ac else "#ef4444"
                html_dias += f"""
                <div class="day-bar-wrap">
                  <div class="day-label">
                    <span>Dia {dia:02d}{badge}
                      <span style="font-size:0.68rem;color:{cor_cmp};margin-left:6px">{acima} vs média</span>
                    </span>
                    <span style="font-weight:700;color:#e2e8f0">
                      {int(row['acessos'])} ac.
                      <span style="color:#64748b;font-weight:400"> · R$ {row['receita']:,.2f} · acum. {int(row['acumulado'])}</span>
                    </span>
                  </div>
                  <div style="position:relative">
                    {_bar(row['acessos'], max_ac, cor)}
                    <div style="position:absolute;top:0;left:{pct_med}%;width:2px;height:12px;background:#f59e0b;opacity:0.8"></div>
                  </div>
                </div>"""
            st.markdown(
                f'<div style="max-height:500px;overflow-y:auto;padding-right:8px">'
                f'<div style="font-size:0.68rem;color:#f59e0b;margin-bottom:8px">🟡 Linha amarela = média de {media_ac:.1f} ac./dia</div>'
                f'{html_dias}</div>',
                unsafe_allow_html=True
            )
        else:
            # Visão tabela
            df_tab = diario.copy()
            df_tab.columns = ["Dia","Acessos","R$","Pedidos","Acumulado"]
            df_tab["vs Média"] = df_tab["Acessos"].apply(
                lambda x: f"▲ +{x-media_ac:.0f}" if x >= media_ac else f"▼ {x-media_ac:.0f}"
            )
            st.dataframe(df_tab, use_container_width=True, hide_index=True,
                column_config={
                    "Dia":       st.column_config.NumberColumn("Dia", format="%d"),
                    "Acessos":   st.column_config.NumberColumn(format="%d"),
                    "Pedidos":   st.column_config.NumberColumn(format="%d"),
                    "Acumulado": st.column_config.NumberColumn(format="%d"),
                    "R$":        st.column_config.NumberColumn(format="R$ %.2f"),
                })

        # Detalhe por vendedor/dia
        st.markdown("")
        with st.expander("📋 Ver detalhe por vendedor/dia", expanded=False):
            det = (df_d.groupby([df_d[col_data].dt.day, "vendedor_real"])
                   .agg(acessos=("acessos","sum"), receita=("preco_oferta","sum"),
                        pedidos=("pedido","nunique") if "pedido" in df_d.columns else ("acessos","count"))
                   .reset_index().rename(columns={col_data:"dia"}))
            det.columns = ["Dia","Vendedor","Acessos","R$","Pedidos"]
            st.dataframe(det.sort_values(["Dia","Acessos"], ascending=[True,False]),
                         use_container_width=True, hide_index=True,
                         column_config={
                             "Acessos": st.column_config.NumberColumn(format="%d"),
                             "Pedidos": st.column_config.NumberColumn(format="%d"),
                             "R$":      st.column_config.NumberColumn(format="R$ %.2f"),
                         })

    with tab_input:
        _render_diario(df_mes_input, "dt_input", "#6366f1", "#a78bfa", "input")

    with tab_atv:
        _render_diario(df_mes_atv, "dt_ativacao", "#10b981", "#34d399", "ativação")

    with tab_backlog:
        # BACKLOG CORRETO: pedidos cujo mês de input é DIFERENTE do mês analisado
        # e que ainda não foram ativados
        df_backlog = df_base[
            df_base["dt_ativacao"].isna() &
            (
                (df_base["dt_input"].dt.month != mes_num) |
                (df_base["dt_input"].dt.year  != ano_num)
            )
        ].copy()

        if df_backlog.empty:
            st.success("🎉 Sem backlog de meses anteriores!")
        else:
            total_bl = int(df_backlog["acessos"].sum())
            n_ped    = df_backlog["pedido"].nunique() if "pedido" in df_backlog.columns else len(df_backlog)

            # KPIs backlog
            b1, b2, b3 = st.columns(3)
            with b1:
                st.markdown(f"""<div style="background:#1a1f2e;border-radius:10px;padding:14px 20px;border:1px solid #2d3748">
                  <div style="font-size:0.68rem;color:#94a3b8;text-transform:uppercase">⏳ Total Backlog</div>
                  <div style="font-size:1.8rem;font-weight:800;color:#f59e0b">{total_bl:,} ac.</div>
                </div>""", unsafe_allow_html=True)
            with b2:
                st.markdown(f"""<div style="background:#1a1f2e;border-radius:10px;padding:14px 20px;border:1px solid #2d3748">
                  <div style="font-size:0.68rem;color:#94a3b8;text-transform:uppercase">📋 Pedidos</div>
                  <div style="font-size:1.8rem;font-weight:800;color:#f59e0b">{n_ped}</div>
                </div>""", unsafe_allow_html=True)
            with b3:
                meses_bl = df_backlog["dt_input"].dt.strftime("%m/%Y").dropna().unique()
                st.markdown(f"""<div style="background:#1a1f2e;border-radius:10px;padding:14px 20px;border:1px solid #2d3748">
                  <div style="font-size:0.68rem;color:#94a3b8;text-transform:uppercase">📅 Meses de Origem</div>
                  <div style="font-size:1rem;font-weight:700;color:#f59e0b">{' · '.join(sorted(meses_bl))}</div>
                </div>""", unsafe_allow_html=True)

            st.markdown("")

            # Por vendedor
            if "vendedor_real" in df_backlog.columns:
                por_vend = (df_backlog.groupby("vendedor_real")
                            .agg(acessos=("acessos","sum"),
                                 pedidos=("pedido","nunique"),
                                 receita=("preco_oferta","sum"))
                            .reset_index().sort_values("acessos", ascending=False))

                for _, row in por_vend.iterrows():
                    with st.expander(
                        f"👤 {row['vendedor_real']} — {int(row['acessos'])} ac. · {int(row['pedidos'])} pedido(s) · R$ {row['receita']:,.2f}",
                        expanded=False
                    ):
                        df_vend_bl = df_backlog[df_backlog["vendedor_real"] == row["vendedor_real"]]
                        cols_show  = [c for c in ["pedido","razao_social","fila_atual","acessos","preco_oferta","dt_input"] if c in df_vend_bl.columns]
                        df_show    = df_vend_bl[cols_show].copy()
                        if "dt_input" in df_show.columns:
                            df_show["dt_input"] = df_show["dt_input"].dt.strftime("%d/%m/%Y")
                        st.dataframe(df_show.sort_values("acessos", ascending=False),
                                     use_container_width=True, hide_index=True,
                                     column_config={
                                         "pedido":       "Pedido",
                                         "razao_social": "Razão Social",
                                         "fila_atual":   "Fila Atual",
                                         "acessos":      st.column_config.NumberColumn("Acessos", format="%d"),
                                         "preco_oferta": st.column_config.NumberColumn("R$", format="R$ %.2f"),
                                         "dt_input":     "Data Input",
                                     })


main()
