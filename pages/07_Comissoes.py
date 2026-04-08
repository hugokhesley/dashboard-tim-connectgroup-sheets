"""
07_Comissoes.py — Comissão de Parceiros (Versão Simples e Funcional)
"""

import streamlit as st
import pandas as pd
from datetime import date, timedelta
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from auth import require_login
from data_loader import get_gspread_client, registrar_acesso

st.set_page_config(page_title="Comissões Parceiros", page_icon="💰", layout="wide")
username = require_login("comissoes")
registrar_acesso("Comissões Parceiros", username=username)

# ==================== CONSTANTES ====================
TIPOS_PRODUTO = [
    "Plano Voz (Móvel)", "Plano Dados (Móvel)", "Plug In", "M2M",
    "TIM Office Fixo", "Ultra Fibra (CNPJ)", "VAS",
    "Migração Pré→Pós Corporate", "Outro"
]

MESES_PT = {"01":"Jan","02":"Fev","03":"Mar","04":"Abr","05":"Mai","06":"Jun","07":"Jul","08":"Ago",
            "09":"Set","10":"Out","11":"Nov","12":"Dez"}

def fmt_brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def fmt_comp(ym: str) -> str:
    if not ym or len(ym) < 7: return ym
    y, m = ym[:4], ym[5:7]
    return f"{MESES_PT.get(m, m)}/{y}"

# ==================== CARREGAR PARCEIROS ====================
@st.cache_data(ttl=60)
def load_parceiros_sheet() -> pd.DataFrame:
    try:
        client = get_gspread_client()
        ss = client.open_by_url(st.secrets["sheets"]["url"])
        ws = ss.worksheet("Parceiros")
        vals = ws.get_all_values()
        if not vals or len(vals) < 2:
            return pd.DataFrame()
        df = pd.DataFrame(vals[1:], columns=vals[0])
        if "ativo" in df.columns:
            df = df[df["ativo"].str.upper() != "NÃO"].copy()
        return df.reset_index(drop=True)
    except Exception as e:
        st.warning(f"Erro ao carregar Parceiros: {e}")
        return pd.DataFrame()

# ==================== SESSION STATE ====================
if "com_step" not in st.session_state:
    st.session_state.update({
        "com_step": 1,
        "com_parceiro": None,
        "com_vendas": [],
        "com_comp": date.today().strftime("%Y-%m"),
    })

# ==================== TÍTULO ====================
st.title("💰 Emissão de Comissão de Parceiros")
st.caption("Conforme Ordem de Serviço TIM SMB OS_2025_29")

step = st.session_state.com_step

# ==================== ETAPA 1 ====================
if step == 1:
    st.subheader("1. Selecionar ou Cadastrar Parceiro")
    
    df_parc = load_parceiros_sheet()

    tab1, tab2 = st.tabs(["Parceiros Existentes", "Novo Parceiro"])

    with tab1:
        if df_parc.empty:
            st.info("Nenhum parceiro cadastrado.")
        else:
            nomes = ["— Selecione um parceiro —"] + df_parc["nome"].dropna().tolist()
            sel = st.selectbox("Escolha o parceiro", nomes)
            
            if sel != "— Selecione um parceiro —":
                p = df_parc[df_parc["nome"] == sel].iloc[0].to_dict()
                col1, col2, col3 = st.columns(3)
                col1.metric("CNPJ/CPF", p.get("cnpj_cpf", "—"))
                col2.metric("E-mail", p.get("email", "—"))
                col3.metric("PIX", f"{p.get('pix_tipo','—')}: {p.get('pix_chave','—')}")
                
                if st.button("✅ Continuar com este parceiro", type="primary", use_container_width=True):
                    st.session_state.com_parceiro = p
                    st.session_state.com_step = 2
                    st.rerun()

    with tab2:
        with st.form("novo_parceiro"):
            nome = st.text_input("Nome / Razão Social *")
            cnpj = st.text_input("CNPJ / CPF *")
            email = st.text_input("E-mail")
            pix_chave = st.text_input("Chave PIX *")
            pix_tipo = st.selectbox("Tipo PIX", ["CNPJ", "CPF", "E-mail", "Celular", "Aleatória"])
            
            if st.form_submit_button("Cadastrar e Continuar", type="primary"):
                if nome and cnpj and pix_chave:
                    st.session_state.com_parceiro = {
                        "nome": nome, "cnpj_cpf": cnpj, "email": email,
                        "pix_chave": pix_chave, "pix_tipo": pix_tipo
                    }
                    st.session_state.com_step = 2
                    st.rerun()
                else:
                    st.error("Nome, CNPJ/CPF e Chave PIX são obrigatórios.")

# ==================== ETAPA 2 ====================
elif step == 2:
    if not st.session_state.com_parceiro:
        st.error("Parceiro não selecionado.")
        if st.button("Voltar"):
            st.session_state.com_step = 1
            st.rerun()
    else:
        p = st.session_state.com_parceiro
        st.subheader(f"2. Vendas — {p.get('nome', 'Parceiro')}")

        with st.form("add_venda", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns([3, 1.5, 1.5, 1.5])
            desc = c1.text_input("Produto / Descrição *")
            comp = c2.text_input("Competência (MM/AAAA)", value=fmt_comp(st.session_state.com_comp))
            valor = c3.number_input("Valor da Venda (R$)", min_value=0.0, step=0.01, format="%.2f")
            tipo = c4.selectbox("Tipo de Produto", TIPOS_PRODUTO)
            
            submit = st.form_submit_button("➕ Adicionar Venda", type="primary")

            if submit:
                if desc and valor > 0:
                    st.session_state.com_vendas.append({
                        "desc": desc,
                        "comp": comp,
                        "valor": valor,
                        "tipo": tipo
                    })
                    st.rerun()
                else:
                    st.error("Descrição e valor são obrigatórios.")

        # Mostrar vendas já adicionadas
        if st.session_state.com_vendas:
            df_v = pd.DataFrame(st.session_state.com_vendas)
            st.dataframe(df_v, use_container_width=True, hide_index=True)
            st.metric("Total Base", fmt_brl(df_v["valor"].sum()))

        col1, col2 = st.columns([1, 3])
        if col1.button("← Voltar"):
            st.session_state.com_step = 1
            st.rerun()
        if col2.button("Próximo →", type="primary", disabled=len(st.session_state.com_vendas) == 0):
            st.session_state.com_step = 3
            st.rerun()

else:
    st.info(f"Etapa {step} ainda em desenvolvimento.")

st.caption("Sistema de Comissões Connect Group")
