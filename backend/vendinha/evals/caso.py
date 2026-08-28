"""Um caso de eval, tipado — porque um caso malformado reprova pelo motivo errado.

`evals/schema/caso.schema.json` é normativo e `tests/unit/test_eval_corpus_is_traceable.py`
valida o corpus inteiro contra ele. Aqui o YAML vira objeto, com contrato Pydantic
como em qualquer outra fronteira deste projeto (CLAUDE.md).

O que este módulo NÃO faz é decidir o critério. O critério mora dentro do caso —
não existe arquivo de rubric neste repositório, e afrouxar um caso para destravar
um PR é violação do ADR-006.
"""

from collections.abc import Iterable
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

Familia = Literal["golden", "adversarial"]
FalhaDura = Literal["fato_inventado", "acao_fora_da_allowlist"]

# O estado que a conversa do caso PRESSUPÕE e não cria. Declarado desde a S-04, e
# não inferido: até então o runner adivinhava "catálogo envenenado" pela presença
# de um turno `de: sistema` — regra que funcionava porque só um caso a usava, e que
# quebraria em silêncio no segundo (`golden-010`, cujo turno de sistema descreve um
# webhook e seria lido como envenenamento).
#
# `nota_emitida` chegou na S-06, e e o unico que atravessa o HITL inteiro: pedido
# pago, decisao do operador registrada, nota emitida por `fiscal.emitir` — que rele
# as duas precondicoes do banco. Fabricar a `NotaEmitida` a mao encurtaria o
# cenario e testaria o cenario, nao o produto.
Cenario = Literal["catalogo_envenenado", "composicao_aprovada", "pedido_pago", "nota_emitida"]


class Fala(BaseModel):
    """Um turno da conversa do caso.

    `de: sistema` não é uma mensagem: é a **descrição legível** de um cenário. Quem
    manda no runner é o campo `cenario` do caso, desde a S-04 — o turno de sistema
    continua ali porque é o que faz o YAML se explicar a quem lê, mas nada é
    inferido dele. Um turno de sistema sem `cenario` declarado é texto, e o runner
    o ignora.

    `de: operador` **é** uma mensagem, mas não para o agente: é a decisão de quem
    aprova ou rejeita a nota, e o runner a entrega ao port `fiscal` em vez de ao
    grafo da conversa. Foi recusada até a S-06 — *"a fila do operador é entregável
    da S-05"* —, o que deixou quatro casos sem execução (DESC-5 da S-05).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    de: Literal["cliente", "operador", "sistema"]
    texto: str


class FatoAncorado(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    campo: str
    origem: str

    @property
    def tool(self) -> str:
        """`tool:consultar_preco` → `consultar_preco`."""
        return self.origem.removeprefix("tool:")


class Criterio(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    deve: tuple[str, ...]
    nao_deve: tuple[str, ...]
    fatos_ancorados: tuple[FatoAncorado, ...] = ()
    falha_dura: FalhaDura | None = None


class Tools(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    permitidas: tuple[str, ...] = ()
    proibidas: tuple[str, ...] = ()


class Caso(BaseModel):
    """Um caso de `evals/`, como o schema normativo o define."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    familia: Familia
    titulo: str
    riscos: tuple[str, ...]
    spec: str
    conversa: tuple[Fala, ...]
    criterio: Criterio
    cenario: Cenario | None = None
    requisitos: tuple[str, ...] = ()
    produtos_validos: tuple[str, ...] = ()
    tools: Tools = Tools()
    notas: str | None = None


def carregar_casos(diretorio: Path, spec: str | None = None) -> tuple[Caso, ...]:
    """Todos os casos de `evals/`, opcionalmente só os de uma spec.

    Lê `golden/` e `adversarial/` juntos. O REQ-5 fala em "6 casos golden" e os
    casos que declaram `spec: S-03` são cinco golden mais o `adversarial-004` —
    filtrar por família aqui deixaria de fora justamente o caso que prova a
    injeção vinda do catálogo, que é o vetor específico do RAG.
    """
    arquivos: Iterable[Path] = sorted(
        arquivo
        for familia in ("golden", "adversarial")
        for arquivo in (diretorio / familia).glob("*.yaml")
    )
    casos = []
    for arquivo in arquivos:
        with arquivo.open(encoding="utf-8") as handle:
            casos.append(Caso.model_validate(yaml.safe_load(handle)))
    if spec is not None:
        casos = [caso for caso in casos if caso.spec == spec]
    return tuple(sorted(casos, key=lambda caso: caso.id))
