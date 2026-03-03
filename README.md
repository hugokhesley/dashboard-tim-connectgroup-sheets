# 📊 Dashboard Connect Group — TIM Corporate

Dashboard de gestão de vendas e renegociações em Streamlit.

## 📁 Estrutura de Arquivos

```
/
├── app.py                        ← Painel de Vendas (NOVO + ADITIVO)
├── pages/
│   └── 01_Renegociação.py        ← Painel de Renegociação
├── requirements.txt
└── *.xlsx                        ← Suas planilhas (na raiz)
```

## 🗂️ Colunas Obrigatórias no Excel

| Coluna               | Descrição                          |
|----------------------|------------------------------------|
| `parceiro`           | Nome do parceiro                   |
| `tipo de contratação`| NOVO / ADITIVO / RENEGOCIAÇÃO      |
| `fila atual`         | Status atual do pedido             |
| `data de ativação`   | Data de ativação (dd/mm/aaaa)      |
| `data de input`      | Data de entrada (dd/mm/aaaa)       |
| `acessos`            | Volume de acessos (número)         |
| `preço oferta`       | Valor da oferta (número)           |
| `razão social`       | Nome da empresa cliente            |

## 🚀 Deploy no Streamlit Cloud

1. Suba esta pasta para um repositório GitHub
2. Acesse [share.streamlit.io](https://share.streamlit.io)
3. Aponte para o arquivo `app.py` como entry point
4. Pronto! Os arquivos `.xlsx` devem estar na raiz do repositório

## 🔄 Atualizar Dados

- Substitua os arquivos `.xlsx` no repositório
- No dashboard: clique em **"🔄 Limpar Cache e Recarregar"** na sidebar
- Ou use **"Reboot App"** no menu ⋮ do Streamlit Cloud

## ⚙️ Regras de Negócio

- **Mês alvo:** Março/2026 (fixo em `MES_ALVO`)
- **Ativados:** `data de ativação` == mês alvo
- **Pipeline:** `data de ativação` vazia + `data de input` == mês alvo
- **Excluídos:** registros com `fila atual` == CANCELADO ou ativados em outros meses
- **Meta Vendas:** 626 acessos
- **Meta Renegociação:** 751 acessos (120% da meta de vendas)

## 🔧 Rodar Localmente

```bash
pip install -r requirements.txt
streamlit run app.py
```
