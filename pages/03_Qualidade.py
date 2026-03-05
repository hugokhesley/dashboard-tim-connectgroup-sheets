import streamlit as st
import pandas as pd
from datetime import datetime
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
  section[data-testid="stSidebar"] { background: #130d24 !important; }
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=180)
def load_qualidade() -> pd.DataFrame:
    try:
        client = get_gspread_client()
        sheet_url = st.secrets["sheets_qualidade"]["url"]
        spreadsheet = client.open_by_url(sheet_url)
        # Tenta pelo nome exato, cai para primeira aba
        try:
            ws = spreadsheet.worksheet("BASE_SAFRAS_QUALIDADE")
        except Exception:
            ws = spreadsheet.worksheets()[0]
        all_values = ws.get_all_values()
        if not all_values or len(all_values) < 2:
            return pd.DataFrame()
        df = pd.DataFrame(all_values[1:], columns=all_values[0])
        df = _dedup_columns(df)
        # Remove linhas completamente vazias
        df = df[df.apply(lambda r: any(_s(v) for v in r), axis=1)].reset_index(drop=True)
        return df
    except Exception as e:
        st.error(f"Erro ao carregar planilha de qualidade: {e}")
        return pd.DataFrame()


def normalize_qual(df: pd.DataFrame) -> pd.DataFrame:
    df = _dedup_columns(df.copy())
    rename = {}
    for col in df.columns:
        n = _normalize(col)
        if n == "safra":                                rename[col] = "safra"
        elif "parceiro" in n:                           rename[col] = "parceiro"
        elif "custcode" in n:                           rename[col] = "custcode"
        elif "fatura" in n and "enviada" not in n and "atraso" not in n and ("n" in n or "numero" in n): rename[col] = "n_fatura"
        elif "cnpj" in n:                               rename[col] = "cnpj"
        elif "lider" in n or "líder" in n:              rename[col] = "lider"
        elif "cliente" in n and "contato" not in n:     rename[col] = "cliente"
        elif n == "venda":                              rename[col] = "venda"
        elif "consultor" in n:                          rename[col] = "consultor"
        elif "vencimento" in n:                         rename[col] = "vencimento"
        elif "valor" in n:                              rename[col] = "valor_rs"
        elif "ultima" in n and "analise" in n:          rename[col] = "ultima_analise"
        elif "contato" in n and "cliente" in n:         rename[col] = "contato_cliente"
        elif "fatura" in n and "enviada" in n:          rename[col] = "fatura_enviada"
        elif "observa" in n:                            rename[col] = "observacoes"
    df = df.rename(columns=rename)
    df = _dedup_columns(df)

    for col in ["safra", "parceiro", "cliente", "consultor", "lider", "cnpj",
                "contato_cliente", "fatura_enviada", "vencimento"]:
        if col in df.columns:
            df[col] = df[col].apply(_s)

    # Normaliza safra para MM/AAAA (aceita: out./25, out/25, 10/2025, 10/25)
    MESES = {"jan":"01","fev":"02","mar":"03","abr":"04","mai":"05","jun":"06",
             "jul":"07","ago":"08","set":"09","out":"10","nov":"11","dez":"12"}

    def _norm_safra(s):
        s = _s(s).lower().strip().rstrip(".")
        if not s:
            return s
        # Já está no formato MM/AAAA ou MM/AA
        import re
        m = re.match(r"^(\d{1,2})/(\d{2,4})$", s)
        if m:
            mes, ano = m.group(1).zfill(2), m.group(2)
            ano = "20" + ano if len(ano) == 2 else ano
            return f"{mes}/{ano}"
        # Formato textual: out./25, out/25, outubro/25
        m2 = re.match(r"^([a-záéíóúã]+)\.?/(\d{2,4})$", s)
        if m2:
            txt, ano = m2.group(1)[:3], m2.group(2)
            ano = "20" + ano if len(ano) == 2 else ano
            mes = MESES.get(txt, "??")
            return f"{mes}/{ano}"
        return _s(s)  # retorna como veio se não reconhecer

    if "safra" in df.columns:
        df["safra"] = df["safra"].apply(_norm_safra)

    if "venda" in df.columns:
        df["venda"] = df["venda"].apply(_to_num)
    if "valor_rs" in df.columns:
        df["valor_rs"] = df["valor_rs"].apply(_to_num)

    # Calcula coluna ADIMPLENTE com 3 estados baseado na data de vencimento
    hoje = pd.Timestamp(datetime.now().date())

    def _calc_adimplente(venc_str):
        v = _s(venc_str).strip()
        if not v:
            return "SIM"   # sem fatura em aberto
        try:
            # Tenta vários formatos de data
            for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y"]:
                try:
                    dt = pd.to_datetime(v, format=fmt)
                    return "GERADA" if dt >= hoje else "NÃO"
                except:
                    continue
            # Fallback genérico
            dt = pd.to_datetime(v, dayfirst=True, errors="coerce")
            if pd.isna(dt):
                return "SIM"
            return "GERADA" if dt >= hoje else "NÃO"
        except:
            return "SIM"

    df["adimplente"] = df["vencimento"].apply(_calc_adimplente) if "vencimento" in df.columns else "SIM"
    return df


