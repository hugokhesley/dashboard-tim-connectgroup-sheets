"""
10_Discador.py — Análise do Funil de Ligações (Discador)
Connect Group | Dashboard TIM Empresas
"""

import streamlit as st
import pandas as pd
import gspread
import os, sys
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from auth import require_login
from data_loader import registrar_acesso, get_gspread_client, load_colaboradores

st.set_page_config(
    page_title="Connect Group | Discador",
    page_icon="📞",
    layout="wide",
    initial_sidebar_state="expanded"
)

username = require_login("discador")
registrar_acesso("Discador", username=username)

# ─────────────────────────────────────────────────────────────────
#  CLASSIFICAÇÃO DO FUNIL
# ─────────────────────────────────────────────────────────────────

# Contato efetivo = cliente atendeu e interagiu
CONTATO_EFETIVO = [
    "Contato realizado",
    "Desligou Apos Atendimento",
    "Ciente Nao tem Interesse",
    "Nao Deseja Ouvir Oferta",
    "Ligar Mais Tarde",
    "Oferta WhattsApp",
    "Finalizando WhattsApp",
    "Cliente Claro",
    "Cliente TIM",
    "Possui um Contrato Recente",
    "Blacklist",
]

# Proposta enviada / interesse demonstrado
PROPOSTA_ENVIADA = [
    "Oferta WhattsApp",
    "Finalizando WhattsApp",
    "Contato realizado",
    "Ligar Mais Tarde",
]

# Não alcançado (telefone não atendeu)
NAO_ALCANCADO = [
    "Nao atende",
    "Nao Atendeu",
    "Mensagem eletronica",
    "Caixa Postal",
    "Ocupado",
    "Numero invalido",
    "Numero Incorreto",
    "Problemas de rota",
    "Desligado sem operadores livres",
    "LIgacao Muda",
]

def classificar(resultado: str) -> str:
    """Classifica o resultado da ligação em categoria do funil."""
    r = str(resultado).strip()
    base = r.split("(")[0].strip()
    for p in PROPOSTA_ENVIADA:
        if p.lower() in base.lower():
            return "Proposta/Interesse"
    for p in CONTATO_EFETIVO:
        if p.lower() in base.lower():
            return "Contato Efetivo"
    for p in NAO_ALCANCADO:
        if p.lower() in base.lower():
            return "Não Alcançado"
    return "Outros"


# ─────────────────────────────────────────────────────────────────
#  CARREGAMENTO DOS DADOS
# ─────────────────────────────────────────────────────────────────

SPREADSHEET_ID = "1HmtEFf2Akh7NLR2prxDh9S4gmioKYw419B4bkx4yBLg"
ABA_DISCADOR   = "Discador"

