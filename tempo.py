"""Relogio da operacao. Todo "hoje" e "agora" do sistema sai daqui.

O Streamlit Cloud e o GitHub Actions rodam com o relogio em UTC. Brasilia e
UTC-3, entao das 21h a meia-noite o servidor ja esta no dia seguinte: no dia
31, as 22h, `datetime.now()` devolve dia 01 do mes que vem. As paginas que
filtram pelo mes vigente (Tramitacao Atual, Performance, Consolidada) passavam
a olhar um mes sem venda nenhuma e as ativacoes do dia sumiam da tela.

As funcoes daqui devolvem datetime/date NAIVE, ja convertidos para o horario de
Brasilia, para serem substitutos diretos de `datetime.now()` e `date.today()` —
o resto do codigo compara com datas naive lidas da planilha.

Quem precisa de UTC de verdade (carimbo de log, escala de conta no runner) usa
`datetime.now(timezone.utc)` explicitamente e nao passa por aqui.
"""

from datetime import date, datetime, timedelta, timezone

# O Brasil nao tem horario de verao desde 2019, entao UTC-3 fixo esta correto
# hoje. Ainda assim preferimos o banco de fusos quando ele existe: se o DST
# voltar, a conta continua certa sem mexer no codigo. No Windows sem o pacote
# `tzdata` o zoneinfo nao acha a zona — dai o fallback.
try:
    from zoneinfo import ZoneInfo

    FUSO = ZoneInfo("America/Sao_Paulo")
except Exception:  # pragma: no cover - depende do SO ter o banco de fusos
    FUSO = timezone(timedelta(hours=-3), name="America/Sao_Paulo")


def em_brasilia(instante_utc: datetime) -> datetime:
    """Converte um instante UTC para o horario de Brasilia, sem tzinfo.

    Separada de `agora()` so para o teste conseguir fixar o instante.
    """
    return instante_utc.astimezone(FUSO).replace(tzinfo=None)


def agora() -> datetime:
    """Agora em Brasilia, sem tzinfo. Substitui `datetime.now()`."""
    return em_brasilia(datetime.now(timezone.utc))


def hoje() -> date:
    """Data de hoje em Brasilia. Substitui `date.today()`."""
    return agora().date()


def mes_atual() -> str:
    """Mes vigente em Brasilia no formato "MM/AAAA" usado nos filtros."""
    return agora().strftime("%m/%Y")
