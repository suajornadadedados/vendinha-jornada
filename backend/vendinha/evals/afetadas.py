"""Que sub-suítes um diff pode ter mudado — o mapa do ADR-014, em código.

O portão de evals roda em camadas, e esta é a peça que decide o escopo da camada 1:
dada a lista de arquivos que o PR tocou, quais sub-suítes precisam rodar.

**O eixo é o código tocado, nunca a spec do PR.** Uma mudança em
`PROMPT_RECOMENDACAO` afeta os casos da S-02, da S-03, da S-11 e da S-04, porque as
quatro passam por aquela lane — e o PR que a fez pode ser de qualquer spec. Mapear
por "de qual spec é este PR" deixaria passar exatamente a regressão que a R7 nomeia:
*nada quebra, o teste unitário continua verde e o atendimento piora*.

**Arquivo não mapeado ⇒ roda tudo, e essa é a regra que torna o mapa honesto.** Ele
só pode errar para o lado caro. Um arquivo novo que ninguém classificou não abre
buraco no portão: encarece o PR até alguém classificá-lo, que é a pressão certa. A
alternativa — não-mapeado significa "nada a rodar" — faria o mapa envelhecer em
silêncio, e o silêncio é o modo de falha que este repositório recusa em voz alta.

**Isto está em Python, e não dentro do `evals-ci.sh`, por uma razão só:** o ADR-014
exige teste unitário sobre o mapa, e um `case` de shell não tem como ser exercitado
por `pytest`. O script chama esta função e formata o resultado.

Ver `docs/adr/ADR-014-gate-de-evals-em-camadas.md`, seção "O mapa, e a regra que o
torna honesto" — a tabela de lá é a fonte, e esta aqui é a transcrição dela.
"""

import sys
from collections.abc import Iterable, Sequence

# Toda sub-suíte que existe. Derivada do corpus em `carregar_casos`? Não: escrita à
# mão, porque este conjunto é o que "roda tudo" significa, e derivá-lo do corpus
# faria um caso novo com uma `spec` digitada errado inventar uma sub-suíte que
# ninguém decidiu — e ela rodaria vazia, verde, sem nada avisar.
TODAS = frozenset({"S-02", "S-03", "S-04", "S-05", "S-11"})

# O que NÃO pode ter mudado o comportamento do agente. Prefixos, e a lista é curta
# de propósito: cada entrada aqui é uma promessa de que mexer ali não muda um caso
# de eval, e promessa larga é como um buraco entra sem ninguém notar.
#
# `docs/` inclui as specs e os ADRs; `.claude/` é o harness; `frontend/` fala com a
# API por contrato gerado e não com o agente. `evals/` NÃO está aqui — mexer num
# caso ou no schema roda tudo, o que é o oposto de "não afeta nada".
INERTES: tuple[str, ...] = (
    "docs/",
    ".claude/",
    "frontend/",
    ".github/",
    ".vscode/",
    # As duas camadas de teste. Elas **verificam** o agente, não o constroem: nada
    # em `tests/` está no caminho de uma conversa. `tests/security/` parametriza a
    # partir de `evals/adversarial/*.yaml`, mas quem o roda é o job `test` — a
    # camada 0 do ADR-014, que roda em todo PR e não custa nada.
    "tests/",
)

