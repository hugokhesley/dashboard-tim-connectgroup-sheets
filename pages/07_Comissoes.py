"""
07_Comissoes.py — Sistema de Comissão de Parceiros
Connect Group | Dashboard TIM Empresas

Acesso restrito: hugo, angelo (conforme PAGE_ACCESS em auth.py)
Integrado ao DadosRadar via Google Sheets (aba: Parceiros, aba: Comissoes)
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from auth import require_login
from data_loader import (
    get_gspread_client,
    registrar_acesso,
    _s, _to_num, _norm_pedido,
)

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Connect Group | Comissões",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

username = require_login("comissoes")
registrar_acesso("Comissões", username=username)

# ─────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────
FATORES_PADRAO = {
    "Black — Fidelizado Novo (5,80)":        5.80,
    "Platinum — Fidelizado (5,00)":          5.00,
    "Black — Dados/Plug In (4,80)":          4.80,
    "Silver — Fidelizado Novo (4,50)":       4.50,
    "Platinum — Dados/Plug In (4,00)":       4.00,
    "Silver — Aditivo (3,50)":               3.50,
    "Blue — Qualquer (3,00)":                3.00,
    "Portabilidade (1,25)":                  1.25,
    "Não fidelizado (0,30)":                 0.30,
    "⚙️ Personalizado":                      None,
}

TIPOS_PRODUTO = [
    "Plano Voz (Móvel)",
    "Plano Dados (Móvel)",
    "Plug In",
    "M2M",
    "TIM Office Fixo",
    "Ultra Fibra (CNPJ)",
    "VAS",
    "Migração Pré→Pós Corporate",
    "Outro",
]

ALIQUOTAS_SIMPLES = [6.00, 6.84, 7.54, 8.04, 10.26, 11.31, 13.50]

MESES_PT = {
    "01": "Jan", "02": "Fev", "03": "Mar", "04": "Abr",
    "05": "Mai", "06": "Jun", "07": "Jul", "08": "Ago",
    "09": "Set", "10": "Out", "11": "Nov", "12": "Dez",
}

# ─────────────────────────────────────────────
# HELPERS SHEETS
# ─────────────────────────────────────────────
SHEET_URL = lambda: st.secrets["sheets"]["url"]

@st.cache_data(ttl=60)
def load_parceiros_sheet() -> pd.DataFrame:
    """Carrega aba 'Parceiros' do Sheets."""
    try:
        client = get_gspread_client()
        ss = client.open_by_url(SHEET_URL())
        try:
            ws = ss.worksheet("Parceiros")
        except Exception:
            # Cria a aba se não existir
            ws = ss.add_worksheet(title="Parceiros", rows=500, cols=8)
            ws.update("A1:H1", [[
                "id", "nome", "cnpj_cpf", "email", "telefone",
                "pix_chave", "pix_tipo", "ativo"
            ]])
            return pd.DataFrame(columns=[
                "id", "nome", "cnpj_cpf", "email", "telefone",
                "pix_chave", "pix_tipo", "ativo"
            ])
        vals = ws.get_all_values()
        if not vals or len(vals) < 2:
            return pd.DataFrame(columns=[
                "id", "nome", "cnpj_cpf", "email", "telefone",
                "pix_chave", "pix_tipo", "ativo"
            ])
        df = pd.DataFrame(vals[1:], columns=vals[0])
        df = df[df["ativo"].str.upper() != "NÃO"].copy()
        df = df[df["nome"] != ""].copy()
        return df.reset_index(drop=True)
    except Exception as e:
        st.warning(f"Aba Parceiros não carregada: {e}")
        return pd.DataFrame()


def salvar_parceiro(dados: dict) -> tuple:
    """Insere novo parceiro na aba Parceiros."""
    try:
        client = get_gspread_client()
        ss = client.open_by_url(SHEET_URL())
        ws = ss.worksheet("Parceiros")
        import time
        novo_id = str(int(time.time()))
        ws.append_row([
            novo_id,
            dados["nome"],
            dados["cnpj_cpf"],
            dados["email"],
            dados["telefone"],
            dados["pix_chave"],
            dados["pix_tipo"],
            "SIM",
        ], value_input_option="USER_ENTERED")
        load_parceiros_sheet.clear()
        return True, novo_id
    except Exception as e:
        return False, str(e)


def salvar_emissao(dados: dict) -> tuple:
    """
    Grava o registro de emissão na aba 'Comissoes'.
    Cria a aba automaticamente se não existir.
    """
    try:
        client = get_gspread_client()
        ss = client.open_by_url(SHEET_URL())
        try:
            ws = ss.worksheet("Comissoes")
        except Exception:
            ws = ss.add_worksheet(title="Comissoes", rows=2000, cols=15)
            ws.update("A1:O1", [[
                "timestamp", "emitido_por", "parceiro", "cnpj_cpf",
                "competencia", "vencimento", "fator", "aliquota_simples",
                "base_vendas", "comissao_bruta", "desconto_imposto",
                "comissao_liquida", "pix_tipo", "pix_chave", "canal_envio"
            ]])
        agora = (datetime.utcnow() - timedelta(hours=3)).strftime("%d/%m/%Y %H:%M:%S")
        ws.append_row([
            agora,
            dados.get("emitido_por", ""),
            dados.get("parceiro", ""),
            dados.get("cnpj_cpf", ""),
            dados.get("competencia", ""),
            dados.get("vencimento", ""),
            dados.get("fator", 0),
            dados.get("aliquota_simples", 0),
            dados.get("base_vendas", 0),
            dados.get("comissao_bruta", 0),
            dados.get("desconto_imposto", 0),
            dados.get("comissao_liquida", 0),
            dados.get("pix_tipo", ""),
            dados.get("pix_chave", ""),
            dados.get("canal_envio", ""),
        ], value_input_option="USER_ENTERED")
        return True, agora
    except Exception as e:
        return False, str(e)


@st.cache_data(ttl=60)
def load_historico_emissoes() -> pd.DataFrame:
    """Carrega histórico de emissões da aba Comissoes."""
    try:
        client = get_gspread_client()
        ss = client.open_by_url(SHEET_URL())
        ws = ss.worksheet("Comissoes")
        vals = ws.get_all_values()
        if not vals or len(vals) < 2:
            return pd.DataFrame()
        df = pd.DataFrame(vals[1:], columns=vals[0])
        for col in ["base_vendas", "comissao_bruta", "desconto_imposto", "comissao_liquida", "fator", "aliquota_simples"]:
            if col in df.columns:
                df[col] = df[col].apply(_to_num)
        return df
    except Exception:
        return pd.DataFrame()


# ─────────────────────────────────────────────
# FORMATAÇÃO
# ─────────────────────────────────────────────
def fmt_brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def fmt_comp(ym: str) -> str:
    """'2025-05' → 'Mai/2025'"""
    if not ym or len(ym) < 7:
        return ym
    y, m = ym[:4], ym[5:7]
    return f"{MESES_PT.get(m, m)}/{y}"


# ─────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────
def _init_state():
    defaults = {
        "com_step": 1,
        "com_parceiro": None,
        "com_vendas": [],
        "com_fator": None,
        "com_fator_label": None,
        "com_imposto": None,
        "com_bruto": 0.0,
        "com_liquido": 0.0,
        "com_desconto_imp": 0.0,
        "com_comp": date.today().strftime("%Y-%m"),
        "com_vencimento": (date.today() + timedelta(days=10)).isoformat(),
        "com_pix_chave": "",
        "com_pix_tipo": "CNPJ",
        "com_canal": "E-mail",
        "com_registro_ts": None,
        "com_mostrar_historico": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()


def reset_fluxo():
    keys = [k for k in st.session_state if k.startswith("com_")]
    for k in keys:
        del st.session_state[k]
    _init_state()


def calcular():
    vendas = st.session_state.com_vendas
    base = sum(v["valor"] for v in vendas)
    fator = st.session_state.com_fator or 0.0
    imp = st.session_state.com_imposto or 0.0
    bruto = base * fator
    desconto = bruto * (imp / 100)
    liquido = bruto - desconto
    st.session_state.com_bruto = bruto
    st.session_state.com_desconto_imp = desconto
    st.session_state.com_liquido = liquido
    return base, bruto, desconto, liquido


# ─────────────────────────────────────────────
# SIDEBAR — NAVEGAÇÃO
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("---")
    st.markdown("**💰 Comissão de Parceiros**")

    passos = ["1 · Parceiro", "2 · Vendas", "3 · Cálculo", "4 · Contrato", "5 · Envio"]
    step_atual = st.session_state.com_step

    for i, nome in enumerate(passos, 1):
        if i < step_atual:
            st.markdown(f"✅ ~~{nome}~~")
        elif i == step_atual:
            st.markdown(f"**➤ {nome}**")
        else:
            st.markdown(f"<span style='color:#555'>{nome}</span>", unsafe_allow_html=True)

    st.markdown("---")

    if st.button("🔄 Nova emissão", use_container_width=True):
        reset_fluxo()
        st.rerun()

    if st.button("📋 Histórico de emissões", use_container_width=True):
        st.session_state.com_mostrar_historico = not st.session_state.com_mostrar_historico
        st.rerun()


# ─────────────────────────────────────────────
# HISTÓRICO (toggle)
# ─────────────────────────────────────────────
if st.session_state.com_mostrar_historico:
    st.title("📋 Histórico de emissões")
    df_hist = load_historico_emissoes()
    if df_hist.empty:
        st.info("Nenhuma emissão registrada ainda.")
    else:
        df_show = df_hist.copy()
        for col in ["comissao_bruta", "comissao_liquida", "base_vendas"]:
            if col in df_show.columns:
                df_show[col] = df_show[col].apply(fmt_brl)
        st.dataframe(df_show, use_container_width=True, hide_index=True)
        # Download CSV
        csv = df_hist.to_csv(index=False).encode("utf-8")
        st.download_button("⬇ Baixar CSV", csv, "emissoes_comissao.csv", "text/csv")
    st.stop()


# ─────────────────────────────────────────────
# TÍTULO DA PÁGINA
# ─────────────────────────────────────────────
st.title("💰 Comissão de Parceiros")
step = st.session_state.com_step
st.progress(step / 5, text=f"Etapa {step} de 5")


# ══════════════════════════════════════════════
# ETAPA 1 — PARCEIRO
# ══════════════════════════════════════════════
if step == 1:
    st.subheader("1 · Selecionar parceiro")

    df_parc = load_parceiros_sheet()

    tab_sel, tab_novo = st.tabs(["Parceiros cadastrados", "Novo parceiro"])

    with tab_sel:
        if df_parc.empty:
            st.info("Nenhum parceiro cadastrado. Use a aba 'Novo parceiro'.")
        else:
            opcoes = ["— selecione —"] + df_parc["nome"].tolist()
            sel = st.selectbox("Parceiro", opcoes, key="sel_parceiro_nome")

            if sel != "— selecione —":
                linha = df_parc[df_parc["nome"] == sel].iloc[0]
                p = linha.to_dict()
                col1, col2, col3 = st.columns(3)
                col1.markdown(f"**CNPJ/CPF:** `{p.get('cnpj_cpf','—')}`")
                col2.markdown(f"**E-mail:** {p.get('email','—')}")
                col3.markdown(f"**PIX ({p.get('pix_tipo','—')}):** `{p.get('pix_chave','—')}`")

                if st.button("✅ Confirmar parceiro", type="primary", use_container_width=True):
                    st.session_state.com_parceiro = p
                    st.session_state.com_pix_chave = p.get("pix_chave", "")
                    st.session_state.com_pix_tipo = p.get("pix_tipo", "CNPJ")
                    st.session_state.com_step = 2
                    st.rerun()

    with tab_novo:
        with st.form("form_novo_parceiro"):
            c1, c2 = st.columns(2)
            nome_novo = c1.text_input("Nome / Razão Social *")
            doc_novo  = c2.text_input("CNPJ / CPF *")
            c3, c4    = st.columns(2)
            email_novo = c3.text_input("E-mail")
            tel_novo   = c4.text_input("Telefone")
            c5, c6    = st.columns([3, 1])
            pix_chave_novo = c5.text_input("Chave PIX *")
            pix_tipo_novo  = c6.selectbox("Tipo PIX", ["CNPJ", "CPF", "E-mail", "Celular", "Aleatória"])
            submit_novo = st.form_submit_button("Cadastrar e usar", type="primary", use_container_width=True)

        if submit_novo:
            if not nome_novo or not doc_novo or not pix_chave_novo:
                st.error("Preencha Nome, CNPJ/CPF e Chave PIX.")
            else:
                dados_novo = {
                    "nome": nome_novo, "cnpj_cpf": doc_novo,
                    "email": email_novo, "telefone": tel_novo,
                    "pix_chave": pix_chave_novo, "pix_tipo": pix_tipo_novo,
                }
                ok, novo_id = salvar_parceiro(dados_novo)
                if ok:
                    st.success(f"Parceiro cadastrado (ID {novo_id}).")
                    dados_novo["id"] = novo_id
                    st.session_state.com_parceiro = dados_novo
                    st.session_state.com_pix_chave = pix_chave_novo
                    st.session_state.com_pix_tipo = pix_tipo_novo
                    st.session_state.com_step = 2
                    st.rerun()
                else:
                    st.error(f"Erro ao salvar: {novo_id}")


# ══════════════════════════════════════════════
# ETAPA 2 — VENDAS
# ══════════════════════════════════════════════
elif step == 2:
    p = st.session_state.com_parceiro
    st.subheader(f"2 · Vendas — {p.get('nome','')}")

    # Formulário de adição
    with st.form("form_add_venda", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns([3, 1.5, 1.5, 1.5])
        desc_v  = c1.text_input("Produto / Descrição *")
        comp_v  = c2.text_input("Competência (MM/AAAA)", value=fmt_comp(st.session_state.com_comp))
        valor_v = c3.number_input("Valor venda (R$) *", min_value=0.0, step=0.01, format="%.2f")
        tipo_v  = c4.selectbox("Tipo", TIPOS_PRODUTO)
        add_btn = st.form_submit_button("➕ Adicionar linha", use_container_width=True)

    if add_btn:
        if not desc_v or valor_v <= 0:
            st.error("Preencha descrição e valor.")
        else:
            import time
            st.session_state.com_vendas.append({
                "id": int(time.time() * 1000),
                "desc": desc_v,
                "comp": comp_v,
                "valor": valor_v,
                "tipo": tipo_v,
            })
            st.rerun()

    # Tabela de vendas
    vendas = st.session_state.com_vendas
    if vendas:
        df_v = pd.DataFrame(vendas)

        # Coluna de delete
        col_header = st.columns([3, 1.5, 1.5, 1.5, 0.5])
        col_header[0].markdown("**Produto**")
        col_header[1].markdown("**Competência**")
        col_header[2].markdown("**Valor**")
        col_header[3].markdown("**Tipo**")

        ids_remover = []
        for _, row in df_v.iterrows():
            c1, c2, c3, c4, c5 = st.columns([3, 1.5, 1.5, 1.5, 0.5])
            c1.write(row["desc"])
            c2.write(row["comp"])
            c3.write(fmt_brl(row["valor"]))
            c4.write(row["tipo"])
            if c5.button("✕", key=f"del_{row['id']}"):
                ids_remover.append(row["id"])

        if ids_remover:
            st.session_state.com_vendas = [v for v in vendas if v["id"] not in ids_remover]
            st.rerun()

        total_base = sum(v["valor"] for v in vendas)
        st.markdown("---")
        m1, m2 = st.columns(2)
        m1.metric("Total base de vendas", fmt_brl(total_base))
        m2.metric("Qtd. linhas", len(vendas))
    else:
        st.info("Nenhuma venda adicionada ainda.")

    st.markdown("---")
    c_back, c_next = st.columns([1, 3])
    if c_back.button("← Voltar"):
        st.session_state.com_step = 1
        st.rerun()
    if c_next.button("Próximo →", type="primary", disabled=len(vendas) == 0, use_container_width=True):
        st.session_state.com_step = 3
        st.rerun()


# ══════════════════════════════════════════════
# ETAPA 3 — CÁLCULO
# ══════════════════════════════════════════════
elif step == 3:
    p = st.session_state.com_parceiro
    st.subheader("3 · Fator e cálculo")

    col_fator, col_resumo = st.columns([1.2, 1])

    with col_fator:
        st.markdown("**Fator multiplicador**")
        st.caption("Conforme classificação TBP 360 (OS TIM SMB OS_2025_29)")

        fator_sel = st.selectbox(
            "Selecione o fator",
            list(FATORES_PADRAO.keys()),
            index=0,
        )

        fator_val = FATORES_PADRAO[fator_sel]
        if fator_val is None:
            fator_val = st.number_input(
                "Fator personalizado", min_value=0.01, max_value=20.0,
                step=0.01, format="%.2f", value=3.0,
            )

        st.session_state.com_fator = fator_val
        st.session_state.com_fator_label = fator_sel

        st.markdown("---")
        st.markdown("**Simples Nacional — alíquota efetiva**")

        opcoes_imp = [f"{a:.2f}%".replace(".", ",") for a in ALIQUOTAS_SIMPLES] + ["Personalizada"]
        imp_sel = st.radio("Alíquota", opcoes_imp, horizontal=True)

        if imp_sel == "Personalizada":
            imp_val = st.number_input("Alíquota (%)", min_value=0.0, max_value=33.0, step=0.01, format="%.2f")
        else:
            imp_val = float(imp_sel.replace(",", ".").replace("%", ""))

        st.session_state.com_imposto = imp_val

    with col_resumo:
        base, bruto, desconto, liquido = calcular()

        st.markdown("**Resumo financeiro**")
        st.markdown(f"""
