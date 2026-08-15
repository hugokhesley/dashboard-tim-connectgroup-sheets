"""
08_Analise_Espelho.py — Análise do Espelho de Comissionamento TIM
Connect Group | Dashboard TIM Empresas

Lê o CSV do espelho TIM (encoding latin1, vírgula decimal, CNPJ float),
categoriza em 6 blocos, cruza com DadosRadar e exibe comparativo completo.
Preparado para múltiplos custcodes.
"""

import streamlit as st
import pandas as pd
import io
from datetime import datetime, date
import sys, os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from auth import require_login
from erros import registrar_falha
from data_loader import registrar_acesso, get_gspread_client, load_data, apply_filters, _s, _to_num

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
# CUSTCODES CONHECIDOS
# ─────────────────────────────────────────────
CUSTCODES = {
    "NE80_NEN15I_NEE021": "Connect Group Solutions (53.692.197/0001-33)",
    "NE80_NEN15I_NEE363": "Conect Brasil (29.753.512/0001-00)",
}

# ─────────────────────────────────────────────
# MAPEAMENTO DE CATEGORIAS
# ─────────────────────────────────────────────
# Tipo de Comissão → categoria interna
CATEGORIAS = {
    "Comissão Básica VOZ":   "voz",
    "Comissão Pós-venda Pós": "renegociacao",
    "Bonus Qualidade":        "bonus_qualidade",
    "Bonus Meta":             "bonus_meta",
    "Incentivo a Vendas":     "bonus_estrutura",
    "Comissão Banda Larga":   "fibra",
}

LABELS = {
    "voz":             "Comissão Básica VOZ",
    "renegociacao":    "Pós-venda / Renegociação",
    "bonus_qualidade": "Bônus Qualidade (M7/M14)",
    "bonus_meta":      "Bônus Meta Corporate",
    "bonus_estrutura": "Bônus Estrutura (CLTs)",
    "fibra":           "Comissão Banda Larga",
}

MESES_PT = {
    1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",
    7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez",
}
# Indexado pelos 3 primeiros chars — imune a acentos e variações ("Março" → "mar" → 3)
MESES_PT_INV = {v.lower()[:3]: k for k, v in MESES_PT.items()}

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def fmt(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",","X").replace(".",",").replace("X",".")

def fmt_pct(v: float) -> str:
    return f"{v:.1f}%".replace(".",",")

def to_num_br(v) -> float:
    """Converte string com vírgula decimal ('1.234,56') para float."""
    if pd.isna(v) or str(v).strip() in ("", "0", "-"):
        return 0.0
    try:
        return float(str(v).replace(".","").replace(",","."))
    except Exception:
        return 0.0

def norm_cnpj(v) -> str:
    """
    Converte qualquer formato de CNPJ para string de 14 dígitos.
    Trata: float (6,6E+10), int, string com/sem máscara.
    """
    if pd.isna(v):
        return ""
    s = str(v).strip()
    # Remove notação científica / float
    try:
        s = str(int(float(s)))
    except Exception:
        pass
    # Remove caracteres não numéricos
    s = "".join(c for c in s if c.isdigit())
    return s.zfill(14) if s else ""

def fmt_cnpj(v: str) -> str:
    d = str(v).zfill(14)
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return v

def mes_espelho_para_num(s: str) -> int:
    """'Março' → 3  (usa os 3 primeiros chars para ignorar acentos/sufixos)"""
    return MESES_PT_INV.get(s.strip().lower()[:3], 0)

# ─────────────────────────────────────────────
# PARSER DO CSV DO ESPELHO
# ─────────────────────────────────────────────
def parse_espelho_csv(file_bytes: bytes) -> pd.DataFrame:
    """
    Lê CSV do espelho TIM (encoding latin1, separador detectado automaticamente).
    Normaliza tipos e retorna df limpo.
    """
    df = pd.read_csv(
        io.BytesIO(file_bytes),
        encoding="latin1",
        sep=None,
        engine="python",
        on_bad_lines="skip",
    )
    df.columns = [str(c).strip() for c in df.columns]

    # Converte valores monetários (vírgula decimal)
    cols_num = [
        "Valor Unitário", "Receita Contratada", "Fator Elemento",
        "Total Receita Bônus Meta", "Total Receita Bônus Aceleração",
        "Gross Bonus", "Fator Bonus", "percentual_qualidade",
        "meta_grupo_economico", "atingimento_grupo_economico",
    ]
    for col in cols_num:
        if col in df.columns:
            df[col] = df[col].apply(to_num_br)

    # Normaliza CNPJ do cliente
    if "CPF/CNPJ Cliente" in df.columns:
        df["cnpj_norm"] = df["CPF/CNPJ Cliente"].apply(norm_cnpj)

    # Categoria interna
    if "Tipo de Comissão" in df.columns:
        df["categoria"] = df["Tipo de Comissão"].map(CATEGORIAS).fillna("outro")

    return df