@st.cache_data(ttl=120, show_spinner=False)
def load_discador():
    try:
        gc = get_gspread_client()
        planilha = gc.open_by_key(SPREADSHEET_ID)
        aba = planilha.worksheet(ABA_DISCADOR)
        dados = aba.get_all_records()
        if not dados:
            return pd.DataFrame()
        df = pd.DataFrame(dados)
        # Normaliza colunas
        df.columns = [c.strip() for c in df.columns]
        # Renomeia para padrão
        rename = {
            "Data / Hora": "data_hora",
            "Usuário": "usuario",
            "Telefone": "telefone",
            "Resultado": "resultado",
            "Duração": "duracao",
            "Campanha": "campanha",
            "Operadora": "operadora",
            "Modo Disc.": "modo",
        }
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
        # Filtra sem usuário
        df = df[df["usuario"].notna() & (df["usuario"].str.strip() != "")]
        # Parse data
        df["data_hora"] = pd.to_datetime(df["data_hora"], dayfirst=True, errors="coerce")
        df["data"]      = df["data_hora"].dt.date
        df["hora"]      = df["data_hora"].dt.hour
        # Duração em segundos
        def dur_seg(d):
            try:
                parts = str(d).split(":")
                return int(parts[0])*3600 + int(parts[1])*60 + int(parts[2])
            except Exception:
                return 0
        df["dur_seg"] = df["duracao"].apply(dur_seg)
        # Classificação funil
        df["funil"] = df["resultado"].apply(classificar)
        return df
    except Exception as e:
        st.error(f"Erro ao carregar aba Discador: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────
#  ESTILO
# ─────────────────────────────────────────────────────────────────

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
  html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
  .stApp { background-color: #0f1117; color: #e2e8f0; }
  .header-disc {
    background: linear-gradient(135deg, #0c1a2e 0%, #1e3a5f 50%, #2563eb 100%);
    border-radius: 16px; padding: 28px 36px; margin-bottom: 28px;
    box-shadow: 0 8px 32px rgba(37,99,235,0.25);
    border: 1px solid rgba(255,255,255,0.08);
    display: flex; align-items: center; justify-content: space-between;
  }
  .header-title { font-size: 1.9rem; font-weight: 800; color: #fff; margin: 0; }
  .header-sub   { font-size: 0.85rem; color: rgba(255,255,255,0.65); margin: 4px 0 0 0; }
  .header-badge { background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.25); border-radius: 20px; padding: 6px 16px; font-size: 0.8rem; color: #fff; font-weight: 600; }
  .kpi-mini { background: #1a1f2e; border-radius: 12px; padding: 16px 18px; border: 1px solid #2d3748; position: relative; overflow: hidden; margin-bottom: 4px; }
  .kpi-mini::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; }
  .kpi-mini.blue::before   { background: linear-gradient(90deg, #3b82f6, #1d4ed8); }
  .kpi-mini.green::before  { background: linear-gradient(90deg, #22c55e, #15803d); }
  .kpi-mini.amber::before  { background: linear-gradient(90deg, #f59e0b, #d97706); }
  .kpi-mini.purple::before { background: linear-gradient(90deg, #8b5cf6, #6d28d9); }
  .kpi-mini.red::before    { background: linear-gradient(90deg, #ef4444, #dc2626); }
  .kpi-label { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 1px; color: #94a3b8; font-weight: 600; margin-bottom: 6px; }
  .kpi-value { font-size: 1.7rem; font-weight: 800; color: #f1f5f9; line-height: 1; }
  .kpi-sub   { font-size: 0.72rem; color: #64748b; margin-top: 4px; }
  .vis-card  { background: #1a1f2e; border-radius: 14px; padding: 20px 24px; border: 1px solid #2d3748; margin-bottom: 16px; }
  .vis-title { font-size: 0.78rem; text-transform: uppercase; letter-spacing: 1px; color: #94a3b8; font-weight: 600; margin-bottom: 16px; }
  .rank-bar-wrap { margin: 4px 0 10px 0; }
  .rank-name  { font-size: 0.8rem; font-weight: 600; color: #e2e8f0; margin-bottom: 3px; display:flex; justify-content:space-between; }
  .rank-bg    { background: #2d3748; border-radius: 99px; height: 8px; }
  .rank-fill  { height: 8px; border-radius: 99px; }
  .rank-meta  { font-size: 0.68rem; color: #64748b; margin-top: 2px; }
  .section-title { font-size:0.75rem; text-transform:uppercase; letter-spacing:1.5px; color:#3b82f6; font-weight:700; margin:24px 0 12px 0; border-left: 3px solid #3b82f6; padding-left: 10px; }
  .funil-step { background: #1a1f2e; border-radius: 12px; padding: 16px 20px; border: 1px solid #2d3748; text-align: center; position: relative; }
  .funil-num  { font-size: 2.2rem; font-weight: 800; line-height: 1; }
  .funil-label { font-size: 0.72rem; color: #94a3b8; margin-top: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
  .funil-pct  { font-size: 0.85rem; font-weight: 700; margin-top: 6px; }
  section[data-testid="stSidebar"] { background: #0c1a2e !important; }
  .divider { border: none; border-top: 1px solid #1e293b; margin: 24px 0; }
</style>
""", unsafe_allow_html=True)


def _bar(valor, maximo, cor="#3b82f6", h=8):
    pct = min(int(valor / maximo * 100), 100) if maximo > 0 else 0
    return f'<div class="rank-bg"><div class="rank-fill" style="width:{pct}%;background:{cor};height:{h}px"></div></div>'


# ─────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────

def main():
    st.markdown("""
    <div class="header-disc">
      <div>
        <p class="header-title">📞 DISCADOR — FUNIL DE LIGAÇÕES</p>
        <p class="header-sub">Análise de conversão · Ligações · Contatos · Propostas</p>
      </div>
      <span class="header-badge">📊 DISCADOR</span>
    </div>
    """, unsafe_allow_html=True)

    with st.spinner("Carregando dados do discador..."):
        df = load_discador()
        colab = load_colaboradores()

    if df.empty:
        st.warning("""
        ⚠️ **Aba 'Discador' não encontrada ou vazia.**

        **Como usar:**
        1. Exporte o relatório do discador em CSV (separador `;`)
        2. Abra o Google Sheets da Connect Group
        3. Crie uma aba chamada **Discador**
        4. Cole o conteúdo do CSV lá (com cabeçalho)
        5. Recarregue esta página
        """)
        st.stop()

    # Monta dicionário lider→vendedores do Colaboradores
    lider_por_vend = {}
    if not colab.empty and "vendedor" in colab.columns and "lider" in colab.columns:
        for _, row in colab.iterrows():
            lider_por_vend[str(row["vendedor"]).strip().upper()] = str(row["lider"]).strip()

    # Adiciona coluna lider no df
    def get_lider(usuario):
        u = str(usuario).strip().upper()
        return lider_por_vend.get(u, "Sem Equipe")

    df["lider"] = df["usuario"].apply(get_lider)

    # ── Sidebar filtros ──────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 🔧 Filtros")

        # Período
        periodo = st.selectbox("Período", [
            "Hoje", "Ontem", "Últimos 7 dias", "Últimos 30 dias",
            "Mês atual", "Personalizado"
        ])
        hoje = date.today()
        if periodo == "Hoje":
            dt_ini, dt_fim = hoje, hoje
        elif periodo == "Ontem":
            dt_ini = dt_fim = hoje - timedelta(days=1)
        elif periodo == "Últimos 7 dias":
            dt_ini, dt_fim = hoje - timedelta(days=6), hoje
        elif periodo == "Últimos 30 dias":
            dt_ini, dt_fim = hoje - timedelta(days=29), hoje
        elif periodo == "Mês atual":
            dt_ini = hoje.replace(day=1)
            dt_fim = hoje
        else:
            dt_ini = st.date_input("De", hoje - timedelta(days=6))
            dt_fim = st.date_input("Até", hoje)

        # Lider
        lideres_opts = ["Todos"] + sorted([l for l in df["lider"].unique() if l != "Sem Equipe"])
        lider_sel = st.selectbox("Equipe / Líder", lideres_opts)

        # Vendedor
        if lider_sel != "Todos":
            vendedores_opts = ["Todos"] + sorted(df[df["lider"] == lider_sel]["usuario"].unique().tolist())
        else:
            vendedores_opts = ["Todos"] + sorted(df["usuario"].unique().tolist())
        vend_sel = st.selectbox("Vendedor", vendedores_opts)

        # Campanha
        campanhas = ["Todas"] + sorted(df["campanha"].dropna().unique().tolist())
        camp_sel = st.selectbox("Campanha", campanhas)

        st.markdown("---")
        if st.button("🔄 Atualizar"):
            st.cache_data.clear()
            st.rerun()
        st.caption(f"Total de registros: {len(df):,}")

    # ── Aplica filtros ───────────────────────────────────────────
    mask = (df["data"] >= dt_ini) & (df["data"] <= dt_fim)
    if lider_sel != "Todos":
        mask &= df["lider"] == lider_sel
    if vend_sel != "Todos":
        mask &= df["usuario"] == vend_sel
    if camp_sel != "Todas":
        mask &= df["campanha"] == camp_sel

    dff = df[mask].copy()

    if dff.empty:
        st.info("Nenhum dado para os filtros selecionados.")
        st.stop()

    # ── KPIs do funil ────────────────────────────────────────────
    st.markdown('<p class="section-title">📊 Funil de Ligações</p>', unsafe_allow_html=True)

    total        = len(dff)
    contato      = len(dff[dff["funil"] == "Contato Efetivo"])
    proposta     = len(dff[dff["funil"] == "Proposta/Interesse"])
    nao_alcancado= len(dff[dff["funil"] == "Não Alcançado"])
    outros       = len(dff[dff["funil"] == "Outros"])

    tx_contato  = round(contato  / total * 100, 1) if total > 0 else 0
    tx_proposta = round(proposta / contato * 100, 1) if contato > 0 else 0
    tx_nao_alc  = round(nao_alcancado / total * 100, 1) if total > 0 else 0

    dur_media = round(dff[dff["dur_seg"] > 0]["dur_seg"].mean(), 0) if not dff[dff["dur_seg"] > 0].empty else 0
    dur_min   = int(dur_media // 60)
    dur_seg_r = int(dur_media % 60)

    # Funil visual
    f1, f2, f3, f4, f5 = st.columns(5)
    with f1:
        st.markdown(f"""<div class="funil-step">
          <div class="funil-label">📞 Total Discado</div>
          <div class="funil-num" style="color:#3b82f6">{total:,}</div>
          <div class="funil-pct" style="color:#64748b">100%</div>
        </div>""", unsafe_allow_html=True)
    with f2:
        st.markdown(f"""<div class="funil-step">
          <div class="funil-label">🔴 Não Alcançado</div>
          <div class="funil-num" style="color:#ef4444">{nao_alcancado:,}</div>
          <div class="funil-pct" style="color:#ef4444">{tx_nao_alc}% do total</div>
        </div>""", unsafe_allow_html=True)
    with f3:
        cor_c = "#22c55e" if tx_contato >= 30 else "#f59e0b" if tx_contato >= 15 else "#ef4444"
        st.markdown(f"""<div class="funil-step">
          <div class="funil-label">✅ Contato Efetivo</div>
          <div class="funil-num" style="color:{cor_c}">{contato:,}</div>
          <div class="funil-pct" style="color:{cor_c}">{tx_contato}% do total</div>
        </div>""", unsafe_allow_html=True)
    with f4:
        cor_p = "#22c55e" if tx_proposta >= 40 else "#f59e0b" if tx_proposta >= 20 else "#ef4444"
        st.markdown(f"""<div class="funil-step">
          <div class="funil-label">💬 Proposta/Interesse</div>
          <div class="funil-num" style="color:{cor_p}">{proposta:,}</div>
          <div class="funil-pct" style="color:{cor_p}">{tx_proposta}% dos contatos</div>
        </div>""", unsafe_allow_html=True)
    with f5:
        st.markdown(f"""<div class="funil-step">
          <div class="funil-label">⏱ Duração Média</div>
          <div class="funil-num" style="color:#8b5cf6;font-size:1.6rem">{dur_min}m{dur_seg_r:02d}s</div>
          <div class="funil-pct" style="color:#64748b">por ligação</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("")

    # ── KPIs extras ──────────────────────────────────────────────
    k1, k2, k3, k4 = st.columns(4)
    vendedores_ativos = dff["usuario"].nunique()
    media_por_vend    = round(total / vendedores_ativos, 1) if vendedores_ativos > 0 else 0
    melhor_vend = dff.groupby("usuario").size().idxmax() if not dff.empty else "—"
    melhor_tx_vend = ""
    if not dff.empty:
        tx_por_vend = dff.groupby("usuario").apply(
            lambda x: round(len(x[x["funil"]=="Contato Efetivo"])/len(x)*100, 1)
        )
        melhor_tx_vend = f"{tx_por_vend.max()}% conversão" if not tx_por_vend.empty else ""

    with k1:
        st.markdown(f"""<div class="kpi-mini blue">
          <div class="kpi-label">👥 Vendedores Ativos</div>
          <div class="kpi-value">{vendedores_ativos}</div>
          <div class="kpi-sub">no período</div>
        </div>""", unsafe_allow_html=True)
    with k2:
        st.markdown(f"""<div class="kpi-mini purple">
          <div class="kpi-label">📊 Média Lig./Vendedor</div>
          <div class="kpi-value">{media_por_vend}</div>
          <div class="kpi-sub">ligações por pessoa</div>
        </div>""", unsafe_allow_html=True)
    with k3:
        st.markdown(f"""<div class="kpi-mini green">
          <div class="kpi-label">🏆 Maior Volume</div>
          <div class="kpi-value" style="font-size:1rem">{melhor_vend.split()[0] if melhor_vend != '—' else '—'}</div>
          <div class="kpi-sub">{dff.groupby('usuario').size().max() if not dff.empty else 0} ligações</div>
        </div>""", unsafe_allow_html=True)
    with k4:
        campanhas_ativas = dff["campanha"].nunique() if "campanha" in dff.columns else 0
        st.markdown(f"""<div class="kpi-mini amber">
          <div class="kpi-label">📋 Campanhas</div>
          <div class="kpi-value">{campanhas_ativas}</div>
          <div class="kpi-sub">ativas no período</div>
        </div>""", unsafe_allow_html=True)

    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    # ── Ranking por vendedor ──────────────────────────────────────
    st.markdown('<p class="section-title">👤 Ranking por Vendedor</p>', unsafe_allow_html=True)

    grp = dff.groupby("usuario").apply(lambda x: pd.Series({
        "total":    len(x),
        "contato":  len(x[x["funil"]=="Contato Efetivo"]),
        "proposta": len(x[x["funil"]=="Proposta/Interesse"]),
        "nao_alc":  len(x[x["funil"]=="Não Alcançado"]),
        "dur_media": round(x[x["dur_seg"]>0]["dur_seg"].mean(), 0) if len(x[x["dur_seg"]>0]) > 0 else 0,
        "lider":    x["lider"].iloc[0],
    })).reset_index().sort_values("total", ascending=False)

    grp["tx_contato"]  = (grp["contato"]  / grp["total"] * 100).round(1)
    grp["tx_proposta"] = (grp["proposta"] / grp["contato"] * 100).round(1).fillna(0)

    mx_total = grp["total"].max() if not grp.empty else 1

    col_r, col_d = st.columns([3, 2])

    with col_r:
        st.markdown('<div class="vis-card">', unsafe_allow_html=True)
        st.markdown('<div class="vis-title">📞 Volume e Conversão por Vendedor</div>', unsafe_allow_html=True)
        html = ""
        for _, row in grp.iterrows():
            nome_curto = str(row["usuario"]).split()[0].title()
            cor_c = "#22c55e" if row["tx_contato"] >= 30 else "#f59e0b" if row["tx_contato"] >= 15 else "#ef4444"
            min_d = int(row["dur_media"] // 60)
            seg_d = int(row["dur_media"] % 60)
            html += f"""<div class="rank-bar-wrap">
              <div class="rank-name">
                <span>👤 {nome_curto} <span style="color:#64748b;font-size:0.7rem">({row['lider'].split()[0] if row['lider'] != 'Sem Equipe' else 'Sem Equipe'})</span></span>
                <span style="color:#3b82f6;font-weight:700">{int(row['total'])} lig.</span>
              </div>
              {_bar(row['total'], mx_total, "#3b82f6")}
              <div class="rank-meta">
                ✅ {int(row['contato'])} contatos ({row['tx_contato']}%) · 
                💬 {int(row['proposta'])} propostas ({row['tx_proposta']}%) · 
                ⏱ {min_d}m{seg_d:02d}s médio
              </div>
            </div>"""
        st.markdown(html, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with col_d:
        # Distribuição por resultado
        st.markdown('<div class="vis-card">', unsafe_allow_html=True)
        st.markdown('<div class="vis-title">📊 Distribuição por Resultado</div>', unsafe_allow_html=True)
        res_grp = dff.groupby("resultado").size().sort_values(ascending=False).head(12)
        mx_res = res_grp.max()
        html_r = ""
        CORES_RES = {
            "Contato Efetivo": "#22c55e",
            "Proposta/Interesse": "#3b82f6",
            "Não Alcançado": "#ef4444",
            "Outros": "#64748b"
        }
        for resultado, qty in res_grp.items():
            funil_cat = classificar(resultado)
            cor = CORES_RES.get(funil_cat, "#64748b")
            base = str(resultado).split("(")[0].strip()[:35]
            pct = round(qty/len(dff)*100, 1)
            html_r += f"""<div class="rank-bar-wrap">
              <div class="rank-name">
                <span style="font-size:0.75rem">{base}</span>
                <span style="color:{cor};font-weight:700">{qty} <span style="color:#64748b">({pct}%)</span></span>
              </div>
              {_bar(qty, mx_res, cor)}
            </div>"""
        st.markdown(html_r, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # ── Por equipe ────────────────────────────────────────────────
    if lider_sel == "Todos":
        st.markdown('<p class="section-title">🏆 Ranking por Equipe</p>', unsafe_allow_html=True)
        eq_grp = dff.groupby("lider").apply(lambda x: pd.Series({
            "total":    len(x),
            "contato":  len(x[x["funil"]=="Contato Efetivo"]),
            "proposta": len(x[x["funil"]=="Proposta/Interesse"]),
            "vendedores": x["usuario"].nunique(),
        })).reset_index().sort_values("total", ascending=False)
        eq_grp["tx_contato"] = (eq_grp["contato"] / eq_grp["total"] * 100).round(1)

        mx_eq = eq_grp["total"].max()
        st.markdown('<div class="vis-card">', unsafe_allow_html=True)
        html_eq = ""
        for _, row in eq_grp.iterrows():
            if row["lider"] == "Sem Equipe":
                continue
            cor_c = "#22c55e" if row["tx_contato"] >= 30 else "#f59e0b" if row["tx_contato"] >= 15 else "#ef4444"
            html_eq += f"""<div class="rank-bar-wrap">
              <div class="rank-name">
                <span>👥 {row['lider']} ({int(row['vendedores'])} vend.)</span>
                <span style="color:#3b82f6;font-weight:700">{int(row['total'])} lig.</span>
              </div>
              {_bar(row['total'], mx_eq, "#3b82f6")}
              <div class="rank-meta">
                ✅ {int(row['contato'])} contatos ({row['tx_contato']}%) · 
                💬 {int(row['proposta'])} propostas
              </div>
            </div>"""
        st.markdown(html_eq, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # ── Tabela detalhada ──────────────────────────────────────────
    st.markdown('<p class="section-title">📋 Tabela por Vendedor</p>', unsafe_allow_html=True)
    tabela = grp.rename(columns={
        "usuario": "Vendedor", "lider": "Líder",
        "total": "Total Lig.", "contato": "Contato Efetivo",
        "proposta": "Proposta/Interesse", "nao_alc": "Não Alcançado",
        "tx_contato": "% Contato", "tx_proposta": "% Proposta",
        "dur_media": "Dur. Média (s)"
    })
    st.dataframe(
        tabela[["Vendedor", "Líder", "Total Lig.", "Contato Efetivo", "% Contato",
                "Proposta/Interesse", "% Proposta", "Não Alcançado", "Dur. Média (s)"]],
        use_container_width=True, hide_index=True,
        column_config={
            "Total Lig.":          st.column_config.NumberColumn("📞 Total",      format="%d"),
            "Contato Efetivo":     st.column_config.NumberColumn("✅ Contato",    format="%d"),
            "% Contato":           st.column_config.NumberColumn("% Contato",     format="%.1f%%"),
            "Proposta/Interesse":  st.column_config.NumberColumn("💬 Proposta",   format="%d"),
            "% Proposta":          st.column_config.NumberColumn("% Proposta",    format="%.1f%%"),
            "Não Alcançado":       st.column_config.NumberColumn("🔴 Não Alc.",   format="%d"),
            "Dur. Média (s)":      st.column_config.NumberColumn("⏱ Dur.(s)",    format="%d"),
        }
    )

    csv = tabela.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Exportar CSV", csv,
        f"discador_{dt_ini}_{dt_fim}.csv", "text/csv")

    # ── Log detalhado ─────────────────────────────────────────────
    with st.expander("🔍 Log completo de ligações"):
        st.dataframe(
            dff[["data_hora", "usuario", "lider", "telefone", "resultado", "funil", "duracao", "campanha", "modo"]].sort_values("data_hora", ascending=False),
            use_container_width=True, hide_index=True,
            column_config={
                "data_hora": "Data/Hora",
                "usuario":   "Vendedor",
                "lider":     "Líder",
                "telefone":  "Telefone",
                "resultado": "Resultado",
                "funil":     "Categoria",
                "duracao":   "Duração",
                "campanha":  "Campanha",
                "modo":      "Modo",
            }
        )


main()
