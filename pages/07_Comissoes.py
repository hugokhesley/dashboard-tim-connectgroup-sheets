"""
07_Comissoes.py — Sistema de Comissão de Parceiros (Versão Melhorada 2026)
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

# ==================== CONFIGURAÇÃO ====================
st.set_page_config(
    page_title="Connect Group | Comissões Parceiros",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

username = require_login("comissoes")
registrar_acesso("Comissões Parceiros", username=username)

# ==================== PDF ====================
try:
    import pdfkit
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    st.warning("⚠️ Biblioteca pdfkit não encontrada. PDF não estará disponível.")

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

MESES_PT = {
    "01": "Jan", "02": "Fev", "03": "Mar", "04": "Abr", "05": "Mai", "06": "Jun",
    "07": "Jul", "08": "Ago", "09": "Set", "10": "Out", "11": "Nov", "12": "Dez"
}

# ==================== HELPERS ====================
def fmt_brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def fmt_comp(ym: str) -> str:
    if not ym or len(ym) < 7:
        return ym
    y, m = ym[:4], ym[5:7]
    return f"{MESES_PT.get(m, m)}/{y}"

# ==================== CARREGAMENTO ====================
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
        df = df[df.get("ativo", "").str.upper() != "NÃO"].copy()
        return df.reset_index(drop=True)
    except Exception as e:
        st.warning(f"Erro ao carregar Parceiros: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=60)
def load_historico_emissoes() -> pd.DataFrame:
    try:
        client = get_gspread_client()
        ss = client.open_by_url(st.secrets["sheets"]["url"])
        ws = ss.worksheet("Comissoes")
        vals = ws.get_all_values()
        if not vals or len(vals) < 2:
            return pd.DataFrame()
        df = pd.DataFrame(vals[1:], columns=vals[0])
        for col in ["base_vendas", "comissao_bruta", "desconto_imposto", "comissao_liquida"]:
            if col in df.columns:
                df[col] = df[col].apply(_to_num)
        return df
    except Exception:
        return pd.DataFrame()

# ==================== SALVAR NO GOOGLE SHEETS ====================
def salvar_emissao(dados: dict) -> tuple:
    try:
        client = get_gspread_client()
        ss = client.open_by_url(st.secrets["sheets"]["url"])
        try:
            ws = ss.worksheet("Comissoes")
        except Exception:
            ws = ss.add_worksheet(title="Comissoes", rows=2000, cols=15)
            ws.update("A1:O1", [[
                "timestamp", "emitido_por", "parceiro", "cnpj_cpf", "competencia",
                "vencimento", "fator", "aliquota_simples", "base_vendas",
                "comissao_bruta", "desconto_imposto", "comissao_liquida",
                "pix_tipo", "pix_chave", "canal_envio"
            ]])

        agora = (datetime.utcnow() - timedelta(hours=3)).strftime("%d/%m/%Y %H:%M:%S")
        ws.append_row([
            agora, dados["emitido_por"], dados["parceiro"], dados["cnpj_cpf"],
            dados["competencia"], dados["vencimento"], dados["fator"],
            dados["aliquota_simples"], dados["base_vendas"], dados["comissao_bruta"],
            dados["desconto_imposto"], dados["comissao_liquida"],
            dados["pix_tipo"], dados["pix_chave"], dados["canal_envio"]
        ], value_input_option="USER_ENTERED")
        return True, agora
    except Exception as e:
        return False, str(e)

# ==================== GERAÇÃO DE PDF ====================
def gerar_pdf_contrato(html_content: str) -> bytes | None:
    if not PDF_AVAILABLE:
        st.error("pdfkit não está instalado. Instale com: `pip install pdfkit`")
        return None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            pdf_path = tmp.name

        options = {
            'page-size': 'A4',
            'margin-top': '20mm',
            'margin-right': '15mm',
            'margin-bottom': '20mm',
            'margin-left': '15mm',
            'encoding': "UTF-8",
            'no-outline': None,
        }

        pdfkit.from_string(html_content, pdf_path, options=options)

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        os.unlink(pdf_path)
        return pdf_bytes
    except Exception as e:
        st.error(f"Erro ao gerar PDF: {e}")
        return None

# ==================== ENVIO DE E-MAIL ====================
def enviar_email_com_anexo(destinatario: str, assunto: str, html_body: str, pdf_bytes: bytes, pdf_filename: str) -> tuple:
    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.base import MIMEBase
        from email import encoders

        cfg = st.secrets["email"]

        msg = MIMEMultipart()
        msg["Subject"] = assunto
        msg["From"] = cfg.get("from", cfg["user"])
        msg["To"] = destinatario
        msg["Reply-To"] = cfg.get("from", cfg["user"])

        msg.attach(MIMEText(html_body, "html", "utf-8"))

        # Anexo PDF
        part = MIMEBase("application", "octet-stream")
        part.set_payload(pdf_bytes)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={pdf_filename}")
        msg.attach(part)

        # SMTP mais confiável (porta 587 + STARTTLS)
        with smtplib.SMTP(cfg.get("host", "smtp.titan.email"), 587) as server:
            server.starttls()
            server.login(cfg["user"], cfg["password"])
            server.sendmail(cfg["user"], destinatario, msg.as_string())

        return True, "E-mail enviado com sucesso!"
    except Exception as e:
        return False, f"Erro no envio: {str(e)}"

# ==================== SESSION STATE ====================
def init_session():
    if "com_step" not in st.session_state:
        st.session_state.com_step = 1
        st.session_state.com_parceiro = None
        st.session_state.com_vendas = []
        st.session_state.com_fator = 0.0
        st.session_state.com_fator_label = ""
        st.session_state.com_imposto = 6.0
        st.session_state.com_comp = date.today().strftime("%Y-%m")
        st.session_state.com_vencimento = (date.today() + timedelta(days=10)).isoformat()
        st.session_state.com_pix_tipo = "CNPJ"
        st.session_state.com_pix_chave = ""
        st.session_state.com_canal = "E-mail"

init_session()

# ==================== SIDEBAR ====================
with st.sidebar:
    st.markdown("### 💰 Comissão de Parceiros")
    st.progress(min(st.session_state.com_step / 5, 1.0))

    if st.button("🔄 Nova Emissão", use_container_width=True):
        for key in list(st.session_state.keys()):
            if key.startswith("com_"):
                del st.session_state[key]
        init_session()
        st.rerun()

    if st.button("📋 Histórico de Emissões", use_container_width=True):
        st.session_state.com_mostrar_historico = not st.session_state.get("com_mostrar_historico", False)
        st.rerun()

# ==================== HISTÓRICO ====================
if st.session_state.get("com_mostrar_historico", False):
    st.title("📋 Histórico de Emissões")
    df_hist = load_historico_emissoes()
    if df_hist.empty:
        st.info("Nenhuma emissão registrada ainda.")
    else:
        st.dataframe(df_hist, use_container_width=True, hide_index=True)
        csv = df_hist.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Baixar CSV", csv, "historico_comissoes.csv", "text/csv")
    st.stop()

# ==================== TÍTULO ====================
st.title("💰 Emissão de Comissão de Parceiros")
st.caption("Conforme Ordem de Serviço TIM SMB OS_2025_29")

step = st.session_state.com_step

# ==================== ETAPA 1 — PARCEIRO ====================
if step == 1:
    st.subheader("1. Selecionar ou Cadastrar Parceiro")
    df_parc = load_parceiros_sheet()

    tab_sel, tab_novo = st.tabs(["Parceiros Cadastrados", "Novo Parceiro"])

    with tab_sel:
        if df_parc.empty:
            st.info("Nenhum parceiro cadastrado.")
        else:
            opcoes = ["— Selecione um parceiro —"] + df_parc["nome"].tolist()
            sel = st.selectbox("Parceiro", opcoes)
            if sel != "— Selecione um parceiro —":
                p = df_parc[df_parc["nome"] == sel].iloc[0].to_dict()
                col1, col2, col3 = st.columns(3)
                col1.metric("CNPJ/CPF", p.get("cnpj_cpf", "—"))
                col2.metric("E-mail", p.get("email", "—"))
                col3.metric("PIX", f"{p.get('pix_tipo','—')}: {p.get('pix_chave','—')}")
                if st.button("✅ Usar este parceiro", type="primary", use_container_width=True):
                    st.session_state.com_parceiro = p
                    st.session_state.com_pix_chave = p.get("pix_chave", "")
                    st.session_state.com_pix_tipo = p.get("pix_tipo", "CNPJ")
                    st.session_state.com_step = 2
                    st.rerun()

    with tab_novo:
        with st.form("form_novo_parceiro"):
            c1, c2 = st.columns(2)
            nome = c1.text_input("Nome / Razão Social *")
            doc = c2.text_input("CNPJ / CPF *")
            email = st.text_input("E-mail")
            c3, c4 = st.columns(2)
            pix_chave = c3.text_input("Chave PIX *")
            pix_tipo = c4.selectbox("Tipo PIX", ["CNPJ", "CPF", "E-mail", "Celular", "Aleatória"])
            submitted = st.form_submit_button("Cadastrar e Continuar", type="primary")
            if submitted:
                if nome and doc and pix_chave:
                    # Aqui você pode chamar sua função salvar_parceiro se quiser
                    st.session_state.com_parceiro = {
                        "nome": nome, "cnpj_cpf": doc, "email": email,
                        "pix_chave": pix_chave, "pix_tipo": pix_tipo
                    }
                    st.session_state.com_pix_chave = pix_chave
                    st.session_state.com_pix_tipo = pix_tipo
                    st.session_state.com_step = 2
                    st.rerun()
                else:
                    st.error("Nome, CNPJ/CPF e Chave PIX são obrigatórios.")

# ==================== ETAPA 2 — VENDAS ====================
elif step == 2:
    p = st.session_state.com_parceiro
    st.subheader(f"2. Vendas — {p.get('nome', 'Parceiro')}")

    with st.form("add_venda", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns([3, 1.5, 1.5, 1.5])
        desc = c1.text_input("Produto / Descrição *")
        comp = c2.text_input("Competência (MM/AAAA)", value=fmt_comp(st.session_state.com_comp))
        valor = c3.number_input("Valor da Venda (R$)", min_value=0.0, step=0.01, format="%.2f")
        tipo_prod = c4.selectbox("Tipo de Produto", TIPOS_PRODUTO)
        if st.form_submit_button("➕ Adicionar Venda"):
            if desc and valor > 0:
                st.session_state.com_vendas.append({
                    "desc": desc, "comp": comp, "valor": valor, "tipo": tipo_prod
                })
                st.rerun()

    if st.session_state.com_vendas:
        df_v = pd.DataFrame(st.session_state.com_vendas)
        st.dataframe(df_v, use_container_width=True, hide_index=True)

        total = df_v["valor"].sum()
        st.metric("Total Base de Vendas", fmt_brl(total))

    col_back, col_next = st.columns([1, 3])
    if col_back.button("← Voltar"):
        st.session_state.com_step = 1
        st.rerun()
    if col_next.button("Próximo →", type="primary", disabled=len(st.session_state.com_vendas) == 0):
        st.session_state.com_step = 3
        st.rerun()

# ==================== ETAPA 3 — CÁLCULO ====================
elif step == 3:
    st.subheader("3. Fator e Cálculo da Comissão")
    base = sum(v["valor"] for v in st.session_state.com_vendas)

    col1, col2 = st.columns([1.2, 1])

    with col1:
        fator_label = st.selectbox("Fator Multiplicador", list(FATORES_PADRAO.keys()))
        fator_val = FATORES_PADRAO[fator_label]
        if fator_val is None:
            fator_val = st.number_input("Valor personalizado", min_value=0.01, max_value=20.0, value=3.0, step=0.01)

        st.session_state.com_fator = fator_val
        st.session_state.com_fator_label = fator_label

        aliquota = st.radio("Alíquota Simples Nacional", 
                           [f"{a:.2f}%" for a in ALIQUOTAS_SIMPLES] + ["Personalizada"],
                           horizontal=True)
        if aliquota == "Personalizada":
            imposto = st.number_input("Alíquota (%)", min_value=0.0, max_value=33.0, value=6.0, step=0.01)
        else:
            imposto = float(aliquota.replace("%", ""))
        st.session_state.com_imposto = imposto

    with col2:
        bruto = base * fator_val
        desconto = bruto * (imposto / 100)
        liquido = bruto - desconto

        st.success(f"**Comissão Líquida:** {fmt_brl(liquido)}")
        st.metric("Base", fmt_brl(base))
        st.metric("Comissão Bruta", fmt_brl(bruto))
        st.metric("Desconto Imposto", fmt_brl(desconto))

    col_back, col_next = st.columns([1, 3])
    if col_back.button("← Voltar"):
        st.session_state.com_step = 2
        st.rerun()
    if col_next.button("Gerar Contrato →", type="primary"):
        st.session_state.com_step = 4
        st.rerun()

# ==================== ETAPA 4 — CONTRATO & PDF ====================
elif step == 4:
    p = st.session_state.com_parceiro
    base = sum(v["valor"] for v in st.session_state.com_vendas)
    bruto = base * st.session_state.com_fator
    desconto = bruto * (st.session_state.com_imposto / 100)
    liquido = bruto - desconto

    st.subheader("4. Termo de Comissionamento")

    vencimento = st.date_input("Data de Vencimento", 
                               value=date.fromisoformat(st.session_state.com_vencimento))

    st.session_state.com_vencimento = vencimento.isoformat()

    # Gera HTML do contrato
    linhas = "\n".join([f"<tr><td>{v['desc']}</td><td>{v['comp']}</td><td>{v['tipo']}</td><td align='right'>{fmt_brl(v['valor'])}</td></tr>" 
                        for v in st.session_state.com_vendas])

    contrato_html = f"""
    <html><head><meta charset="utf-8"><style>
        body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
        h1 {{ color: #1e3a8a; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ccc; padding: 8px; }}
        th {{ background: #f0f0f0; }}
    </style></head><body>
    <h1>TERMO DE COMISSIONAMENTO</h1>
    <p><strong>Parceiro:</strong> {p.get('nome')} — {p.get('cnpj_cpf')}</p>
    <p><strong>Competência:</strong> {fmt_comp(st.session_state.com_comp)}</p>
    
    <h2>Vendas do Período</h2>
    <table>
        <tr><th>Descrição</th><th>Competência</th><th>Tipo</th><th>Valor</th></tr>
        {linhas}
        <tr><td colspan="3"><strong>TOTAL BASE</strong></td><td align="right"><strong>{fmt_brl(base)}</strong></td></tr>
    </table>

    <h2>Cálculo da Comissão</h2>
    <p><strong>Fator:</strong> {st.session_state.com_fator_label} × {st.session_state.com_fator:.2f}</p>
    <p><strong>Comissão Bruta:</strong> {fmt_brl(bruto)}</p>
    <p><strong>Desconto Simples Nacional ({st.session_state.com_imposto:.2f}%):</strong> − {fmt_brl(desconto)}</p>
    <h2><strong>Valor Líquido a Receber: {fmt_brl(liquido)}</strong></h2>

    <p><strong>PIX:</strong> {st.session_state.com_pix_tipo} — {st.session_state.com_pix_chave}</p>
    <p><strong>Vencimento:</strong> {vencimento.strftime('%d/%m/%Y')}</p>
    </body></html>
    """

    pdf_bytes = gerar_pdf_contrato(contrato_html)

    if pdf_bytes:
        st.download_button(
            label="⬇️ Baixar Contrato em PDF",
            data=pdf_bytes,
            file_name=f"Comissao_{p.get('nome','').replace(' ','_')}_{fmt_comp(st.session_state.com_comp)}.pdf",
            mime="application/pdf",
            use_container_width=True
        )

    col_back, col_next = st.columns([1, 3])
    if col_back.button("← Voltar"):
        st.session_state.com_step = 3
        st.rerun()
    if col_next.button("Preparar Envio →", type="primary", disabled=pdf_bytes is None):
        st.session_state.com_step = 5
        st.rerun()

# ==================== ETAPA 5 — ENVIO ====================
elif step == 5:
    p = st.session_state.com_parceiro
    liquido = sum(v["valor"] for v in st.session_state.com_vendas) * st.session_state.com_fator * (1 - st.session_state.com_imposto/100)
    pdf_bytes = None  # Será gerado novamente

    st.subheader("5. Envio da Comissão")

    email_dest = p.get("email", "").strip()
    canal = st.selectbox("Canal de Envio", ["E-mail", "E-mail + WhatsApp", "WhatsApp", "Presencial"])

    if st.button("✅ Gerar PDF e Enviar", type="primary", use_container_width=True):
        # Gerar PDF novamente
        # (reutiliza o mesmo HTML da etapa 4 - simplificado aqui)
        pdf_bytes = gerar_pdf_contrato(contrato_html)  # Note: contrato_html vem da etapa anterior, idealmente salvar em session_state

        if pdf_bytes and email_dest and "E-mail" in canal:
            assunto = f"Termo de Comissionamento - {fmt_comp(st.session_state.com_comp)}"
            html_body = f"""
            <p>Olá {p.get('nome','')},</p>
            <p>Segue o Termo de Comissionamento referente à competência {fmt_comp(st.session_state.com_comp)}.</p>
            <p><strong>Valor Líquido:</strong> {fmt_brl(liquido)}</p>
            <p>Atenciosamente,<br>Connect Group Telecom</p>
            """

            sucesso, msg = enviar_email_com_anexo(
                destinatario=email_dest,
                assunto=assunto,
                html_body=html_body,
                pdf_bytes=pdf_bytes,
                pdf_filename=f"Comissao_{p.get('nome','')}.pdf"
            )

            if sucesso:
                st.success("✅ PDF gerado e e-mail enviado com sucesso!")
            else:
                st.error(msg)
        else:
            st.warning("E-mail não enviado (sem destinatário ou PDF).")

    # Botão de registro final
    if st.button("Registrar Emissão na Planilha", type="primary"):
        dados = {
            "emitido_por": username,
            "parceiro": p.get("nome", ""),
            "cnpj_cpf": p.get("cnpj_cpf", ""),
            "competencia": fmt_comp(st.session_state.com_comp),
            "vencimento": date.fromisoformat(st.session_state.com_vencimento).strftime("%d/%m/%Y"),
            "fator": st.session_state.com_fator,
            "aliquota_simples": st.session_state.com_imposto,
            "base_vendas": sum(v["valor"] for v in st.session_state.com_vendas),
            "comissao_bruta": sum(v["valor"] for v in st.session_state.com_vendas) * st.session_state.com_fator,
            "desconto_imposto": sum(v["valor"] for v in st.session_state.com_vendas) * st.session_state.com_fator * (st.session_state.com_imposto / 100),
            "comissao_liquida": liquido,
            "pix_tipo": st.session_state.com_pix_tipo,
            "pix_chave": st.session_state.com_pix_chave,
            "canal_envio": canal,
        }
        ok, msg = salvar_emissao(dados)
        if ok:
            st.success("Emissão registrada com sucesso na aba Comissoes!")
            st.balloons()
        else:
            st.error(f"Erro ao registrar: {msg}")

# Rodapé
st.markdown("---")
st.caption("Sistema de Comissões Connect Group • Versão Melhorada")