def _bool_icon(val):
    v = _s(val).upper()
    if v.startswith("SIM"):                         return "✅"
    if v.startswith("NÃO") or v.startswith("NAO"): return "❌"
    if v:                                           return v
    return "—"


def _adim_icon(val):
    v = _s(val).upper()
    if v == "SIM":    return "🟢 SIM"
    if v == "NÃO" or v == "NAO": return "🔴 NÃO"
    if v == "GERADA": return "🟡 GERADA"
    return "—"


COLS_TABELA = ["safra","parceiro","cliente","cnpj","custcode","n_fatura","consultor","lider",
               "adimplente","venda","vencimento","valor_rs","ultima_analise",
               "contato_cliente","fatura_enviada","observacoes"]

COL_CONFIG = {
    "safra":          "Safra",
    "parceiro":       "Parceiro",
    "cliente":        "Cliente",
    "cnpj":           "CNPJ",
    "custcode":       "CustCode",
    "n_fatura":       "Nº Fatura",
    "consultor":      "Consultor",
    "lider":          "Líder",
    "adimplente":     "Adimplente?",
    "venda":          st.column_config.NumberColumn("Venda", format="%d"),
    "vencimento":     "Vencimento",
    "valor_rs":       st.column_config.NumberColumn("Valor R$", format="R$ %.2f"),
    "ultima_analise": "Última Análise P2B",
    "contato_cliente":"Contato?",
    "fatura_enviada": "Fatura Enviada?",
    "observacoes":    "Observações",
}


def _tabela(df):
    cols = [c for c in COLS_TABELA if c in df.columns]
    d = df[cols].copy()
    for col in ["contato_cliente", "fatura_enviada"]:
        if col in d.columns:
            d[col] = d[col].apply(_bool_icon)
    if "adimplente" in d.columns:
        d["adimplente"] = d["adimplente"].apply(_adim_icon)
    st.dataframe(d, use_container_width=True, hide_index=True, column_config=COL_CONFIG)


def _mask_inadim(df):
    """Retorna máscara booleana: True = NÃO adimplente (vencido)."""
    if "adimplente" in df.columns:
        return df["adimplente"].apply(lambda x: _s(x).upper() in ["NÃO", "NAO"])
    return pd.Series([False] * len(df))


