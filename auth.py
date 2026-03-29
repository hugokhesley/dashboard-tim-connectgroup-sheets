import streamlit as st
import streamlit_authenticator as stauth

# ---------------------------------------------------------------------------
# CONFIGURAÇÃO DE USUÁRIOS
# ---------------------------------------------------------------------------

def _build_credentials():
    s = st.secrets["auth"]
    return {
        "usernames": {
            "hugo":      {"name": "Hugo",      "password": s["hugo_pw"]},
            "angelo":    {"name": "Angelo",    "password": s["angelo_pw"]},
            "roberta":   {"name": "Roberta",   "password": s["roberta_pw"]},
            "erivan":    {"name": "Erivan",    "password": s["erivan_pw"]},
            "alice":     {"name": "Alice",     "password": s["alice_pw"]},
            "andrey":    {"name": "Andrey",    "password": s["andrey_pw"]},
            "bertulio":  {"name": "Bertulio",  "password": s["bertulio_pw"]},
            "nivandro":  {"name": "Nivandro",  "password": s["nivandro_pw"]},
            "welligton": {"name": "Welligton", "password": s["welligton_pw"]},
        }
    }

# ---------------------------------------------------------------------------
# CONTROLE DE ACESSO POR PÁGINA
# ---------------------------------------------------------------------------

PAGE_ACCESS = {
    "tramitacao":  ["hugo", "angelo", "roberta", "erivan", "alice", "andrey", "bertulio", "nivandro", "welligton"],
    "pos_venda":   ["hugo", "angelo"],
    "resultados":  ["hugo", "angelo"],
    "qualidade":   ["hugo", "angelo", "roberta", "erivan", "alice", "andrey", "bertulio", "nivandro", "welligton"],
    "performance": ["hugo", "angelo"],
    "atividade":   ["hugo", "angelo", "roberta", "erivan", "alice", "andrey", "bertulio", "nivandro", "welligton"],
    "consolidada": ["hugo", "angelo"],
}

# ---------------------------------------------------------------------------
# CSS DA TELA DE LOGIN
# ---------------------------------------------------------------------------

LOGIN_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background-color: #0a0e1a !important;
}

.stApp {
    background: linear-gradient(135deg, #0a0e1a 0%, #0f1629 50%, #0a0e1a 100%) !important;
}

/* Esconde sidebar na tela de login */
section[data-testid="stSidebar"] { display: none !important; }

/* Remove padding padrão do Streamlit */
.block-container {
    padding-top: 0 !important;
    max-width: 100% !important;
}

/* Container central do login */
.login-wrapper {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 100vh;
    padding: 20px;
}

.login-card {
    background: #111827;
    border: 1px solid #1e2d4a;
    border-radius: 24px;
    padding: 48px 44px;
    width: 100%;
    max-width: 420px;
    box-shadow: 0 24px 64px rgba(0,0,0,0.5), 0 0 0 1px rgba(59,130,246,0.1);
    text-align: center;
}

.login-logo {
    width: 180px;
    height: auto;
    margin: 0 auto 28px auto;
    display: block;
}

.login-divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, #1e3a5f, transparent);
    margin: 24px 0;
}

.login-title {
    font-size: 1.35rem;
    font-weight: 700;
    color: #f1f5f9;
    margin: 0 0 4px 0;
}

.login-sub {
    font-size: 0.82rem;
    color: #64748b;
    margin: 0 0 28px 0;
}

.login-footer {
    margin-top: 28px;
    font-size: 0.72rem;
    color: #334155;
    text-align: center;
}

/* Estiliza o formulário do streamlit-authenticator */
div[data-testid="stForm"] {
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
}

/* Inputs */
div[data-testid="stTextInput"] input {
    background: #1a2234 !important;
    border: 1px solid #1e3a5f !important;
    border-radius: 10px !important;
    color: #e2e8f0 !important;
    font-size: 0.9rem !important;
    padding: 12px 16px !important;
}

div[data-testid="stTextInput"] input:focus {
    border-color: #3b82f6 !important;
    box-shadow: 0 0 0 2px rgba(59,130,246,0.15) !important;
}

div[data-testid="stTextInput"] label {
    color: #94a3b8 !important;
    font-size: 0.8rem !important;
    font-weight: 500 !important;
}

/* Botão de login */
div[data-testid="stForm"] button[kind="primaryFormSubmit"],
div[data-testid="stForm"] button[kind="primary"] {
    background: linear-gradient(135deg, #1d4ed8, #3b82f6) !important;
    color: #fff !important;
    border: none !important;
    border-radius: 10px !important;
    padding: 12px 24px !important;
    font-weight: 600 !important;
    font-size: 0.9rem !important;
    width: 100% !important;
    cursor: pointer !important;
    transition: all 0.2s !important;
    letter-spacing: 0.3px !important;
    box-shadow: 0 4px 16px rgba(59,130,246,0.3) !important;
}

div[data-testid="stForm"] button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 20px rgba(59,130,246,0.4) !important;
}

