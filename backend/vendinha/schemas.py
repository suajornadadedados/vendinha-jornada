"""Pydantic contracts for the HTTP boundary.

Every boundary in this project is typed (CLAUDE.md), and the reason is narrower
than "good practice": these models are what FastAPI turns into OpenAPI, and the
OpenAPI is what generates the TypeScript client in S-07 (ADR-004). A field that is
loose here becomes a loose type in the frontend three specs from now.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, SecretStr, StringConstraints

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
