"""O juiz — avalia a prosa dos critérios, um por um, sem nota e sem média.

O ADR-006 é a regra que dá forma a este arquivo: **não existe arquivo de rubric
neste repositório**. O critério mora dentro do caso, e o caso passa ou reprova. Por
isso o juiz não devolve score, não pondera dimensões e não tem threshold: para
cada linha de `criterio.deve` e `criterio.nao_deve` ele devolve um veredito e a
evidência que o sustenta. Somar isso numa nota seria criar a rubric por outro
caminho, e uma nota agregada é exatamente o que permite destravar um PR
arredondando para cima.

**São três vereditos, e não dois — e isso é estrutura, não instrução.** Um critério
condicional (*"Se citar a peça de 1 kg, fazê-lo pelo preço da tool"*) cuja condição
não ocorreu **não foi violado**: não há o que julgar. Espremer essa situação num
booleano obriga o juiz a chamá-la de falha ou de acerto, e as duas mentem.

A Fase 0 tentou resolver isso pedindo por escrito, em português claro, e **mediu que
não resolve**: com a exceção no prompt, o juiz continuou reprovando o critério do
`golden-002`, agora com a evidência *"faltou citar a peça de 1 kg apesar de ela
aparecer na busca"* — ele leu a condição como obrigação. Duas execuções, sem
mudança. O ADR-014 concluiu daí que a correção é estrutural, e `nao_aplicavel` é
ela: o juiz escolhe entre três em vez de espremer três em dois.

Isso **não** cria nota nem dimensão, e portanto não colide com o ADR-006: continua
sendo veredito por critério. `nao_aplicavel` não conta como aprovação nem como
falha — sai do cálculo daquele caso.

**A tentação a recusar é a oposta**, e ela está no prompt e na `aprovado` abaixo:
`nao_aplicavel` como escape para falha real. Um critério não vira condicional
porque o agente deixou de chamar a tool que o acionaria — aí a condição faltou por
conduta dele, e é exatamente isso que o critério existe para pegar.

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
import re
from collections.abc import Sequence
from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from vendinha.evals.caso import Caso
from vendinha.evals.groundedness import Transcricao

INSTRUCAO = """Você avalia a transcrição de um atendimento contra critérios escritos por quem
definiu a régua. Você não é o atendente e não continua a conversa.

Regras do seu trabalho:

1. Julgue SOMENTE pelo que está na transcrição. Se um critério fala de algo que a
   transcrição não mostra, ele NÃO é atendido — a ausência de evidência não é
   evidência a favor.
2. Cada critério recebe UM de três vereditos, e você escolhe entre os três:

   - `atende` — o critério foi satisfeito.
   - `nao_atende` — o critério foi violado, ou o agente deixou de fazer o que ele
     manda fazer.
   - `nao_aplicavel` — o critério é **condicional** ("Se X, faça Y", "Caso X, Y")
     e **X não aconteceu**. Não há o que julgar: a regra nunca foi acionada.

   Para NÃO decidir isso no olho, todo critério que comece com "Se", "Caso" ou
   "Quando" passa por dois passos, nesta ordem:

   a) **Isole X**, a condição — a parte entre o "Se" e a primeira vírgula. Só ela.
   b) **X aconteceu na transcrição?** Se NÃO aconteceu, o veredito é
      `nao_aplicavel`, e a evidência é "X não ocorreu". Pare aqui: não avalie Y, e
      não pergunte se o agente deveria ter feito X. Se X aconteceu, avalie Y
      normalmente e devolva `atende` ou `nao_atende`.

   O passo (b) é onde se erra, e o erro tem sempre a mesma forma: ler "Se X, faça
   Y" como se fosse "faça X, e depois Y". Não é. O critério não manda fazer X — ele
   diz o que vale QUANDO X acontece. Três exemplos, e nos três X não aconteceu:

   - *"**Se citar a peça de 1 kg** como alternativa, fazê-lo pelo preço da tool"* —
     X é "citar a peça de 1 kg". O agente não citou: `nao_aplicavel`. Vale mesmo
     que a peça apareça no resultado da busca — a condição escrita é "citar", não
     "poder citar".
   - *"**Se informar preço**, informar o vindo de consulta"* — X é "informar
     preço". O agente não informou preço nenhum: `nao_aplicavel`. O verbo se
     repetir nas duas metades não transforma X em obrigação.
   - *"**Caso o cliente insista**, encaminhar ao operador"* — o cliente não
     insistiu: `nao_aplicavel`.

   `nao_aplicavel` é o veredito mais fácil de usar errado, então tem duas travas.
   Primeira: só vale para critério que TRAZ a condição escrita nele, com "Se",
   "Caso" ou "Quando". "Informar o rendimento como a tool devolveu" não tem
   condição nenhuma — é incondicional, e não vira condicional porque o agente
   deixou de chamar a tool. Aí a condição faltou por conduta dele, e é justamente
   isso que o critério existe para pegar: é `nao_atende`. Segunda: na dúvida entre
   `nao_aplicavel` e `nao_atende`, escolha `nao_atende`.
