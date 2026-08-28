"""Pydantic contracts for the HTTP boundary.

Every boundary in this project is typed (CLAUDE.md), and the reason is narrower
than "good practice": these models are what FastAPI turns into OpenAPI, and the
OpenAPI is what generates the TypeScript client in S-07 (ADR-004). A field that is
loose here becomes a loose type in the frontend three specs from now.

S-05 brought the first models here that **reuse** domain types — `Endereco` and
`ComposicaoDoPedido` — instead of restating them. The operator queue exists so a
person can check what the invoice will read, item by item; a second projection of
the same rows would be the one that goes stale, and then the queue would be showing
one thing while the emitter reads another. Reuse is not laziness here, it is the
requirement (RF-3.2).
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StringConstraints

from vendinha.pedidos import ComposicaoDoPedido, Endereco
from vendinha.tools.composicao import ComposicaoValidada

# `strip_whitespace` before `min_length` is the whole point: a message of three
# spaces is an empty message, and refusing it in the contract keeps the check out
# of the handler, where it would be an `if` somebody eventually deletes.
NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ChatRequest(BaseModel):
    """One customer turn."""

    message: NonEmptyText = Field(description="O que o cliente escreveu.")
    session_id: str | None = Field(
        default=None,
        description=(
            "Identificador da conversa. Ausente na primeira mensagem: o servidor gera um "
            "e devolve no primeiro evento do stream."
        ),
    )
    model: str | None = Field(
        default=None,
        description=(
            "Modelo a usar, no formato `provedor:modelo`. Precisa estar entre os que "
            "`GET /models` devolve — texto livre aqui deixaria o cliente escolher para "
            "qual fornecedor o servidor autentica e quanto gasta (ADR-012)."
        ),
    )


class SessionEvent(BaseModel):
    """First event of every stream, so the client can continue the conversation."""

    session_id: str


class TokenEvent(BaseModel):
    """One chunk of the answer.

    JSON-encoded rather than raw text on the SSE `data:` line: a token that happens
    to contain a newline would otherwise be split across two events and silently
    change the message.
    """

    text: str


class DoneEvent(BaseModel):
    """End of stream. A client that never sees this one is still waiting."""

    session_id: str


class ErrorEvent(BaseModel):
    """Something failed mid-stream, after the HTTP status was already sent as 200."""

    detail: str


class HealthResponse(BaseModel):
    status: str


class ProviderStatus(BaseModel):
    """Whether a provider can be used — and never how.

    `hint` is the last four characters of the key. Enough for a person to recognise
    which credential is in place, useless to anyone who wants to spend it.
    """

    provider: str
    configured: bool
    source: Literal["banco", "ambiente", "nenhuma"]
    hint: str | None = None


class ConfigResponse(BaseModel):
    """The configuration as the API is allowed to describe it. No secrets, ever."""

    selected_model: str | None
    providers: list[ProviderStatus]
    editable: bool = Field(
        description=(
            "Se este ambiente aceita gravar configuracao. Fora de APP_ENV=local e "
            "`false` ate existir autenticacao — a rota guarda credencial (S-02, D-8)."
        )
    )
    encryption_ready: bool = Field(
        description="Se CONFIG_ENCRYPTION_KEY esta definida. Sem ela, gravar chave e recusado."
    )


class ConfigUpdate(BaseModel):
    """What the operator may change. Both fields optional, at least one required."""

    provider: str | None = Field(default=None, description="anthropic | openai")
    api_key: SecretStr | None = Field(
        default=None, description="Credencial do provedor. Nunca volta em nenhuma resposta."
    )
    model: str | None = Field(default=None, description="Modelo default, `provedor:modelo`.")


class ModelsResponse(BaseModel):
    """What the picker in the UI is offered — read from the providers, not from memory."""

    models: list[str]
    selected: str | None


class DadosDoEvento(BaseModel):
    """O `data` da notificação do Mercado Pago: o id do pagamento, e nada mais."""

    id: str


class NotificacaoDePagamento(BaseModel):
    """O corpo do webhook do Mercado Pago (S-04, RF-2.5).

    `extra="ignore"` de propósito: o gateway acrescenta campos com o tempo, e uma
    notificação recusada por um campo novo é um pagamento que fica sem efeito por
    um motivo que nada tem a ver com dinheiro. O que precisa estar presente está
    tipado; o resto passa.
    """

    model_config = ConfigDict(extra="ignore")

    type: str | None = Field(default=None, description="`payment` é o que nos interessa.")
    action: str | None = None
    data: DadosDoEvento


class WebhookProcessado(BaseModel):
    """O que a rota responde. Sempre 200 quando a origem confere.

    `resultado` distingue o que aconteceu sem transformar duplicata em erro: um
    gateway que recebe 4xx ou 5xx reenvia o evento, e reenviar é justamente o que
    a idempotência existe para tolerar.
    """

    resultado: Literal["registrado", "duplicado", "ignorado"]


class DestinatarioDaNota(BaseModel):
    """O comprador PJ como o operador precisa vê-lo para conferir a nota.

    **CNPJ em claro, e formatado.** É o oposto do que `mascarar_cnpj` faz no retorno
    de tool, e a diferença é o destinatário: lá o leitor é o modelo, e o número
    mascarado existe para não haver de onde copiá-lo para a resposta (ADR-007, R5).
    Aqui o leitor é a pessoa que vai autorizar a emissão, e conferir o documento **é
    o trabalho dela** — o `golden-011` rejeita uma nota justamente por um dado do
    destinatário. Uma fila com o CNPJ mascarado pediria uma decisão sobre um dado que
    ela não pode ler.
    """

    razao_social: str
    cnpj: str = Field(description="Formatado, para conferência humana.")
    inscricao_estadual: str = Field(
        description="Como sairá na nota: a IE informada, ou ISENTO quando não houver."
    )
    contato_nome: str
    contato_email: str
    endereco: Endereco


class PedidoNaFila(BaseModel):
    """Um pedido esperando decisão, com os dados completos da nota (RF-3.2).

    `composicoes` são os **modelos persistidos**, reusados e não reprojetados. É
    deliberado: o operador precisa ver item a item exatamente o que a nota vai ler,
    e uma segunda projeção do mesmo dado é a que fica velha — aprovando-se então uma
    coisa e emitindo-se outra.
    """

    pedido_id: str
    criado_em: datetime
    total: Decimal
    destinatario: DestinatarioDaNota
    composicoes: tuple[ComposicaoDoPedido, ...]


class FilaDoOperador(BaseModel):
    """A fila inteira, do mais antigo para o mais novo."""

    pendentes: tuple[PedidoNaFila, ...]


class DecisaoDoOperador(BaseModel):
    """O corpo de aprovar e de rejeitar. Um contrato para as duas rotas.

    `motivo` é opcional aqui e **obrigatório na rejeição** — quem impõe isso é
    `fiscal.Aprovacao`, não esta classe. Duas classes quase iguais fariam o cliente
    TypeScript da S-07 ter dois tipos para o mesmo formulário, e a regra continuaria
    valendo no servidor de qualquer jeito.
    """

    operador: NonEmptyText = Field(
        description=(
            "Quem está decidindo. Gravado como veio: este projeto ainda não tem "
            "autenticação, então é uma declaração, não uma identidade provada."
        )
    )
    motivo: str | None = Field(
        default=None, description="Obrigatório na rejeição — é o que o cliente recebe."
    )


class DecisaoRegistrada(BaseModel):
    """O que a rota responde depois de decidir — e o que **valeu**.

    Pode não ser a decisão que acabou de chegar: a primeira vence (a chave primária
    de `aprovacao_de_nf`). Um segundo operador clicando em "aprovar" num pedido já
    rejeitado recebe de volta a rejeição, com quem e quando, em vez de um 200 que o
    faria acreditar que aprovou.
    """

    pedido_id: str
    decisao: Literal["aprovada", "rejeitada"]
    operador: str
    decidido_em: datetime
    motivo: str | None = None
    numero_nota: int | None = Field(
        default=None, description="Preenchido quando a emissão já aconteceu."
    )
    chave_da_nota: str | None = None


# ---------------------------------------------------------------------------
# Os eventos do painel (S-07)
#
# Ficam aqui, e não em `eventos.py`, porque são contrato de fronteira como todo o
# resto deste arquivo: eles saem por SSE e viram tipos TypeScript. Espalhar eventos
# de SSE por dois módulos deixaria `SessionEvent` e `TokenEvent` de um lado e estes
# do outro, sem que a divisão dissesse nada.
#
# `tipo` é literal em todos e é o discriminador da união — e é também o nome do
# `event:` na linha do SSE, para que o cliente não precise inspecionar o corpo para
# saber o que chegou.
# ---------------------------------------------------------------------------


class SessaoIniciada(BaseModel):
    """Uma conversa nova apareceu. É o que faz a linha surgir na lista do painel."""

    tipo: Literal["sessao_iniciada"] = "sessao_iniciada"
    em: datetime
    session_id: str
    canal: str


class MensagemRegistrada(BaseModel):
    """Uma fala completa, do cliente ou do atendente.

    O painel recebe a fala do atendente **inteira**, no fim do turno, e não token a
    token como o cliente. O cliente espera a frase se formar porque é a conversa
    dele; o operador está olhando uma lista de conversas, e streaming em todas ao
    mesmo tempo é ruído que nenhuma decisão usa.
    """

    tipo: Literal["mensagem"] = "mensagem"
    em: datetime
    session_id: str
    papel: Literal["cliente", "atendente"]
    texto: str


class ComposicaoAvaliada(BaseModel):
    """O veredito do validador, **como ele voltou** — nunca reprojetado.

    É o evento que carrega a regra de ouro até a tela: o modelo propôs, o código
    respondeu isto, e o painel mostra a resposta do código. Reprojetar aqui seria
    dar ao painel a chance de discordar do validador.
    """

    tipo: Literal["composicao_avaliada"] = "composicao_avaliada"
    em: datetime
    session_id: str
    veredito: ComposicaoValidada


class PedidoAtualizado(BaseModel):
    """O pedido mudou de estado. `session_id` é o que permite avisar o cliente."""

    tipo: Literal["pedido_atualizado"] = "pedido_atualizado"
    em: datetime
    pedido_id: str
    session_id: str | None = None
    status: str
    total: Decimal
    razao_social: str


class AprovacaoPendente(BaseModel):
    """Uma nota entrou na fila e espera decisão humana. É a notificação do HITL.

    Deliberadamente magro: id, valor e razão social — o bastante para o sino tocar
    com contexto. O detalhe que autoriza a decisão continua vindo de
    `GET /operador/fila`, que é a projeção que o RF-3.2 governa. Um evento gordo
    seria uma segunda projeção da nota, e a que fica velha.
    """

    tipo: Literal["aprovacao_pendente"] = "aprovacao_pendente"
    em: datetime
    pedido_id: str
    total: Decimal
    razao_social: str


class NotaDecidida(BaseModel):
    """A decisão saiu. Com `session_id`, é o que faz o cartão da NF aparecer no chat."""

    tipo: Literal["nota_decidida"] = "nota_decidida"
    em: datetime
    pedido_id: str
    session_id: str | None = None
    decisao: Literal["aprovada", "rejeitada"]
    numero_nota: int | None = None
    motivo: str | None = None


class AtrasoNoStream(BaseModel):
    """Eventos foram descartados porque este assinante não os consumiu a tempo.

    Existe para que a tela possa dizer *"você perdeu N atualizações, recarregando"*
    em vez de seguir exibindo um estado furado. É o preço da fila limitada, e a
    alternativa — bloquear quem publica — faria um painel lento segurar a resposta
    de um cliente.
    """

    tipo: Literal["atraso"] = "atraso"
    em: datetime
    perdidos: int


EventoDoPainel = Annotated[
    SessaoIniciada
    | MensagemRegistrada
    | ComposicaoAvaliada
    | PedidoAtualizado
    | AprovacaoPendente
    | NotaDecidida
    | AtrasoNoStream,
    Field(discriminator="tipo"),
]


# ---------------------------------------------------------------------------
# O painel (S-07, ADR-015) — tudo leitura, tudo já somado no backend.
#
# A regra que governa esta seção: se um número aparece aqui, ele foi calculado em
# `Decimal` no servidor. O frontend formata; não soma. É métrica da spec, e é a
# forma mais fácil de furar a regra de ouro sem ninguém notar no diff.
# ---------------------------------------------------------------------------


class MensagemDaConversa(BaseModel):
    """Uma fala da conversa, lida do checkpointer — não de uma cópia nossa.

    `ferramenta` e `argumentos` existem para a tela de rastreabilidade: é ali que se
    vê **o que o modelo propôs** ao lado do que o código respondeu. Sem os
    argumentos, a proposta do modelo some e sobra só o veredito.
    """

    papel: Literal["cliente", "atendente", "ferramenta"]
    texto: str
    ferramenta: str | None = None
    argumentos: str | None = None


class CustoApurado(BaseModel):
    """O custo como a tela deve exibi-lo — inclusive quando não dá para saber.

    `completo` é falso quando algum modelo não tem preço ou algum turno não
    informou consumo. A tela que ignora esse campo apresenta um parcial como total,
    que é o modo de falha que o ADR-015 nomeia.
    """

    usd: Decimal | None = None
    brl: Decimal | None = None
    completo: bool = True
    modelos_sem_preco: tuple[str, ...] = ()
    turnos_sem_uso: int = 0


class UsoPorModelo(BaseModel):
    modelo: str
    tokens_entrada: int
    tokens_saida: int
    turnos: int


class ConversaNaLista(BaseModel):
    """Uma linha da lista de conversas."""

    session_id: str
    canal: str
    iniciada_em: datetime
    ultima_atividade: datetime
    turnos: int
    erros: int
    custo: CustoApurado
    pedido_id: str | None = None
    status_do_pedido: str | None = None


class PaginaDeConversas(BaseModel):
    conversas: tuple[ConversaNaLista, ...]


class TurnoDoPainel(BaseModel):
    """Um turno com o que ele custou e quanto o cliente esperou."""

    modelo: str
    tokens_entrada: int | None = None
    tokens_saida: int | None = None
    primeiro_token_ms: int | None = None
    duracao_ms: int
    iniciado_em: datetime
    erro: bool
    custo: CustoApurado


class VeredictoNoPainel(BaseModel):
    """Uma passagem pelo validador, como ele a devolveu."""

    aprovada: bool
    tipo_de_evento: str
    pessoas: int
    total: Decimal
    valor_por_pessoa: Decimal
    motivos: tuple[str, ...] = ()
    avaliado_em: datetime


class DetalheDaConversa(BaseModel):
    """A conversa inteira para a tela de rastreabilidade."""

    resumo: ConversaNaLista
    mensagens: tuple[MensagemDaConversa, ...]
    turnos: tuple[TurnoDoPainel, ...]
    vereditos: tuple[VeredictoNoPainel, ...]
    uso: tuple[UsoPorModelo, ...]
    mensagens_indisponiveis: bool = Field(
        default=False,
        description=(
            "Verdadeiro quando o checkpointer não devolveu a conversa. A tela diz "
            "isso em vez de mostrar uma conversa vazia como se fosse curta."
        ),
    )


class PedidoNoPainel(BaseModel):
    """Um pedido como a tela de pedidos o lista e detalha."""

    pedido_id: str
    criado_em: datetime
    status: str
    total: Decimal
    razao_social: str
    cnpj: str
    url_pagamento: str | None = None
    composicoes: tuple[ComposicaoDoPedido, ...] = ()
    status_nf: str
    numero_nota: int | None = None
    url_danfe: str | None = None
    url_xml: str | None = None


class PaginaDePedidos(BaseModel):
    pedidos: tuple[PedidoNoPainel, ...]


class RecusaDoValidador(BaseModel):
    motivo: str
    recusas: int


class Metricas(BaseModel):
    """Os KPIs da janela. Cada número já somado, e cada ausência explícita."""

    janela: str
    desde: datetime

    conversas: int
    conversas_com_pedido: int
    taxa_de_conversao: Decimal | None = None
    turnos: int
    turnos_por_conversa: Decimal | None = None
    atendimento_medio_ms: int | None = None
    erros_de_stream: int

    uso: tuple[UsoPorModelo, ...] = ()
    custo: CustoApurado = CustoApurado()

    primeiro_token_p50_ms: int | None = None
    primeiro_token_p95_ms: int | None = None
    primeiro_token_alvo_ms: int = Field(
        default=3000, description="RNF-4. Vai no contrato para a régua aparecer na tela."
    )

    pedidos: int
    receita: Decimal
    ticket_medio: Decimal | None = None
    custo_sobre_ticket: Decimal | None = Field(
        default=None,
        description=(
            "Custo de LLM como fração da receita. `None` sem cotação do dólar "
            "configurada — comparar dólar com real por uma taxa inventada seria pior "
            "que não comparar."
        ),
    )

    fila_pendentes: int
    decisoes: int
    aprovadas: int
    taxa_de_aprovacao: Decimal | None = None

    recusas_do_validador: tuple[RecusaDoValidador, ...] = ()


class PromptVigente(BaseModel):
    """Um prompt do agente, em modo leitura. Nunca editável — ADR-015.

    `sha` é do texto, não do arquivo: é o que permite conferir numa demo que o
    prompt em memória é o do commit, sem abrir o repositório.
    """

    subagent: str
    texto: str
    arquivo: str
    sha: str
    ferramentas: tuple[str, ...] = ()


class PromptsDoAgente(BaseModel):
    prompts: tuple[PromptVigente, ...]
    editavel: Literal[False] = Field(
        default=False,
        description=(
            "Sempre falso, em todo ambiente. Prompt muda por PR com evals — editá-lo "
            "em runtime contornaria o portão do ADR-014 (ADR-015)."
        ),
    )
    tabela_de_precos_atualizada_em: date | None = None
