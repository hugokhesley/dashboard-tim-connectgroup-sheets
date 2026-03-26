import streamlit as st
import streamlit_authenticator as stauth

# ---------------------------------------------------------------------------
# CONFIGURAÇÃO DE USUÁRIOS
# Senhas hasheadas com bcrypt — alterar via secrets.toml no Streamlit Cloud
# ---------------------------------------------------------------------------

CREDENTIALS = {
    "usernames": {
        "hugo": {
            "name": "Hugo",
            "password": st.secrets["auth"]["hugo_pw"],
        },
        "angelo": {
            "name": "Angelo",
            "password": st.secrets["auth"]["angelo_pw"],
        },
        "roberta": {
            "name": "Roberta",
            "password": st.secrets["auth"]["roberta_pw"],
        },
        "erivan": {
            "name": "Erivan",
            "password": st.secrets["auth"]["erivan_pw"],
        },
        "alice": {
            "name": "Alice",
            "password": st.secrets["auth"]["alice_pw"],
        },
        "andrey": {
            "name": "Andrey",
            "password": st.secrets["auth"]["andrey_pw"],
        },
        "bertulio": {
            "name": "Bertulio",
            "password": st.secrets["auth"]["bertulio_pw"],
        },
        "nivandro": {
            "name": "Nivandro",
            "password": st.secrets["auth"]["nivandro_pw"],
        },
        "welligton": {
            "name": "Welligton",
            "password": st.secrets["auth"]["welligton_pw"],
        },
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
        credentials=CREDENTIALS,
        cookie_name="connectgroup_auth",
        cookie_key=st.secrets["auth"]["cookie_key"],
        cookie_expiry_days=1,
    )


def require_login(pagina: str) -> str:
    """
    Exibe tela de login se não autenticado.
    Verifica se o usuário tem acesso à página.
    Retorna o username logado.
    Chama st.stop() se não autorizado.
    """
    authenticator = get_authenticator()

    name, authentication_status, username = authenticator.login(
        location="main",
        fields={
            "Form name": "🔐 Connect Group — Liderança",
            "Username":  "Usuário",
            "Password":  "Senha",
            "Login":     "Entrar",
        }
    )

    if authentication_status is False:
        st.error("❌ Usuário ou senha incorretos.")
        st.stop()

    if authentication_status is None:
        st.stop()

    # Verifica acesso à página
    permitidos = PAGE_ACCESS.get(pagina, [])
    if username not in permitidos:
        st.error("🚫 Seu usuário não tem acesso a esta página.")
        authenticator.logout("Sair", location="main")
        st.stop()

    # Logout discreto na sidebar
    with st.sidebar:
        st.markdown(f"👤 **{name}**")
        authenticator.logout("Sair", location="sidebar")

    return username
