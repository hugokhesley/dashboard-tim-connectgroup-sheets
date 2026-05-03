"""
=====================================================================
  notify_pendentes.py — Roda no GitHub Actions
=====================================================================
  Detecta pedidos sem vendedor_real e notifica líderes via Telegram
  com o link fixo da página de atribuição.
=====================================================================
"""

import os
import requests
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# ─────────────────────────────────────────────────────────────────
#  CONFIGURAÇÕES
# ─────────────────────────────────────────────────────────────────

SPREADSHEET_ID  = os.environ["SPREADSHEET_ID"]
TELEGRAM_TOKEN  = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_LIDERES = os.environ.get("TELEGRAM_LIDERES", "")  # "chat_id1,chat_id2,chat_id3"
LINK_ATRIBUICAO = os.environ.get("LINK_ATRIBUICAO", "https://dashboard-connectgroup.streamlit.app/Atribuicao_Vendedor")

ABA_RADAR  = "DadosRadar"
ABA_DEPARA = "DePara"


# ─────────────────────────────────────────────────────────────────
#  SHEETS
# ─────────────────────────────────────────────────────────────────

def get_gc():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds  = Credentials.from_service_account_file("credentials.json", scopes=scopes)
    return gspread.authorize(creds)


def contar_pendentes():
    """Retorna número de pedidos no Radar sem vendedor_real no DePara."""
    gc = get_gc()
    planilha = gc.open_by_key(SPREADSHEET_ID)

    # Radar
    aba_radar = planilha.worksheet(ABA_RADAR)
    df_radar  = pd.DataFrame(aba_radar.get_all_records())
    if df_radar.empty:
        return 0, pd.DataFrame()

    df_radar.columns = [c.strip().lower().replace(" ", "_") for c in df_radar.columns]
    if "pedido" not in df_radar.columns:
        return 0, pd.DataFrame()

    df_radar["_pedido_norm"] = df_radar["pedido"].apply(lambda x: str(x).strip().split(".")[0])
    df_radar = df_radar[df_radar["_pedido_norm"] != ""].drop_duplicates("_pedido_norm")

    # DePara
    try:
        aba_dp = planilha.worksheet(ABA_DEPARA)
        df_dp  = pd.DataFrame(aba_dp.get_all_records())
        if not df_dp.empty:
            df_dp.columns = [c.strip().lower().replace(" ", "_") for c in df_dp.columns]
            pedidos_ok = set(
                df_dp[df_dp["vendedor_real"].apply(lambda x: str(x).strip() != "")]["pedido"]
                .apply(lambda x: str(x).strip().split(".")[0])
            )
        else:
            pedidos_ok = set()
    except Exception:
        pedidos_ok = set()

    df_pend = df_radar[~df_radar["_pedido_norm"].isin(pedidos_ok)]

    colunas = [c for c in ["pedido", "razao_social", "acessos", "status_dash"] if c in df_pend.columns]
    return len(df_pend), df_pend[colunas].head(5)


# ─────────────────────────────────────────────────────────────────
#  TELEGRAM
# ─────────────────────────────────────────────────────────────────

def enviar_telegram(chat_id: str, mensagem: str):
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    resp = requests.post(url, json={
        "chat_id":    chat_id,
        "text":       mensagem,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }, timeout=10)
    return resp.ok


# ─────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  NOTIFY PENDENTES — ATRIBUIÇÃO DE VENDEDORES")
    print("=" * 55)

    total, df_amostra = contar_pendentes()
    print(f"  Pedidos pendentes: {total}")

    if total == 0:
        print("  ✅ Nenhum pendente. Notificação não enviada.")
        return

    # Monta preview dos pedidos
    linhas_preview = ""
    for _, row in df_amostra.iterrows():
        pedido  = str(row.get("pedido", "")).split(".")[0]
        cliente = str(row.get("razao_social", "—"))[:35]
        acessos = str(row.get("acessos", "")).split(".")[0]
        linhas_preview += f"\n  • <b>{pedido}</b> — {cliente} ({acessos} acs)"

    if total > 5:
        linhas_preview += f"\n  <i>...e mais {total - 5} pedido(s)</i>"

    mensagem = (
        f"👤 <b>Atribuição de Vendedores</b>\n"
        f"Connect Group · {pd.Timestamp.now().strftime('%d/%m/%Y %H:%M')}\n\n"
        f"<b>{total} pedido(s)</b> sem vendedor atribuído:{linhas_preview}\n\n"
        f"👉 <a href=\"{LINK_ATRIBUICAO}\">Abrir formulário de atribuição</a>"
    )

    # Envia para cada líder
    chat_ids = [c.strip() for c in TELEGRAM_LIDERES.split(",") if c.strip()]
    if not chat_ids:
        print("  ⚠️  Nenhum chat_id configurado em TELEGRAM_LIDERES.")
        return

    enviados = 0
    for cid in chat_ids:
        ok = enviar_telegram(cid, mensagem)
        print(f"  {'✅' if ok else '❌'} chat_id {cid}")
        if ok:
            enviados += 1

    print(f"\n  📨 Notificações enviadas: {enviados}/{len(chat_ids)}")
    print("=" * 55)


if __name__ == "__main__":
    main()
