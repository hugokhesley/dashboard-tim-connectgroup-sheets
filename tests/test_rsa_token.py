"""Token vinculado a dispositivo: device ID por conta e falha em claro.

O bug que motivou isso nao era o token quebrar — era ele NAO quebrar: sem device
ID o .sdtid vinculado gera 8 digitos perfeitamente formados que a TIM recusa, e
o log so dizia "sessao nao chegou no radar-blue". Estes testes travam as duas
garantias que evitam a volta disso: o ID nunca vaza de uma conta para outra, e
device ID errado vira erro falado em vez de OTP silenciosamente invalido.
"""

import os
import sys
import types

# ── stubs das dependencias pesadas (mesmo padrao dos outros testes) ──
for mod in ("securid", "securid.sdtid", "securid.exceptions"):
    sys.modules.setdefault(mod, types.ModuleType(mod))


class InvalidSignature(Exception):
    pass


sys.modules["securid.exceptions"].InvalidSignature = InvalidSignature

# Registra qual device ID chegou em get_token e se o MAC foi desligado.
chamadas = []


class SdtidFileFalso:
    # Setado pelo teste: se verdadeiro, get_token levanta InvalidSignature.
    mac_falha = False

    def __init__(self, path):
        self.path = path
        self.mac_verificado = True

    def verify_mac(self, *a, **k):  # pragma: no cover - substituido no caminho "solto"
        pass

    def get_token(self, password=None):
        # `verify_mac` sobrescrito NA INSTANCIA == caminho do token solto.
        chamadas.append({"password": password, "mac_desligado": "verify_mac" in self.__dict__})
        if type(self).mac_falha:
            raise InvalidSignature("MAC check failed")
        return types.SimpleNamespace(pin=None, now=lambda: "12345678")


sys.modules["securid.sdtid"].SdtidFile = SdtidFileFalso

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rsa_token as R  # noqa: E402

ARQUIVO_QUE_EXISTE = os.path.abspath(__file__)


def _limpar_env():
    for chave in list(os.environ):
        if chave.startswith("RSA_DEVICE_ID"):
            del os.environ[chave]


def teste_device_id_vem_do_secret_da_conta():
    _limpar_env()
    os.environ["RSA_DEVICE_ID_T3761125"] = "DEV-ABC"
    assert R.device_id("t3761125") == "DEV-ABC"
    assert R.device_id("T3761125") == "DEV-ABC", "login e case-insensitive"


def teste_device_id_nao_vaza_para_outra_conta():
    """O ponto mais importante do arquivo.

    t3729525 e t3748937 ainda usam token SOLTO e logam bem hoje. Se o ID da
    t3761125 escorresse para elas, o MAC delas passaria a ser verificado com a
    chave errada e derrubariamos duas contas que funcionam para consertar uma.
    """
    _limpar_env()
    os.environ["RSA_DEVICE_ID_T3761125"] = "DEV-ABC"
    assert R.device_id("t3729525") is None
    assert R.device_id("t3748937") is None


def teste_sem_secret_nenhum_e_token_solto():
    _limpar_env()
    assert R.device_id("t3761125") is None
    assert R.device_id("") is None


def teste_nao_existe_fallback_global():
    """`RSA_DEVICE_ID` sem sufixo nao vale para ninguem — de proposito."""
    _limpar_env()
    os.environ["RSA_DEVICE_ID"] = "DEV-GLOBAL"
    assert R.device_id("t3761125") is None


def teste_token_solto_ignora_mac_e_nao_passa_password():
    _limpar_env()
    chamadas.clear()
    SdtidFileFalso.mac_falha = False
    assert R.gerar_token(ARQUIVO_QUE_EXISTE, login="t3729525") == "12345678"
    assert chamadas[-1]["password"] is None
    assert chamadas[-1]["mac_desligado"], "token solto precisa seguir ignorando o MAC"


def teste_token_vinculado_passa_device_id_e_cobra_o_mac():
    _limpar_env()
    os.environ["RSA_DEVICE_ID_T3761125"] = "DEV-ABC"
    chamadas.clear()
    SdtidFileFalso.mac_falha = False
    assert R.gerar_token(ARQUIVO_QUE_EXISTE, login="t3761125") == "12345678"
    assert chamadas[-1]["password"] == "DEV-ABC"
    assert not chamadas[-1]["mac_desligado"], "token vinculado NAO pode ignorar o MAC"


def teste_device_id_errado_falha_falando():
    _limpar_env()
    os.environ["RSA_DEVICE_ID_T3761125"] = "DEV-ERRADO"
    SdtidFileFalso.mac_falha = True
    try:
        R.gerar_token(ARQUIVO_QUE_EXISTE, login="t3761125")
    except RuntimeError as e:
        assert "RSA_DEVICE_ID_T3761125" in str(e), "o erro tem que dizer QUAL secret conferir"
        assert "device ID" in str(e)
    else:
        raise AssertionError("device ID errado tem que estourar, nao gerar OTP invalido")
    finally:
        SdtidFileFalso.mac_falha = False


def teste_arquivo_ausente_fala_o_caminho():
    _limpar_env()
    try:
        R.gerar_token("nao_existe_T9999999.sdtid", login="t3761125")
    except RuntimeError as e:
        assert "nao_existe_T9999999.sdtid" in str(e)
    else:
        raise AssertionError("arquivo ausente tem que estourar")


if __name__ == "__main__":
    testes = [v for k, v in sorted(globals().items()) if k.startswith("teste_")]
    for t in testes:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(testes)} testes passaram")
