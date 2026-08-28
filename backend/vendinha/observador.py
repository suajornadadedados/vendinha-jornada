"""O observador do turno: mede o que custou e conta ao painel o que aconteceu.

Ele existe para que o painel não custe nada ao grafo. Três regras.

**Não muda o grafo, e observa o que a rota já descarta.** O `astream` de `/chat`
com `stream_mode="messages"` já entrega os `ToolMessage`, e o filtro de tokens os
joga fora porque o cliente não pode vê-los. O observador olha justamente esse lixo:
é ali que está o veredito de `validar_composicao` e o id do pedido de
`criar_pedido`. A alternativa — um callback dentro da tool, ou um nó novo — poria
telemetria dentro da fronteira de permissão que a S-04 fechou por arquitetura, em
troca de nada.

**Nada aqui derruba um atendimento.** Toda publicação e toda gravação passam por
`_a_salvo`. A conta que o painel mostra é a informação menos urgente do sistema;
uma exceção ao gravá-la não pode custar a venda. É a assimetria do ADR-010 aplicada
ao read model.

**O que não se sabe fica `None`.** Um turno em que o provedor não informou consumo
grava `tokens_entrada = None`, e o custo daquela conversa passa a se declarar
incompleto. Zero seria a resposta fácil e seria falsa.
"""

import json
import logging
import time
from decimal import Decimal
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from vendinha.eventos import Barramento, agora
from vendinha.graph import fala_com_o_cliente
from vendinha.schemas import (
    ComposicaoAvaliada,
    MensagemRegistrada,
    PedidoAtualizado,
    SessaoIniciada,
)
from vendinha.telemetria import Telemetria, Turno, VereditoRegistrado
from vendinha.tools.composicao import ComposicaoValidada

logger = logging.getLogger(__name__)

VALIDAR = "validar_composicao"
CRIAR_PEDIDO = "criar_pedido"


def _ms(inicio: float) -> int:
    return int((time.monotonic() - inicio) * 1000)


