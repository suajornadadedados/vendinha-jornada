"""Gera o `openapi.json` sem subir servidor — é o portão de contrato da S-07.

    python -m vendinha.openapi            # grava openapi.json na raiz do repo
    python -m vendinha.openapi caminho.json

**Por que não `curl http://localhost:8000/openapi.json`.** Porque o cliente
TypeScript é gerado no build, e o build roda no CI. Um gerador que precisa da API
de pé transforma o portão de contrato num teste de integração — a camada que a
ADR-011 recusou — e um dia falha por causa do Postgres, não por causa do contrato.
`app.openapi()` é uma função pura sobre os modelos Pydantic: não abre conexão, não
lê credencial, não precisa de `lifespan`.

**Por que os eventos de SSE precisam de um empurrão.** O FastAPI descreve o corpo
que uma rota *retorna*, e as três rotas de stream retornam `EventSourceResponse` —
uma sequência de eventos, que o OpenAPI não tem como expressar. Sem o que este
módulo faz, `TokenEvent` e `AprovacaoPendente` simplesmente não existiriam no
schema, e o frontend teria de **digitar à mão** os tipos do stream. A métrica da
spec é "tipos de fronteira escritos à mão: 0", e o stream é a fronteira mais
movimentada que existe aqui.

Então o schema dos eventos é injetado em `components.schemas` e as três rotas
passam a declarar `text/event-stream` com a união que emitem. É pós-processamento
honesto: nada aqui inventa um campo que o servidor não manda.
"""

import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from vendinha.app import create_app
from vendinha.config import REPO_ROOT
from vendinha.schemas import (
    DoneEvent,
    ErrorEvent,
    EventoDoPainel,
    SessionEvent,
    TokenEvent,
)

REF = "#/components/schemas/{model}"
PADRAO = REPO_ROOT / "openapi.json"

# As três rotas que devolvem `text/event-stream`, e o que cada uma emite.
STREAMS: dict[str, tuple[str, str]] = {
    "/chat": (
        "EventosDoChat",
        "Stream do atendimento: `session` primeiro, `token` a cada pedaço da "
        "resposta, `error` quando falha depois do primeiro byte, e `done` sempre.",
    ),
    "/admin/eventos": (
        "EventoDoPainel",
        "Tudo que acontece no servidor, para o painel. O nome do `event:` é o campo "
        "`tipo`. Um `atraso` significa que este assinante perdeu eventos.",
    ),
    "/eventos/sessao/{session_id}": (
        "EventoDaSessao",
        "Só os eventos desta conversa: mudança de status do pedido e decisão da "
        "nota. É o que faz a NF aparecer no chat sem o cliente perguntar.",
    ),
}


class EventosDoChat(BaseModel):
    """Reúne os quatro eventos de `/chat` para que entrem no schema.

    Não é um corpo que alguma rota devolva: é o veículo que leva os quatro modelos
    até `components.schemas`. Está declarado como classe, e não montado à mão em
    dicionário, para que ele não possa divergir dos modelos que a rota realmente
    emite — se alguém acrescentar um campo em `TokenEvent`, este schema acompanha.
    """

    session: SessionEvent
    token: TokenEvent
    error: ErrorEvent
    done: DoneEvent


class EventoDaSessao(BaseModel):
    """O que `GET /eventos/sessao/{id}` pode emitir."""

    evento: EventoDoPainel


class _TodosOsEventos(BaseModel):
    chat: EventosDoChat
    painel: EventoDoPainel
    sessao: EventoDaSessao


def esquema() -> dict[str, Any]:
    """O OpenAPI do app, com os eventos de stream dentro."""
    documento: dict[str, Any] = create_app().openapi()
    componentes: dict[str, Any] = documento.setdefault("components", {}).setdefault("schemas", {})

    dos_eventos = _TodosOsEventos.model_json_schema(ref_template=REF)
    # `$defs` é onde o Pydantic põe todo modelo referenciado. Copiamos sem
    # sobrescrever: os modelos que já vieram do FastAPI são os mesmos objetos, e
    # deixá-lo vencer evita duas definições do mesmo nome divergindo por ordem.
    for nome, definicao in (dos_eventos.get("$defs") or {}).items():
        componentes.setdefault(nome, definicao)

    caminhos: dict[str, Any] = documento.get("paths", {})
    for caminho, (modelo, descricao) in STREAMS.items():
        rota = caminhos.get(caminho, {}).get("get") or caminhos.get(caminho, {}).get("post")
        if rota is None:
            continue
        rota["responses"]["200"] = {
            "description": descricao,
            "content": {"text/event-stream": {"schema": {"$ref": REF.format(model=modelo)}}},
        }

    return documento


def main(argv: Sequence[str] = ()) -> int:
    """Escreve o documento no arquivo, ordenado e terminado por quebra de linha.

    **Escreve o arquivo em vez de imprimir em stdout, e isso não é preferência.**
    No Windows o stdout do console é cp1252, e `python -m vendinha.openapi >
    openapi.json` produzia um arquivo corrompido no primeiro `ç` de uma descrição
    de campo — um portão de contrato que só funciona em metade das máquinas do time
    é pior do que nenhum. Aqui o encoding é do arquivo, e é sempre UTF-8.

    `sort_keys` porque o arquivo é commitado e o CI o compara com `git diff`: uma
    ordem instável de chaves produziria diff em todo build, e diff em todo build
    ensina a ignorar o portão que este arquivo existe para sustentar.
    """
    destino = Path(argv[0]) if argv else PADRAO
    destino.write_text(
        json.dumps(esquema(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"openapi escrito em {destino}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
