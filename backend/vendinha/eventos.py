"""O barramento que faz o painel ser ao vivo — e as três coisas que ele recusa.

**Recusa bloquear quem publica.** Todo assinante tem fila própria e **limitada**.
Fila cheia descarta o mais antigo e conta o descarte; nunca espera. A alternativa —
`await fila.put(...)` — poria um painel aberto num navegador lento no caminho da
resposta de um cliente, e o cliente pagaria pela lentidão de alguém que ele não
conhece. O assinante que perdeu eventos recebe um `AtrasoNoStream` antes do próximo,
para que a tela possa dizer que está furada em vez de fingir estar inteira.

**Recusa entregar o que não foi endereçado.** Um assinante de sessão
(`assinar(sessao=...)`, que é o push para o cliente em `GET /eventos/sessao/{id}`)
só recebe evento que **carrega aquele `session_id`**. Evento sem sessão — a fila de
aprovação, por exemplo — não vai para ninguém que assinou por sessão. A regra é de
inclusão explícita e não de exclusão, porque uma lista de eventos proibidos é uma
lista que alguém esquece de atualizar quando o sétimo evento nascer.

**Recusa fingir que sobrevive a duas instâncias.** Isto é in-process. Com duas APIs,
cada uma vê só os próprios eventos, e o `Barramento` é Protocol justamente para que
a troca por `LISTEN/NOTIFY` do Postgres não toque em nenhuma rota. Está registrado
como dívida da S-08 no ADR-015, e não como detalhe de implementação, porque é o tipo
de limite que só aparece no dia do deploy.

Publicar nunca levanta. Um evento perdido custa uma linha na tela; uma exceção no
publicador custa a venda. É a mesma assimetria que o ADR-010 fixou para o Langfuse.
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Protocol

from vendinha.schemas import AtrasoNoStream, EventoDoPainel

logger = logging.getLogger(__name__)

# Quantos eventos um assinante pode dever antes de começar a perder os antigos.
# 256 é folgado para um humano olhando uma tela e apertado o bastante para que uma
# aba esquecida em segundo plano não vire memória crescendo sozinha.
CAPACIDADE = 256


def agora() -> datetime:
    """Um só lugar constrói o carimbo dos eventos, e ele é sempre com fuso."""
    return datetime.now(UTC)


def _da_sessao(evento: EventoDoPainel, sessao: str) -> bool:
    """Este evento pertence a esta sessão?

    `getattr` e não `isinstance` por tipo: o teste é sobre o evento **carregar** a
    sessão, então um evento novo que a carregue passa a ser entregue sem que
    ninguém precise lembrar de o acrescentar numa lista — e um que não a carregue
    fica de fora por construção.
    """
    return getattr(evento, "session_id", None) == sessao


class Barramento(Protocol):
    """A porta. Uma implementação hoje; a segunda é a da S-08."""

    async def publicar(self, evento: EventoDoPainel) -> None: ...

    def assinar(self, *, sessao: str | None = None) -> "Assinatura": ...


class Assinatura:
    """Uma fila viva. Context manager assíncrono para que cancelar não vaze.

    O `async with` é o que garante o descadastro: um cliente que fecha a aba faz o
    ASGI cancelar a task do stream, e sem o `finally` o assinante ficaria na lista
    para sempre, recebendo eventos numa fila que ninguém lê — que é como um
    barramento in-process vira vazamento de memória.
    """

    def __init__(self, barramento: "BarramentoEmMemoria", sessao: str | None) -> None:
        self._barramento = barramento
        self.sessao = sessao
        self.fila: asyncio.Queue[EventoDoPainel] = asyncio.Queue(maxsize=CAPACIDADE)
        self.perdidos = 0

    def aceita(self, evento: EventoDoPainel) -> bool:
        return True if self.sessao is None else _da_sessao(evento, self.sessao)

    def entregar(self, evento: EventoDoPainel) -> None:
        """Sem `await`: publicar não espera por assinante nenhum."""
        try:
            self.fila.put_nowait(evento)
        except asyncio.QueueFull:
            # Descarta o mais antigo, não o mais novo: numa tela de estado atual, o
            # evento velho é o que menos importa. E conta, para que o assinante seja
            # avisado de que perdeu — perder em silêncio é o que faria a tela mentir.
            with contextlib.suppress(asyncio.QueueEmpty):
                self.fila.get_nowait()
            self.perdidos += 1
            with contextlib.suppress(asyncio.QueueFull):
                self.fila.put_nowait(evento)

    async def __aenter__(self) -> AsyncIterator[EventoDoPainel]:
        self._barramento._assinantes.add(self)
        return self._eventos()

    async def __aexit__(self, *_: object) -> None:
        self._barramento._assinantes.discard(self)

    async def _eventos(self) -> AsyncIterator[EventoDoPainel]:
        while True:
            evento = await self.fila.get()
            if self.perdidos:
                # Antes do próximo evento e não depois: a tela precisa saber que
                # está furada **antes** de aplicar a atualização seguinte por cima.
                perdidos, self.perdidos = self.perdidos, 0
                yield AtrasoNoStream(em=agora(), perdidos=perdidos)
            yield evento


class BarramentoEmMemoria:
    """Fan-out in-process. A única implementação hoje — e a de teste também."""

    def __init__(self) -> None:
        self._assinantes: set[Assinatura] = set()

    @property
    def assinantes(self) -> int:
        """Quantos ouvem agora. Público porque é o que um teste de vazamento afirma."""
        return len(self._assinantes)

    async def publicar(self, evento: EventoDoPainel) -> None:
        """Entrega a quem aceita. Nunca levanta, nunca espera.

        A cópia da lista importa: `entregar` não faz `await`, mas um assinante pode
        se descadastrar entre duas iterações se algo mudar aqui um dia, e iterar
        sobre um `set` que muda é um erro que aparece uma vez por mês em produção.
        """
        for assinante in tuple(self._assinantes):
            if not assinante.aceita(evento):
                continue
            try:
                assinante.entregar(evento)
            except Exception:
                # Um assinante quebrado não pode derrubar a publicação para os
                # outros — nem para quem chamou, que está no meio de uma venda.
                logger.exception("falha ao entregar evento a um assinante do painel")

    def assinar(self, *, sessao: str | None = None) -> Assinatura:
        return Assinatura(self, sessao)
