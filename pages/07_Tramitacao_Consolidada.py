import streamlit as st
from datetime import datetime

MESES_PT = {
    '01':'Janeiro','02':'Fevereiro','03':'Março','04':'Abril',
    '05':'Maio','06':'Junho','07':'Julho','08':'Agosto',
    '09':'Setembro','10':'Outubro','11':'Novembro','12':'Dezembro'
}
import pandas as pd
from data_loader import (
    load_data, load_bko, load_metas, load_colaboradores,
    apply_filters, get_parceiros, _s, _to_num, _norm_pedido,
    registrar_acesso
)
from auth import require_login
from ui import aplicar_estilo_base
from regras import atingimento, largura_barra

st.set_page_config(
    page_title="Connect Group | Tramitação Consolidada",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

username = require_login("consolidada")
aplicar_estilo_base()
registrar_acesso("consolidada", username=username)

MES_ALVO = datetime.now().strftime("%m/%Y")

st.markdown("""
<style>
  .header-cons {
    background: linear-gradient(135deg, #064e3b 0%, #047857 50%, #10b981 100%);
    border-radius: 16px; padding: 24px 32px; margin-bottom: 24px;
    box-shadow: 0 8px 32px rgba(16,185,129,0.25);
    border: 1px solid rgba(255,255,255,0.08);
    display: flex; align-items: center; justify-content: space-between;
  }
  .header-title { font-size: 1.7rem; font-weight: 800; color: #fff; letter-spacing: -0.5px; margin: 0; }
  .header-sub   { font-size: 0.82rem; color: rgba(255,255,255,0.65); margin: 4px 0 0 0; }
  .header-badge { background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.25); border-radius: 20px; padding: 6px 16px; font-size: 0.8rem; color: #fff; font-weight: 600; }
  .header-logo { height:44px;width:auto;object-fit:contain;mix-blend-mode:multiply;border-radius:6px; }
  .header-right { display:flex;align-items:center;gap:14px; }
  .section-title { font-size:0.72rem; text-transform:uppercase; letter-spacing:1.5px; color:#10b981; font-weight:700; margin:20px 0 10px 0; border-left: 3px solid #10b981; padding-left: 10px; }
  section[data-testid="stSidebar"] { background: #0d1a0f !important; }
  .col-header { font-size:0.65rem; text-transform:uppercase; letter-spacing:1px; color:#64748b; font-weight:600; text-align:right; }
  .col-header:first-child { text-align:left; }
  .ating-card { background:#1a1f2e; border-radius:14px; padding:20px 24px; border:1px solid #2d3748; position:relative; overflow:hidden; }
  .ating-card::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; }
  .ating-card.green::before  { background: linear-gradient(90deg, #10b981, #059669); }
  .ating-card.amber::before  { background: linear-gradient(90deg, #f59e0b, #d97706); }
  .ating-card.red::before    { background: linear-gradient(90deg, #ef4444, #dc2626); }
  .ating-card.blue::before   { background: linear-gradient(90deg, #3b82f6, #1d4ed8); }
  .ating-label { font-size:0.68rem; text-transform:uppercase; letter-spacing:1px; color:#94a3b8; font-weight:600; margin-bottom:6px; }
  .ating-val   { font-size:1.8rem; font-weight:800; line-height:1; }
  .ating-sub   { font-size:0.75rem; color:#64748b; margin-top:6px; }
  .prog-bg   { background:#1e293b; border-radius:99px; height:14px; margin:8px 0 4px; overflow:hidden; }
  .prog-fill { height:14px; border-radius:99px; }
</style>
""", unsafe_allow_html=True)


ETAPAS_CONFIG = {
    "PRE-VENDA":          {"icon": "🔍", "cor": "#6366f1", "bg": "#1e1b4b22"},
    "EM ANALISE":         {"icon": "🔬", "cor": "#3b82f6", "bg": "#1e3a5f22"},
    "CREDITO":            {"icon": "💳", "cor": "#8b5cf6", "bg": "#2d1b6922"},
    "DEVOLVIDOS":         {"icon": "↩️",  "cor": "#ef4444", "bg": "#2d1b1b22"},
    "ENTRANTE NÃO ATIVO": {"icon": "⏳", "cor": "#f59e0b", "bg": "#2d220522"},
    "ATIVO":              {"icon": "✅", "cor": "#10b981", "bg": "#064e3b22"},
}

def _cor_pct(pct):
    if pct >= 100: return "#10b981"
    if pct >= 70:  return "#f59e0b"
    return "#ef4444"

def _bar(val, maximo, cor, h=12):
    pct = largura_barra(val, maximo)   # largura de barra: sempre presa em 100
    return f'<div class="prog-bg"><div class="prog-fill" style="width:{pct}%;background:{cor};height:{h}px"></div></div>'


def main():
    mes_str = MESES_PT.get(datetime.now().strftime("%m"), "") + "/" + datetime.now().strftime("%Y")
    st.markdown(f"""
    <div class="header-cons">
      <div>
        <p class="header-title">📊 TRAMITAÇÃO CONSOLIDADA — CONNECT GROUP</p>
        <p class="header-sub">TIM Corporate · Meta vs Realizado por Etapa · {mes_str}</p>
      </div>
      <div class="header-right">
        <img src="https://raw.githubusercontent.com/hugokhesley/dashboard-tim-connectgroup-sheets/main/logo.png" class="header-logo" onerror="this.style.display='none'">
        <span class="header-badge">📊 CONSOLIDADA</span>
      </div>
    </div>
    </div>""", unsafe_allow_html=True)

    with st.spinner("Carregando..."):
        raw   = load_data()
        bko   = load_bko()
        metas = load_metas()
        colab = load_colaboradores()

    if raw.empty:
        st.warning("⚠️ Nenhum dado encontrado.")
        st.stop()

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 🔧 Filtros")
        parceiro_sel = st.selectbox("Parceiro / Aba", get_parceiros(raw))

        lideres_colab = sorted([l for l in colab["lider"].unique() if l and l != "Sem Equipe"]) if not colab.empty else []
        lider_sel = st.selectbox("Líder / Equipe", ["Todos"] + lideres_colab)

        st.markdown("---")
        st.markdown(f"**Mês:** `{MES_ALVO}`")
        meta_ac  = int(metas.get("vendas_acessos", 626))
        meta_rec = float(metas.get("vendas_receita", 0))
        st.markdown(f"**Meta Acessos:** `{meta_ac:,}`")
        if meta_rec > 0:
            st.markdown(f"**Meta Receita:** `R$ {meta_rec:,.2f}`")
        st.markdown("---")
        if st.button("🔄 Atualizar"):
            st.cache_data.clear()
            st.rerun()
        st.caption("Dados via Google Sheets · cache 3 min")

    # ── Dados ─────────────────────────────────────────────────────────────────
    df = apply_filters(raw.copy(), MES_ALVO, ["NOVO", "ADITIVO"], parceiro_sel)

    # Esta página é sempre do mês corrente: usa só a aba DadosRadar.
    # (load_data concatena todas as abas; a aba resultados é p/ meses passados
    #  e, somada, dobraria acessos/receita da mesma venda.)
    if "_aba" in df.columns:
        df = df[df["_aba"].apply(lambda x: _s(x).strip().lower()) == "dadosradar"].copy()

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

    df_atv          = df[df["mes_ativacao"] == MES_ALVO].copy()
    df_pip          = df[df["mes_ativacao"].isna()].copy()
    df_pip_entrante = df_pip[df_pip["status_dash"] == "ENTRANTE"].copy()

    def _calc(nome):
        if nome == "ATIVO":
            d = df_atv
        elif nome == "ENTRANTE NÃO ATIVO":
            d = df_pip_entrante
        else:
            d = df_pip[df_pip["status_dash"] == nome]
        return {
            "acessos": int(d["acessos"].sum()),
            "receita": d["preco_oferta"].sum(),
            "pedidos": d["pedido"].nunique() if "pedido" in d.columns else len(d),
            "df": d,
        }

    dados = {n: _calc(n) for n in ETAPAS_CONFIG}

    # ── Seletor de etapas ─────────────────────────────────────────────────────
    st.markdown('<p class="section-title">☑️ Selecione as Etapas para o Atingimento</p>', unsafe_allow_html=True)

    defaults = {"ATIVO": True, "ENTRANTE NÃO ATIVO": True,
                "PRE-VENDA": False, "EM ANALISE": False, "CREDITO": False, "DEVOLVIDOS": False}
    cols_chk = st.columns(len(ETAPAS_CONFIG))
    etapas_sel = {}
    for i, (nome, cfg) in enumerate(ETAPAS_CONFIG.items()):
        with cols_chk[i]:
            etapas_sel[nome] = st.checkbox(
                f"{cfg['icon']} {nome}",
                value=defaults.get(nome, False),
                key=f"chk_{nome}"
            )

    st.markdown("")

    # ── Tabela por etapa ──────────────────────────────────────────────────────
    st.markdown('<p class="section-title">📋 Volume por Etapa</p>', unsafe_allow_html=True)

    max_ac  = max((v["acessos"] for v in dados.values()), default=1) or 1
    max_rec = max((v["receita"] for v in dados.values()), default=1) or 1
    total_pip_ac = sum(v["acessos"] for k, v in dados.items() if k != "ATIVO") or 1

    # Header
    st.markdown("""
    <div style="display:grid;grid-template-columns:210px 1fr 1fr 80px 120px;
      gap:8px;padding:6px 14px;margin-bottom:4px">
      <div class="col-header" style="text-align:left">Etapa</div>
      <div class="col-header">Acessos</div>
      <div class="col-header">Receita</div>
      <div class="col-header">Pedidos</div>
      <div class="col-header">% Pipeline</div>
    </div>""", unsafe_allow_html=True)

    for nome, cfg in ETAPAS_CONFIG.items():
        d   = dados[nome]
        sel = etapas_sel.get(nome, False)
        bg  = cfg["bg"] if sel else "#13151f"
        brd = f"2px solid {cfg['cor']}88" if sel else "1px solid #1e293b"
        pct_pip = f"{round(d['acessos']/total_pip_ac*100,1)}%" if nome != "ATIVO" else "—"

        bar_ac  = _bar(d["acessos"], max_ac,  cfg["cor"], 10)
        bar_rec = _bar(d["receita"], max_rec, cfg["cor"], 10)

        st.markdown(f"""
        <div style="display:grid;grid-template-columns:210px 1fr 1fr 80px 120px;
          gap:8px;padding:12px 14px;border-radius:10px;margin-bottom:5px;
          background:{bg};border:{brd}">
          <div>
            <div style="font-size:0.85rem;font-weight:700;color:{cfg['cor']}">{cfg['icon']} {nome}</div>
            <div style="font-size:0.68rem;color:#475569;margin-top:2px">{d['pedidos']} pedido(s)</div>
          </div>
          <div>
            <div style="font-size:1.1rem;font-weight:800;color:#e2e8f0;text-align:right">{d['acessos']:,}</div>
            {bar_ac}
          </div>
          <div>
            <div style="font-size:1.05rem;font-weight:800;color:#e2e8f0;text-align:right">R$ {d['receita']:,.0f}</div>
            {bar_rec}
          </div>
          <div style="text-align:right;font-size:0.9rem;font-weight:600;color:#94a3b8;padding-top:4px">
            {d['pedidos']:,}
          </div>
          <div style="text-align:right;font-size:0.82rem;color:#64748b;padding-top:4px">
            {pct_pip}
          </div>
        </div>""", unsafe_allow_html=True)

    # ── Cards de atingimento ──────────────────────────────────────────────────
    st.markdown("")
    st.markdown('<p class="section-title">🎯 Atingimento</p>', unsafe_allow_html=True)

    etapas_ativas = [n for n, v in etapas_sel.items() if v]
    sel_ac  = sum(dados[n]["acessos"] for n in etapas_ativas)
    sel_rec = sum(dados[n]["receita"] for n in etapas_ativas)
    falta_ac  = max(meta_ac - sel_ac, 0)
    falta_rec = max(meta_rec - sel_rec, 0)
    pct_ac    = min(int(sel_ac / meta_ac * 100), 999) if meta_ac > 0 else 0
    pct_rec   = min(int(sel_rec / meta_rec * 100), 999) if meta_rec > 0 else 0
    cor_ac    = _cor_pct(pct_ac)
    cor_rec   = _cor_pct(pct_rec)
    cls_ac    = "green" if pct_ac >= 100 else "amber" if pct_ac >= 70 else "red"
    cls_rec   = "green" if pct_rec >= 100 else "amber" if pct_rec >= 70 else "red"

    if etapas_ativas:
        st.caption(f"Considerando: **{' + '.join(etapas_ativas)}**")
    else:
        st.info("Selecione ao menos uma etapa acima.")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""<div class="ating-card {cls_ac}">
          <div class="ating-label">🎯 Acessos Selecionados</div>
          <div class="ating-val" style="color:{cor_ac}">{sel_ac:,}</div>
          <div>{_bar(sel_ac, meta_ac, cor_ac)}</div>
          <div class="ating-sub">Meta: {meta_ac:,} · {pct_ac}%</div>
        </div>""", unsafe_allow_html=True)

    with c2:
        cls2 = "green" if falta_ac == 0 else "red"
        st.markdown(f"""<div class="ating-card {cls2}">
          <div class="ating-label">⬇️ Falta — Acessos</div>
          <div class="ating-val" style="color:{'#10b981' if falta_ac==0 else '#ef4444'}">{falta_ac:,}</div>
          <div class="ating-sub">{'✅ Meta atingida!' if falta_ac == 0 else f'{falta_ac:,} ac. restantes'}</div>
        </div>""", unsafe_allow_html=True)

    with c3:
        if meta_rec > 0:
            st.markdown(f"""<div class="ating-card {cls_rec}">
              <div class="ating-label">💰 Receita Selecionada</div>
              <div class="ating-val" style="color:{cor_rec}">R$ {sel_rec:,.0f}</div>
              <div>{_bar(sel_rec, meta_rec, cor_rec)}</div>
              <div class="ating-sub">Meta: R$ {meta_rec:,.0f} · {pct_rec}%</div>
            </div>""", unsafe_allow_html=True)
        else:
            st.markdown(f"""<div class="ating-card blue">
              <div class="ating-label">💰 Receita Selecionada</div>
              <div class="ating-val" style="color:#3b82f6">R$ {sel_rec:,.0f}</div>
              <div class="ating-sub">Meta de receita não configurada</div>
            </div>""", unsafe_allow_html=True)

    with c4:
        if meta_rec > 0:
            cls4 = "green" if falta_rec == 0 else "red"
            st.markdown(f"""<div class="ating-card {cls4}">
              <div class="ating-label">⬇️ Falta — Receita</div>
              <div class="ating-val" style="color:{'#10b981' if falta_rec==0 else '#ef4444'}">R$ {falta_rec:,.0f}</div>
              <div class="ating-sub">{'✅ Meta atingida!' if falta_rec == 0 else f'R$ {falta_rec:,.0f} restantes'}</div>
            </div>""", unsafe_allow_html=True)
        else:
            total_pip = sum(dados[n]["acessos"] for n in ETAPAS_CONFIG if n != "ATIVO")
            st.markdown(f"""<div class="ating-card blue">
              <div class="ating-label">⏳ Total Pipeline</div>
              <div class="ating-val" style="color:#3b82f6">{total_pip:,}</div>
              <div class="ating-sub">acessos em tramitação</div>
            </div>""", unsafe_allow_html=True)

    # ── Detalhamento por vendedor ─────────────────────────────────────────────
    if etapas_ativas:
        st.markdown("")
        st.markdown('<p class="section-title">👤 Detalhamento por Vendedor</p>', unsafe_allow_html=True)

        frames = []
        for nome in etapas_ativas:
            d = dados[nome]["df"].copy()
            if not d.empty:
                d["_etapa"] = nome
                frames.append(d)

        if frames:
            df_det = pd.concat(frames, ignore_index=True)
            meta_dict = dict(zip(colab["vendedor"], colab["meta"])) if not colab.empty else {}

            resumo = (df_det.groupby("vendedor_real")
                      .agg(acessos=("acessos","sum"), receita=("preco_oferta","sum"),
                           pedidos=("pedido","nunique"))
                      .reset_index().sort_values("acessos", ascending=False))
            resumo.columns = ["Vendedor","Acessos","R$","Pedidos"]
            resumo["Meta"]    = resumo["Vendedor"].apply(lambda v: meta_dict.get(v, 0))
            resumo["% Meta"]  = resumo.apply(
                lambda r: f"{atingimento(r['Acessos'], r['Meta'])}%" if r["Meta"] > 0 else "—", axis=1
            )

            st.dataframe(resumo, use_container_width=True, hide_index=True,
                column_config={
                    "Acessos": st.column_config.NumberColumn(format="%d"),
                    "Pedidos": st.column_config.NumberColumn(format="%d"),
                    "Meta":    st.column_config.NumberColumn("Meta", format="%d"),
                    "R$":      st.column_config.NumberColumn(format="R$ %.2f"),
                })


main()
