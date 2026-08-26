"""O catálogo — tudo que o agente pode afirmar, e de onde cada afirmação vem.

Este módulo existe para sustentar uma frase do `data/catalogo/README.md`: *o modelo
nunca afirma um número que não tenha vindo daqui*. Ele é a única porta entre o seed
e o agente, e a forma dele carrega três decisões.

**Qdrant ranqueia, Postgres afirma.** A busca semântica devolve *ids ordenados por
similaridade* e nada mais. Todo fato que chega ao modelo — nome, atributo,
disponibilidade, preço — é lido do Postgres, que `docs/arquitetura.md` nomeia fonte
da verdade. Um payload de vetor que carrega preço vira uma segunda cópia do preço,
e a segunda cópia é a que fica velha sem ninguém perceber (R1).

**O payload do Qdrant não carrega dinheiro.** Filtro de faixa de preço acontece no
Postgres, em `Decimal`. Qdrant filtra o que não é dinheiro — `tipo`, `disponivel`.
Um filtro de preço em ponto flutuante deixaria passar exatamente a classe de erro
que R1 existe para impedir (`docs/testes.md` §4).

**O texto indexado não tem preço nem prazo.** O vetor precisa responder *"presente
pra minha sogra que ama vinho tinto"*, não ordenar por valor. Preço no documento
embedado faria a busca ranquear por dinheiro sem ninguém pedir.

Uma nota sobre nomes: identificadores são em inglês (CLAUDE.md), com duas exceções
deliberadas. Os campos de `Produto` espelham as chaves do seed uma a uma — uma
tabela de tradução entre `preco` e `price` seria mais um lugar onde um fato pode
mudar de sentido. E os nomes das tools, na S-03, são os que o corpus de evals cita
literalmente.
"""

import json
import uuid
from collections.abc import Iterable, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal, Protocol

import psycopg
from langchain_core.embeddings import Embeddings
from psycopg import sql
from pydantic import BaseModel, ConfigDict, Field, field_validator
from qdrant_client import AsyncQdrantClient, models

# `text[]` e não uma tabela filha: `harmonizacao` e `ocasiao` são atributos de
# leitura do produto, nunca entidades com vida própria. Uma tabela de junção aqui
# seria normalização a serviço de nada — ninguém consulta "todos os produtos que
# harmonizam com X" a não ser pela busca semântica, que vive no Qdrant.
#
# `numeric(8,2)` casa exatamente com o `^[0-9]{1,6}\\.[0-9]{2}$` do schema do seed,
# e psycopg devolve `numeric` como `Decimal` — o dinheiro atravessa o banco sem
# passar por float em nenhum ponto.
SCHEMA = """
CREATE TABLE IF NOT EXISTS produto (
    id               text PRIMARY KEY,
    nome             text NOT NULL,
    tipo             text NOT NULL,
    regiao           text NOT NULL,
    produtor         text NOT NULL,
    descricao        text NOT NULL,
    intensidade      text NOT NULL,
    harmonizacao     text[] NOT NULL,
    ocasiao          text[] NOT NULL,
    peso             text NOT NULL,
    preco            numeric(8,2) NOT NULL CHECK (preco > 0),
    disponivel       boolean NOT NULL,
    prazo_estimado   text NOT NULL,
    maturacao        text,
    torra            text,
    notas_sensoriais text[] NOT NULL DEFAULT '{}',
    teor_alcoolico   text,
    atualizado_em    timestamptz NOT NULL DEFAULT now()
)
"""

# O Qdrant só aceita UUID ou inteiro como id de ponto, e o id do seed é um slug.
# Derivar o UUID do slug — em vez de sortear um — é o que faz `make seed` rodar
# duas vezes produzir o mesmo índice em vez de duas cópias de cada produto.
POINT_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://vendinha.local/catalogo")

TipoDeProduto = Literal["queijo", "cafe", "doce", "cachaca", "licor"]
Intensidade = Literal["suave", "media", "marcante"]


