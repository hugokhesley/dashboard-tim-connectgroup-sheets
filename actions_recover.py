# “””

# ACTIONS RECOVER — Recuperação pós-timeout

# Roda quando o actions_runner.py cancela após os emails já terem
chegado. Vai direto ao IMAP das 3 contas, pega os links e sobe
para o Sheets. Sem login no Radar, sem RSA, sem espera.

“””

import os
import time
import imaplib
import email
import re
import requests
import pandas as pd
import gspread
import io
from datetime import datetime, timezone, timedelta
from email.header import decode_header
from email.utils import parsedate_to_datetime
from google.oauth2.service_account import Credentials

# ─────────────────────────────────────────────────────────────────

# ⚙️  CONFIGURAÇÕES

# ─────────────────────────────────────────────────────────────────

EMAIL_1        = os.environ[“EMAIL_1”]
SENHA_1        = os.environ[“SENHA_1”]
EMAIL_2        = os.environ[“EMAIL_2”]
SENHA_2        = os.environ[“SENHA_2”]
EMAIL_3        = os.environ[“EMAIL_3”]
SENHA_3        = os.environ[“SENHA_3”]
SPREADSHEET_ID = os.environ[“SPREADSHEET_ID”]

# Janela de busca em horas (padrão: últimas 6h)

JANELA_HORAS   = int(os.environ.get(“JANELA_HORAS”, “6”))

IMAP_HOST      = “imap.titan.email”
IMAP_PORT      = 993
INTERVALO_IMAP = 60   # segundos entre tentativas
MAX_TENTATIVAS = 10
ABA_DESTINO    = “DadosRadar”

CONTAS_EMAIL = [
{“nome”: “Conta 1”, “email”: EMAIL_1, “senha”: SENHA_1},
{“nome”: “Conta 2”, “email”: EMAIL_2, “senha”: SENHA_2},
{“nome”: “Conta 3”, “email”: EMAIL_3, “senha”: SENHA_3},
]

# ─────────────────────────────────────────────────────────────────

# IMAP

# ─────────────────────────────────────────────────────────────────

def verificar_email(email_conta, senha, desde):
try:
mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
mail.login(email_conta, senha)

```
    _, pastas_raw = mail.list()
    caixas = ["INBOX"]
    for p in pastas_raw:
        if p:
            nome = p.decode(errors="ignore").split('"/"')[-1].strip().strip('"')
            if "gmail" in nome.lower() or "totodecasa" in nome.lower() or "@gmail" in nome.lower():
                caixas.append(nome)

    desde_utc = desde.astimezone(timezone.utc)
    data_imap = desde_utc.strftime("%d-%b-%Y")

    for caixa in caixas:
        try:
            status_sel, _ = mail.select(f'"{caixa}"')
            if status_sel != "OK":
                continue
        except Exception:
            continue

        status, msgs = mail.search(None, f'SINCE "{data_imap}"')
        if status != "OK" or not msgs[0]:
            continue

        for uid in reversed(msgs[0].split()):
            _, dados = mail.fetch(uid, "(RFC822)")
            msg = email.message_from_bytes(dados[0][1])

            data_str = msg.get("Date")
            if not data_str:
                continue
            try:
                data_email = parsedate_to_datetime(data_str)
                if data_email.tzinfo is None:
                    data_email = data_email.replace(tzinfo=timezone.utc)
                else:
                    data_email = data_email.astimezone(timezone.utc)
            except Exception:
                continue

            if data_email <= desde_utc:
                continue

            assunto_raw = msg.get("Subject", "")
            try:
                partes = decode_header(assunto_raw)
                assunto = ""
                for parte, enc in partes:
                    if isinstance(parte, bytes):
                        assunto += parte.decode(enc or "utf-8", errors="ignore")
                    else:
                        assunto += parte
            except Exception:
                assunto = assunto_raw

            if "Radar" not in assunto and "radar" not in assunto:
                continue

            for parte in msg.walk():
                if parte.get_content_type() in ("text/plain", "text/html"):
                    corpo = parte.get_payload(decode=True).decode(errors="ignore")
                    match = re.search(r'https://radar\.timbrasil\.com\.br/[^\s"<>\)]+', corpo)
                    if match:
                        mail.logout()
                        return match.group(0).strip()

    mail.logout()
    return None
except Exception as e:
    print(f"  ⚠️ Erro IMAP {email_conta}: {e}")
    return None
```

