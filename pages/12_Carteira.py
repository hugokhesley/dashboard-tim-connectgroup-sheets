"""
=====================================================================
  12_Carteira.py — Carteira de Atendimento · Connect Group
=====================================================================
  Sistema de controle de clientes por CNPJ.
  Integrado ao Gestão de Equipe (mesmo auth: credentials_gestao).

  Regras:
    - CNPJ livre     → qualquer usuário registra
    - CNPJ ocupado   → bloqueia com mensagem + contato admin
    - Libera após 60 dias OU status = Ativado
    - Admin pode liberar manualmente a qualquer momento
    - Vendedor/Líder/TBP puxados da aba Colaboradores (coluna TBP)

  Aba Sheets: CarteiraAtendimento (criada automaticamente)
=====================================================================
"""

import streamlit as st
import pandas as pd
import requests
import re
import hashlib
from datetime import datetime, timedelta
import streamlit_authenticator as stauth

from data_loader import load_colaboradores, get_gspread_client

# ─────────────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Carteira de Atendimento — Connect Group",
    page_icon="📁",
    layout="wide",
    initial_sidebar_state="expanded",
)

SPREADSHEET_ID  = "1HmtEFf2Akh7NLR2prxDh9S4gmioKYw419B4bkx4yBLg"
ABA_CARTEIRA    = "CarteiraAtendimento"
DIAS_EXPIRACAO  = 60

STATUS_CARTEIRA = ["Em Atendimento", "Ativado", "Expirado", "Liberado pelo Admin"]
COR_STATUS = {
    "Em Atendimento": "#f59e0b",
    "Ativado":        "#22c55e",
    "Expirado":       "#64748b",
    "Liberado pelo Admin": "#8b5cf6",
}