class Produto(BaseModel):
    """Uma linha do catálogo, do jeito que o seed a escreve.

    `extra="forbid"` para que um campo novo no seed apareça como erro de validação
    aqui, e não como um atributo que existe no JSON e some silenciosamente no
    caminho até o cliente.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    nome: str
    tipo: TipoDeProduto
    regiao: str
    produtor: str
    descricao: str
    intensidade: Intensidade
    harmonizacao: tuple[str, ...]
    ocasiao: tuple[str, ...]
    peso: str
    preco: Annotated[Decimal, Field(gt=0, decimal_places=2)]
    disponivel: bool
    prazo_estimado: str

    # Condicionais por tipo — o schema do seed diz quais são obrigatórios para
    # cada um, e é lá que essa exigência é verificada
    # (`tests/unit/test_catalog_seed_is_usable.py`).
    maturacao: str | None = None
    torra: str | None = None
    notas_sensoriais: tuple[str, ...] = ()
    teor_alcoolico: str | None = None

    @field_validator("preco", mode="before")
    @classmethod
    def _price_never_arrives_as_a_float(cls, value: object) -> object:
        """R1 — dinheiro é `Decimal`, nunca float (`docs/testes.md` §4).

        Pydantic aceita `float` para um campo `Decimal` e converte. A conversão é
        justamente a perda: `89.90` já chegou aqui como `89.90000000000000568...`
        se alguém trocou a string do seed por um número JSON. Recusar na fronteira
        é mais barato do que descobrir no total de um pedido.
        """
        if isinstance(value, float):
            raise ValueError(
                "preco chegou como float e perde centavos na conversão; "
                "o seed grava preço como string (data/catalogo/README.md)"
            )
        return value


def carregar_seed(diretorio: Path) -> tuple[Produto, ...]:
    """Lê `data/catalogo/*.json` inteiro, ordenado por id e sem repetição.

    A ordem é estável de propósito: uma reindexação que muda a ordem dos pontos
    sem que nada tenha mudado no seed produz um diff que ninguém sabe ler.
    """
    produtos: list[Produto] = []
    for arquivo in sorted(diretorio.glob("*.json")):
        with arquivo.open(encoding="utf-8") as handle:
            linhas: list[dict[str, Any]] = json.load(handle)
        produtos.extend(Produto.model_validate(linha) for linha in linhas)

    vistos: dict[str, int] = {}
    for produto in produtos:
        vistos[produto.id] = vistos.get(produto.id, 0) + 1
    repetidos = sorted(pid for pid, quantas in vistos.items() if quantas > 1)
    if repetidos:
        # Dois produtos com o mesmo id tornam "o preço do X" uma pergunta ambígua,
        # e os casos de eval citam produto por id.
        raise ValueError(f"ids repetidos no seed: {', '.join(repetidos)}")

    return tuple(sorted(produtos, key=lambda produto: produto.id))


def texto_para_embedding(produto: Produto) -> str:
    """O documento que vira vetor.

    Sem preço e sem prazo, de propósito: o vetor responde *para quem serve este
    produto*, e valor não é uma dimensão de semelhança que alguém pediu. O que
    entra é o que faz "presente pra minha sogra que ama vinho tinto" encontrar um
    queijo — `harmonizacao` e `ocasiao` antes de tudo (`data/catalogo/README.md`).
    """
    linhas = [
        f"{produto.nome} — {produto.tipo} de {produto.regiao}, do produtor {produto.produtor}.",
        f"Intensidade {produto.intensidade}. Peso {produto.peso}.",
        produto.descricao,
        f"Harmoniza com: {', '.join(produto.harmonizacao)}.",
        f"Indicado para: {', '.join(produto.ocasiao)}.",
    ]
    if produto.maturacao:
        linhas.append(f"Maturação: {produto.maturacao}.")
    if produto.torra:
        linhas.append(f"Torra: {produto.torra}.")
    if produto.notas_sensoriais:
        linhas.append(f"Notas sensoriais: {', '.join(produto.notas_sensoriais)}.")
    if produto.teor_alcoolico:
        linhas.append(f"Teor alcoólico: {produto.teor_alcoolico}.")
    return "\n".join(linhas)


def ponto_de(produto_id: str) -> str:
    """O id do ponto no Qdrant, derivado do id do seed. Sempre o mesmo."""
    return str(uuid.uuid5(POINT_NAMESPACE, produto_id))


def payload_de(produto: Produto) -> dict[str, object]:
    """O que o Qdrant guarda ao lado do vetor: só o que filtro estrutural usa.

    Nem preço, nem descrição, nem nome. Não é economia de espaço — é que qualquer
    campo aqui é um fato com duas moradas, e o dia em que as duas discordarem o
    agente vai citar a errada com a mesma confiança.
    """
    return {"id": produto.id, "tipo": produto.tipo, "disponivel": produto.disponivel}


def colunas_de(produto: Produto) -> tuple[object, ...]:
    """A linha do Postgres, na ordem de `COLUNAS`."""
    return (
        produto.id,
        produto.nome,
        produto.tipo,
        produto.regiao,
        produto.produtor,
        produto.descricao,
        produto.intensidade,
        list(produto.harmonizacao),
        list(produto.ocasiao),
        produto.peso,
        produto.preco,
        produto.disponivel,
        produto.prazo_estimado,
        produto.maturacao,
        produto.torra,
        list(produto.notas_sensoriais),
        produto.teor_alcoolico,
    )


COLUNAS: tuple[str, ...] = (
    "id",
    "nome",
    "tipo",
    "regiao",
    "produtor",
    "descricao",
    "intensidade",
    "harmonizacao",
    "ocasiao",
    "peso",
    "preco",
    "disponivel",
    "prazo_estimado",
    "maturacao",
    "torra",
    "notas_sensoriais",
    "teor_alcoolico",
)


def _upsert_sql() -> sql.Composed:
    """O upsert montado por `psycopg.sql`, e não por f-string.

    Os nomes vêm de `COLUNAS`, que é constante deste módulo — então concatenar
    texto seria seguro *hoje*, por um argumento sobre a origem do dado. `sql.SQL`
    torna a mesma coisa segura por construção, que é a diferença entre um
    argumento e uma garantia. É a regra de ouro do projeto aplicada ao próprio
    código: o que não pode acontecer não deveria depender de alguém lembrar.
    """
    identificadores = [sql.Identifier(coluna) for coluna in COLUNAS]
    return sql.SQL(
        "INSERT INTO produto ({campos}) VALUES ({marcadores}) "
        "ON CONFLICT (id) DO UPDATE SET {atualiza}, atualizado_em = now()"
    ).format(
        campos=sql.SQL(", ").join(identificadores),
        marcadores=sql.SQL(", ").join(sql.Placeholder() for _ in COLUNAS),
        atualiza=sql.SQL(", ").join(
            sql.SQL("{coluna} = EXCLUDED.{coluna}").format(coluna=sql.Identifier(coluna))
            for coluna in COLUNAS
            if coluna != "id"
        ),
    )


class Catalogo(Protocol):
    """A fonte da verdade, como quem lê a enxerga.

    Só leitura. Não é que a escrita esteja proibida nesta interface — é que ela
    não existe nela: o único código que escreve no catálogo é `make seed`, e ele
    fala com `PostgresCatalogo` diretamente. Um subagent que recebe um `Catalogo`
    não tem o que chamar para mudar um preço (ADR-002, RF-1.5).
    """

    async def por_ids(self, ids: Sequence[str]) -> dict[str, Produto]: ...

    async def quantos(self) -> int: ...


class Busca(Protocol):
    """O ranqueador. Devolve ids, e nada além de ids.

    A assinatura é a fronteira: não há como esta interface devolver um preço, um
    atributo ou um texto, então não há como um fato entrar na conversa por aqui.
    Quem afirma é o `Catalogo`.
    """

    async def ids_similares(
        self, necessidade: str, *, tipo: str | None, apenas_disponiveis: bool, limite: int
    ) -> list[str]: ...


class PostgresCatalogo:
    """O catálogo no Postgres: a escrita do `make seed` e a leitura das tools."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    async def setup(self) -> None:
        async with await psycopg.AsyncConnection.connect(self._dsn, autocommit=True) as conn:
            await conn.execute(SCHEMA)

    async def por_ids(self, ids: Sequence[str]) -> dict[str, Produto]:
        """Os produtos pedidos, por id. Id que não existe simplesmente não volta.

        Devolver um mapa, e não uma lista, é o que faz "não achei este produto"
        ser uma ausência que o chamador tem que tratar — em vez de uma lista mais
        curta que ele pode não perceber que encurtou.
        """
        if not ids:
            return {}
        async with await psycopg.AsyncConnection.connect(self._dsn, autocommit=True) as conn:
            cursor = await conn.execute(
                sql.SQL("SELECT {campos} FROM produto WHERE id = ANY(%s)").format(
                    campos=sql.SQL(", ").join(sql.Identifier(coluna) for coluna in COLUNAS)
                ),
                (list(ids),),
            )
            linhas = await cursor.fetchall()
        encontrados = (
            Produto.model_validate(dict(zip(COLUNAS, linha, strict=True))) for linha in linhas
        )
        return {produto.id: produto for produto in encontrados}

    async def quantos(self) -> int:
        """Quantos produtos o catálogo tem. Zero é o sintoma de `make seed` esquecido."""
        async with await psycopg.AsyncConnection.connect(self._dsn, autocommit=True) as conn:
            linha = await (await conn.execute("SELECT count(*) FROM produto")).fetchone()
        return int(linha[0]) if linha else 0

    async def todos(self) -> tuple[Produto, ...]:
        """O catálogo inteiro, do banco.

        **Não faz parte do protocolo `Catalogo`, e isso é a decisão.** Quem recebe
        um `Catalogo` são as tools do subagent, e "me dê o catálogo inteiro" não é
        uma pergunta que a recomendação precise fazer — é despejo de vitrine, que
        é justamente o que o RF-1.2 existe para não ser. Quem chama isto é o eval,
        que tem a classe concreta e precisa comparar o que o agente disse contra a
        fonte da verdade.
        """
        async with await psycopg.AsyncConnection.connect(self._dsn, autocommit=True) as conn:
            cursor = await conn.execute(
                sql.SQL("SELECT {campos} FROM produto ORDER BY id").format(
                    campos=sql.SQL(", ").join(sql.Identifier(coluna) for coluna in COLUNAS)
                )
            )
            linhas = await cursor.fetchall()
        return tuple(
            Produto.model_validate(dict(zip(COLUNAS, linha, strict=True))) for linha in linhas
        )

    async def substituir_tudo(self, produtos: Sequence[Produto]) -> int:
        """Grava o seed inteiro e apaga o que saiu dele. Uma transação, tudo ou nada.

        Apagar é a metade que se esquece: um produto renomeado no seed deixaria a
        linha antiga viva, e o agente continuaria capaz de citar um produto que a
        loja não vende mais — com preço e tudo, vindo do banco, passando por
        qualquer verificação de groundedness.
        """
        if not produtos:
            raise ValueError("recusando gravar um catálogo vazio")

        async with await psycopg.AsyncConnection.connect(self._dsn) as conn:
            async with conn.cursor() as cur:
                await cur.executemany(_upsert_sql(), [colunas_de(p) for p in produtos])
                await cur.execute(
                    "DELETE FROM produto WHERE id <> ALL(%s)", ([p.id for p in produtos],)
                )
            await conn.commit()
        return len(produtos)