# ─────────────────────────────────────────────────────────────────

# SHEETS

# ─────────────────────────────────────────────────────────────────

def subir_para_sheets(df):
scopes = [“https://www.googleapis.com/auth/spreadsheets”, “https://www.googleapis.com/auth/drive”]
creds = Credentials.from_service_account_file(“credentials.json”, scopes=scopes)
gc = gspread.authorize(creds)
planilha = gc.open_by_key(SPREADSHEET_ID)
try:
aba = planilha.worksheet(ABA_DESTINO)
except gspread.WorksheetNotFound:
aba = planilha.add_worksheet(title=ABA_DESTINO, rows=1, cols=1)
aba.clear()
df = df.fillna(””)
dados = [df.columns.tolist()] + df.values.tolist()
dados = [[str(v) for v in linha] for linha in dados]
aba.update(dados, value_input_option=“USER_ENTERED”)
print(f”  ✅ {len(df)} linhas gravadas em ‘{ABA_DESTINO}’!”)

# ─────────────────────────────────────────────────────────────────

# MAIN

# ─────────────────────────────────────────────────────────────────

def main():
print(”=” * 55)
print(”  ACTIONS RECOVER — BUSCA DE LINKS E UPLOAD”)
print(”=” * 55)
print(f”🔍 Buscando emails das últimas {JANELA_HORAS}h…”)

```
desde = datetime.now().astimezone() - timedelta(hours=JANELA_HORAS)
links = [None, None, None]
tentativa = 0

while tentativa < MAX_TENTATIVAS:
    tentativa += 1
    print(f"\n📬 Tentativa #{tentativa}...")

    for i, conta in enumerate(CONTAS_EMAIL):
        if not links[i]:
            links[i] = verificar_email(conta["email"], conta["senha"], desde)
            status = "✅ encontrado" if links[i] else "⏸ aguardando"
            print(f"  {conta['nome']} ({conta['email']}): {status}")

    if all(links):
        break

    if tentativa < MAX_TENTATIVAS:
        print(f"  ⏳ Aguardando {INTERVALO_IMAP}s...")
        time.sleep(INTERVALO_IMAP)

# Verifica quais chegaram
faltando = [CONTAS_EMAIL[i]["nome"] for i, l in enumerate(links) if not l]
if faltando:
    print(f"\n⚠️  Links não encontrados: {', '.join(faltando)}")
    links_validos = [l for l in links if l]
    if not links_validos:
        print("❌ Nenhum link encontrado. Abortando.")
        exit(1)
    print(f"  Prosseguindo com {len(links_validos)} de 3 links...")
else:
    links_validos = links
    print("\n✅ Todos os links encontrados!")

# Download
print("\n⬇️  Baixando planilhas...")
dfs = []
for i, link in enumerate(links_validos):
    try:
        content = requests.get(link, headers={"User-Agent": "Mozilla/5.0"}, timeout=60).content
        try:
            df = pd.read_excel(io.BytesIO(content), engine="openpyxl", header=0)
        except Exception:
            df = pd.read_excel(io.BytesIO(content), engine="xlrd", header=0)
        print(f"  Arquivo {i+1}: {len(df)} linhas")
        dfs.append(df)
    except Exception as e:
        print(f"  ⚠️ Erro no download {i+1}: {e}")

if not dfs:
    print("❌ Nenhum arquivo baixado. Abortando.")
    exit(1)

df_final = pd.concat(dfs, ignore_index=True)
print(f"  📋 Total consolidado: {len(df_final)} linhas")

# Upload
subir_para_sheets(df_final)

print("\n🎉 Recuperação concluída com sucesso!")
print("=" * 55)
```

if **name** == “**main**”:
main()