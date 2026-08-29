"""As rotas do painel. Leitura, e o stream que faz a tela ser ao vivo.

**Tudo aqui é `GET`.** A única escrita que o painel faz é a decisão de HITL, e ela
mora onde sempre morou — `/operador/pedidos/{id}/aprovar|rejeitar`, com o mesmo
contrato que a S-05 verificou. Um `/admin/pedidos/{id}` que aceitasse `PATCH` seria
o "painel administrativo completo" que o PRD recusou entrando pela porta dos fundos
(ADR-015).

**Fail-closed, e o teste percorre todas.** Cada rota depende do
`X-Operador-Token` pelo mesmo `_operador_autenticado` da fila. Sem
`OPERADOR_API_TOKEN` configurado, tudo responde 401 — porque a alternativa
transformaria uma variável de ambiente esquecida num painel aberto que lista CNPJ,
endereço e conversa de compradoras.

**As mensagens vêm do checkpointer.** Não há tabela de mensagem neste projeto, e
não haverá: a conversa já está indexada pelo `session_id`, e uma segunda cópia é a
que fica velha. Quando o checkpointer não responde, a resposta diz
`mensagens_indisponiveis: true` em vez de devolver uma lista vazia — uma conversa
que não pôde ser lida e uma conversa curta têm de ser distinguíveis na tela.

**O painel não constrói grafo.** Ler a conversa pelo checkpointer direto e não por
`graph.aget_state` é deliberado: montar o grafo exige credencial de provedor, e um
operador não deve precisar de uma chave de LLM configurada para ver o que já
aconteceu.
"""

import hashlib
import json
import logging
from collections.abc import Callable, Sequence
from typing import Annotated, Any

from fastapi import FastAPI, Header, HTTPException, Request, status
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from sse_starlette.sse import EventSourceResponse

from vendinha.config import Settings
from vendinha.documentos import formatar_cnpj
from vendinha.graph import session_config
from vendinha.metricas import apurar, apurar_metricas, status_fiscal
from vendinha.nota.documento import numero_da_nota
from vendinha.pedidos import Pedido
from vendinha.precos import TabelaDePrecos, tabela
from vendinha.schemas import (
    ConversaNaLista,
    DetalheDaConversa,
    MensagemDaConversa,
    Metricas,
    PaginaDeConversas,
    PaginaDePedidos,
    PedidoNoPainel,
    PromptsDoAgente,
    PromptVigente,
    TurnoDoPainel,
    UsoPorModelo,
    VeredictoNoPainel,
)
from vendinha.subagents import PROMPT_CHECKOUT, PROMPT_RECOMENDACAO
from vendinha.telemetria import ResumoDaSessao, UsoDeModelo

logger = logging.getLogger(__name__)

# Um `ping` a cada 15s. Sem ele, um proxy que corta conexão ociosa em 30 ou 60
# segundos derruba o stream de um painel que só estava esperando — e o operador vê
# "desconectado" numa loja parada, que é ruído indistinguível de falha real.
HEARTBEAT_SEGUNDOS = 15

# Teto de uma página do painel. Existe no contrato e não só na query para que
# ninguém peça 100.000 conversas e derrube a tela pedindo educadamente.
PAGINA_MAXIMA = 200


def _sha(texto: str) -> str:
    """Primeiros 12 hex do sha256 do prompt — o bastante para conferir numa demo."""
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:12]


def _uso_publico(uso: Sequence[UsoDeModelo]) -> tuple[UsoPorModelo, ...]:
    return tuple(
        UsoPorModelo(
            modelo=linha.modelo,
            tokens_entrada=linha.tokens_entrada,
            tokens_saida=linha.tokens_saida,
            turnos=linha.turnos,
        )
        for linha in uso
    )


