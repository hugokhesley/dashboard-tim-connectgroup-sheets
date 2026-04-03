"""
08_Analise_Espelho.py — Análise do Espelho de Comissionamento TIM
Connect Group | Dashboard TIM Empresas

Compara o resultado apurado nos Resultados do dashboard
com o que foi efetivamente pago pela TIM via planilha Espelho.
Acesso restrito: hugo, angelo
"""

import streamlit as st
import pandas as pd
import io
from datetime import datetime
import sys, os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from auth import require_login
from data_loader import (
    registrar_acesso,
    get_gspread_client,
    load_metas_historico,
    apply_filters,
    load_data,
    load_bko,
    _to_num, _s,
)

# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Connect Group | Análise Espelho",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

username = require_login("espelho")
registrar_acesso("Análise Espelho", username=username)

# ─────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────

# Classificação TBP 360 → fatores Platinum (referência Connect Group)
# A TIM classifica por custcode — pode divergir do negociado com o parceiro
FATORES_PLATINUM = {
    "Fidelizado Novo":    5.0,
    "Fidelizado Aditivo": 4.0,
    "Não Fidelizado":     0.3,
}
FATOR_FIBRA_PLATINUM = 2.5   # Ultra Fibra — fator TIM direto (valor fixo por linha)

TIPOS_COMISSAO = {
    "Comissão Básica VOZ":    "voz",
    "Comissão Banda Larga":   "fibra",
    "Bonus Meta":             "bonus_meta",
    "Bonus Qualidade":        "bonus_qualidade",
}

MESES_PT = {
    "01":"Jan","02":"Fev","03":"Mar","04":"Abr",
    "05":"Mai","06":"Jun","07":"Jul","08":"Ago",
    "09":"Set","10":"Out","11":"Nov","12":"Dez",
}

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def fmt(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",","X").replace(".",",").replace("X",".")

def fmt_pct(v: float) -> str:
    return f"{v:.1f}%".replace(".",",")

def delta_color(diff: float) -> str:
    if diff >= 0:
        return "normal"
    return "inverse"

def mes_label(ym: str) -> str:
    """'02/2026' → 'Fev/2026'"""
    if not ym or "/" not in ym:
        return ym
    m, y = ym.split("/")
    return f"{MESES_PT.get(m, m)}/{y}"

