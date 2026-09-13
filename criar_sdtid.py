"""Escreve os .sdtid em disco a partir dos secrets em base64.

Roda como primeiro passo dos workflows que fazem login no Radar. Antes isso era
um `python -c` inline copiado nos três, cada um com uma variação — e a variação
custou caro: nenhum deles limpava o BOM.

O base64 é gerado no Windows e colado à mão no GitHub. O `| clip` do PowerShell
prefixa um BOM (`﻿`) invisível, que vai junto no Ctrl+V e faz o
`b64decode` estourar com "string argument should contain only ASCII characters"
antes de o RSA sequer entrar em cena (13/09/2026, run 34769895204). Limpar aqui
é mais barato do que confiar que o próximo Ctrl+V venha limpo.

Secret ausente não é erro: a conta simplesmente não roda (o recover depende
disso). Secret PRESENTE e inválido é erro — e falando o que fazer, em vez de um
traceback de base64 que não diz nada a quem está com pressa.
"""

import base64
import os
import sys

# login -> nome do arquivo em disco. O serial vai no nome por convenção da TIM;
# quando uma conta reseta e muda de serial, muda aqui e no CONTAS/PARCEIROS.
ARQUIVOS = [
    ("SDTID_T3729525_B64", "T3729525_001938489117.sdtid"),
    ("SDTID_T3761125_B64", "T3761125_001938495279.sdtid"),
    ("SDTID_T3748937_B64", "T3748937_001938491397.sdtid"),
]


def limpar(valor: str) -> str:
    """Tira BOM e espaços/quebras que sobram de copiar e colar."""
    return valor.lstrip("﻿").strip()


def escrever(var: str, destino: str) -> bool:
    bruto = os.environ.get(var, "")
    if not limpar(bruto):
        print(f"  · {var} não configurado — conta fora desta rodada")
        return False

    try:
        dados = base64.b64decode(limpar(bruto), validate=True)
    except Exception as e:
        print(f"::error::{var} não é base64 válido ({e}).")
        print("::error::Regere com [Convert]::ToBase64String([IO.File]::ReadAllBytes(...))")
        print("::error::e cole no secret sem quebras de linha.")
        raise SystemExit(1)

    # Um .sdtid é XML. Se decodificou mas não é XML, o secret tem outra coisa
    # dentro — vale gritar agora, e não 4 minutos depois num login recusado.
    if not dados.lstrip().startswith(b"<?xml"):
        print(f"::error::{var} decodificou mas não parece um .sdtid (esperava XML).")
        raise SystemExit(1)

    with open(destino, "wb") as f:
        f.write(dados)
    print(f"  ✓ {destino} ({len(dados)} bytes)")
    return True


if __name__ == "__main__":
    escritos = sum(escrever(var, destino) for var, destino in ARQUIVOS)
    if not escritos:
        print("::error::Nenhum SDTID configurado — nenhuma conta pode logar.")
        sys.exit(1)
    print(f"{escritos} de {len(ARQUIVOS)} arquivos SDTID criados")
