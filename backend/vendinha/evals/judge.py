"""O juiz — avalia a prosa dos critérios, um por um, sem nota e sem média.

O ADR-006 é a regra que dá forma a este arquivo: **não existe arquivo de rubric
neste repositório**. O critério mora dentro do caso, e o caso passa ou reprova. Por
isso o juiz não devolve score, não pondera dimensões e não tem threshold: para
cada linha de `criterio.deve` e `criterio.nao_deve` ele devolve um booleano e a
evidência que o sustenta. Somar isso numa nota seria criar a rubric por outro
caminho, e uma nota agregada é exatamente o que permite destravar um PR
arredondando para cima.

**A evidência é obrigatória, e é ela que torna o veredito auditável.** Um juiz que
responde "não atende" e nada mais transfere o problema: alguém tem que reler a
conversa inteira para saber do que ele está falando. Com a citação, a
discordância com o juiz é uma conversa de trinta segundos.

**O juiz vê a transcrição, incluindo as chamadas de tool.** Sem isso ele não teria
como avaliar "chamar consultar_preco antes de dizer qualquer valor", que é
literalmente um critério do `golden-002`.

**O juiz não decide sobre preço.** Isso é `groundedness.py`, por igualdade exata:
pedir a um modelo que compare dois `Decimal` troca uma comparação por uma opinião.

**Agente e juiz devem ser modelos diferentes.** `EVALS_JUDGE_MODEL` existe para
isso. Sem ele configurado, o runner cai no `LLM_MODEL` e **avisa em voz alta**: um
modelo avaliando a própria saída é um viés conhecido, e a régua não pode escondê-lo
de quem lê o relatório.
"""

import json
from collections.abc import Sequence
from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from vendinha.evals.caso import Caso
from vendinha.evals.groundedness import Transcricao

INSTRUCAO = """Você avalia a transcrição de um atendimento contra critérios escritos por quem
definiu a régua. Você não é o atendente e não continua a conversa.

Regras do seu trabalho:

1. Julgue SOMENTE pelo que está na transcrição. Se um critério fala de algo que a
   transcrição não mostra, ele NÃO é atendido — a ausência de evidência não é
   evidência a favor.
2. Cada critério é avaliado sozinho. Não compense um critério mal atendido com
   outro bem atendido, e não dê nota: cada um é atendido ou não é.
3. Para os critérios de "não deve", `atende: true` significa que o agente
   RESPEITOU a proibição — ou seja, ele NÃO fez a coisa descrita.
4. `evidencia` é uma citação curta e literal da transcrição que sustenta o seu
   veredito. Se o veredito é "não atende" por ausência, escreva o que faltou.
   `tipo` diz de qual das duas listas o critério veio: "deve" ou "nao_deve".
5. Você não avalia preço nem valor numérico: isso é conferido por comparação
   exata fora daqui. Se um critério falar de preço, avalie a CONDUTA descrita
   (chamou a tool antes? evitou "aproximadamente"?), nunca o número em si."""


class VeredictoDeCriterio(BaseModel):
    """O veredito de uma linha de `deve` ou `nao_deve`."""

    model_config = ConfigDict(frozen=True)

    criterio: str = Field(description="O critério avaliado, copiado literalmente.")
    tipo: Literal["deve", "nao_deve"] = Field(
        description="De qual das duas listas este critério veio."
    )
    atende: bool = Field(
        description="Verdadeiro se o critério foi satisfeito. Para 'nao_deve', "
        "verdadeiro significa que o agente respeitou a proibição."
    )
    evidencia: str = Field(
        description="Citação curta da transcrição que sustenta o veredito, ou o que faltou."
    )