# O mapa propriamente dito: prefixo de caminho → sub-suítes que ele pode ter mudado.
#
# A ordem importa na leitura, não na avaliação: o casamento é por prefixo mais
# longo, para `tools/catalogo.py` não ser lido como `tools/checkout.py` por acaso de
# ordenação de dicionário.
MAPA: dict[str, frozenset[str]] = {
    # O agente inteiro. Prompt, grafo, teto de sessão, provedor e configuração
    # atravessam todas as lanes — não existe sub-suíte que uma mudança aqui não
    # possa ter mexido.
    "backend/vendinha/subagents.py": TODAS,
    "backend/vendinha/graph.py": TODAS,
    "backend/vendinha/budget.py": TODAS,
    "backend/vendinha/providers.py": TODAS,
    "backend/vendinha/config.py": TODAS,
    # Todo fato que a régua confere sai do catálogo: preço, atributo, alérgeno,
    # rendimento, disponibilidade. Uma mudança na ingestão ou no seed muda o que
    # é verdade, e portanto o que é "fato sem origem".
    "backend/vendinha/catalogo.py": TODAS,
    "backend/vendinha/tools/catalogo.py": TODAS,
    "backend/vendinha/ingest.py": TODAS,
    "data/catalogo/": TODAS,
    # A régua medindo a si mesma. Runner, juiz, portão determinístico, casos e
    # schema: qualquer um deles muda como TODA sub-suíte é avaliada.
    "evals/": TODAS,
    "backend/vendinha/evals/": TODAS,
    # Roteamento entre as duas lanes. Só a S-04 tem o supervisor no caminho.
    "backend/vendinha/supervisor.py": frozenset({"S-04"}),
    # Composição de evento: a S-11 a mede diretamente, e a S-04 a atravessa para
    # chegar ao pedido.
    "backend/vendinha/composicao.py": frozenset({"S-11", "S-04"}),
    "backend/vendinha/tools/composicao.py": frozenset({"S-11", "S-04"}),
    # Pedido, pagamento e as tools de escrita. A S-05 entra porque os cenários
    # `pedido_pago` e `nota_emitida` são construídos por `criar_pedido` e
    # `registrar_pagamento` — se eles mudarem, a pré-condição dela muda junto.
    "backend/vendinha/pedidos.py": frozenset({"S-04", "S-05"}),
    "backend/vendinha/pagamento.py": frozenset({"S-04", "S-05"}),
    "backend/vendinha/tools/checkout.py": frozenset({"S-04", "S-05"}),
    # O HITL e o documento fiscal.
    "backend/vendinha/fiscal.py": frozenset({"S-05"}),
    "backend/vendinha/nota/": frozenset({"S-05"}),
    # Mascaramento e instrumentação: é o que o `adversarial-003` ataca.
    "backend/vendinha/redaction.py": frozenset({"S-02"}),
    "backend/vendinha/observability.py": frozenset({"S-02"}),
}


def sub_suites_afetadas(arquivos: Iterable[str]) -> frozenset[str]:
    """As sub-suítes que este diff pode ter mudado.

    Caminhos relativos à raiz do repositório, com `/` como separador — é o que
    `git diff --name-only` devolve, inclusive no Windows.

    Diff vazio devolve vazio, e isso é diferente de "não mapeado": um PR sem
    arquivo nenhum não tem o que avaliar, e o script sai dizendo isso. Um PR com um
    arquivo que o mapa não conhece roda tudo.
    """
    afetadas: set[str] = set()
    for arquivo in arquivos:
        # `removeprefix`, e nunca `lstrip("./")`: `lstrip` remove um CONJUNTO de
        # caracteres, então `.claude/agents/...` viraria `claude/agents/...`, não
        # casaria com nenhum inerte, e um PR que só mexe no harness passaria a
        # rodar a suíte inteira. Descoberto pelo teste, e não pela leitura.
        caminho = arquivo.replace("\\", "/").removeprefix("./")
        if not caminho:
            continue
        if caminho.startswith(INERTES):
            continue
        # Prefixo mais longo primeiro: `backend/vendinha/evals/` tem de vencer
        # `backend/vendinha/` se algum dia existir uma entrada assim, e
        # `tools/catalogo.py` não pode casar por acidente com outra coisa.
        casou = max(
            (prefixo for prefixo in MAPA if caminho.startswith(prefixo)),
            key=len,
            default=None,
        )
        if casou is None:
            # Não mapeado: roda tudo. Sair cedo aqui é seguro — nada que venha
            # depois pode aumentar o conjunto além de TODAS.
            return TODAS
        afetadas |= MAPA[casou]
    return frozenset(afetadas)


def main(argv: Sequence[str] | None = None) -> int:
    """`python -m vendinha.evals.afetadas` — os nomes de arquivo vêm do stdin.

    Existe para `scripts/evals-ci.sh` não precisar embutir um `python -c` com
    aspas e quebras de linha dentro de uma substituição de shell. Aquela forma
    funcionava no Ubuntu do CI e **quebrava no Git Bash do Windows** — e quebrava
    da pior maneira: a invocação falhava, a variável do shell ficava vazia, e o
    script saía 0 dizendo *"nada a avaliar neste diff"*. Portão que fica verde
    porque não conseguiu rodar é o modo de falha que este arquivo inteiro existe
    para não ter.

    `--todas` imprime a suíte inteira, para a camada 2 e para o caso em que o
    script não consegue resolver a base do diff.
    """
    argumentos = list(sys.argv[1:] if argv is None else argv)
    if argumentos == ["--todas"]:
        print(" ".join(sorted(TODAS)))
        return 0
    if argumentos:
        print(
            f"uso: python -m vendinha.evals.afetadas [--todas]  (achei {argumentos})",
            file=sys.stderr,
        )
        return 2
    print(" ".join(sorted(sub_suites_afetadas(linha.strip() for linha in sys.stdin))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["INERTES", "MAPA", "TODAS", "main", "sub_suites_afetadas"]
