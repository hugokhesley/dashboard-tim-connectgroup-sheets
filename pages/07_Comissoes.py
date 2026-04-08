"""
07_Comissoes.py — Sistema de Comissão de Parceiros (Versão WeasyPrint)
Connect Group | TIM Empresas
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import sys
import os
import tempfile
import base64

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

# ==================== IMPORT WEASYPRINT ====================
try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False
    st.error("WeasyPrint não está instalado. Adicione 'weasyprint' no requirements.txt")

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

MESES_PT = {"01":"Jan","02":"Fev","03":"Mar","04":"Abr","05":"Mai","06":"Jun",
            "07":"Jul","08":"Ago","09":"Set","10":"Out","11":"Nov","12":"Dez"}

# ==================== HELPERS ====================
def fmt_brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def fmt_comp(ym: str) -> str:
    if not ym or len(ym) < 7: return ym
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
            ws.update("A1:O1", [["timestamp","emitido_por","parceiro","cnpj_cpf","competencia",
                                "vencimento","fator","aliquota_simples","base_vendas",
                                "comissao_bruta","desconto_imposto","comissao_liquida",
                                "pix_tipo","pix_chave","canal_envio"]])

        agora = (datetime.utcnow() - timedelta(hours=3)).strftime("%d/%m/%Y %H:%M:%S")
        ws.append_row([agora, dados["emitido_por"], dados["parceiro"], dados["cnpj_cpf"],
                       dados["competencia"], dados["vencimento"], dados["fator"],
                       dados["aliquota_simples"], dados["base_vendas"], dados["comissao_bruta"],
                       dados["desconto_imposto"], dados["comissao_liquida"],
                       dados["pix_tipo"], dados["pix_chave"], dados["canal_envio"]],
                      value_input_option="USER_ENTERED")
        return True, agora
    except Exception as e:
        return False, str(e)

# ==================== GERAÇÃO DE PDF COM WEASYPRINT ====================
def gerar_pdf_contrato(html_content: str) -> bytes | None:
    if not WEASYPRINT_AVAILABLE:
        st.error("WeasyPrint não está disponível.")
        return None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            pdf_path = tmp.name

        HTML(string=html_content).write_pdf(pdf_path)

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        os.unlink(pdf_path)
        return pdf_bytes
    except Exception as e:
        st.error(f"Erro ao gerar PDF: {e}")
        return None

# ==================== ENVIO DE E-MAIL ====================
def enviar_email_com_anexo(destinatario: str, assunto: str, html_body: str, pdf_bytes: bytes, pdf_filename: str):
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

        part = MIMEBase("application", "octet-stream")
        part.set_payload(pdf_bytes)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={pdf_filename}")
        msg.attach(part)

        with smtplib.SMTP(cfg.get("host", "smtp.titan.email"), 587) as server:
            server.starttls()
            server.login(cfg["user"], cfg["password"])
            server.sendmail(cfg["user"], destinatario, msg.as_string())

        return True, "E-mail enviado com sucesso!"
    except Exception as e:
        return False, f"Erro no envio: {str(e)}"

# ==================== SESSION STATE ====================
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

    if st.button("📋 Histórico", use_container_width=True):
        st.session_state.com_mostrar_historico = not st.session_state.get("com_mostrar_historico", False)
        st.rerun()

if st.session_state.get("com_mostrar_historico", False):
    st.title("📋 Histórico de Emissões")
    df_hist = load_historico_emissoes()
    if df_hist.empty:
        st.info("Nenhuma emissão registrada.")
    else:
        st.dataframe(df_hist, use_container_width=True, hide_index=True)
        csv = df_hist.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Baixar CSV", csv, "historico_comissoes.csv", "text/csv")
    st.stop()

# ==================== TÍTULO ====================
st.title("💰 Emissão de Comissão de Parceiros")
st.caption("Conforme Ordem de Serviço TIM SMB OS_2025_29")

step = st.session_state.com_step

# ==================== ETAPAS (Resumidas para brevidade - posso expandir se precisar) ====================
# ... (as etapas 1 a 5 seguem a mesma lógica anterior, mas com WeasyPrint)

# Exemplo da função de gerar contrato (Etapa 4):
if step == 4:
    p = st.session_state.com_parceiro
    base = sum(v["valor"] for v in st.session_state.com_vendas)
    bruto = base * st.session_state.com_fator
    desconto = bruto * (st.session_state.com_imposto / 100)
    liquido = bruto - desconto
    vencimento = date.fromisoformat(st.session_state.com_vencimento)

    # HTML mais bonito para WeasyPrint
    contrato_html = f"""
    <html>
    <head><meta charset="utf-8">
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
        h1 {{ color: #1e3a8a; text-align: center; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ border: 1px solid #999; padding: 10px; text-align: left; }}
        th {{ background: #f0f0f0; }}
        .total {{ font-weight: bold; background: #e6f0ff; }}
    </style>
    </head>
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
        <h2 style="color:#15803d;">Valor Líquido a Receber: {fmt_brl(liquido)}</h2>

        <p><strong>PIX:</strong> {st.session_state.com_pix_tipo} — {st.session_state.com_pix_chave}</p>
        <p><strong>Vencimento:</strong> {vencimento.strftime('%d/%m/%Y')}</p>
    </body>
    </html>
    """

    pdf_bytes = gerar_pdf_contrato(contrato_html)

    if pdf_bytes:
        st.download_button(
            "⬇️ Baixar Contrato em PDF",
            data=pdf_bytes,
            file_name=f"Comissao_{p.get('nome','parceiro').replace(' ','_')}_{fmt_comp(st.session_state.com_comp)}.pdf",
            mime="application/pdf",
            use_container_width=True
        )

    # Botões de navegação...
