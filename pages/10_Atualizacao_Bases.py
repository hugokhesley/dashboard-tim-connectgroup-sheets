"""
09_Atualizacao_Bases.py — Acesso Rápido aos sistemas TIM
Connect Group | Dashboard TIM Empresas
Acesso restrito: hugo
"""

import streamlit as st
import requests
import gspread
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from auth import require_login
from ui import aplicar_estilo_base
from data_loader import registrar_acesso, get_gspread_client

# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Connect Group | Acesso Rápido",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded",
)

username = require_login("atualizacao_bases")
aplicar_estilo_base()
registrar_acesso("Atualização de Bases", username=username)

st.markdown("""
<style>
  .header-res {
    background: linear-gradient(135deg, #0f2027 0%, #203a43 50%, #2c5364 100%);
    border-radius: 16px; padding: 28px 36px; margin-bottom: 28px;
    box-shadow: 0 8px 32px rgba(44,83,100,0.3);
    border: 1px solid rgba(255,255,255,0.08);
  }
  .header-title { font-size: 1.9rem; font-weight: 800; color: #fff; margin: 0; }
  .header-sub   { font-size: 0.85rem; color: rgba(255,255,255,0.65); margin: 4px 0 0 0; }
  section[data-testid="stSidebar"] { background: #111827 !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="header-res">
  <div>
    <p class="header-title">🌐 Acesso Rápido</p>
    <p class="header-sub">Abre os sistemas TIM com login automático para cada conta</p>
  </div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# CONFIGURAÇÕES
# ─────────────────────────────────────────────

SPREADSHEET_ID = "1HmtEFf2Akh7NLR2prxDh9S4gmioKYw419B4bkx4yBLg"

SISTEMAS_DISPONIVEIS = {
    "radar":   {"label": "📡 Radar TIM",  "emoji": "📡"},
    "phoenix": {"label": "🔥 Phoenix",    "emoji": "🔥"},
}

# ─────────────────────────────────────────────
# CONTAS DO SHEETS
# ─────────────────────────────────────────────

@st.cache_data(ttl=30, show_spinner=False)
def carregar_contas_radar():
    try:
        gc = get_gspread_client()
        planilha = gc.open_by_key(SPREADSHEET_ID)
        try:
            aba = planilha.worksheet("ContasRadar")
            dados = aba.get_all_records()
            return dados
        except gspread.WorksheetNotFound:
            aba = planilha.add_worksheet(title="ContasRadar", rows=20, cols=2)
            aba.update([
                ["login", "nome"],
                ["t3729525", "Campina Grande"],
                ["t3761125", "Serra Redonda"],
            ])
            return [
                {"login": "t3729525", "nome": "Campina Grande"},
                {"login": "t3761125", "nome": "Serra Redonda"},
            ]
    except Exception as e:
        st.warning(f"Não foi possível carregar contas: {e}")
        return []


def salvar_contas_radar(contas: list):
    gc = get_gspread_client()
    planilha = gc.open_by_key(SPREADSHEET_ID)
    try:
        aba = planilha.worksheet("ContasRadar")
    except gspread.WorksheetNotFound:
        aba = planilha.add_worksheet(title="ContasRadar", rows=20, cols=2)
    aba.clear()
    dados = [["login", "nome"]] + [[c["login"], c["nome"]] for c in contas]
    aba.update(dados)
    st.cache_data.clear()


# ─────────────────────────────────────────────
# INTERFACE — ACESSO RÁPIDO
# ─────────────────────────────────────────────

st.markdown("### 🌐 Acesso Rápido aos Sistemas TIM")
st.caption("Clique para abrir o sistema já logado na conta desejada (requer script local instalado no PC)")

contas_radar = carregar_contas_radar()

tabs_sistemas = st.tabs([info["label"] for info in SISTEMAS_DISPONIVEIS.values()])

for tab, (sistema, info) in zip(tabs_sistemas, SISTEMAS_DISPONIVEIS.items()):
    with tab:
        if contas_radar:
            cols = st.columns(min(len(contas_radar), 4))
            for i, conta in enumerate(contas_radar):
                with cols[i % 4]:
                    login = conta.get("login", "")
                    nome  = conta.get("nome", login)
                    url_protocolo = f"radar-login://{sistema}/{login}"
                    st.link_button(
                        f"{info['emoji']} {nome}\n`{login}`",
                        url=url_protocolo,
                        use_container_width=True,
                    )
        else:
            st.info("Nenhuma conta cadastrada ainda.")

# ─────────────────────────────────────────────
# GERENCIAR CONTAS
# ─────────────────────────────────────────────

with st.expander("⚙️ Gerenciar contas"):
    st.caption("Adicione ou remova logins — valem para todos os sistemas")

    col_a, col_b, col_c = st.columns([2, 3, 1])
    with col_a:
        novo_login = st.text_input("Login (ex: t3729525)", key="novo_login_input").strip().lower()
    with col_b:
        novo_nome = st.text_input("Nome da cidade/regional", key="novo_nome_input").strip()
    with col_c:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("➕ Adicionar", use_container_width=True):
            if novo_login and novo_nome:
                logins_existentes = [c["login"] for c in contas_radar]
                if novo_login in logins_existentes:
                    st.warning(f"Login `{novo_login}` já existe.")
                else:
                    contas_radar.append({"login": novo_login, "nome": novo_nome})
                    salvar_contas_radar(contas_radar)
                    st.success(f"✅ `{novo_login}` adicionado!")
                    st.rerun()
            else:
                st.warning("Preencha o login e o nome.")

    if contas_radar:
        st.markdown("**Remover conta:**")
        opcoes = {f"{c['nome']} ({c['login']})": c["login"] for c in contas_radar}
        remover_sel = st.selectbox("Selecione para remover", ["—"] + list(opcoes.keys()), key="remover_sel")
        if remover_sel != "—":
            if st.button("🗑️ Remover conta selecionada", type="secondary"):
                login_rem = opcoes[remover_sel]
                contas_radar = [c for c in contas_radar if c["login"] != login_rem]
                salvar_contas_radar(contas_radar)
                st.success(f"✅ Conta `{login_rem}` removida!")
                st.rerun()

st.markdown("""
<div style="background:#1a1f2e;border-radius:10px;padding:12px 16px;margin:16px 0 0 0;
    border:1px solid #2d3748;font-size:0.78rem;color:#64748b;">
    💡 <b>Como funciona:</b> Clique em qualquer botão → Chrome abre e faz login automático no sistema escolhido.
    Requer o <code>radar_login_handler.py</code> instalado localmente
    (execute <code>registrar_protocolo.bat</code> como Administrador uma vez).
</div>
""", unsafe_allow_html=True)
