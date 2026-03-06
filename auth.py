"""
Módulo de autenticação por senha para páginas do dashboard.

Uso:
    from auth import require_password
    require_password("qualidade")  # chave no secrets [passwords]

Secrets necessários (.streamlit/secrets.toml):
    [passwords]
    qualidade = "senha123"
    resultados = "outrasenha"
"""

import streamlit as st


def require_password(page_key: str, title: str = "Acesso Restrito"):
    """
    Bloqueia a página com uma senha.
    - page_key: chave dentro de [passwords] nos secrets
    - title: título exibido na tela de login
    Retorna True se autenticado, False caso contrário (e para a execução).
    """
    session_key = f"auth_{page_key}"

    # Já autenticado nesta sessão
    if st.session_state.get(session_key):
        return True

    # Verifica se a senha está configurada nos secrets
    try:
        senha_correta = st.secrets["passwords"][page_key]
    except (KeyError, Exception):
        # Se não houver senha configurada, libera acesso
        st.session_state[session_key] = True
        return True

    # Tela de login
    st.markdown(f"""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
      html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}
      .stApp {{ background-color: #0f1117; }}
      .login-wrap {{
        display: flex; flex-direction: column; align-items: center;
        justify-content: center; min-height: 70vh; gap: 0;
      }}
      .login-box {{
        background: #1a1230;
        border: 1px solid #2d1f4e;
        border-radius: 20px;
        padding: 48px 52px;
        width: 100%;
        max-width: 420px;
        box-shadow: 0 20px 60px rgba(124,58,237,0.25);
      }}
      .login-icon {{ font-size: 2.8rem; text-align: center; margin-bottom: 8px; }}
      .login-title {{
        font-size: 1.5rem; font-weight: 800; color: #f1f5f9;
        text-align: center; margin-bottom: 4px;
      }}
      .login-sub {{
        font-size: 0.82rem; color: #64748b;
        text-align: center; margin-bottom: 28px;
      }}
    </style>
    <div class="login-wrap">
      <div class="login-box">
        <div class="login-icon">🔐</div>
        <div class="login-title">{title}</div>
        <div class="login-sub">Digite a senha para acessar esta área</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Inputs centralizados
    col_l, col_c, col_r = st.columns([1, 2, 1])
    with col_c:
        senha_input = st.text_input(
            "Senha",
            type="password",
            placeholder="••••••••",
            label_visibility="collapsed",
            key=f"input_{page_key}"
        )
        entrar = st.button("Entrar", use_container_width=True, type="primary")

        if entrar or senha_input:
            if senha_input == senha_correta:
                st.session_state[session_key] = True
                st.rerun()
            elif senha_input:
                st.error("Senha incorreta. Tente novamente.")

    st.stop()