def resumo_espelho(df: pd.DataFrame) -> dict:
    """Extrai totais consolidados por categoria."""
    out = {}

    def _sub(cat, positivo=True):
        mask = df["categoria"] == cat
        if positivo:
            mask = mask & (df["Valor Unitário"] >= 0)
        else:
            mask = mask & (df["Valor Unitário"] < 0)
        return df[mask]

    # VOZ
    voz = _sub("voz")
    out["voz_valor"]    = voz["Valor Unitário"].sum()
    out["voz_linhas"]   = len(voz)
    out["voz_receita"]  = voz["Receita Contratada"].sum()
    out["voz_novo"]     = voz[voz["Tipo de Venda"].str.lower() == "novo"]["Valor Unitário"].sum()
    out["voz_aditivo"]  = voz[voz["Tipo de Venda"].str.lower() == "aditivo"]["Valor Unitário"].sum()

    # Renegociação
    ren = _sub("renegociacao")
    out["ren_valor"]   = ren["Valor Unitário"].sum()
    out["ren_linhas"]  = len(ren)
    out["ren_receita"] = ren["Receita Contratada"].sum()

    # Fibra
    fibra_pos = _sub("fibra", positivo=True)
    fibra_neg = _sub("fibra", positivo=False)
    out["fibra_valor"]   = fibra_pos["Valor Unitário"].sum()
    out["fibra_estorno"] = fibra_neg["Valor Unitário"].sum()
    out["fibra_liquido"] = out["fibra_valor"] + out["fibra_estorno"]
    out["fibra_linhas"]  = len(fibra_pos)

    # Bônus Qualidade — M7 (210 dias) e M14 (420 dias)
    bq = _sub("bonus_qualidade")
    bq210 = bq[bq["Descrição"].str.contains("210", na=False)]
    bq420 = bq[bq["Descrição"].str.contains("420", na=False)]
    out["bq_m7_valor"]  = bq210["Valor Unitário"].sum()
    out["bq_m7_linhas"] = len(bq210)
    out["bq_m14_valor"] = bq420["Valor Unitário"].sum()
    out["bq_m14_linhas"]= len(bq420)
    out["bq_total"]     = bq["Valor Unitário"].sum()

    # Bônus Meta — valor real é o campo Total Receita Bônus Meta (único por espelho)
    bm = _sub("bonus_meta")
    out["bm_valor"]          = bm["Total Receita Bônus Meta"].max() if len(bm) else 0
    out["bm_linhas_elegiveis"] = len(bm)

    # Bônus Estrutura
    be = _sub("bonus_estrutura")
    out["be_valor"]  = be["Valor Unitário"].sum()
    out["be_linhas"] = len(be)

    # Percentual qualidade
    pq = df["percentual_qualidade"].replace(0, pd.NA).dropna()
    out["pct_qualidade"] = pq.iloc[0] if len(pq) else None

    # Identificação
    out["custcode"]  = df["Custcode Pagamento"].iloc[0] if "Custcode Pagamento" in df.columns else "—"
    out["mes_label"] = df["Mês"].iloc[0] if "Mês" in df.columns else "—"
    out["ano"]       = df["Ano"].iloc[0] if "Ano" in df.columns else "—"
    out["cnpj_parc"] = df["CNPJ Parceiro"].iloc[0] if "CNPJ Parceiro" in df.columns else "—"

    # Total geral
    out["total"] = (
        out["voz_valor"] + out["ren_valor"] + out["fibra_liquido"]
        + out["bq_total"] + out["bm_valor"] + out["be_valor"]
    )

    return out


# ─────────────────────────────────────────────
# DADOS DASHBOARD
# ─────────────────────────────────────────────
@st.cache_data(ttl=180, show_spinner=False)
def get_dash_mes(mes_alvo: str) -> dict:
    """
    Puxa acessos NOVO+ADITIVO para o mês informado.
    Busca diretamente em todas as abas da planilha via gspread,
    filtrando por data_ativacao correspondente ao mês.
    Usa normalize_columns do data_loader para compatibilidade.
    """
    from data_loader import normalize_columns, _dedup_columns, _to_num, _s, _sup, parse_month

    try:
        client     = get_gspread_client()
        sheet_url  = st.secrets["sheets"]["url"]
        ss         = client.open_by_url(sheet_url)

        # Para análise do espelho, busca APENAS na aba "resultados"
        # que contém o histórico fechado mês a mês
        ABAS_HISTORICO = {"resultados"}

        dfs = []
        for ws in ss.worksheets():
            titulo = ws.title.strip().lower()
            if titulo not in ABAS_HISTORICO:
                continue
            try:
                vals = ws.get_all_values()
                if not vals or len(vals) < 2:
                    continue
                df = pd.DataFrame(vals[1:], columns=vals[0])
                df = _dedup_columns(df)
                df.columns = [_s(c).lower() for c in df.columns]
                df = _dedup_columns(df)
                df["_aba"] = ws.title
                dfs.append(df)
            except Exception as e:
                # Pular a aba calado tira um mês inteiro da análise sem avisar.
                registrar_falha(f"ler a aba '{ws.title}'", e)
                continue

        if not dfs:
            return {}

        all_cols = list(dict.fromkeys(c for d in dfs for c in d.columns))
        raw = pd.concat([d.reindex(columns=all_cols) for d in dfs], ignore_index=True)

        # Normaliza e filtra diretamente — sem apply_filters
        # pois a aba "resultados" só tem ativados (sem pipeline, sem cancelados)
        raw = normalize_columns(raw)
        raw = _dedup_columns(raw)

        for col in ["acessos", "preco_oferta"]:
            if col in raw.columns:
                raw[col] = raw[col].apply(_to_num)

        # Gera mes_ativacao
        if "data_ativacao" not in raw.columns:
            return {}
        raw["mes_ativacao"] = parse_month(raw["data_ativacao"])

        # Filtra só o mês alvo
        ativ = raw[raw["mes_ativacao"] == mes_alvo].copy()

        # Filtra NOVO e ADITIVO — sem excluir por fila (resultados só tem ativos)
        if "tipo_contratacao" in ativ.columns:
            ativ = ativ[ativ["tipo_contratacao"].apply(
                lambda x: _sup(x) in ["NOVO", "ADITIVO"]
            )].copy()

        # NÃO deduplica por pedido — na aba resultados cada linha = 1 acesso
        # (um pedido com 12 linhas = 12 acessos distintos, todos devem ser contados)

        if ativ.empty:
            return {}

        # Info de debug
        _mes_raw = raw[raw["mes_ativacao"] == mes_alvo].copy()
        total_antes = len(_mes_raw)
        tipos_encontrados = _mes_raw["tipo_contratacao"].value_counts().to_dict() if "tipo_contratacao" in _mes_raw.columns else {}
        acessos_por_tipo = _mes_raw.groupby("tipo_contratacao")["acessos"].sum().to_dict() if "tipo_contratacao" in _mes_raw.columns else {}
        receita_por_tipo = _mes_raw.groupby("tipo_contratacao")["preco_oferta"].sum().to_dict() if "tipo_contratacao" in _mes_raw.columns else {}

        if "cnpj" in ativ.columns:
            ativ["cnpj_norm"] = ativ["cnpj"].apply(norm_cnpj)

        novo  = ativ[ativ["tipo_contratacao"].apply(lambda x: _sup(x) == "NOVO")]
        adic  = ativ[ativ["tipo_contratacao"].apply(lambda x: _sup(x) == "ADITIVO")]

        # Renegociação — no mesmo raw, filtra tipo RENEGOCIAÇÃO no mês
        reneg = _mes_raw[
            _mes_raw["tipo_contratacao"].apply(lambda x: _sup(x) == "RENEGOCIAÇÃO")
        ].copy() if "tipo_contratacao" in _mes_raw.columns else pd.DataFrame()

        return {
            "vol_total":        int(ativ["acessos"].sum()),
            "vol_novo":         int(novo["acessos"].sum()),
            "vol_aditivo":      int(adic["acessos"].sum()),
            "vol_reneg":        int(reneg["acessos"].sum()) if not reneg.empty else 0,
            "receita":          ativ["preco_oferta"].sum(),
            "receita_novo":     novo["preco_oferta"].sum(),
            "receita_adic":     adic["preco_oferta"].sum(),
            "receita_reneg":    reneg["preco_oferta"].sum() if not reneg.empty else 0,
            "cnpjs":            set(ativ["cnpj_norm"].dropna().unique()) if "cnpj_norm" in ativ.columns else set(),
            "df":               ativ,
            "abas_lidas":       list(raw["_aba"].unique()),
            "total_antes":       total_antes,
            "tipos_encontrados": tipos_encontrados,
            "acessos_por_tipo":  acessos_por_tipo,
            "receita_por_tipo":  receita_por_tipo,
        }
    except Exception as e:
        st.warning(f"Erro ao carregar dados do dashboard: {e}")
        return {}


