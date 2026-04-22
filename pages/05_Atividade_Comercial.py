import streamlit as st
import pandas as pd
from datetime import datetime, date

MESES_PT = {
    '01':'Janeiro','02':'Fevereiro','03':'Março','04':'Abril',
    '05':'Maio','06':'Junho','07':'Julho','08':'Agosto',
    '09':'Setembro','10':'Outubro','11':'Novembro','12':'Dezembro'
}
from data_loader import (
    load_data, apply_filters, get_parceiros,
    load_bko, _s, _to_num, _norm_pedido,
    registrar_acesso
)
from auth import require_login

st.set_page_config(
    page_title="Connect Group | Atividade Comercial",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded"
)

username = require_login("atividade")
registrar_acesso("atividade", username=username)

# ── Temas ────────────────────────────────────────────────────────────────────
TEMAS = {
    "🌙 Escuro": {
        "app_bg":       "#0f1117",
        "app_color":    "#e2e8f0",
        "card_bg":      "#1a1f2e",
        "card_border":  "#2d3748",
        "sidebar_bg":   "#0d0e1f",
        "label_color":  "#94a3b8",
        "value_color":  "#f1f5f9",
        "sub_color":    "#64748b",
        "bar_bg":       "#2d3748",
        "day_label":    "#e2e8f0",
        "details_bg":   "#1a1f2e",
        "details_brd":  "#2d3748",
        "details_clr":  "#e2e8f0",
        "section_clr":  "#6366f1",
        "mini_bg":      "#1a1f2e",
        "mini_border":  "#2d3748",
    },
    "☀️ Claro": {
        "app_bg":       "#f8fafc",
        "app_color":    "#1e293b",
        "card_bg":      "#ffffff",
        "card_border":  "#e2e8f0",
        "sidebar_bg":   "#f1f5f9",
        "label_color":  "#64748b",
        "value_color":  "#0f172a",
        "sub_color":    "#94a3b8",
        "bar_bg":       "#e2e8f0",
        "day_label":    "#334155",
        "details_bg":   "#ffffff",
        "details_brd":  "#e2e8f0",
        "details_clr":  "#1e293b",
        "section_clr":  "#4f46e5",
        "mini_bg":      "#f8fafc",
        "mini_border":  "#e2e8f0",
    },
}

