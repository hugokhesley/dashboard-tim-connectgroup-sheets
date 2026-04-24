import streamlit as st
from datetime import datetime, date, timedelta

MESES_PT = {
    "01":"Janeiro","02":"Fevereiro","03":"Março","04":"Abril",
    "05":"Maio","06":"Junho","07":"Julho","08":"Agosto",
    "09":"Setembro","10":"Outubro","11":"Novembro","12":"Dezembro"
}
import pandas as pd
from data_loader import (
    load_data, load_bko, load_colaboradores, apply_filters, get_parceiros,
    STATUS_COLORS, _s, _norm_pedido, inserir_pendentes_bko,
    registrar_acesso, get_gspread_client
)
from auth import require_login

st.set_page_config(
    page_title="Connect Group | Performance",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="expanded"
)

username = require_login("performance")
registrar_acesso("performance", username=username)

MES_ALVO          = datetime.now().strftime("%m/%Y")
META_VENDEDOR_PAD = 850
SPREADSHEET_ID    = "1HmtEFf2Akh7NLR2prxDh9S4gmioKYw419B4bkx4yBLg"

def _meta_vend(nome: str, meta_dict: dict) -> float:
    return meta_dict.get(nome, META_VENDEDOR_PAD)

DESTINATARIOS_TESTE = ["hugo@connectgroup.solutions"]
DESTINATARIOS_FULL = [
    "bko2@connectbrasil.tech",
    "bko@connectbrasil.tech",
    "hugo@connectgroup.solutions",
    "angelo@connectgroup.solutions",
    "andrey.albuquerque@connectgroup.solutions",
]

# ── Classificação funil discador ──────────────────────────────────
CONTATO_EFETIVO = [
    "Contato realizado", "Desligou Apos Atendimento", "Ciente Nao tem Interesse",
    "Nao Deseja Ouvir Oferta", "Ligar Mais Tarde", "Oferta WhattsApp",
    "Finalizando WhattsApp", "Cliente Claro", "Cliente TIM",
    "Possui um Contrato Recente", "Blacklist",
]
PROPOSTA_ENVIADA = [
    "Oferta WhattsApp", "Finalizando WhattsApp", "Contato realizado", "Ligar Mais Tarde",
]

def _classificar_funil(resultado: str) -> str:
    r = str(resultado).split("(")[0].strip()
    for p in PROPOSTA_ENVIADA:
        if p.lower() in r.lower():
            return "proposta"
    for p in CONTATO_EFETIVO:
        if p.lower() in r.lower():
            return "contato"
    return "nao_alcancado"

@st.cache_data(ttl=120, show_spinner=False)
def load_discador_resumo():
    """Carrega aba Discador e retorna resumo por vendedor (hoje e mês)."""
    # De/Para: nomes do discador → nomes do dashboard
    DEPARA = {
        "MARIA GABRIELLI CORREIA BARROS":     "MARIA GABRIELLI CORREIA",
        "JOSE LUIZ FELIX BARBOSA":            "JOSE LUIZ FELX BARBOSA",
        "KENNIA ANDRIELY DOS SANTOS MARINHO": "KENNIA ANDRIELY DOS SANTOS",
    }
    try:
        gc = get_gspread_client()
        planilha = gc.open_by_key(SPREADSHEET_ID)
        aba = planilha.worksheet("Discador")
        dados = aba.get_all_records()
        if not dados:
            return pd.DataFrame()
        df = pd.DataFrame(dados)
        df.columns = [c.strip() for c in df.columns]
        rename = {
            "Data / Hora": "data_hora", "Usuário": "usuario",
            "Resultado": "resultado", "Campanha": "campanha",
            "Duração": "duracao",
        }
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
        df = df[df["usuario"].notna() & (df["usuario"].str.strip() != "")]
        # Aplica De/Para
        df["usuario"] = df["usuario"].apply(
            lambda u: DEPARA.get(str(u).strip().upper(), str(u).strip()) if pd.notna(u) else u
        )
        df["data_hora"] = pd.to_datetime(df["data_hora"], dayfirst=True, errors="coerce")
        df["data"]      = df["data_hora"].dt.date
        df["funil"]     = df["resultado"].apply(_classificar_funil)
        return df
    except Exception:
        return pd.DataFrame()

def resumo_discador_por_lider(df_disc, colab):
    """Retorna dict {lider: [{vendedor, total, contato, proposta}]}"""
    if df_disc.empty or colab is None or colab.empty:
        return {}

    # Mapa vendedor → lider
    lider_map = {}
    for _, row in colab.iterrows():
        lider_map[str(row["vendedor"]).strip().upper()] = str(row["lider"]).strip()

    df_disc["lider"] = df_disc["usuario"].apply(
        lambda u: lider_map.get(str(u).strip().upper(), "Sem Equipe")
    )

    # Hoje e mês atual
    hoje = date.today()
    mes_ini = hoje.replace(day=1)

    resultado = {}
    for lider in df_disc["lider"].unique():
        if lider == "Sem Equipe":
            continue
        dl = df_disc[df_disc["lider"] == lider]
        vendedores = []
        for vend in sorted(dl["usuario"].unique()):
            dv      = dl[dl["usuario"] == vend]
            dv_hoje = dv[dv["data"] == hoje]
            dv_mes  = dv[dv["data"] >= mes_ini]
            vendedores.append({
                "vendedor":        vend.split()[0].title(),
                "hoje_total":      len(dv_hoje),
                "hoje_contato":    len(dv_hoje[dv_hoje["funil"].isin(["contato","proposta"])]),
                "hoje_proposta":   len(dv_hoje[dv_hoje["funil"] == "proposta"]),
                "mes_total":       len(dv_mes),
                "mes_contato":     len(dv_mes[dv_mes["funil"].isin(["contato","proposta"])]),
                "mes_proposta":    len(dv_mes[dv_mes["funil"] == "proposta"]),
            })
        resultado[lider] = vendedores
    return resultado

# ── Telegram ──────────────────────────────────────────────────────
# Token do bot e chat_ids dos líderes
# Configurar nos secrets do Streamlit:
# [telegram]
# token = "7776803920:AAE4ZYll8iakct7pIRGfszVgeF659kPywy0"
# [telegram.lideres]
# "Nome Lider" = "chat_id"

def _telegram_token():
    try:
        return st.secrets["telegram"]["token"]
    except Exception:
        return "7776803920:AAE4ZYll8iakct7pIRGfszVgeF659kPywy0"

def _telegram_lideres():
    """Retorna dict {nome_lider: chat_id} dos secrets."""
    try:
        return dict(st.secrets["telegram"]["lideres"])
    except Exception:
        return {}

