"""Estilo base compartilhado pelas paginas do dashboard.

Antes, cada pagina repetia o mesmo cabecalho de CSS (import da fonte Inter,
family no body e o tema escuro do .stApp). Ficava facil uma pagina divergir das
outras sem ninguem notar. Agora a base mora aqui e cada pagina so declara o que
tem de proprio (header, cards, tabelas).

Uso, no topo da pagina e antes do <style> especifico dela:

    from ui import aplicar_estilo_base
    aplicar_estilo_base()
"""
import streamlit as st

# Todos os pesos que as paginas usam, reunidos num import so.
FONTE = ("https://fonts.googleapis.com/css2?"
         "family=Inter:wght@300;400;500;600;700;800&display=swap")

FUNDO = "#0f1117"
TEXTO = "#e2e8f0"

CSS_BASE = f"""
<style>
  @import url('{FONTE}');
  html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}
  .stApp {{ background-color: {FUNDO}; color: {TEXTO}; }}
</style>
"""


def aplicar_estilo_base() -> None:
    """Injeta a fonte e o tema escuro comuns a todas as paginas."""
    st.markdown(CSS_BASE, unsafe_allow_html=True)
