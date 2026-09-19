"""Token RSA SecurID das contas do Radar. Todo OTP do sistema sai daqui.

Desde 2026 o portal da TIM não gera mais `.sdtid` "solto": a geração exige um
"Identificador do dispositivo" e a semente sai cifrada com ele. Sem o ID o
arquivo AINDA abre e AINDA produz 8 dígitos — só que são os dígitos errados, e a
TIM recusa o login no iam-pf sem dizer o motivo. Foi o que derrubou a t3761125
em 13/09/2026: token gerado, `✅ Token gerado para T3761125` no log, e duas
tentativas morrendo em "sessão não chegou no radar-blue".

Quem denuncia isso pra gente é o MAC do próprio arquivo. A chave que decifra a
semente vem de `hash_password(device_id, Dest, Name)`, e o MAC só fecha se essa
chave estiver certa. Logo: **MAC batendo == device ID certo**, verificado
offline, sem depender de tentar logar no Radar. É por isso que aqui o MAC não é
mais ignorado quando existe device ID configurado — ele é justamente o teste.

O token antigo (solto) continua como sempre: sem device ID e com o MAC ignorado,
porque nos arquivos que a TIM emitiu antes da mudança ele não fecha e o login
funciona do mesmo jeito. Daí o device ID ser POR CONTA e não global: as contas
que ainda usam token solto não podem receber ID nenhum, senão quebram junto.
"""

import os

from securid.exceptions import InvalidSignature
from securid.sdtid import SdtidFile

PIN_PADRAO = 1234


def device_id(login: str) -> str | None:
    """Device ID do token dessa conta, ou None se ela ainda usa token solto.

    Vem do secret `RSA_DEVICE_ID_<LOGIN>` — ex.: `RSA_DEVICE_ID_T3761125`. O
    valor é o **login em maiúsculas**, não o Device Serial Number da máquina: o
    portal da TIM pede o serial na hora de gerar e grava ele em
    `<DeviceSerialNumber>`, mas quem decifra a semente (e fecha o MAC) é o
    login. Conferido em 19/09/2026 nos dois tokens vinculados. Não existe
    fallback global de propósito: um `RSA_DEVICE_ID` valendo para todas
    passaria o ID também para as contas de token solto e derrubaria as que hoje
    funcionam.
    """
    if not login:
        return None
    return os.environ.get(f"RSA_DEVICE_ID_{login.upper()}") or None


def _abrir_token(sdtid_path: str, dev_id: str | None):
    arquivo = SdtidFile(sdtid_path)
    if dev_id is None:
        # Token solto: o MAC desses arquivos não fecha e nunca fechou. Ignorar
        # só neste caminho preserva o comportamento que funciona nas outras
        # contas, sem estender a cegueira ao token vinculado.
        arquivo.verify_mac = lambda *a, **k: None
    return arquivo.get_token(dev_id)


def gerar_token(sdtid_path: str, pin: int = PIN_PADRAO, login: str = "") -> str:
    """OTP atual da conta, como string de 8 dígitos.

    Levanta RuntimeError com o motivo em claro quando o arquivo não existe ou
    quando o device ID configurado não corresponde ao token — os dois casos que
    antes viravam falha silenciosa de login.
    """
    if not os.path.exists(sdtid_path):
        raise RuntimeError(f"SDTID não encontrado: {sdtid_path}")

    dev_id = device_id(login)
    try:
        token_obj = _abrir_token(sdtid_path, dev_id)
    except InvalidSignature as e:
        raise RuntimeError(
            f"device ID não bate com o token {os.path.basename(sdtid_path)}: o MAC "
            f"do arquivo não fecha com o secret RSA_DEVICE_ID_{login.upper()}. "
            "Confira o valor contra o 'Identificador do dispositivo' usado ao gerar "
            "o token no portal da TIM (no app da RSA: Options > Token Storage "
            "Devices). Token gerado com este ID errado produz OTP válido na forma "
            "e recusado pela TIM."
        ) from e

    token_obj.pin = pin
    return token_obj.now()


def conferir(sdtid_path: str, dev_id: str) -> bool:
    """Diz se este device ID abre este .sdtid, sem tentar logar no Radar.

    O MAC fecha só com a chave certa, então isso responde offline a pergunta que
    antes só o Radar respondia — e respondia mal, com "sessão não chegou no
    radar-blue" 4 minutos depois. Não imprime semente nem OTP.
    """
    try:
        _abrir_token(sdtid_path, dev_id)
        return True
    except InvalidSignature:
        return False


def descrever(sdtid_path: str, login: str = "") -> str:
    """Uma linha sobre como a conta está configurada, para o log do Actions.

    Serve para separar, num run que falhou, "esta conta usa token vinculado e o
    ID está lá" de "esta conta está sem ID nenhum" — que é a diferença entre um
    ID errado e um secret que ninguém cadastrou.
    """
    vinculo = "vinculado (device ID presente)" if device_id(login) else "solto (sem device ID)"
    return f"{os.path.basename(sdtid_path)} — {vinculo}"


if __name__ == "__main__":
    # Uso: python rsa_token.py <arquivo.sdtid> <device_id>
    # Confere o par ANTES de cadastrar nos secrets. Só imprime veredito.
    import sys

    if len(sys.argv) != 3:
        print("uso: python rsa_token.py <arquivo.sdtid> <device_id>")
        raise SystemExit(2)

    caminho, ident = sys.argv[1], sys.argv[2]
    if not os.path.exists(caminho):
        print(f"❌ arquivo não encontrado: {caminho}")
        raise SystemExit(1)

    if conferir(caminho, ident):
        print(f"✅ device ID confere com {os.path.basename(caminho)} — pode cadastrar nos secrets")
        raise SystemExit(0)

    print(f"❌ device ID NÃO confere com {os.path.basename(caminho)}")
    print("   O MAC do arquivo não fecha com esse ID. Confira o 'Identificador do")
    print("   dispositivo' usado ao gerar o token no portal da TIM.")
    print("   (se este token for do formato antigo, solto, ele não tem device ID)")
    raise SystemExit(1)