def enviar_telegram(chat_id: str, mensagem: str) -> bool:
    """Envia mensagem individual via Telegram Bot API."""
    import requests as _req
    try:
        token = _telegram_token()
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = _req.post(url, json={
            "chat_id": chat_id,
            "text": mensagem,
            "parse_mode": "HTML"
        }, timeout=10)
        return resp.status_code == 200
    except Exception:
        return False


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
  .kpi-mini.gold::before   { background: linear-gradient(90deg, #f59e0b, #b45309); }
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
  .header-logo { height:44px;width:auto;object-fit:contain;mix-blend-mode:multiply;border-radius:6px; }
  .header-right { display:flex;align-items:center;gap:14px; }
  .section-title { font-size:0.75rem; text-transform:uppercase; letter-spacing:1.5px; color:#22c55e; font-weight:700; margin:24px 0 12px 0; border-left: 3px solid #22c55e; padding-left: 10px; }
  section[data-testid="stSidebar"] { background: #0d1a0f !important; }
  details { background:#1a1f2e !important; border:1px solid #2d3748 !important; border-radius:0 0 10px 10px !important; }
  details summary { color:#e2e8f0 !important; font-weight:600 !important; }
  .divider { border: none; border-top: 1px solid #1e293b; margin: 28px 0; }
  .vis-card { background: #1a1f2e; border-radius: 14px; padding: 20px 24px; border: 1px solid #2d3748; }
  .vis-title { font-size: 0.78rem; text-transform: uppercase; letter-spacing: 1px; color: #94a3b8; font-weight: 600; margin-bottom: 16px; }
  .comiss-card { background: #1a1f2e; border-radius: 14px; padding: 20px 24px; border: 1px solid #2d3748; margin-bottom: 16px; }
  .comiss-lider { font-size: 1rem; font-weight: 800; color: #fbbf24; margin-bottom: 12px; }
  .comiss-row { display:flex; justify-content:space-between; align-items:center; padding: 8px 0; border-bottom: 1px solid #1e293b; }
  .comiss-vend { font-size: 0.82rem; color: #e2e8f0; }
  .comiss-val  { font-size: 0.82rem; font-weight: 700; }
  .comiss-ok   { color: #22c55e; }
  .comiss-no   { color: #ef4444; }
  .comiss-total { display:flex; justify-content:space-between; padding: 10px 0 0 0; margin-top: 8px; }
  .comiss-total-label { font-size: 0.78rem; color: #94a3b8; font-weight: 600; text-transform: uppercase; }
  .comiss-total-val   { font-size: 1.1rem; font-weight: 800; color: #fbbf24; }

  /* ── DETALHADO ── */
  .det-parceiro {
    background: linear-gradient(90deg, #0d1f3c, #1e3a5f);
    border-left: 5px solid #3b82f6;
    border-radius: 12px; padding: 14px 22px; margin: 20px 0 12px 0;
    display: flex; align-items: center; justify-content: space-between;
  }
  .det-parceiro-nome { font-size: 1.05rem; font-weight: 800; color: #93c5fd; letter-spacing: 0.5px; }
  .det-parceiro-stats { font-size: 0.78rem; color: #64748b; }
  .det-lider {
    background: #131f2e; border-left: 4px solid #22c55e;
    border-radius: 10px; padding: 10px 18px; margin: 10px 0 6px 16px;
    display: flex; align-items: center; justify-content: space-between;
    cursor: default;
  }
  .det-lider-nome { font-size: 0.92rem; font-weight: 700; color: #86efac; }
  .det-lider-stats { font-size: 0.75rem; color: #64748b; }
  .det-vendedor {
    background: #0f1820; border-left: 3px solid #334155;
    border-radius: 8px; padding: 10px 16px; margin: 5px 0 5px 32px;
  }
  .det-vend-header {
    display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;
  }
  .det-vend-nome { font-size: 0.83rem; font-weight: 700; color: #cbd5e1; }
  .det-vend-kpis { display: flex; gap: 14px; font-size: 0.75rem; color: #64748b; }
  .det-vend-kpi-val { font-weight: 700; color: #e2e8f0; }
  .det-cliente-row {
    display: flex; align-items: center; justify-content: space-between;
    padding: 5px 8px; border-radius: 6px; margin: 3px 0;
    background: #0a1018; border: 1px solid #1e293b;
    font-size: 0.75rem;
  }
  .det-cliente-nome { color: #94a3b8; max-width: 40%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .det-cliente-stats { display: flex; gap: 12px; color: #64748b; flex-shrink: 0; }
  .det-cliente-ac { color: #60a5fa; font-weight: 600; }
  .det-cliente-rec { color: #4ade80; font-weight: 600; }
  .det-cliente-fila { font-size: 0.68rem; padding: 2px 6px; border-radius: 99px; font-weight: 600; }
  .det-empty { color: #475569; font-size: 0.75rem; font-style: italic; padding: 6px 8px; }
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


def render_visual(df, lideres, lider_sel, meta_dict):
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

    with c_gauge:
        rec_atv = df_atv_all["preco_oferta"].sum()
        rec_pip = df_pip_all["preco_oferta"].sum()
        rec_g   = rec_atv + rec_pip if incluir_pipeline else rec_atv
        meta    = sum(_meta_vend(v, meta_dict) for v in df["vendedor_real"].unique()) if meta_dict else df["vendedor_real"].nunique() * META_VENDEDOR_PAD
        pct     = min(int(rec_g / meta * 100), 999) if meta > 0 else 0
        cor     = _cor(pct)
        sub_pip = f"<div class='gauge-sub' style='margin-top:2px'>⏳ +R$ {rec_pip:,.2f} pipeline</div>" if incluir_pipeline else "<div></div>"
        st.markdown(f"""<div class="gauge-wrap">
          <div class="vis-title">🎯 {'Ativ. + Pipeline' if incluir_pipeline else 'Atingimento Receita'}</div>
          <div class="gauge-pct" style="color:{cor}">{pct}%</div>
          <div style="margin:10px 0">{_bar(rec_g, meta, cor, 14)}</div>
          <div class="gauge-sub">R$ {rec_g:,.2f} de R$ {meta:,.2f}</div>
          {sub_pip}
          <div class="gauge-sub" style="margin-top:4px">{df["vendedor_real"].nunique()} vendedor(es)</div>
        </div>""", unsafe_allow_html=True)

    with c_eq:
        st.markdown('<div class="vis-card">', unsafe_allow_html=True)
        lbl_eq = "Ativ. + Pipeline" if incluir_pipeline else "Receita Ativada"
        st.markdown(f'<div class="vis-title">🏆 Ranking de Equipes — {lbl_eq}</div>', unsafe_allow_html=True)
        rows = []
        for l in lideres:
            dl   = df[df["lider"] == l]
            r    = _vend_rec(dl)
            ratv = dl[dl["mes_ativacao"] == MES_ALVO]["preco_oferta"].sum()
            rpip = dl[dl["mes_ativacao"].isna()]["preco_oferta"].sum()
            meta_eq = sum(_meta_vend(v, meta_dict) for v in dl["vendedor_real"].unique()) if meta_dict else dl["vendedor_real"].nunique() * META_VENDEDOR_PAD
            nv = dl["vendedor_real"].nunique()
            rows.append({"lider":l,"rec":r,"ratv":ratv,"rpip":rpip,"meta":meta_eq,"nv":nv})
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
            mv = _meta_vend(vend, meta_dict)
            p  = min(int(val / mv * 100), 100) if mv > 0 else 0
            c  = _cor(p)
            m  = medals[i] if i < 3 else f"{i+1}º"
            if incluir_pipeline:
                a = ser_atv.get(vend, 0)
                p2= ser_pip.get(vend, 0)
                sub = f"<div class='rank-meta'>✅ R$ {a:,.2f} · ⏳ R$ {p2:,.2f} · meta R$ {mv:,.2f}</div>"
            else:
                sub = f"<div class='rank-meta'>meta individual R$ {mv:,.2f}</div>"
            html_v += f"""<div class="rank-bar-wrap">
              <div class="rank-name"><span>{m} {vend}</span>
              <span style="color:{c};font-weight:700">R$ {val:,.2f} <span style="color:#64748b">({p}%)</span></span></div>
              {_bar(val, mx_v, c)}{sub}
            </div>"""

        if not html_v:
            html_v = '<p style="color:#64748b;font-size:0.8rem">Nenhuma ativação no período.</p>'
        st.markdown(html_v, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

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


# ─────────────────────────────────────────────────────────────────
#  NOVA VISÃO: COMISSIONAMENTO
# ─────────────────────────────────────────────────────────────────

def calcular_comissionamento(df, lideres, meta_dict, colab=None):
    """
    Calcula comissionamento de vendedores e líderes.
    Usa a planilha Colaboradores como base — todos os vendedores aparecem,
    mesmo os que não ativaram nada no mês.
    """
    import unicodedata

    def normalizar(s):
        """Remove acentos e deixa em minúsculas para comparação."""
        return ''.join(
            c for c in unicodedata.normalize('NFD', str(s).strip().lower())
            if unicodedata.category(c) != 'Mn'
        )

    df_atv = df[df["mes_ativacao"] == MES_ALVO].copy()
    rec_por_vend = df_atv.groupby("vendedor_real")["preco_oferta"].sum()

    vends_por_lider = {}
    if colab is not None and not colab.empty:
        # Cria mapa normalizado: nome_normalizado → nome_original no colab
        colab_lider_norm = {normalizar(row["lider"]): row["lider"]
                            for _, row in colab.iterrows() if pd.notna(row.get("lider"))}

        for lider in lideres:
            if lider == "Sem Equipe":
                continue
            lider_norm = normalizar(lider)
            # Busca por nome normalizado (ignora acentos e case)
            mask = colab["lider"].apply(normalizar) == lider_norm
            vends = colab[mask]["vendedor"].dropna().unique().tolist()
            vends_por_lider[lider] = sorted(vends)
    else:
        for lider in lideres:
            if lider == "Sem Equipe":
                continue
            dl = df[df["lider"] == lider]
            vends_por_lider[lider] = sorted([v for v in dl["vendedor_real"].unique() if v != "Sem Vendedor"])

    resultado = {}
    for lider in lideres:
        if lider == "Sem Equipe":
            continue

        vendedores = vends_por_lider.get(lider, [])

        # Fallback: se colab não encontrou ninguém, usa os pedidos
        if not vendedores:
            dl = df[df["lider"] == lider]
            vendedores = sorted([v for v in dl["vendedor_real"].unique() if v not in ("Sem Vendedor", "")])

        vendedores_data = []
        total_comiss_lider = 0.0

        for vend in vendedores:
            meta    = _meta_vend(vend, meta_dict)
            receita = rec_por_vend.get(vend, 0.0)
            bateu   = receita >= meta

            comiss_vend  = receita if bateu else 0.0
            comiss_lider = receita * 0.5 if bateu else 0.0
            total_comiss_lider += comiss_lider

            vendedores_data.append({
                "vendedor":     vend,
                "meta":         meta,
                "receita":      receita,
                "bateu":        bateu,
                "pct":          min(int(receita / meta * 100), 100) if meta > 0 else 0,
                "comiss_vend":  comiss_vend,
                "comiss_lider": comiss_lider,
            })

        meta_lider = sum(_meta_vend(v, meta_dict) for v in vendedores) if vendedores else 0
        rec_lider  = sum(d["receita"] for d in vendedores_data)
        n_bateram  = sum(1 for d in vendedores_data if d["bateu"])

        resultado[lider] = {
            "vendedores":         vendedores_data,
            "total_comiss_lider": total_comiss_lider,
            "meta_lider":         meta_lider,
            "rec_lider":          rec_lider,
            "n_vendedores":       len(vendedores),
            "n_bateram":          n_bateram,
        }

    return resultado


def render_comissionamento(df, lideres, meta_dict, colab=None):
    st.markdown('<p class="section-title">💰 Projeção de Comissionamento — Meta x Realizado</p>', unsafe_allow_html=True)

    st.info(f"""
    **Regras de Comissionamento — {MES_ALVO}:**
    • **Vendedor:** recebe 100% da receita ativada se ≥ R$ 850 (meta individual)
    • **Líder:** recebe 50% da receita de cada vendedor que atingiu a meta
    • Baseado apenas em **ativações do mês** (mes_ativacao == {MES_ALVO})
    """)

    dados = calcular_comissionamento(df, lideres, meta_dict, colab=colab)

    if not dados:
        st.warning("Nenhum dado de comissionamento disponível.")
        return

    # ── Diagnóstico (expander) ────────────────────────────────────
    with st.expander("🔍 Diagnóstico de dados", expanded=False):
        st.caption(f"**Mês alvo:** `{MES_ALVO}`")
        st.caption(f"**Líderes encontrados:** {list(dados.keys())}")
        st.caption(f"**Ativações no mês:** {len(df[df['mes_ativacao'] == MES_ALVO])} pedidos")
        st.caption(f"**Colaboradores carregados:** {len(colab) if colab is not None and not colab.empty else 0}")
        if colab is not None and not colab.empty:
            st.caption(f"**Líderes no colab:** {sorted(colab['lider'].dropna().unique().tolist())}")
            st.caption(f"**Líderes no BKO:** {lideres}")
        for lider, d in dados.items():
            st.caption(f"→ **{lider}**: {d['n_vendedores']} vendedores | {[v['vendedor'] for v in d['vendedores']]}")

    # ── KPIs Globais ──────────────────────────────────────────────
    total_vend_all  = sum(sum(v["comiss_vend"] for v in d["vendedores"]) for d in dados.values())
    total_lider_all = sum(d["total_comiss_lider"] for d in dados.values())
    total_bateram   = sum(d["n_bateram"] for d in dados.values())
    total_vends     = sum(d["n_vendedores"] for d in dados.values())

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(f"""<div class="kpi-mini green">
          <div class="kpi-label">💰 Comiss. Vendedores</div>
          <div class="kpi-value" style="font-size:1.3rem">R$ {total_vend_all:,.2f}</div>
          <div class="kpi-sub">total projetado</div>
        </div>""", unsafe_allow_html=True)
    with k2:
        st.markdown(f"""<div class="kpi-mini gold">
          <div class="kpi-label">🏆 Comiss. Líderes</div>
          <div class="kpi-value" style="font-size:1.3rem">R$ {total_lider_all:,.2f}</div>
          <div class="kpi-sub">50% dos vendedores que bateram</div>
        </div>""", unsafe_allow_html=True)
    with k3:
        st.markdown(f"""<div class="kpi-mini blue">
          <div class="kpi-label">✅ Bateram a Meta</div>
          <div class="kpi-value">{total_bateram}</div>
          <div class="kpi-sub">de {total_vends} vendedores</div>
        </div>""", unsafe_allow_html=True)
    with k4:
        taxa = round(total_bateram / total_vends * 100) if total_vends > 0 else 0
        st.markdown(f"""<div class="kpi-mini {'green' if taxa >= 70 else 'amber' if taxa >= 40 else 'red'}">
          <div class="kpi-label">📊 Taxa de Atingimento</div>
          <div class="kpi-value">{taxa}%</div>
          <div class="kpi-sub">vendedores acima da meta</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("")
    st.markdown("---")

    # ── Visão por Equipe ──────────────────────────────────────────
    tab_equipes, tab_consolidado = st.tabs([
        "👥 Por Equipe (Líder + Vendedores)",
        "📊 Consolidado Geral"
    ])

    with tab_equipes:
        for lider, d in dados.items():
            pct_lider = min(int(d["rec_lider"] / d["meta_lider"] * 100), 100) if d["meta_lider"] > 0 else 0
            cor_lider = _cor(pct_lider)
            icon_lider = "✅" if pct_lider >= 100 else "⚠️" if pct_lider >= 70 else "🔴"

            st.markdown(f"""
            <div class="comiss-card">
              <div class="comiss-lider">
                {icon_lider} {lider}
                <span style="font-size:0.75rem;color:#94a3b8;font-weight:400;margin-left:12px">
                  {d['n_bateram']}/{d['n_vendedores']} vendedores bateram a meta
                </span>
              </div>
            """, unsafe_allow_html=True)

            # Linha por vendedor
            rows_html = ""
            for v in d["vendedores"]:
                cor_v  = "#22c55e" if v["bateu"] else "#ef4444"
                icon_v = "✅" if v["bateu"] else "❌"
                bar    = _bar(v["receita"], v["meta"], cor_v, 6)
                rows_html += f"""
                <div class="comiss-row">
                  <div style="flex:1">
                    <div class="comiss-vend">{icon_v} {v['vendedor']}</div>
                    <div style="margin:4px 0 2px">{bar}</div>
                    <div style="font-size:0.67rem;color:#64748b">
                      R$ {v['receita']:,.2f} / meta R$ {v['meta']:,.0f} · {v['pct']}%
                    </div>
                  </div>
                  <div style="text-align:right;padding-left:16px;min-width:180px">
                    <div style="font-size:0.72rem;color:#94a3b8">Comiss. Vendedor</div>
                    <div class="comiss-val {'comiss-ok' if v['bateu'] else 'comiss-no'}">
                      R$ {v['comiss_vend']:,.2f}
                    </div>
                    <div style="font-size:0.72rem;color:#94a3b8;margin-top:4px">Repasse Líder (50%)</div>
                    <div class="comiss-val {'comiss-ok' if v['bateu'] else 'comiss-no'}">
                      R$ {v['comiss_lider']:,.2f}
                    </div>
                  </div>
                </div>"""

            st.markdown(rows_html, unsafe_allow_html=True)

            # Total do líder
            st.markdown(f"""
              <div class="comiss-total">
                <span class="comiss-total-label">💰 Total Comissão do Líder {lider}</span>
                <span class="comiss-total-val">R$ {d['total_comiss_lider']:,.2f}</span>
              </div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("")

    with tab_consolidado:
        # Tabela consolidada
        rows_consolidado = []
        for lider, d in dados.items():
            for v in d["vendedores"]:
                rows_consolidado.append({
                    "Líder":           lider,
                    "Vendedor":        v["vendedor"],
                    "Meta (R$)":       v["meta"],
                    "Receita (R$)":    v["receita"],
                    "% Atingimento":   v["pct"],
                    "Bateu":           "✅" if v["bateu"] else "❌",
                    "Comiss. Vend.":   v["comiss_vend"],
                    "Repasse Líder":   v["comiss_lider"],
                })

        if rows_consolidado:
            df_cons = pd.DataFrame(rows_consolidado)
            st.dataframe(
                df_cons,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Meta (R$)":     st.column_config.NumberColumn("Meta (R$)",    format="R$ %.2f"),
                    "Receita (R$)":  st.column_config.NumberColumn("Receita (R$)", format="R$ %.2f"),
                    "% Atingimento": st.column_config.NumberColumn("% Meta",       format="%d%%"),
                    "Comiss. Vend.": st.column_config.NumberColumn("Comiss. Vend.",format="R$ %.2f"),
                    "Repasse Líder": st.column_config.NumberColumn("Repasse Líder",format="R$ %.2f"),
                }
            )

            csv = df_cons.to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Exportar CSV", csv,
                f"comissionamento_{MES_ALVO.replace('/','_')}.csv", "text/csv")

    st.markdown("---")

    # ── Notificações ──────────────────────────────────────────────
    st.markdown('<p class="section-title">📣 Notificar Líderes</p>', unsafe_allow_html=True)

    telegram_lideres = _telegram_lideres()

    # Seletor de líderes para envio
    lideres_disponiveis = list(dados.keys())
    lideres_com_tg = [l for l in lideres_disponiveis if l in telegram_lideres]
    lideres_sem_tg  = [l for l in lideres_disponiveis if l not in telegram_lideres]

    if lideres_com_tg:
        lideres_selecionados = st.multiselect(
            "👥 Selecione quais líderes devem receber a notificação:",
            options=lideres_disponiveis,
            default=lideres_com_tg,
            key="sel_lideres_tg",
            help="Apenas líderes com chat_id configurado receberão pelo Telegram"
        )
        if lideres_sem_tg:
            st.caption(f"⚠️ Sem Telegram configurado: {', '.join(lideres_sem_tg)}")
    else:
        lideres_selecionados = []
        st.caption("⚠️ Configure os chat_ids dos líderes nos secrets do Streamlit para habilitar o Telegram.")

    c_toggle, c_email_btn, c_tg_btn = st.columns([1, 1, 1])

    with c_toggle:
        modo_teste = st.toggle("🧪 Só para mim", value=True, key="toggle_comiss",
            help="Ativado = envia só para hugo@connectgroup.solutions | Desativado = envia para os líderes")

    with c_email_btn:
        enviar_email = st.button("📧 Enviar por E-mail", type="primary",
            use_container_width=True, key="btn_email_comiss")

    with c_tg_btn:
        enviar_tg = st.button("✈️ Enviar pelo Telegram", type="secondary",
            use_container_width=True, key="btn_tg_comiss",
            disabled=len(lideres_selecionados) == 0)

    # ── E-mail ────────────────────────────────────────────────────
    if enviar_email:
        dest_lista = DESTINATARIOS_TESTE if modo_teste else DESTINATARIOS_FULL
        with st.spinner("Enviando e-mail..."):
            try:
                import smtplib
                from email.mime.multipart import MIMEMultipart as _MM
                from email.mime.text import MIMEText as _MT
                from datetime import datetime as _dt

                agora = _dt.now().strftime("%d/%m/%Y às %H:%M")

                # Monta HTML do e-mail
                rows_html_email = ""
                for lider, d in dados.items():
                    rows_html_email += f"""
                    <tr style="background:#f0fdf4">
                      <td colspan="5" style="padding:8px 10px;font-weight:bold;color:#15803d;border:1px solid #ddd">
                        👤 {lider} — Comissão Total: R$ {d['total_comiss_lider']:,.2f}
                      </td>
                    </tr>"""
                    for v in d["vendedores"]:
                        cor_e = "#15803d" if v["bateu"] else "#dc2626"
                        rows_html_email += f"""
                        <tr>
                          <td style="padding:6px 10px;border:1px solid #ddd">{v['vendedor']}</td>
                          <td style="padding:6px 10px;border:1px solid #ddd;text-align:right">R$ {v['meta']:,.2f}</td>
                          <td style="padding:6px 10px;border:1px solid #ddd;text-align:right">R$ {v['receita']:,.2f}</td>
                          <td style="padding:6px 10px;border:1px solid #ddd;text-align:center;color:{cor_e};font-weight:bold">{'✅' if v['bateu'] else '❌'} {v['pct']}%</td>
                          <td style="padding:6px 10px;border:1px solid #ddd;text-align:right;font-weight:bold;color:{cor_e}">R$ {v['comiss_lider']:,.2f}</td>
                        </tr>"""

                html = f"""<html><body style="font-family:Arial,sans-serif;color:#333;max-width:900px">
                  <div style="background:linear-gradient(135deg,#0d2b1a,#15803d);padding:20px 30px;border-radius:10px;margin-bottom:24px">
                    <h2 style="color:#fff;margin:0">💰 Projeção de Comissionamento — Connect Group</h2>
                    <p style="color:rgba(255,255,255,0.75);margin:6px 0 0">{MES_ALVO} · Gerado em {agora}</p>
                  </div>
                  <table style="border-collapse:collapse;width:100%;font-size:13px">
                    <tr style="background:#14532d;color:#fff">
                      <th style="padding:8px 10px;text-align:left">Vendedor</th>
                      <th style="padding:8px 10px;text-align:right">Meta</th>
                      <th style="padding:8px 10px;text-align:right">Receita</th>
                      <th style="padding:8px 10px;text-align:center">Atingimento</th>
                      <th style="padding:8px 10px;text-align:right">Repasse Líder (50%)</th>
                    </tr>
                    {rows_html_email}
                  </table>
                  <br>
                  <div style="background:#f0fdf4;border:1px solid #86efac;border-radius:8px;padding:16px;margin-top:16px">
                    <strong>💰 Total Comissão Vendedores: R$ {total_vend_all:,.2f}</strong><br>
                    <strong>🏆 Total Repasse Líderes: R$ {total_lider_all:,.2f}</strong>
                  </div>
                  <hr><p style="font-size:11px;color:#999">Mensagem automática — dashboard Connect Group</p>
                </body></html>"""

                cfg = st.secrets["email"]
                msg = _MM("alternative")
                msg["Subject"] = f"[Connect Group] Comissionamento {MES_ALVO}"
                msg["From"]    = cfg.get("from", cfg["user"])
                msg["To"]      = ", ".join(dest_lista)
                msg.attach(_MT(html, "html"))

                with smtplib.SMTP_SSL(cfg["host"], int(cfg["port"]), timeout=20) as sv:
                    sv.login(cfg["user"], cfg["password"])
                    sv.sendmail(cfg["user"], dest_lista, msg.as_string())

                st.success(f"✅ E-mail enviado para: {', '.join(dest_lista)}")
            except Exception as e:
                st.error(f"❌ Erro ao enviar e-mail: {e}")

    # ── Telegram ──────────────────────────────────────────────────
    if enviar_tg and lideres_selecionados:
        resultados_tg = {}
        # Carrega admin_lideres antes do loop
        try:
            admin_lideres = dict(st.secrets.get("telegram", {}).get("admin", {}))
        except Exception:
            admin_lideres = {}

        # Carrega resumo do discador
        disc_df = load_discador_resumo()
        disc_resumo = resumo_discador_por_lider(disc_df, colab) if not disc_df.empty else {}

        with st.spinner("Enviando pelo Telegram..."):
            for lider in lideres_selecionados:
                d = dados.get(lider)
                if not d:
                    continue
                chat_id = telegram_lideres.get(lider)
                if not chat_id:
                    resultados_tg[lider] = "⚠️ chat_id não configurado"
                    continue

                # Monta linhas de vendedores (comissionamento)
                linhas_vend = ""
                for v in d["vendedores"]:
                    icon  = "✅" if v["bateu"] else "❌"
                    falta = max(v["meta"] - v["receita"], 0)
                    info_falta = f" | falta R$ {falta:,.2f}" if not v["bateu"] and falta > 0 else ""
                    linhas_vend += f"\n  {icon} <b>{v['vendedor']}</b>: R$ {v['receita']:,.2f} ({v['pct']}%){info_falta}"
                    if v["bateu"]:
                        linhas_vend += f" → repasse R$ {v['comiss_lider']:,.2f}"

                # Calcula pipeline da equipe deste líder
                df_pip_lider = df[
                    (df["lider"] == lider) &
                    (df["mes_ativacao"].isna())
                ]
                rec_pip_total = df_pip_lider["preco_oferta"].sum()
                n_pip = int(df_pip_lider["acessos"].sum())

                pip_por_vend = df_pip_lider.groupby("vendedor_real")["preco_oferta"].sum()
                linhas_pip = ""
                for v in d["vendedores"]:
                    if not v["bateu"]:
                        pip_vend = pip_por_vend.get(v["vendedor"], 0)
                        falta    = max(v["meta"] - v["receita"], 0)
                        if pip_vend > 0:
                            cobre = "✅ cobre a meta!" if pip_vend >= falta else f"⚡ cobre {min(int(pip_vend/falta*100),100)}% do que falta"
                            linhas_pip += f"\n  ⏳ <b>{v['vendedor']}</b>: R$ {pip_vend:,.2f} tramitando → {cobre}"

                if linhas_pip:
                    pip_section = f"\n\n⏳ <b>Pipeline que pode fechar a meta:</b>{linhas_pip}"
                elif rec_pip_total > 0:
                    pip_section = f"\n\n⏳ <b>Pipeline da equipe:</b> R$ {rec_pip_total:,.2f} ({n_pip} acessos tramitando)"
                else:
                    pip_section = "\n\n⏳ <i>Sem pedidos tramitando no momento.</i>"

                # Status da equipe
                falta_equipe = max(d["meta_lider"] - d["rec_lider"], 0)
                pct_eq = min(int(d["rec_lider"] / d["meta_lider"] * 100), 100) if d["meta_lider"] > 0 else 0
                status_equipe = "✅ Meta atingida!" if falta_equipe == 0 else f"🎯 Falta R$ {falta_equipe:,.2f} para meta da equipe"

                # ── Resumo de ligações do discador ─────────────────
                disc_section = ""
                vends_disc = disc_resumo.get(lider, [])
                if vends_disc:
                    hoje_total   = sum(v["hoje_total"]   for v in vends_disc)
                    hoje_contato = sum(v["hoje_contato"] for v in vends_disc)
                    hoje_prop    = sum(v["hoje_proposta"] for v in vends_disc)
                    tx_hoje = round(hoje_contato / hoje_total * 100, 1) if hoje_total > 0 else 0

                    linhas_disc = ""
                    for v in vends_disc:
                        if v["hoje_total"] > 0:
                            tx_v = round(v["hoje_contato"] / v["hoje_total"] * 100, 1) if v["hoje_total"] > 0 else 0
                            linhas_disc += f"\n  📞 <b>{v['vendedor']}</b>: {v['hoje_total']} lig. · ✅ {v['hoje_contato']} contatos ({tx_v}%) · 💬 {v['hoje_proposta']} propostas"
                        else:
                            linhas_disc += f"\n  ⚪ <b>{v['vendedor']}</b>: sem ligações hoje"

                    disc_section = f"""

📞 <b>Discador — Hoje:</b>
• Total: {hoje_total} lig. · ✅ {hoje_contato} contatos ({tx_hoje}%) · 💬 {hoje_prop} propostas{linhas_disc}"""

                mensagem = f"""💰 <b>Comissionamento {MES_ALVO} — {lider}</b>

📊 <b>Resumo da equipe ({pct_eq}%):</b>
• Vendedores: {d['n_vendedores']} | Bateram meta: {d['n_bateram']}
• Receita ativada: R$ {d['rec_lider']:,.2f} / R$ {d['meta_lider']:,.2f}
• {status_equipe}
• 🏆 <b>Sua comissão estimada: R$ {d['total_comiss_lider']:,.2f}</b>

👥 <b>Por vendedor:</b>{linhas_vend}{pip_section}{disc_section}

📅 <i>{MES_ALVO} · Connect Group</i>"""

                ok = enviar_telegram(str(chat_id), mensagem)
                resultados_tg[lider] = "✅ Enviado" if ok else "❌ Falha no envio"

                # Envia cópia para o admin com indicação de qual líder recebeu
                for nome_admin, chat_admin in admin_lideres.items():
                    msg_copia = f"📋 <b>[CÓPIA — enviado para {lider}]</b>\n\n{mensagem}"
                    enviar_telegram(str(chat_admin), msg_copia)

        for lider, status in resultados_tg.items():
            st.caption(f"{status} → {lider}")

        # Envia resumo consolidado para o admin
        if admin_lideres:
            linhas_admin = ""
            total_comiss_geral = 0
            for lider, d in dados.items():
                pct_eq = min(int(d["rec_lider"] / d["meta_lider"] * 100), 100) if d["meta_lider"] > 0 else 0
                icon   = "✅" if pct_eq >= 100 else "⚠️" if pct_eq >= 70 else "🔴"
                total_comiss_geral += d["total_comiss_lider"]
                linhas_admin += f"\n{icon} <b>{lider}</b>: {d['n_bateram']}/{d['n_vendedores']} · R$ {d['rec_lider']:,.2f} ({pct_eq}%) · comiss. R$ {d['total_comiss_lider']:,.2f}"

            msg_admin = f"""📋 <b>Resumo Geral Comissionamento {MES_ALVO}</b>

👥 <b>Por equipe:</b>{linhas_admin}

💰 <b>Total repasse líderes: R$ {total_comiss_geral:,.2f}</b>
📅 <i>{MES_ALVO} · Connect Group</i>"""

            for nome_admin, chat_admin in admin_lideres.items():
                ok_admin = enviar_telegram(str(chat_admin), msg_admin)
                st.caption(f"{'✅' if ok_admin else '❌'} Resumo admin enviado → {nome_admin}")


def render_equipe(df_eq, lider, meta_dict):
    ac_ativ  = int(df_eq[df_eq["mes_ativacao"] == MES_ALVO]["acessos"].sum())
    rec_ativ = df_eq[df_eq["mes_ativacao"] == MES_ALVO]["preco_oferta"].sum()
    pipeline = int(df_eq[df_eq["mes_ativacao"].isna()]["acessos"].sum())
    n_vend   = df_eq["vendedor_real"].nunique()
    meta_eq  = sum(_meta_vend(v, meta_dict) for v in df_eq["vendedor_real"].unique()) if meta_dict else n_vend * META_VENDEDOR_PAD
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
        rank["% Meta"] = rank.apply(
            lambda row: f"{min(int(row['Receita'] / _meta_vend(row['vendedor_real'], meta_dict) * 100), 100)}%"
            if _meta_vend(row['vendedor_real'], meta_dict) > 0 else "—", axis=1
        )
        st.dataframe(rank, use_container_width=True, hide_index=True,
            column_config={"vendedor_real":"Vendedor",
                "Ativados":st.column_config.NumberColumn("✅ Ativados",format="%d"),
                "Pipeline":st.column_config.NumberColumn("⏳ Pipeline",format="%d"),
                "Receita":st.column_config.NumberColumn("R$ Receita",format="R$ %.2f"),
                "% Meta":"% Meta"})

    st.markdown('<hr class="divider">', unsafe_allow_html=True)


def _fila_badge(fila: str) -> str:
    """Retorna badge HTML colorido para o status de fila."""
    fila = str(fila).strip().upper() if fila else "—"
    cfg = STATUS_COLORS.get(fila, STATUS_COLORS.get("ENTRANTE", {}))
    cor = cfg.get("border", "#64748b")
    icon = cfg.get("icon", "📋")
    return f'<span class="det-cliente-fila" style="background:{cor}22;color:{cor};border:1px solid {cor}55">{icon} {fila}</span>'


def _montar_mensagem_detalhado_lider(lider: str, vendedores_data: list) -> str:
    """Monta mensagem Telegram para um líder na visão DETALHADO."""
    mes = MES_ALVO
    linhas = f"📋 <b>Detalhado {mes} — {lider}</b>\n"

    for vd in vendedores_data:
        ac_atv = vd["ac_ativ"]
        ac_pip = vd["ac_pip"]
        rec    = vd["rec"]
        clientes = vd["clientes"]

        linhas += f"\n👤 <b>{vd['nome']}</b>"
        linhas += f"\n   ✅ {ac_atv} atv · ⏳ {ac_pip} pip · 💰 R$ {rec:,.2f}\n"

        if clientes:
            for c in clientes:
                linhas += f"   • {c['razao']} — {c['ac']} ac · R$ {c['rec']:,.2f} · {c['fila']}\n"
        else:
            linhas += "   <i>Sem pedidos tramitando.</i>\n"

    linhas += f"\n📅 <i>{mes} · Connect Group</i>"
    return linhas


def render_detalhado(df_full, bko, lideres, meta_dict, colab, parceiro_sel):
    """Aba DETALHADO: Parceiro → Líder → Vendedor → Clientes tramitando."""
    st.markdown('<p class="section-title">📋 Visão Detalhada — Pedidos em Tramitação por Vendedor</p>',
                unsafe_allow_html=True)

    # ── Dados filtrados: todos os pedidos do mês (ativados + pipeline) ──
    df = df_full.copy()
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

    # Parceiros disponíveis
    parceiros_disp = sorted(df["parceiro"].dropna().unique().tolist()) if "parceiro" in df.columns else ["—"]
    if "Todos" in (parceiro_sel or ""):
        parceiros_loop = parceiros_disp
    else:
        parceiros_loop = [parceiro_sel] if parceiro_sel in parceiros_disp else parceiros_disp

    # Mapa vendedor → parceiro (via colab se disponível)
    parc_map = {}
    if colab is not None and not colab.empty and "parceiro" in colab.columns:
        for _, row in colab.iterrows():
            parc_map[str(row.get("vendedor","")).strip()] = str(row.get("parceiro","")).strip()

    # Telegram setup
    telegram_lideres = _telegram_lideres()
    try:
        admin_lideres = dict(st.secrets.get("telegram", {}).get("admin", {}))
    except Exception:
        admin_lideres = {}

    # ── Controles de envio Telegram ──
    col_tg1, col_tg2, col_tg3 = st.columns([2, 1, 2])
    with col_tg1:
        lideres_validos = [l for l in lideres if l != "Sem Equipe"]
        lideres_det_sel = st.multiselect(
            "📤 Selecionar líderes para enviar pelo Telegram",
            options=lideres_validos,
            default=[],
            key="det_tg_lideres"
        )
    with col_tg2:
        modo_teste_det = st.toggle("🧪 Só para mim", value=True, key="det_tg_teste",
            help="Ativado = envia só para o admin")
        enviar_det_tg = st.button("📨 Enviar Telegram", type="primary",
                                   use_container_width=True, key="det_tg_btn",
                                   disabled=not lideres_det_sel)
    with col_tg3:
        if lideres_det_sel:
            destinos_str = ", ".join(lideres_det_sel)
            st.markdown(f"""<div style="padding:8px 0;color:#94a3b8;font-size:0.78rem">
              {'🧪 Enviando só para admin' if modo_teste_det else f'📢 Enviando para: <b style="color:#e2e8f0">{destinos_str}</b>'}
            </div>""", unsafe_allow_html=True)

    st.markdown("---")

    # ── Renderização hierárquica ──
    dados_por_lider_tg: dict = {}  # acumula para o envio

    for parceiro in parceiros_loop:
        df_parc = df[df["parceiro"] == parceiro] if "parceiro" in df.columns else df
        if df_parc.empty:
            continue

        lideres_parc = sorted([l for l in df_parc["lider"].unique() if l not in ("Sem Equipe", "")])
        ac_parc = int(df_parc["acessos"].sum())
        rec_parc = df_parc[df_parc["mes_ativacao"] == MES_ALVO]["preco_oferta"].sum()
        pip_parc = int(df_parc[df_parc["mes_ativacao"].isna()]["acessos"].sum())

        st.markdown(f"""<div class="det-parceiro">
          <span class="det-parceiro-nome">🏢 {parceiro}</span>
          <span class="det-parceiro-stats">
            {len(lideres_parc)} equipe(s) · ✅ {ac_parc} ac · ⏳ {pip_parc} pip · 💰 R$ {rec_parc:,.2f}
          </span>
        </div>""", unsafe_allow_html=True)

        for lider in lideres_parc:
            df_lid = df_parc[df_parc["lider"] == lider]
            ac_lid = int(df_lid[df_lid["mes_ativacao"] == MES_ALVO]["acessos"].sum())
            pip_lid = int(df_lid[df_lid["mes_ativacao"].isna()]["acessos"].sum())
            rec_lid = df_lid[df_lid["mes_ativacao"] == MES_ALVO]["preco_oferta"].sum()
            vends_lid = sorted([v for v in df_lid["vendedor_real"].unique() if v not in ("Sem Vendedor", "")])

            st.markdown(f"""<div class="det-lider">
              <span class="det-lider-nome">👤 {lider}</span>
              <span class="det-lider-stats">
                {len(vends_lid)} vend. · ✅ {ac_lid} atv · ⏳ {pip_lid} pip · 💰 R$ {rec_lid:,.2f}
              </span>
            </div>""", unsafe_allow_html=True)

            vendedores_data_tg = []

            for vend in vends_lid:
                df_vend = df_lid[df_lid["vendedor_real"] == vend]
                ac_atv_v = int(df_vend[df_vend["mes_ativacao"] == MES_ALVO]["acessos"].sum())
                ac_pip_v = int(df_vend[df_vend["mes_ativacao"].isna()]["acessos"].sum())
                rec_v = df_vend[df_vend["mes_ativacao"] == MES_ALVO]["preco_oferta"].sum()

                # Clientes: todos os pedidos (ativados e tramitando) ordenados por fila
                clientes_df = df_vend.copy()
                if "razao_social" not in clientes_df.columns:
                    clientes_df["razao_social"] = "—"

                clientes_rows = (clientes_df
                    .groupby(["razao_social","fila_atual","status_dash"], as_index=False)
                    .agg(ac=("acessos","sum"), rec=("preco_oferta","sum"))
                    .sort_values("ac", ascending=False))

                # Build HTML de clientes
                clientes_html = ""
                clientes_tg_list = []
                for _, crow in clientes_rows.iterrows():
                    razao = str(crow.get("razao_social", "—"))[:45]
                    fila  = str(crow.get("fila_atual", "—"))
                    ac_c  = int(crow.get("ac", 0))
                    rec_c = float(crow.get("rec", 0))
                    badge = _fila_badge(fila)
                    clientes_html += f"""
                    <div class="det-cliente-row">
                      <span class="det-cliente-nome" title="{razao}">{razao}</span>
                      <span class="det-cliente-stats">
                        <span class="det-cliente-ac">🔢 {ac_c} ac</span>
                        <span class="det-cliente-rec">💰 R$ {rec_c:,.2f}</span>
                        {badge}
                      </span>
                    </div>"""
                    clientes_tg_list.append({"razao": razao, "ac": ac_c, "rec": rec_c, "fila": fila})

                if not clientes_html:
                    clientes_html = '<div class="det-empty">Sem pedidos no mês.</div>'

                meta_v = _meta_vend(vend, meta_dict)
                pct_v  = min(int(rec_v / meta_v * 100), 100) if meta_v > 0 else 0
                cor_v  = _cor(pct_v)

                st.markdown(f"""<div class="det-vendedor">
                  <div class="det-vend-header">
                    <span class="det-vend-nome">📌 {vend}</span>
                    <span class="det-vend-kpis">
                      <span>✅ Atv: <span class="det-vend-kpi-val">{ac_atv_v}</span></span>
                      <span>⏳ Pip: <span class="det-vend-kpi-val">{ac_pip_v}</span></span>
                      <span>💰 <span class="det-vend-kpi-val" style="color:{cor_v}">R$ {rec_v:,.2f} ({pct_v}%)</span></span>
                    </span>
                  </div>
                  {clientes_html}
                </div>""", unsafe_allow_html=True)

                vendedores_data_tg.append({
                    "nome": vend,
                    "ac_ativ": ac_atv_v,
                    "ac_pip": ac_pip_v,
                    "rec": rec_v,
                    "clientes": clientes_tg_list,
                })

            dados_por_lider_tg[lider] = vendedores_data_tg

        st.markdown("")

    # ── Envio Telegram ──
    if enviar_det_tg and lideres_det_sel:
        resultados_tg = {}
        with st.spinner("Enviando pelo Telegram..."):
            for lider in lideres_det_sel:
                vds = dados_por_lider_tg.get(lider, [])
                mensagem = _montar_mensagem_detalhado_lider(lider, vds)

                if modo_teste_det:
                    # Envia só para admins
                    ok = False
                    for nome_admin, chat_admin in admin_lideres.items():
                        ok = enviar_telegram(str(chat_admin), f"🧪 [TESTE — {lider}]\n\n{mensagem}")
                    if not admin_lideres:
                        ok = enviar_telegram("7776803920", mensagem)  # fallback
                    resultados_tg[lider] = "✅ Enviado (admin)" if ok else "❌ Falha"
                else:
                    chat_id = telegram_lideres.get(lider)
                    if chat_id:
                        ok = enviar_telegram(str(chat_id), mensagem)
                        resultados_tg[lider] = "✅ Enviado" if ok else "❌ Falha"
                        # Cópia para admins
                        for nome_admin, chat_admin in admin_lideres.items():
                            enviar_telegram(str(chat_admin), f"📋 [CÓPIA — {lider}]\n\n{mensagem}")
                    else:
                        resultados_tg[lider] = "⚠️ chat_id não configurado"

        for lider, status in resultados_tg.items():
            st.caption(f"{status} → {lider}")


def main():
    mes_str = MESES_PT.get(datetime.now().strftime("%m"), "") + "/" + datetime.now().strftime("%Y")
    st.markdown(f"""<div class="header-perf">
      <div>
        <p class="header-title">🏆 PERFORMANCE — CONNECT GROUP</p>
        <p class="header-sub">TIM Corporate · Ranking de Vendedores · {mes_str}</p>
      </div>
      <div class="header-right">
        <img src="https://raw.githubusercontent.com/hugokhesley/dashboard-tim-connectgroup-sheets/main/logo.png" class="header-logo" onerror="this.style.display='none'">
        <span class="header-badge">🏆 PERFORMANCE</span>
      </div>
    </div></div>""", unsafe_allow_html=True)

    with st.spinner("Carregando dados..."):
        raw   = load_data()
        bko   = load_bko()
        colab = load_colaboradores()

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
        st.markdown(f"**Meta/Vendedor:** `R$ {META_VENDEDOR_PAD:,}`")
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

    meta_dict = dict(zip(colab["vendedor"], colab["meta"])) if not colab.empty else {}

    # ── TABS PRINCIPAIS ───────────────────────────────────────────
    tab_perf, tab_comiss, tab_det = st.tabs([
        "🏆 Performance",
        "💰 Comissionamento",
        "📋 Detalhado",
    ])

    with tab_perf:
        # KPIs globais
        st.markdown('<p class="section-title">📈 Visão Consolidada</p>', unsafe_allow_html=True)
        atv_g  = df[df["mes_ativacao"] == MES_ALVO]
        ac_g   = int(atv_g["acessos"].sum())
        rec_g  = atv_g["preco_oferta"].sum()
        pip_g  = int(df[df["mes_ativacao"].isna()]["acessos"].sum())
        nv_g   = df["vendedor_real"].nunique()
        meta_g = sum(_meta_vend(v, meta_dict) for v in df["vendedor_real"].unique()) if meta_dict else nv_g * META_VENDEDOR_PAD
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
        render_visual(df, lideres, lider_sel, meta_dict)

        st.markdown('<p class="section-title">👤 Desempenho por Equipe — Kanban</p>', unsafe_allow_html=True)
        for lider in lideres:
            render_equipe(df[df["lider"] == lider].copy(), lider, meta_dict)

        # Vendedores zerados
        st.markdown('<p class="section-title">🔴 Vendedores Sem Ativação no Mês</p>', unsafe_allow_html=True)

        if not colab.empty:
            colab_fil = colab.copy()
            if lider_sel != "Todos":
                colab_fil = colab_fil[colab_fil["lider"] == lider_sel]

            ser_atv = df[df["mes_ativacao"] == MES_ALVO].groupby("vendedor_real")["preco_oferta"].sum()

            colab_fil["receita"] = colab_fil["vendedor"].map(ser_atv).fillna(0)
            zerados   = colab_fil[colab_fil["receita"] == 0].sort_values("vendedor")
            parciais  = colab_fil[(colab_fil["receita"] > 0) & (colab_fil["receita"] < colab_fil["meta"])].sort_values("receita")
            bateram   = colab_fil[colab_fil["receita"] >= colab_fil["meta"]].sort_values("receita", ascending=False)

            z1, z2, z3 = st.columns(3)
            with z1:
                st.markdown(f"""<div class="kpi-mini red">
                  <div class="kpi-label">🔴 Zerados</div>
                  <div class="kpi-value">{len(zerados)}</div>
                  <div class="kpi-sub">sem nenhuma ativação</div>
                </div>""", unsafe_allow_html=True)
            with z2:
                st.markdown(f"""<div class="kpi-mini amber">
                  <div class="kpi-label">🟡 Abaixo da Meta</div>
                  <div class="kpi-value">{len(parciais)}</div>
                  <div class="kpi-sub">ativaram mas não bateram</div>
                </div>""", unsafe_allow_html=True)
            with z3:
                st.markdown(f"""<div class="kpi-mini green">
                  <div class="kpi-label">🟢 Bateram a Meta</div>
                  <div class="kpi-value">{len(bateram)}</div>
                  <div class="kpi-sub">acima de R$ {META_VENDEDOR_PAD:,}</div>
                </div>""", unsafe_allow_html=True)

            st.markdown("")

            tab_z1, tab_z2, tab_z3 = st.tabs([
                f"🔴 Zerados ({len(zerados)})",
                f"🟡 Abaixo da Meta ({len(parciais)})",
                f"🟢 Bateram ({len(bateram)})"
            ])

            def _render_vend_table(dff):
                if dff.empty:
                    st.success("Nenhum vendedor nesta categoria.")
                    return
                rows_html = ""
                for _, row in dff.iterrows():
                    pct = min(int(row["receita"] / row["meta"] * 100), 100) if row["meta"] > 0 else 0
                    cor = _cor(pct)
                    bar = _bar(row["receita"], row["meta"], cor, 8)
                    rows_html += f"""
                    <div style="padding:10px 0;border-bottom:1px solid #1e293b">
                      <div style="display:flex;justify-content:space-between;margin-bottom:4px">
                        <span style="font-size:0.85rem;font-weight:600;color:#e2e8f0">{row['vendedor']}</span>
                        <span style="font-size:0.82rem;color:{cor};font-weight:700">R$ {row['receita']:,.2f} <span style="color:#64748b">({pct}%)</span></span>
                      </div>
                      {bar}
                      <div style="font-size:0.68rem;color:#64748b;margin-top:2px">{row['lider'] if row['lider'] else '—'} · meta R$ {row['meta']:,.0f}</div>
                    </div>"""
                st.markdown(f'<div style="max-height:400px;overflow-y:auto">{rows_html}</div>', unsafe_allow_html=True)

            with tab_z1:
                _render_vend_table(zerados)
            with tab_z2:
                _render_vend_table(parciais)
            with tab_z3:
                _render_vend_table(bateram)
        else:
            st.info("Aba Colaboradores não encontrada ou sem dados.")

        st.markdown('<hr class="divider">', unsafe_allow_html=True)

        # Pendências BKO
        st.markdown('<p class="section-title">⚠️ Pendências de Cadastro no BKO</p>', unsafe_allow_html=True)

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

        df_nan = (df_full[df_full["vendedor_real"] == ""][COLS_SHOW]
                  .drop_duplicates(subset=["pedido"]).copy()) if "pedido" in df_full.columns else pd.DataFrame()
        df_seq = (df_full[df_full["lider"] == "Sem Equipe"][COLS_SHOW + ["vendedor_real"]]
                  .drop_duplicates(subset=["pedido"]).copy()) if "Sem Equipe" in df_full["lider"].values and "pedido" in df_full.columns else pd.DataFrame()

        tab_nan, tab_seq = st.tabs(["❓ Não cadastrados no BKO", "👤 Sem Equipe (BKO sem Líder)"])

        with tab_nan:
            if df_nan.empty:
                st.success("✅ Todos os pedidos estão cadastrados no BKO!")
            else:
                st.warning(f"**{len(df_nan)} pedido(s)** sem cadastro no BKO-VENDEDOR-REAL.")
                st.dataframe(df_nan, use_container_width=True, hide_index=True, column_config=COL_CFG)
                csv = df_nan.to_csv(index=False).encode("utf-8")
                st.download_button("⬇️ Exportar (.csv)", data=csv,
                    file_name=f"sem_bko_{MES_ALVO.replace('/','_')}.csv", mime="text/csv")

        with tab_seq:
            if df_seq.empty:
                st.success("✅ Todos os pedidos cadastrados no BKO têm equipe definida!")
            else:
                st.warning(f"**{len(df_seq)} pedido(s)** com vendedor no BKO mas sem líder definido.")
                st.dataframe(df_seq, use_container_width=True, hide_index=True,
                    column_config={**COL_CFG, "vendedor_real": "Vendedor Real"})
                csv2 = df_seq.to_csv(index=False).encode("utf-8")
                st.download_button("⬇️ Exportar (.csv)", data=csv2,
                    file_name=f"sem_equipe_{MES_ALVO.replace('/','_')}.csv", mime="text/csv")

        st.markdown("")
        total_pend = len(df_nan) + len(df_seq)
        st.markdown("---")
        if total_pend > 0:
            c_toggle, c_btn, c_info = st.columns([1, 1, 3])
            with c_toggle:
                modo_teste_bko = st.toggle("🧪 Só para mim", value=True,
                    help="Ativado = envia só para hugo@connectgroup.solutions")
            with c_btn:
                enviar_bko = st.button("📧 Notificar por E-mail", type="primary", use_container_width=True)
            with c_info:
                dest_lista_bko = DESTINATARIOS_TESTE if modo_teste_bko else DESTINATARIOS_FULL
                st.markdown(f"""<div style="padding:8px 0;color:#94a3b8;font-size:0.8rem">
                  {'🧪 Modo teste — ' if modo_teste_bko else '📢 Envio completo — '}
                  <strong style="color:#e2e8f0">{' · '.join(dest_lista_bko)}</strong>
                </div>""", unsafe_allow_html=True)
            if enviar_bko:
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

                        html = f"""<html><body style="font-family:Arial,sans-serif;color:#333;max-width:900px">
                          <div style="background:linear-gradient(135deg,#0d2b1a,#15803d);padding:20px 30px;border-radius:10px;margin-bottom:24px">
                            <h2 style="color:#fff;margin:0">⚠️ Pendências BKO — Connect Group</h2>
                            <p style="color:rgba(255,255,255,0.75);margin:6px 0 0">{MES_ALVO} · Gerado em {agora}</p>
                          </div>
                          {_tab(df_nan_e,"❓ Pedidos sem Vendedor Real no BKO","#dc2626")}
                          {_tab(df_seq_e,"👤 Pedidos sem Líder definido","#d97706")}
                          <br>
                          <div style="background:#f0fdf4;border:1px solid #86efac;border-radius:8px;padding:16px 20px;margin:16px 0">
                            <a href="{BKO_URL}" style="color:#15803d;font-weight:bold">👉 Clique aqui para abrir o BKO-VENDEDOR-REAL</a>
                          </div>
                          <hr><p style="font-size:11px;color:#999">Mensagem automática — dashboard Connect Group</p>
                        </body></html>"""

                        import smtplib
                        from email.mime.multipart import MIMEMultipart as _MM
                        from email.mime.text import MIMEText as _MT

                        cfg = st.secrets["email"]
                        msg = _MM("alternative")
                        msg["Subject"] = f"[Connect Group] Pendências BKO — {MES_ALVO} ({total_pend} itens)"
                        msg["From"]    = cfg.get("from", cfg["user"])
                        msg["To"]      = ", ".join(dest_lista_bko)
                        msg.attach(_MT(html, "html"))

                        with smtplib.SMTP_SSL(cfg["host"], int(cfg["port"]), timeout=20) as sv:
                            sv.login(cfg["user"], cfg["password"])
                            sv.sendmail(cfg["user"], dest_lista_bko, msg.as_string())

                        st.success(f"✅ E-mail enviado para: {', '.join(dest_lista_bko)}")

                        if not df_nan_e.empty and "pedido" in df_nan_e.columns:
                            cols_bko = [c for c in ["pedido", "razao_social"] if c in df_nan_e.columns]
                            ok_bko, msg_bko = inserir_pendentes_bko(df_nan_e[cols_bko].copy(), MES_ALVO)
                            st.cache_data.clear()
                            if ok_bko:
                                st.info(f"📋 {msg_bko}")
                            else:
                                st.warning(f"⚠️ {msg_bko}")

                    except Exception as e:
                        st.error(f"❌ Erro ao enviar: {e}")
        else:
            st.success("✅ Sem pendências — nenhum e-mail necessário.")

    # ── TAB COMISSIONAMENTO ───────────────────────────────────────
    with tab_comiss:
        render_comissionamento(df, lideres, meta_dict, colab=colab)

    # ── TAB DETALHADO ─────────────────────────────────────────────
    with tab_det:
        render_detalhado(
            df_full=apply_filters(raw.copy(), MES_ALVO, ["NOVO","ADITIVO"], parceiro_sel),
            bko=bko,
            lideres=lideres,
            meta_dict=meta_dict,
            colab=colab,
            parceiro_sel=parceiro_sel,
        )


main()
