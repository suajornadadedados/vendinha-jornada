"""A imagem do Qdrant e o `qdrant-client` não podem andar sozinhos.

**Este arquivo não fecha risco da matriz, e não declara `risco` de propósito.**
`riscos_cobertos` da S-08 é `[]`; marcar um R# aqui só para o teste parecer
importante inverteria o mapa de `docs/testes.md` §2, que é justamente o que
permite responder "qual teste prova este risco" sem ler implementação. Um
marcador falso é pior que marcador nenhum.

O que ele fecha é a **RS-6** da verificação independente da S-03, endereçada
nominalmente à S-08:

    qdrant-client preso ao minor da imagem (D-7): subir a imagem do compose
    passa a exigir commit nos dois lugares. Não há teste nem check que force isso

O acoplamento existe desde a S-03 e era mantido **por comentário**: o
`pyproject.toml` diz "preso ao MESMO minor da imagem do compose", e nada além
da atenção de quem lê garantia isso. O sintoma de deixar divergir já aconteceu
uma vez — o resolvedor trouxe a 1.19.0 e toda ingestão passou a imprimir aviso
de incompatibilidade —, e é da mesma classe do D-16 da S-02: régua que anda de
um lado só.

A S-08 é onde isto tinha que ser resolvido porque ela cria o **segundo** lugar
onde a imagem aparece. Antes havia um compose; agora há dois, e um upgrade
distraído pode acertar um e esquecer o outro — o de deploy, que é o que roda
longe de quem edita.

Sem rede e sem contêiner: lê os três arquivos que já estão no repositório.
"""

import re
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

COMPOSES = (
    REPO_ROOT / "docker-compose.yml",
    REPO_ROOT / "deploy" / "docker-compose.yml",
)
PYPROJECT = REPO_ROOT / "backend" / "pyproject.toml"

# `qdrant/qdrant:v1.13.6` -> ("1", "13")
IMAGEM = re.compile(r"^\s*image:\s*qdrant/qdrant:v(\d+)\.(\d+)\.", re.MULTILINE)
# `qdrant-client>=1.13,<1.14` -> ("1", "13", "1", "14")
CLIENTE = re.compile(r"qdrant-client>=(\d+)\.(\d+),<(\d+)\.(\d+)")


def _minor_da_imagem(compose: Path) -> tuple[int, int]:
    achados = IMAGEM.findall(compose.read_text(encoding="utf-8"))
    assert achados, f"{compose.name} não declara uma imagem `qdrant/qdrant:vX.Y.Z`"
    assert len(achados) == 1, f"{compose.name} declara a imagem do Qdrant mais de uma vez"
    maior, menor = achados[0]
    return int(maior), int(menor)


def _faixa_do_cliente() -> tuple[tuple[int, int], tuple[int, int]]:
    with PYPROJECT.open("rb") as arquivo:
        pyproject = tomllib.load(arquivo)

    linhas = [
        dependencia
        for dependencia in pyproject["project"]["dependencies"]
        if dependencia.startswith("qdrant-client")
    ]
    assert len(linhas) == 1, "esperava exatamente uma linha de `qdrant-client` em dependencies"

    casado = CLIENTE.match(linhas[0])
    assert casado, (
        f"`{linhas[0]}` não está na forma `qdrant-client>=X.Y,<X.Y+1`. "
        "O teto é o que impede o resolvedor de subir de minor sozinho (S-03, D-7)."
    )
    piso_maior, piso_menor, teto_maior, teto_menor = (int(g) for g in casado.groups())
    return (piso_maior, piso_menor), (teto_maior, teto_menor)


def test_every_compose_pins_the_same_qdrant_image() -> None:
    """Os dois compose usam a MESMA imagem do Qdrant.

    O de deploy roda longe de quem edita: divergir aqui produz um ambiente que
    indexa contra uma versão e desenvolve contra outra, e a diferença aparece
    como busca ruim, não como erro.

    **Sem `parametrize`, e isso é o conserto de um teste que não mordia.** A
    primeira versão parametrizava sobre `COMPOSES` e comparava cada um contra
    `COMPOSES[0]` — que é um dos parametrizados. O caso da raiz virava
    `assert x == x`: passava por construção, e o relatório do pytest mostrava
    **dois** casos onde havia uma verificação só. Apontado pela verificação
    independente da S-08 (RS-1); é exatamente a vacuidade que `docs/testes.md`
    §3.3 recusa, em escala pequena.
    """
    # Sem isto, `len(set(...)) == 1` seria verdadeiro para um conjunto de UM
    # elemento: se algum dia sobrar um compose só, o teste ficaria verde sem
    # comparar nada. É a mesma vacuidade que a rodada 1 apontou, num gatilho
    # diferente — apontada pela rodada 2 (RS-3).
    assert len(COMPOSES) >= 2, "este teste compara compose; com menos de dois não há comparação"

    minors = {compose: _minor_da_imagem(compose) for compose in COMPOSES}

    assert len(set(minors.values())) == 1, (
        "os compose divergiram na imagem do Qdrant: "
        + ", ".join(f"{c.parent.name}/{c.name} v{ma}.{me}" for c, (ma, me) in minors.items())
    )


@pytest.mark.parametrize("compose", COMPOSES, ids=lambda caminho: caminho.parent.name)
def test_the_qdrant_client_is_pinned_to_the_minor_of_the_image(compose: Path) -> None:
    """O `qdrant-client` cobre o minor da imagem, e só ele.

    Duas asserções, e a segunda é a que morde: o piso precisa **casar** com a
    imagem (senão o cliente é mais velho que o servidor), e o teto precisa ser o
    minor seguinte (senão o resolvedor sobe sozinho, que é o que já aconteceu).
    """
    imagem = _minor_da_imagem(compose)
    piso, teto = _faixa_do_cliente()

    assert piso == imagem, (
        f"a imagem em {compose.name} é v{imagem[0]}.{imagem[1]} e o `qdrant-client` "
        f"começa em {piso[0]}.{piso[1]}. Subir a imagem é um commit que mexe nos dois lugares."
    )
    assert teto == (imagem[0], imagem[1] + 1), (
        f"o teto do `qdrant-client` é <{teto[0]}.{teto[1]}, que não é o minor seguinte a "
        f"v{imagem[0]}.{imagem[1]}. Sem o teto certo o resolvedor traz um minor novo sem "
        "que nada no repositório mude."
    )