# ─────────────────────────────────────────────
# TABELA DE FATORES POR FAIXA — OS TIM SMB
# ─────────────────────────────────────────────
# Estrutura: {classificacao: {"NOVO": [(limite, fator),...], "ADITIVO": [...]}}
# Sem atingimento de meta: fator varia por faixa de receita contratada
# Com atingimento de meta: fator máximo (última faixa) para todos os acessos

FATORES_FAIXA = {
    "Black": {
        "NOVO":    [(10,3.5),(20,4.1),(25,4.6),(29.99,5.2),(float("inf"),5.8)],
        "ADITIVO": [(10,2.9),(20,3.4),(25,3.8),(29.99,4.3),(float("inf"),4.8)],
    },
    "Platinum": {
        "NOVO":    [(10,3.0),(20,3.5),(25,4.0),(29.99,4.5),(float("inf"),5.0)],
        "ADITIVO": [(10,2.4),(20,2.8),(25,3.2),(29.99,3.6),(float("inf"),4.0)],
    },
    "Silver": {
        "NOVO":    [(10,2.7),(20,3.2),(25,3.6),(29.99,4.1),(float("inf"),4.5)],
        "ADITIVO": [(10,2.3),(20,2.5),(25,2.8),(29.99,3.2),(float("inf"),3.5)],
    },
    "Blue": {
        "NOVO":    [(10,2.4),(20,2.8),(25,3.4),(29.99,3.6),(float("inf"),4.0)],
        "ADITIVO": [(10,1.8),(20,2.1),(25,2.4),(29.99,2.7),(float("inf"),3.0)],
    },
}

def fator_por_faixa(classificacao: str, tipo_venda: str, receita: float, meta_atingida: bool) -> float:
    """
    Retorna o fator de comissão conforme classificação TBP, tipo de venda e receita.
    Se meta atingida → fator máximo (≥29,99) independente da receita.
    """
    cls  = FATORES_FAIXA.get(classificacao, FATORES_FAIXA["Platinum"])
    tipo = "NOVO" if str(tipo_venda).strip().upper() == "NOVO" else "ADITIVO"
    faixas = cls[tipo]
    if meta_atingida:
        return faixas[-1][1]  # melhor faixa
    for limite, fator in faixas:
        if receita < limite:
            return fator
    return faixas[-1][1]

def calcular_expectativa_voz(df_ativ: pd.DataFrame, classificacao: str, meta_atingida: bool) -> dict:
    """
    Calcula expectativa de comissão VOZ linha a linha.
    Retorna dict com totais por tipo e expectativa total.
    """
    if df_ativ.empty or "preco_oferta" not in df_ativ.columns:
        return {"exp_novo":0,"exp_adic":0,"exp_total":0,"linhas":0}

    df = df_ativ.copy()
    df["tipo_upper"] = df["tipo_contratacao"].apply(lambda x: str(x).strip().upper())
    df["fator_calc"] = df.apply(
        lambda r: fator_por_faixa(
            classificacao,
            r["tipo_upper"],
            r["preco_oferta"],
            meta_atingida,
        ), axis=1
    )
    df["comissao_calc"] = df["preco_oferta"] * df["fator_calc"]

    novo_mask = df["tipo_upper"] == "NOVO"
    adic_mask = df["tipo_upper"] == "ADITIVO"

    return {
        "exp_novo":   df[novo_mask]["comissao_calc"].sum(),
        "exp_adic":   df[adic_mask]["comissao_calc"].sum(),
        "exp_total":  df["comissao_calc"].sum(),
        "linhas":     len(df),
        "df_calc":    df,
    }