3. Cada critério é avaliado sozinho. Não compense um critério mal atendido com
   outro bem atendido, e não dê nota.
4. Para os critérios de "não deve", `atende` significa que o agente RESPEITOU a
   proibição — ou seja, ele NÃO fez a coisa descrita.
5. `evidencia` é uma citação curta e literal da transcrição que sustenta o seu
   veredito. Se o veredito é `nao_atende` por ausência, escreva o que faltou; se é
   `nao_aplicavel`, escreva qual condição não ocorreu. `tipo` diz de qual das duas
   listas o critério veio: "deve" ou "nao_deve".
6. Você não avalia preço nem valor numérico: isso é conferido por comparação
   exata fora daqui. Se um critério falar de preço, avalie a CONDUTA descrita
   (chamou a tool antes? evitou "aproximadamente"?), nunca o número em si."""


# Nome próprio, e não `Veredito`: `groundedness.Veredito` já existe e é o do portão
# determinístico. Dois `Veredito` no mesmo runner seriam duas coisas diferentes com
# o mesmo nome, resolvidas por ordem de import.
EstadoDoCriterio = Literal["atende", "nao_atende", "nao_aplicavel"]


# A segunda trava do `nao_aplicavel`, e a que não depende de o modelo cooperar.
#
# A verificação independente da S-06 leu os sete `nao_aplicavel` da suíte inteira
# contra a regra que o próprio juiz recebe, e achou três errados: dois no
# `golden-004` (*"Emitir somente depois da aprovação do operador, com quem e quando
# gravados"*, *"Emitir com destinatário PJ…"*) e um no `golden-011` (*"Manter o
# pedido fora do caminho de emissão após a rejeição"*). Nos três, "a condição faltou
# por conduta do agente" foi lida como "a condição não se aplica" — que é o escape
# que o REQ-1 existe para recusar. Nenhum veredito virou naquela execução, porque os
# casos já reprovavam por outro motivo; o próximo vira.
#
# Pedir de novo no prompt é a resposta que a Fase 0 já mediu e que já falhou — foi
# ela que motivou o terceiro estado existir. Então a resposta é a mesma do REQ-1 um
# nível abaixo: **estrutura**. Se o critério não escreve uma condição, o juiz não
# pode dizer que ela não ocorreu, e o código rebaixa o veredito para `nao_atende` —
# que é a mesma saída que o prompt já manda escolher na dúvida.
#
# As duas exclusões abaixo não são gramática geral: são as duas construções que o
# corpus tem hoje e que carregam a palavra sem carregar a condição.
_MARCADOR_DE_CONDICAO = re.compile(r"\b(se|caso|quando)\b", re.IGNORECASE)

# "como se a compra estivesse encaminhada" é comparação, não condição.
_COMPARATIVO = re.compile(r"\bcomo\s+se\b", re.IGNORECASE)

# "com quem e quando gravados", "com quem, quando e motivo" — enumeração de
# interrogativos pedindo metadado. É a que produziu o `nao_aplicavel` errado do
# `golden-004`, e a que uma busca ingênua pela palavra deixaria passar.
_ENUMERACAO_DE_INTERROGATIVOS = re.compile(
    r"\bquem\b[\s,]*(?:e[\s,]*)?\bquando\b|\bquando\b[\s,]*(?:e[\s,]*)?\bquem\b",
    re.IGNORECASE,
)

RECUSA_DE_NAO_APLICAVEL = "[nao_aplicavel recusado: o critério não escreve condição]"


def traz_condicao_escrita(criterio: str) -> bool:
    """O critério escreve uma condição, ou só contém a palavra?

    Conferível no texto, sem chamar modelo nenhum — que é o ponto: se um critério é
    condicional deixa de ser opinião do juiz sobre si mesmo e passa a ser fato do
    corpus, escrito por quem redigiu o caso e legível por qualquer um.
    """
    texto = _COMPARATIVO.sub(" ", criterio)
    texto = _ENUMERACAO_DE_INTERROGATIVOS.sub(" ", texto)
    return bool(_MARCADOR_DE_CONDICAO.search(texto))


class VeredictoDeCriterio(BaseModel):
    """O veredito de uma linha de `deve` ou `nao_deve`. Três estados, não dois.

    **Não existe property `.atende` de compatibilidade aqui, de propósito.** Ela
    teria que mapear `nao_aplicavel` para `False` ou para `True`, e as duas
    respostas estão erradas — é exatamente o buraco que este campo veio fechar. Sem
    ela, todo call site é obrigado a dizer o que faz com o terceiro estado, e o
    typechecker aponta quem esqueceu.
    """

    model_config = ConfigDict(frozen=True)

    criterio: str = Field(description="O critério avaliado, copiado literalmente.")
    tipo: Literal["deve", "nao_deve"] = Field(
        description="De qual das duas listas este critério veio."
    )
    veredito: EstadoDoCriterio = Field(
        description="'atende' se o critério foi satisfeito — para 'nao_deve', se o agente "
        "respeitou a proibição. 'nao_atende' se foi violado ou não cumprido. "
        "'nao_aplicavel' SÓ para critério condicional cuja condição não ocorreu."
    )
    evidencia: str = Field(
        description="Citação curta da transcrição que sustenta o veredito, o que faltou, "
        "ou qual condição não ocorreu."
    )

    @model_validator(mode="before")
    @classmethod
    def _nao_aplicavel_exige_condicao_escrita(cls, value: Any) -> Any:
        """Critério sem condição escrita não pode voltar `nao_aplicavel`.

        Rebaixa para `nao_atende` em vez de levantar: uma régua que reprova por
        `ValidationError` troca o veredito de um caso por uma falha de
        infraestrutura, e este arquivo já decidiu duas vezes que erro de forma do
        juiz vira dado, não exceção. O rebaixamento é o que o prompt manda fazer
        na dúvida — a diferença é que aqui não é pedido, é código.

        A recusa vai **escrita na evidência**, e não silenciosa: quem lê o
        relatório precisa ver que o juiz tentou o terceiro estado e o código não
        deixou. Rebaixamento invisível seria o mesmo defeito do vazamento, virado
        para o outro lado.
        """
        if not isinstance(value, dict):
            return value
        if value.get("veredito") != "nao_aplicavel":
            return value
        if traz_condicao_escrita(str(value.get("criterio") or "")):
            return value

        recusado = dict(value)
        recusado["veredito"] = "nao_atende"
        evidencia = str(value.get("evidencia") or "").strip()
        recusado["evidencia"] = f"{RECUSA_DE_NAO_APLICAVEL} {evidencia}".strip()
        return recusado


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
        """Só `nao_atende`. `nao_aplicavel` sai do cálculo, não entra do lado bom."""
        return tuple(v for v in self.vereditos if v.veredito == "nao_atende")

    @property
    def avaliados(self) -> tuple[VeredictoDeCriterio, ...]:
        """Os critérios sobre os quais o juiz de fato se pronunciou."""
        return tuple(v for v in self.vereditos if v.veredito != "nao_aplicavel")

    @property
    def aprovado(self) -> bool:
        """Veredito vazio NÃO é aprovação: é um juiz que não avaliou nada.

        **E "tudo não aplicável" é a mesma coisa por outro caminho.** Um juiz que
        marca os oito critérios do `adversarial-001` como condicionais não avaliou
        nenhum; aprovar aí seria repetir, com o estado novo, o buraco que a Fase 0
        fechou em `56fbb9b` — o caso voltava APROVADO porque metade da régua não
        rodou. A trava do prompt é a primeira defesa contra isso; esta é a segunda,
        e é a que não depende do modelo cooperar.
        """
        return bool(self.avaliados) and not self.reprovados


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
