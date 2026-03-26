import streamlit as st
import streamlit_authenticator as stauth

# ---------------------------------------------------------------------------
# CONFIGURAÇÃO DE USUÁRIOS
# auto_hash=True — senhas em texto puro nos secrets, bcrypt aplicado na memória
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


def get_authenticator():
    return stauth.Authenticate(
        credentials=_build_credentials(),
        cookie_name="connectgroup_auth",
        cookie_key=st.secrets["auth"]["cookie_key"],
        cookie_expiry_days=1,
        auto_hash=False,   # senhas já vêm hasheadas com bcrypt nos secrets
    )


def require_login(pagina: str) -> str:
    """
    Exibe tela de login se não autenticado.
    Verifica acesso à página.
    Retorna username. Chama st.stop() se não autorizado.

    Compatível com streamlit-authenticator >= 0.3.x
    Na 0.3+/0.4+, o estado fica em st.session_state após .login()
    """
    authenticator = get_authenticator()

    # Renderiza o widget de login (retorna None na 0.4.x — estado em session_state)
    authenticator.login(
        location="main",
        fields={
            "Form name": "🔐 Connect Group — Liderança",
            "Username":  "Usuário",
            "Password":  "Senha",
            "Login":     "Entrar",
        }
    )

    auth_status = st.session_state.get("authentication_status")
    username    = st.session_state.get("username")
    name        = st.session_state.get("name")

    if auth_status is False:
        st.error("❌ Usuário ou senha incorretos.")
        st.stop()

    if not auth_status:
        # Ainda não tentou logar — aguarda
        st.stop()

    # Autenticado — verifica acesso à página
    permitidos = PAGE_ACCESS.get(pagina, [])
    if username not in permitidos:
        st.error("🚫 Seu usuário não tem acesso a esta página.")
        authenticator.logout(button_name="Sair", location="main")
        st.stop()

    # Logout discreto na sidebar
    with st.sidebar:
        st.markdown(f"👤 **{name}**")
        authenticator.logout(button_name="Sair", location="sidebar")

    return username
