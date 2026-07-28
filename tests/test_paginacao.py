"""Teste da varredura paginada do encontrar_relatorio_alvo, com driver falso.

Simula a fila do Radar: 3 páginas de 6 relatórios, parâmetro honrado = 'pagina'
(os outros nomes são IGNORADOS pelo ASP e devolvem sempre a página 1) — que é
exatamente o cenário que fez 2 contas reportarem "sumiu" em 27/jul.
"""
import sys, types, os

# ── stubs de dependências pesadas (não instaladas aqui) ──────────────
for mod in ("requests", "pandas", "gspread", "securid", "securid.sdtid",
            "google", "google.oauth2", "google.oauth2.service_account",
            "selenium", "selenium.webdriver", "selenium.webdriver.common",
            "selenium.webdriver.common.by", "selenium.webdriver.support",
            "selenium.webdriver.support.ui", "selenium.webdriver.chrome",
            "selenium.webdriver.chrome.options", "selenium.webdriver.chrome.service"):
    sys.modules.setdefault(mod, types.ModuleType(mod))
sys.modules["selenium.webdriver.support"].expected_conditions = types.ModuleType("ec")
sys.modules["selenium.webdriver.support.expected_conditions"] = types.ModuleType("ec")
sys.modules["selenium.webdriver.common.by"].By = type("By", (), {"XPATH": "xpath", "ID": "id", "NAME": "name"})
sys.modules["selenium.webdriver.support.ui"].WebDriverWait = object
sys.modules["securid.sdtid"].SdtidFile = type("SdtidFile", (), {"verify_mac": lambda *a, **k: None})
sys.modules["google.oauth2.service_account"].Credentials = object
os.environ.setdefault("SPREADSHEET_ID", "fake")
# roda de qualquer lugar: o script sob teste está na raiz do repo
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import actions_runner as R

# ── driver falso ─────────────────────────────────────────────────────
PAGINAS = {
    1: [781940, 781941, 781942, 781943, 781944, 781945],
    2: [781946, 781947, 781948, 781949, 781950, 781951],
    3: [781952, 781953, 781954],          # o alvo está aqui (página 3)
}
PARAM_HONRADO = "pagina"
PRONTOS = {781952}                        # só esse tem link de download


class Celula:
    def __init__(self, texto): self.text = texto


class Linha:
    def __init__(self, id_rel):
        self.id_rel = id_rel
        pronto = id_rel in PRONTOS
        self.text = f"{id_rel} Após 01/05/2009 {'Concluído' if pronto else 'Pendente'}"
        self._cels = [Celula(str(id_rel)), Celula("Após 01/05/2009"),
                      Celula("Concluído" if pronto else "Pendente"), Celula("1")]

    def find_elements(self, by, xpath):
        return self._cels

    def find_element(self, by, xpath):
        if self.id_rel in PRONTOS:
            return Celula(f"https://radar/report-queue-download.asp?id={self.id_rel}")
        raise Exception("sem link")


class DriverFalso:
    def __init__(self):
        self.pagina = 1
        self.current_url = R.URL_FILA
        self.gets = []

    def get(self, url):
        self.gets.append(url)
        self.current_url = url
        self.pagina = 1
        if "?" in url:
            qs = url.split("?", 1)[1]
            nome, _, valor = qs.partition("=")
            if nome == PARAM_HONRADO and valor.isdigit():
                self.pagina = min(int(valor), max(PAGINAS) + 1)

    def find_elements(self, by, xpath):
        if "report-queue-download" in xpath:
            return []
        return [Linha(i) for i in PAGINAS.get(self.pagina, [])]


def get_attribute_patch(self, _):
    return self.text
Celula.get_attribute = get_attribute_patch


def cenario(id_alvo, rotulo):
    R.links_capturados.clear()
    R.paginacao_param.clear()
    d = DriverFalso()
    d.get(R.URL_FILA)
    texto, link, estrategia = R.encontrar_relatorio_alvo(d, id_alvo, "t3729525")
    print(f"{rotulo}: estrategia={estrategia} link={'sim' if link else 'nao'} "
          f"paginas_visitadas={len(d.gets)} param_aprendido={R.paginacao_param.get('t3729525')}")
    return texto, link, estrategia, d


# 1) alvo na página 3 — antes o código só olhava a página 2 e devolvia "sumiu"
texto, link, est, d = cenario(781952, "alvo na pagina 3 (pronto)")
assert texto is not None, "NÃO achou o relatório na página 3"
assert est == "?pagina=3", est
assert link, "não capturou o link de download"
assert R.esta_pronto(texto), "linha deveria estar pronta"

# 2) alvo inexistente — precisa terminar (sem loop infinito) e com poucas requisições
texto2, link2, est2, d2 = cenario(999999, "alvo inexistente")
assert texto2 is None and est2 is None
assert len(d2.gets) < 20, f"varredura cara demais: {len(d2.gets)} requisições"

# 3) parâmetro aprendido evita redescoberta no poll seguinte
R.links_capturados.clear()
R.paginacao_param["t3729525"] = "pagina"
d3 = DriverFalso(); d3.get(R.URL_FILA)
R.encontrar_relatorio_alvo(d3, 781953, "t3729525")
primeiro_param = d3.gets[1].split("?")[1].split("=")[0]
assert primeiro_param == "pagina", f"não usou o param aprendido primeiro: {primeiro_param}"
print(f"param aprendido usado de cara: ?{primeiro_param}=...")

# 4) cache de link continua valendo
R.links_capturados["t3729525"] = "https://radar/cached"
t, l, e = R.encontrar_relatorio_alvo(DriverFalso(), 781952, "t3729525")
assert e == "cache" and l == "https://radar/cached"
print("cache de link: ok")

print("\nTODOS OS CENÁRIOS PASSARAM")
