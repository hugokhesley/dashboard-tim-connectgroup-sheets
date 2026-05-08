"""
=====================================================================
  11_Gestao_Equipe.py — Gestão de Vendas · Connect Group
=====================================================================
  Página isolada para líderes e parceiros visualizarem
  apenas suas próprias vendas (Detalhado + Atribuição).
  
  Níveis de acesso (configurados em secrets [credentials_gestao]):
    - admin   → vê tudo, filtra livremente
    - lider   → vê só a equipe definida em lider = "NOME"
    - parceiro → vê só o parceiro definido em parceiro = "NOME"
=====================================================================
"""

import streamlit as st
import pandas as pd
import io
from datetime import datetime
import streamlit_authenticator as stauth

from data_loader import (
    load_data, load_bko, load_colaboradores, apply_filters,
    get_parceiros, STATUS_COLORS, _s, _norm_pedido, get_gspread_client
)

st.set_page_config(
    page_title="Gestão de Vendas — Connect Group",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

MESES_PT = {
    "01":"Janeiro","02":"Fevereiro","03":"Março","04":"Abril",
    "05":"Maio","06":"Junho","07":"Julho","08":"Agosto",
    "09":"Setembro","10":"Outubro","11":"Novembro","12":"Dezembro"
}

MES_ALVO          = datetime.now().strftime("%m/%Y")
META_VENDEDOR_PAD = 850
SPREADSHEET_ID    = "1HmtEFf2Akh7NLR2prxDh9S4gmioKYw419B4bkx4yBLg"
LINK_ATRIBUICAO   = "https://dashboard-tim-connectgroup-sheets-yhmvrhy6akairuh3yjmbmw.streamlit.app/Atribuicao_Vendedor"

# ─────────────────────────────────────────────────────────────────
#  CSS
# ─────────────────────────────────────────────────────────────────

st.markdown("""
<style>
  [data-testid="stSidebarNav"] { display: none; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
  html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
  .stApp { background-color: #0f1117; color: #e2e8f0; }
  .header-gestao {
    background: linear-gradient(135deg, #0d2b1a 0%, #14532d 40%, #15803d 70%, #22c55e 100%);
    border-radius: 16px; padding: 24px 32px; margin-bottom: 24px;
    border: 1px solid rgba(255,255,255,0.08);
    display: flex; align-items: center; justify-content: space-between;
  }
  .header-title { font-size: 1.6rem; font-weight: 800; color: #fff; margin: 0; }
  .header-sub   { font-size: 0.82rem; color: rgba(255,255,255,0.65); margin: 4px 0 0; }
  .header-badge { background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.25); border-radius: 20px; padding: 5px 14px; font-size: 0.78rem; color: #fff; font-weight: 600; }
  .kpi-mini { background: #1a1f2e; border-radius: 12px; padding: 16px 18px; border: 1px solid #2d3748; position: relative; overflow: hidden; margin-bottom: 4px; }
  .kpi-mini::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; }
  .kpi-mini.blue::before   { background: linear-gradient(90deg, #3b82f6, #1d4ed8); }
  .kpi-mini.green::before  { background: linear-gradient(90deg, #22c55e, #15803d); }
  .kpi-mini.amber::before  { background: linear-gradient(90deg, #f59e0b, #d97706); }
  .kpi-mini.purple::before { background: linear-gradient(90deg, #8b5cf6, #6d28d9); }
  .kpi-label { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 1px; color: #94a3b8; font-weight: 600; margin-bottom: 6px; }
  .kpi-value { font-size: 1.6rem; font-weight: 800; color: #f1f5f9; line-height: 1; }
  .kpi-sub   { font-size: 0.72rem; color: #64748b; margin-top: 4px; }
  .section-title { font-size:0.75rem; text-transform:uppercase; letter-spacing:1.5px; color:#22c55e; font-weight:700; margin:24px 0 12px 0; border-left: 3px solid #22c55e; padding-left: 10px; }
  .det-parceiro { background: linear-gradient(90deg,#0d1f3c,#1e3a5f); border-left:5px solid #3b82f6; border-radius:12px; padding:14px 22px; margin:20px 0 4px 0; display:flex; align-items:center; justify-content:space-between; }
  .det-parceiro-nome  { font-size:1.05rem; font-weight:800; color:#93c5fd; }
  .det-parceiro-stats { font-size:0.78rem; color:#64748b; }
  .det-lider { background:#131f2e; border-left:4px solid #22c55e; border-radius:10px; padding:10px 18px; margin:8px 0 4px 20px; display:flex; align-items:center; justify-content:space-between; }
  .det-lider-nome  { font-size:0.92rem; font-weight:700; color:#86efac; }
  .det-lider-stats { font-size:0.75rem; color:#64748b; }
  .det-vendedor-wrap { background:#0f1820; border-left:3px solid #334155; border-radius:8px; padding:10px 16px; margin:4px 0 4px 40px; }
  .det-vend-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:10px; flex-wrap:wrap; gap:6px; }
  .det-vend-nome { font-size:0.83rem; font-weight:700; color:#e2e8f0; }
  .det-vend-kpis { display:flex; gap:0; font-size:0.74rem; background:#0a1018; border-radius:8px; overflow:hidden; border:1px solid #1e293b; }
  .det-kpi-block { display:flex; flex-direction:column; align-items:center; padding:5px 14px; border-right:1px solid #1e293b; line-height:1.3; }
  .det-kpi-block:last-child { border-right:none; }
  .det-kpi-label { font-size:0.62rem; text-transform:uppercase; letter-spacing:.7px; color:#475569; font-weight:600; }
  .det-kpi-val   { font-size:0.82rem; font-weight:700; color:#e2e8f0; margin-top:1px; }
  .det-clientes-wrap { background:#060c12; border-radius:6px; border:1px solid #1a2333; padding:6px 8px; margin-left:4px; }
  .det-cliente-row { display:flex; align-items:center; justify-content:space-between; padding:5px 10px; border-radius:5px; margin:2px 0; background:#0c1520; font-size:0.74rem; border-left:2px solid #1e293b; }
  .det-cli-nome { color:#94a3b8; flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; margin-right:12px; }
  .det-cli-stats { display:flex; gap:14px; align-items:center; flex-shrink:0; }
  .det-cli-ac   { color:#60a5fa; font-weight:600; font-size:0.73rem; }
  .det-cli-rec  { color:#4ade80; font-weight:600; font-size:0.73rem; }
  .det-cli-fila { font-size:0.66rem; padding:2px 8px; border-radius:99px; font-weight:600; }
  .det-empty { color:#475569; font-size:0.74rem; font-style:italic; padding:4px 6px; }
  .rank-bg   { background: #2d3748; border-radius: 99px; height: 8px; }
  .rank-fill { height: 8px; border-radius: 99px; }
  section[data-testid="stSidebar"] { background: #0d1a0f !important; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────
#  AUTENTICAÇÃO
# ─────────────────────────────────────────────────────────────────

def _carregar_auth():
    try:
        creds_raw = dict(st.secrets["credentials_gestao"]["usernames"])
        usernames = {}
        for user, info in creds_raw.items():
            usernames[user] = {
                "name":     info.get("name", user),
                "password": info.get("password", ""),
            }
        return {
            "credentials": {"usernames": usernames},
            "cookie":      {"name": "gestao_cookie", "key": "gestao_secret_key", "expiry_days": 1},
        }
    except Exception as e:
        st.error(f"Erro ao carregar credenciais: {e}")
        st.stop()


def _info_usuario(username: str) -> dict:
    try:
        info = dict(st.secrets["credentials_gestao"]["usernames"][username])
        return {
            "tipo":     info.get("tipo", "lider"),
            "lider":    info.get("lider", ""),
            "parceiro": info.get("parceiro", ""),
            "name":     info.get("name", username),
        }
    except Exception:
        return {"tipo": "lider", "lider": "", "parceiro": "", "name": username}


# ─────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────

def _bar(valor, maximo, cor="#22c55e", h=8):
    pct = min(int(valor / maximo * 100), 100) if maximo > 0 else 0
    return f'<div class="rank-bg"><div class="rank-fill" style="width:{pct}%;background:{cor};height:{h}px"></div></div>'

def _cor(pct):
    if pct >= 100: return "#22c55e"
    if pct >= 70:  return "#f59e0b"
    return "#ef4444"

def _meta_vend(nome, meta_dict):
    return meta_dict.get(nome, META_VENDEDOR_PAD)

def _fila_badge(fila):
    fila_up = str(fila).strip().upper() if fila else "—"
    cfg = STATUS_COLORS.get(fila_up, {"border": "#64748b", "icon": "▪️"})
    cor  = cfg.get("border", "#64748b")
    icon = cfg.get("icon", "▪️")
    return (f'<span class="det-cli-fila" '
            f'style="background:{cor}22;color:{cor};border:1px solid {cor}55">'
            f'{icon} {fila_up}</span>')

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


# ─────────────────────────────────────────────────────────────────
#  EXPORTAR PDF
# ─────────────────────────────────────────────────────────────────

def gerar_pdf(df_atv, meta_dict, mes):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT, TA_CENTER

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
        leftMargin=14*mm, rightMargin=14*mm,
        topMargin=14*mm, bottomMargin=14*mm)

    VERDE     = colors.HexColor("#22c55e")
    VERDE_ESC = colors.HexColor("#15803d")
    AZUL      = colors.HexColor("#3b82f6")
    AMBER     = colors.HexColor("#f59e0b")
    CINZA     = colors.HexColor("#64748b")
    CINZA_ESC = colors.HexColor("#1e293b")
    BRANCO    = colors.white
    FL        = colors.HexColor("#131f2e")
    FV        = colors.HexColor("#0f1820")
    FC        = colors.HexColor("#080e15")
    TEXTO     = colors.HexColor("#e2e8f0")
    TDIM      = colors.HexColor("#94a3b8")

    def s(name, **kw):
        base = {"fontName": "Helvetica", "fontSize": 9, "textColor": TEXTO, "leading": 13}
        base.update(kw)
        return ParagraphStyle(name, **base)

    sTitle = s("T", fontSize=15, fontName="Helvetica-Bold", textColor=BRANCO)
    sRight = s("R", fontSize=7,  textColor=BRANCO, alignment=TA_RIGHT)
    sLider = s("L", fontSize=9,  fontName="Helvetica-Bold", textColor=BRANCO)
    sVend  = s("V", fontSize=8,  fontName="Helvetica-Bold", textColor=TEXTO)
    sCli   = s("C", fontSize=7,  textColor=TDIM)

    story = []
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")

    # Header
    h = Table([[Paragraph(f"<b>CONNECT GROUP — Gestão de Vendas {mes}</b>", sTitle),
                Paragraph(f"Gerado em {agora}", sRight)]], colWidths=["70%","30%"])
    h.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),VERDE_ESC),
        ("ROWPADDING",(0,0),(-1,-1),10),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE")
    ]))
    story.append(h)
    story.append(Spacer(1, 6*mm))

    lideres = sorted([l for l in df_atv["lider"].dropna().unique() if l and l not in ("Sem Equipe", "")])

    for lider in lideres:
        df_l  = df_atv[df_atv["lider"] == lider]
        ac_l  = int(df_l["acessos"].sum())
        rec_l = df_l["preco_oferta"].sum()
        vends = sorted([v for v in df_l["vendedor_real"].dropna().unique() if v and v not in ("Sem Vendedor", "")])

        lr = Table([[Paragraph(f"  {lider}", sLider),
                     Paragraph(f"{len(vends)} vend.   {ac_l} ac / R$ {rec_l:,.2f}", sRight)]],
                   colWidths=["55%","45%"])
        lr.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,-1),AZUL),
            ("ROWPADDING",(0,0),(-1,-1),8),
            ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            ("LINEBELOW",(0,0),(-1,0),2,colors.HexColor("#1d4ed8"))
        ]))
        story.append(lr)

        for vend in vends:
            df_v   = df_l[df_l["vendedor_real"] == vend]
            ac_v   = int(df_v["acessos"].sum())
            rec_v  = df_v["preco_oferta"].sum()
            meta_v = _meta_vend(vend, meta_dict)
            pct_v  = min(int(rec_v / meta_v * 100), 100) if meta_v > 0 else 0
            cor_v  = VERDE if pct_v >= 100 else AMBER if pct_v >= 70 else colors.HexColor("#ef4444")

            vr = Table([[Paragraph(f"    {vend}", sVend),
                         Paragraph(f"{ac_v} ac / R$ {rec_v:,.2f} ({pct_v}%)", sRight)]],
                       colWidths=["55%","45%"])
            vr.setStyle(TableStyle([
                ("BACKGROUND",(0,0),(-1,-1),FL),
                ("ROWPADDING",(0,0),(-1,-1),6),
                ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                ("LINEBELOW",(0,0),(-1,0),0.5,CINZA_ESC),
                ("TEXTCOLOR",(1,0),(1,0),cor_v)
            ]))
            story.append(vr)

            # Clientes
            cols_grp = [c for c in ["razao_social","fila_atual"] if c in df_v.columns]
            if cols_grp:
                df_g = df_v.copy()
                for col in cols_grp:
                    df_g[col] = df_g[col].fillna("—")
                cdf = (df_g.groupby(cols_grp, as_index=False)
                       .agg(ac=("acessos","sum"), rec=("preco_oferta","sum"))
                       .sort_values("ac", ascending=False))
                for _, crow in cdf.iterrows():
                    razao = str(crow.get("razao_social","—"))[:55]
                    fila  = str(crow.get("fila_atual","—")).upper()
                    ac_c  = int(crow.get("ac",0))
                    rec_c = float(crow.get("rec",0))
                    cr = Table([[Paragraph(f"        {razao}", sCli),
                                 Paragraph(f"{ac_c} ac   R$ {rec_c:,.2f}   {fila}", sRight)]],
                               colWidths=["60%","40%"])
                    cr.setStyle(TableStyle([
                        ("BACKGROUND",(0,0),(-1,-1),FC),
                        ("ROWPADDING",(0,0),(-1,-1),3),
                        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                        ("LINEBELOW",(0,0),(-1,0),0.3,CINZA_ESC)
                    ]))
                    story.append(cr)

        story.append(Spacer(1, 4*mm))

    story.append(HRFlowable(width="100%", thickness=0.5, color=CINZA_ESC))
    story.append(Spacer(1, 1*mm))
    story.append(Paragraph(
        f"Connect Group · {mes} · {agora}",
        s("F", fontSize=6, textColor=CINZA, alignment=TA_CENTER)
    ))
    doc.build(story)
    buf.seek(0)
    return buf.read()


# ─────────────────────────────────────────────────────────────────
#  EXPORTAR EXCEL
# ─────────────────────────────────────────────────────────────────

def gerar_excel(df_atv, meta_dict, mes):
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = f"Vendas {mes.replace('/', '-')}"

    def fill(hex_color):
        return PatternFill("solid", fgColor=hex_color.replace("#",""))

    ft_title = Font(name="Calibri", bold=True, size=14, color="FFFFFF")
    ft_lider = Font(name="Calibri", bold=True, size=11, color="FFFFFF")
    ft_vend  = Font(name="Calibri", bold=True, size=10, color="E2E8F0")
    ft_cli   = Font(name="Calibri", size=9,    color="94A3B8")

    al_left  = Alignment(horizontal="left",  vertical="center")
    al_right = Alignment(horizontal="right", vertical="center")
    al_center= Alignment(horizontal="center",vertical="center")

    agora = datetime.now().strftime("%d/%m/%Y %H:%M")

    ws.column_dimensions["A"].width = 45
    ws.column_dimensions["B"].width = 15
    ws.column_dimensions["C"].width = 15
    ws.column_dimensions["D"].width = 12
    ws.column_dimensions["E"].width = 20

    row = 1
    ws.merge_cells(f"A{row}:E{row}")
    ws[f"A{row}"] = f"CONNECT GROUP — Gestão de Vendas {mes}"
    ws[f"A{row}"].font = ft_title
    ws[f"A{row}"].fill = fill("#15803d")
    ws[f"A{row}"].alignment = al_left
    ws.row_dimensions[row].height = 28
    row += 1

    ws.merge_cells(f"A{row}:E{row}")
    ws[f"A{row}"] = f"Gerado em {agora}"
    ws[f"A{row}"].font = Font(name="Calibri", size=9, color="94A3B8")
    ws[f"A{row}"].fill = fill("#0f1117")
    ws[f"A{row}"].alignment = al_left
    row += 2

    lideres = sorted([l for l in df_atv["lider"].dropna().unique() if l and l not in ("Sem Equipe", "")])

    for lider in lideres:
        df_l  = df_atv[df_atv["lider"] == lider]
        ac_l  = int(df_l["acessos"].sum())
        rec_l = df_l["preco_oferta"].sum()
        vends = sorted([v for v in df_l["vendedor_real"].dropna().unique() if v and v not in ("Sem Vendedor", "")])

        ws.merge_cells(f"A{row}:C{row}")
        ws[f"A{row}"] = f"  {lider}"
        ws[f"A{row}"].font = ft_lider
        ws[f"A{row}"].fill = fill("#1d4ed8")
        ws[f"A{row}"].alignment = al_left
        ws[f"D{row}"] = ac_l
        ws[f"D{row}"].font = ft_lider
        ws[f"D{row}"].fill = fill("#1d4ed8")
        ws[f"D{row}"].alignment = al_right
        ws[f"E{row}"] = rec_l
        ws[f"E{row}"].font = ft_lider
        ws[f"E{row}"].fill = fill("#1d4ed8")
        ws[f"E{row}"].alignment = al_right
        ws[f"E{row}"].number_format = "R$ #,##0.00"
        ws.row_dimensions[row].height = 20
        row += 1

        for vend in vends:
            df_v   = df_l[df_l["vendedor_real"] == vend]
            ac_v   = int(df_v["acessos"].sum())
            rec_v  = df_v["preco_oferta"].sum()
            meta_v = _meta_vend(vend, meta_dict)
            pct_v  = min(int(rec_v / meta_v * 100), 100) if meta_v > 0 else 0
            cor_v  = "22C55E" if pct_v >= 100 else "F59E0B" if pct_v >= 70 else "EF4444"

            ws.merge_cells(f"A{row}:C{row}")
            ws[f"A{row}"] = f"    {vend}"
            ws[f"A{row}"].font = ft_vend
            ws[f"A{row}"].fill = fill("#131f2e")
            ws[f"A{row}"].alignment = al_left
            ws[f"D{row}"] = ac_v
            ws[f"D{row}"].font = Font(name="Calibri", bold=True, size=10, color=cor_v)
            ws[f"D{row}"].fill = fill("#131f2e")
            ws[f"D{row}"].alignment = al_right
            ws[f"E{row}"] = rec_v
            ws[f"E{row}"].font = Font(name="Calibri", bold=True, size=10, color=cor_v)
            ws[f"E{row}"].fill = fill("#131f2e")
            ws[f"E{row}"].alignment = al_right
            ws[f"E{row}"].number_format = "R$ #,##0.00"
            ws.row_dimensions[row].height = 18
            row += 1

            cols_grp = [c for c in ["razao_social","fila_atual"] if c in df_v.columns]
            if cols_grp:
                df_g = df_v.copy()
                for col in cols_grp:
                    df_g[col] = df_g[col].fillna("—")
                cdf = (df_g.groupby(cols_grp, as_index=False)
                       .agg(ac=("acessos","sum"), rec=("preco_oferta","sum"))
                       .sort_values("ac", ascending=False))
                for _, crow in cdf.iterrows():
                    razao = str(crow.get("razao_social","—"))[:60]
                    fila  = str(crow.get("fila_atual","—")).upper()
                    ac_c  = int(crow.get("ac",0))
                    rec_c = float(crow.get("rec",0))
                    ws.merge_cells(f"A{row}:B{row}")
                    ws[f"A{row}"] = f"        {razao}"
                    ws[f"A{row}"].font = ft_cli
                    ws[f"A{row}"].fill = fill("#080e15")
                    ws[f"A{row}"].alignment = al_left
                    ws[f"C{row}"] = fila
                    ws[f"C{row}"].font = ft_cli
                    ws[f"C{row}"].fill = fill("#080e15")
                    ws[f"C{row}"].alignment = al_center
                    ws[f"D{row}"] = ac_c
                    ws[f"D{row}"].font = ft_cli
                    ws[f"D{row}"].fill = fill("#080e15")
                    ws[f"D{row}"].alignment = al_right
                    ws[f"E{row}"] = rec_c
                    ws[f"E{row}"].font = ft_cli
                    ws[f"E{row}"].fill = fill("#080e15")
                    ws[f"E{row}"].alignment = al_right
                    ws[f"E{row}"].number_format = "R$ #,##0.00"
                    ws.row_dimensions[row].height = 15
                    row += 1

        row += 1

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


# ─────────────────────────────────────────────────────────────────
#  RENDER DETALHADO
# ─────────────────────────────────────────────────────────────────

def render_detalhado(df, mes_alvo, meta_dict):
    FILAS_CANCEL = {"CANCELADO", "CANCELADA", "CANCEL"}

    parceiros = sorted(df["parceiro"].dropna().unique()) if "parceiro" in df.columns else ["—"]

    for parceiro in parceiros:
        df_p = df[df["parceiro"] == parceiro] if "parceiro" in df.columns else df
        if df_p.empty:
            continue

        if "fila_atual" in df_p.columns:
            df_p = df_p[~df_p["fila_atual"].str.strip().str.upper().isin(FILAS_CANCEL)]

        lideres_p = sorted([l for l in df_p["lider"].unique() if l and l not in ("Sem Equipe", "")])
        ac_p  = int(df_p[df_p["mes_ativacao"] == mes_alvo]["acessos"].sum())
        rec_p = df_p[df_p["mes_ativacao"] == mes_alvo]["preco_oferta"].sum()
        pip_p = int(df_p[df_p["mes_ativacao"].isna()]["acessos"].sum())

        st.markdown(f"""<div class="det-parceiro">
          <span class="det-parceiro-nome">🏢 {parceiro}</span>
          <span class="det-parceiro-stats">
            {len(lideres_p)} equipe(s) &nbsp;·&nbsp;
            ✅ {ac_p} ac / R$ {rec_p:,.2f} &nbsp;·&nbsp;
            ⏳ {pip_p} ac tramitando
          </span>
        </div>""", unsafe_allow_html=True)

        for lider in lideres_p:
            df_l = df_p[df_p["lider"] == lider]
            df_l_ok = df_l[~df_l["fila_atual"].str.strip().str.upper().isin(FILAS_CANCEL)] if "fila_atual" in df_l.columns else df_l
            ac_l  = int(df_l_ok[df_l_ok["mes_ativacao"] == mes_alvo]["acessos"].sum())
            rec_l = df_l_ok[df_l_ok["mes_ativacao"] == mes_alvo]["preco_oferta"].sum()
            pip_l = int(df_l_ok[df_l_ok["mes_ativacao"].isna()]["acessos"].sum())
            vends = sorted([v for v in df_l["vendedor_real"].unique() if v and v not in ("Sem Vendedor", "")])

            st.markdown(f"""<div class="det-lider">
              <span class="det-lider-nome">👤 {lider}</span>
              <span class="det-lider-stats">
                {len(vends)} vend. &nbsp;·&nbsp;
                ✅ {ac_l} ac / R$ {rec_l:,.2f} &nbsp;·&nbsp;
                ⏳ {pip_l} ac
              </span>
            </div>""", unsafe_allow_html=True)

            for vend in vends:
                df_v = df_l[df_l["vendedor_real"] == vend]
                df_v_ok = df_v[~df_v["fila_atual"].str.strip().str.upper().isin(FILAS_CANCEL)] if "fila_atual" in df_v.columns else df_v

                df_atv_v = df_v_ok[df_v_ok["mes_ativacao"] == mes_alvo]
                df_pip_v = df_v_ok[df_v_ok["mes_ativacao"].isna()]

                ac_atv_v  = int(df_atv_v["acessos"].sum())
                rec_atv_v = df_atv_v["preco_oferta"].sum()
                ac_pip_v  = int(df_pip_v["acessos"].sum())
                rec_pip_v = df_pip_v["preco_oferta"].sum()
                meta_v    = _meta_vend(vend, meta_dict)
                pct_v     = min(int(rec_atv_v / meta_v * 100), 100) if meta_v > 0 else 0
                cor_v     = _cor(pct_v)

                cols_grp = [c for c in ["razao_social", "fila_atual", "status_dash"] if c in df_v_ok.columns]
                if cols_grp:
                    df_grp = df_v_ok.copy()
                    for col in cols_grp:
                        df_grp[col] = df_grp[col].fillna("—")
                    clientes_df = (
                        df_grp.groupby(cols_grp, as_index=False)
                        .agg(ac=("acessos","sum"), rec=("preco_oferta","sum"),
                             n_atv=("mes_ativacao", lambda x: (x == mes_alvo).sum()))
                        .sort_values(["n_atv","ac"], ascending=[False, False])
                    )
                else:
                    clientes_df = pd.DataFrame()

                clientes_html = ""
                if clientes_df.empty:
                    clientes_html = '<div class="det-empty">Sem pedidos no mês.</div>'
                else:
                    for _, crow in clientes_df.iterrows():
                        razao = str(crow.get("razao_social", "—"))
                        if razao.strip().startswith("#") or razao.strip() == "":
                            razao = "—"
                        fila  = str(crow.get("fila_atual", crow.get("status_dash", "—")))
                        ac_c  = int(crow.get("ac", 0))
                        rec_c = float(crow.get("rec", 0))
                        razao_trunc = (razao[:52] + "…") if len(razao) > 52 else razao
                        clientes_html += f"""<div class="det-cliente-row">
                          <span class="det-cli-nome">{razao_trunc}</span>
                          <span class="det-cli-stats">
                            <span class="det-cli-ac">🔢 {ac_c} ac</span>
                            <span class="det-cli-rec">💰 R$ {rec_c:,.2f}</span>
                            {_fila_badge(fila)}
                          </span>
                        </div>"""

                st.markdown(f"""<div class="det-vendedor-wrap">
                  <div class="det-vend-header">
                    <span class="det-vend-nome">📌 {vend}</span>
                    <div class="det-vend-kpis">
                      <div class="det-kpi-block">
                        <span class="det-kpi-label">✅ Ativado</span>
                        <span class="det-kpi-val" style="color:{cor_v}">
                          {ac_atv_v} ac · R$ {rec_atv_v:,.2f}
                          <span style="color:#64748b;font-size:0.68rem"> ({pct_v}%)</span>
                        </span>
                      </div>
                      <div class="det-kpi-block">
                        <span class="det-kpi-label">⏳ Tramitando</span>
                        <span class="det-kpi-val" style="color:#f59e0b">
                          {ac_pip_v} ac · R$ {rec_pip_v:,.2f}
                        </span>
                      </div>
                    </div>
                  </div>
                  <div class="det-clientes-wrap">{clientes_html}</div>
                </div>""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────
#  RENDER ATRIBUIÇÃO
# ─────────────────────────────────────────────────────────────────

def render_atribuicao(df_pendentes, ws_bko, vendedores):
    if df_pendentes.empty:
        st.success("✅ Nenhum pedido pendente de atribuição!")
        return

    total = len(df_pendentes)
    st.markdown(f"**{total} pedido(s) sem vendedor.** Preencha os do seu time e salve.")
    st.markdown("---")

    vendedores_opts = ["— não é meu —"] + vendedores
    atribuicoes = []

    for _, row in df_pendentes.iterrows():
        pedido  = _s(row.get("pedido", ""))
        cliente = _s(row.get("razao_social", "—"))
        safra   = _s(row.get("safra", "—"))
        row_idx = int(row.get("_row_idx", 0))
        col_idx = int(row.get("_col_vendedor_idx", 4))

        col1, col2 = st.columns([3, 2])
        with col1:
            st.markdown(f"""<div style="background:#1a1f2e;border:1px solid #2d3748;border-radius:12px;padding:14px 16px;margin-bottom:4px">
              <div style="font-size:0.75rem;color:#64748b">Pedido {pedido} · {safra}</div>
              <div style="font-size:0.95rem;font-weight:600;color:#f1f5f9;margin-top:4px">{cliente}</div>
            </div>""", unsafe_allow_html=True)
        with col2:
            sel = st.selectbox(" ", vendedores_opts, key=f"atr_{pedido}", label_visibility="collapsed")
            if sel and sel != "— não é meu —":
                atribuicoes.append({"pedido": pedido, "row_idx": row_idx, "col_idx": col_idx, "vendedor": sel})

    st.markdown("---")
    n_attr = len(atribuicoes)
    if n_attr > 0:
        st.info(f"**{n_attr}** pedido(s) atribuído(s). Salve quando terminar.")
        if st.button("💾 Salvar atribuições", type="primary", use_container_width=True):
            salvos = 0
            with st.spinner("Salvando..."):
                for item in atribuicoes:
                    try:
                        ws_bko.update_cell(item["row_idx"], item["col_idx"], item["vendedor"])
                        salvos += 1
                    except Exception as e:
                        st.warning(f"Erro no pedido {item['pedido']}: {e}")
                st.cache_data.clear()
            st.success(f"✅ {salvos} atribuição(ões) salva(s)!")
            st.rerun()
    else:
        st.button("💾 Salvar atribuições", disabled=True, use_container_width=True)
        st.caption("Selecione ao menos um vendedor para salvar.")

    if st.button("🔄 Atualizar lista", use_container_width=True):
        st.cache_data.clear()
        st.rerun()


# ─────────────────────────────────────────────────────────────────
#  CARREGAMENTO DE DADOS
# ─────────────────────────────────────────────────────────────────

@st.cache_data(ttl=600, show_spinner=False)
def _load_all():
    raw   = load_data()
    bko   = load_bko()
    colab = load_colaboradores()
    return raw, bko, colab


@st.cache_data(ttl=300, show_spinner=False)
def _carregar_pendentes_bko(lider_filtro="", parceiro_filtro="", tipo="admin"):
    gc       = get_gspread_client()
    planilha = gc.open_by_key(SPREADSHEET_ID)
    ws       = planilha.worksheet("BKO-VENDEDOR-REAL")
    all_values = ws.get_all_values()
    if not all_values or len(all_values) < 3:
        return pd.DataFrame(), ws

    headers = all_values[1]
    rows    = all_values[2:]
    df = pd.DataFrame(rows, columns=headers)
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    df["_row_idx"] = [i + 3 for i in range(len(df))]

    col_pedido   = next((c for c in df.columns if "pedido" in c), None)
    col_razao    = next((c for c in df.columns if "raz" in c and "social" in c), None)
    col_vendedor = next((c for c in df.columns if "vendedor" in c and "real" in c), None)
    col_safra    = next((c for c in df.columns if "safra" in c), None)
    col_tipo     = next((c for c in df.columns if "tipo" in c and "contrat" in c), None)
    col_fila     = next((c for c in df.columns if "fila" in c), None)

    if not col_pedido or not col_vendedor:
        return pd.DataFrame(), ws

    df_pend = df[df[col_vendedor].apply(lambda x: _s(x) == "")].copy()
    df_pend = df_pend[df_pend[col_pedido].apply(lambda x: _norm_pedido(x) != "")].copy()

    if col_tipo:
        df_pend = df_pend[~df_pend[col_tipo].apply(lambda x: "RENEGOCI" in _s(x).upper())]
    if col_fila:
        df_pend = df_pend[~df_pend[col_fila].apply(lambda x: "CANCELAD" in _s(x).upper())]

    from datetime import timedelta
    limite = datetime.today() - timedelta(days=60)
    if col_safra:
        def _parse(v):
            try:
                return datetime.strptime(_s(v).strip(), "%m/%Y")
            except Exception:
                return None
        df_pend["_dt"] = df_pend[col_safra].apply(_parse)
        df_pend = df_pend[df_pend["_dt"].apply(lambda d: d is not None and d >= limite.replace(day=1))]

    rename = {}
    if col_pedido:   rename[col_pedido]   = "pedido"
    if col_razao:    rename[col_razao]    = "razao_social"
    if col_safra:    rename[col_safra]    = "safra"
    if col_vendedor: rename[col_vendedor] = "vendedor_real"

    df_pend = df_pend.rename(columns=rename)
    if "pedido" not in df_pend.columns:
        return pd.DataFrame(), ws
    df_pend["pedido"] = df_pend["pedido"].apply(_norm_pedido)
    df_pend = df_pend[df_pend["pedido"] != ""].drop_duplicates("pedido").reset_index(drop=True)

    try:
        col_vend_idx = headers.index(
            next(h for h in headers if "vendedor" in h.lower() and "real" in h.lower())
        ) + 1
    except Exception:
        col_vend_idx = 4

    df_pend["_col_vendedor_idx"] = col_vend_idx
    colunas = [c for c in ["pedido","razao_social","safra","_row_idx","_col_vendedor_idx"] if c in df_pend.columns]
    return df_pend[colunas], ws


# ─────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────

def main():
    # ── Auth ──────────────────────────────────────────────────────
    auth_config = _carregar_auth()
    authenticator = stauth.Authenticate(
        auth_config["credentials"],
        auth_config["cookie"]["name"],
        auth_config["cookie"]["key"],
        auth_config["cookie"]["expiry_days"],
    )

    login_result = authenticator.login(location="main")
    if login_result:
        name, authentication_status, username = login_result
    else:
        name = st.session_state.get("name")
        authentication_status = st.session_state.get("authentication_status")
        username = st.session_state.get("username")

    if authentication_status is False:
        st.error("Usuário ou senha incorretos.")
        st.stop()
    if authentication_status is None:
        st.info("Informe seu usuário e senha para acessar.")
        st.stop()

    # ── Usuário logado ────────────────────────────────────────────
    info = _info_usuario(username)
    tipo       = info["tipo"]
    lider_u    = info["lider"]
    parceiro_u = info["parceiro"]

    # ── Header ────────────────────────────────────────────────────
    mes_str = MESES_PT.get(datetime.now().strftime("%m"), "") + "/" + datetime.now().strftime("%Y")
    badge   = "🔑 ADMIN" if tipo == "admin" else ("👤 LÍDER" if tipo == "lider" else "🏢 PARCEIRO")
    st.markdown(f"""<div class="header-gestao">
      <div>
        <p class="header-title">📊 GESTÃO DE VENDAS — CONNECT GROUP</p>
        <p class="header-sub">TIM Corporate · {mes_str} · Bem-vindo, {name}</p>
      </div>
      <div style="display:flex;align-items:center;gap:12px">
        <img src="https://raw.githubusercontent.com/hugokhesley/dashboard-tim-connectgroup-sheets/main/logo.png"
             style="height:40px;object-fit:contain;border-radius:6px" onerror="this.style.display='none'">
        <span class="header-badge">{badge}</span>
      </div>
    </div>""", unsafe_allow_html=True)

    # ── Carrega dados ─────────────────────────────────────────────
    with st.spinner("Carregando dados..."):
        raw, bko, colab = _load_all()

    if raw.empty:
        st.warning("⚠️ Nenhum dado encontrado.")
        st.stop()

    meta_dict = dict(zip(colab["vendedor"], colab["meta"])) if not colab.empty else {}

    # ── Sidebar ───────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 🔧 Filtros")

        meses_opcoes = gerar_meses_opcoes()
        mes_labels   = [MESES_PT.get(m[:2], m[:2]) + "/" + m[3:] for m in meses_opcoes]
        mes_idx      = st.selectbox("📅 Mês", range(len(meses_opcoes)),
                                    format_func=lambda i: mes_labels[i], index=0)
        mes_alvo = meses_opcoes[mes_idx]

        if tipo == "admin":
            parceiro_sel = st.selectbox("Parceiro / Aba", get_parceiros(raw))
            lider_opts   = ["Todos"] + sorted([l for l in bko["lider"].unique() if l and l != "Sem Equipe"]) if not bko.empty else ["Todos"]
            lider_sel    = st.selectbox("Equipe / Líder", lider_opts)
        else:
            parceiro_sel = "Todos"
            lider_sel    = "Todos"

        st.markdown("---")
        if st.button("🔄 Atualizar dados"):
            st.cache_data.clear()
            st.rerun()
        st.markdown("---")
        authenticator.logout("🚪 Sair", "sidebar")
        st.markdown(f"**Mês:** `{mes_alvo}`")
        st.caption("Dados via Google Sheets · cache 3 min")

    is_mes_atual = (mes_alvo == datetime.now().strftime("%m/%Y"))

    # ── Aplica filtros ────────────────────────────────────────────
    df = apply_filters(raw.copy(), mes_alvo, ["NOVO", "ADITIVO"], parceiro_sel)

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

    if tipo == "lider" and lider_u:
        df = df[df["lider"].apply(lambda x: _s(x).upper()) == lider_u.upper()]
    elif tipo == "parceiro" and parceiro_u:
        if "parceiro" in df.columns:
            df = df[df["parceiro"].apply(lambda x: _s(x).upper()) == parceiro_u.upper()]
    elif tipo == "admin" and lider_sel != "Todos":
        df = df[df["lider"] == lider_sel]

    if not is_mes_atual:
        df = df[df["mes_ativacao"] == mes_alvo].copy()

    if df.empty:
        st.info("Nenhum dado para os filtros selecionados.")
        st.stop()

    # ── KPIs ──────────────────────────────────────────────────────
    atv    = df[df["mes_ativacao"] == mes_alvo]
    ac_g   = int(atv["acessos"].sum())
    rec_g  = atv["preco_oferta"].sum()
    pip_g  = int(df[df["mes_ativacao"].isna()]["acessos"].sum())
    nv_g   = df["vendedor_real"].nunique()
    meta_g = sum(_meta_vend(v, meta_dict) for v in df["vendedor_real"].unique()) if meta_dict else nv_g * META_VENDEDOR_PAD
    pct_g  = min(int(rec_g / meta_g * 100), 999) if meta_g > 0 else 0

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(f"""<div class="kpi-mini blue"><div class="kpi-label">🎯 Acessos Ativados</div>
          <div class="kpi-value">{ac_g:,}</div><div class="kpi-sub">no mês</div></div>""", unsafe_allow_html=True)
    with k2:
        st.markdown(f"""<div class="kpi-mini green"><div class="kpi-label">💰 Receita Ativada</div>
          <div class="kpi-value">R$ {rec_g:,.2f}</div><div class="kpi-sub">{pct_g}% da meta</div></div>""", unsafe_allow_html=True)
    with k3:
        st.markdown(f"""<div class="kpi-mini amber"><div class="kpi-label">⏳ Pipeline</div>
          <div class="kpi-value">{pip_g:,}</div><div class="kpi-sub">em tramitação</div></div>""", unsafe_allow_html=True)
    with k4:
        st.markdown(f"""<div class="kpi-mini purple"><div class="kpi-label">👥 Vendedores</div>
          <div class="kpi-value">{nv_g}</div><div class="kpi-sub">ativos</div></div>""", unsafe_allow_html=True)

    # ── Tabs ──────────────────────────────────────────────────────
    df_atv = atv.copy()  # só ativados do mês para exportação

    if tipo == "parceiro":
        tabs = st.tabs(["📋 Detalhado"])
        with tabs[0]:
            st.markdown('<p class="section-title">📋 Visão Detalhada por Vendedor</p>', unsafe_allow_html=True)
            render_detalhado(df, mes_alvo, meta_dict)

            # ── Exportar ──────────────────────────────────────────
            st.markdown("---")
            st.markdown('<p class="section-title">📥 Exportar Relatório</p>', unsafe_allow_html=True)
            _render_exportar(df_atv, meta_dict, mes_alvo)

    else:
        tab_det, tab_atr = st.tabs(["📋 Detalhado", "👤 Atribuição de Vendedores"])

        with tab_det:
            st.markdown('<p class="section-title">📋 Visão Detalhada por Vendedor</p>', unsafe_allow_html=True)
            render_detalhado(df, mes_alvo, meta_dict)

            # ── Exportar ──────────────────────────────────────────
            st.markdown("---")
            st.markdown('<p class="section-title">📥 Exportar Relatório</p>', unsafe_allow_html=True)
            _render_exportar(df_atv, meta_dict, mes_alvo)

        with tab_atr:
            st.markdown('<p class="section-title">👤 Pedidos sem Vendedor Atribuído</p>', unsafe_allow_html=True)
            with st.spinner("Carregando pendentes..."):
                df_pend, ws_bko = _carregar_pendentes_bko(
                    lider_filtro=lider_u,
                    parceiro_filtro=parceiro_u,
                    tipo=tipo
                )
                vendedores = sorted([v for v in colab["vendedor"].dropna().unique() if _s(v)]) if not colab.empty else []

            render_atribuicao(df_pend, ws_bko, vendedores)


def _render_exportar(df_atv, meta_dict, mes_alvo):
    """Botões de exportar PDF e Excel."""
    if df_atv.empty or "lider" not in df_atv.columns:
        st.info("Sem dados ativados no mês para exportar.")
        return

    col_pdf, col_xlsx = st.columns(2)

    with col_pdf:
        if st.button("📄 Gerar PDF", use_container_width=True, type="primary"):
            with st.spinner("Gerando PDF..."):
                try:
                    pdf_bytes = gerar_pdf(df_atv, meta_dict, mes_alvo)
                    st.download_button(
                        label="⬇️ Baixar PDF",
                        data=pdf_bytes,
                        file_name=f"gestao_vendas_{mes_alvo.replace('/','_')}.pdf",
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True,
                    )
                except Exception as e:
                    st.error(f"Erro ao gerar PDF: {e}")

    with col_xlsx:
        if st.button("📊 Gerar Excel", use_container_width=True):
            with st.spinner("Gerando Excel..."):
                try:
                    xlsx_bytes = gerar_excel(df_atv, meta_dict, mes_alvo)
                    st.download_button(
                        label="⬇️ Baixar Excel",
                        data=xlsx_bytes,
                        file_name=f"gestao_vendas_{mes_alvo.replace('/','_')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                    )
                except Exception as e:
                    st.error(f"Erro ao gerar Excel: {e}")


main()
