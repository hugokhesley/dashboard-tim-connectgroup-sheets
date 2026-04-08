"""
07_Comissoes.py — Comissão de Parceiros (Versão Estável com WeasyPrint)
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
from data_loader import get_gspread_client, registrar_acesso, _s, _to_num

# ==================== CONFIG ====================
st.set_page_config(
    page_title="Connect Group | Comissões Parceiros",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

username = require_login("comissoes")
registrar_acesso("Comissões Parceiros", username=username)

# ==================== WEASYPRINT (com fallback) ====================
WEASYPRINT_AVAILABLE = False
try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except Exception as e:
    st.warning("⚠️ WeasyPrint não carregou corretamente. PDF será desabilitado.")

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

# ==================== ETAPA 1 - PARCEIRO (simplificada para teste) ====================
step = st.session_state.com_step

if step == 1:
    st.subheader("1. Selecionar Parceiro")
    st.info("Etapa 1 carregada com sucesso.")
    if st.button("Avançar para teste →", type="primary"):
        st.session_state.com_step = 4   # pula direto para etapa do PDF para testar
        st.rerun()

# ==================== ETAPA 4 - TESTE DE PDF (para diagnosticar) ====================
elif step == 4:
    st.subheader("4. Teste de Geração de PDF")

    html_test = """
    <html>
    <head><meta charset="utf-8">
    <style>body { font-family: Arial; margin: 40px; }</style>
    </head>
    <body>
        <h1>Teste de PDF - WeasyPrint</h1>
        <p>Se você está vendo este PDF, o WeasyPrint está funcionando corretamente.</p>
        <p>Data: """ + date.today().strftime("%d/%m/%Y") + """</p>
    </body>
    </html>
    """

    if WEASYPRINT_AVAILABLE:
        try:
            pdf_bytes = HTML(string=html_test).write_pdf()

            st.success("✅ WeasyPrint carregado com sucesso!")
            st.download_button(
                label="⬇️ Baixar PDF de Teste",
                data=pdf_bytes,
                file_name="teste_weasyprint.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        except Exception as e:
            st.error(f"Erro ao gerar PDF: {e}")
    else:
        st.error("WeasyPrint não está disponível.")

    if st.button("Voltar"):
        st.session_state.com_step = 1
        st.rerun()

else:
    st.info(f"Etapa {step} em desenvolvimento.")

st.caption("Sistema de Comissões Connect Group • Versão WeasyPrint")