def _aplicar_tema(t: dict):
    st.markdown(f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
  html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}
  .stApp {{ background-color: {t['app_bg']}; color: {t['app_color']}; }}
  .header-atv {{
    background: linear-gradient(135deg, #1e1b4b 0%, #3730a3 50%, #6366f1 100%);
    border-radius: 16px; padding: 28px 36px; margin-bottom: 28px;
    box-shadow: 0 8px 32px rgba(99,102,241,0.3);
    border: 1px solid rgba(255,255,255,0.08);
    display: flex; align-items: center; justify-content: space-between;
  }}
  .header-title {{ font-size: 1.9rem; font-weight: 800; color: #fff; letter-spacing: -0.5px; margin: 0; }}
  .header-sub   {{ font-size: 0.85rem; color: rgba(255,255,255,0.65); margin: 4px 0 0 0; }}
  .header-badge {{ background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.25); border-radius: 20px; padding: 6px 16px; font-size: 0.8rem; color: #fff; font-weight: 600; }}
  .kpi-card {{ background: {t['card_bg']}; border-radius: 14px; padding: 22px 24px; border: 1px solid {t['card_border']}; position: relative; overflow: hidden; margin-bottom: 4px; }}
  .kpi-card::before {{ content:''; position:absolute; top:0; left:0; right:0; height:3px; }}
  .kpi-card.indigo::before {{ background: linear-gradient(90deg, #6366f1, #4f46e5); }}
  .kpi-card.green::before  {{ background: linear-gradient(90deg, #10b981, #059669); }}
  .kpi-card.amber::before  {{ background: linear-gradient(90deg, #f59e0b, #d97706); }}
  .kpi-card.blue::before   {{ background: linear-gradient(90deg, #3b82f6, #1d4ed8); }}
  .kpi-card.red::before    {{ background: linear-gradient(90deg, #ef4444, #dc2626); }}
  .kpi-label {{ font-size: 0.72rem; text-transform: uppercase; letter-spacing: 1px; color: {t['label_color']}; font-weight: 600; margin-bottom: 8px; }}
  .kpi-value {{ font-size: 2.1rem; font-weight: 800; color: {t['value_color']}; line-height: 1; }}
  .kpi-sub   {{ font-size: 0.78rem; color: {t['sub_color']}; margin-top: 6px; }}
  .header-logo {{ height:44px;width:auto;object-fit:contain;mix-blend-mode:multiply;border-radius:6px; }}
  .header-right {{ display:flex;align-items:center;gap:14px; }}
  .section-title {{ font-size:0.75rem; text-transform:uppercase; letter-spacing:1.5px; color:{t['section_clr']}; font-weight:700; margin:24px 0 12px 0; border-left: 3px solid {t['section_clr']}; padding-left: 10px; }}
  .day-bar-wrap {{ margin: 3px 0 8px 0; }}
  .day-label {{ font-size: 0.78rem; color: {t['day_label']}; margin-bottom: 3px; display:flex; justify-content:space-between; }}
  .day-bg    {{ background: {t['bar_bg']}; border-radius: 99px; height: 12px; }}
  .day-fill  {{ height: 12px; border-radius: 99px; }}
  .hoje-badge {{ background: #6366f1; color: #fff; font-size: 0.65rem; font-weight: 700; padding: 1px 6px; border-radius: 4px; margin-left: 6px; }}
  section[data-testid="stSidebar"] {{ background: {t['sidebar_bg']} !important; }}
  details {{ background:{t['details_bg']} !important; border:1px solid {t['details_brd']} !important; border-radius:0 0 10px 10px !important; }}
  details summary {{ color:{t['details_clr']} !important; font-weight:600 !important; }}
</style>""", unsafe_allow_html=True)


def _parse_dates(df: pd.DataFrame, col: str) -> pd.Series:
    """Converte coluna de data para datetime. Aceita YYYY-MM-DD HH:MM:SS ou DD/MM/YYYY."""
    def _normalizar(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        s = str(v).strip()
        if not s:
            return None
        return s
    series = df[col].apply(_normalizar)
    # Tenta formato ISO primeiro (YYYY-MM-DD ...), depois DD/MM/YYYY
    parsed = pd.to_datetime(series, errors="coerce", dayfirst=False)
    # Para os que falharam, tenta dayfirst=True
    mask_nat = parsed.isna() & series.notna()
    if mask_nat.any():
        parsed[mask_nat] = pd.to_datetime(series[mask_nat], errors="coerce", dayfirst=True)
    return parsed


def _bar(valor, maximo, cor="#6366f1", h=12):
    pct = min(int(valor / maximo * 100), 100) if maximo > 0 else 0
    return f'<div class="day-bg"><div class="day-fill" style="width:{pct}%;background:{cor};height:{h}px"></div></div>'


def _render_gestao_vista(df_base, df_mes_atv, df_mes_input, mes_sel, hoje, eh_mes_atual, tema_sel, raw=None, bko=None, parceiro_sel='Todos', lider_sel='Todos'):
    """Visão Gestão à Vista — para impressão e colagem no quadro físico.
    Foco em RECEITA CONTRATADA (preco_oferta), não acessos.
    Meta = meta_individual × nº de vendedores ativos no parceiro filtrado.
    """
    from data_loader import load_colaboradores
    t = TEMAS[tema_sel]

    mes_num, ano_num = int(mes_sel[:2]), int(mes_sel[3:])
    nome_mes = MESES_PT.get(f"{mes_num:02d}", mes_sel)
    agora    = datetime.now().strftime("%d/%m/%Y às %H:%M")

    st.markdown(f"""
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:18px">
      <div>
        <p style="font-size:1.25rem;font-weight:800;color:#f1f5f9;margin:0">
          🖨️ GESTÃO À VISTA — {nome_mes.upper()} {ano_num}
        </p>
        <p style="font-size:0.78rem;color:#64748b;margin:4px 0 0 0">
          Atualizado em {agora} · Receita Contratada · Para impressão e quadro físico
        </p>
      </div>
      <div>
        <span style="background:#1e3a5f;border:1px solid #3b82f6;border-radius:8px;padding:6px 14px;font-size:0.72rem;color:#93c5fd;font-weight:600">
          🔴 &lt;70% · 🟡 70–89% · 🟢 ≥90%
        </span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Garante coluna preco_oferta existe ──────────────────────────────────
    for df in [df_mes_atv, df_mes_input, df_base]:
        if "preco_oferta" not in df.columns:
            df["preco_oferta"] = 0.0
        if "vendedor_real" not in df.columns:
            df["vendedor_real"] = "Sem Vendedor"
        if "lider" not in df.columns:
            df["lider"] = "Sem Equipe"

    # ── Carrega meta individual da planilha Colaboradores ───────────────────
    # meta_individual é o valor por vendedor (ex: R$ 850)
    meta_individual = 0.0
    metas_por_vendedor = {}  # fallback por nome se quiser metas diferentes por pessoa
    colab = None
    try:
        colab = load_colaboradores()
        if not colab.empty:
            for _, row in colab.iterrows():
                nome_v = _s(row.get("vendedor", row.get("nome", "")))
                meta_v = _to_num(row.get("meta", row.get("meta_receita", row.get("meta_acessos", 0))))
                if nome_v and meta_v:
                    metas_por_vendedor[nome_v.upper()] = meta_v
            # Usa a meta mais comum como padrão individual
            if metas_por_vendedor:
                from collections import Counter
                meta_individual = Counter(metas_por_vendedor.values()).most_common(1)[0][0]
    except Exception:
        pass

    # ── Usa apply_filters — mesma fonte de verdade da Performance ──────────────
    # Garante NOVO/ADITIVO, sem CANCELADO, filtra parceiro, gera mes_ativacao
    from data_loader import apply_filters as _apply_filters
    mes_alvo_str = mes_sel  # ex: "04/2026"

    if raw is None or raw.empty:
        st.info("Dados brutos não disponíveis para Gestão à Vista.")
        return

    df_gav = _apply_filters(raw.copy(), mes_alvo_str, ["NOVO", "ADITIVO"], parceiro_sel)

    # Join com BKO para ter vendedor_real e lider
    if not bko.empty and "pedido" in df_gav.columns:
        bk_gav = bko.copy()
        df_gav["pedido"]  = df_gav["pedido"].apply(_norm_pedido)
        bk_gav["pedido"]  = bk_gav["pedido"].apply(_norm_pedido)
        df_gav = df_gav.merge(bk_gav[["pedido","vendedor_real","lider"]], on="pedido", how="left")
        df_gav["vendedor_real"] = df_gav["vendedor_real"].apply(lambda x: _s(x) if _s(x) else "Sem Vendedor")
        df_gav["lider"]         = df_gav["lider"].apply(lambda x: _s(x) if _s(x) else "Sem Equipe")
    else:
        df_gav["vendedor_real"] = "Sem Vendedor"
        df_gav["lider"]         = "Sem Equipe"

    # Aplica filtro de líder se selecionado
    if lider_sel != "Todos":
        df_gav = df_gav[df_gav["lider"] == lider_sel]

    # ── Real Ativado: pedidos com mes_ativacao == mês selecionado ────────────
    # Deduplica por pedido (mesmo pedido pode ter múltiplas linhas)
    df_atv_gav = df_gav[df_gav["mes_ativacao"] == mes_alvo_str].copy()
    if "pedido" in df_atv_gav.columns:
        df_atv_gav = (
            df_atv_gav.groupby(["pedido", "vendedor_real", "lider"], as_index=False)
            .agg(preco_oferta=("preco_oferta", "sum"))
        )

    atv_por_vend = (
        df_atv_gav.groupby(["vendedor_real", "lider"])
        .agg(real_ativo=("preco_oferta", "sum"))
        .reset_index()
    )

    # ── Tramitando: mes_ativacao nulo (pipeline) ─────────────────────────────
    df_tram = df_gav[df_gav["mes_ativacao"].isna()].copy()

    tram_por_vend = (
        df_tram.groupby(["vendedor_real", "lider"])
        .agg(tramitando=("preco_oferta", "sum"))
        .reset_index()
    )

    # ── Base: TODOS os vendedores do Colaboradores (incluindo zerados) ─────────
    # Filtra pelo parceiro: só entra lider que aparece no df_gav (já filtrado pelo parceiro)
    if metas_por_vendedor and colab is not None and not colab.empty:
        # Descobre quais líderes pertencem ao parceiro filtrado
        lideres_do_parceiro = set(df_gav["lider"].dropna().unique()) if not df_gav.empty else set()
        # Remove "Sem Equipe" do conjunto
        lideres_do_parceiro.discard("Sem Equipe")

        base_colab = colab[["vendedor", "lider"]].copy()
        base_colab = base_colab.rename(columns={"vendedor": "vendedor_real"})
        # Mantém só vendedores cujo líder pertence ao parceiro filtrado
        if lideres_do_parceiro:
            base_colab = base_colab[base_colab["lider"].isin(lideres_do_parceiro)].copy()
        # Aplica filtro de líder se selecionado
        if lider_sel != "Todos":
            base_colab = base_colab[base_colab["lider"] == lider_sel]
        todos_vend = base_colab.drop_duplicates(subset=["vendedor_real"])
    else:
        # Fallback: usa só quem tem pedido
        vend_atv = df_atv_gav[["vendedor_real","lider"]].drop_duplicates() if not df_atv_gav.empty else pd.DataFrame()
        vend_pip = df_tram[["vendedor_real","lider"]].drop_duplicates() if not df_tram.empty else pd.DataFrame()
        todos_vend = pd.concat([vend_atv, vend_pip]).drop_duplicates(subset=["vendedor_real"])

    tabela = todos_vend.merge(atv_por_vend, on=["vendedor_real", "lider"], how="left")
    tabela = tabela.merge(tram_por_vend[["vendedor_real", "tramitando"]], on="vendedor_real", how="left")
    tabela["real_ativo"] = tabela["real_ativo"].fillna(0.0)
    tabela["tramitando"] = tabela["tramitando"].fillna(0.0)
    tabela["projecao"]   = tabela["real_ativo"] + tabela["tramitando"]

    # Remove linhas sem vendedor
    tabela = tabela[~tabela["vendedor_real"].isin(["Sem Vendedor", ""])].copy()

    if tabela.empty:
        st.info("Nenhum dado disponível para o período selecionado.")
        return

    # ── Meta por vendedor = meta_individual (ou específica se houver) ───────
    # Meta TOTAL = meta_individual × nº de vendedores presentes no filtro atual
    n_vendedores = len(tabela)
    tabela["meta"] = tabela["vendedor_real"].apply(
        lambda v: metas_por_vendedor.get(_s(v).upper(), meta_individual)
    )
    # Meta total correta: soma das metas individuais dos vendedores filtrados
    # (se todos têm a mesma meta → meta_individual × n_vendedores)
    total_meta = tabela["meta"].sum()

    # % atingimento individual
    def _pct(row):
        if row["meta"] <= 0:
            return None
        return round(row["real_ativo"] / row["meta"] * 100, 1)

    tabela["pct_ating"] = tabela.apply(_pct, axis=1)

    # Semáforo — vermelho = longe da meta (ruim), verde = batendo (bom)
    def _status(row):
        if row["meta"] <= 0 or row["pct_ating"] is None:
            return "⚪", "#64748b"
        p = row["pct_ating"]
        if p >= 90:   return "🟢", "#10b981"
        elif p >= 70: return "🟡", "#f59e0b"
        else:         return "🔴", "#ef4444"

    tabela["_semaforo"], tabela["_cor_pct"] = zip(*tabela.apply(_status, axis=1))

    # Ordena: maior real_ativo primeiro (dentro do líder se agrupado)
    tabela = tabela.sort_values(["real_ativo"], ascending=[False]).reset_index(drop=True)

    # ── KPIs gerais ─────────────────────────────────────────────────────────
    total_ativo = tabela["real_ativo"].sum()
    total_tram  = tabela["tramitando"].sum()
    total_proj  = total_ativo + total_tram
    pct_geral   = round(total_ativo / total_meta * 100, 1) if total_meta > 0 else 0

    def _fmt_r(v): return f"R$ {v:,.2f}"

    g1, g2, g3, g4, g5 = st.columns(5)
    _mini = lambda bg, lbl, val, sub="": f"""<div style="background:{bg};border-radius:10px;padding:12px 16px;border:1px solid #2d3748;margin-bottom:12px">
      <div style="font-size:0.65rem;color:#94a3b8;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px">{lbl}</div>
      <div style="font-size:1.35rem;font-weight:800;color:#f1f5f9;line-height:1.2">{val}</div>
      {"<div style='font-size:0.68rem;color:#64748b;margin-top:4px'>" + sub + "</div>" if sub else ""}
    </div>"""

    with g1: st.markdown(_mini("#1e1b4b", f"🎯 Meta Total ({n_vendedores} vend.)", _fmt_r(total_meta), f"R$ {meta_individual:,.2f} × {n_vendedores}"), unsafe_allow_html=True)
    with g2: st.markdown(_mini("#064e3b", "✅ Real Ativado", _fmt_r(total_ativo), "receita contratada"), unsafe_allow_html=True)
    with g3: st.markdown(_mini("#1e3a5f", "🔄 Tramitando", _fmt_r(total_tram), "pipeline sem ativação"), unsafe_allow_html=True)
    with g4: st.markdown(_mini("#1c1917", "📈 Projeção", _fmt_r(total_proj), "ativo + tramitando"), unsafe_allow_html=True)
    with g5:
        cor_geral = "#ef4444" if pct_geral < 70 else ("#f59e0b" if pct_geral < 90 else "#10b981")
        st.markdown(f"""<div style="background:#0f1117;border-radius:10px;padding:12px 16px;border:2px solid {cor_geral};margin-bottom:12px">
          <div style="font-size:0.65rem;color:#94a3b8;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px">⚡ % Atingimento</div>
          <div style="font-size:1.35rem;font-weight:800;color:{cor_geral};line-height:1.2">{pct_geral:.1f}%</div>
          <div style="font-size:0.68rem;color:#64748b;margin-top:4px">real / meta</div>
        </div>""", unsafe_allow_html=True)

    # ── Opções de tabela ────────────────────────────────────────────────────
    col_opt1, col_opt2 = st.columns([3, 1])
    with col_opt2:
        agrupar = st.checkbox("Agrupar por Líder", value=True, key="gav_agrupar")

    # ── CSS ─────────────────────────────────────────────────────────────────
    st.markdown("""
    <style>
      @media print {
        section[data-testid="stSidebar"], [data-testid="stHeader"],
        button, .stRadio, .stCheckbox, .stSelectbox { display: none !important; }
        .gav-table { font-size: 11px !important; }
      }
      .gav-table { border-collapse: collapse; width: 100%; font-family: 'Inter', sans-serif; }
      .gav-table th {
        background: #1e1b4b; color: #c7d2fe; font-size: 0.7rem;
        text-transform: uppercase; letter-spacing: 1px; padding: 10px 14px;
        text-align: left; border-bottom: 2px solid #6366f1; font-weight: 700;
      }
      .gav-table td { padding: 10px 14px; font-size: 0.82rem; border-bottom: 1px solid #1e293b; color: #e2e8f0; vertical-align: middle; }
      .gav-table tr:hover td { background: #1a1f2e; }
      .gav-lider-row td {
        background: #1e293b !important; color: #93c5fd !important;
        font-weight: 700; font-size: 0.75rem; text-transform: uppercase;
        letter-spacing: 1px; padding: 6px 14px; border-top: 2px solid #334155;
      }
      .gav-total-row td { background: #1e1b4b !important; color: #c7d2fe !important; font-weight: 800; border-top: 2px solid #6366f1; }
      .pct-badge { display: inline-block; border-radius: 6px; padding: 2px 8px; font-size: 0.75rem; font-weight: 700; min-width: 52px; text-align: center; }
      .bar-mini { height: 6px; border-radius: 3px; background: #1e293b; }
      .bar-mini-fill { height: 6px; border-radius: 3px; }
    </style>
    """, unsafe_allow_html=True)

    def _pct_badge(pct, meta):
        if meta <= 0 or pct is None:
            return "<span style='color:#475569'>—</span>"
        p = float(pct)
        if p >= 90:   bg, clr = "#022c22", "#34d399"   # verde — batendo meta
        elif p >= 70: bg, clr = "#451a03", "#fbbf24"   # amarelo — no caminho
        else:         bg, clr = "#450a0a", "#f87171"   # vermelho — longe
        return f"<span class='pct-badge' style='background:{bg};color:{clr}'>{p:.1f}%</span>"

    def _minibar(val, meta, cor):
        if meta <= 0: return ""
        pct = min(int(val / meta * 100), 100)
        return f"<div class='bar-mini'><div class='bar-mini-fill' style='width:{pct}%;background:{cor}'></div></div>"

    # ── Monta HTML ──────────────────────────────────────────────────────────
    html = """<div style='overflow-x:auto'><table class='gav-table'>
    <thead><tr>
      <th>Vendedor</th>
      <th>Líder / Equipe</th>
      <th style='text-align:right'>Meta (R$)</th>
      <th style='text-align:right'>✅ Real Ativado</th>
      <th style='text-align:right'>🔄 Tramitando</th>
      <th style='text-align:right'>📈 Projeção</th>
      <th style='text-align:center'>% Atingimento</th>
      <th style='text-align:center'>Status</th>
    </tr></thead><tbody>"""

    lideres_vistos = set()

    for _, row in tabela.iterrows():
        lider_nome = row["lider"] or "Sem Equipe"
        vend  = row["vendedor_real"]
        meta  = row["meta"]
        real  = row["real_ativo"]
        tram  = row["tramitando"]
        proj  = row["projecao"]
        semaf = row["_semaforo"]
        pct   = row["pct_ating"]
        badge = _pct_badge(pct, meta)
        bar_real = _minibar(real, meta, "#10b981")
        bar_proj = _minibar(proj, meta, "#6366f1")

        if agrupar and lider_nome not in lideres_vistos:
            lideres_vistos.add(lider_nome)
            grp    = tabela[tabela["lider"] == lider_nome]
            g_meta = grp["meta"].sum()
            g_real = grp["real_ativo"].sum()
            g_tram = grp["tramitando"].sum()
            g_proj = g_real + g_tram
            g_n    = len(grp)
            g_pct  = f"{g_real/g_meta*100:.1f}%" if g_meta > 0 else "—"
            html += f"""<tr class='gav-lider-row'>
              <td colspan='2'>👥 {lider_nome} &nbsp;<span style='font-weight:400;font-size:0.7rem;color:#64748b'>({g_n} vendedor{'es' if g_n > 1 else ''})</span></td>
              <td style='text-align:right'>R$ {g_meta:,.2f}</td>
              <td style='text-align:right'>R$ {g_real:,.2f}</td>
              <td style='text-align:right'>R$ {g_tram:,.2f}</td>
              <td style='text-align:right'>R$ {g_proj:,.2f}</td>
              <td style='text-align:center'>{g_pct}</td>
              <td></td>
            </tr>"""

        meta_txt = f"R$ {meta:,.2f}" if meta > 0 else "—"
        html += f"""<tr>
          <td><span style='font-weight:600'>{vend}</span></td>
          <td style='color:#94a3b8;font-size:0.75rem'>{lider_nome}</td>
          <td style='text-align:right;color:#94a3b8'>{meta_txt}</td>
          <td style='text-align:right'>
            <span style='font-weight:700;font-size:0.95rem;color:#34d399'>R$ {real:,.2f}</span>
            <div style='margin-top:3px'>{bar_real}</div>
          </td>
          <td style='text-align:right;color:#60a5fa;font-weight:600'>R$ {tram:,.2f}</td>
          <td style='text-align:right'>
            <span style='font-weight:700;color:#a78bfa'>R$ {proj:,.2f}</span>
            <div style='margin-top:3px'>{bar_proj}</div>
          </td>
          <td style='text-align:center'>{badge}</td>
          <td style='text-align:center;font-size:1.1rem'>{semaf}</td>
        </tr>"""

    pct_geral_txt = f"{pct_geral:.1f}%" if total_meta > 0 else "—"
    html += f"""<tr class='gav-total-row'>
      <td colspan='2'>🏁 TOTAL GERAL ({n_vendedores} vendedores)</td>
      <td style='text-align:right'>R$ {total_meta:,.2f}</td>
      <td style='text-align:right'>R$ {total_ativo:,.2f}</td>
      <td style='text-align:right'>R$ {total_tram:,.2f}</td>
      <td style='text-align:right'>R$ {total_proj:,.2f}</td>
      <td style='text-align:center'>{pct_geral_txt}</td>
      <td style='text-align:center'>{'🟢' if pct_geral >= 90 else ('🟡' if pct_geral >= 70 else '🔴')}</td>
    </tr>"""

    html += "</tbody></table></div>"

    st.markdown(html, unsafe_allow_html=True)

    # ── Tabela por Líder ────────────────────────────────────────────────────
    st.markdown("""
    <div style='margin-top:32px;margin-bottom:10px;display:flex;align-items:center;gap:10px'>
      <div style='height:2px;flex:1;background:linear-gradient(90deg,#6366f1,transparent)'></div>
      <span style='font-size:0.72rem;text-transform:uppercase;letter-spacing:2px;color:#6366f1;font-weight:700'>Consolidado por Líder</span>
      <div style='height:2px;flex:1;background:linear-gradient(270deg,#6366f1,transparent)'></div>
    </div>
    """, unsafe_allow_html=True)

    # Agrupa por líder
    lideres_tab = (
        tabela.groupby("lider")
        .agg(
            n_vendedores=("vendedor_real", "count"),
            meta=("meta", "sum"),
            real_ativo=("real_ativo", "sum"),
            tramitando=("tramitando", "sum"),
        )
        .reset_index()
    )
    lideres_tab["projecao"]  = lideres_tab["real_ativo"] + lideres_tab["tramitando"]
    lideres_tab["pct_ating"] = lideres_tab.apply(
        lambda r: round(r["real_ativo"] / r["meta"] * 100, 1) if r["meta"] > 0 else None, axis=1
    )
    lideres_tab = lideres_tab.sort_values("real_ativo", ascending=False).reset_index(drop=True)

    html_l = """<div style='overflow-x:auto'><table class='gav-table'>
    <thead><tr>
      <th>Líder / Equipe</th>
      <th style='text-align:center'>Vendedores</th>
      <th style='text-align:right'>Meta (R$)</th>
      <th style='text-align:right'>✅ Real Ativado</th>
      <th style='text-align:right'>🔄 Tramitando</th>
      <th style='text-align:right'>📈 Projeção</th>
      <th style='text-align:center'>% Atingimento</th>
      <th style='text-align:center'>Status</th>
    </tr></thead><tbody>"""

    for _, row in lideres_tab.iterrows():
        lnome = row["lider"] or "Sem Equipe"
        l_n   = int(row["n_vendedores"])
        l_meta = row["meta"]
        l_real = row["real_ativo"]
        l_tram = row["tramitando"]
        l_proj = row["projecao"]
        l_pct  = row["pct_ating"]

        l_badge = _pct_badge(l_pct, l_meta)
        l_bar_real = _minibar(l_real, l_meta, "#10b981")
        l_bar_proj = _minibar(l_proj, l_meta, "#6366f1")

        if l_pct is None:    l_semaf = "⚪"
        elif l_pct >= 90:    l_semaf = "🟢"
        elif l_pct >= 70:    l_semaf = "🟡"
        else:                l_semaf = "🔴"

        meta_txt = f"R$ {l_meta:,.2f}" if l_meta > 0 else "—"
        html_l += f"""<tr>
          <td><span style='font-weight:700;font-size:0.9rem'>{lnome}</span></td>
          <td style='text-align:center;color:#94a3b8'>{l_n} vendedor{'es' if l_n > 1 else ''}</td>
          <td style='text-align:right;color:#94a3b8'>{meta_txt}</td>
          <td style='text-align:right'>
            <span style='font-weight:700;font-size:0.95rem;color:#34d399'>R$ {l_real:,.2f}</span>
            <div style='margin-top:3px'>{l_bar_real}</div>
          </td>
          <td style='text-align:right;color:#60a5fa;font-weight:600'>R$ {l_tram:,.2f}</td>
          <td style='text-align:right'>
            <span style='font-weight:700;color:#a78bfa'>R$ {l_proj:,.2f}</span>
            <div style='margin-top:3px'>{l_bar_proj}</div>
          </td>
          <td style='text-align:center'>{l_badge}</td>
          <td style='text-align:center;font-size:1.1rem'>{l_semaf}</td>
        </tr>"""

    # Total geral na tabela de líderes
    html_l += f"""<tr class='gav-total-row'>
      <td>🏁 TOTAL GERAL</td>
      <td style='text-align:center'>{n_vendedores}</td>
      <td style='text-align:right'>R$ {total_meta:,.2f}</td>
      <td style='text-align:right'>R$ {total_ativo:,.2f}</td>
      <td style='text-align:right'>R$ {total_tram:,.2f}</td>
      <td style='text-align:right'>R$ {total_proj:,.2f}</td>
      <td style='text-align:center'>{pct_geral_txt}</td>
      <td style='text-align:center'>{'🟢' if pct_geral >= 90 else ('🟡' if pct_geral >= 70 else '🔴')}</td>
    </tr>"""

    html_l += "</tbody></table></div>"

    st.markdown(html_l, unsafe_allow_html=True)

    html_footer = f"""<div style='margin-top:16px;padding:10px 16px;background:#0f1117;border-radius:8px;
      border:1px solid #1e293b;display:flex;justify-content:space-between;align-items:center'>
      <span style='font-size:0.7rem;color:#475569'>🖨️ Connect Group · TIM Empresas · Gerado em {agora}</span>
      <span style='font-size:0.7rem;color:#475569'>Período: {nome_mes} {ano_num} · Receita Contratada · Gestão à Vista</span>
    </div>"""

    st.markdown(html_footer, unsafe_allow_html=True)

    st.markdown("""
    <div style='margin-top:14px;padding:10px 16px;background:#1e3a2e;border-radius:8px;
      border:1px solid #065f46;font-size:0.78rem;color:#6ee7b7'>
      💡 <strong>Para imprimir:</strong> use <kbd>Ctrl+P</kbd> e selecione orientação <strong>paisagem</strong>.
    </div>
    """, unsafe_allow_html=True)

    # ── Envio manual por Telegram ────────────────────────────────────────────
    st.markdown("")
    st.markdown('<p class="section-title">📤 Enviar por Telegram</p>', unsafe_allow_html=True)

    col_tg1, col_tg2 = st.columns([3, 1])
    with col_tg1:
        try:
            _default_ids = st.secrets.get("telegram_gestao", {}).get("chat_ids", "")
        except Exception:
            _default_ids = ""
        chat_ids_input = st.text_input(
            "Chat IDs (separados por vírgula)",
            value=_default_ids,
            placeholder="123456789,987654321",
            help="Seu chat_id e do gerente. Envie qualquer msg pro bot e acesse: api.telegram.org/bot<TOKEN>/getUpdates",
            key="gav_chat_ids"
        )
    with col_tg2:
        st.markdown("<div style='margin-top:28px'>", unsafe_allow_html=True)
        enviar_tg = st.button("📤 Enviar PDF", type="primary", use_container_width=True, key="gav_enviar_tg")
        st.markdown("</div>", unsafe_allow_html=True)

    if enviar_tg:
        chat_ids = [c.strip() for c in chat_ids_input.split(",") if c.strip()]
        if not chat_ids:
            st.warning("Informe ao menos um Chat ID.")
        else:
            with st.spinner("Gerando PDF e enviando..."):
                try:
                    import io
                    import requests as _req
                    from reportlab.lib import colors as _rc
                    from reportlab.lib.pagesizes import A4, landscape as _ls
                    from reportlab.lib.styles import ParagraphStyle as _PS
                    from reportlab.lib.units import cm
                    from reportlab.platypus import (
                        SimpleDocTemplate, Table, TableStyle,
                        Paragraph, Spacer, HRFlowable
                    )
                    from data_loader import load_colaboradores as _lc2, apply_filters as _af2

                    # ── Recalcula dados usando a mesma lógica da tela ────────
                    _df_g = _af2(raw.copy(), mes_sel, ["NOVO", "ADITIVO"], parceiro_sel)
                    if not bko.empty and "pedido" in _df_g.columns:
                        _bk = bko.copy()
                        _df_g["pedido"] = _df_g["pedido"].apply(_norm_pedido)
                        _bk["pedido"]   = _bk["pedido"].apply(_norm_pedido)
                        _df_g = _df_g.merge(_bk[["pedido","vendedor_real","lider"]], on="pedido", how="left")
                        _df_g["vendedor_real"] = _df_g["vendedor_real"].apply(lambda x: _s(x) or "Sem Vendedor")
                        _df_g["lider"]         = _df_g["lider"].apply(lambda x: _s(x) or "Sem Equipe")
                    if lider_sel != "Todos":
                        _df_g = _df_g[_df_g["lider"] == lider_sel]

                    _atv = _df_g[_df_g["mes_ativacao"] == mes_sel].copy()
                    if "pedido" in _atv.columns:
                        _atv = _atv.groupby(["pedido","vendedor_real","lider"], as_index=False).agg(preco_oferta=("preco_oferta","sum"))
                    _atv_pv = _atv.groupby(["vendedor_real","lider"]).agg(real_ativo=("preco_oferta","sum")).reset_index()

                    _trm = _df_g[_df_g["mes_ativacao"].isna()].copy()
                    _trm_pv = _trm.groupby(["vendedor_real","lider"]).agg(tramitando=("preco_oferta","sum")).reset_index()

                    _col2  = _lc2()
                    _metas2 = dict(zip(_col2["vendedor"].str.upper(), _col2["meta"])) if not _col2.empty else {}

                    # Base = Colaboradores filtrado pelos líderes do parceiro (inclui zerados)
                    if _metas2 and not _col2.empty:
                        _lideres_parc = set(_df_g["lider"].dropna().unique()) - {"Sem Equipe"}
                        _base = _col2[["vendedor","lider"]].copy().rename(columns={"vendedor":"vendedor_real"})
                        if _lideres_parc:
                            _base = _base[_base["lider"].isin(_lideres_parc)].copy()
                        if lider_sel != "Todos":
                            _base = _base[_base["lider"] == lider_sel]
                        _todos = _base.drop_duplicates(subset=["vendedor_real"])
                    else:
                        _todos = pd.concat([
                            _atv[["vendedor_real","lider"]].drop_duplicates(),
                            _trm[["vendedor_real","lider"]].drop_duplicates(),
                        ]).drop_duplicates(subset=["vendedor_real"])
                        _todos = _todos[~_todos["vendedor_real"].isin(["Sem Vendedor",""])].copy()

                    tv = _todos.merge(_atv_pv, on=["vendedor_real","lider"], how="left")
                    tv = tv.merge(_trm_pv[["vendedor_real","tramitando"]], on="vendedor_real", how="left")
                    tv["real_ativo"] = tv["real_ativo"].fillna(0.0)
                    tv["tramitando"] = tv["tramitando"].fillna(0.0)
                    tv["projecao"]   = tv["real_ativo"] + tv["tramitando"]
                    tv["meta"] = tv["vendedor_real"].apply(lambda v: _metas2.get(_s(v).upper(), 850.0))
                    tv["pct"]  = tv.apply(lambda r: round(r["real_ativo"]/r["meta"]*100,1) if r["meta"]>0 else None, axis=1)
                    tv = tv.sort_values("real_ativo", ascending=False).reset_index(drop=True)

                    tl = tv.groupby("lider").agg(
                        n=("vendedor_real","count"), meta=("meta","sum"),
                        real_ativo=("real_ativo","sum"), tramitando=("tramitando","sum")
                    ).reset_index()
                    tl["projecao"] = tl["real_ativo"] + tl["tramitando"]
                    tl["pct"] = tl.apply(lambda r: round(r["real_ativo"]/r["meta"]*100,1) if r["meta"]>0 else None, axis=1)
                    tl = tl.sort_values("real_ativo", ascending=False).reset_index(drop=True)

                    t_meta  = tv["meta"].sum()
                    t_ativo = tv["real_ativo"].sum()
                    t_tram  = tv["tramitando"].sum()
                    t_proj  = t_ativo + t_tram
                    pct_g   = round(t_ativo/t_meta*100,1) if t_meta > 0 else 0
                    n_v     = len(tv)

                    # ── Helpers ──────────────────────────────────────────────
                    def _fr(v): return f"R$ {v:,.2f}".replace(",","X").replace(".",",").replace("X",".")
                    def _sm(p):
                        if p is None: return "⚪"
                        return "🟢" if p>=90 else ("🟡" if p>=70 else "🔴")
                    def _cp(p):
                        if p is None: return _rc.HexColor("#94a3b8")
                        return (_rc.HexColor("#34d399") if p>=90 else (_rc.HexColor("#fbbf24") if p>=70 else _rc.HexColor("#f87171")))

                    CH = _rc.HexColor
                    C = {"hb":CH("#1e1b4b"),"ht":CH("#c7d2fe"),"ra":CH("#0f1117"),"rb":CH("#1a1f2e"),
                         "tb":CH("#1e1b4b"),"tt":CH("#c7d2fe"),"bd":CH("#2d3748"),
                         "vd":CH("#34d399"),"az":CH("#60a5fa"),"rx":CH("#a78bfa"),
                         "tx":CH("#e2e8f0"),"sb":CH("#94a3b8"),"ac":CH("#6366f1")}

                    MESES = {1:"Janeiro",2:"Fevereiro",3:"Março",4:"Abril",5:"Maio",6:"Junho",
                             7:"Julho",8:"Agosto",9:"Setembro",10:"Outubro",11:"Novembro",12:"Dezembro"}
                    nm = MESES.get(mes_num, str(mes_num))
                    ag = datetime.now().strftime("%d/%m/%Y às %H:%M")

                    # ── Gera PDF ─────────────────────────────────────────────
                    buf = io.BytesIO()
                    doc = SimpleDocTemplate(buf, pagesize=_ls(A4),
                        leftMargin=1.2*cm, rightMargin=1.2*cm,
                        topMargin=1.2*cm, bottomMargin=1.2*cm)

                    st_tit = _PS("t", fontSize=15, textColor=_rc.white, fontName="Helvetica-Bold", spaceAfter=3)
                    st_sub = _PS("s", fontSize=7,  textColor=C["sb"],   fontName="Helvetica", spaceAfter=10)
                    st_sec = _PS("sc",fontSize=9,  textColor=C["ht"],   fontName="Helvetica-Bold", spaceBefore=12, spaceAfter=5)
                    st_rod = _PS("r", fontSize=6,  textColor=C["sb"],   fontName="Helvetica", spaceBefore=3)

                    story = []
                    story.append(Paragraph(f"GESTÃO À VISTA — {nm.upper()} {ano_num}", st_tit))
                    story.append(Paragraph(f"Connect Group · TIM Empresas · Receita Contratada · {ag}", st_sub))
                    story.append(HRFlowable(width="100%", thickness=1, color=C["bd"], spaceAfter=8))

                    # KPIs
                    cg = _cp(pct_g)
                    kd = [
                        ["🎯 Meta Total","✅ Real Ativado","🔄 Tramitando","📈 Projeção","⚡ % Atingimento"],
                        [_fr(t_meta),_fr(t_ativo),_fr(t_tram),_fr(t_proj),f"{pct_g:.1f}%"],
                        [f"{n_v} vendedores","receita ativada","pipeline","ativo + pipeline","real / meta"],
                    ]
                    cw = doc.width/5
                    kt = Table(kd, colWidths=[cw]*5, rowHeights=[16,22,12])
                    kt.setStyle(TableStyle([
                        ("BACKGROUND",(0,0),(-1,0),C["hb"]),("TEXTCOLOR",(0,0),(-1,0),C["ht"]),
                        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,0),7),
                        ("BACKGROUND",(0,1),(-1,1),C["rb"]),("TEXTCOLOR",(0,1),(-1,1),_rc.white),
                        ("FONTNAME",(0,1),(-1,1),"Helvetica-Bold"),("FONTSIZE",(0,1),(-1,1),10),
                        ("TEXTCOLOR",(4,1),(4,1),cg),
                        ("BACKGROUND",(0,2),(-1,2),C["ra"]),("TEXTCOLOR",(0,2),(-1,2),C["sb"]),("FONTSIZE",(0,2),(-1,2),6),
                        ("ALIGN",(0,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                        ("BOX",(0,0),(-1,-1),0.5,C["bd"]),("INNERGRID",(0,0),(-1,-1),0.3,C["bd"]),
                        ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
                    ]))
                    story.append(kt)
                    story.append(Spacer(1,10))

                    def _tbl(rows, cws, sx):
                        t = Table(rows, colWidths=cws)
                        t.setStyle(TableStyle([
                            ("BACKGROUND",(0,0),(-1,0),C["hb"]),("TEXTCOLOR",(0,0),(-1,0),C["ht"]),
                            ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,0),7),
                            ("ALIGN",(0,0),(-1,0),"CENTER"),
                            ("BOX",(0,0),(-1,-1),0.5,C["bd"]),("INNERGRID",(0,0),(-1,-1),0.3,C["bd"]),
                            ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
                            ("FONTSIZE",(0,1),(-1,-1),8),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                        ] + sx))
                        return t

                    # Tabela vendedores
                    story.append(Paragraph("👤  Por Vendedor", st_sec))
                    cw_v = [6.5*cm,3.5*cm,2.8*cm,2.8*cm,2.8*cm,2.8*cm,2.2*cm,1.5*cm]
                    rv = [["Vendedor","Líder / Equipe","Meta (R$)","✅ Real Ativado","🔄 Tramitando","📈 Projeção","% Ating.","Status"]]
                    sv = []
                    for i, row in tv.iterrows():
                        ri = i+1; bg = C["ra"] if i%2==0 else C["rb"]; p = row["pct"]
                        sv += [("BACKGROUND",(0,ri),(-1,ri),bg),("TEXTCOLOR",(0,ri),(-1,ri),C["tx"]),
                               ("FONTNAME",(0,ri),(0,ri),"Helvetica-Bold"),
                               ("TEXTCOLOR",(3,ri),(3,ri),C["vd"]),("TEXTCOLOR",(4,ri),(4,ri),C["az"]),
                               ("TEXTCOLOR",(5,ri),(5,ri),C["rx"]),("TEXTCOLOR",(6,ri),(6,ri),_cp(p)),
                               ("FONTNAME",(6,ri),(6,ri),"Helvetica-Bold"),("ALIGN",(2,ri),(-1,ri),"RIGHT")]
                        rv.append([row["vendedor_real"],row["lider"],
                                   _fr(row["meta"]) if row["meta"]>0 else "—",
                                   _fr(row["real_ativo"]),_fr(row["tramitando"]),_fr(row["projecao"]),
                                   f"{p:.1f}%" if p is not None else "—",_sm(p)])
                    ri_t = len(rv)
                    sv += [("BACKGROUND",(0,ri_t),(-1,ri_t),C["tb"]),("TEXTCOLOR",(0,ri_t),(-1,ri_t),C["tt"]),
                           ("FONTNAME",(0,ri_t),(-1,ri_t),"Helvetica-Bold"),("ALIGN",(2,ri_t),(-1,ri_t),"RIGHT"),
                           ("LINEABOVE",(0,ri_t),(-1,ri_t),1.5,C["ac"])]
                    rv.append([f"🏁 TOTAL ({n_v} vend.)","",_fr(t_meta),_fr(t_ativo),_fr(t_tram),_fr(t_proj),f"{pct_g:.1f}%",_sm(pct_g)])
                    story.append(_tbl(rv, cw_v, sv))
                    story.append(Spacer(1,14))

                    # Tabela líderes
                    story.append(HRFlowable(width="100%",thickness=1,color=C["ac"],spaceAfter=6))
                    story.append(Paragraph("👥  Consolidado por Líder", st_sec))
                    cw_l = [6*cm,2.5*cm,3.2*cm,3.2*cm,3.2*cm,3.2*cm,2.5*cm,1.5*cm]
                    rl = [["Líder / Equipe","Vendedores","Meta (R$)","✅ Real Ativado","🔄 Tramitando","📈 Projeção","% Ating.","Status"]]
                    sl = []
                    for i, row in tl.iterrows():
                        ri = i+1; bg = C["ra"] if i%2==0 else C["rb"]; p = row["pct"]
                        sl += [("BACKGROUND",(0,ri),(-1,ri),bg),("TEXTCOLOR",(0,ri),(-1,ri),C["tx"]),
                               ("FONTNAME",(0,ri),(0,ri),"Helvetica-Bold"),
                               ("TEXTCOLOR",(3,ri),(3,ri),C["vd"]),("TEXTCOLOR",(4,ri),(4,ri),C["az"]),
                               ("TEXTCOLOR",(5,ri),(5,ri),C["rx"]),("TEXTCOLOR",(6,ri),(6,ri),_cp(p)),
                               ("FONTNAME",(6,ri),(6,ri),"Helvetica-Bold"),("ALIGN",(1,ri),(-1,ri),"RIGHT")]
                        rl.append([row["lider"],f"{int(row['n'])} vend.",
                                   _fr(row["meta"]) if row["meta"]>0 else "—",
                                   _fr(row["real_ativo"]),_fr(row["tramitando"]),_fr(row["projecao"]),
                                   f"{p:.1f}%" if p is not None else "—",_sm(p)])
                    ri_tl = len(rl)
                    sl += [("BACKGROUND",(0,ri_tl),(-1,ri_tl),C["tb"]),("TEXTCOLOR",(0,ri_tl),(-1,ri_tl),C["tt"]),
                           ("FONTNAME",(0,ri_tl),(-1,ri_tl),"Helvetica-Bold"),("ALIGN",(1,ri_tl),(-1,ri_tl),"RIGHT"),
                           ("LINEABOVE",(0,ri_tl),(-1,ri_tl),1.5,C["ac"])]
                    rl.append(["🏁 TOTAL GERAL",f"{n_v}",_fr(t_meta),_fr(t_ativo),_fr(t_tram),_fr(t_proj),f"{pct_g:.1f}%",_sm(pct_g)])
                    story.append(_tbl(rl, cw_l, sl))

                    story.append(Spacer(1,8))
                    story.append(HRFlowable(width="100%",thickness=0.5,color=C["bd"]))
                    story.append(Paragraph(f"Connect Group · TIM Empresas · {nm} {ano_num} · Gerado em {ag}", st_rod))

                    doc.build(story)
                    buf.seek(0)
                    pdf_bytes = buf.getvalue()

                    # ── Envia pelo Telegram ───────────────────────────────────
                    try:
                        token = st.secrets["telegram"]["token"]
                    except Exception:
                        token = ""

                    if not token:
                        st.error("❌ Token do Telegram não encontrado nos secrets.")
                    else:
                        semf_g = _sm(pct_g)
                        caption = (
                            f"{semf_g} *Gestão à Vista — {nm} {ano_num}*\n"
                            f"📊 Ativado: *{_fr(t_ativo)}* de {_fr(t_meta)} ({pct_g:.1f}%)\n"
                            f"_Connect Group · TIM Empresas_"
                        )
                        erros = []
                        for cid in chat_ids:
                            r = _req.post(
                                f"https://api.telegram.org/bot{token}/sendDocument",
                                data={"chat_id": cid, "caption": caption, "parse_mode": "Markdown"},
                                files={"document": (f"gestao_vista_{nm.lower()}_{ano_num}.pdf",
                                                    io.BytesIO(pdf_bytes), "application/pdf")},
                                timeout=30
                            )
                            if r.status_code != 200:
                                erros.append(f"{cid}: {r.text}")
                        if erros:
                            st.error(f"❌ Falha em {len(erros)} envio(s):\n" + "\n".join(erros))
                        else:
                            st.success(f"✅ PDF enviado com sucesso para {len(chat_ids)} destinatário(s)!")

                except ImportError:
                    st.error("❌ Instale a biblioteca `reportlab` no requirements.txt")
                except Exception as e:
                    st.error(f"❌ Erro: {e}")


def main():
    st.markdown("""
    <div class="header-atv">
      <div>
        <p class="header-title">📅 ATIVIDADE COMERCIAL — CONNECT GROUP</p>
        <p class="header-sub">TIM Corporate · Input e Ativação Diária</p>
      </div>
      <div class="header-right">
        <img src="https://raw.githubusercontent.com/hugokhesley/dashboard-tim-connectgroup-sheets/main/logo.png" class="header-logo" onerror="this.style.display='none'">
        <span class="header-badge">📅 ATIVIDADE</span>
      </div>
    </div>
      <div class="header-badge">🟣 ATIVIDADE</div>
    </div>""", unsafe_allow_html=True)

    with st.spinner("Carregando dados..."):
        raw = load_data()
        bko = load_bko()

    if raw.empty:
        st.warning("⚠️ Nenhum dado encontrado.")
        st.stop()

    # ── Sidebar ──────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 🔧 Filtros")

        # Toggle de tema
        tema_sel = st.radio("Tema:", list(TEMAS.keys()), horizontal=True,
                            key="tema_atividade",
                            index=0 if st.session_state.get("tema_atividade", "🌙 Escuro") == "🌙 Escuro" else 1)

        st.markdown("---")
        parceiro_sel = st.selectbox("Parceiro / Aba", get_parceiros(raw))

        # Seletor de mês
        hoje = date.today()
        meses_disp = []
        for ano in [2025, 2026]:
            for mes in range(1, 13):
                meses_disp.append(f"{mes:02d}/{ano}")
        mes_atual = f"{hoje.month:02d}/{hoje.year}"
        idx_mes = meses_disp.index(mes_atual) if mes_atual in meses_disp else 0
        mes_sel = st.selectbox("Mês", meses_disp, index=idx_mes)

        # Filtro de líder — populado após o join com BKO
        # placeholder, será substituído depois do join
        lider_placeholder = st.empty()

        st.markdown("---")
        if st.button("🔄 Atualizar dados"):
            st.cache_data.clear()
            st.rerun()
        st.markdown("---")
        st.caption("Dados via Google Sheets · cache 3 min")

    # Aplica tema selecionado
    _aplicar_tema(TEMAS[tema_sel])

    # ── Prepara dados ─────────────────────────────────────────────────────────
    from data_loader import normalize_columns, _dedup_columns

    # Filtra apenas a aba DadosRadar ANTES de normalizar
    df_raw = raw.copy()
    if "_aba" in df_raw.columns:
        df_raw = df_raw[df_raw["_aba"] == "DadosRadar"].copy()

    # Parse das datas ANTES do normalize_columns (usa nome original da coluna)
    col_input_orig  = next((c for c in df_raw.columns if "data de input" in c.lower()), None)
    col_atv_orig    = next((c for c in df_raw.columns if "data de ativa" in c.lower()), None)

    if col_input_orig:
        df_raw["dt_input"] = _parse_dates(df_raw, col_input_orig)
    else:
        df_raw["dt_input"] = pd.NaT

    if col_atv_orig:
        df_raw["dt_ativacao"] = _parse_dates(df_raw, col_atv_orig)
    else:
        df_raw["dt_ativacao"] = pd.NaT

    df_base = normalize_columns(df_raw)
    df_base = _dedup_columns(df_base)

    # Filtra parceiro
    if parceiro_sel != "Todos" and "parceiro" in df_base.columns:
        df_base = df_base[df_base["parceiro"].apply(lambda x: _s(x).upper() == parceiro_sel.upper())]

    # Filtra tipo
    if "tipo_contratacao" in df_base.columns:
        df_base = df_base[df_base["tipo_contratacao"].apply(lambda x: _s(x).upper() in ["NOVO", "ADITIVO"])]

    # Exclui cancelados
    if "fila_atual" in df_base.columns:
        df_base = df_base[~df_base["fila_atual"].apply(lambda x: _s(x).upper() == "CANCELADO")]

    for col in ["acessos", "preco_oferta"]:
        if col in df_base.columns:
            df_base[col] = df_base[col].apply(_to_num)

    # dt_input e dt_ativacao já foram parseados antes do normalize
    mes_num, ano_num = int(mes_sel[:2]), int(mes_sel[3:])
    hoje_dt = pd.Timestamp(hoje)

    # Filtra pelo mês selecionado para input
    df_mes_input = df_base[
        (df_base["dt_input"].dt.month == mes_num) &
        (df_base["dt_input"].dt.year  == ano_num)
    ].copy()

    # Filtra pelo mês selecionado para ativação
    df_mes_atv = df_base[
        (df_base["dt_ativacao"].dt.month == mes_num) &
        (df_base["dt_ativacao"].dt.year  == ano_num)
    ].copy()

    # Join com BKO para ter vendedor real
    if not bko.empty and "pedido" in df_base.columns:
        df_base["pedido"]     = df_base["pedido"].apply(_norm_pedido)
        bk = bko.copy()
        bk["pedido"] = bk["pedido"].apply(_norm_pedido)
        df_mes_input = df_mes_input.merge(bk[["pedido","vendedor_real","lider"]], on="pedido", how="left")
        df_mes_atv   = df_mes_atv.merge(bk[["pedido","vendedor_real","lider"]], on="pedido", how="left")
        df_base      = df_base.merge(bk[["pedido","vendedor_real","lider"]], on="pedido", how="left")
        for d in [df_mes_input, df_mes_atv, df_base]:
            d["vendedor_real"] = d["vendedor_real"].apply(lambda x: _s(x) if _s(x) else "Sem Vendedor")
            d["lider"]         = d["lider"].apply(lambda x: _s(x) if _s(x) else "Sem Equipe")

    # Popula filtro de líder com os valores disponíveis
    lideres_disp = sorted([l for l in df_base["lider"].unique() if l and l != "Sem Equipe"])
    lider_sel = lider_placeholder.selectbox("Líder / Equipe", ["Todos"] + lideres_disp)

    # Aplica filtro de líder
    if lider_sel != "Todos":
        df_base      = df_base[df_base["lider"] == lider_sel]
        df_mes_input = df_mes_input[df_mes_input["lider"] == lider_sel] if "lider" in df_mes_input.columns else df_mes_input
        df_mes_atv   = df_mes_atv[df_mes_atv["lider"] == lider_sel] if "lider" in df_mes_atv.columns else df_mes_atv

    # ── KPIs do dia ───────────────────────────────────────────────────────────
    eh_mes_atual = (mes_num == hoje.month and ano_num == hoje.year)

    st.markdown('<p class="section-title">📊 KPIs do Dia</p>', unsafe_allow_html=True)

    if eh_mes_atual:
        df_hoje_input = df_mes_input[df_mes_input["dt_input"].dt.date == hoje]
        df_hoje_atv   = df_mes_atv[df_mes_atv["dt_ativacao"].dt.date == hoje]

        input_hoje_ac  = int(df_hoje_input["acessos"].sum())
        input_hoje_rec = df_hoje_input["preco_oferta"].sum()
        atv_hoje_ac    = int(df_hoje_atv["acessos"].sum())
        atv_hoje_rec   = df_hoje_atv["preco_oferta"].sum()
        input_hoje_ped = df_hoje_input["pedido"].nunique() if "pedido" in df_hoje_input.columns else 0

        k1, k2, k3, k4, k5 = st.columns(5)
        with k1:
            st.markdown(f"""<div class="kpi-card indigo">
              <div class="kpi-label">📥 Input Hoje — Pedidos</div>
              <div class="kpi-value">{input_hoje_ped}</div>
              <div class="kpi-sub">pedidos inseridos hoje</div>
            </div>""", unsafe_allow_html=True)
        with k2:
            st.markdown(f"""<div class="kpi-card indigo">
              <div class="kpi-label">📥 Input Hoje — Acessos</div>
              <div class="kpi-value">{input_hoje_ac:,}</div>
              <div class="kpi-sub">R$ {input_hoje_rec:,.2f}</div>
            </div>""", unsafe_allow_html=True)
        with k3:
            st.markdown(f"""<div class="kpi-card green">
              <div class="kpi-label">✅ Ativados Hoje</div>
              <div class="kpi-value">{atv_hoje_ac:,}</div>
              <div class="kpi-sub">R$ {atv_hoje_rec:,.2f}</div>
            </div>""", unsafe_allow_html=True)
        with k4:
            input_mes_ac = int(df_mes_input["acessos"].sum())
            st.markdown(f"""<div class="kpi-card blue">
              <div class="kpi-label">📥 Input Acumulado</div>
              <div class="kpi-value">{input_mes_ac:,}</div>
              <div class="kpi-sub">acessos no mês até hoje</div>
            </div>""", unsafe_allow_html=True)
        with k5:
            atv_mes_ac = int(df_mes_atv["acessos"].sum())
            st.markdown(f"""<div class="kpi-card amber">
              <div class="kpi-label">✅ Ativado Acumulado</div>
              <div class="kpi-value">{atv_mes_ac:,}</div>
              <div class="kpi-sub">acessos no mês até hoje</div>
            </div>""", unsafe_allow_html=True)
    else:
        # Mês histórico — só acumulado
        input_mes_ac  = int(df_mes_input["acessos"].sum())
        input_mes_rec = df_mes_input["preco_oferta"].sum()
        atv_mes_ac    = int(df_mes_atv["acessos"].sum())
        atv_mes_rec   = df_mes_atv["preco_oferta"].sum()
        input_mes_ped = df_mes_input["pedido"].nunique() if "pedido" in df_mes_input.columns else 0

        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.markdown(f"""<div class="kpi-card indigo">
              <div class="kpi-label">📥 Total Input — Pedidos</div>
              <div class="kpi-value">{input_mes_ped}</div>
              <div class="kpi-sub">pedidos no mês</div>
            </div>""", unsafe_allow_html=True)
        with k2:
            st.markdown(f"""<div class="kpi-card indigo">
              <div class="kpi-label">📥 Total Input — Acessos</div>
              <div class="kpi-value">{input_mes_ac:,}</div>
              <div class="kpi-sub">R$ {input_mes_rec:,.2f}</div>
            </div>""", unsafe_allow_html=True)
        with k3:
            st.markdown(f"""<div class="kpi-card green">
              <div class="kpi-label">✅ Total Ativado — Acessos</div>
              <div class="kpi-value">{atv_mes_ac:,}</div>
              <div class="kpi-sub">R$ {atv_mes_rec:,.2f}</div>
            </div>""", unsafe_allow_html=True)
        with k4:
            backlog = int(df_base[df_base["dt_ativacao"].isna()]["acessos"].sum())
            st.markdown(f"""<div class="kpi-card red">
              <div class="kpi-label">⏳ Backlog</div>
              <div class="kpi-value">{backlog:,}</div>
              <div class="kpi-sub">sem ativação ainda</div>
            </div>""", unsafe_allow_html=True)

    st.markdown("")

    # ── Tabs principais ───────────────────────────────────────────────────────
    st.markdown('<p class="section-title">📊 Análise Diária</p>', unsafe_allow_html=True)

    tab_input, tab_atv, tab_backlog, tab_gestao = st.tabs([
        "📥 Input Diário", "✅ Ativação Diária", "⏳ Backlog (meses anteriores)", "🖨️ Gestão à Vista"
    ])

    def _render_diario(df_d, col_data, cor_bar, cor_hoje, label):
        """Renderiza visão diária com toggle barras/tabela e linha de média."""
        t = TEMAS[tema_sel]
        if df_d.empty:
            st.info(f"Nenhum {label} encontrado para o período.")
            return

        diario = (df_d.groupby(df_d[col_data].dt.day)
                  .agg(acessos=("acessos","sum"), receita=("preco_oferta","sum"),
                       pedidos=("pedido","nunique") if "pedido" in df_d.columns else ("acessos","count"))
                  .reset_index())
        diario = diario.rename(columns={col_data: "dia"})
        diario["dia"] = diario["dia"].astype(int)
        diario = diario.sort_values("dia").reset_index(drop=True)
        diario["acumulado"] = diario["acessos"].cumsum()

        n_dias     = len(diario)
        media_ac   = diario["acessos"].mean()
        media_rec  = diario["receita"].mean()
        total_ac   = int(diario["acessos"].sum())
        total_rec  = diario["receita"].sum()

        # Médias em destaque
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.markdown(f"""<div style="background:{t['mini_bg']};border-radius:10px;padding:12px 16px;border:1px solid {t['mini_border']}">
              <div style="font-size:0.68rem;color:{t['label_color']};text-transform:uppercase;margin-bottom:4px">📊 Média/dia — Acessos</div>
              <div style="font-size:1.4rem;font-weight:800;color:{cor_bar}">{media_ac:.1f}</div>
              <div style="font-size:0.7rem;color:{t['sub_color']}">{n_dias} dia(s) com {label}</div>
            </div>""", unsafe_allow_html=True)
        with m2:
            st.markdown(f"""<div style="background:{t['mini_bg']};border-radius:10px;padding:12px 16px;border:1px solid {t['mini_border']}">
              <div style="font-size:0.68rem;color:{t['label_color']};text-transform:uppercase;margin-bottom:4px">💰 Média/dia — Receita</div>
              <div style="font-size:1.4rem;font-weight:800;color:{cor_bar}">R$ {media_rec:,.2f}</div>
              <div style="font-size:0.7rem;color:{t['sub_color']}">por dia útil</div>
            </div>""", unsafe_allow_html=True)
        with m3:
            st.markdown(f"""<div style="background:{t['mini_bg']};border-radius:10px;padding:12px 16px;border:1px solid {t['mini_border']}">
              <div style="font-size:0.68rem;color:{t['label_color']};text-transform:uppercase;margin-bottom:4px">📈 Total Acessos</div>
              <div style="font-size:1.4rem;font-weight:800;color:{t['value_color']}">{total_ac:,}</div>
              <div style="font-size:0.7rem;color:{t['sub_color']}">no período</div>
            </div>""", unsafe_allow_html=True)
        with m4:
            st.markdown(f"""<div style="background:{t['mini_bg']};border-radius:10px;padding:12px 16px;border:1px solid {t['mini_border']}">
              <div style="font-size:0.68rem;color:{t['label_color']};text-transform:uppercase;margin-bottom:4px">💰 Total Receita</div>
              <div style="font-size:1.4rem;font-weight:800;color:{t['value_color']}">R$ {total_rec:,.2f}</div>
              <div style="font-size:0.7rem;color:#64748b">no período</div>
            </div>""", unsafe_allow_html=True)

        st.markdown("")

        # Toggle de visualização
        viz = st.radio("Visualização:", ["📊 Barras", "📋 Tabela", "📅 Calendário Semanal"],
                       horizontal=True, key=f"viz_{label}")

        max_ac = diario["acessos"].max()

        if viz == "📅 Calendário Semanal":
            import calendar
            # Monta dicionário dia -> acessos/receita
            dia_ac  = dict(zip(diario["dia"].astype(int), diario["acessos"].astype(int)))
            dia_rec = dict(zip(diario["dia"].astype(int), diario["receita"]))

            # Calendário do mês
            cal = calendar.monthcalendar(ano_num, mes_num)
            dias_semana = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]

            # Reordena para Dom-Sáb (calendar usa Seg=0 ... Dom=6)
            # monthcalendar retorna Seg=0, precisamos Dom primeiro
            # Converte: coloca domingo (índice 6 do calendar) na frente
            cal_dom = []
            for semana in cal:
                # semana: [seg, ter, qua, qui, sex, sab, dom]
                nova = [semana[6]] + semana[:6]
                cal_dom.append(nova)

            # Header
            header_cells = "".join(
                f"<th style='padding:8px 12px;text-align:center;font-size:0.72rem;"
                f"text-transform:uppercase;letter-spacing:1px;color:#94a3b8;font-weight:600;"
                f"border-bottom:2px solid #2d3748'>{d}</th>"
                for d in dias_semana
            )

            rows_html = ""
            for s_idx, semana in enumerate(cal_dom):
                cells = ""
                tem_dado = any(d > 0 and dia_ac.get(d, 0) > 0 for d in semana)
                for d in semana:
                    if d == 0:
                        cells += "<td style='padding:10px 8px;background:#0f1117'></td>"
                    else:
                        ac  = dia_ac.get(d, 0)
                        rec = dia_rec.get(d, 0.0)
                        eh_hj = (eh_mes_atual and d == hoje.day)
                        # Cor de fundo baseada no volume
                        if ac == 0:
                            bg = "#1a1f2e"
                            cor_num = "#475569"
                        elif ac >= media_ac * 1.2:
                            bg = "#064e3b"
                            cor_num = "#34d399"
                        elif ac >= media_ac:
                            bg = "#1e3a2e"
                            cor_num = "#10b981"
                        elif ac > 0:
                            bg = "#2d1f1f"
                            cor_num = "#f87171"
                        borda = "2px solid #6366f1" if eh_hj else "1px solid #2d3748"
                        hoje_lbl = f"<div style='font-size:0.6rem;color:#a78bfa;font-weight:700'>HOJE</div>" if eh_hj else ""
                        ac_txt   = f"<div style='font-size:1.1rem;font-weight:800;color:{cor_num}'>{ac}</div>" if ac > 0 else "<div style='font-size:0.8rem;color:#475569'>—</div>"
                        rec_txt  = f"<div style='font-size:0.62rem;color:#64748b'>R$ {rec:,.0f}</div>" if rec > 0 else ""
                        cells += f"""<td style='padding:6px 4px;text-align:center;
                          background:{bg};border:{borda};border-radius:8px;
                          min-width:80px;vertical-align:top'>
                          <div style='font-size:0.72rem;color:#94a3b8;margin-bottom:2px'>{d:02d}</div>
                          {hoje_lbl}{ac_txt}{rec_txt}
                        </td>"""

                rows_html += f"""<tr>
                  <td colspan="7" style="padding:4px 0 2px 0;font-size:0.65rem;
                    color:#475569;text-transform:uppercase;letter-spacing:1px">
                    Semana {s_idx + 1}
                  </td></tr>
                <tr style='border-bottom:4px solid #0f1117'>{cells}</tr>
                <tr><td colspan='7' style='padding:4px 0'></td></tr>"""

            legenda = f"""
            <div style='display:flex;gap:16px;font-size:0.7rem;color:#94a3b8;margin-bottom:12px'>
              <span>🟢 Acima da média ({media_ac:.1f} ac.)</span>
              <span>🔴 Abaixo da média</span>
              <span>⬛ Sem input</span>
              <span style='color:#a78bfa'>🟣 Hoje</span>
            </div>"""

            st.markdown(legenda, unsafe_allow_html=True)
            st.markdown(f"""
            <div style='overflow-x:auto'>
              <table style='border-collapse:separate;border-spacing:4px;width:100%'>
                <thead><tr>{header_cells}</tr></thead>
                <tbody>{rows_html}</tbody>
              </table>
            </div>""", unsafe_allow_html=True)

        elif viz == "📊 Barras":
            html_dias = ""
            for _, row in diario.iterrows():
                dia     = int(row["dia"])
                eh_hj   = (eh_mes_atual and dia == hoje.day)
                badge   = '<span class="hoje-badge">HOJE</span>' if eh_hj else ""
                cor     = cor_hoje if eh_hj else cor_bar
                pct_med = min(int(media_ac / max_ac * 100), 100) if max_ac > 0 else 0
                acima   = "▲" if row["acessos"] >= media_ac else "▼"
                cor_cmp = "#10b981" if row["acessos"] >= media_ac else "#ef4444"
                html_dias += f"""
                <div class="day-bar-wrap">
                  <div class="day-label">
                    <span>Dia {dia:02d}{badge}
                      <span style="font-size:0.68rem;color:{cor_cmp};margin-left:6px">{acima} vs média</span>
                    </span>
                    <span style="font-weight:700;color:#e2e8f0">
                      {int(row['acessos'])} ac.
                      <span style="color:#64748b;font-weight:400"> · R$ {row['receita']:,.2f} · acum. {int(row['acumulado'])}</span>
                    </span>
                  </div>
                  <div style="position:relative">
                    {_bar(row['acessos'], max_ac, cor)}
                    <div style="position:absolute;top:0;left:{pct_med}%;width:2px;height:12px;background:#f59e0b;opacity:0.8"></div>
                  </div>
                </div>"""
            st.markdown(
                f'<div style="max-height:500px;overflow-y:auto;padding-right:8px">'
                f'<div style="font-size:0.68rem;color:#f59e0b;margin-bottom:8px">🟡 Linha amarela = média de {media_ac:.1f} ac./dia</div>'
                f'{html_dias}</div>',
                unsafe_allow_html=True
            )
        else:
            # Visão tabela
            df_tab = diario.copy()
            df_tab.columns = ["Dia","Acessos","R$","Pedidos","Acumulado"]
            df_tab["vs Média"] = df_tab["Acessos"].apply(
                lambda x: f"▲ +{x-media_ac:.0f}" if x >= media_ac else f"▼ {x-media_ac:.0f}"
            )
            st.dataframe(df_tab, use_container_width=True, hide_index=True,
                column_config={
                    "Dia":       st.column_config.NumberColumn("Dia", format="%d"),
                    "Acessos":   st.column_config.NumberColumn(format="%d"),
                    "Pedidos":   st.column_config.NumberColumn(format="%d"),
                    "Acumulado": st.column_config.NumberColumn(format="%d"),
                    "R$":        st.column_config.NumberColumn(format="R$ %.2f"),
                })

        # Detalhe por vendedor/dia
        st.markdown("")
        with st.expander("📋 Ver detalhe por vendedor/dia", expanded=False):
            det = (df_d.groupby([df_d[col_data].dt.day, "vendedor_real"])
                   .agg(acessos=("acessos","sum"), receita=("preco_oferta","sum"),
                        pedidos=("pedido","nunique") if "pedido" in df_d.columns else ("acessos","count"))
                   .reset_index().rename(columns={col_data:"dia"}))
            det.columns = ["Dia","Vendedor","Acessos","R$","Pedidos"]
            st.dataframe(det.sort_values(["Dia","Acessos"], ascending=[True,False]),
                         use_container_width=True, hide_index=True,
                         column_config={
                             "Acessos": st.column_config.NumberColumn(format="%d"),
                             "Pedidos": st.column_config.NumberColumn(format="%d"),
                             "R$":      st.column_config.NumberColumn(format="R$ %.2f"),
                         })

    with tab_input:
        _render_diario(df_mes_input, "dt_input", "#6366f1", "#a78bfa", "input")

    with tab_atv:
        _render_diario(df_mes_atv, "dt_ativacao", "#10b981", "#34d399", "ativação")

    with tab_gestao:
        _render_gestao_vista(df_base, df_mes_atv, df_mes_input, mes_sel, hoje, eh_mes_atual, tema_sel, raw=raw, bko=bko, parceiro_sel=parceiro_sel, lider_sel=lider_sel)

    with tab_backlog:
        # BACKLOG CORRETO: pedidos cujo mês de input é DIFERENTE do mês analisado
        # e que ainda não foram ativados
        df_backlog = df_base[
            df_base["dt_ativacao"].isna() &
            (
                (df_base["dt_input"].dt.month != mes_num) |
                (df_base["dt_input"].dt.year  != ano_num)
            )
        ].copy()

        if df_backlog.empty:
            st.success("🎉 Sem backlog de meses anteriores!")
        else:
            total_bl = int(df_backlog["acessos"].sum())
            n_ped    = df_backlog["pedido"].nunique() if "pedido" in df_backlog.columns else len(df_backlog)

            # KPIs backlog
            b1, b2, b3 = st.columns(3)
            with b1:
                st.markdown(f"""<div style="background:#1a1f2e;border-radius:10px;padding:14px 20px;border:1px solid #2d3748">
                  <div style="font-size:0.68rem;color:#94a3b8;text-transform:uppercase">⏳ Total Backlog</div>
                  <div style="font-size:1.8rem;font-weight:800;color:#f59e0b">{total_bl:,} ac.</div>
                </div>""", unsafe_allow_html=True)
            with b2:
                st.markdown(f"""<div style="background:#1a1f2e;border-radius:10px;padding:14px 20px;border:1px solid #2d3748">
                  <div style="font-size:0.68rem;color:#94a3b8;text-transform:uppercase">📋 Pedidos</div>
                  <div style="font-size:1.8rem;font-weight:800;color:#f59e0b">{n_ped}</div>
                </div>""", unsafe_allow_html=True)
            with b3:
                meses_bl = df_backlog["dt_input"].dt.strftime("%m/%Y").dropna().unique()
                st.markdown(f"""<div style="background:#1a1f2e;border-radius:10px;padding:14px 20px;border:1px solid #2d3748">
                  <div style="font-size:0.68rem;color:#94a3b8;text-transform:uppercase">📅 Meses de Origem</div>
                  <div style="font-size:1rem;font-weight:700;color:#f59e0b">{' · '.join(sorted(meses_bl))}</div>
                </div>""", unsafe_allow_html=True)

            st.markdown("")

            # Por vendedor
            if "vendedor_real" in df_backlog.columns:
                por_vend = (df_backlog.groupby("vendedor_real")
                            .agg(acessos=("acessos","sum"),
                                 pedidos=("pedido","nunique"),
                                 receita=("preco_oferta","sum"))
                            .reset_index().sort_values("acessos", ascending=False))

                for _, row in por_vend.iterrows():
                    with st.expander(
                        f"👤 {row['vendedor_real']} — {int(row['acessos'])} ac. · {int(row['pedidos'])} pedido(s) · R$ {row['receita']:,.2f}",
                        expanded=False
                    ):
                        df_vend_bl = df_backlog[df_backlog["vendedor_real"] == row["vendedor_real"]]
                        cols_show  = [c for c in ["pedido","razao_social","fila_atual","acessos","preco_oferta","dt_input"] if c in df_vend_bl.columns]
                        df_show    = df_vend_bl[cols_show].copy()
                        if "dt_input" in df_show.columns:
                            df_show["dt_input"] = df_show["dt_input"].dt.strftime("%d/%m/%Y")
                        st.dataframe(df_show.sort_values("acessos", ascending=False),
                                     use_container_width=True, hide_index=True,
                                     column_config={
                                         "pedido":       "Pedido",
                                         "razao_social": "Razão Social",
                                         "fila_atual":   "Fila Atual",
                                         "acessos":      st.column_config.NumberColumn("Acessos", format="%d"),
                                         "preco_oferta": st.column_config.NumberColumn("R$", format="R$ %.2f"),
                                         "dt_input":     "Data Input",
                                     })


main()
