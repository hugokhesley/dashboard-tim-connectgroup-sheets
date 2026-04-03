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
def parse_espelho(file_bytes_1: bytes, file_bytes_2: bytes | None = None) -> pd.DataFrame:
    """
    Lê um ou dois XLSX do espelho e retorna df consolidado.
    Quando dois arquivos são passados, faz concat (mesmo layout, partes diferentes).
    """
    def _ler(b: bytes) -> pd.DataFrame:
        df = pd.read_excel(io.BytesIO(b), header=0)
        df.columns = [str(c).strip() for c in df.columns]
        return df

    df = _ler(file_bytes_1)
    if file_bytes_2:
        df2 = _ler(file_bytes_2)
        # Alinha colunas — garante que ambos tenham as mesmas antes do concat
        all_cols = list(dict.fromkeys(list(df.columns) + list(df2.columns)))
        df  = df.reindex(columns=all_cols)
        df2 = df2.reindex(columns=all_cols)
        df  = pd.concat([df, df2], ignore_index=True)

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

        # Filtra apenas aba DadosRadar — evita duplicação com outras abas da planilha
        raw_radar = raw.copy()
        if "_aba" in raw_radar.columns:
            raw_radar = raw_radar[raw_radar["_aba"] == "DadosRadar"].copy()

        # Apenas NOVO e ADITIVO — RENEGOCIAÇÃO tratada separadamente no futuro
        df = apply_filters(raw_radar, mes_alvo, ["NOVO", "ADITIVO"])

        # Apenas ativados no mês
        ativ = df[df["mes_ativacao"] == mes_alvo].copy()

        # Separa por tipo para exibição, mas fator é único (NOVO e ADITIVO = mesma lógica)
        novo    = ativ[ativ["tipo_contratacao"].str.upper() == "NOVO"]
        aditivo = ativ[ativ["tipo_contratacao"].str.upper() == "ADITIVO"]

        vol_total     = int(ativ["acessos"].sum())
        vol_novo      = int(novo["acessos"].sum())
        vol_aditivo   = int(aditivo["acessos"].sum())
        receita_total = ativ["preco_oferta"].sum()
        receita_novo  = novo["preco_oferta"].sum()
        receita_adic  = aditivo["preco_oferta"].sum()

        # Expectativa calculada fora desta função com o fator da sidebar
        # (fator único sobre receita_total — NOVO e ADITIVO seguem a mesma lógica)
        return {
            "vol_total":     vol_total,
            "vol_novo":      vol_novo,
            "vol_aditivo":   vol_aditivo,
            "receita_total": receita_total,
            "receita_novo":  receita_novo,
            "receita_adic":  receita_adic,
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
    st.markdown("**Fator de comissionamento VOZ**")
    st.caption("NOVO e ADITIVO seguem o mesmo fator — definido pela classificação TBP")

    fator_voz = st.number_input(
        "Fator (Receita Contratada × Fator = Comissão)",
        min_value=0.1, max_value=10.0, value=4.5, step=0.1, format="%.1f",
        help="Platinum fidelizado = 5,0 | Silver fidelizado = 4,5 | Blue = 4,0 | Não fidelizado = 0,3",
    )

    st.markdown("---")
    if st.button("🔄 Atualizar dados dashboard", use_container_width=True):
        get_resultados_mes.clear()
        st.rerun()
    st.caption(f"Mês selecionado: **{mes_label(mes_sel)}**")

# ─────────────────────────────────────────────
# UPLOAD DO ESPELHO (1 ou 2 arquivos)
# ─────────────────────────────────────────────
st.markdown("#### 📂 Upload do Espelho TIM")
st.caption("Selecione um ou dois arquivos de uma vez (Ctrl+clique ou Cmd+clique para selecionar múltiplos).")

uploaded_files = st.file_uploader(
    "Planilha(s) Espelho TIM (.xlsx)",
    type=["xlsx"],
    accept_multiple_files=True,
    key="espelho_files",
    help="Selecione os dois arquivos simultaneamente se o espelho vier dividido em partes.",
)

if not uploaded_files:
    st.markdown("""
    <div class="info-box">
        ℹ️ Carregue a planilha Espelho TIM para visualizar o comparativo.
        Se vier em duas partes, selecione os dois arquivos de uma vez (Ctrl+clique).
        Os dados do dashboard para o mês selecionado são carregados automaticamente.
    </div>
    """, unsafe_allow_html=True)

    with st.spinner("Carregando dados do dashboard..."):
        res = get_resultados_mes(mes_sel)

    if res:
        st.markdown(f"### 📊 Dados apurados — {mes_label(mes_sel)}")
        c1, c2, c3 = st.columns(3)
        c1.metric("Volume total ativado", f"{res.get('vol_total',0):,} acessos")
        c2.metric("Receita Contratada",   fmt(res.get("receita_total", 0)))
        c3.metric("Expectativa VOZ (Platinum)",
                  fmt(res.get("receita_total",0) * fator_voz))
        st.info("⬆ Carregue o Espelho acima para ver o comparativo completo.")
    st.stop()

# ─────────────────────────────────────────────
# PROCESSAMENTO
# ─────────────────────────────────────────────
bytes_1 = uploaded_files[0].read()
bytes_2 = uploaded_files[1].read() if len(uploaded_files) > 1 else None

n_arquivos = len(uploaded_files)
nomes = " + ".join(f.name for f in uploaded_files)

with st.spinner(f"Processando {n_arquivos} arquivo(s) do espelho..."):
    df_esp   = parse_espelho(bytes_1, bytes_2)
    res_esp  = resumo_espelho(df_esp)
    res_dash = get_resultados_mes(mes_sel)

if n_arquivos == 2:
    st.success(f"✅ Dois arquivos consolidados: **{nomes}** — {len(df_esp)} linhas no total.")
else:
    st.info(f"📄 Arquivo carregado: **{nomes}** — {len(df_esp)} linhas.")

# Recalcula expectativa com fatores personalizados da sidebar
# Expectativa VOZ: receita total (NOVO+ADITIVO) × fator único configurável
exp_voz = res_dash.get("receita_total", 0) * fator_voz

# ─────────────────────────────────────────────
# ─────────────────────────────────────────────
# NORMALIZAÇÃO DE CNPJ
# ─────────────────────────────────────────────
def norm_cnpj(v) -> str:
    """Remove tudo que não é dígito e retorna string zerada à esquerda."""
    if pd.isna(v):
        return ""
    return str(int(float(str(v).strip()))).zfill(14) if str(v).strip().replace(".","").replace("/","").replace("-","").isdigit() else str(v).strip().replace(".","").replace("/","").replace("-","")

def fmt_cnpj(v: str) -> str:
    d = v.zfill(14)
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return v

# ─────────────────────────────────────────────
# PREPARA CNPJs DO ESPELHO
# só linhas de Comissão Básica VOZ e Banda Larga (as vendas — exclui bônus)
# ─────────────────────────────────────────────
tipos_venda_esp = ["Comissão Básica VOZ", "Comissão Banda Larga"]
df_venda_esp = df_esp[df_esp["Tipo de Comissão"].isin(tipos_venda_esp)].copy()
df_venda_esp["cnpj_norm"] = df_venda_esp["CPF/CNPJ Cliente"].apply(norm_cnpj)
df_venda_esp = df_venda_esp[df_venda_esp["cnpj_norm"] != ""]

# Um registro por CNPJ no espelho (cliente único)
cnpjs_espelho = set(df_venda_esp["cnpj_norm"].unique())

# Resumo por CNPJ no espelho: acessos e comissão
esp_por_cnpj = (
    df_venda_esp[df_venda_esp["Valor Unitário"] > 0]
    .groupby("cnpj_norm")
    .agg(
        acessos_esp=("Valor Unitário", "count"),
        comissao_esp=("Valor Unitário", "sum"),
        razao_esp=("Razão Social", "first"),
        plano_esp=("Plano", lambda x: x.mode()[0] if len(x) else ""),
    )
    .reset_index()
)

# ─────────────────────────────────────────────
# PREPARA CNPJs DO DASHBOARD (DadosRadar)
# ─────────────────────────────────────────────
from data_loader import normalize_columns, _dedup_columns, load_data, apply_filters, _s

raw = load_data()
raw_radar = raw.copy()
if "_aba" in raw_radar.columns:
    raw_radar = raw_radar[raw_radar["_aba"] == "DadosRadar"].copy()

df_dash = apply_filters(raw_radar, mes_sel, ["NOVO", "ADITIVO"])
df_dash = df_dash[df_dash["mes_ativacao"] == mes_sel].copy()

# Normaliza CNPJ do dashboard
df_dash["cnpj_norm"] = df_dash["cnpj"].apply(norm_cnpj) if "cnpj" in df_dash.columns else ""
df_dash = df_dash[df_dash["cnpj_norm"] != ""]

cnpjs_dashboard = set(df_dash["cnpj_norm"].unique())

# Resumo por CNPJ no dashboard
dash_por_cnpj = (
    df_dash.groupby("cnpj_norm")
    .agg(
        acessos_dash=("acessos", "sum"),
        receita_dash=("preco_oferta", "sum"),
        razao_dash=("razao_social", "first"),
    )
    .reset_index()
)
dash_por_cnpj["acessos_dash"] = dash_por_cnpj["acessos_dash"].astype(int)

# ─────────────────────────────────────────────
# CRUZAMENTO
# ─────────────────────────────────────────────
em_ambos       = cnpjs_dashboard & cnpjs_espelho
so_dashboard   = cnpjs_dashboard - cnpjs_espelho   # vendemos mas TIM não pagou
so_espelho     = cnpjs_espelho   - cnpjs_dashboard # TIM pagou mas não achamos no dashboard

# Merge completo para tabela detalhada
df_cruzado = dash_por_cnpj.merge(esp_por_cnpj, on="cnpj_norm", how="outer")
df_cruzado["status"] = df_cruzado.apply(
    lambda r: "✅ Em ambos"        if pd.notna(r.get("acessos_dash")) and pd.notna(r.get("acessos_esp"))
    else "⚠️ Só no Dashboard"     if pd.notna(r.get("acessos_dash"))
    else "❓ Só no Espelho",
    axis=1
)
df_cruzado["razao"] = df_cruzado["razao_dash"].fillna(df_cruzado["razao_esp"])
df_cruzado["cnpj_fmt"] = df_cruzado["cnpj_norm"].apply(fmt_cnpj)

# ─────────────────────────────────────────────
# HEADER DO COMPARATIVO
# ─────────────────────────────────────────────
st.markdown(f"### 🔍 Comparativo de clientes — {mes_label(mes_sel)}")

# KPIs de cobertura
c1, c2, c3, c4 = st.columns(4)
c1.metric("Clientes no Dashboard",  len(cnpjs_dashboard))
c2.metric("Clientes no Espelho",    len(cnpjs_espelho))
c3.metric("✅ Encontrados nos dois", len(em_ambos))
c4.metric("⚠️ Divergências",        len(so_dashboard) + len(so_espelho))

st.markdown("---")

# ─────────────────────────────────────────────
# TABELA PRINCIPAL
# ─────────────────────────────────────────────
tab_todos, tab_faltando, tab_extra = st.tabs([
    f"Todos ({len(df_cruzado)})",
    f"⚠️ Só no Dashboard — não pagos TIM ({len(so_dashboard)})",
    f"❓ Só no Espelho — não achados ({len(so_espelho)})",
])

cols_exibir = ["status", "cnpj_fmt", "razao", "acessos_dash", "receita_dash", "acessos_esp", "comissao_esp", "plano_esp"]
cols_presentes = [c for c in cols_exibir if c in df_cruzado.columns]

col_cfg = {
    "status":       st.column_config.TextColumn("Status"),
    "cnpj_fmt":     st.column_config.TextColumn("CNPJ"),
    "razao":        st.column_config.TextColumn("Razão Social"),
    "acessos_dash": st.column_config.NumberColumn("Acessos Dashboard", format="%d"),
    "receita_dash": st.column_config.NumberColumn("Receita Dashboard (R$)", format="R$ %.2f"),
    "acessos_esp":  st.column_config.NumberColumn("Acessos Espelho", format="%d"),
    "comissao_esp": st.column_config.NumberColumn("Comissão TIM (R$)", format="R$ %.2f"),
    "plano_esp":    st.column_config.TextColumn("Plano"),
}

with tab_todos:
    st.dataframe(
        df_cruzado[cols_presentes].sort_values("status"),
        use_container_width=True, hide_index=True,
        column_config=col_cfg,
    )
    csv = df_cruzado[cols_presentes].to_csv(index=False).encode("utf-8")
    st.download_button("⬇ Exportar CSV", csv, "comparativo_cnpj.csv", "text/csv")

with tab_faltando:
    if so_dashboard:
        df_falt = df_cruzado[df_cruzado["cnpj_norm"].isin(so_dashboard)][cols_presentes]
        st.caption("Clientes que constam nos Resultados do Dashboard mas **não aparecem no Espelho TIM**. Possíveis causas: churn antes da apuração, não elegível, ou erro de CNPJ.")
        st.dataframe(df_falt, use_container_width=True, hide_index=True, column_config=col_cfg)
    else:
        st.success("Todos os clientes do Dashboard foram encontrados no Espelho. ✅")

with tab_extra:
    if so_espelho:
        df_ext = df_cruzado[df_cruzado["cnpj_norm"].isin(so_espelho)][cols_presentes]
        st.caption("Clientes que aparecem no Espelho TIM mas **não foram encontrados no Dashboard**. Possíveis causas: CNPJ diferente no cadastro, venda de outro custcode, ou dado não lançado no Radar.")
        st.dataframe(df_ext, use_container_width=True, hide_index=True, column_config=col_cfg)
    else:
        st.success("Todos os clientes do Espelho foram encontrados no Dashboard. ✅")