def _texto(conteudo: Any) -> str:
    """Achata o conteúdo de uma mensagem, venha ele como string ou como blocos.

    Um provedor responde com texto puro e outro com uma lista de blocos tipados; a
    tela não pode depender de qual foi. É a mesma razão do `.text` no stream de
    `/chat`.
    """
    if isinstance(conteudo, str):
        return conteudo
    if isinstance(conteudo, list):
        partes = []
        for bloco in conteudo:
            if isinstance(bloco, str):
                partes.append(bloco)
            elif isinstance(bloco, dict) and bloco.get("type") == "text":
                partes.append(str(bloco.get("text", "")))
        return "".join(partes)
    return str(conteudo)


def projetar_mensagens(mensagens: Sequence[Any]) -> tuple[MensagemDaConversa, ...]:
    """Do estado do LangGraph para o que a tela de rastreabilidade mostra.

    Uma `AIMessage` com `tool_calls` vira **uma linha por chamada**, com os
    argumentos: é ali que está *o que o modelo propôs*, e é metade do que a tela de
    rastreabilidade existe para mostrar. A outra metade — o que o código respondeu —
    é o `ToolMessage` logo abaixo.
    """
    projetadas: list[MensagemDaConversa] = []
    for mensagem in mensagens:
        if isinstance(mensagem, HumanMessage):
            projetadas.append(MensagemDaConversa(papel="cliente", texto=_texto(mensagem.content)))
            continue
        if isinstance(mensagem, ToolMessage):
            projetadas.append(
                MensagemDaConversa(
                    papel="ferramenta",
                    texto=_texto(mensagem.content),
                    ferramenta=getattr(mensagem, "name", None),
                )
            )
            continue
        if isinstance(mensagem, AIMessage):
            texto = _texto(mensagem.content)
            if texto.strip():
                projetadas.append(MensagemDaConversa(papel="atendente", texto=texto))
            for chamada in mensagem.tool_calls or ():
                projetadas.append(
                    MensagemDaConversa(
                        papel="atendente",
                        texto="",
                        ferramenta=chamada.get("name"),
                        argumentos=json.dumps(
                            chamada.get("args", {}), ensure_ascii=False, default=str
                        ),
                    )
                )
    return tuple(projetadas)


async def ler_conversa(checkpointer: Any, session_id: str) -> tuple[Any, ...] | None:
    """As mensagens do checkpointer. `None` quando não deu para ler.

    `None` e não `()`: a tela precisa distinguir *"esta conversa não pôde ser lida"*
    de *"esta conversa não tem mensagens"*. Engolir a diferença aqui produziria uma
    tela que mostra silêncio no lugar de uma falha.
    """
    if checkpointer is None:
        return None
    try:
        tupla = await checkpointer.aget_tuple(session_config(session_id))
    except Exception:
        logger.exception("falha ao ler o checkpoint da sessao %s", session_id)
        return None
    if tupla is None:
        return ()
    valores = tupla.checkpoint.get("channel_values") or {}
    return tuple(valores.get("messages") or ())


def no_painel(pedido: Pedido, *, base_url: str, numero_nota: int | None) -> PedidoNoPainel:
    """O pedido como a tela o mostra. Composições sem reprojeção, como na fila."""
    fiscal = status_fiscal(pedido.status.value)
    emitida = numero_nota is not None
    return PedidoNoPainel(
        pedido_id=pedido.id,
        criado_em=pedido.criado_em,
        status=pedido.status.value,
        total=pedido.total,
        razao_social=pedido.empresa.razao_social,
        cnpj=formatar_cnpj(pedido.empresa.cnpj),
        url_pagamento=pedido.url_pagamento,
        composicoes=pedido.composicoes,
        status_nf=fiscal,
        numero_nota=numero_nota,
        url_danfe=f"{base_url}/pedidos/{pedido.id}/nota.pdf" if emitida else None,
        url_xml=f"{base_url}/pedidos/{pedido.id}/nota.xml" if emitida else None,
    )


