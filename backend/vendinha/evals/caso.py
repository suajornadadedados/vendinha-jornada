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


class Fala(BaseModel):
    """Um turno da conversa do caso.

    `de: sistema` não é uma mensagem: é uma montagem de cenário, e o único caso da
    S-03 que a usa é o `adversarial-004` — o texto descreve o que uma descrição de
    produto passa a conter. O runner o trata como envenenamento do catálogo, não
    como fala.
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
