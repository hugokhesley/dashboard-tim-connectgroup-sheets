"""
07_Comissoes.py — Comissão de Parceiros (Versão Estável)
Connect Group | TIM Empresas
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import sys
import os
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from auth import require_login
from data_loader import get_gspread_client, registrar_acesso

# ==================== CONFIG ====================
st.set_page_config(
    page_title="Connect Group | Comissões Parceiros",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

username = require_login("comissoes")
registrar_acesso("Comissões Parceiros", username=username)

# ==================== WEASYPRINT ====================
try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except Exception:
    WEASYPRINT_AVAILABLE = False

# ==================== CONSTANTES ====================
FATORES_PADRAO = {
    "Black — Fidelizado Novo (5,80)": 5.80,
    "Platinum — Fidelizado (5,00)": 5.00,
    "Black — Dados/Plug In (4,80)": 4.80,
    "Silver — Fidelizado Novo (4,50)": 4.50,
    "Platinum — Dados/Plug In (4,00)": 4.00,
    "Silver — Aditivo (3,50)": 3.50,
    "Blue — Qualquer (3,00)": 3.00,
    "Portabilidade (1,25)": 1.25,
    "Não fidelizado (0,30)": 0.30,
    "⚙️ Personalizado": None,
}

TIPOS_PRODUTO = ["Plano Voz (Móvel)", "Plano Dados (Móvel)", "Plug In", "M2M", "TIM Office Fixo",
                 "Ultra Fibra (CNPJ)", "VAS", "Migração Pré→Pós Corporate", "Outro"]

ALIQUOTAS_SIMPLES = [6.00, 6.84, 7.54, 8.04, 10.26, 11.31, 13.50]

MESES_PT = {"01":"Jan","02":"Fev","03":"Mar","04":"Abr","05":"Mai","06":"Jun","07":"Jul","08":"Ago",
            "09":"Set","10":"Out","11":"Nov","12":"Dez"}

def fmt_brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def fmt_comp(ym: str) -> str:
    if not ym or len(ym) < 7: return ym
    y, m = ym[:4], ym[5:7]
    return f"{MESES_PT.get(m, m)}/{y}"

# ==================== FUNÇÃO DE CARREGAMENTO DE PARCEIROS ====================
@st.cache_data(ttl=60)
def load_parceiros_sheet() -> pd.DataFrame:
    """Carrega a aba 'Parceiros' do Google Sheets"""
    try:
        client = get_gspread_client()
        ss = client.open_by_url(st.secrets["sheets"]["url"])
        ws = ss.worksheet("Parceiros")
        vals = ws.get_all_values()
        if not vals or len(vals) < 2:
            return pd.DataFrame(columns=["nome", "cnpj_cpf", "email", "pix_chave", "pix_tipo", "ativo"])
        
        df = pd.DataFrame(vals[1:], columns=vals[0])
        # Filtra apenas parceiros ativos
        if "ativo" in df.columns:
            df = df[df["ativo"].str.upper() != "NÃO"].copy()
        return df.reset_index(drop=True)
    except Exception as e:
        st.warning(f"Erro ao carregar aba Parceiros: {e}")
        return pd.DataFrame(columns=["nome", "cnpj_cpf", "email", "pix_chave", "pix_tipo"])

# ==================== SESSION STATE ====================
if "com_step" not in st.session_state:
    st.session_state.update({
        "com_step": 1,
        "com_parceiro": None,
        "com_vendas": [],
        "com_fator": 0.0,
        "com_fator_label": "",
        "com_imposto": 6.0,
        "com_comp": date.today().strftime("%Y-%m"),
        "com_vencimento": (date.today() + timedelta(days=10)).isoformat(),
        "com_pix_tipo": "CNPJ",
        "com_pix_chave": "",
        "com_canal": "E-mail",
    })

# ==================== SIDEBAR ====================
with st.sidebar:
    st.markdown("### 💰 Comissão de Parceiros")
    st.progress(min(st.session_state.com_step / 5, 1.0))

    if st.button("🔄 Nova Emissão", use_container_width=True):
        for key in list(st.session_state.keys()):
            if key.startswith("com_"):
                del st.session_state[key]
        st.session_state.com_step = 1
        st.rerun()

# ==================== TÍTULO ====================
st.title("💰 Emissão de Comissão de Parceiros")
st.caption("Conforme Ordem de Serviço TIM SMB OS_2025_29")

step = st.session_state.com_step

# ==================== ETAPA 1: PARCEIRO ====================
if step == 1:
    st.subheader("1. Selecionar ou Cadastrar Parceiro")
    
    df_parc = load_parceiros_sheet()

    tab1, tab2 = st.tabs(["Parceiros Existentes", "Novo Parceiro"])

    with tab1:
        if df_parc.empty:
            st.info("Nenhum parceiro cadastrado ainda.")
        else:
            nomes = ["— Selecione um parceiro —"] + df_parc["nome"].dropna().unique().tolist()
            sel = st.selectbox("Escolha o parceiro", nomes)
            
            if sel != "— Selecione um parceiro —":
                p = df_parc[df_parc["nome"] == sel].iloc[0].to_dict()
                
                col1, col2, col3 = st.columns(3)
                col1.metric("CNPJ/CPF", p.get("cnpj_cpf", "—"))
                col2.metric("E-mail", p.get("email", "—"))
                col3.metric("PIX", f"{p.get('pix_tipo','—')}: {p.get('pix_chave','—')}")
                
                if st.button("✅ Continuar com este parceiro", type="primary", use_container_width=True):
                    st.session_state.com_parceiro = p
                    st.session_state.com_pix_chave = p.get("pix_chave", "")
                    st.session_state.com_pix_tipo = p.get("pix_tipo", "CNPJ")
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
                    st.session_state.com_pix_chave = pix_chave
                    st.session_state.com_pix_tipo = pix_tipo
                    st.session_state.com_step = 2
                    st.rerun()
                else:
                    st.error("Nome, CNPJ/CPF e Chave PIX são obrigatórios.")

# ==================== ETAPA 4: TESTE PDF ====================
elif step == 4:
    st.subheader("4. Teste de Geração de PDF")
    
    if not st.session_state.com_parceiro:
        st.warning("Por favor, volte e selecione um parceiro primeiro.")
    else:
        p = st.session_state.com_parceiro
        html_test = f"""
        <html><head><meta charset="utf-8">
        <style>body {{ font-family: Arial; margin: 40px; }}</style>
        </head>
        <body>
            <h1>Teste de PDF - WeasyPrint</h1>
            <p><strong>Parceiro:</strong> {p.get('nome', '—')}</p>
            <p><strong>CNPJ/CPF:</strong> {p.get('cnpj_cpf', '—')}</p>
            <p>Data: {date.today().strftime('%d/%m/%Y')}</p>
        </body></html>
        """

        if WEASYPRINT_AVAILABLE:
            try:
                pdf_bytes = HTML(string=html_test).write_pdf()
                st.success("✅ WeasyPrint funcionando corretamente!")
                st.download_button(
                    "⬇️ Baixar PDF de Teste",
                    data=pdf_bytes,
                    file_name="teste_comissao.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
            except Exception as e:
                st.error(f"Erro ao gerar PDF: {e}")
        else:
            st.error("WeasyPrint não disponível.")

# Rodapé
st.caption("Sistema de Comissões Connect Group • Versão Corrigida")
