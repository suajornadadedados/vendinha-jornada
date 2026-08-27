"""`make seed` — o seed vira catálogo consultável, nos dois lugares que ele ocupa.

    make up && make db-setup && make seed

Postgres recebe os fatos; Qdrant recebe os vetores. Nesta ordem, e é uma ordem com
motivo: se a embedagem falhar no meio — chave errada, rede caída, cota estourada —
o banco já está correto e o agente responde com busca ruim em vez de responder um
preço errado. A falha degrada a *recomendação*, nunca a *afirmação*.

**Idempotente.** Rodar duas vezes produz o mesmo estado: upsert por id nos dois
lados, e o que saiu do seed é apagado dos dois. Ver `catalogo.py` sobre por que
apagar é a metade que se esquece.

**A credencial vem do mesmo lugar que a do chat** (ADR-012): ambiente por baixo,
configuração gravada no banco por cima. Um operador que trocou a chave pela API não
precisa também editar o `.env` para conseguir reindexar.

A S-03 embeda pela OpenAI (D-1). Isso torna `OPENAI_API_KEY` necessária para este
comando mesmo numa instância que conversa só por Anthropic — contra a letra do
RNF-1, decidido assim pelo PO, e a mensagem de erro abaixo diz isso em voz alta em
vez de deixar a pessoa adivinhar por que "provider not found".
"""

import logging
import sys
from pathlib import Path

from langchain.embeddings import init_embeddings

from vendinha import runtime
from vendinha.catalogo import PostgresCatalogo, QdrantIndice, carregar_seed, documentos
from vendinha.config import REPO_ROOT, get_settings
from vendinha.config_store import PostgresConfigStore
from vendinha.credentials import Vault
from vendinha.db import with_connect_timeout
from vendinha.providers import effective_credentials, split_model

logger = logging.getLogger(__name__)

CATALOGO = REPO_ROOT / "data" / "catalogo"


class CredencialDeEmbeddingAusente(Exception):
    """Não há chave para o provedor que embeda. Diz qual, e como resolver."""


async def ingest(seed: Path = CATALOGO) -> tuple[int, int]:
    """Lê o seed, grava no Postgres, indexa no Qdrant. Devolve (linhas, pontos)."""
    settings = get_settings()
    dsn = with_connect_timeout(settings.database_url)

    produtos = carregar_seed(seed)
    logger.info("seed lido: %d produtos em %s", len(produtos), seed)

    linhas = await PostgresCatalogo(dsn).substituir_tudo(produtos)
    logger.info("postgres: %d linhas", linhas)

    provider, model = split_model(settings.embedding_model)
    stored = await PostgresConfigStore(dsn, Vault(settings.config_encryption_key)).load()
    api_key = effective_credentials(stored.credentials).get(provider)
    if not api_key:
        raise CredencialDeEmbeddingAusente(
            f"EMBEDDING_MODEL={settings.embedding_model} precisa de credencial do "
            f"provedor '{provider}', e não há nenhuma — nem no ambiente, nem gravada "
            f"pela API. Defina a chave desse provedor no .env ou em PUT /config.\n"
            f"Sim, isso vale mesmo se a conversa roda em outro provedor: a S-03 "
            f"decidiu embedar pela OpenAI (D-1)."
        )

    embeddings = init_embeddings(model, provider=provider, api_key=api_key)
    vetores = await embeddings.aembed_documents(documentos(produtos))
    logger.info("embeddings: %d vetores de dimensão %d", len(vetores), len(vetores[0]))

    pontos = await QdrantIndice(settings.qdrant_url, settings.qdrant_collection).reindexar(
        produtos, vetores
    )
    logger.info("qdrant: %d pontos na coleção %s", pontos, settings.qdrant_collection)
    return linhas, pontos


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = get_settings()
    try:
        linhas, pontos = runtime.run(ingest())
    except CredencialDeEmbeddingAusente as sem_chave:
        print(str(sem_chave), file=sys.stderr)
        return 1
    except Exception as error:
        # Mesmo formato do `db.py`: a exceção do psycopg ou do Qdrant diz qual dos
        # dois está fora, e isso vale mais para quem acabou de rodar o comando do
        # que um traceback.
        print(f"a ingestão falhou: {error}", file=sys.stderr)
        print("Postgres e Qdrant estão de pé? `make up` sobe os dois.", file=sys.stderr)
        print(f"Qdrant em uso: {settings.qdrant_url}", file=sys.stderr)
        print("a tabela `produto` existe? ela é criada por `make db-setup`.", file=sys.stderr)
        return 1
    print(f"catálogo pronto: {linhas} linhas no Postgres, {pontos} pontos no Qdrant.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
