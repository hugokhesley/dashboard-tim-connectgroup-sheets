import streamlit as st
import pandas as pd
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date as _date
from data_loader import _s, _to_num, _soma_valor, _normalize, _dedup_columns, get_gspread_client, registrar_acesso
from auth import require_password

st.set_page_config(
    page_title="Connect Group | Qualidade",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

require_password("qualidade", "Qualidade — Connect Group")
registrar_acesso("qualidade")

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
        n = _normalize(col).replace("?","").replace(".","").replace("°","").replace("º","").strip()
        if n == "safra":                                rename[col] = "safra"
        elif "parceiro" in n:                           rename[col] = "parceiro"
        elif "custcode" in n:                           rename[col] = "custcode"
        elif "fatura" in n and "enviada" not in n and "atraso" not in n and ("n" in n or "numero" in n): rename[col] = "n_fatura"
        elif "cnpj" in n:                               rename[col] = "cnpj"
        elif "lider" in n:                              rename[col] = "lider"
        elif "adimplente" in n:                         rename[col] = "adimplente"
        elif "cliente" in n and "contato" not in n:     rename[col] = "cliente"
        elif n == "venda":                              rename[col] = "venda"
        elif "consultor" in n:                          rename[col] = "consultor"
        elif "vencimento" in n or "vecimento" in n:     rename[col] = "vencimento"
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
        s = _s(s).lower().strip()
        if not s:
            return s
        import re
        # Remove ponto final solto: "out." → "out"
        s = re.sub(r"\.$", "", s)
        # Formato numérico: MM/AAAA ou MM/AA
        m = re.match(r"^(\d{1,2})[/\-](\d{2,4})$", s)
        if m:
            mes, ano = m.group(1).zfill(2), m.group(2)
            ano = "20" + ano if len(ano) == 2 else ano
            return f"{mes}/{ano}"
        # Formato textual com separador / ou . : out./25, out/25, nov.2025, nov/2025
        m2 = re.match(r"^([a-záéíóúã]+)\.?[/\.](\d{2,4})$", s)
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
        df["valor_rs"] = df["valor_rs"].apply(_soma_valor)

    # ADIMPLENTE? é preenchida manualmente pela analista — lê direto da coluna
    # Se a coluna não existir ou estiver vazia, assume SIM (sem débito)
    if "adimplente" in df.columns:
        df["adimplente"] = df["adimplente"].apply(lambda x: _s(x) if _s(x) else "SIM")
    else:
        df["adimplente"] = "SIM"
    return df


def _bool_icon(val):
    v = _s(val).upper()
    if v.startswith("SIM"):                         return "✅"
    if v.startswith("NÃO") or v.startswith("NAO"): return "❌"
    if v:                                           return v
    return "—"


def _adim_icon(val):
    v = _s(val).upper().strip()
    if v == "SIM":                        return "🟢 SIM"
    if v in ("NÃO", "NAO"):              return "🔴 NÃO"
    if v in ("GERADA", "FATURA GERADA"): return "🟡 FATURA GERADA"
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
    """Retorna máscara booleana: True = NÃO adimplente (fatura vencida)."""
    if "adimplente" in df.columns:
        return df["adimplente"].apply(lambda x: _s(x).upper().strip() in ["NÃO", "NAO"])
    return pd.Series([False] * len(df))


def _mask_gerada(df):
    """Retorna máscara booleana: True = fatura gerada ainda não vencida."""
    if "adimplente" in df.columns:
        return df["adimplente"].apply(lambda x: _s(x).upper().strip() in ["GERADA", "FATURA GERADA"])
    return pd.Series([False] * len(df))


def _mask_sem_contato(df):
    """True = tem débito E analista ainda não fez contato."""
    mask_debito = _mask_inadim(df) | _mask_gerada(df)
    if "contato_cliente" in df.columns:
        mask_sc = df["contato_cliente"].apply(lambda x: not _s(x).upper().startswith("SIM"))
        return mask_debito & mask_sc
    return mask_debito


def _enviar_alerta_qualidade(df_alerta, safras_sel, parceiros_sel, destinatarios, smtp_user, smtp_pass, smtp_from=None):
    hoje = _date.today().strftime("%d/%m/%Y")
    total       = len(df_alerta)
    inadim      = df_alerta[_mask_inadim(df_alerta)]
    gerada      = df_alerta[_mask_gerada(df_alerta)]
    sem_contato = df_alerta[_mask_sem_contato(df_alerta)]

    def _val(r):
        try: return float(r.get("valor_rs", 0))
        except: return 0.0

    def _linhas(df_sub, cor):
        rows = ""
        for _, r in df_sub.iterrows():
            v = _s(r.get("adimplente","")).upper()
            icon = "🔴 NÃO" if "NÃO" in v or "NAO" in v else "🟡 FATURA GERADA"
            rows += f"""<tr>
              <td style="padding:7px 10px;border-bottom:1px solid #e2e8f0">{_s(r.get("safra",""))}</td>
              <td style="padding:7px 10px;border-bottom:1px solid #e2e8f0">{_s(r.get("parceiro",""))}</td>
              <td style="padding:7px 10px;border-bottom:1px solid #e2e8f0;font-weight:600">{_s(r.get("cliente",""))}</td>
              <td style="padding:7px 10px;border-bottom:1px solid #e2e8f0">{_s(r.get("cnpj",""))}</td>
              <td style="padding:7px 10px;border-bottom:1px solid #e2e8f0">{_s(r.get("custcode",""))}</td>
              <td style="padding:7px 10px;border-bottom:1px solid #e2e8f0">{_s(r.get("n_fatura",""))}</td>
              <td style="padding:7px 10px;border-bottom:1px solid #e2e8f0">{_s(r.get("vencimento",""))}</td>
              <td style="padding:7px 10px;border-bottom:1px solid #e2e8f0;font-weight:600">R$ {_val(r):,.2f}</td>
              <td style="padding:7px 10px;border-bottom:1px solid #e2e8f0;color:{cor};font-weight:700">{icon}</td>
            </tr>"""
        return rows

    def _linhas_urgente(df_sub):
        rows = ""
        for _, r in df_sub.iterrows():
            v = _s(r.get("adimplente","")).upper()
            icon = "🔴 NÃO" if "NÃO" in v or "NAO" in v else "🟡 GERADA"
            rows += f"""<tr style="background:#fff8f8">
              <td style="padding:7px 10px;border-bottom:1px solid #fecaca;font-weight:700;color:#991b1b">{_s(r.get("safra",""))}</td>
              <td style="padding:7px 10px;border-bottom:1px solid #fecaca">{_s(r.get("parceiro",""))}</td>
              <td style="padding:7px 10px;border-bottom:1px solid #fecaca;font-weight:700">{_s(r.get("cliente",""))}</td>
              <td style="padding:7px 10px;border-bottom:1px solid #fecaca">{_s(r.get("cnpj",""))}</td>
              <td style="padding:7px 10px;border-bottom:1px solid #fecaca">{_s(r.get("custcode",""))}</td>
              <td style="padding:7px 10px;border-bottom:1px solid #fecaca">{_s(r.get("n_fatura",""))}</td>
              <td style="padding:7px 10px;border-bottom:1px solid #fecaca">{_s(r.get("vencimento",""))}</td>
              <td style="padding:7px 10px;border-bottom:1px solid #fecaca;font-weight:700;color:#991b1b">R$ {_val(r):,.2f}</td>
              <td style="padding:7px 10px;border-bottom:1px solid #fecaca;font-weight:700">{icon}</td>
            </tr>"""
        return rows

    def _thead(cor):
        return f"""<table style="width:100%;border-collapse:collapse;font-size:0.83rem;font-family:Arial,sans-serif">
      <thead><tr style="background:{cor};color:#fff">
        <th style="padding:9px 10px;text-align:left">Safra</th>
        <th style="padding:9px 10px;text-align:left">Parceiro</th>
        <th style="padding:9px 10px;text-align:left">Cliente</th>
        <th style="padding:9px 10px;text-align:left">CNPJ</th>
        <th style="padding:9px 10px;text-align:left">CustCode</th>
        <th style="padding:9px 10px;text-align:left">Nº Fatura</th>
        <th style="padding:9px 10px;text-align:left">Vencimento</th>
        <th style="padding:9px 10px;text-align:left">Valor R$</th>
        <th style="padding:9px 10px;text-align:left">Status</th>
      </tr></thead><tbody>"""

    debito = sum(_val(r) for _, r in df_alerta.iterrows())
    safras_str    = ", ".join(safras_sel)
    parceiros_str = ", ".join(parceiros_sel) if parceiros_sel and parceiros_sel != ["Todos"] else "Todos"

    html = f"""<html><body style="font-family:Arial,sans-serif;background:#f8fafc;padding:20px">
    <div style="max-width:1000px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.1)">
      <div style="background:linear-gradient(135deg,#1a0533,#4a1272,#7c3aed);padding:24px 32px">
        <h1 style="color:#fff;margin:0;font-size:1.4rem">🔍 Alerta de Adimplência — Connect Group</h1>
        <p style="color:rgba(255,255,255,0.7);margin:4px 0 0 0">TIM Corporate · Safras: {safras_str} · Parceiros: {parceiros_str}</p>
        <p style="color:rgba(255,255,255,0.6);margin:2px 0 0 0;font-size:0.82rem">{hoje}</p>
      </div>
      <div style="display:flex;gap:12px;padding:20px 32px;background:#faf5ff">
        <div style="flex:1;background:#fff;border-radius:8px;padding:14px;border:1px solid #e9d5ff;text-align:center">
          <div style="font-size:0.68rem;color:#7c3aed;text-transform:uppercase;font-weight:700">Clientes</div>
          <div style="font-size:1.8rem;font-weight:800;color:#1e1b4b">{total}</div>
        </div>
        <div style="flex:1;background:#fff;border-radius:8px;padding:14px;border:1px solid #fecaca;text-align:center">
          <div style="font-size:0.68rem;color:#dc2626;text-transform:uppercase;font-weight:700">🔴 Vencidos</div>
          <div style="font-size:1.8rem;font-weight:800;color:#dc2626">{len(inadim)}</div>
        </div>
        <div style="flex:1;background:#fff;border-radius:8px;padding:14px;border:1px solid #fde68a;text-align:center">
          <div style="font-size:0.68rem;color:#d97706;text-transform:uppercase;font-weight:700">🟡 Gerados</div>
          <div style="font-size:1.8rem;font-weight:800;color:#d97706">{len(gerada)}</div>
        </div>
        <div style="flex:1;background:#fff;border-radius:8px;padding:14px;border:1px solid #fecaca;text-align:center">
          <div style="font-size:0.68rem;color:#b91c1c;text-transform:uppercase;font-weight:700">⚠️ Sem Contato</div>
          <div style="font-size:1.8rem;font-weight:800;color:#b91c1c">{len(sem_contato)}</div>
        </div>
        <div style="flex:1;background:#fff;border-radius:8px;padding:14px;border:1px solid #e9d5ff;text-align:center">
          <div style="font-size:0.68rem;color:#7c3aed;text-transform:uppercase;font-weight:700">💸 Débito</div>
          <div style="font-size:1.2rem;font-weight:800;color:#1e1b4b">R$ {debito:,.2f}</div>
        </div>
      </div>
      <div style="padding:0 32px 32px">"""

    if len(sem_contato) > 0:
        html += f"""
        <div style="background:#fef2f2;border:2px solid #fca5a5;border-radius:10px;padding:16px 20px;margin:20px 0">
          <h2 style="color:#991b1b;font-size:1rem;margin:0 0 4px 0">⚠️ AÇÃO URGENTE — {len(sem_contato)} cliente(s) sem contato registrado</h2>
          <p style="color:#b91c1c;font-size:0.82rem;margin:0 0 14px 0">Estes clientes possuem débito em aberto e a analista ainda não realizou contato. Prioridade máxima!</p>
          {_thead("#991b1b")}{_linhas_urgente(sem_contato)}</tbody></table>
        </div>"""

    if len(inadim) > 0:
        html += f"""<h2 style="color:#dc2626;font-size:0.95rem;margin:20px 0 10px">🔴 Faturas Vencidas ({len(inadim)})</h2>
        {_thead("#dc2626")}{_linhas(inadim, "#dc2626")}</tbody></table>"""

    if len(gerada) > 0:
        html += f"""<h2 style="color:#d97706;font-size:0.95rem;margin:20px 0 10px">🟡 Fatura Gerada — A Vencer ({len(gerada)})</h2>
        {_thead("#d97706")}{_linhas(gerada, "#d97706")}</tbody></table>"""

    html += """</div>
      <div style="background:#f1f5f9;padding:12px 32px;text-align:center;font-size:0.72rem;color:#94a3b8">
        Enviado pelo Dashboard Connect Group · TIM Corporate
      </div>
    </div></body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🔍 Alerta Qualidade — {total} clientes ({len(sem_contato)} sem contato) | {hoje}"
    msg["From"]    = smtp_from or smtp_user
    msg["To"]      = ", ".join(destinatarios)
    msg.attach(MIMEText(html, "html"))

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.titan.email", 465, context=ctx) as srv:
        srv.login(smtp_user, smtp_pass)
        srv.sendmail(smtp_user, destinatarios, msg.as_string())
    return total, len(sem_contato)


def _acessos(d: pd.DataFrame) -> int:
    """Soma a coluna VENDA (acessos/linhas). Fallback para contagem de linhas."""
    if "venda" in d.columns:
        return int(d["venda"].fillna(0).sum())
    return len(d)


def render_painel_geral(df: pd.DataFrame):
    st.markdown('<p class="section-title">📊 Visão Geral por Safra</p>', unsafe_allow_html=True)

    safras = sorted(df["safra"].dropna().unique()) if "safra" in df.columns else []
    rows = []
    for safra in safras:
        dfs         = df[df["safra"] == safra]
        mask_nao    = _mask_inadim(dfs)
        mask_gerada = _mask_gerada(dfs)
        mask_sim    = ~mask_nao & ~mask_gerada
        total  = _acessos(dfs)
        nao    = _acessos(dfs[mask_nao])
        gerada = _acessos(dfs[mask_gerada])
        sim    = _acessos(dfs[mask_sim])
        debito = dfs["valor_rs"].sum() if "valor_rs" in dfs.columns else 0
        pct    = round(sim / total * 100, 1) if total > 0 else 0
        rows.append({
            "Safra": safra, "Total Acessos": total,
            "🟢 Adimplentes": sim, "🟡 Gerada": gerada, "🔴 Vencidos": nao,
            "% Adimplência": pct, "Débito Total": debito,
        })

    if not rows:
        st.info("Nenhuma safra encontrada.")
        return

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True,
        column_config={
            "Safra":            st.column_config.TextColumn("Safra"),
            "Total Acessos":    st.column_config.NumberColumn("Total Acessos", format="%d"),
            "🟢 Adimplentes":   st.column_config.NumberColumn("🟢 Adimplentes", format="%d"),
            "🟡 Gerada":        st.column_config.NumberColumn("🟡 Gerada", format="%d"),
            "🔴 Vencidos":      st.column_config.NumberColumn("🔴 Vencidos", format="%d"),
            "% Adimplência":    st.column_config.ProgressColumn("% Adimplência", min_value=0, max_value=100, format="%.1f%%"),
            "Débito Total":     st.column_config.NumberColumn("Débito Total", format="R$ %.2f"),
        })

    # KPIs consolidados
    st.markdown('<p class="section-title">📈 KPIs Consolidados</p>', unsafe_allow_html=True)
    mask_nao_g    = _mask_inadim(df)
    mask_gerada_g = _mask_gerada(df)
    mask_sim_g    = ~mask_nao_g & ~mask_gerada_g
    total_g  = _acessos(df)
    nao_g    = _acessos(df[mask_nao_g])
    gerada_g = _acessos(df[mask_gerada_g])
    sim_g    = _acessos(df[mask_sim_g])
    debito_g = df["valor_rs"].sum() if "valor_rs" in df.columns else 0
    pct_g    = round(sim_g / total_g * 100, 1) if total_g > 0 else 0

    g1, g2, g3, g4 = st.columns(4)
    with g1:
        st.markdown(f"""<div class="kpi-card purple">
          <div class="kpi-label">📶 Total de Acessos</div>
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
          <div class="kpi-sub">🟡 {gerada_g} acessos gerados</div>
        </div>""", unsafe_allow_html=True)


def render_safra_detalhe(df: pd.DataFrame, safra: str):
    dfs = df[df["safra"] == safra].copy() if safra != "Todas" else df.copy()

    inadim_mask  = _mask_inadim(dfs)
    gerada_mask  = _mask_gerada(dfs)
    sim_mask     = ~inadim_mask & ~gerada_mask
    total        = _acessos(dfs)
    nao          = _acessos(dfs[inadim_mask])
    gerada       = _acessos(dfs[gerada_mask])
    sim          = _acessos(dfs[sim_mask])
    pct          = round(sim / total * 100, 1) if total > 0 else 0
    debito       = dfs["valor_rs"].sum() if "valor_rs" in dfs.columns else 0
    sem_contato  = _acessos(dfs[inadim_mask & dfs["contato_cliente"].apply(
        lambda x: not _s(x).upper().startswith("SIM")
    )]) if "contato_cliente" in dfs.columns else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""<div class="kpi-card purple">
          <div class="kpi-label">📶 Total de Acessos</div>
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
        pct_nao = round(nao / total * 100, 1) if total > 0 else 0
        st.markdown(f"""<div class="kpi-card red">
          <div class="kpi-label">🔴 Vencidos</div>
          <div class="kpi-value">{nao:,}</div>
          <div class="kpi-sub">{pct_nao}% da safra · R$ {debito:,.2f} em aberto</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""<div class="kpi-card amber">
          <div class="kpi-label">📵 Sem Contato</div>
          <div class="kpi-value">{sem_contato:,}</div>
          <div class="kpi-sub">acessos vencidos sem contato</div>
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

    # ── Alerta por Email ────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown('<p class="section-title">📧 Enviar Alerta por Email</p>', unsafe_allow_html=True)
    with st.expander("📨 Configurar e enviar alerta de inadimplência", expanded=False):
        col_a, col_b = st.columns(2)
        with col_a:
            safras_alerta = st.multiselect(
                "Safras para incluir",
                options=safras_disp,
                default=safras_disp[-1:] if safras_disp else [],
                key="safras_alerta"
            )
            parceiros_alerta = st.multiselect(
                "Parceiros para incluir",
                options=["Todos"] + parceiros_disp,
                default=["Todos"],
                key="parceiros_alerta"
            )
            incluir_vencida = st.checkbox("Incluir 🔴 Vencidos", value=True, key="chk_vencida")
            incluir_gerada  = st.checkbox("Incluir 🟡 Fatura Gerada (a vencer)", value=True, key="chk_gerada")
        with col_b:
            _emails_pad = [
                "bko2@connectbrasil.tech",
                "angelo.roncaly@connectgroup.solutions",
                "hugo@connectgroup.solutions",
                "maria.alice@connectgroup.solutions",
            ]
            emails_input = st.text_area(
                "Destinatários (um por linha)",
                value="\n".join(_emails_pad),
                height=130, key="emails_alerta"
            )
        st.caption("⚠️ Clientes sem contato registrado serão destacados automaticamente como urgentes no topo do email.")
        if st.button("📧 Enviar Alerta", type="primary", key="btn_alerta_qualidade"):
            if not safras_alerta:
                st.warning("Selecione pelo menos uma safra.")
            else:
                destinatarios = [e.strip() for e in emails_input.split("\n") if e.strip() and "@" in e]
                if not destinatarios:
                    st.warning("Informe pelo menos um email válido.")
                else:
                    df_alerta = df[df["safra"].isin(safras_alerta)].copy()
                    # Filtra parceiros se não for "Todos"
                    if "Todos" not in parceiros_alerta and parceiros_alerta and "parceiro" in df_alerta.columns:
                        df_alerta = df_alerta[df_alerta["parceiro"].isin(parceiros_alerta)]
                    masks = []
                    if incluir_vencida: masks.append(_mask_inadim(df_alerta))
                    if incluir_gerada:  masks.append(_mask_gerada(df_alerta))
                    if masks:
                        mask_final = masks[0]
                        for m in masks[1:]: mask_final = mask_final | m
                        df_alerta = df_alerta[mask_final]
                    if df_alerta.empty:
                        st.info("Nenhum cliente com pendência para o filtro selecionado.")
                    else:
                        try:
                            smtp_user = st.secrets["email"]["user"]
                            smtp_pass = st.secrets["email"]["password"]
                            smtp_from = st.secrets["email"].get("from", smtp_user)
                            with st.spinner(f"Enviando para {len(destinatarios)} destinatário(s)..."):
                                total, sem_ct = _enviar_alerta_qualidade(
                                    df_alerta, safras_alerta, parceiros_alerta,
                                    destinatarios, smtp_user, smtp_pass, smtp_from
                                )
                            msg_ok = f"✅ Alerta enviado! {total} clientes incluídos."
                            if sem_ct > 0:
                                msg_ok += f" ⚠️ {sem_ct} sem contato destacados como urgentes."
                            st.success(msg_ok)
                        except Exception as e:
                            st.error(f"❌ Erro ao enviar: {e}")

    if visao == "Painel Geral":
        render_painel_geral(df)
    else:
        st.markdown(f'<p class="section-title">🗓️ Safra: {safra_sel}</p>', unsafe_allow_html=True)
        render_safra_detalhe(df, safra_sel)


main()