# ─────────────────────────────────────────────
# LEITURA DO ESPELHO
# ─────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def parse_espelho(file_bytes: bytes) -> pd.DataFrame:
    """Lê o XLSX do espelho e retorna df limpo."""
    df = pd.read_excel(io.BytesIO(file_bytes), header=0)
    # Normaliza nomes de colunas
    df.columns = [str(c).strip() for c in df.columns]
    # Garante numéricas
    for col in ["Valor Unitário", "Receita Contratada", "Fator Elemento",
                "Total Receita Bônus Meta", "Total Receita Bônus Aceleração",
                "percentual_qualidade", "Gross Bonus"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


def resumo_espelho(df: pd.DataFrame) -> dict:
    """Extrai os totais consolidados do espelho."""
    out = {}

    # VOZ — comissão básica
    voz = df[df["Tipo de Comissão"] == "Comissão Básica VOZ"]
    out["voz_linhas"]       = len(voz)
    out["voz_receita"]      = voz["Receita Contratada"].sum()
    out["voz_comissao"]     = voz["Valor Unitário"].sum()
    out["voz_fator_medio"]  = (out["voz_comissao"] / out["voz_receita"]) if out["voz_receita"] else 0

    # FIBRA — banda larga positivos e estornos
    fibra = df[df["Tipo de Comissão"] == "Comissão Banda Larga"]
    fibra_pos = fibra[fibra["Valor Unitário"] > 0]
    fibra_neg = fibra[fibra["Valor Unitário"] < 0]
    out["fibra_linhas"]         = len(fibra_pos)
    out["fibra_comissao_bruta"] = fibra_pos["Valor Unitário"].sum()
    out["fibra_estornos"]       = fibra_neg["Valor Unitário"].sum()   # negativo
    out["fibra_comissao_liq"]   = out["fibra_comissao_bruta"] + out["fibra_estornos"]

    # BÔNUS META
    bm = df[df["Tipo de Comissão"] == "Bonus Meta"]
    # O campo Total Receita Bônus Meta é repetido por linha — pegar valor único
    out["bonus_meta_valor"] = bm["Total Receita Bônus Meta"].max() if len(bm) else 0
    out["bonus_meta_linhas_elegiveis"] = len(bm)
    out["bonus_meta_fator"] = bm["Fator Elemento"].iloc[0] if len(bm) else 0

    # BÔNUS QUALIDADE / PERMANÊNCIA
    bq = df[df["Tipo de Comissão"] == "Bonus Qualidade"]
    out["bonus_qual_valor"]  = bq["Valor Unitário"].sum()
    out["bonus_qual_linhas"] = len(bq)

    # TOTAL LÍQUIDO DO ESPELHO
    out["total_espelho"] = (
        out["voz_comissao"]
        + out["fibra_comissao_liq"]
        + out["bonus_meta_valor"]
        + out["bonus_qual_valor"]
    )

    # PERCENTUAL DE QUALIDADE (campo do espelho)
    pct_qual = df["percentual_qualidade"].replace(0, pd.NA).dropna()
    out["percentual_qualidade"] = pct_qual.iloc[0] if len(pct_qual) else None

    # Mês de referência do espelho
    if "Mês" in df.columns:
        out["mes_referencia"] = str(df["Mês"].iloc[0])
    elif "Ano" in df.columns and "Mês" in df.columns:
        out["mes_referencia"] = f"{df['Mês'].iloc[0]}/{df['Ano'].iloc[0]}"
    else:
        out["mes_referencia"] = "—"

    return out


# ─────────────────────────────────────────────
# DADOS DO DASHBOARD (Resultados)
# ─────────────────────────────────────────────
@st.cache_data(ttl=180, show_spinner=False)
def get_resultados_mes(mes_alvo: str) -> dict:
    """
    Puxa do DadosRadar os dados do mês informado (formato MM/AAAA).
    Retorna resumo compatível com o comparativo.
    """
    try:
        raw = load_data()
        bko = load_bko()
        if raw.empty:
            return {}

        df = apply_filters(raw.copy(), mes_alvo, ["NOVO", "ADITIVO"])

        # Apenas ativados no mês
        ativ = df[df["mes_ativacao"] == mes_alvo].copy()

        # Separa NOVO e ADITIVO
        novo    = ativ[ativ["tipo_contratacao"].str.upper() == "NOVO"]
        aditivo = ativ[ativ["tipo_contratacao"].str.upper() == "ADITIVO"]

        vol_total     = int(ativ["acessos"].sum())
        vol_novo      = int(novo["acessos"].sum())
        vol_aditivo   = int(aditivo["acessos"].sum())
        receita_total = ativ["preco_oferta"].sum()
        receita_novo  = novo["preco_oferta"].sum()
        receita_adic  = aditivo["preco_oferta"].sum()

        # Expectativa de comissão VOZ — Platinum fidelizado
        # Novo fidelizado = 5.0 | Aditivo fidelizado = 4.0
        exp_voz_novo    = receita_novo    * FATORES_PLATINUM["Fidelizado Novo"]
        exp_voz_aditivo = receita_adic    * FATORES_PLATINUM["Fidelizado Aditivo"]
        exp_voz_total   = exp_voz_novo + exp_voz_aditivo

        return {
            "vol_total":      vol_total,
            "vol_novo":       vol_novo,
            "vol_aditivo":    vol_aditivo,
            "receita_total":  receita_total,
            "receita_novo":   receita_novo,
            "receita_adic":   receita_adic,
            "exp_voz_novo":   exp_voz_novo,
            "exp_voz_aditivo": exp_voz_aditivo,
            "exp_voz_total":  exp_voz_total,
        }
    except Exception as e:
        st.warning(f"Erro ao carregar dados do dashboard: {e}")
        return {}


# ─────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
.header-espelho {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    border-radius: 12px; padding: 20px 28px; margin-bottom: 24px;
    border-left: 5px solid #e63946;
    display: flex; align-items: center; justify-content: space-between;
}
.header-title { font-size: 1.3rem; font-weight: 700; color: #fff; margin: 0; }
.header-sub   { font-size: 0.85rem; color: #94a3b8; margin: 4px 0 0; }
.header-badge {
    background: #e63946; color: #fff; font-weight: 700;
    padding: 6px 14px; border-radius: 20px; font-size: 0.8rem;
}

.bloco {
    background: #1e2230; border-radius: 10px;
    padding: 16px 20px; border: 1px solid #2a2f3e; margin-bottom: 12px;
}
.bloco-title {
    font-size: 0.75rem; font-weight: 600; text-transform: uppercase;
    letter-spacing: 1px; color: #64748b; margin-bottom: 10px;
}

.valor-grande { font-size: 1.6rem; font-weight: 700; font-family: monospace; }
.label-sm     { font-size: 0.78rem; color: #94a3b8; margin-bottom: 2px; }
.verde  { color: #2ec4b6; }
.vermelho { color: #e63946; }
.amarelo  { color: #f7b731; }
.azul     { color: #4361ee; }
.cinza    { color: #94a3b8; }

.diff-positivo {
    background: rgba(46,196,182,0.1); border: 1px solid rgba(46,196,182,0.3);
    border-radius: 6px; padding: 8px 14px; text-align: center;
}
.diff-negativo {
    background: rgba(230,57,70,0.1); border: 1px solid rgba(230,57,70,0.3);
    border-radius: 6px; padding: 8px 14px; text-align: center;
}
.diff-neutro {
    background: rgba(100,116,139,0.1); border: 1px solid rgba(100,116,139,0.3);
    border-radius: 6px; padding: 8px 14px; text-align: center;
}

.separador { border: none; border-top: 1px solid #2a2f3e; margin: 20px 0; }

.info-box {
    background: rgba(67,97,238,0.08); border: 1px solid rgba(67,97,238,0.25);
    border-radius: 8px; padding: 12px 16px; font-size: 0.82rem; color: #94a3b8;
    margin-bottom: 16px;
}
.warn-box {
    background: rgba(247,183,49,0.08); border: 1px solid rgba(247,183,49,0.3);
    border-radius: 8px; padding: 12px 16px; font-size: 0.82rem; color: #f7b731;
    margin-bottom: 16px;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────
st.markdown("""
<div class="header-espelho">
  <div>
    <p class="header-title">🔍 ANÁLISE DO ESPELHO TIM</p>
    <p class="header-sub">Comparativo: Resultados Dashboard × Pagamento TIM</p>
  </div>
  <div class="header-badge">💰 ESPELHO</div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Configurações")

    # Seleção do mês de referência
    historico_metas = load_metas_historico()
    meses_disponiveis = list(historico_metas.keys()) if historico_metas else []

    # Adiciona meses padrão recentes se não estiverem
    meses_padrao = []
    hoje = datetime.now()
    for delta in range(6):
        m = hoje.month - delta
        y = hoje.year
        while m <= 0:
            m += 12
            y -= 1
        meses_padrao.append(f"{m:02d}/{y}")

    todos_meses = sorted(
        set(meses_disponiveis + meses_padrao),
        key=lambda x: (int(x.split("/")[1]), int(x.split("/")[0])),
        reverse=True
    )

    mes_sel = st.selectbox(
        "Mês de referência (Resultados)",
        todos_meses,
        help="Mês cujos dados do dashboard serão comparados com o espelho",
    )

    st.markdown("---")

    # Fator negociado com TIM (classificação do custcode)
    st.markdown("**Classificação TBP do custcode**")
    st.caption("Define os fatores de expectativa (Comissão Básica VOZ)")

    fator_novo = st.number_input(
        "Fator NOVO fidelizado",
        min_value=0.1, max_value=10.0, value=5.0, step=0.1, format="%.1f",
        help="Platinum fidelizado novo = 5.0 | Silver = 4.5 | Blue = 4.0",
    )
    fator_adic = st.number_input(
        "Fator ADITIVO fidelizado",
        min_value=0.1, max_value=10.0, value=4.0, step=0.1, format="%.1f",
        help="Platinum aditivo fidelizado = 4.0 | Silver = 3.5",
    )

    st.markdown("---")
    if st.button("🔄 Atualizar dados dashboard", use_container_width=True):
        get_resultados_mes.clear()
        st.rerun()
    st.caption(f"Mês selecionado: **{mes_label(mes_sel)}**")

# ─────────────────────────────────────────────
# UPLOAD DO ESPELHO
# ─────────────────────────────────────────────
uploaded = st.file_uploader(
    "📂 Carregar planilha Espelho TIM (.xlsx)",
    type=["xlsx"],
    help="Planilha enviada pela TIM com o detalhamento do pagamento",
)

if not uploaded:
    st.markdown("""
    <div class="info-box">
        ℹ️ Faça o upload da planilha Espelho TIM para visualizar o comparativo.
        Os dados do dashboard para o mês selecionado serão carregados automaticamente.
    </div>
    """, unsafe_allow_html=True)

    # Mostra preview dos dados do dashboard mesmo sem espelho
    with st.spinner("Carregando dados do dashboard..."):
        res = get_resultados_mes(mes_sel)

    if res:
        st.markdown(f"### 📊 Dados apurados — {mes_label(mes_sel)}")
        c1, c2, c3 = st.columns(3)
        c1.metric("Volume total ativado", f"{res.get('vol_total',0):,} acessos")
        c2.metric("Receita Contratada",   fmt(res.get("receita_total", 0)))
        c3.metric("Expectativa VOZ (Platinum)",
                  fmt(res.get("receita_novo",0)*fator_novo + res.get("receita_adic",0)*fator_adic))
        st.info("⬆ Faça o upload do Espelho para ver o comparativo completo.")
    st.stop()

# ─────────────────────────────────────────────
# PROCESSAMENTO
# ─────────────────────────────────────────────
with st.spinner("Processando espelho e carregando dados do dashboard..."):
    file_bytes  = uploaded.read()
    df_esp      = parse_espelho(file_bytes)
    res_esp     = resumo_espelho(df_esp)
    res_dash    = get_resultados_mes(mes_sel)

# Recalcula expectativa com fatores personalizados da sidebar
exp_voz = res_dash.get("receita_novo", 0) * fator_novo + res_dash.get("receita_adic", 0) * fator_adic

# ─────────────────────────────────────────────
# CABEÇALHO DO COMPARATIVO
# ─────────────────────────────────────────────
mes_esp_label = mes_label(
    f"02/{df_esp['Ano'].iloc[0]}" if "Ano" in df_esp.columns else mes_sel
) if len(df_esp) else mes_label(mes_sel)

st.markdown(f"### 📋 Comparativo — {mes_label(mes_sel)}")

st.markdown("""
<div class="info-box">
    📌 <b>Como ler este comparativo:</b>
    A coluna <b>Dashboard</b> reflete os dados apurados pelo sistema (vendas ativadas no mês).
    A coluna <b>Espelho TIM</b> reflete o que foi efetivamente pago pela TIM.
    A diferença pode ocorrer por divergência de fator, elegibilidade, churn prévio ou
    estornos de qualidade aplicados pela TIM.
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# BLOCO 1 — VOLUME E RECEITA
# ─────────────────────────────────────────────
st.markdown("#### 1 · Volume e Receita Contratada")
c1, c2, c3 = st.columns(3)

with c1:
    st.markdown('<div class="bloco">', unsafe_allow_html=True)
    st.markdown('<div class="bloco-title">Volume ativado (Dashboard)</div>', unsafe_allow_html=True)
    vol  = res_dash.get("vol_total", 0)
    novo = res_dash.get("vol_novo", 0)
    adic = res_dash.get("vol_aditivo", 0)
    st.markdown(f'<div class="valor-grande azul">{vol:,}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="label-sm">🆕 Novo: {novo} &nbsp;|&nbsp; ➕ Aditivo: {adic}</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

with c2:
    st.markdown('<div class="bloco">', unsafe_allow_html=True)
    st.markdown('<div class="bloco-title">Linhas no Espelho (VOZ + Fibra)</div>', unsafe_allow_html=True)
    lin_esp = res_esp["voz_linhas"] + res_esp["fibra_linhas"]
    st.markdown(f'<div class="valor-grande cinza">{lin_esp:,}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="label-sm">🎤 VOZ: {res_esp["voz_linhas"]} &nbsp;|&nbsp; 📡 Fibra: {res_esp["fibra_linhas"]}</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

with c3:
    diff_lin = vol - lin_esp
    cls = "diff-positivo" if diff_lin >= 0 else "diff-negativo"
    sinal = "+" if diff_lin >= 0 else ""
    cor = "verde" if diff_lin >= 0 else "vermelho"
    st.markdown(f"""
    <div class="{cls}" style="margin-top:8px; height:80px; display:flex; flex-direction:column; align-items:center; justify-content:center;">
        <div class="label-sm">Diferença volume</div>
        <div class="valor-grande {cor}" style="font-size:1.4rem">{sinal}{diff_lin:,}</div>
        <div class="label-sm" style="font-size:0.7rem">
            {"Dashboard > Espelho (linhas não elegíveis/churn)" if diff_lin > 0 else "Espelho > Dashboard" if diff_lin < 0 else "Valores iguais"}
        </div>
    </div>
    """, unsafe_allow_html=True)

# Receita contratada
c1, c2, c3 = st.columns(3)
with c1:
    st.metric("Receita Contratada (Dashboard VOZ)", fmt(res_dash.get("receita_total", 0)))
with c2:
    st.metric("Receita Contratada (Espelho VOZ)", fmt(res_esp["voz_receita"]))
with c3:
    diff_rec = res_dash.get("receita_total", 0) - res_esp["voz_receita"]
    st.metric("Diferença Receita", fmt(diff_rec), delta=fmt(diff_rec), delta_color=delta_color(-diff_rec))

st.markdown('<hr class="separador">', unsafe_allow_html=True)

# ─────────────────────────────────────────────
# BLOCO 2 — COMISSÃO BÁSICA VOZ
# ─────────────────────────────────────────────
st.markdown("#### 2 · Comissão Básica VOZ")

c1, c2, c3 = st.columns(3)

with c1:
    st.markdown('<div class="bloco">', unsafe_allow_html=True)
    st.markdown('<div class="bloco-title">Expectativa (Dashboard)</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="valor-grande azul">{fmt(exp_voz)}</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="label-sm">
        Novo: {fmt(res_dash.get("receita_novo",0))} × {fator_novo} = {fmt(res_dash.get("receita_novo",0)*fator_novo)}<br>
        Adic: {fmt(res_dash.get("receita_adic",0))} × {fator_adic} = {fmt(res_dash.get("receita_adic",0)*fator_adic)}
    </div>
    """, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

with c2:
    st.markdown('<div class="bloco">', unsafe_allow_html=True)
    st.markdown('<div class="bloco-title">Pago pela TIM (Espelho)</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="valor-grande verde">{fmt(res_esp["voz_comissao"])}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="label-sm">Fator médio TIM: {res_esp["voz_fator_medio"]:.2f}</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

with c3:
    diff_voz = res_esp["voz_comissao"] - exp_voz
    cls = "diff-positivo" if diff_voz >= 0 else "diff-negativo"
    cor = "verde" if diff_voz >= 0 else "vermelho"
    sinal = "+" if diff_voz >= 0 else ""
    pct_voz = (diff_voz / exp_voz * 100) if exp_voz else 0
    st.markdown(f"""
    <div class="{cls}" style="height:100%; min-height:90px; display:flex; flex-direction:column; align-items:center; justify-content:center;">
        <div class="label-sm">TIM pagou vs esperado</div>
        <div class="valor-grande {cor}" style="font-size:1.3rem">{sinal}{fmt(diff_voz)}</div>
        <div class="label-sm">{sinal}{fmt_pct(pct_voz)}</div>
        <div class="label-sm" style="font-size:0.7rem; margin-top:4px">
            {"TIM pagou a mais" if diff_voz > 0 else "TIM pagou a menos" if diff_voz < 0 else "Valores iguais"}
        </div>
    </div>
    """, unsafe_allow_html=True)

# Alerta de diferença de fator
if res_esp["voz_fator_medio"] > 0:
    fator_esperado_medio = (
        res_dash.get("receita_novo",0) * fator_novo + res_dash.get("receita_adic",0) * fator_adic
    ) / res_dash.get("receita_total", 1) if res_dash.get("receita_total",0) > 0 else 0

    if abs(res_esp["voz_fator_medio"] - fator_esperado_medio) > 0.1:
        st.markdown(f"""
        <div class="warn-box">
            ⚠️ <b>Divergência de fator detectada:</b>
            Fator médio esperado: <b>{fator_esperado_medio:.2f}</b> &nbsp;|&nbsp;
            Fator médio pago TIM: <b>{res_esp["voz_fator_medio"]:.2f}</b><br>
            A TIM pode ter classificado o custcode em tier diferente (Silver vs Platinum) ou
            há mix de tipos de venda (fidelizado × não fidelizado).
        </div>
        """, unsafe_allow_html=True)

st.markdown('<hr class="separador">', unsafe_allow_html=True)

# ─────────────────────────────────────────────
# BLOCO 3 — ULTRA FIBRA
# ─────────────────────────────────────────────
st.markdown("#### 3 · Comissão Ultra Fibra (Banda Larga)")

c1, c2, c3 = st.columns(3)
with c1:
    st.markdown('<div class="bloco">', unsafe_allow_html=True)
    st.markdown('<div class="bloco-title">Comissão Fibra (Espelho)</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="valor-grande verde">{fmt(res_esp["fibra_comissao_bruta"])}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="label-sm">{res_esp["fibra_linhas"]} linhas × valor fixo TIM</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

with c2:
    st.markdown('<div class="bloco">', unsafe_allow_html=True)
    st.markdown('<div class="bloco-title">Estornos Qualidade Fibra</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="valor-grande vermelho">{fmt(res_esp["fibra_estornos"])}</div>', unsafe_allow_html=True)
    st.markdown('<div class="label-sm">Estornos por cesta de qualidade (M-6)</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

with c3:
    st.markdown('<div class="bloco">', unsafe_allow_html=True)
    st.markdown('<div class="bloco-title">Fibra Líquida</div>', unsafe_allow_html=True)
    cor_fibra = "verde" if res_esp["fibra_comissao_liq"] >= 0 else "vermelho"
    st.markdown(f'<div class="valor-grande {cor_fibra}">{fmt(res_esp["fibra_comissao_liq"])}</div>', unsafe_allow_html=True)
    pct_est = (abs(res_esp["fibra_estornos"]) / res_esp["fibra_comissao_bruta"] * 100) if res_esp["fibra_comissao_bruta"] else 0
    st.markdown(f'<div class="label-sm">Deflação qualidade: {fmt_pct(pct_est)}</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<hr class="separador">', unsafe_allow_html=True)

# ─────────────────────────────────────────────
# BLOCO 4 — BÔNUS
# ─────────────────────────────────────────────
st.markdown("#### 4 · Bônus (recebidos da TIM — não repassados a parceiros)")

c1, c2, c3 = st.columns(3)
with c1:
    st.markdown('<div class="bloco">', unsafe_allow_html=True)
    st.markdown('<div class="bloco-title">Bônus Meta Corporate</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="valor-grande amarelo">{fmt(res_esp["bonus_meta_valor"])}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="label-sm">Fator atingimento: {res_esp["bonus_meta_fator"]:.2f} &nbsp;|&nbsp; {res_esp["bonus_meta_linhas_elegiveis"]} linhas elegíveis</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

with c2:
    st.markdown('<div class="bloco">', unsafe_allow_html=True)
    st.markdown('<div class="bloco-title">Bônus Qualidade / Permanência</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="valor-grande amarelo">{fmt(res_esp["bonus_qual_valor"])}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="label-sm">{res_esp["bonus_qual_linhas"]} linhas — Bônus Permanência 210 dias</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

with c3:
    total_bonus = res_esp["bonus_meta_valor"] + res_esp["bonus_qual_valor"]
    st.markdown(f"""
    <div class="bloco">
        <div class="bloco-title">Total Bônus TIM</div>
        <div class="valor-grande amarelo">{fmt(total_bonus)}</div>
        <div class="label-sm">Receita adicional Connect Group</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown('<hr class="separador">', unsafe_allow_html=True)

# ─────────────────────────────────────────────
# BLOCO 5 — RESUMO TOTAL
# ─────────────────────────────────────────────
st.markdown("#### 5 · Resumo Geral — Total a Receber da TIM")

total_esp  = res_esp["total_espelho"]
exp_total  = exp_voz + res_esp["fibra_comissao_liq"] + res_esp["bonus_meta_valor"] + res_esp["bonus_qual_valor"]

# Se não tivermos dados fibra do dashboard, usa o do espelho como referência
diff_total = total_esp - exp_voz  # diferença apenas na parte que conseguimos prever

c1, c2, c3, c4 = st.columns(4)
c1.metric("Comissão VOZ (TIM)",  fmt(res_esp["voz_comissao"]))
c2.metric("Fibra Líquida (TIM)", fmt(res_esp["fibra_comissao_liq"]))
c3.metric("Bônus (TIM)",         fmt(res_esp["bonus_meta_valor"] + res_esp["bonus_qual_valor"]))
c4.metric("**TOTAL ESPELHO**",   fmt(total_esp))

st.markdown(f"""
<div style="background:linear-gradient(135deg,#0f3460,#1a1a2e);border-radius:12px;
            padding:20px 28px;margin-top:8px;border:1px solid #2a2f3e;
            display:flex;align-items:center;justify-content:space-between;">
  <div>
    <div style="font-size:0.8rem;color:#94a3b8;text-transform:uppercase;letter-spacing:1px;">
      Total do Espelho TIM — {mes_label(mes_sel)}
    </div>
    <div style="font-size:2rem;font-weight:700;color:#2ec4b6;font-family:monospace;margin-top:4px;">
      {fmt(total_esp)}
    </div>
    <div style="font-size:0.8rem;color:#64748b;margin-top:2px;">
      VOZ {fmt(res_esp["voz_comissao"])} &nbsp;+&nbsp;
      Fibra liq. {fmt(res_esp["fibra_comissao_liq"])} &nbsp;+&nbsp;
      Bônus {fmt(res_esp["bonus_meta_valor"] + res_esp["bonus_qual_valor"])}
    </div>
  </div>
  <div style="text-align:right;">
    <div style="font-size:0.8rem;color:#94a3b8;">Expectativa VOZ</div>
    <div style="font-size:1.2rem;font-weight:600;color:#4361ee;font-family:monospace;">{fmt(exp_voz)}</div>
    <div style="font-size:0.75rem;color:{'#2ec4b6' if res_esp['voz_comissao']>=exp_voz else '#e63946'};">
      Diferença: {'+' if res_esp['voz_comissao']>=exp_voz else ''}{fmt(res_esp['voz_comissao']-exp_voz)}
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

st.markdown('<hr class="separador">', unsafe_allow_html=True)

# ─────────────────────────────────────────────
# BLOCO 6 — DETALHE DO ESPELHO
# ─────────────────────────────────────────────
st.markdown("#### 6 · Detalhe do Espelho")

tab_voz, tab_fibra, tab_bonus, tab_raw = st.tabs([
    f"🎤 VOZ ({res_esp['voz_linhas']})",
    f"📡 Fibra ({res_esp['fibra_linhas'] + abs(int(df_esp[(df_esp['Tipo de Comissão']=='Comissão Banda Larga') & (df_esp['Valor Unitário']<0)].shape[0]))})",
    "⭐ Bônus",
    "📄 Raw completo",
])

cols_exibir = ["Tipo de Comissão", "Plano", "Descrição", "Tipo de Venda",
               "Receita Contratada", "Fator Elemento", "Valor Unitário",
               "Data Ativação", "CPF/CNPJ Cliente", "GSM"]

def df_para_exibir(filtro):
    sub = df_esp[filtro].copy()
    cols = [c for c in cols_exibir if c in sub.columns]
    return sub[cols].reset_index(drop=True)

with tab_voz:
    df_v = df_para_exibir(df_esp["Tipo de Comissão"] == "Comissão Básica VOZ")
    st.dataframe(df_v, use_container_width=True, hide_index=True,
        column_config={
            "Valor Unitário":      st.column_config.NumberColumn("Comissão (R$)", format="R$ %.2f"),
            "Receita Contratada":  st.column_config.NumberColumn("Receita Contrat. (R$)", format="R$ %.2f"),
            "Fator Elemento":      st.column_config.NumberColumn("Fator TIM", format="%.2f"),
        })

with tab_fibra:
    df_f = df_para_exibir(df_esp["Tipo de Comissão"] == "Comissão Banda Larga")
    st.dataframe(df_f, use_container_width=True, hide_index=True,
        column_config={
            "Valor Unitário":  st.column_config.NumberColumn("Comissão (R$)", format="R$ %.2f"),
            "Fator Elemento":  st.column_config.NumberColumn("Fator TIM", format="%.2f"),
        })

with tab_bonus:
    df_b = df_para_exibir(df_esp["Tipo de Comissão"].isin(["Bonus Meta", "Bonus Qualidade"]))
    cols_b = ["Tipo de Comissão", "Descrição", "Receita Contratada",
              "Fator Elemento", "Valor Unitário", "Total Receita Bônus Meta"]
    cols_b = [c for c in cols_b if c in df_b.columns]
    st.dataframe(df_b[cols_b], use_container_width=True, hide_index=True,
        column_config={
            "Valor Unitário":          st.column_config.NumberColumn("Valor Unitário (R$)", format="R$ %.2f"),
            "Receita Contratada":      st.column_config.NumberColumn("Receita Contrat. (R$)", format="R$ %.2f"),
            "Total Receita Bônus Meta": st.column_config.NumberColumn("Total Bônus Meta (R$)", format="R$ %.2f"),
        })

with tab_raw:
    st.dataframe(df_esp, use_container_width=True, hide_index=True)
    csv = df_esp.to_csv(index=False).encode("utf-8")
    st.download_button("⬇ Baixar CSV completo", csv, "espelho_completo.csv", "text/csv")