| Item | Valor |
|---|---|
| Base bruta de vendas | **{fmt_brl(base)}** |
| Fator × {fator_val:.2f} | |
| **Comissão bruta** | **{fmt_brl(bruto)}** |
| Desconto imposto ({imp_val:.2f}%) | − {fmt_brl(desconto)} |
""")
        st.success(f"💰 Valor líquido a pagar: **{fmt_brl(liquido)}**")

    st.markdown("---")
    c_back, c_next = st.columns([1, 3])
    if c_back.button("← Voltar"):
        st.session_state.com_step = 2
        st.rerun()
    if c_next.button("Gerar contrato →", type="primary", use_container_width=True):
        st.session_state.com_step = 4
        st.rerun()


# ══════════════════════════════════════════════
# ETAPA 4 — CONTRATO
# ══════════════════════════════════════════════
elif step == 4:
    p = st.session_state.com_parceiro
    vendas = st.session_state.com_vendas
    base = sum(v["valor"] for v in vendas)
    bruto = st.session_state.com_bruto
    liquido = st.session_state.com_liquido
    desconto = st.session_state.com_desconto_imp
    fator = st.session_state.com_fator
    imp = st.session_state.com_imposto

    st.subheader("4 · Termo de Comissionamento")

    col_cfg, col_prev = st.columns([1, 1.4])

    with col_cfg:
        st.markdown("**Configurações do termo**")
        comp_pag = st.text_input(
            "Competência do pagamento",
            value=fmt_comp(st.session_state.com_comp),
            key="comp_pag_input",
        )
        venc_pag = st.date_input(
            "Vencimento",
            value=date.fromisoformat(st.session_state.com_vencimento),
        )
        st.session_state.com_vencimento = venc_pag.isoformat()

        pix_tipo = st.selectbox(
            "Tipo de PIX",
            ["CNPJ", "CPF", "E-mail", "Celular", "Aleatória"],
            index=["CNPJ", "CPF", "E-mail", "Celular", "Aleatória"].index(
                st.session_state.com_pix_tipo
                if st.session_state.com_pix_tipo in ["CNPJ", "CPF", "E-mail", "Celular", "Aleatória"]
                else "CNPJ"
            ),
        )
        pix_chave = st.text_input("Chave PIX", value=st.session_state.com_pix_chave)
        st.session_state.com_pix_tipo = pix_tipo
        st.session_state.com_pix_chave = pix_chave

    with col_prev:
        st.markdown("**Preview do documento**")

    # Gera conteúdo do contrato como texto
    hoje_str = date.today().strftime("%d/%m/%Y")
    venc_str = venc_pag.strftime("%d/%m/%Y")
    linhas_tab = "\n".join(
        f"| {v['desc']} | {v['comp']} | {v['tipo']} | {fmt_brl(v['valor'])} |"
        for v in vendas
    )

    contrato_md = f"""