class QdrantIndice:
    """O índice semântico. Guarda vetor e três campos de filtro — nunca um fato."""

    def __init__(self, url: str, colecao: str) -> None:
        self._url = url
        self._colecao = colecao

    async def reindexar(self, produtos: Sequence[Produto], vetores: Sequence[list[float]]) -> int:
        """Recria a coleção quando a dimensão muda, faz upsert e limpa o que sobrou."""
        if len(produtos) != len(vetores):
            raise ValueError(f"{len(produtos)} produtos para {len(vetores)} vetores")
        if not produtos:
            raise ValueError("recusando indexar um catálogo vazio")

        dimensao = len(vetores[0])
        client = AsyncQdrantClient(url=self._url)
        try:
            await self._garantir_colecao(client, dimensao)
            await client.upsert(
                collection_name=self._colecao,
                points=[
                    models.PointStruct(
                        id=ponto_de(produto.id), vector=vetor, payload=payload_de(produto)
                    )
                    for produto, vetor in zip(produtos, vetores, strict=True)
                ],
                wait=True,
            )
            # Mesmo motivo do DELETE no Postgres: produto que saiu do seed não pode
            # continuar sendo encontrado pela busca.
            await client.delete(
                collection_name=self._colecao,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must_not=[
                            models.FieldCondition(
                                key="id",
                                match=models.MatchAny(any=[produto.id for produto in produtos]),
                            )
                        ]
                    )
                ),
                wait=True,
            )
        finally:
            await client.close()
        return len(produtos)

    async def _garantir_colecao(self, client: AsyncQdrantClient, dimensao: int) -> None:
        """Cria a coleção, e recria quando o modelo de embedding mudou de tamanho.

        Trocar `EMBEDDING_MODEL` muda a dimensão do vetor. Fazer upsert de um vetor
        de 1536 numa coleção de 384 é um erro do servidor no meio da ingestão, com
        metade do catálogo dentro — mais confuso do que reconstruir.
        """
        if await client.collection_exists(self._colecao):
            atual = (await client.get_collection(self._colecao)).config.params.vectors
            # `vectors` é `VectorParams` para uma coleção de vetor único e um `dict`
            # para coleção de vetores nomeados. Só a primeira forma é nossa: se
            # alguém apontou `QDRANT_COLLECTION` para uma coleção de outro projeto,
            # o certo é reconstruir e não fazer upsert dentro dela.
            if isinstance(atual, models.VectorParams) and atual.size == dimensao:
                return
            await client.delete_collection(self._colecao)

        await client.create_collection(
            collection_name=self._colecao,
            vectors_config=models.VectorParams(size=dimensao, distance=models.Distance.COSINE),
        )
        # Sem índice de payload o filtro por tipo/disponibilidade vira varredura.
        # Com 50 produtos não se mede; a linha existe para a busca continuar sendo
        # busca quando o catálogo crescer.
        for campo in ("id", "tipo"):
            await client.create_payload_index(
                collection_name=self._colecao,
                field_name=campo,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
        await client.create_payload_index(
            collection_name=self._colecao,
            field_name="disponivel",
            field_schema=models.PayloadSchemaType.BOOL,
        )


def documentos(produtos: Iterable[Produto]) -> list[str]:
    """Os textos a embedar, na mesma ordem dos produtos."""
    return [texto_para_embedding(produto) for produto in produtos]


def _filtro(tipo: str | None, apenas_disponiveis: bool) -> models.Filter | None:
    """O filtro estrutural do Qdrant. Nunca dinheiro — esse é do Postgres."""
    condicoes: list[models.Condition] = []
    if tipo is not None:
        condicoes.append(
            models.FieldCondition(key="tipo", match=models.MatchValue(value=tipo)),
        )
    if apenas_disponiveis:
        condicoes.append(
            models.FieldCondition(key="disponivel", match=models.MatchValue(value=True)),
        )
    return models.Filter(must=condicoes) if condicoes else None


class QdrantBusca:
    """A busca semântica de verdade. Embeda a necessidade e devolve ids ordenados."""

    def __init__(self, url: str, colecao: str, embeddings: Embeddings) -> None:
        self._colecao = colecao
        self._embeddings = embeddings
        # Um cliente por processo, não por chamada: o cliente carrega pool de
        # conexão, e abrir um por consulta é o tipo de coisa que parece bem até a
        # segunda pessoa conversar ao mesmo tempo.
        self._client = AsyncQdrantClient(url=url)

    async def ids_similares(
        self, necessidade: str, *, tipo: str | None, apenas_disponiveis: bool, limite: int
    ) -> list[str]:
        vetor = await self._embeddings.aembed_query(necessidade)
        resposta = await self._client.query_points(
            collection_name=self._colecao,
            query=vetor,
            query_filter=_filtro(tipo, apenas_disponiveis),
            limit=limite,
            with_payload=True,
        )
        return [
            str(ponto.payload["id"])
            for ponto in resposta.points
            if ponto.payload and "id" in ponto.payload
        ]

    async def aclose(self) -> None:
        await self._client.close()


class CatalogoEmMemoria:
    """Um `Catalogo` de verdade, sem banco. Não é mock — é a segunda implementação.

    `docs/testes.md` §4: mock só na fronteira de port. É exatamente o que
    `InMemoryConfigStore` é para a configuração, e ele existe pelo mesmo motivo —
    a suíte unitária não sobe contêiner.
    """

    def __init__(self, produtos: Iterable[Produto]) -> None:
        self._produtos = {produto.id: produto for produto in produtos}

    async def por_ids(self, ids: Sequence[str]) -> dict[str, Produto]:
        return {pid: self._produtos[pid] for pid in ids if pid in self._produtos}

    async def quantos(self) -> int:
        return len(self._produtos)


class BuscaEmMemoria:
    """Ranqueia por sobreposição de palavras sobre o mesmo texto que seria embedado.

    Não pretende ser um bom buscador — pretende ser *o mesmo contrato*: recebe uma
    necessidade em português, aplica os mesmos filtros estruturais e devolve ids em
    ordem. É o que permite testar a tool sem chave de API e sem Qdrant, sem mockar
    nada que seja interno ao nosso código.
    """

    def __init__(self, produtos: Iterable[Produto]) -> None:
        self._produtos = tuple(produtos)

    async def ids_similares(
        self, necessidade: str, *, tipo: str | None, apenas_disponiveis: bool, limite: int
    ) -> list[str]:
        termos = {palavra for palavra in _palavras(necessidade) if len(palavra) > 3}
        candidatos = [
            produto
            for produto in self._produtos
            if (tipo is None or produto.tipo == tipo)
            and (not apenas_disponiveis or produto.disponivel)
        ]
        pontuados = sorted(
            candidatos,
            key=lambda produto: (
                -len(termos & _palavras(texto_para_embedding(produto))),
                produto.id,
            ),
        )
        return [produto.id for produto in pontuados[:limite]]


def _palavras(texto: str) -> set[str]:
    return {palavra.strip(".,;:!?—-").lower() for palavra in texto.split()}
