"""Escrita dos .sdtid a partir dos secrets: tolera o lixo do copiar e colar.

O secret e gerado no Windows e colado a mao. O `| clip` do PowerShell prefixa um
BOM invisivel que foi junto no Ctrl+V e derrubou tres runs em 13/09/2026 com
"string argument should contain only ASCII characters" — um erro que nao tem
nada a ver com RSA e mandou a investigacao para o lado errado.
"""

import base64
import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(RAIZ, "criar_sdtid.py")

XML = b'<?xml version="1.0"?><TKNBatch><TKN><SN>001938495279</SN></TKN></TKNBatch>'
B64 = base64.b64encode(XML).decode()

ARQUIVOS = [
    "T3729525_001938489117.sdtid",
    "T3761125_001938495279.sdtid",
    "T3748937_001938491397.sdtid",
]


def _rodar(**secrets):
    env = {k: v for k, v in os.environ.items() if not k.startswith("SDTID_")}
    env.update(secrets)
    r = subprocess.run([sys.executable, SCRIPT], env=env, cwd=RAIZ,
                       capture_output=True, text=True, encoding="utf-8")
    return r


def _limpar():
    for nome in ARQUIVOS:
        caminho = os.path.join(RAIZ, nome)
        if os.path.exists(caminho):
            os.remove(caminho)


def teste_base64_limpo_escreve_os_tres():
    _limpar()
    r = _rodar(SDTID_T3729525_B64=B64, SDTID_T3761125_B64=B64, SDTID_T3748937_B64=B64)
    assert r.returncode == 0, r.stdout + r.stderr
    for nome in ARQUIVOS:
        assert open(os.path.join(RAIZ, nome), "rb").read() == XML
    _limpar()


def teste_bom_do_clip_nao_derruba():
    """O caso real: `| clip` no PowerShell prefixa \\ufeff e o b64decode estoura."""
    _limpar()
    r = _rodar(SDTID_T3729525_B64=B64,
               SDTID_T3761125_B64="﻿" + B64 + "\r\n",
               SDTID_T3748937_B64=B64)
    assert r.returncode == 0, r.stdout + r.stderr
    escrito = open(os.path.join(RAIZ, "T3761125_001938495279.sdtid"), "rb").read()
    assert escrito == XML, "o BOM nao pode entrar no arquivo nem derrubar a decodificacao"
    _limpar()


def teste_secret_ausente_nao_e_erro():
    """Conta sem secret so fica fora da rodada — o recover depende disso."""
    _limpar()
    r = _rodar(SDTID_T3729525_B64=B64, SDTID_T3748937_B64=B64)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not os.path.exists(os.path.join(RAIZ, "T3761125_001938495279.sdtid"))
    _limpar()


def teste_nenhum_secret_e_erro():
    _limpar()
    r = _rodar()
    assert r.returncode == 1
    assert "Nenhum SDTID configurado" in r.stdout


def teste_base64_invalido_fala_o_que_fazer():
    _limpar()
    r = _rodar(SDTID_T3761125_B64="isso nao e base64 @@@@")
    assert r.returncode == 1
    assert "SDTID_T3761125_B64" in r.stdout
    assert "ToBase64String" in r.stdout, "o erro tem que dizer como regerar"


def teste_conteudo_que_nao_e_sdtid_e_recusado():
    """Secret com outra coisa dentro grita agora, nao num login recusado depois."""
    _limpar()
    r = _rodar(SDTID_T3761125_B64=base64.b64encode(b"nada a ver").decode())
    assert r.returncode == 1
    assert "nao parece um .sdtid" in r.stdout or "não parece um .sdtid" in r.stdout


if __name__ == "__main__":
    testes = [v for k, v in sorted(globals().items()) if k.startswith("teste_")]
    for t in testes:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(testes)} testes passaram")
