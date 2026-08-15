"""Falha visivel em vez de dado vazio.

O padrao `except Exception: return []` espalhado pelo projeto tem um custo alto:
o erro some e a tela mostra um resultado que PARECE certo. Foi assim que a
Carteira ficou com o dropdown de vendedor vazio sem ninguem perceber — um
TypeError virou lista vazia e ninguem foi avisado.

A regra aqui e simples: engolir a excecao para nao derrubar a pagina tudo bem,
mas ela precisa aparecer em algum lugar.
"""
import sys

import streamlit as st


def registrar_aviso(contexto: str, detalhe: str, *, avisar: bool = False) -> None:
    """Registra uma falha que nao veio como excecao.

    Ex: uma API que responde 400 com o motivo no corpo — nao levanta erro em
    Python, mas o motivo e exatamente o que se precisa saber depois.
    """
    print(f"[FALHA] {contexto}: {detalhe}", file=sys.stderr, flush=True)
    if not avisar:
        return
    try:
        st.warning(f"⚠️ {contexto} — {detalhe}")
    except Exception:
        pass


def registrar_falha(contexto: str, erro: BaseException, *, avisar: bool = True) -> None:
    """Registra a falha no log do servidor e, por padrao, avisa na tela.

    contexto -- o que estava sendo feito ("carregar Colaboradores")
    avisar   -- False para o que nao deve incomodar o usuario (ex: log de
                acesso). Mesmo assim vai para o log do servidor.

    Cuidado conhecido: dentro de funcao com @st.cache_data o aviso so aparece
    quando o cache erra — em acerto de cache a funcao nem roda. Por isso o log
    no stderr vem sempre, e e onde vale procurar (Manage app -> Logs).
    """
    mensagem = f"[FALHA] {contexto}: {type(erro).__name__}: {erro}"
    print(mensagem, file=sys.stderr, flush=True)

    if not avisar:
        return
    try:
        st.warning(f"⚠️ Falha ao {contexto} — {type(erro).__name__}: {erro}")
    except Exception:
        # Fora do ciclo de render do Streamlit (thread, script solto) nao ha
        # onde desenhar. O stderr acima ja garantiu o registro.
        pass