# ─────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
.esp-header {
    background: linear-gradient(135deg,#0d1117,#161b22,#1c2333);
    border-radius:12px; padding:20px 28px; margin-bottom:24px;
    border-left:5px solid #e63946;
    display:flex; align-items:center; justify-content:space-between;
}
.esp-title { font-size:1.3rem; font-weight:700; color:#fff; margin:0; }
.esp-sub   { font-size:0.85rem; color:#8b949e; margin:4px 0 0; }
.esp-badge { background:#e63946; color:#fff; font-weight:700;
             padding:6px 14px; border-radius:20px; font-size:0.8rem; }

.bloco { background:#161b22; border-radius:10px; padding:16px 20px;
         border:1px solid #30363d; margin-bottom:12px; }
.bloco-title { font-size:0.72rem; font-weight:600; text-transform:uppercase;
               letter-spacing:1.2px; color:#8b949e; margin-bottom:8px; }
.valor-g  { font-size:1.6rem; font-weight:700; font-family:monospace; }
.label-sm { font-size:0.78rem; color:#8b949e; margin-top:2px; }
.verde    { color:#2ec4b6; }
.azul     { color:#4361ee; }
.amarelo  { color:#f7b731; }
.laranja  { color:#ff9f43; }
.roxo     { color:#a29bfe; }
.vermelho { color:#e63946; }
.cinza    { color:#8b949e; }

.total-bar {
    background:linear-gradient(135deg,#0f3460,#1a1a2e);
    border-radius:12px; padding:20px 28px; margin:16px 0;
    border:1px solid #30363d;
    display:flex; align-items:center; justify-content:space-between;
}
.sep { border:none; border-top:1px solid #30363d; margin:20px 0; }

.tag { display:inline-block; padding:2px 10px; border-radius:20px;
       font-size:0.72rem; font-weight:600; }
.tag-voz    { background:rgba(67,97,238,.15); color:#7289fa; }
.tag-ren    { background:rgba(255,159,67,.15); color:#ff9f43; }
.tag-bq     { background:rgba(247,183,49,.15); color:#f7b731; }
.tag-bm     { background:rgba(162,155,254,.15); color:#a29bfe; }
.tag-be     { background:rgba(46,196,182,.15); color:#2ec4b6; }
.tag-fibra  { background:rgba(230,57,70,.15); color:#e63946; }

.diff-pos { background:rgba(46,196,182,.08); border:1px solid rgba(46,196,182,.25);
            border-radius:8px; padding:12px 16px; text-align:center; }
.diff-neg { background:rgba(230,57,70,.08); border:1px solid rgba(230,57,70,.25);
            border-radius:8px; padding:12px 16px; text-align:center; }
.info-box { background:rgba(67,97,238,.08); border:1px solid rgba(67,97,238,.25);
            border-radius:8px; padding:12px 16px; font-size:0.82rem;
            color:#8b949e; margin-bottom:16px; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────
st.markdown("""
<div class="esp-header">
  <div>
    <p class="esp-title">🔍 ANÁLISE DO ESPELHO TIM</p>
    <p class="esp-sub">Comissionamento detalhado · VOZ · Renegociação · Bônus · Estrutura</p>
  </div>
  <div class="esp-badge">ESPELHO</div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Configurações")
    st.caption("Mês detectado automaticamente do espelho.")
    st.markdown("---")

    st.markdown("**Classificação TBP**")
    classificacao = st.selectbox(
        "Classificação do custcode",
        ["Platinum", "Black", "Silver", "Blue"],
        index=0,
    )
    st.markdown("---")

    st.markdown("**Cenário de meta**")
    atingiu_meta = st.radio(
        "Atingimento da Meta Receita Corporate",
        ["✅ Atingiu meta (fator máximo)", "❌ Não atingiu meta (por faixa)"],
        index=1,
    )
    st.markdown("---")

    st.markdown("**Fator Renegociação**")
    fator_reneg = st.number_input(
        "Fator Reneg.",
        min_value=0.1, max_value=10.0, value=3.1, step=0.1, format="%.1f",
        help="Varia por plano — use o fator médio do mês",
    )
    st.markdown("---")

    st.markdown("**Bônus Meta**")
    meta_receita = st.number_input(
        "Meta Receita Corporate (R$)",
        min_value=0.0, value=0.0, step=1000.0, format="%.2f",
        help="Meta definida pela TIM para o mês do espelho",
    )
    st.markdown("---")

    if st.button("🔄 Atualizar dashboard", use_container_width=True):
        get_dash_mes.clear()
        st.rerun()

# ─────────────────────────────────────────────
# UPLOAD
# ─────────────────────────────────────────────
st.markdown("#### 📂 Upload do Espelho TIM (.csv)")
st.caption("Selecione um ou dois arquivos simultaneamente (Ctrl+clique para múltiplos).")

uploads = st.file_uploader(
    "Arquivo(s) CSV do espelho",
    type=["csv"],
    accept_multiple_files=True,
    key="esp_csv",
)

if not uploads:
    st.markdown('<div class="info-box">ℹ️ Faça o upload do CSV do espelho TIM para iniciar a análise.</div>', unsafe_allow_html=True)
    st.info("Faça o upload do espelho — o mês de referência será detectado automaticamente.")
    st.stop()

# ─────────────────────────────────────────────
# PROCESSAMENTO
# ─────────────────────────────────────────────
dfs = []
for f in uploads:
    dfs.append(parse_espelho_csv(f.read()))

df_esp = pd.concat(dfs, ignore_index=True) if len(dfs) > 1 else dfs[0]
res    = resumo_espelho(df_esp)

# Deriva mês/ano do dashboard direto do espelho (colunas Ano e Mês)
mes_num = mes_espelho_para_num(str(res.get("mes_label", "")))
ano_num = int(res.get("ano", datetime.now().year))
mes_dash = f"{mes_num:02d}/{ano_num}" if mes_num else None

with st.sidebar:
    if mes_dash:
        st.info(f"📅 Espelho: **{res.get('mes_label','')} / {ano_num}**\nComparando com Dashboard **{mes_dash}**")

with st.spinner("Carregando dados do dashboard..."):
    dash = get_dash_mes(mes_dash) if mes_dash else {}

# Debug — mostra o que foi encontrado (remover depois de validar)
if dash:
    with st.expander("🔎 Debug — dados encontrados", expanded=False):
        st.write(f"**Abas lidas:** {dash.get('abas_lidas', [])}")
        st.write(f"**Mês buscado:** `{mes_dash}`")
        st.write(f"**Total linhas antes filtro tipo:** {dash.get('total_antes', '?')}")
        st.write(f"**Tipos encontrados (linhas):** {dash.get('tipos_encontrados', '?')}")
        st.write(f"**Acessos por tipo (soma coluna):** {dash.get('acessos_por_tipo', '?')}")
        st.write(f"**Receita por tipo (soma coluna):** {dash.get('receita_por_tipo', '?')}")
        st.write(f"**Acessos NOVO+ADITIVO filtrado:** {dash.get('vol_total', 0)}")
        st.write(f"**Receita NOVO+ADITIVO filtrado:** {fmt(dash.get('receita', 0))}")
elif mes_dash:
    with st.expander("🔎 Debug — nenhum dado encontrado", expanded=True):
        st.warning(f"Buscou `{mes_dash}` — nenhum registro encontrado.")

# Info do espelho
custcode_label = CUSTCODES.get(res["custcode"], res["custcode"])
mes_dash_label = f"{res['mes_label']}/{res['ano']}"
st.success(f"✅ Espelho de **{mes_dash_label}** · {custcode_label} · {len(df_esp):,} linhas · Dashboard carregado automaticamente para o mesmo período")

# ─────────────────────────────────────────────
# SEÇÃO 1 — VISÃO GERAL
# ─────────────────────────────────────────────
st.markdown("---")
st.markdown("### 💰 Visão Geral do Espelho")

# 6 blocos de categorias
col1, col2, col3 = st.columns(3)

with col1:
    st.markdown(f"""
    <div class="bloco">
      <div class="bloco-title"><span class="tag tag-voz">VOZ</span> Comissão Básica</div>
      <div class="valor-g azul">{fmt(res['voz_valor'])}</div>
      <div class="label-sm">{res['voz_linhas']} acessos · Receita: {fmt(res['voz_receita'])}</div>
      <div class="label-sm" style="margin-top:4px">
        🆕 Novo: {fmt(res['voz_novo'])} &nbsp;|&nbsp; ➕ Aditivo: {fmt(res['voz_aditivo'])}
      </div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="bloco">
      <div class="bloco-title"><span class="tag tag-ren">RENEGOCIAÇÃO</span> Pós-venda</div>
      <div class="valor-g laranja">{fmt(res['ren_valor'])}</div>
      <div class="label-sm">{res['ren_linhas']} acessos · Receita: {fmt(res['ren_receita'])}</div>
      <div class="label-sm" style="margin-top:4px; color:#555">Tratamento separado — não compõe meta VOZ</div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    fibra_label = fmt(res['fibra_liquido']) if res.get('fibra_linhas',0) else "—"
    st.markdown(f"""
    <div class="bloco">
      <div class="bloco-title"><span class="tag tag-fibra">FIBRA</span> Banda Larga</div>
      <div class="valor-g verde">{fibra_label}</div>
      <div class="label-sm">Bruto: {fmt(res['fibra_valor'])} · Estorno: {fmt(res['fibra_estorno'])}</div>
    </div>
    """, unsafe_allow_html=True)

col4, col5, col6 = st.columns(3)

with col4:
    st.markdown(f"""
    <div class="bloco">
      <div class="bloco-title"><span class="tag tag-bq">BÔNUS QUALIDADE</span> M7 / M14</div>
      <div class="valor-g amarelo">{fmt(res['bq_total'])}</div>
      <div class="label-sm">
        M7 (210d): {fmt(res['bq_m7_valor'])} · {res['bq_m7_linhas']} linhas<br>
        M14 (420d): {fmt(res['bq_m14_valor'])} · {res['bq_m14_linhas']} linhas
      </div>
    </div>
    """, unsafe_allow_html=True)

with col5:
    pct_q = f"{res['pct_qualidade']:.0f}%" if res.get('pct_qualidade') else "—"
    st.markdown(f"""
    <div class="bloco">
      <div class="bloco-title"><span class="tag tag-bm">BÔNUS META</span> Corporate</div>
      <div class="valor-g roxo">{fmt(res['bm_valor'])}</div>
      <div class="label-sm">{res['bm_linhas_elegiveis']} linhas elegíveis</div>
      <div class="label-sm" style="margin-top:4px">% Qualidade: {pct_q}</div>
    </div>
    """, unsafe_allow_html=True)

with col6:
    st.markdown(f"""
    <div class="bloco">
      <div class="bloco-title"><span class="tag tag-be">BÔNUS ESTRUTURA</span> CLTs</div>
      <div class="valor-g verde">{fmt(res['be_valor'])}</div>
      <div class="label-sm">{res['be_linhas']} lançamento(s) · Valor global único</div>
    </div>
    """, unsafe_allow_html=True)

# Total bar
st.markdown(f"""
<div class="total-bar">
  <div>
    <div style="font-size:.8rem;color:#8b949e;text-transform:uppercase;letter-spacing:1px">
      Total do Espelho — {res['mes_label']}/{res['ano']}
    </div>
    <div style="font-size:2rem;font-weight:700;color:#2ec4b6;font-family:monospace;margin-top:4px">
      {fmt(res['total'])}
    </div>
    <div style="font-size:.78rem;color:#8b949e;margin-top:4px">
      VOZ {fmt(res['voz_valor'])} &nbsp;+&nbsp;
      Reneg. {fmt(res['ren_valor'])} &nbsp;+&nbsp;
      BQ {fmt(res['bq_total'])} &nbsp;+&nbsp;
      BM {fmt(res['bm_valor'])} &nbsp;+&nbsp;
      Estrutura {fmt(res['be_valor'])}
    </div>
  </div>
  <div style="text-align:right">
    <div style="font-size:.8rem;color:#8b949e">Custcode</div>
    <div style="font-size:1rem;font-weight:600;color:#fff">{res['custcode']}</div>
    <div style="font-size:.78rem;color:#8b949e">{res['cnpj_parc']}</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# SEÇÃO 2 — COMPARATIVO VOZ (NOVO e ADITIVO separados)
# ─────────────────────────────────────────────
st.markdown("---")
st.markdown("### 🔄 Comparativo VOZ — Dashboard × Espelho")
st.caption("NOVO e ADITIVO com fatores distintos. Renegociação na seção seguinte.")

if dash and "df" in dash:
    meta_atingida = "✅" in atingiu_meta
    calc = calcular_expectativa_voz(dash["df"], classificacao, meta_atingida)
    exp_novo  = calc["exp_novo"]
    exp_adic  = calc["exp_adic"]
    exp_voz   = calc["exp_total"]
    fator_real = (res["voz_valor"] / res["voz_receita"]) if res["voz_receita"] else 0
    diff_val   = res["voz_valor"] - exp_voz
    diff_pct   = (diff_val / exp_voz * 100) if exp_voz else 0

    cenario_label = "fator máximo (meta atingida)" if meta_atingida else "por faixa de receita"
    fator_max_novo = FATORES_FAIXA[classificacao]["NOVO"][-1][1]
    fator_max_adic = FATORES_FAIXA[classificacao]["ADITIVO"][-1][1]

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"""
        <div class="bloco">
          <div class="bloco-title">Expectativa — {classificacao} · {cenario_label}</div>
          <div class="valor-g azul">{fmt(exp_voz)}</div>
          <div class="label-sm" style="margin-top:6px">
            🆕 Novo: {fmt(dash.get('receita_novo',0))} → <b>{fmt(exp_novo)}</b><br>
            ➕ Adic: {fmt(dash.get('receita_adic',0))} → <b>{fmt(exp_adic)}</b>
          </div>
          <div class="label-sm" style="margin-top:4px">
            {dash.get('vol_novo',0)} Novos · {dash.get('vol_aditivo',0)} Aditivos · {calc['linhas']} linhas calculadas
          </div>
          {'<div class="label-sm amarelo">⚡ Fator máximo: Novo '+str(fator_max_novo)+' / Adic '+str(fator_max_adic)+'</div>' if meta_atingida else ''}
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="bloco">
          <div class="bloco-title">Pago TIM — Espelho</div>
          <div class="valor-g verde">{fmt(res['voz_valor'])}</div>
          <div class="label-sm" style="margin-top:6px">
            🆕 Novo pago: <b>{fmt(res['voz_novo'])}</b><br>
            ➕ Adic pago: <b>{fmt(res['voz_aditivo'])}</b>
          </div>
          <div class="label-sm" style="margin-top:4px">Fator médio TIM: {fator_real:.2f} · {res['voz_linhas']} linhas</div>
        </div>
        """, unsafe_allow_html=True)
    with c3:
        cls = "diff-pos" if diff_val >= 0 else "diff-neg"
        cor = "verde" if diff_val >= 0 else "vermelho"
        sinal = "+" if diff_val >= 0 else ""
        st.markdown(f"""
        <div class="{cls}" style="height:100%;min-height:110px;display:flex;
             flex-direction:column;align-items:center;justify-content:center;margin-top:4px">
          <div class="label-sm">TIM pagou vs esperado</div>
          <div class="valor-g {cor}" style="font-size:1.5rem">{sinal}{fmt(diff_val)}</div>
          <div class="label-sm">{sinal}{fmt_pct(diff_pct)}</div>
        </div>
        """, unsafe_allow_html=True)

    # Expander com detalhe por faixa
    with st.expander("📊 Detalhe por faixa de receita"):
        if "df_calc" in calc:
            df_detalhe = calc["df_calc"].copy()
            df_detalhe["cnpj_fmt"] = df_detalhe["cnpj"].apply(fmt_cnpj) if "cnpj" in df_detalhe.columns else ""
            cols = [c for c in ["cnpj_fmt","razao_social","tipo_contratacao","preco_oferta","fator_calc","comissao_calc"] if c in df_detalhe.columns]
            st.dataframe(df_detalhe[cols].rename(columns={
                "cnpj_fmt":"CNPJ","razao_social":"Razão Social",
                "tipo_contratacao":"Tipo","preco_oferta":"Receita (R$)",
                "fator_calc":"Fator","comissao_calc":"Comissão Esp. (R$)"
            }), use_container_width=True, hide_index=True,
            column_config={
                "Receita (R$)":       st.column_config.NumberColumn(format="R$ %.2f"),
                "Comissão Esp. (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
                "Fator":              st.column_config.NumberColumn(format="%.1f"),
            })
else:
    st.info("Dados do dashboard não disponíveis para o mês selecionado.")

# ─────────────────────────────────────────────
# SEÇÃO 2b — RENEGOCIAÇÃO
# ─────────────────────────────────────────────
st.markdown("---")
st.markdown("### 🔁 Comparativo Renegociação — Dashboard × Espelho")
st.caption("Pós-venda / Renegociação com fator próprio.")

if dash:
    rec_reneg  = dash.get("receita_reneg", 0)
    exp_reneg  = rec_reneg * fator_reneg
    diff_reneg = res["ren_valor"] - exp_reneg
    diff_rpct  = (diff_reneg / exp_reneg * 100) if exp_reneg else 0

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"""
        <div class="bloco">
          <div class="bloco-title">Expectativa — Renegociação</div>
          <div class="valor-g laranja">{fmt(exp_reneg)}</div>
          <div class="label-sm">Base: {fmt(rec_reneg)} × {fator_reneg:.1f}</div>
          <div class="label-sm">{dash.get('vol_reneg',0)} acessos renegociados</div>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="bloco">
          <div class="bloco-title">Pago TIM — Renegociação</div>
          <div class="valor-g laranja">{fmt(res['ren_valor'])}</div>
          <div class="label-sm">{res['ren_linhas']} linhas · Receita: {fmt(res['ren_receita'])}</div>
        </div>
        """, unsafe_allow_html=True)
    with c3:
        cls = "diff-pos" if diff_reneg >= 0 else "diff-neg"
        cor = "verde" if diff_reneg >= 0 else "vermelho"
        sinal = "+" if diff_reneg >= 0 else ""
        if rec_reneg == 0:
            st.markdown('<div class="diff-neutro" style="height:100%;min-height:90px;display:flex;flex-direction:column;align-items:center;justify-content:center"><div class="label-sm cinza">Informe a meta de receita<br>de renegociação no dashboard<br>para ver a expectativa</div></div>', unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="{cls}" style="height:100%;min-height:90px;display:flex;
                 flex-direction:column;align-items:center;justify-content:center;margin-top:4px">
              <div class="label-sm">TIM pagou vs esperado</div>
              <div class="valor-g {cor}" style="font-size:1.4rem">{sinal}{fmt(diff_reneg)}</div>
              <div class="label-sm">{sinal}{fmt_pct(diff_rpct)}</div>
            </div>
            """, unsafe_allow_html=True)
else:
    st.info("Dados do dashboard não disponíveis para o mês selecionado.")

# ─────────────────────────────────────────────
# SEÇÃO 2c — BÔNUS META
# ─────────────────────────────────────────────
st.markdown("---")
st.markdown("### 🎯 Bônus Meta Corporate")
st.caption("Pago entre 60% e 110% de atingimento da meta de receita Corporate.")

bm_pago = res["bm_valor"]

if meta_receita > 0:
    # Calcula atingimento implícito: bm_pago / meta_receita * 100
    ating_implicito = (bm_pago / meta_receita * 100) if meta_receita else 0

    # Expectativa: atingimento esperado = 100% → paga 100% da meta
    # Regra TIM: paga entre 60% e 110% do atingimento aplicado sobre a meta
    def calc_bonus_meta(meta: float, pct_ating: float) -> float:
        if pct_ating < 60:
            return 0.0
        pct_pago = min(pct_ating, 110) / 100
        return meta * pct_pago

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"""
        <div class="bloco">
          <div class="bloco-title">Meta Receita Corporate</div>
          <div class="valor-g roxo">{fmt(meta_receita)}</div>
          <div class="label-sm" style="margin-top:6px">
            Paga a partir de 60% de atingimento<br>
            Limite máximo: 110% da meta
          </div>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="bloco">
          <div class="bloco-title">Bônus Meta Pago TIM</div>
          <div class="valor-g roxo">{fmt(bm_pago)}</div>
          <div class="label-sm">Atingimento implícito: {fmt_pct(ating_implicito)}</div>
          <div class="label-sm">{res['bm_linhas_elegiveis']} acessos elegíveis</div>
        </div>
        """, unsafe_allow_html=True)
    with c3:
        # Simula expectativas em diferentes níveis
        st.markdown("**Simulador de Bônus Meta**")
        pct_sim = st.slider("% atingimento simulado", 0, 150, 100, 5, key="sim_meta")
        bm_sim = calc_bonus_meta(meta_receita, pct_sim)
        cor_sim = "verde" if pct_sim >= 60 else "vermelho"
        st.markdown(f"""
        <div class="bloco" style="margin-top:0">
          <div class="label-sm">Se atingir {pct_sim}% da meta:</div>
          <div class="valor-g {cor_sim}" style="font-size:1.3rem">{fmt(bm_sim)}</div>
          <div class="label-sm">{'✅ Elegível' if pct_sim >= 60 else '❌ Abaixo do mínimo (60%)'}</div>
          {'<div class="label-sm amarelo">⚠️ Limitado a 110%</div>' if pct_sim > 110 else ''}
        </div>
        """, unsafe_allow_html=True)
else:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"""
        <div class="bloco">
          <div class="bloco-title">Bônus Meta Pago TIM</div>
          <div class="valor-g roxo">{fmt(bm_pago)}</div>
          <div class="label-sm">{res['bm_linhas_elegiveis']} acessos elegíveis</div>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.info("Informe a **Meta Receita Corporate** na sidebar para ver o simulador e o atingimento implícito.")

# ─────────────────────────────────────────────
# SEÇÃO 3 — CRUZAMENTO POR CNPJ
# ─────────────────────────────────────────────
st.markdown("---")
st.markdown("### 🔍 Cruzamento por CNPJ — VOZ + Renegociação")

# CNPJs do espelho (apenas comissões de venda, positivas)
esp_venda = df_esp[
    df_esp["categoria"].isin(["voz","renegociacao"]) &
    (df_esp["Valor Unitário"] > 0)
].copy()

esp_por_cnpj = (
    esp_venda.groupby("cnpj_norm")
    .agg(
        acessos_esp=("Valor Unitário","count"),
        comissao_esp=("Valor Unitário","sum"),
        receita_esp=("Receita Contratada","sum"),
        tipo_principal=("Tipo de Comissão", lambda x: x.mode()[0] if len(x) else ""),
    )
    .reset_index()
)

cnpjs_esp  = set(esp_por_cnpj["cnpj_norm"].unique()) - {""}

if dash and "df" in dash:
    df_dash_raw = dash["df"].copy()
    if "cnpj_norm" not in df_dash_raw.columns and "cnpj" in df_dash_raw.columns:
        df_dash_raw["cnpj_norm"] = df_dash_raw["cnpj"].apply(norm_cnpj)

    dash_por_cnpj = (
        df_dash_raw.groupby("cnpj_norm")
        .agg(
            acessos_dash=("acessos","sum"),
            receita_dash=("preco_oferta","sum"),
            razao_dash=("razao_social","first"),
        )
        .reset_index()
    )
    dash_por_cnpj["acessos_dash"] = dash_por_cnpj["acessos_dash"].astype(int)
    cnpjs_dash = set(dash_por_cnpj["cnpj_norm"].unique()) - {""}

    em_ambos     = cnpjs_dash & cnpjs_esp
    so_dash      = cnpjs_dash - cnpjs_esp
    so_esp       = cnpjs_esp  - cnpjs_dash

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Clientes no Dashboard",  len(cnpjs_dash))
    c2.metric("Clientes no Espelho",    len(cnpjs_esp))
    c3.metric("✅ Em ambos",            len(em_ambos))
    c4.metric("⚠️ Divergências",        len(so_dash) + len(so_esp))

    # Merge completo
    df_cruzado = dash_por_cnpj.merge(esp_por_cnpj, on="cnpj_norm", how="outer")
    df_cruzado["status"] = df_cruzado.apply(
        lambda r: "✅ Em ambos"
        if pd.notna(r.get("acessos_dash")) and pd.notna(r.get("acessos_esp"))
        else "⚠️ Só no Dashboard"
        if pd.notna(r.get("acessos_dash"))
        else "❓ Só no Espelho",
        axis=1,
    )
    df_cruzado["cnpj_fmt"] = df_cruzado["cnpj_norm"].apply(fmt_cnpj)

    tab1, tab2, tab3 = st.tabs([
        f"Todos ({len(df_cruzado)})",
        f"⚠️ Só no Dashboard — não pagos ({len(so_dash)})",
        f"❓ Só no Espelho — não mapeados ({len(so_esp)})",
    ])

    col_cfg = {
        "status":       st.column_config.TextColumn("Status", width="small"),
        "cnpj_fmt":     st.column_config.TextColumn("CNPJ"),
        "razao_dash":   st.column_config.TextColumn("Razão Social"),
        "acessos_dash": st.column_config.NumberColumn("Acessos Dash", format="%d"),
        "receita_dash": st.column_config.NumberColumn("Receita Dash (R$)", format="R$ %.2f"),
        "acessos_esp":  st.column_config.NumberColumn("Acessos Esp.", format="%d"),
        "comissao_esp": st.column_config.NumberColumn("Comissão TIM (R$)", format="R$ %.2f"),
        "tipo_principal": st.column_config.TextColumn("Tipo"),
    }
    cols_show = ["status","cnpj_fmt","razao_dash","acessos_dash","receita_dash","acessos_esp","comissao_esp","tipo_principal"]
    cols_show = [c for c in cols_show if c in df_cruzado.columns]

    with tab1:
        st.dataframe(df_cruzado[cols_show].sort_values("status"), use_container_width=True, hide_index=True, column_config=col_cfg)
        csv = df_cruzado[cols_show].to_csv(index=False).encode("utf-8")
        st.download_button("⬇ Exportar CSV", csv, "cruzamento_cnpj.csv", "text/csv")
    with tab2:
        if so_dash:
            st.caption("Clientes no Dashboard que **não aparecem no Espelho**. Possíveis causas: churn antes da apuração, não elegível, CNPJ divergente.")
            df_f = df_cruzado[df_cruzado["cnpj_norm"].isin(so_dash)][cols_show]
            st.dataframe(df_f, use_container_width=True, hide_index=True, column_config=col_cfg)
        else:
            st.success("Todos os clientes do Dashboard foram encontrados no Espelho. ✅")
    with tab3:
        if so_esp:
            st.caption("Clientes no Espelho que **não foram encontrados no Dashboard**. Possíveis causas: CNPJ diferente no cadastro, venda de outro custcode.")
            df_e = df_cruzado[df_cruzado["cnpj_norm"].isin(so_esp)][cols_show]
            st.dataframe(df_e, use_container_width=True, hide_index=True, column_config=col_cfg)
        else:
            st.success("Todos os clientes do Espelho foram encontrados no Dashboard. ✅")
else:
    st.info("Selecione o mês correspondente na sidebar para cruzar com o Dashboard.")

# ─────────────────────────────────────────────
# SEÇÃO 4 — DETALHE POR CATEGORIA
# ─────────────────────────────────────────────
st.markdown("---")
st.markdown("### 📋 Detalhe por categoria")

cols_base = ["Tipo de Comissão","Descrição","Plano","Tipo de Venda",
             "cnpj_norm","GSM","Receita Contratada","Fator Elemento","Valor Unitário","Data Ativação"]

def df_cat(cat):
    sub = df_esp[df_esp["categoria"] == cat].copy()
    if "cnpj_norm" in sub.columns:
        sub["CNPJ"] = sub["cnpj_norm"].apply(fmt_cnpj)
    cols = [c for c in cols_base + ["CNPJ"] if c in sub.columns]
    return sub[cols].reset_index(drop=True)

col_num_cfg = {
    "Valor Unitário":      st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f"),
    "Receita Contratada":  st.column_config.NumberColumn("Receita (R$)", format="R$ %.2f"),
    "Fator Elemento":      st.column_config.NumberColumn("Fator", format="%.2f"),
}

tab_voz, tab_ren, tab_bq, tab_bm, tab_be, tab_raw = st.tabs([
    f"🎤 VOZ ({res['voz_linhas']})",
    f"🔁 Renegociação ({res['ren_linhas']})",
    f"⭐ Bônus Qualidade ({res['bq_m7_linhas']+res['bq_m14_linhas']})",
    f"🎯 Bônus Meta",
    f"🏗️ Bônus Estrutura",
    "📄 Raw completo",
])

with tab_voz:
    st.dataframe(df_cat("voz"), use_container_width=True, hide_index=True, column_config=col_num_cfg)

with tab_ren:
    st.caption("Renegociação: receita × fator próprio. Não compõe base de cálculo de meta VOZ.")
    st.dataframe(df_cat("renegociacao"), use_container_width=True, hide_index=True, column_config=col_num_cfg)

with tab_bq:
    bq_df = df_cat("bonus_qualidade")
    c1, c2 = st.columns(2)
    c1.metric("M7 — 210 dias", fmt(res["bq_m7_valor"]), f"{res['bq_m7_linhas']} linhas")
    c2.metric("M14 — 420 dias", fmt(res["bq_m14_valor"]), f"{res['bq_m14_linhas']} linhas")
    st.dataframe(bq_df, use_container_width=True, hide_index=True, column_config=col_num_cfg)

with tab_bm:
    st.metric("Total Receita Bônus Meta Corporate", fmt(res["bm_valor"]))
    st.caption(f"{res['bm_linhas_elegiveis']} acessos elegíveis. O valor total é único por espelho — o campo 'Valor Unitário' é apenas a parcela por acesso.")
    bm_df = df_cat("bonus_meta")
    cols_bm = [c for c in ["Tipo de Comissão","Descrição","CNPJ","GSM","Valor Unitário","Total Receita Bônus Meta"] if c in bm_df.columns]
    st.dataframe(bm_df[cols_bm] if cols_bm else bm_df, use_container_width=True, hide_index=True, column_config=col_num_cfg)

with tab_be:
    st.metric("Bônus Estrutura (CLTs TIM)", fmt(res["be_valor"]))
    st.caption("Valor global único, calculado pela TIM com base na quantidade de vendedores CLT auditados.")
    be_df = df_cat("bonus_estrutura")
    st.dataframe(be_df, use_container_width=True, hide_index=True, column_config=col_num_cfg)

with tab_raw:
    st.dataframe(df_esp, use_container_width=True, hide_index=True)
    csv_raw = df_esp.to_csv(index=False).encode("utf-8")
    st.download_button("⬇ Baixar CSV completo", csv_raw, "espelho_completo.csv", "text/csv")
