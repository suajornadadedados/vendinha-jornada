"""Pydantic contracts for the HTTP boundary.

Every boundary in this project is typed (CLAUDE.md), and the reason is narrower
than "good practice": these models are what FastAPI turns into OpenAPI, and the
OpenAPI is what generates the TypeScript client in S-07 (ADR-004). A field that is
loose here becomes a loose type in the frontend three specs from now.
"""

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

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
