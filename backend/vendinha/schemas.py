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

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StringConstraints

from vendinha.pedidos import ComposicaoDoPedido, Endereco

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