def render_painel_geral(df: pd.DataFrame):
    st.markdown('<p class="section-title">📊 Visão Geral por Safra</p>', unsafe_allow_html=True)

    safras = sorted(df["safra"].dropna().unique()) if "safra" in df.columns else []
    rows = []
    for safra in safras:
        dfs    = df[df["safra"] == safra]
        total  = len(dfs)
        nao    = int(_mask_inadim(dfs).sum())
        gerada = int((dfs["adimplente"].apply(lambda x: _s(x).upper() == "GERADA")).sum()) if "adimplente" in dfs.columns else 0
        sim    = total - nao - gerada
        debito = dfs["valor_rs"].sum() if "valor_rs" in dfs.columns else 0
        pct    = round(sim / total * 100, 1) if total > 0 else 0
        rows.append({
            "Safra": safra, "Total": total,
            "🟢 Adimplentes": sim, "🟡 Gerada": gerada, "🔴 Vencidos": nao,
            "% Adimplência": pct, "Débito Total": debito,
        })

    if not rows:
        st.info("Nenhuma safra encontrada.")
        return

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True,
        column_config={
            "Safra":            st.column_config.TextColumn("Safra"),
            "Total":            st.column_config.NumberColumn("Total", format="%d"),
            "🟢 Adimplentes":   st.column_config.NumberColumn("🟢 Adimplentes", format="%d"),
            "🟡 Gerada":        st.column_config.NumberColumn("🟡 Gerada", format="%d"),
            "🔴 Vencidos":      st.column_config.NumberColumn("🔴 Vencidos", format="%d"),
            "% Adimplência":    st.column_config.ProgressColumn("% Adimplência", min_value=0, max_value=100, format="%.1f%%"),
            "Débito Total":     st.column_config.NumberColumn("Débito Total", format="R$ %.2f"),
        })

    # KPIs consolidados
    st.markdown('<p class="section-title">📈 KPIs Consolidados</p>', unsafe_allow_html=True)
    total_g  = len(df)
    nao_g    = int(_mask_inadim(df).sum())
    gerada_g = int((df["adimplente"].apply(lambda x: _s(x).upper() == "GERADA")).sum()) if "adimplente" in df.columns else 0
    sim_g    = total_g - nao_g - gerada_g
    debito_g = df["valor_rs"].sum() if "valor_rs" in df.columns else 0
    pct_g    = round(sim_g / total_g * 100, 1) if total_g > 0 else 0

    g1, g2, g3, g4 = st.columns(4)
    with g1:
        st.markdown(f"""<div class="kpi-card purple">
          <div class="kpi-label">👥 Total Geral</div>
          <div class="kpi-value">{total_g:,}</div>
          <div class="kpi-sub">em {len(safras)} safras</div>
        </div>""", unsafe_allow_html=True)
    with g2:
        st.markdown(f"""<div class="kpi-card green">
          <div class="kpi-label">🟢 Adimplentes</div>
          <div class="kpi-value">{sim_g:,}</div>
          <div class="kpi-sub">{pct_g}% do total</div>
        </div>""", unsafe_allow_html=True)
    with g3:
        st.markdown(f"""<div class="kpi-card red">
          <div class="kpi-label">🔴 Vencidos</div>
          <div class="kpi-value">{nao_g:,}</div>
          <div class="kpi-sub">{round(nao_g/total_g*100,1) if total_g else 0}% do total</div>
        </div>""", unsafe_allow_html=True)
    with g4:
        st.markdown(f"""<div class="kpi-card amber">
          <div class="kpi-label">💸 Débito Total</div>
          <div class="kpi-value">R$ {debito_g:,.2f}</div>
          <div class="kpi-sub">🟡 {gerada_g} faturas geradas</div>
        </div>""", unsafe_allow_html=True)


