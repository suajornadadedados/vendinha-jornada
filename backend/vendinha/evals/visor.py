"""O Langfuse como **visor** da régua — nunca como portão (ADR-014).

Comparar duas execuções é o que se faz com um relatório de eval, e até aqui isso
era abrir dois markdown lado a lado. Este módulo põe o resultado onde a comparação
é barata: dataset run por execução, trace por caso, score booleano por caso.

Quatro regras dão forma ao arquivo, e cada uma fecha uma porta.

**O veredito continua sendo o exit code do runner.** O Langfuse oferece uma action
de CI que levanta `RegressionError` sobre um threshold, e ela está recusada por
duas razões: o veredito sairia do repositório para dentro de um número — a rubric
que o ADR-006 recusou de frente — e o merge passaria a depender de um SaaS estar
de pé. O ADR-010 aceitou um terceiro na observabilidade **com** a cláusula de que
ele nunca derruba o atendimento; pôr o portão atrás dele seria a mesma aposta sem
a mesma cláusula. O agregado que a UI mostra é artefato de visor, e um "87%" na
tela é exatamente o número que alguém citaria um dia para liberar um PR vermelho.

**A sincronização é de mão única: `evals/` → Langfuse, nunca de volta.** O dataset
lá é uma projeção do corpus, indexada pelo `id` do caso. Editar um item na UI não
muda veredito nenhum — o portão lê o YAML do repositório, que é o que o CODEOWNERS
protege. Não existe função de leitura aqui, e a ausência é a garantia.

**O cliente é o do projeto, e isso não é detalhe de estilo.** `observability.client()`
é o que carrega `mask_otel_spans`; um `Langfuse()` default exportaria as conversas
de eval — com o CNPJ e o e-mail de `EMPRESA_DO_CENARIO`, e com tudo que o cliente
de teste disser — sem redação nenhuma. Desde o ADR-010 o Langfuse é Cloud, então
isso sai da infra. `tests/security/test_evals_visor.py` afirma este parágrafo.

**Nada aqui levanta.** Langfuse fora do ar loga e segue: a suíte que já custou
dinheiro para rodar não pode reprovar porque o visor não respondeu (ADR-010). Toda
função pública devolve `None` ou não faz nada, e o relatório em markdown continua
saindo do runner como sempre saiu.
"""

import logging
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from vendinha import observability
from vendinha.evals.caso import Caso

if TYPE_CHECKING:  # pragma: no cover - só para o typechecker
    from vendinha.evals.runner import Resultado

logger = logging.getLogger(__name__)

# Onde os traces de eval vivem. Separado de produção de propósito (ADR-014): sem
# isso, 23 conversas sintéticas por execução entrariam na mesma janela de métricas
# que o atendimento de verdade, e a latência média do produto passaria a incluir a
# régua medindo o produto.
AMBIENTE = "evals"

# Um dataset por sub-suíte, e não um só com tudo. A execução do PR roda um
# subconjunto — é a camada 1 do ADR-014 —, e uma run com 6 de 23 itens num dataset
# único apareceria na UI como uma execução que deixou 17 casos de fora, que é
# indistinguível de uma que quebrou no meio.
PREFIXO_DO_DATASET = "vendinha-evals-"

# O nome do score. Um só, booleano, por caso — não uma família de scores por
# dimensão, que seria a rubric entrando pela porta dos fundos.
SCORE = "aprovado"


def nome_do_dataset(spec: str) -> str:
    return f"{PREFIXO_DO_DATASET}{spec.lower()}"


def nome_da_execucao(spec: str, modelo: str, quando: datetime | None = None) -> str:
    """O nome da run: quando, contra quem.

    Carrega o modelo porque é a primeira coisa que quem compara duas execuções
    precisa saber, e a que faltava no markdown até a Fase 0. O timestamp é UTC e
    tem segundos: duas execuções da mesma sub-suíte no mesmo minuto acontecem o
    tempo todo quando se está medindo variância, e colidir o nome faria a segunda
    sobrescrever a leitura da primeira.
    """
    agora = (quando or datetime.now(UTC)).strftime("%Y-%m-%dT%H-%M-%S")
    return f"{spec}-{agora}-{modelo.replace(':', '-')}"


def sincronizar(casos: Sequence[Caso], spec: str) -> str | None:
    """Projeta o corpus no dataset. Mão única, e idempotente pelo `id` do caso.

    `create_dataset` e `create_dataset_item` fazem upsert por nome/id, então rodar
    a suíte duas vezes não duplica item nenhum — e um caso editado no repositório
    reaparece corrigido na projeção, que é a direção certa da seta.

    O `expected_output` são os critérios do caso, e não uma resposta esperada:
    não existe resposta certa em texto aqui, existe conduta que atende ou não
    atende. Pôr uma frase-modelo ali convidaria alguém a comparar strings, que é
    exatamente o tipo de régua que o ADR-006 recusou.
    """
    cliente = observability.client()
    if cliente is None:
        return None

    dataset = nome_do_dataset(spec)
    try:
        cliente.create_dataset(
            name=dataset,
            description=(
                f"Projeção somente-leitura dos casos `spec: {spec}` de `evals/`. "
                f"A fonte da verdade é o YAML do repositório, protegido por CODEOWNERS: "
                f"editar um item aqui não muda veredito nenhum (ADR-006, ADR-014)."
            ),
        )
        for caso in casos:
            cliente.create_dataset_item(
                dataset_name=dataset,
                id=caso.id,
                input={"conversa": [{"de": f.de, "texto": f.texto} for f in caso.conversa]},
                expected_output={
                    "deve": list(caso.criterio.deve),
                    "nao_deve": list(caso.criterio.nao_deve),
                },
                metadata={
                    "riscos": list(caso.riscos),
                    "requisitos": list(caso.requisitos),
                    "familia": caso.familia,
                    "cenario": caso.cenario,
                    "falha_dura": caso.criterio.falha_dura,
                },
            )
    except Exception:
        logger.warning("nao consegui sincronizar o dataset %s; seguindo", dataset, exc_info=True)
        return None
    return dataset


