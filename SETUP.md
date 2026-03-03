# 🚀 GUIA DE SETUP — Dashboard Connect Group + Google Sheets

## Estrutura de arquivos
```
/
├── app.py
├── data_loader.py
├── pages/
│   └── 01_Renegociação.py
├── requirements.txt
├── .streamlit/
│   └── secrets.toml       ← NÃO suba este arquivo para o GitHub!
└── README.md
```

---

## PASSO 1 — Criar a Conta de Serviço Google (5 min, só uma vez)

1. Acesse https://console.cloud.google.com
2. Crie um projeto (ou use um existente)
3. No menu lateral: **APIs e Serviços → Biblioteca**
4. Ative as duas APIs:
   - **Google Sheets API**
   - **Google Drive API**
5. Vá em **APIs e Serviços → Credenciais**
6. Clique em **Criar credenciais → Conta de serviço**
7. Dê um nome (ex: `dashboard-connect`) e clique em **Criar**
8. Na conta criada, clique em **Chaves → Adicionar chave → JSON**
9. Salve o arquivo `.json` baixado — você vai precisar dele

---

## PASSO 2 — Preparar o Google Sheets (2 min)

1. Crie uma planilha nova em https://sheets.google.com
2. Crie **2 abas** (clicando no + na parte inferior):
   - Aba 1: nome do Parceiro A (ex: `Parceiro Alpha`)
   - Aba 2: nome do Parceiro B (ex: `Parceiro Beta`)
3. Na linha 1 de cada aba, coloque os cabeçalhos obrigatórios:
   ```
   parceiro | tipo de contratação | fila atual | data de ativação | data de input | acessos | preço oferta | razão social
   ```
4. Copie a URL da planilha (ex: `https://docs.google.com/spreadsheets/d/ABC123/edit`)
5. Clique em **Compartilhar** e adicione o e-mail da conta de serviço
   (está no campo `client_email` do arquivo JSON)
   com permissão de **Editor** ou **Leitor**

---

## PASSO 3 — Configurar o secrets.toml (local)

Abra o arquivo `.streamlit/secrets.toml` e preencha com os dados do JSON:

```toml
[gcp_service_account]
type                        = "service_account"
project_id                  = "meu-projeto-123"
private_key_id              = "abc123..."
private_key                 = "-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----\n"
client_email                = "dashboard-connect@meu-projeto.iam.gserviceaccount.com"
client_id                   = "123456789"
auth_uri                    = "https://accounts.google.com/o/oauth2/auth"
token_uri                   = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url        = "https://www.googleapis.com/robot/v1/metadata/x509/..."

[sheets]
url = "https://docs.google.com/spreadsheets/d/SEU_ID/edit"
```

> ⚠️ **NUNCA suba o secrets.toml para o GitHub!**
> Adicione `.streamlit/secrets.toml` no seu `.gitignore`

---

## PASSO 4 — Testar localmente

```bash
pip install -r requirements.txt
streamlit run app.py
```

---

## PASSO 5 — Deploy no Streamlit Cloud

1. Suba o projeto para o GitHub (**sem** o `secrets.toml`)
2. Acesse https://share.streamlit.io
3. Conecte ao repositório e aponte para `app.py`
4. Vá em **Advanced settings → Secrets**
5. Cole o conteúdo do seu `secrets.toml` no campo de texto
6. Clique em **Deploy**

---

## Como atualizar os dados

Fluxo rápido do dia a dia:

```
Baixa o .xlsx do sistema
        ↓
Abre o Google Sheets
        ↓
Arquivo → Importar → Fazer upload
Seleciona a aba correta (Parceiro A ou B)
Marca "Substituir dados na aba atual"
        ↓
Dashboard atualiza em até 3 minutos automaticamente
(ou clique em "🔄 Atualizar dados" na sidebar)
```

---

## Colunas obrigatórias no Sheets

| Coluna               | Tipo     | Exemplo                |
|----------------------|----------|------------------------|
| parceiro             | Texto    | Alpha Telecom          |
| tipo de contratação  | Texto    | NOVO / ADITIVO / RENEGOCIAÇÃO |
| fila atual           | Texto    | EM ANÁLISE             |
| data de ativação     | Data     | 15/03/2026             |
| data de input        | Data     | 01/03/2026             |
| acessos              | Número   | 12                     |
| preço oferta         | Número   | 1490.00                |
| razão social         | Texto    | Empresa XYZ Ltda       |
