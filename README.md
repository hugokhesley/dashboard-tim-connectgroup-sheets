# 📊 Dashboard Connect Group — TIM Empresas

Dashboard de gestão comercial em Streamlit, com os dados vindo de uma planilha
Google Sheets e cinco automações rodando no GitHub Actions.

Para o setup inicial (conta de serviço Google, secrets, primeiro deploy), veja
[`SETUP.md`](SETUP.md).

## 📁 Estrutura

```
app.py                    entrypoint do Streamlit Cloud — redireciona p/ Tramitação Atual
auth.py                   login (streamlit-authenticator) + PAGE_ACCESS por página
data_loader.py            leitura da planilha, normalização e regras de negócio
ui.py                     estilo base (fonte Inter + tema escuro) usado por todas as páginas
pages/                    as 14 páginas do dashboard, na ordem do menu
tests/                    testes que rodam sem credencial, com stubs
requirements.txt          dependências do app
requirements-actions.txt  dependências das automações (não instaladas no app)
```

### Páginas

| # | Página | Chave em `PAGE_ACCESS` |
|---|--------|------------------------|
| 01 | Tramitação Atual | `tramitacao` |
| 02 | Pós Venda | `pos_venda` |
| 03 | Resultados | `resultados` |
| 04 | Qualidade | `qualidade` |
| 05 | Performance | `performance` |
| 06 | Atividade Comercial | `atividade` |
| 07 | Tramitação Consolidada | `consolidada` |
| 08 | Comissões | `comissoes` |
| 09 | Análise Espelho | `espelho` |
| 10 | Atualização Bases | `atualizacao_bases` |
| 11 | Atribuição Vendedor | — (pública) |
| 12 | Discador | `discador` |
| 13 | Gestão Equipe | usa `credentials_gestao` |
| 14 | Carteira | usa `credentials_gestao` |

> O prefixo numérico só define a ordem no menu — a URL de cada página ignora ele
> (`/Resultados`, `/Performance`, …), então renumerar não quebra link salvo.

## 🗂️ Abas da planilha

`load_data()` concatena **todas as abas exceto `metas`** e deixa o `apply_filters`
descartar o que não é venda (ele exige `tipo de contratação`). A base em si vem
principalmente de:

| Aba | Para que serve |
|-----|----------------|
| `DadosRadar` | **a base de vendas** — dump do Radar gravado pela automação |
| abas de safra | eventuais abas por mês (ex: `MAR/2026`) |

> ⚠️ **Não saia excluindo aba de `ABAS_NAO_BASE`.** `DadosRadar` já foi tratado
> como "aba operacional" uma vez e o dashboard inteiro apareceu vazio em
> produção. Só exclua aba que comprovadamente não tem as colunas de venda.

As abas abaixo entram na concatenação mas são descartadas pelo filtro, e têm
loader próprio para o uso específico delas:

| Aba | Para que serve |
|-----|----------------|
| `metas` | metas de acessos/receita por mês (única realmente pulada) |
| `Colaboradores` | vendedores ativos, líder, TBP e meta individual |
| `BKO-VENDEDOR-REAL` | de-para pedido → vendedor real |
| `deParaDiscador` / `DePara` | normalização de nome de vendedor |
| `RadarRunStatus` | heartbeat da automação (consumido pelo n8n) |
| `StatusQuickTIM` | saída da automação QuickTIM |
| `Discador` | saída do sync ConnectVoice |
| `CarteiraAtendimento` / `CarteiraContatos` | carteira de clientes por CNPJ |
| `BASE_SAFRAS_QUALIDADE` | base da página Qualidade |
| `Parceiros` / `Comissoes` | cadastro e apuração de comissionamento |
| `resultados` | consolidado da página Resultados |
| `Logs` | registro de acesso por página |

Se alguma dessas ficar grande a ponto de pesar na carga, dá para pular pelos
secrets, sem mexer no código:

```toml
[sheets]
url = "https://docs.google.com/spreadsheets/d/SEU_ID/edit"
ignorar_abas = ["Logs", "CarteiraContatos"]
```

### Colunas esperadas nas abas de safra

| Coluna | Descrição |
|--------|-----------|
| `parceiro` | Nome do parceiro |
| `tipo de contratação` | NOVO / ADITIVO / RENEGOCIAÇÃO |
| `fila atual` | Status atual do pedido (mapeado em `STATUS_MAP`) |
| `data de ativação` | dd/mm/aaaa — vazio significa que ainda está no pipeline |
| `data de input` | dd/mm/aaaa |
| `acessos` | Volume de acessos |
| `preço oferta` | Valor da oferta |
| `razão social` | Nome da empresa cliente |
| `pedido` | Usado no cruzamento com o BKO |

## ⚙️ Regras de negócio

Implementadas em `apply_filters()` (`data_loader.py`):

- **Ativados:** `data de ativação` dentro do mês alvo
- **Pipeline:** `data de ativação` vazia
- **Excluídos:** `fila atual` = CANCELADO, e ativados em outros meses
- **Status do dashboard:** `fila atual` cai em PRÉ-VENDA, EM ANÁLISE, CRÉDITO,
  DEVOLVIDOS ou ENTRANTE via `STATUS_MAP`
- **Metas:** lidas da aba `metas`, por mês (`get_meta_mes`)

## 🤖 Automações (GitHub Actions)

| Workflow | Script | O que faz |
|----------|--------|-----------|
| `atualizar_dados_radar.yml` | `actions_runner.py` | baixa a base do Radar → aba `DadosRadar` |
| `recover_dadosradar.yml` | `actions_recover.py` | reprocessa quando o run principal falha |
| `connectvoice_sync.yml` | `connectvoice_sync.py` | puxa ligações do ConnectVoice → aba `Discador` |
| `quicktim_status.yml` | `quicktim_status.py` | consulta status no QuickTIM → aba `StatusQuickTIM` |
| `notify_pendentes.yml` | `notify_pendentes.py` | avisa pedidos sem vendedor atribuído |

Esses scripts usam Selenium + Chromium e instalam suas dependências no próprio
workflow. Por isso **não** entram no `requirements.txt` do app: o Streamlit Cloud
levaria uns 150 MB a mais para subir sem precisar.

## 🔐 Secrets

```toml
[gcp_service_account]   # JSON da conta de serviço (ver SETUP.md)
[sheets]                # url da planilha + ignorar_abas (opcional)
[auth]                  # <usuario>_pw para cada pessoa + cookie_key
[credentials_gestao]    # usuários das páginas Gestão Equipe e Carteira
```

## 🔧 Rodar localmente

```bash
pip install -r requirements.txt
streamlit run app.py
```

Precisa de um `.streamlit/secrets.toml` válido (gitignored).

## ✅ Testes

Rodam sem credencial nenhuma — as dependências pesadas são stubadas:

```bash
python tests/test_data_loader.py    # data_loader: conversões e montagem da base
python tests/test_paginacao.py      # automação do Radar: varredura paginada
python tests/test_recover.py        # automação do Radar: recover parcial
```

## 🔄 Atualizar os dados no dashboard

O cache é de 3 minutos. Para forçar antes disso, use **"🔄 Limpar Cache e
Recarregar"** na sidebar, ou **Reboot App** no menu ⋮ do Streamlit Cloud.