def montar(
    app: FastAPI,
    *,
    autenticado: Callable[[str | None], None],
    settings: Settings,
) -> None:
    """Registra `/admin/*`. Chamado por `create_app`, e só por ele."""

    def precos() -> TabelaDePrecos:
        return tabela()

    async def _linha(request: Request, sessao: ResumoDaSessao) -> ConversaNaLista:
        status_pedido: str | None = None
        if sessao.pedido_id is not None:
            # Uma consulta por conversa **que tem pedido** — que numa lista de
            # conversas é a minoria. O caro seria montar o pedido inteiro para as
            # que não têm, e é justamente o que este `if` evita.
            pedido = await request.app.state.pedidos.por_id(sessao.pedido_id)
            status_pedido = None if pedido is None else pedido.status.value
        return ConversaNaLista(
            session_id=sessao.session_id,
            canal=sessao.canal,
            iniciada_em=sessao.iniciada_em,
            ultima_atividade=sessao.ultima_atividade,
            turnos=sessao.turnos,
            erros=sessao.erros,
            custo=apurar(sessao.uso, precos()),
            pedido_id=sessao.pedido_id,
            status_do_pedido=status_pedido,
        )

    @app.get("/admin/conversas", response_model=PaginaDeConversas, tags=["painel"])
    async def conversas(
        request: Request,
        limite: int = 50,
        offset: int = 0,
        x_operador_token: Annotated[str | None, Header()] = None,
    ) -> PaginaDeConversas:
        autenticado(x_operador_token)
        sessoes = await request.app.state.telemetria.sessoes(
            limite=min(max(limite, 1), PAGINA_MAXIMA), offset=max(offset, 0)
        )
        return PaginaDeConversas(
            conversas=tuple([await _linha(request, sessao) for sessao in sessoes])
        )

    @app.get("/admin/conversas/{session_id}", response_model=DetalheDaConversa, tags=["painel"])
    async def conversa(
        session_id: str,
        request: Request,
        x_operador_token: Annotated[str | None, Header()] = None,
    ) -> DetalheDaConversa:
        autenticado(x_operador_token)
        telemetria = request.app.state.telemetria
        sessao = await telemetria.sessao(session_id)
        if sessao is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "conversa desconhecida")

        mensagens = await ler_conversa(request.app.state.checkpointer, session_id)
        turnos = await telemetria.turnos(session_id)
        vereditos = await telemetria.vereditos(session_id)
        tabela_vigente = precos()

        return DetalheDaConversa(
            resumo=await _linha(request, sessao),
            mensagens=() if mensagens is None else projetar_mensagens(mensagens),
            mensagens_indisponiveis=mensagens is None,
            turnos=tuple(
                TurnoDoPainel(
                    modelo=turno.modelo,
                    tokens_entrada=turno.tokens_entrada,
                    tokens_saida=turno.tokens_saida,
                    primeiro_token_ms=turno.primeiro_token_ms,
                    duracao_ms=turno.duracao_ms,
                    iniciado_em=turno.iniciado_em,
                    erro=turno.erro,
                    custo=apurar(
                        (
                            UsoDeModelo(
                                modelo=turno.modelo,
                                tokens_entrada=turno.tokens_entrada or 0,
                                tokens_saida=turno.tokens_saida or 0,
                                turnos=1,
                                turnos_sem_uso=1 if turno.tokens_entrada is None else 0,
                            ),
                        ),
                        tabela_vigente,
                    ),
                )
                for turno in turnos
            ),
            vereditos=tuple(
                VeredictoNoPainel(
                    aprovada=veredito.aprovada,
                    tipo_de_evento=veredito.tipo_de_evento,
                    pessoas=veredito.pessoas,
                    total=veredito.total,
                    valor_por_pessoa=veredito.valor_por_pessoa,
                    motivos=veredito.motivos,
                    avaliado_em=veredito.avaliado_em,
                )
                for veredito in vereditos
            ),
            uso=_uso_publico(sessao.uso),
        )

    @app.get("/admin/pedidos", response_model=PaginaDePedidos, tags=["painel"])
    async def lista_de_pedidos(
        request: Request,
        limite: int = 50,
        offset: int = 0,
        x_operador_token: Annotated[str | None, Header()] = None,
    ) -> PaginaDePedidos:
        autenticado(x_operador_token)
        encontrados = await request.app.state.pedidos.listar(
            limite=min(max(limite, 1), PAGINA_MAXIMA), offset=max(offset, 0)
        )
        notas = {
            pedido.id: await request.app.state.fiscal.nota_de(pedido.id) for pedido in encontrados
        }
        return PaginaDePedidos(
            pedidos=tuple(
                no_painel(
                    pedido,
                    base_url=settings.public_base_url,
                    numero_nota=numero_da_nota(notas[pedido.id]),
                )
                for pedido in encontrados
            )
        )

    @app.get("/admin/pedidos/{pedido_id}", response_model=PedidoNoPainel, tags=["painel"])
    async def pedido_no_painel(
        pedido_id: str,
        request: Request,
        x_operador_token: Annotated[str | None, Header()] = None,
    ) -> PedidoNoPainel:
        autenticado(x_operador_token)
        pedido = await request.app.state.pedidos.por_id(pedido_id)
        if pedido is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "pedido desconhecido")
        return no_painel(
            pedido,
            base_url=settings.public_base_url,
            numero_nota=numero_da_nota(await request.app.state.fiscal.nota_de(pedido_id)),
        )

    @app.get("/admin/metricas", response_model=Metricas, tags=["painel"])
    async def metricas(
        request: Request,
        janela: str = "24h",
        x_operador_token: Annotated[str | None, Header()] = None,
    ) -> Metricas:
        autenticado(x_operador_token)
        return await apurar_metricas(
            janela=janela,
            telemetria=request.app.state.telemetria,
            pedidos=request.app.state.pedidos,
            fiscal=request.app.state.fiscal,
            precos=precos(),
        )

    @app.get("/admin/prompts", response_model=PromptsDoAgente, tags=["painel"])
    async def prompts(
        x_operador_token: Annotated[str | None, Header()] = None,
    ) -> PromptsDoAgente:
        """Os prompts vigentes, **em leitura**. Não existe rota que os escreva.

        `editavel` é um literal `False` no contrato, e não um booleano calculado:
        o cliente TypeScript passa a ter o tipo `false`, e um botão de salvar nem
        chega a compilar. É a forma mais barata de manter a decisão do ADR-015
        depois que alguém esquecer por que ela existe.
        """
        autenticado(x_operador_token)
        vigente = precos()
        return PromptsDoAgente(
            prompts=(
                PromptVigente(
                    subagent="recomendacao",
                    texto=PROMPT_RECOMENDACAO,
                    arquivo="backend/vendinha/subagents.py",
                    sha=_sha(PROMPT_RECOMENDACAO),
                ),
                PromptVigente(
                    subagent="checkout",
                    texto=PROMPT_CHECKOUT,
                    arquivo="backend/vendinha/subagents.py",
                    sha=_sha(PROMPT_CHECKOUT),
                ),
            ),
            tabela_de_precos_atualizada_em=vigente.atualizado_em,
        )

    @app.get("/admin/eventos", tags=["painel"])
    async def eventos_do_painel(
        request: Request,
        x_operador_token: Annotated[str | None, Header()] = None,
    ) -> EventSourceResponse:
        """O barramento, como SSE. É o que faz o painel dispensar polling.

        A autenticação acontece **antes** de abrir o stream, na função da rota, e
        não dentro do gerador: um 401 emitido de dentro do stream já teria mandado
        200 na linha de status, e o cliente aprenderia a tratar não-autorizado como
        sucesso.
        """
        autenticado(x_operador_token)
        barramento = request.app.state.barramento

        async def stream() -> Any:
            async with barramento.assinar() as fluxo:
                async for evento in fluxo:
                    yield {"event": evento.tipo, "data": evento.model_dump_json()}

        return EventSourceResponse(stream(), ping=HEARTBEAT_SEGUNDOS)
