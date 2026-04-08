"""
07_Comissoes.py — Comissão de Parceiros (Etapas 1 a 4 funcionando)
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

TIPOS_PRODUTO = [
    "Plano Voz (Móvel)", "Plano Dados (Móvel)", "Plug In", "M2M",
    "TIM Office Fixo", "Ultra Fibra (CNPJ)", "VAS",
    "Migração Pré→Pós Corporate", "Outro"
]

ALIQUOTAS_SIMPLES = [6.00, 6.84, 7.54, 8.04, 10.26, 11.31, 13.50]

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
    except Exception:
        return pd.DataFrame()

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
    })

# ==================== TÍTULO ====================
st.title("💰 Emissão de Comissão de Parceiros")
st.caption("Conforme Ordem de Serviço TIM SMB OS_2025_29")

step = st.session_state.com_step

# ETAPA 1
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
                    st.session_state.com_parceiro = {"nome": nome, "cnpj_cpf": cnpj, "email": email, "pix_chave": pix_chave, "pix_tipo": pix_tipo}
                    st.session_state.com_step = 2
                    st.rerun()

# ETAPA 2
elif step == 2:
    p = st.session_state.com_parceiro
    st.subheader(f"2. Vendas — {p.get('nome', 'Parceiro')}")

    with st.form("add_venda", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns([3, 1.5, 1.5, 1.5])
        desc = c1.text_input("Produto / Descrição *")
        comp = c2.text_input("Competência", value=fmt_comp(st.session_state.com_comp))
        valor = c3.number_input("Valor da Venda (R$)", min_value=0.0, step=0.01)
        tipo = c4.selectbox("Tipo de Produto", TIPOS_PRODUTO)
        
        if st.form_submit_button("➕ Adicionar Venda", type="primary"):
            if desc and valor > 0:
                st.session_state.com_vendas.append({"desc": desc, "comp": comp, "valor": valor, "tipo": tipo})
                st.rerun()

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

# ETAPA 3
elif step == 3:
    st.subheader("3. Cálculo da Comissão")
    base = sum(v["valor"] for v in st.session_state.com_vendas)

    fator_label = st.selectbox("Fator Multiplicador", list(FATORES_PADRAO.keys()))
    fator = FATORES_PADRAO[fator_label] or st.number_input("Fator personalizado", value=3.0, step=0.1)

    aliquota = st.radio("Alíquota Simples Nacional", [f"{x:.2f}%" for x in ALIQUOTAS_SIMPLES] + ["Personalizada"], horizontal=True)
    imposto = float(aliquota.replace("%","")) if aliquota != "Personalizada" else st.number_input("Alíquota (%)", value=6.0)

    bruto = base * fator
    desconto = bruto * (imposto / 100)
    liquido = bruto - desconto

    st.session_state.com_fator = fator
    st.session_state.com_fator_label = fator_label
    st.session_state.com_imposto = imposto

    st.success(f"**Valor Líquido a Pagar: {fmt_brl(liquido)}**")

    col1, col2 = st.columns([1, 3])
    if col1.button("← Voltar"):
        st.session_state.com_step = 2
        st.rerun()
    if col2.button("Gerar Contrato →", type="primary"):
        st.session_state.com_step = 4
        st.rerun()

# ETAPA 4 - CONTRATO + PDF
elif step == 4:
    st.subheader("4. Termo de Comissionamento")
    p = st.session_state.com_parceiro
    base = sum(v["valor"] for v in st.session_state.com_vendas)
    bruto = base * st.session_state.com_fator
    desconto = bruto * (st.session_state.com_imposto / 100)
    liquido = bruto - desconto
    venc = date.fromisoformat(st.session_state.com_vencimento)

    contrato_html = f"""
    <html><head><meta charset="utf-8">
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
        h1 {{ color: #1e3a8a; text-align: center; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ border: 1px solid #ccc; padding: 10px; }}
        th {{ background: #f0f0f0; }}
        .total {{ font-weight: bold; background: #e6f0ff; }}
    </style></head>
    <body>
        <h1>TERMO DE COMISSIONAMENTO</h1>
        <p><strong>Parceiro:</strong> {p.get('nome')} — {p.get('cnpj_cpf')}</p>
        <p><strong>Competência:</strong> {fmt_comp(st.session_state.com_comp)}</p>
        
        <h2>Vendas do Período</h2>
        <table>
            <tr><th>Descrição</th><th>Competência</th><th>Tipo</th><th>Valor</th></tr>
            {"".join(f"<tr><td>{v['desc']}</td><td>{v['comp']}</td><td>{v['tipo']}</td><td align='right'>{fmt_brl(v['valor'])}</td></tr>" for v in st.session_state.com_vendas)}
            <tr class="total"><td colspan="3">TOTAL BASE</td><td align="right">{fmt_brl(base)}</td></tr>
        </table>

        <h2>Cálculo da Comissão</h2>
        <p>Fator: {st.session_state.com_fator_label} × {st.session_state.com_fator:.2f}</p>
        <p>Comissão Bruta: {fmt_brl(bruto)}</p>
        <p>Desconto Simples Nacional ({st.session_state.com_imposto:.2f}%): − {fmt_brl(desconto)}</p>
        <h2 style="color:#15803d">Valor Líquido a Receber: {fmt_brl(liquido)}</h2>

        <p><strong>PIX:</strong> {st.session_state.com_pix_tipo} — {st.session_state.com_pix_chave}</p>
        <p><strong>Vencimento:</strong> {venc.strftime('%d/%m/%Y')}</p>
    </body></html>
    """

    if WEASYPRINT_AVAILABLE:
        try:
            pdf_bytes = HTML(string=contrato_html).write_pdf()
            st.success("✅ Contrato gerado com sucesso!")
            st.download_button(
                "⬇️ Baixar Contrato em PDF",
                data=pdf_bytes,
                file_name=f"Comissao_{p.get('nome','').replace(' ','_')}_{fmt_comp(st.session_state.com_comp)}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        except Exception as e:
            st.error(f"Erro ao gerar PDF: {e}")
    else:
        st.warning("WeasyPrint não disponível. PDF desabilitado.")

    col1, col2 = st.columns([1, 3])
    if col1.button("← Voltar"):
        st.session_state.com_step = 3
        st.rerun()
    if col2.button("Preparar Envio →", type="primary"):
        st.session_state.com_step = 5
        st.rerun()

else:
    st.info("Etapa em desenvolvimento...")

st.caption("Sistema de Comissões Connect Group")
