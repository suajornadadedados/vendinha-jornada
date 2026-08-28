"""O trace da conversa: um por atendimento, e não um por turno.

Sem marcador de risco, e de propósito. É teste de feature — `docs/testes.md` §3
item 1 —, e o `risco` fica reservado para o que fecha uma linha da matriz. A linha
R5 do Langfuse (PII mascarada na origem) é medida em
`tests/security/test_pii_redaction.py`, que é outra pergunta sobre o mesmo SDK.

Nada aqui abre rede: `create_trace_id` é uma função pura de hash, e o caminho sem
credencial é exercitado trocando `client` por um duplo.
"""

from typing import Any

import pytest

from vendinha import observability
from vendinha.observability import callback_handler, trace_id_da_sessao


def test_a_mesma_sessao_da_sempre_o_mesmo_trace() -> None:
    """O tripwire desta feature.

    Cada `POST /chat` é uma requisição própria, então o handler do LangChain abre um
    run raiz por turno — e um run raiz por turno é um TRACE por turno. Ler um
    atendimento de doze turnos virava abrir doze traces e remontar a ordem de
    cabeça.

    O que junta tudo é o id derivado da sessão ser o MESMO em toda chamada. Se
    alguém trocar isto por um id aleatório, o Langfuse volta a mostrar N traces sem
    erro nenhum, sem log nenhum, e a regressão só aparece quando alguém for
    depurar uma conversa. É essa a falha que esta asserção segura.
    """
    assert trace_id_da_sessao("abc123") == trace_id_da_sessao("abc123")


def test_sessoes_diferentes_nao_se_misturam() -> None:
    """Um trace por atendimento é o objetivo; um trace para dois, não."""
    assert trace_id_da_sessao("abc123") != trace_id_da_sessao("def456")


def test_o_id_tem_a_forma_que_o_langfuse_exige() -> None:
    """32 hex minúsculos — 16 bytes de trace id do OpenTelemetry.

    Vem de `Langfuse.create_trace_id`, e é justamente por vir de lá que o formato
    não é problema nosso. A asserção existe para o dia em que alguém "simplificar"
    isto para o próprio `session_id`, que é hex de 32 por coincidência do `uuid4().hex`
    e deixaria de ser no dia em que o id da sessão mudasse de forma.
    """
    gerado = trace_id_da_sessao("abc123")

    assert len(gerado) == 32
    assert gerado == gerado.lower()
    assert all(caractere in "0123456789abcdef" for caractere in gerado)


@pytest.mark.parametrize("sessao", [None, "abc123"])
def test_sem_langfuse_configurado_nao_ha_handler(
    monkeypatch: pytest.MonkeyPatch, sessao: str | None
) -> None:
    """ADR-010 aplicado às duas formas de pedir o handler.

    Sem credencial, o atendimento roda sem trace em vez de não rodar — e isso vale
    tanto para o handler da subida quanto para o por sessão. Um `CallbackHandler`
    construído aqui falaria com o cliente default do SDK, sem `mask_otel_spans`, e
    exportaria a conversa inteira sem redação nenhuma.
    """

    def sem_cliente(*_: Any, **__: Any) -> None:
        return None

    monkeypatch.setattr(observability, "client", sem_cliente)

    assert callback_handler(session_id=sessao) is None