def registrar(
    resultados: Sequence["Resultado"], spec: str, execucao: str, dataset: str | None
) -> None:
    """Um item de run e um score booleano por caso. Não levanta, aconteça o que for.

    O score é `aprovado`, e ele é o **mesmo booleano** que decide o exit code do
    runner — lido de `Resultado.aprovado`, não recalculado aqui. Recalcular criaria
    a segunda conta que a regra de ouro deste projeto existe para não ter, e a
    divergência entre a tela e o portão apareceria como "o Langfuse diz que passou".

    O `comment` carrega por que reprovou, porque um booleano vermelho sem motivo
    manda a pessoa de volta ao markdown — e o ponto de estar aqui é não precisar.
    """
    cliente = observability.client()
    if cliente is None or dataset is None:
        return

    registrados = 0
    for resultado in resultados:
        try:
            if resultado.trace_id is not None:
                cliente.api.dataset_run_items.create(
                    run_name=execucao,
                    dataset_item_id=resultado.caso.id,
                    trace_id=resultado.trace_id,
                    run_description=f"Sub-suite {spec} contra `{resultado.modelo}`.",
                    metadata={
                        "spec": spec,
                        "modelo": resultado.modelo,
                        "juiz": resultado.juiz_nome,
                    },
                )
            cliente.create_score(
                name=SCORE,
                value=resultado.aprovado,
                data_type="BOOLEAN",
                trace_id=resultado.trace_id,
                comment=_por_que(resultado),
                environment=AMBIENTE,
                metadata={"spec": spec, "execucao": execucao, "caso": resultado.caso.id},
            )
            registrados += 1
        except Exception:
            # Um caso que não chegou ao visor não pode contaminar os outros nem a
            # execução: o veredito já está decidido e o markdown já existe.
            logger.warning(
                "nao consegui registrar %s no Langfuse; seguindo", resultado.caso.id, exc_info=True
            )

    try:
        cliente.flush()
    except Exception:
        logger.warning("nao consegui esvaziar a fila do Langfuse; seguindo", exc_info=True)

    # **Em voz alta, e não só no log.** Este módulo engole toda exceção de
    # propósito — Langfuse fora do ar não reprova a suíte —, e o preço disso é que
    # ele quebra em silêncio: a S-06 mandou a primeira execução inteira para o
    # Langfuse com a chamada de dataset run errada, e a suíte "deu certo" com zero
    # runs do outro lado. Só apareceu porque alguém foi conferir à mão.
    #
    # Uma linha no stderr é o que torna a próxima quebra visível sem pôr o portão
    # atrás do SaaS. `registrados < len(resultados)` é o sinal, e a frase diz o que
    # fazer com ele.
    if registrados == len(resultados):
        print(f"visor: {registrados} casos em `{dataset}`, run `{execucao}`.", file=sys.stderr)
    else:
        print(
            f"AVISO: so {registrados} de {len(resultados)} casos chegaram ao Langfuse "
            f"(dataset `{dataset}`, run `{execucao}`). O veredito acima NAO depende "
            f"disso — mas o visor esta cego, e o log diz por que.",
            file=sys.stderr,
        )


def _por_que(resultado: "Resultado") -> str:
    """A frase que explica o booleano — a mesma informação que o markdown dá.

    Ordem deliberada: cenário que não montou vem primeiro, porque ele significa que
    o caso **não foi avaliado**, e é uma informação diferente de "o agente errou".
    A S-04 aprendeu do jeito caro que confundir os dois manda consertar a coisa
    errada.
    """
    if resultado.aprovado:
        return "aprovado"
    if resultado.erro_do_cenario is not None:
        return f"o cenario nao montou: {resultado.erro_do_cenario}"
    if resultado.erro_do_juiz is not None:
        return f"o juiz nao emitiu veredito: {resultado.erro_do_juiz}"
    if resultado.juiz is None:
        return "juiz nao executado (sem credencial): nenhum criterio em prosa foi avaliado"
    motivos = [f"fato sem origem: {achado}" for achado in resultado.portao.achados]
    motivos += [f"criterio nao atendido: {v.criterio}" for v in resultado.juiz.reprovados]
    return "; ".join(motivos) or "reprovado"


__all__ = [
    "AMBIENTE",
    "SCORE",
    "nome_da_execucao",
    "nome_do_dataset",
    "registrar",
    "sincronizar",
]
