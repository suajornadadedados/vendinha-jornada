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
    PreambuloEvent,
    SessionEvent,
    TokenEvent,
)

REF = "#/components/schemas/{model}"
PADRAO = REPO_ROOT / "openapi.json"

DO_CHAT = (
    "Stream do atendimento: `session` primeiro, `token` a cada pedaço da resposta, "
    "`error` quando falha depois do primeiro byte, e `done` sempre."
)
DO_PAINEL = (
    "Tudo que acontece no servidor, para o painel. O nome do `event:` é o campo "
    "`tipo`. Um `atraso` significa que este assinante perdeu eventos."
)
DA_SESSAO = (
    "Só os eventos desta conversa — o barramento filtra por `session_id`. É o que "
    "faz a NF aparecer no chat sem o cliente perguntar."
)


class EventosDoChat(BaseModel):
    """Reúne os eventos de `/chat` para que entrem no schema.

    Não é um corpo que alguma rota devolva: é o veículo que leva os modelos até
    `components.schemas`. Está declarado como classe, e não montado à mão em
    dicionário, para que ele não possa divergir dos modelos que a rota realmente
    emite — se alguém acrescentar um campo em `TokenEvent`, este schema acompanha.
    """

    session: SessionEvent
    token: TokenEvent
    preambulo: PreambuloEvent
    error: ErrorEvent
    done: DoneEvent


class _TodosOsEventos(BaseModel):
    """Só existe para arrastar todo modelo de evento para `$defs`."""

    chat: EventosDoChat
    painel: EventoDoPainel


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

    # A união do painel é **inlinada**, e não referenciada por nome.
    # `EventoDoPainel` é um alias com discriminador, não um `BaseModel`: o Pydantic
    # não cria um `$def` para ele, e um `$ref` a um nome que não existe quebra o
    # gerador do cliente com uma mensagem que não diz isso. O gerador reclamando
    # foi o que trouxe o erro à tona, e é o motivo de o portão existir.
    uniao = {chave: valor for chave, valor in dos_eventos["properties"]["painel"].items()}

    caminhos: dict[str, Any] = documento.get("paths", {})
    for caminho, esquema_do_corpo, descricao in (
        ("/chat", {"$ref": REF.format(model="EventosDoChat")}, DO_CHAT),
        ("/admin/eventos", uniao, DO_PAINEL),
        ("/eventos/sessao/{session_id}", uniao, DA_SESSAO),
    ):
        metodos = caminhos.get(caminho, {})
        rota = metodos.get("get") or metodos.get("post")
        if rota is None:
            continue
        rota["responses"]["200"] = {
            "description": descricao,
            "content": {"text/event-stream": {"schema": esquema_do_corpo}},
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