---
### TERMO DE COMISSIONAMENTO
**Connect Group Telecom — Parceiro Sem Vínculo Empregatício**

---

**1. IDENTIFICAÇÃO DAS PARTES**

**Contratante:** Connect Group Telecom (Revendedor TIM Empresas)
**Parceiro:** {p.get('nome','')} — {p.get('cnpj_cpf','')}
**E-mail:** {p.get('email','—')} | **Tel:** {p.get('telefone','—')}

---

**2. RELAÇÃO ENTRE AS PARTES**

O Parceiro atua como prestador de serviços independente, sem vínculo empregatício,
subordinação ou exclusividade com a Contratante, sendo remunerado exclusivamente pelos
resultados comerciais obtidos, conforme Ordem de Serviço TIM SMB **(OS_2025_29)**.

---

**3. VENDAS DO PERÍODO — Competência {comp_pag}**

| Produto / Descrição | Comp. | Tipo | Valor Venda |
|---|---|---|---|
{linhas_tab}
| **TOTAL BASE** | | | **{fmt_brl(base)}** |

---

**4. CÁLCULO DA COMISSÃO**

| Item | Valor |
|---|---|
| Base bruta de vendas | {fmt_brl(base)} |
| Fator multiplicador | × {fator:.2f} |
| **Comissão bruta** | **{fmt_brl(bruto)}** |
| Desconto Simples Nacional ({imp:.2f}%) | − {fmt_brl(desconto)} |
| **VALOR LÍQUIDO A RECEBER** | **{fmt_brl(liquido)}** |