st.markdown("<style>[data-testid='stSidebarNav'] { display: none; }</style>", unsafe_allow_html=True)

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
  html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
  .stApp { background-color: #0f1117; color: #e2e8f0; }

  /* inputs */
  input[type="text"], input[type="password"], textarea,
  .stTextInput input, .stTextArea textarea,
  div[data-baseweb="input"] input {
    background-color: #1a1f2e !important;
    color: #e2e8f0 !important;
    border: 1px solid #2d3748 !important;
  }
  label, .stTextInput label, .stSelectbox label,
  .stRadio label, .stCheckbox label {
    color: #94a3b8 !important;
    font-weight: 500 !important;
  }
  div[data-baseweb="select"] > div,
  div[data-baseweb="select"] div[class*="ValueContainer"],
  div[data-baseweb="select"] div[class*="singleValue"],
  div[data-baseweb="select"] input {
    background-color: #1a1f2e !important;
    color: #e2e8f0 !important;
  }
  div[data-baseweb="select"] svg { fill: #64748b !important; }

  /* botões */
  .stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #15803d, #22c55e) !important;
    color: #fff !important; border: none !important;
    border-radius: 8px !important; font-weight: 700 !important;
  }
  .stButton > button:not([kind="primary"]) {
    background: #1a1f2e !important; color: #94a3b8 !important;
    border: 1px solid #2d3748 !important; border-radius: 8px !important;
  }

  /* expanders */
  details { background: #1a1f2e !important; border: 1px solid #2d3748 !important; border-radius: 10px !important; }
  details summary { color: #e2e8f0 !important; font-weight: 600 !important; }

  /* sidebar */
  section[data-testid="stSidebar"] { background: #0d1a0f !important; }

  /* tabs */
  .stTabs [data-baseweb="tab-list"] { gap: 4px; background: transparent; }
  .stTabs [data-baseweb="tab"] {
    border-radius: 8px 8px 0 0; color: #64748b !important;
    font-weight: 600 !important; font-size: 0.82rem !important;
    padding: 8px 16px !important; background: #1a1f2e !important;
    border: 1px solid #2d3748 !important; border-bottom: none !important;
  }
  .stTabs [aria-selected="true"] {
    color: #22c55e !important; background: #0d1f14 !important;
    border-color: #22c55e !important; font-weight: 700 !important;
  }
  .stTabs [data-baseweb="tab-border"] { background: #2d3748 !important; }

  .header-carteira {
    background: linear-gradient(135deg, #0d2b1a 0%, #14532d 40%, #15803d 70%, #22c55e 100%);
    border-radius: 16px; padding: 24px 32px; margin-bottom: 24px;
    border: 1px solid rgba(255,255,255,0.08);
    display: flex; align-items: center; justify-content: space-between;
  }
  .header-title { font-size: 1.5rem; font-weight: 800; color: #fff; margin: 0; }
  .header-sub   { font-size: 0.82rem; color: rgba(255,255,255,0.65); margin: 4px 0 0; }
  .header-badge { background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.25);
                  border-radius: 20px; padding: 5px 14px; font-size: 0.78rem; color: #fff; font-weight: 600; }

  .kpi-mini { background: #1a1f2e; border-radius: 12px; padding: 16px 18px;
              border: 1px solid #2d3748; position: relative; overflow: hidden; margin-bottom: 4px; }
  .kpi-mini::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; }
  .kpi-mini.green::before  { background: linear-gradient(90deg, #22c55e, #15803d); }
  .kpi-mini.amber::before  { background: linear-gradient(90deg, #f59e0b, #d97706); }
  .kpi-mini.blue::before   { background: linear-gradient(90deg, #3b82f6, #1d4ed8); }
  .kpi-mini.red::before    { background: linear-gradient(90deg, #ef4444, #dc2626); }
  .kpi-label { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 1px;
               color: #94a3b8; font-weight: 600; margin-bottom: 6px; }
  .kpi-value { font-size: 1.6rem; font-weight: 800; color: #f1f5f9; line-height: 1; }
  .kpi-sub   { font-size: 0.72rem; color: #64748b; margin-top: 4px; }

  .cnpj-card {
    background: #111827; border: 1px solid #1e3a5f;
    border-left: 5px solid #3b82f6;
    border-radius: 12px; padding: 16px 20px; margin-bottom: 10px;
  }
  .cnpj-card.livre    { border-left-color: #22c55e; }
  .cnpj-card.ocupado  { border-left-color: #ef4444; }
  .cnpj-card.expirado { border-left-color: #64748b; }
  .cnpj-card.ativado  { border-left-color: #22c55e; }

  .empresa-nome { font-size: 1rem; font-weight: 700; color: #f1f5f9; }
  .empresa-info { font-size: 0.76rem; color: #64748b; margin-top: 3px; }
  .status-pill {
    display: inline-block; padding: 3px 10px; border-radius: 99px;
    font-size: 0.7rem; font-weight: 700; color: #fff;
  }
  .bloqueio-box {
    background: #1c0a0a; border: 1px solid #7f1d1d;
    border-radius: 10px; padding: 14px 18px; margin: 12px 0;
    font-size: 0.84rem; color: #fca5a5;
  }
  .section-title {
    font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1.5px;
    color: #22c55e; font-weight: 700; margin: 24px 0 12px 0;
    border-left: 3px solid #22c55e; padding-left: 10px;
  }
  .receita-card {
    background: #0d1f14; border: 1px solid #14532d;
    border-radius: 10px; padding: 14px 18px; margin-bottom: 8px;
  }
  .receita-empresa { font-size: 0.88rem; font-weight: 700; color: #86efac; }
  .receita-detalhe { font-size: 0.73rem; color: #4ade80; margin-top: 2px; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────
#  AUTENTICAÇÃO — mesmo padrão do 11_Gestao_Equipe.py
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
            "cookie": {"name": "carteira_cookie", "key": "gestao_secret_key", "expiry_days": 1},
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
#  GOOGLE SHEETS — CarteiraAtendimento
# ─────────────────────────────────────────────────────────────────

HEADER_CARTEIRA = [
    "cnpj", "razao_social", "nome_fantasia", "atividade_economica",
    "data_fundacao", "capital_social", "telefone", "email",
    "cep", "logradouro", "numero", "bairro", "cidade", "uf",
    "vendedor", "lider", "tbp",
    "status", "data_registro", "data_atualizacao",
    "pedido_tim", "obs", "registrado_por",
]


def _get_aba_carteira(gc):
    sh = gc.open_by_key(SPREADSHEET_ID)
    try:
        return sh.worksheet(ABA_CARTEIRA)
    except Exception:
        aba = sh.add_worksheet(title=ABA_CARTEIRA, rows=2000, cols=len(HEADER_CARTEIRA) + 2)
        aba.append_row(HEADER_CARTEIRA)
        return aba


@st.cache_data(ttl=30, show_spinner=False)
def _load_carteira(_gc):
    try:
        aba  = _get_aba_carteira(_gc)
        rows = aba.get_all_records()
        if not rows:
            return pd.DataFrame(columns=HEADER_CARTEIRA)
        df = pd.DataFrame(rows)
        # Garante todas as colunas
        for col in HEADER_CARTEIRA:
            if col not in df.columns:
                df[col] = ""
        return df
    except Exception as e:
        st.error(f"Erro ao carregar carteira: {e}")
        return pd.DataFrame(columns=HEADER_CARTEIRA)


def _atualizar_expirados(gc, df: pd.DataFrame) -> pd.DataFrame:
    """Marca como Expirado CNPJs com mais de 60 dias sem ativar."""
    if df.empty:
        return df
    hoje = datetime.now()
    atualizados = []
    for idx, row in df.iterrows():
        if str(row.get("status","")) != "Em Atendimento":
            continue
        data_reg = str(row.get("data_registro","")).strip()
        try:
            dt = datetime.strptime(data_reg, "%d/%m/%Y %H:%M")
            if (hoje - dt).days >= DIAS_EXPIRACAO:
                df.at[idx, "status"] = "Expirado"
                df.at[idx, "data_atualizacao"] = hoje.strftime("%d/%m/%Y %H:%M")
                atualizados.append(idx)
        except Exception:
            pass
    if atualizados:
        # Persiste no Sheets
        try:
            aba    = _get_aba_carteira(gc)
            todos  = aba.get_all_values()
            header = [str(h).strip() for h in todos[0]] if todos else []
            if "status" in header and "data_atualizacao" in header:
                col_st = header.index("status") + 1
                col_da = header.index("data_atualizacao") + 1
                col_cn = header.index("cnpj") + 1 if "cnpj" in header else None
                for idx in atualizados:
                    cnpj_alvo = df.at[idx, "cnpj"]
                    for i, row in enumerate(todos[1:], start=2):
                        if col_cn and row[col_cn - 1].strip() == cnpj_alvo:
                            aba.update_cell(i, col_st, "Expirado")
                            aba.update_cell(i, col_da, hoje.strftime("%d/%m/%Y %H:%M"))
                            break
        except Exception:
            pass
    return df


def _cnpj_disponivel(df: pd.DataFrame, cnpj: str):
    """
    Retorna (disponivel: bool, row: dict|None)
    Bloqueado apenas se status == 'Em Atendimento'.
    Expirado, Ativado e Liberado pelo Admin = disponível para novo registro.
    """
    cnpj_limpo = re.sub(r"\D", "", cnpj)
    if df.empty:
        return True, None
    match = df[df["cnpj"].astype(str).str.replace(r"\D","",regex=True) == cnpj_limpo]
    if match.empty:
        return True, None
    row = match.iloc[0]
    if str(row.get("status","")) == "Em Atendimento":
        return False, row.to_dict()
    return True, row.to_dict()


def _registrar_cnpj(gc, dados: dict, usuario: str) -> bool:
    try:
        aba  = _get_aba_carteira(gc)
        agora = datetime.now().strftime("%d/%m/%Y %H:%M")
        linha = [dados.get(c, "") for c in HEADER_CARTEIRA]
        # Garante campos de controle
        idx_status = HEADER_CARTEIRA.index("status")
        idx_data   = HEADER_CARTEIRA.index("data_registro")
        idx_datup  = HEADER_CARTEIRA.index("data_atualizacao")
        idx_reg    = HEADER_CARTEIRA.index("registrado_por")
        linha[idx_status] = "Em Atendimento"
        linha[idx_data]   = agora
        linha[idx_datup]  = agora
        linha[idx_reg]    = usuario
        aba.append_row(linha)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erro ao registrar: {e}")
        return False


def _atualizar_campo(gc, cnpj: str, campos: dict) -> bool:
    """Atualiza campos de um CNPJ existente."""
    try:
        aba   = _get_aba_carteira(gc)
        todos = aba.get_all_values()
        if not todos:
            return False
        header = [str(h).strip() for h in todos[0]]
        cnpj_limpo = re.sub(r"\D", "", cnpj)
        col_cn = header.index("cnpj") if "cnpj" in header else None
        if col_cn is None:
            return False
        campos["data_atualizacao"] = datetime.now().strftime("%d/%m/%Y %H:%M")
        for i, row in enumerate(todos[1:], start=2):
            if not row:
                continue
            val = re.sub(r"\D", "", str(row[col_cn]).strip())
            if val == cnpj_limpo:
                for campo, valor in campos.items():
                    if campo in header:
                        aba.update_cell(i, header.index(campo) + 1, valor)
                st.cache_data.clear()
                return True
        return False
    except Exception as e:
        st.error(f"Erro ao atualizar: {e}")
        return False


# ─────────────────────────────────────────────────────────────────
#  BRASIL API — CNPJ
# ─────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def buscar_cnpj(cnpj: str) -> dict:
    cnpj_limpo = re.sub(r"\D", "", cnpj)
    if len(cnpj_limpo) != 14:
        return {"erro": "CNPJ deve ter 14 dígitos"}
    try:
        r = requests.get(
            f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_limpo}",
            timeout=10
        )
        if r.status_code == 200:
            d = r.json()
            atividade = ""
            if d.get("cnae_fiscal_descricao"):
                atividade = d["cnae_fiscal_descricao"][:60]
            return {
                "cnpj":                cnpj_limpo,
                "razao_social":        d.get("razao_social", ""),
                "nome_fantasia":       d.get("nome_fantasia", "") or d.get("razao_social", ""),
                "atividade_economica": atividade,
                "data_fundacao":       d.get("data_inicio_atividade", ""),
                "capital_social":      f"R$ {d.get('capital_social', 0):,.2f}",
                "telefone":            d.get("ddd_telefone_1", ""),
                "email":               d.get("email", ""),
                "cep":                 re.sub(r"\D", "", d.get("cep", "")),
                "logradouro":          d.get("logradouro", ""),
                "numero":              d.get("numero", ""),
                "bairro":              d.get("bairro", ""),
                "cidade":              d.get("municipio", ""),
                "uf":                  d.get("uf", ""),
            }
        return {"erro": "CNPJ não encontrado na Receita Federal"}
    except Exception as e:
        return {"erro": str(e)}


# ─────────────────────────────────────────────────────────────────
#  COLABORADORES — vendedor / lider / TBP
# ─────────────────────────────────────────────────────────────────

@st.cache_data(ttl=120, show_spinner=False)
def _load_colab_carteira(_gc):
    """Carrega aba Colaboradores e retorna listas únicas de vendedor, lider e TBP."""
    try:
        df = load_colaboradores(_gc)
        if df.empty:
            return [], [], []
        # Detecta colunas por nome normalizado
        import unicodedata

        def _n(s):
            s = str(s).strip().lower()
            return "".join(c for c in unicodedata.normalize("NFD", s)
                           if unicodedata.category(c) != "Mn")

        col_map = {_n(c): c for c in df.columns}
        col_v   = col_map.get("vendedor")
        col_l   = col_map.get("lider")
        col_t   = col_map.get("tbp")

        vendedores = sorted(df[col_v].dropna().unique().tolist()) if col_v else []
        lideres    = sorted(df[col_l].dropna().unique().tolist()) if col_l else []
        tbps       = sorted(df[col_t].dropna().unique().tolist()) if col_t else []

        # Remove valores vazios/inválidos
        vendedores = [v for v in vendedores if v and str(v).strip() not in ("", "nan", "None", "VENDEDOR")]
        lideres    = [l for l in lideres    if l and str(l).strip() not in ("", "nan", "None", "LIDER", "LÍDER")]
        tbps       = [t for t in tbps       if t and str(t).strip() not in ("", "nan", "None", "TBP")]

        # Mapa vendedor → lider e vendedor → tbp
        mapa_lider = {}
        mapa_tbp   = {}
        if col_v and col_l:
            for _, row in df.iterrows():
                v = str(row.get(col_v, "")).strip()
                l = str(row.get(col_l, "")).strip()
                t = str(row.get(col_t, "")).strip() if col_t else ""
                if v:
                    if l:
                        mapa_lider[v] = l
                    if t:
                        mapa_tbp[v] = t

        return vendedores, lideres, tbps, mapa_lider, mapa_tbp
    except Exception as e:
        return [], [], [], {}, {}


# ─────────────────────────────────────────────────────────────────
#  COMPONENTES DE UI
# ─────────────────────────────────────────────────────────────────

def _formatar_cnpj(cnpj: str) -> str:
    c = re.sub(r"\D", "", str(cnpj))
    if len(c) == 14:
        return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"
    return cnpj


def _dias_restantes(data_registro: str) -> int:
    try:
        dt   = datetime.strptime(str(data_registro).strip(), "%d/%m/%Y %H:%M")
        diff = DIAS_EXPIRACAO - (datetime.now() - dt).days
        return max(diff, 0)
    except Exception:
        return DIAS_EXPIRACAO


def _card_carteira(row: dict, is_admin: bool, gc, username: str):
    """Renderiza card de cliente na carteira."""
    cnpj    = _formatar_cnpj(str(row.get("cnpj", "")))
    razao   = str(row.get("razao_social", "—"))
    fantasia= str(row.get("nome_fantasia", ""))
    vend    = str(row.get("vendedor", "—"))
    lider   = str(row.get("lider", "—"))
    tbp     = str(row.get("tbp", "—"))
    status  = str(row.get("status", "Em Atendimento"))
    data_r  = str(row.get("data_registro", ""))
    pedido  = str(row.get("pedido_tim", ""))
    obs     = str(row.get("obs", ""))
    cidade  = str(row.get("cidade", ""))
    uf      = str(row.get("uf", ""))
    cor     = COR_STATUS.get(status, "#64748b")
    dias    = _dias_restantes(data_r) if status == "Em Atendimento" else None

    dias_html = ""
    if dias is not None:
        cor_dias = "#22c55e" if dias > 30 else "#f59e0b" if dias > 10 else "#ef4444"
        dias_html = f"<span style='color:{cor_dias};font-weight:700;font-size:0.75rem'>⏱ {dias} dias restantes</span>"

    pedido_html = f"<span style='color:#60a5fa;font-size:0.73rem'>📌 TIM: {pedido}</span>" if pedido and pedido not in ("", "nan") else ""

    st.markdown(f"""
    <div class="cnpj-card {status.lower().split()[0]}">
      <div style="display:flex;justify-content:space-between;align-items:start;flex-wrap:wrap;gap:8px">
        <div style="flex:1;min-width:200px">
          <div class="empresa-nome">{razao}</div>
          <div class="empresa-info">
            {fantasia + " · " if fantasia and fantasia != razao else ""}
            {cnpj} · {cidade}/{uf}
          </div>
          <div class="empresa-info" style="margin-top:6px">
            👤 <b style="color:#e2e8f0">{vend}</b> · 
            🏅 {lider} · 
            🏢 <span style="color:#a78bfa">{tbp}</span>
          </div>
          <div style="margin-top:6px;display:flex;gap:12px;align-items:center;flex-wrap:wrap">
            {dias_html} {pedido_html}
          </div>
          {f'<div class="empresa-info" style="margin-top:4px">📝 {obs}</div>' if obs and obs not in ("", "nan") else ""}
        </div>
        <div style="display:flex;flex-direction:column;align-items:flex-end;gap:6px">
          <span class="status-pill" style="background:{cor}">{status}</span>
          <span style="font-size:0.68rem;color:#475569">{data_r[:10] if data_r else ""}</span>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Ações admin
    if is_admin:
        with st.expander(f"⚙️ Ações admin — {razao[:40]}"):
            col_s, col_p, col_o, col_btn = st.columns([2, 2, 3, 1])
            with col_s:
                novo_status = st.selectbox(
                    "Status", STATUS_CARTEIRA,
                    index=STATUS_CARTEIRA.index(status) if status in STATUS_CARTEIRA else 0,
                    key=f"st_{row.get('cnpj','')}"
                )
            with col_p:
                novo_pedido = st.text_input(
                    "Nº Pedido TIM",
                    value=pedido if pedido not in ("", "nan") else "",
                    key=f"pt_{row.get('cnpj','')}"
                )
            with col_o:
                nova_obs = st.text_input(
                    "Observação",
                    value=obs if obs not in ("", "nan") else "",
                    key=f"ob_{row.get('cnpj','')}"
                )
            with col_btn:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("💾", key=f"sv_{row.get('cnpj','')}",
                             help="Salvar alterações", use_container_width=True):
                    ok = _atualizar_campo(gc, str(row.get("cnpj", "")), {
                        "status":     novo_status,
                        "pedido_tim": novo_pedido,
                        "obs":        nova_obs,
                    })
                    if ok:
                        st.success("✅ Atualizado!")
                        st.rerun()
    else:
        # Vendedores podem registrar o nº do pedido TIM
        if status == "Em Atendimento" and (not pedido or pedido in ("", "nan")):
            with st.expander(f"📌 Registrar nº pedido TIM — {razao[:35]}"):
                col_pi, col_pbt = st.columns([3, 1])
                with col_pi:
                    np = st.text_input("Nº do Pedido TIM *",
                                       placeholder="ex: 6341069",
                                       key=f"np_{row.get('cnpj','')}")
                with col_pbt:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("✅ Salvar", key=f"spbt_{row.get('cnpj','')}",
                                 type="primary", use_container_width=True):
                        if np.strip():
                            ok = _atualizar_campo(gc, str(row.get("cnpj", "")), {
                                "pedido_tim": np.strip(),
                                "status":     "Em Atendimento",
                            })
                            if ok:
                                st.success("📌 Pedido TIM registrado!")
                                st.rerun()
                        else:
                            st.error("Informe o número do pedido.")


# ─────────────────────────────────────────────────────────────────
#  TELA — NOVO REGISTRO
# ─────────────────────────────────────────────────────────────────

def tela_novo_registro(gc, df_carteira, vendedores, mapa_lider, mapa_tbp, username, info_user):
    st.markdown('<p class="section-title">🔍 BUSCAR CLIENTE PELO CNPJ</p>', unsafe_allow_html=True)

    col_ci, col_cb = st.columns([3, 1])
    with col_ci:
        cnpj_input = st.text_input(
            "CNPJ do cliente",
            placeholder="00.000.000/0000-00",
            key="carteira_cnpj_input"
        )
    with col_cb:
        st.markdown("<br>", unsafe_allow_html=True)
        buscar = st.button("🔍 Consultar Receita", use_container_width=True, key="btn_buscar_carteira")

    if buscar and cnpj_input:
        cnpj_limpo = re.sub(r"\D", "", cnpj_input)

        # ── Verifica disponibilidade ──────────────────────────────
        df_atualizada = _atualizar_expirados(gc, df_carteira.copy())
        disponivel, row_existente = _cnpj_disponivel(df_atualizada, cnpj_limpo)

        if not disponivel and row_existente:
            # BLOQUEADO
            vend_blk  = row_existente.get("vendedor", "—")
            data_blk  = row_existente.get("data_registro", "")
            lider_blk = row_existente.get("lider", "—")
            tbp_blk   = row_existente.get("tbp", "—")
            dias_rest = _dias_restantes(data_blk)
            st.markdown(f"""
            <div class="bloqueio-box">
              <div style="font-size:1rem;font-weight:800;color:#f87171;margin-bottom:8px">
                🔒 Cliente já está em atendimento
              </div>
              <div><b>Vendedor:</b> {vend_blk} &nbsp;·&nbsp; <b>Líder:</b> {lider_blk} &nbsp;·&nbsp; <b>Escritório:</b> {tbp_blk}</div>
              <div style="margin-top:4px"><b>Desde:</b> {data_blk[:10]} &nbsp;·&nbsp; <b>Expira em:</b> {dias_rest} dias</div>
              <div style="margin-top:10px;font-size:0.82rem;color:#fca5a5">
                ⚠️ Para liberar este cliente, entre em contato com o <b>administrador</b>.
              </div>
            </div>
            """, unsafe_allow_html=True)
            return

        # Busca dados na Receita
        with st.spinner("Consultando Receita Federal..."):
            dados_receita = buscar_cnpj(cnpj_limpo)

        if "erro" in dados_receita:
            st.error(f"❌ {dados_receita['erro']}")
            return

        # CNPJ livre — avisa se já existia em outro status
        if row_existente:
            status_ant = row_existente.get("status", "")
            st.info(f"ℹ️ Este CNPJ já esteve na carteira com status **{status_ant}**. Você pode registrar novamente.")

        st.success(f"✅ **{dados_receita['razao_social']}** encontrado! Confirme os dados abaixo.")
        st.session_state["carteira_dados_receita"] = dados_receita

    # ── Formulário de registro ────────────────────────────────────
    c = st.session_state.get("carteira_dados_receita", {})
    if not c:
        st.markdown("""
        <div style="background:#0d1f14;border:1px solid #14532d;border-radius:10px;
                    padding:20px;text-align:center;margin-top:20px">
          <div style="font-size:2rem">📁</div>
          <div style="color:#4ade80;font-weight:700;margin-top:8px">
            Digite o CNPJ acima para iniciar o atendimento
          </div>
          <div style="color:#64748b;font-size:0.82rem;margin-top:4px">
            Os dados da empresa serão preenchidos automaticamente pela Receita Federal
          </div>
        </div>
        """, unsafe_allow_html=True)
        return

    with st.form("form_carteira_registro"):
        st.markdown('<p class="section-title">🏢 DADOS DO CLIENTE (RECEITA FEDERAL)</p>', unsafe_allow_html=True)

        col1, col2, col3 = st.columns(3)
        with col1:
            razao    = st.text_input("Razão Social *", value=c.get("razao_social", ""))
            telefone = st.text_input("Telefone", value=c.get("telefone", ""))
            cidade   = st.text_input("Cidade", value=c.get("cidade", ""))
        with col2:
            fantasia  = st.text_input("Nome Fantasia", value=c.get("nome_fantasia", ""))
            email     = st.text_input("Email", value=c.get("email", ""))
            uf        = st.text_input("UF", value=c.get("uf", ""))
        with col3:
            atividade = st.text_input("Atividade Econômica", value=c.get("atividade_economica", ""))
            fundacao  = st.text_input("Data Fundação", value=c.get("data_fundacao", ""))
            capital   = st.text_input("Capital Social", value=c.get("capital_social", ""))

        st.markdown('<p class="section-title">👤 RESPONSÁVEL PELO ATENDIMENTO</p>', unsafe_allow_html=True)

        col_v, col_l, col_t = st.columns(3)

        # Pré-seleciona o vendedor do usuário logado se for lider/vendedor
        pre_vend = info_user.get("lider", "") or ""

        with col_v:
            if vendedores:
                idx_vend = 0
                if pre_vend and pre_vend in vendedores:
                    idx_vend = vendedores.index(pre_vend)
                vendedor_sel = st.selectbox("Vendedor *", vendedores, index=idx_vend, key="cart_vend")
            else:
                vendedor_sel = st.text_input("Vendedor *", value=pre_vend, key="cart_vend_txt")

        # Auto-preenche líder e TBP com base no vendedor selecionado
        lider_auto = mapa_lider.get(vendedor_sel, "") if isinstance(vendedor_sel, str) else ""
        tbp_auto   = mapa_tbp.get(vendedor_sel, "")   if isinstance(vendedor_sel, str) else ""

        with col_l:
            lider_val = st.text_input("Líder", value=lider_auto, key="cart_lider",
                                      help="Preenchido automaticamente pela Colaboradores")
        with col_t:
            tbp_val = st.text_input("Escritório (TBP)", value=tbp_auto, key="cart_tbp",
                                    help="Preenchido automaticamente pela coluna TBP")

        obs_val = st.text_area("Observações (opcional)", height=70, key="cart_obs")

        st.markdown("")
        submitted = st.form_submit_button(
            "📁 Registrar Cliente na Carteira",
            type="primary",
            use_container_width=True
        )

        if submitted:
            if not razao.strip():
                st.error("⚠️ Razão Social é obrigatória.")
            elif not vendedor_sel or str(vendedor_sel).strip() in ("", "— Selecione —"):
                st.error("⚠️ Selecione o vendedor responsável.")
            else:
                dados_salvar = {
                    "cnpj":                re.sub(r"\D", "", c.get("cnpj", "")),
                    "razao_social":        razao.strip(),
                    "nome_fantasia":       fantasia.strip(),
                    "atividade_economica": atividade.strip(),
                    "data_fundacao":       fundacao.strip(),
                    "capital_social":      capital.strip(),
                    "telefone":            telefone.strip(),
                    "email":               email.strip(),
                    "cep":                 c.get("cep", ""),
                    "logradouro":          c.get("logradouro", ""),
                    "numero":              c.get("numero", ""),
                    "bairro":              c.get("bairro", ""),
                    "cidade":              cidade.strip(),
                    "uf":                  uf.strip(),
                    "vendedor":            str(vendedor_sel).strip(),
                    "lider":               lider_val.strip(),
                    "tbp":                 tbp_val.strip(),
                    "status":              "Em Atendimento",
                    "obs":                 obs_val.strip(),
                    "registrado_por":      username,
                    "pedido_tim":          "",
                }
                with st.spinner("Registrando cliente na carteira..."):
                    ok = _registrar_cnpj(gc, dados_salvar, username)

                if ok:
                    empresa = dados_salvar["razao_social"]
                    st.success(f"""
                    ✅ **{empresa}** registrada na carteira!

                    Vendedor: **{dados_salvar['vendedor']}** · Escritório: **{dados_salvar['tbp']}**

                    Quando o pedido for cadastrado no sistema TIM, volte aqui para registrar o número do pedido.
                    """)
                    st.session_state.pop("carteira_dados_receita", None)
                    st.rerun()


# ─────────────────────────────────────────────────────────────────
#  TELA — MINHA CARTEIRA / CARTEIRA DA EQUIPE
# ─────────────────────────────────────────────────────────────────

def tela_carteira(gc, df, info_user, username, is_admin):
    tipo   = info_user.get("tipo", "lider")
    lider_u = info_user.get("lider", "")

    st.markdown('<p class="section-title">🔍 FILTROS</p>', unsafe_allow_html=True)

    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
    with col_f1:
        busca = st.text_input("Empresa / CNPJ", key="cart_busca")
    with col_f2:
        status_f = st.selectbox("Status", ["Todos"] + STATUS_CARTEIRA, key="cart_sf")
    with col_f3:
        if is_admin:
            tbps_disp = ["Todos"] + sorted(df["tbp"].dropna().unique().tolist()) if "tbp" in df.columns else ["Todos"]
            tbp_f = st.selectbox("Escritório (TBP)", tbps_disp, key="cart_tbpf")
        else:
            tbp_f = "Todos"
    with col_f4:
        if is_admin:
            lideres_disp = ["Todos"] + sorted(df["lider"].dropna().unique().tolist()) if "lider" in df.columns else ["Todos"]
            lider_f = st.selectbox("Líder", lideres_disp, key="cart_lf")
        else:
            lider_f = "Todos"

    # Aplica filtros de perfil
    df_f = df.copy()
    if not is_admin and tipo == "lider" and lider_u:
        df_f = df_f[df_f["lider"].astype(str).str.strip().str.upper() == lider_u.strip().upper()]

    # Aplica filtros de UI
    if busca:
        mask = (
            df_f["razao_social"].astype(str).str.contains(busca, case=False, na=False) |
            df_f["cnpj"].astype(str).str.contains(re.sub(r"\D","",busca), na=False)
        )
        df_f = df_f[mask]
    if status_f != "Todos":
        df_f = df_f[df_f["status"] == status_f]
    if tbp_f != "Todos" and "tbp" in df_f.columns:
        df_f = df_f[df_f["tbp"].astype(str).str.strip() == tbp_f]
    if lider_f != "Todos" and "lider" in df_f.columns:
        df_f = df_f[df_f["lider"].astype(str).str.strip() == lider_f]

    df_f = df_f.sort_values("data_registro", ascending=False) if "data_registro" in df_f.columns else df_f

    st.caption(f"**{len(df_f)}** cliente(s) encontrado(s)")
    st.markdown("")

    if df_f.empty:
        st.markdown("""
        <div style="background:#0d1f14;border:1px solid #14532d;border-radius:10px;
                    padding:24px;text-align:center">
          <div style="font-size:2rem">📭</div>
          <div style="color:#4ade80;font-weight:700;margin-top:8px">Nenhum cliente na carteira</div>
          <div style="color:#64748b;font-size:0.82rem">Use a aba <b>➕ Novo Registro</b> para adicionar clientes</div>
        </div>
        """, unsafe_allow_html=True)
        return

    for _, row in df_f.iterrows():
        _card_carteira(row.to_dict(), is_admin, gc, username)


# ─────────────────────────────────────────────────────────────────
#  TELA — VISÃO ADMIN (tabela + liberação em lote)
# ─────────────────────────────────────────────────────────────────

def tela_admin(gc, df):
    st.markdown('<p class="section-title">📊 VISÃO GERENCIAL — TODOS OS REGISTROS</p>', unsafe_allow_html=True)

    if df.empty:
        st.info("Nenhum registro na carteira.")
        return

    # KPIs gerenciais
    total     = len(df)
    em_atend  = len(df[df["status"] == "Em Atendimento"])
    ativados  = len(df[df["status"] == "Ativado"])
    expirados = len(df[df["status"] == "Expirado"])

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(f"""<div class="kpi-mini blue">
          <div class="kpi-label">📁 Total</div>
          <div class="kpi-value">{total}</div>
          <div class="kpi-sub">CNPJs na carteira</div></div>""", unsafe_allow_html=True)
    with k2:
        st.markdown(f"""<div class="kpi-mini amber">
          <div class="kpi-label">⏳ Em Atendimento</div>
          <div class="kpi-value">{em_atend}</div>
          <div class="kpi-sub">em andamento</div></div>""", unsafe_allow_html=True)
    with k3:
        st.markdown(f"""<div class="kpi-mini green">
          <div class="kpi-label">✅ Ativados</div>
          <div class="kpi-value">{ativados}</div>
          <div class="kpi-sub">contratos ativados</div></div>""", unsafe_allow_html=True)
    with k4:
        st.markdown(f"""<div class="kpi-mini red">
          <div class="kpi-label">💤 Expirados</div>
          <div class="kpi-value">{expirados}</div>
          <div class="kpi-sub">+{DIAS_EXPIRACAO} dias sem ativar</div></div>""", unsafe_allow_html=True)

    st.markdown("")

    # Tabela completa
    cols_show = [c for c in [
        "cnpj", "razao_social", "vendedor", "lider", "tbp",
        "status", "data_registro", "pedido_tim", "cidade", "uf"
    ] if c in df.columns]

    col_cfg = {
        "cnpj":          "CNPJ",
        "razao_social":  "Razão Social",
        "vendedor":      "Vendedor",
        "lider":         "Líder",
        "tbp":           "Escritório",
        "status":        "Status",
        "data_registro": "Registrado em",
        "pedido_tim":    "Nº Pedido TIM",
        "cidade":        "Cidade",
        "uf":            "UF",
    }

    st.dataframe(
        df[cols_show].reset_index(drop=True),
        use_container_width=True,
        hide_index=True,
        column_config={k: v for k, v in col_cfg.items() if k in cols_show},
    )

    # Export CSV
    st.markdown("")
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Exportar CSV completo",
        csv, "carteira_atendimento.csv", "text/csv",
        key="cart_export"
    )

    # Liberação manual pelo admin
    st.markdown('<p class="section-title">🔓 LIBERAR CNPJ MANUALMENTE</p>', unsafe_allow_html=True)
    st.caption("Use para liberar um cliente bloqueado sem aguardar os 60 dias.")

    col_lib, col_mot, col_lbt = st.columns([2, 3, 1])
    with col_lib:
        cnpj_lib = st.text_input("CNPJ a liberar", placeholder="00.000.000/0000-00", key="cart_lib_cnpj")
    with col_mot:
        mot_lib  = st.text_input("Motivo da liberação", key="cart_lib_motivo")
    with col_lbt:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔓 Liberar", key="cart_btn_lib", type="primary", use_container_width=True):
            if cnpj_lib.strip():
                ok = _atualizar_campo(gc, cnpj_lib.strip(), {
                    "status": "Liberado pelo Admin",
                    "obs":    f"[Admin] {mot_lib.strip()}" if mot_lib.strip() else "[Admin] Liberado manualmente",
                })
                if ok:
                    st.success(f"✅ CNPJ {_formatar_cnpj(cnpj_lib)} liberado!")
                    st.rerun()
                else:
                    st.error("CNPJ não encontrado na carteira.")
            else:
                st.error("Informe o CNPJ.")


# ─────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────

def main():
    # ── Auth ─────────────────────────────────────────────────────
    config = _carregar_auth()
    authenticator = stauth.Authenticate(
        config["credentials"],
        config["cookie"]["name"],
        config["cookie"]["key"],
        config["cookie"]["expiry_days"],
    )

    name, authentication_status, username = authenticator.login(
        location="main", fields={
            "Form name": "📁 Carteira de Atendimento — Connect Group",
            "Username": "Usuário",
            "Password": "Senha",
            "Login": "Entrar",
        }
    )

    if authentication_status is False:
        st.error("Usuário ou senha incorretos.")
        return
    if authentication_status is None:
        st.markdown("""
        <div style="text-align:center;padding:40px 0;color:#64748b;font-size:0.85rem">
          Connect Group · TIM Empresas · Sistema de Carteira de Atendimento
        </div>
        """, unsafe_allow_html=True)
        return

    # ── Usuário autenticado ───────────────────────────────────────
    info_user = _info_usuario(username)
    tipo      = info_user.get("tipo", "lider")
    is_admin  = (tipo == "admin")

    badge_map = {"admin": "👑 Admin", "lider": "🏅 Líder", "parceiro": "🤝 Parceiro"}
    badge     = badge_map.get(tipo, "👤 Usuário")

    # ── Header ───────────────────────────────────────────────────
    st.markdown(f"""
    <div class="header-carteira">
      <div>
        <p class="header-title">📁 Carteira de Atendimento</p>
        <p class="header-sub">Connect Group · TIM Empresas · Bem-vindo, {name}</p>
      </div>
      <div style="display:flex;align-items:center;gap:12px">
        <img src="https://raw.githubusercontent.com/hugokhesley/dashboard-tim-connectgroup-sheets/main/logo.png"
             style="height:40px;object-fit:contain;border-radius:6px" onerror="this.style.display='none'">
        <span class="header-badge">{badge}</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Sidebar ───────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(f"**{badge}**")
        st.caption(f"{name} · {username}")
        st.markdown("---")
        if st.button("🔄 Atualizar dados", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        st.markdown("---")
        authenticator.logout("🚪 Sair", "sidebar")
        st.caption(f"Bloqueio: {DIAS_EXPIRACAO} dias sem ativar")
        st.caption("Dados via Google Sheets · cache 30s")

    # ── Carrega dados ─────────────────────────────────────────────
    gc = get_gspread_client()
    with st.spinner("Carregando carteira..."):
        df_raw     = _load_carteira(gc)
        df_carteira = _atualizar_expirados(gc, df_raw.copy())
        try:
            result_colab = _load_colab_carteira(gc)
            if len(result_colab) == 5:
                vendedores, lideres, tbps, mapa_lider, mapa_tbp = result_colab
            else:
                vendedores, lideres, tbps, mapa_lider, mapa_tbp = [], [], [], {}, {}
        except Exception:
            vendedores, lideres, tbps, mapa_lider, mapa_tbp = [], [], [], {}, {}

    # KPIs rápidos no topo
    total_cart = len(df_carteira)
    em_atend   = len(df_carteira[df_carteira["status"] == "Em Atendimento"]) if not df_carteira.empty else 0
    ativados_c = len(df_carteira[df_carteira["status"] == "Ativado"])        if not df_carteira.empty else 0
    expirados_c= len(df_carteira[df_carteira["status"] == "Expirado"])       if not df_carteira.empty else 0

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(f"""<div class="kpi-mini blue"><div class="kpi-label">📁 Carteira Total</div>
          <div class="kpi-value">{total_cart}</div><div class="kpi-sub">CNPJs registrados</div></div>""",
          unsafe_allow_html=True)
    with k2:
        st.markdown(f"""<div class="kpi-mini amber"><div class="kpi-label">⏳ Em Atendimento</div>
          <div class="kpi-value">{em_atend}</div><div class="kpi-sub">em andamento</div></div>""",
          unsafe_allow_html=True)
    with k3:
        st.markdown(f"""<div class="kpi-mini green"><div class="kpi-label">✅ Ativados</div>
          <div class="kpi-value">{ativados_c}</div><div class="kpi-sub">contratos fechados</div></div>""",
          unsafe_allow_html=True)
    with k4:
        st.markdown(f"""<div class="kpi-mini red"><div class="kpi-label">💤 Expirados</div>
          <div class="kpi-value">{expirados_c}</div><div class="kpi-sub">{DIAS_EXPIRACAO}+ dias</div></div>""",
          unsafe_allow_html=True)

    st.markdown("")

    # ── Tabs ──────────────────────────────────────────────────────
    if is_admin:
        tab_cart, tab_novo, tab_admin = st.tabs([
            "📋 Carteira",
            "➕ Novo Registro",
            "⚙️ Admin",
        ])
        with tab_cart:
            tela_carteira(gc, df_carteira, info_user, username, is_admin)
        with tab_novo:
            tela_novo_registro(gc, df_carteira, vendedores, mapa_lider, mapa_tbp, username, info_user)
        with tab_admin:
            tela_admin(gc, df_carteira)
    else:
        tab_cart, tab_novo = st.tabs([
            "📋 Minha Carteira",
            "➕ Novo Registro",
        ])
        with tab_cart:
            tela_carteira(gc, df_carteira, info_user, username, is_admin)
        with tab_novo:
            tela_novo_registro(gc, df_carteira, vendedores, mapa_lider, mapa_tbp, username, info_user)


main()