def render_safra_detalhe(df: pd.DataFrame, safra: str):
    dfs = df[df["safra"] == safra].copy() if safra != "Todas" else df.copy()

    total       = len(dfs)
    inadim_mask = _mask_inadim(dfs)
    nao         = int(inadim_mask.sum())
    gerada      = int((dfs["adimplente"].apply(lambda x: _s(x).upper() == "GERADA")).sum()) if "adimplente" in dfs.columns else 0
    sim         = total - nao - gerada
    pct         = round(sim / total * 100, 1) if total > 0 else 0
    debito      = dfs["valor_rs"].sum() if "valor_rs" in dfs.columns else 0
    sem_contato = dfs[inadim_mask & dfs["contato_cliente"].apply(
        lambda x: not _s(x).upper().startswith("SIM")
    )].shape[0] if "contato_cliente" in dfs.columns else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""<div class="kpi-card purple">
          <div class="kpi-label">👥 Total de Clientes</div>
          <div class="kpi-value">{total:,}</div>
          <div class="kpi-sub">safra {safra}</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class="kpi-card green">
          <div class="kpi-label">🟢 Adimplentes</div>
          <div class="kpi-value">{sim:,}</div>
          <div class="kpi-sub">{pct}% da safra · 🟡 {gerada} geradas</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""<div class="kpi-card red">
          <div class="kpi-label">🔴 Vencidos</div>
          <div class="kpi-value">{nao:,}</div>
          <div class="kpi-sub">R$ {debito:,.2f} em aberto</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""<div class="kpi-card amber">
          <div class="kpi-label">📵 Sem Contato</div>
          <div class="kpi-value">{sem_contato:,}</div>
          <div class="kpi-sub">inadimplentes sem contato</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("")

    tab1, tab2 = st.tabs(["📋 Todos os Clientes", "🔴 Vencidos"])

    with tab1:
        _tabela(dfs)

    with tab2:
        df_inadim = dfs[inadim_mask].copy()
        if df_inadim.empty:
            st.success("🎉 Nenhum cliente com fatura vencida!")
        else:
            _tabela(df_inadim)
            cols_export = [c for c in COLS_TABELA if c in df_inadim.columns]
            csv = df_inadim[cols_export].to_csv(index=False).encode("utf-8")
            st.download_button(
                label="⬇️ Exportar vencidos (.csv)",
                data=csv,
                file_name=f"vencidos_safra_{safra.replace('/','_')}.csv",
                mime="text/csv"
            )


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
        raw = load_qualidade()

    if raw.empty:
        st.warning("⚠️ Nenhum dado encontrado. Verifique se `[sheets_qualidade] url` está nos secrets.")
        st.stop()

    df = normalize_qual(raw)

    safras_disp   = sorted(df["safra"].dropna().unique().tolist())   if "safra"    in df.columns else []
    parceiros_disp = sorted(df["parceiro"].dropna().unique().tolist()) if "parceiro" in df.columns else []

    with st.sidebar:
        st.markdown("### 🔧 Filtros")

        visao = st.radio("Visão", ["Painel Geral", "Safra Específica"])

        safra_sel = "Todas"
        if visao == "Safra Específica":
            safra_sel = st.selectbox(
                "Safra", safras_disp,
                index=len(safras_disp)-1 if safras_disp else 0
            )

        parceiro_sel = st.selectbox("Parceiro", ["Todos"] + parceiros_disp)

        st.markdown("---")
        if st.button("🔄 Atualizar dados"):
            st.cache_data.clear()
            st.rerun()
        st.markdown("---")
        st.caption(f"**{len(safras_disp)} safras** carregadas")
        for s in safras_disp:
            st.markdown(f'<span class="safra-badge">{s}</span>', unsafe_allow_html=True)
        st.caption("Dados via Google Sheets · cache 3 min")

    if parceiro_sel != "Todos" and "parceiro" in df.columns:
        df = df[df["parceiro"] == parceiro_sel]

    if df.empty:
        st.warning("Nenhum dado para o filtro selecionado.")
        st.stop()

    if visao == "Painel Geral":
        render_painel_geral(df)
    else:
        st.markdown(f'<p class="section-title">🗓️ Safra: {safra_sel}</p>', unsafe_allow_html=True)
        render_safra_detalhe(df, safra_sel)


main()