---

**5. PAGAMENTO**

**Chave PIX ({pix_tipo}):** `{pix_chave}`
**Vencimento:** {venc_str}

O pagamento será realizado após conferência dos dados e assinatura deste Termo.

---

**6. PREMISSAS — ESTORNOS E PENALIDADES (OS TIM SMB OS_2025_29)**

**6.1 Churn (Cancelamento):** Cancelamentos voluntários ou involuntários em até **180 dias**
da ativação geram estorno integral da comissão. Churn involuntário: prazo de **270 dias**.

**6.2 Fraude:** Identificação de fraude em até **365 dias** da instalação gera estorno de 100%.

**6.3 Suspensão:** Suspensão temporária (incluindo inadimplência > 7 dias) em até **180 dias**
da ativação gera estorno. Migrações Pré→Pós: prazo de **90 dias**.

**6.4 Downgrade:** Rebaixamento de plano em até **180 dias** da ativação/migração
está sujeito a estorno.

**6.5 Inadimplência:** Inadimplência > 30 dias dentro de 4 meses da ativação gera estorno
aplicado em espelho por até 120 dias.

**6.6 Cesta de Qualidade:** Cálculo: ordens sem incidência / total de ordens instaladas (safra M-6).
Deflações incidirão sobre comissão básica e bônus conforme apuração TIM.