class ObservadorDoTurno:
    """Um por requisição de `/chat`. Descartável, e sem estado entre turnos."""

    def __init__(
        self,
        *,
        barramento: Barramento,
        telemetria: Telemetria,
        session_id: str,
        modelo: str,
        canal: str = "widget",
    ) -> None:
        self._barramento = barramento
        self._telemetria = telemetria
        self.session_id = session_id
        self.modelo = modelo
        self.canal = canal

        self._inicio = time.monotonic()
        # Dois relógios de propósito: `monotonic` mede duração e não anda para
        # trás com ajuste de horário; o carimbo com fuso é o que a janela do
        # painel filtra. Usar um só faria uma das duas coisas errado.
        self._iniciado_em = agora()
        self._primeiro_token_ms: int | None = None
        self._resposta: list[str] = []
        self._entrada = 0
        self._saida = 0
        self._teve_uso = False

    async def _a_salvo(self, o_que: str, corotina: Any) -> None:
        try:
            await corotina
        except Exception:
            logger.exception(
                "telemetria do painel falhou em %s (sessao %s)", o_que, self.session_id
            )

    async def abrir(self, *, primeira_mensagem: str, sessao_nova: bool) -> None:
        await self._a_salvo(
            "abrir_sessao", self._telemetria.abrir_sessao(self.session_id, canal=self.canal)
        )
        if sessao_nova:
            await self._a_salvo(
                "sessao_iniciada",
                self._barramento.publicar(
                    SessaoIniciada(em=agora(), session_id=self.session_id, canal=self.canal)
                ),
            )
        # A fala do cliente vai para o painel **antes** de o modelo responder: é o
        # que faz o operador ver a pergunta enquanto o agente ainda pensa nela.
        await self._a_salvo(
            "mensagem do cliente",
            self._barramento.publicar(
                MensagemRegistrada(
                    em=agora(),
                    session_id=self.session_id,
                    papel="cliente",
                    texto=primeira_mensagem,
                )
            ),
        )

    async def viu(self, chunk: Any, meta: dict[str, Any] | None) -> None:
        """Um pedaço do stream. Chamado para **tudo**, inclusive o que o cliente não vê."""
        if isinstance(chunk, ToolMessage):
            await self._tool(chunk)
            return

        if not isinstance(chunk, AIMessage | AIMessageChunk):
            return

        # O consumo é somado de TODA chamada de modelo do turno, inclusive a do
        # roteador do supervisor: ele custa dinheiro e o cliente pagou por ele.
        # Isto é o oposto do filtro de tokens, que só deixa passar o que o cliente
        # deve ler — os dois olham o mesmo stream com perguntas diferentes.
        uso = getattr(chunk, "usage_metadata", None)
        if uso:
            self._teve_uso = True
            self._entrada += int(uso.get("input_tokens") or 0)
            self._saida += int(uso.get("output_tokens") or 0)

        if not fala_com_o_cliente((meta or {}).get("langgraph_node")):
            return
        if chunk.text:
            if self._primeiro_token_ms is None:
                self._primeiro_token_ms = _ms(self._inicio)
            self._resposta.append(chunk.text)

    async def _tool(self, mensagem: ToolMessage) -> None:
        nome = getattr(mensagem, "name", None)
        if nome not in (VALIDAR, CRIAR_PEDIDO):
            return
        try:
            corpo = json.loads(
                mensagem.content if isinstance(mensagem.content, str) else str(mensagem.content)
            )
        except (TypeError, ValueError):
            return

        if nome == VALIDAR:
            for encontrado in corpo.get("encontrados") or ():
                await self._veredito(encontrado)
            return

        for encontrado in corpo.get("encontrados") or ():
            await self._pedido(encontrado)

    async def _veredito(self, encontrado: dict[str, Any]) -> None:
        """Publica e guarda o veredito **como o validador o devolveu**.

        Revalidar aqui seria dar ao painel a chance de discordar do código que
        decide — e é o código que decide, não a tela (ADR-015).
        """
        try:
            veredito = ComposicaoValidada.model_validate(encontrado)
        except ValueError:
            return

        await self._a_salvo(
            "composicao_avaliada",
            self._barramento.publicar(
                ComposicaoAvaliada(em=agora(), session_id=self.session_id, veredito=veredito)
            ),
        )
        await self._a_salvo(
            "registrar_veredito",
            self._telemetria.registrar_veredito(
                VereditoRegistrado(
                    session_id=self.session_id,
                    aprovada=veredito.aprovada,
                    tipo_de_evento=veredito.tipo_de_evento,
                    pessoas=veredito.pessoas,
                    total=veredito.total_composicao,
                    valor_por_pessoa=veredito.valor_por_pessoa,
                    motivos=tuple(problema.motivo for problema in veredito.problemas_composicao),
                    avaliado_em=agora(),
                )
            ),
        )

    async def _pedido(self, encontrado: dict[str, Any]) -> None:
        pedido_id = encontrado.get("pedido_id")
        if not isinstance(pedido_id, str):
            return
        # A ligação sessão → pedido é o que permite empurrar a NF de volta para o
        # chat certo mais tarde (`GET /eventos/sessao/{id}`).
        await self._a_salvo(
            "vincular_pedido", self._telemetria.vincular_pedido(self.session_id, pedido_id)
        )
        await self._a_salvo(
            "pedido_atualizado",
            self._barramento.publicar(
                PedidoAtualizado(
                    em=agora(),
                    pedido_id=pedido_id,
                    session_id=self.session_id,
                    status=str(encontrado.get("status_pedido") or ""),
                    total=Decimal(str(encontrado.get("total_pedido") or "0")),
                    razao_social=str(encontrado.get("razao_social") or ""),
                )
            ),
        )

    async def fechar(self, *, erro: bool) -> None:
        """Grava o turno e publica a fala do atendente. Chamado sempre, mesmo em erro."""
        texto = "".join(self._resposta)
        if texto.strip():
            await self._a_salvo(
                "mensagem do atendente",
                self._barramento.publicar(
                    MensagemRegistrada(
                        em=agora(),
                        session_id=self.session_id,
                        papel="atendente",
                        texto=texto,
                    )
                ),
            )
        await self._a_salvo(
            "registrar_turno",
            self._telemetria.registrar_turno(
                Turno(
                    session_id=self.session_id,
                    modelo=self.modelo,
                    tokens_entrada=self._entrada if self._teve_uso else None,
                    tokens_saida=self._saida if self._teve_uso else None,
                    primeiro_token_ms=self._primeiro_token_ms,
                    duracao_ms=_ms(self._inicio),
                    iniciado_em=self._iniciado_em,
                    erro=erro,
                )
            ),
        )