/* Remove título padrão do formulário */
div[data-testid="stForm"] h2,
div[data-testid="stForm"] h3 {
    display: none !important;
}

/* Sidebar após login */
section[data-testid="stSidebar"] {
    background: #111827 !important;
    display: block !important;
}

.user-info {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    background: #1a2234;
    border-radius: 10px;
    margin-bottom: 8px;
    border: 1px solid #1e3a5f;
}

.user-avatar {
    width: 32px;
    height: 32px;
    background: linear-gradient(135deg, #1d4ed8, #3b82f6);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.85rem;
    font-weight: 700;
    color: #fff;
}

.user-name {
    font-size: 0.85rem;
    font-weight: 600;
    color: #e2e8f0;
}
</style>
"""

LOGO_URL = "https://raw.githubusercontent.com/hugokhesley/dashboard-tim-connectgroup-sheets/main/logo.png"

def _render_login_page():
    """Renderiza a tela de login estilizada."""
    st.markdown(LOGIN_CSS, unsafe_allow_html=True)
    st.markdown(f"""
    <div style="display:flex;justify-content:center;align-items:center;min-height:85vh">
      <div style="background:#111827;border:1px solid #1e2d4a;border-radius:24px;
                  padding:48px 44px;width:100%;max-width:420px;
                  box-shadow:0 24px 64px rgba(0,0,0,0.5)">
        <img src="{LOGO_URL}" style="width:180px;height:auto;margin:0 auto 28px auto;display:block"
             onerror="this.style.display='none'">
        <div style="height:1px;background:linear-gradient(90deg,transparent,#1e3a5f,transparent);margin:0 0 24px 0"></div>
        <p style="font-size:1.25rem;font-weight:700;color:#f1f5f9;margin:0 0 4px 0;text-align:center">
          Área Restrita
        </p>
        <p style="font-size:0.82rem;color:#64748b;margin:0 0 24px 0;text-align:center">
          Connect Group · TIM Empresas · Liderança
        </p>
      </div>
    </div>
    """, unsafe_allow_html=True)


def get_authenticator():
    return stauth.Authenticate(
        credentials=_build_credentials(),
        cookie_name="connectgroup_auth",
        cookie_key=st.secrets["auth"]["cookie_key"],
        cookie_expiry_days=1,
        auto_hash=False,
    )


def require_login(pagina: str) -> str:
    """
    Exibe tela de login estilizada se não autenticado.
    Verifica acesso à página e retorna username.
    """
    auth_status = st.session_state.get("authentication_status")

    # Injeta CSS em todas as situações
    st.markdown(LOGIN_CSS, unsafe_allow_html=True)

    authenticator = get_authenticator()

    if not auth_status:
        # Cabeçalho visual antes do formulário
        st.markdown(f"""
        <div style="display:flex;flex-direction:column;align-items:center;
                    padding:40px 20px 8px 20px">
          <img src="{LOGO_URL}"
               style="width:200px;height:auto;margin-bottom:32px"
               onerror="this.style.display='none'">
          <div style="height:1px;width:320px;background:linear-gradient(90deg,transparent,#1e3a5f,transparent);margin-bottom:24px"></div>
          <p style="font-size:1.3rem;font-weight:700;color:#f1f5f9;margin:0 0 6px 0">
            Área Restrita
          </p>
          <p style="font-size:0.83rem;color:#64748b;margin:0 0 32px 0">
            Connect Group · TIM Empresas · Liderança
          </p>
        </div>
        """, unsafe_allow_html=True)

        # Centraliza o formulário
        col_l, col_m, col_r = st.columns([1, 1.2, 1])
        with col_m:
            authenticator.login(
                location="main",
                fields={
                    "Form name": "",
                    "Username":  "Usuário",
                    "Password":  "Senha",
                    "Login":     "Entrar",
                }
            )

        auth_status = st.session_state.get("authentication_status")

        if auth_status is False:
            with col_m:
                st.error("❌ Usuário ou senha incorretos.")
            st.stop()

        if not auth_status:
            st.markdown("""
            <p style="text-align:center;font-size:0.72rem;color:#334155;margin-top:16px">
              Acesso exclusivo para liderança Connect Group
            </p>
            """, unsafe_allow_html=True)
            st.stop()

    # ── Autenticado ──────────────────────────────────────────
    username = st.session_state.get("username")
    name     = st.session_state.get("name")

    # Verifica acesso à página
    permitidos = PAGE_ACCESS.get(pagina, [])
    if username not in permitidos:
        st.error("🚫 Seu usuário não tem acesso a esta página.")
        authenticator.logout(button_name="Sair", location="main")
        st.stop()

    # Info do usuário + logout na sidebar
    with st.sidebar:
        inicial = name[0].upper() if name else "?"
        st.markdown(f"""
        <div class="user-info">
          <div class="user-avatar">{inicial}</div>
          <span class="user-name">{name}</span>
        </div>
        """, unsafe_allow_html=True)
        authenticator.logout(button_name="Sair →", location="sidebar")
        st.markdown("---")

    return username