Os estornos serão deduzidos em emissões futuras ou cobrados separadamente.

---

**7. DISPOSIÇÕES GERAIS**

A Connect Group atua como intermediária do repasse da remuneração TIM ao Parceiro.
As regras são sujeitas a alteração conforme novas OS emitidas pela TIM. O Parceiro
será notificado de alterações relevantes.

---

*Emitido em {hoje_str} | Connect Group Telecom*

_____________________________ &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; _____________________________

Connect Group Telecom &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; {p.get('nome','')}

Contratante &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; Parceiro / Prestador
"""

    with col_prev:
        with st.expander("📄 Ver contrato completo", expanded=True):
            st.markdown(contrato_md)

    # Download do contrato como .txt (sem dependência de PDF)
    st.download_button(
        label="⬇ Baixar contrato (.txt)",
        data=contrato_md.encode("utf-8"),
        file_name=f"Comissao_{p.get('nome','parceiro').replace(' ','_')}_{comp_pag.replace('/','_')}.txt",
        mime="text/plain",
        use_container_width=True,
    )

    st.markdown("---")
    c_back, c_next = st.columns([1, 3])
    if c_back.button("← Voltar"):
        st.session_state.com_step = 3
        st.rerun()
    if c_next.button("Preparar envio →", type="primary", use_container_width=True):
        st.session_state.com_step = 5
        st.rerun()


# ══════════════════════════════════════════════
# ETAPA 5 — ENVIO E REGISTRO
# ══════════════════════════════════════════════
elif step == 5:
    p = st.session_state.com_parceiro
    bruto = st.session_state.com_bruto
    liquido = st.session_state.com_liquido
    desconto = st.session_state.com_desconto_imp
    fator = st.session_state.com_fator
    imp = st.session_state.com_imposto

    st.subheader("5 · Envio e registro")

    col_pix, col_email = st.columns(2)

    with col_pix:
        st.markdown("**PIX de pagamento**")
        pix_tipo_f = st.selectbox(
            "Tipo da chave",
            ["CNPJ", "CPF", "E-mail", "Celular", "Aleatória"],
            index=["CNPJ", "CPF", "E-mail", "Celular", "Aleatória"].index(
                st.session_state.com_pix_tipo
                if st.session_state.com_pix_tipo in ["CNPJ", "CPF", "E-mail", "Celular", "Aleatória"]
                else "CNPJ"
            ),
        )
        pix_chave_f = st.text_input("Chave PIX", value=st.session_state.com_pix_chave)
        banco_f = st.text_input("Banco (opcional)", placeholder="Ex: Nubank, Sicoob...")
        canal_f = st.selectbox("Canal de envio", ["E-mail", "WhatsApp", "E-mail + WhatsApp", "Presencial (Impresso)"])

        st.session_state.com_pix_tipo = pix_tipo_f
        st.session_state.com_pix_chave = pix_chave_f
        st.session_state.com_canal = canal_f

    with col_email:
        st.markdown("**Preview do e-mail**")
        comp_str = fmt_comp(st.session_state.com_comp)
        venc_str = date.fromisoformat(st.session_state.com_vencimento).strftime("%d/%m/%Y")
        primeiro_nome = p.get("nome", "").split()[0]

        email_preview = f"""Olá, {primeiro_nome}!