class VeredictoDoJuiz(BaseModel):
    """O veredito do caso inteiro, critério a critério. Sem nota, sem média.

    **Uma lista só, e não duas.** A primeira versão tinha `deve` e `nao_deve` como
    campos separados, e o `claude-haiku-4-5` — que é o modelo default da instância,
    portanto o juiz default — reprovou o schema na primeira execução de verdade:
    devolveu `deve` como *string* com o JSON dentro e omitiu `nao_deve` inteiro.
    Duas listas aninhadas dentro de um objeto é uma forma que modelo pequeno erra;
    uma lista plana de objetos, com o lado dito num campo, é uma forma que ele
    acerta.

    Ninguém teria descoberto isso lendo o código. Apareceu porque o eval rodou
    contra o agente antes do PR, que é a razão de o ritual existir.
    """

    vereditos: list[VeredictoDeCriterio] = Field(
        description="Um item para CADA critério das duas listas."
    )

    @field_validator("vereditos", mode="before")
    @classmethod
    def _aceita_a_lista_serializada_como_string(cls, value: Any) -> Any:
        """Aceita a lista chegando como JSON dentro de uma string.

        É a mesma falha do parágrafo acima, um nível abaixo, e a coerção é segura
        porque o conteúdo é idêntico — só está codificado duas vezes. Recusar
        seria trocar um veredito legítimo por uma reprovação de infraestrutura, e
        uma régua que não roda no modelo default não é régua, é enfeite.
        """
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value

    @property
    def deve(self) -> tuple[VeredictoDeCriterio, ...]:
        return tuple(v for v in self.vereditos if v.tipo == "deve")

    @property
    def nao_deve(self) -> tuple[VeredictoDeCriterio, ...]:
        return tuple(v for v in self.vereditos if v.tipo == "nao_deve")

    @property
    def reprovados(self) -> tuple[VeredictoDeCriterio, ...]:
        return tuple(v for v in self.vereditos if not v.atende)

    @property
    def aprovado(self) -> bool:
        """Veredito vazio NÃO é aprovação: é um juiz que não avaliou nada."""
        return bool(self.vereditos) and not self.reprovados


def formatar_transcricao(transcricao: Transcricao) -> str:
    """A conversa como o juiz a lê: fala do agente e chamada de tool, em ordem.

    As chamadas de tool aparecem como bloco explícito — sem elas, um critério como
    "chamar consultar_preco antes de dizer qualquer valor" não teria como ser
    avaliado por ninguém.
    """
    linhas = []
    for chamada in transcricao.chamadas:
        linhas.append(
            f"[tool] {chamada.tool}({json.dumps(chamada.argumentos, ensure_ascii=False)})"
        )
        linhas.append(f"[retorno] {json.dumps(chamada.retorno, ensure_ascii=False)}")
    for resposta in transcricao.respostas:
        linhas.append(f"[atendente] {resposta}")
    return "\n".join(linhas)


def _pedido(caso: Caso, transcricao: Transcricao, conversa_do_cliente: Sequence[str]) -> str:
    def enumerar(itens: Sequence[str]) -> str:
        return "\n".join(f"{i}. {item}" for i, item in enumerate(itens, start=1)) or "(nenhum)"

    return f"""## Caso
{caso.id} — {caso.titulo}

## O que o cliente disse
{chr(10).join(f"- {fala}" for fala in conversa_do_cliente)}

## Transcrição do atendimento
{formatar_transcricao(transcricao)}

## Critérios "deve" (o agente precisa ter feito)
{enumerar(caso.criterio.deve)}

## Critérios "não deve" (o agente precisa NÃO ter feito)
{enumerar(caso.criterio.nao_deve)}

Devolva um veredito para CADA critério das duas listas, numa lista só,
marcando em `tipo` de qual delas o critério veio."""


async def julgar(
    modelo: BaseChatModel,
    caso: Caso,
    transcricao: Transcricao,
    conversa_do_cliente: Sequence[str],
) -> VeredictoDoJuiz:
    """Avalia um caso. Saída estruturada, para o veredito não depender de parse de prosa.

    **Uma nova tentativa quando o schema não fecha.** Saída estruturada não é
    garantia: o juiz às vezes devolve um veredito sem um dos campos obrigatórios, e
    aí a régua reprova um agente que se comportou corretamente — que `docs/testes.md`
    chama da pior falha possível numa régua, porque ensina a desconfiar dela.

    Uma tentativa, não três: se o juiz erra o próprio schema duas vezes seguidas,
    isso é sinal sobre o juiz, e o `erro_do_juiz` do runner existe para dizer isso
    em vez de esconder. Insistir até passar transformaria um problema visível numa
    latência inexplicada.
    """
    juiz = modelo.with_structured_output(VeredictoDoJuiz)
    mensagens = [
        SystemMessage(content=INSTRUCAO),
        HumanMessage(content=_pedido(caso, transcricao, conversa_do_cliente)),
    ]

    try:
        resposta = await juiz.ainvoke(mensagens)
    except ValidationError:
        resposta = await juiz.ainvoke(mensagens)

    if not isinstance(resposta, VeredictoDoJuiz):  # pragma: no cover - contrato do provedor
        raise TypeError(f"o juiz devolveu {type(resposta).__name__}, esperado VeredictoDoJuiz")
    return resposta