Segue o Termo de Comissionamento — {comp_str}.

RESUMO FINANCEIRO
─────────────────────────────────────
Comissão bruta:          {fmt_brl(bruto)}
Desconto imposto ({imp:.2f}%):  − {fmt_brl(desconto)}
VALOR LÍQUIDO:           {fmt_brl(liquido)}
─────────────────────────────────────

PAGAMENTO VIA PIX
Tipo: {pix_tipo_f}
Chave: {pix_chave_f}
{f'Banco: {banco_f}' if banco_f else ''}
Vencimento: {venc_str}

Por favor, assine o documento em anexo e
confirme os dados de pagamento.

Atenciosamente,
Connect Group Telecom"""

        st.text_area("E-mail gerado", email_preview, height=260, disabled=True)

    st.markdown("---")
    st.info("📌 Ao confirmar, esta emissão será gravada na aba **Comissoes** da planilha com todos os dados.")

    c_back, _, c_conf = st.columns([1, 2, 2])
    if c_back.button("← Voltar"):
        st.session_state.com_step = 4
        st.rerun()

    if c_conf.button("✅ Confirmar e registrar emissão", type="primary", use_container_width=True):
        vendas = st.session_state.com_vendas
        base = sum(v["valor"] for v in vendas)
        comp_str_raw = fmt_comp(st.session_state.com_comp)

        dados_emissao = {
            "emitido_por": username,
            "parceiro": p.get("nome", ""),
            "cnpj_cpf": p.get("cnpj_cpf", ""),
            "competencia": comp_str_raw,
            "vencimento": date.fromisoformat(st.session_state.com_vencimento).strftime("%d/%m/%Y"),
            "fator": fator,
            "aliquota_simples": imp,
            "base_vendas": base,
            "comissao_bruta": bruto,
            "desconto_imposto": desconto,
            "comissao_liquida": liquido,
            "pix_tipo": pix_tipo_f,
            "pix_chave": pix_chave_f,
            "canal_envio": canal_f,
        }

        with st.spinner("Registrando na planilha..."):
            ok, ts_ou_erro = salvar_emissao(dados_emissao)
            load_historico_emissoes.clear()

        if ok:
            st.session_state.com_registro_ts = ts_ou_erro
            st.session_state.com_step = 6
            st.rerun()
        else:
            st.error(f"Erro ao registrar: {ts_ou_erro}")


# ══════════════════════════════════════════════
# ETAPA 6 — CONFIRMAÇÃO
# ══════════════════════════════════════════════
elif step == 6:
    p = st.session_state.com_parceiro
    bruto = st.session_state.com_bruto
    liquido = st.session_state.com_liquido

    st.success("✅ Emissão registrada com sucesso!")
    st.markdown(f"**Registrado em:** {st.session_state.com_registro_ts}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Parceiro", p.get("nome", ""))
    c2.metric("Comissão bruta", fmt_brl(bruto))
    c3.metric("Valor líquido", fmt_brl(liquido))
    c4.metric("PIX", st.session_state.com_pix_chave)

    st.markdown("---")
    st.info(f"📊 O registro foi gravado na aba **Comissoes** da planilha DadosRadar.")

    if st.button("➕ Nova emissão", type="primary", use_container_width=True):
        reset_fluxo()
        st.rerun()
