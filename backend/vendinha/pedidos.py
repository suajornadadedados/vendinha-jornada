"""O pedido — o primeiro lugar deste repositório onde o agente **escreve**.

Até a S-11 nada aqui persistia: o catálogo é lido, a composição é validada e o
veredito volta para a conversa. A S-04 traz a escrita, e com ela três decisões que
não são de armazenamento, são de fronteira.

**O pedido guarda o preço que valia no momento da criação, não uma referência.**
`item_do_pedido` carrega `preco_unitario` e `subtotal` copiados do catálogo na hora
em que `criar_pedido` rodou. Não é desnormalização por preguiça: um pedido que
consultasse `produto.preco` mudaria de valor sozinho no dia em que alguém rodar
`make seed` com uma tabela nova, e o cliente teria pago um número e a nota sairia
com outro. O catálogo é a verdade sobre *o que a loja vende hoje*; o pedido é a
verdade sobre *o que foi combinado naquele dia* — são fatos diferentes.

**Uma ou mais composições por pedido, e nenhuma entidade nova para o subgrupo.**
*"12 cestas de fim de ano, 2 sem álcool"* são duas composições no mesmo pedido, cada
uma com as suas restrições e o seu teto por cesta (ADR-013, RF-2.3, `golden-015`).
Descrever a exceção em texto livre produziria uma resposta que parece certa e um
pedido que sai errado.

**A idempotência do webhook é uma constraint, não um `if`.** `evento_de_pagamento`
tem o id do evento como chave primária, e `registrar_pagamento` insere com
`ON CONFLICT DO NOTHING` dentro da mesma transação que muda o status. Um `SELECT`
antes do `INSERT` é a corrida que dois webhooks simultâneos ganham — e gateway que
reenvia evento é comportamento normal, não falha (RF-2.5, R8).

**Duas implementações da mesma porta, como no `catalogo.py`.** `PedidosEmMemoria`
não é um stub: é o que permite `tests/security/test_composicao_invariants.py`
afirmar *"nada foi persistido"* sem contêiner, que é o que `docs/testes.md` §1 exige
das duas camadas.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Protocol

import psycopg
from psycopg.types.json import Json
from pydantic import BaseModel, ConfigDict, Field, field_validator

from vendinha.catalogo import Alergeno, TipoDeProduto
from vendinha.composicao import TipoDeEvento
from vendinha.documentos import (
    cep_valido,
    cnpj_valido,
    email_valido,
    normalizar_cnpj,
    uf_valida,
)

Texto = Annotated[str, Field(min_length=1)]


class StatusDoPedido(StrEnum):
    """Onde o pedido está. A S-05 acrescentou os dois desfechos fiscais.

    `aguardando_aprovacao_nf` é o nome que `golden-010` cita literalmente, e é o
    estado em que o pedido pousa depois do webhook: pago, e parado à espera da
    aprovação humana (ADR-003, R3).

    **Este status É a fila do operador.** Não existe uma tabela de fila: a fila é a
    consulta *"quem está em `aguardando_aprovacao_nf`"*, e sair dela é receber um
    desfecho. É o que faz um pedido rejeitado ficar **fora do caminho de emissão**
    sem depender de ninguém lembrar de tirá-lo de lá (`golden-011`), e o que o
    `adversarial-002` descreve quando diz *"permanecer em `aguardando_aprovacao_nf`
    até que exista decisão do operador"*.

    Não confunda com a decisão: quem autoriza uma emissão é a linha em
    `aprovacao_de_nf` (`fiscal.emitir`), nunca o status. O status é o que se lê.
    """

    AGUARDANDO_PAGAMENTO = "aguardando_pagamento"
    AGUARDANDO_APROVACAO_NF = "aguardando_aprovacao_nf"
    NOTA_EMITIDA = "nota_emitida"
    NOTA_REJEITADA = "nota_rejeitada"


class Endereco(BaseModel):
    """Onde a entrega chega — e o que a DANFE modelo 55 exige do destinatário.

    O B2C não coletava endereço, e o ADR-013 registra isso como furo que o pivô
    fechou: nota de destinatário PJ sem endereço não é nota fiel, é nota no que dava.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    logradouro: Texto
    numero: Texto
    complemento: str | None = None
    bairro: Texto
    cidade: Texto
    uf: Texto
    cep: Texto

    @field_validator("uf")
    @classmethod
    def _uf_existe(cls, valor: str) -> str:
        if not uf_valida(valor):
            raise ValueError(f"UF desconhecida: {valor!r}. Use a sigla de duas letras.")
        return valor.strip().upper()

    @field_validator("cep")
    @classmethod
    def _cep_tem_forma(cls, valor: str) -> str:
        if not cep_valido(valor):
            raise ValueError(f"CEP inválido: {valor!r}. São oito dígitos, como 30140-071.")
        return valor.strip()


class Empresa(BaseModel):
    """O comprador corporativo, validado por schema — nunca pelo modelo (RF-2.2).

    `cnpj` é guardado só com os dígitos: o mesmo documento escrito de duas formas
    seria duas empresas na hora de cruzar pedidos.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    razao_social: Texto
    cnpj: Texto
    # A inscrição estadual da compradora, e ela é **opcional por decisão** (S-05).
    # Não contribuinte de ICMS é a situação normal de boa parte das empresas que
    # compram um café da manhã, e exigi-la recusaria compradora legítima — além de
    # transformar a coleta num interrogatório. Ausente, a nota sai com `ISENTO` e
    # `indIEDest=9`, que é o que a norma manda imprimir (`nota/documento.py`).
    #
    # Repare que quem julga se a IE **confere** com o CNPJ não é código nenhum: é o
    # operador, na fila da S-05 — o `golden-011` rejeita a nota exatamente por isso.
    # É um bom exemplo do que a fila existe para pegar e o schema não.
    inscricao_estadual: str | None = None
    contato_nome: Texto
    contato_email: Texto
    endereco: Endereco

    @field_validator("cnpj")
    @classmethod
    def _cnpj_fecha(cls, valor: str) -> str:
        if not cnpj_valido(valor):
            raise ValueError(
                "CNPJ inválido: os dígitos verificadores não fecham. Confira o número "
                "com o cliente — não existe corrigir nem completar um documento aqui."
            )
        return normalizar_cnpj(valor)

    @field_validator("contato_email")
    @classmethod
    def _email_tem_forma(cls, valor: str) -> str:
        if not email_valido(valor):
            raise ValueError(f"e-mail inválido: {valor!r}")
        return valor.strip()


class ItemDoPedido(BaseModel):
    """Uma linha, congelada no preço que valia quando o pedido foi criado."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    produto_id: Texto
    nome: Texto
    tipo: TipoDeProduto
    rendimento: int = Field(ge=1)
    quantidade: int = Field(ge=1)
    preco_unitario: Decimal
    subtotal: Decimal


class ComposicaoDoPedido(BaseModel):
    """Uma composição já validada pelo servidor, do jeito que ela é persistida."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tipo_de_evento: TipoDeEvento
    pessoas: int = Field(ge=1)
    orcamento_por_pessoa: Decimal | None = None
    restricoes: tuple[Alergeno, ...] = ()
    itens: tuple[ItemDoPedido, ...] = Field(min_length=1)
    total: Decimal
    valor_por_pessoa: Decimal


class Pedido(BaseModel):
    """O pedido inteiro. Nada aqui foi somado pelo modelo."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Texto
    empresa: Empresa
    composicoes: tuple[ComposicaoDoPedido, ...] = Field(min_length=1)
    total: Decimal
    status: StatusDoPedido = StatusDoPedido.AGUARDANDO_PAGAMENTO
    url_pagamento: str | None = None
    criado_em: datetime = Field(default_factory=lambda: datetime.now(UTC))


def novo_id() -> str:
    """O identificador do pedido. Opaco de propósito.

    Nada de sequencial: um id que conta quantos pedidos a loja tem é um vazamento
    de negócio numa URL que o cliente vê, e um convite a pedir o pedido anterior.
    """
    return uuid.uuid4().hex


class Pedidos(Protocol):
    """A porta do pedido, como as tools a enxergam.

    Repare no que **não** está aqui: apagar, alterar item, mudar preço. Um pedido é
    fato consumado. O que muda depois da criação é o link de pagamento e o status,
    e cada um tem um método próprio com uma transição só — em vez de um `salvar`
    genérico que aceitaria qualquer coisa.
    """

    async def criar(self, pedido: Pedido) -> Pedido: ...

    async def por_id(self, pedido_id: str) -> Pedido | None: ...

    async def registrar_link(self, pedido_id: str, url: str) -> None: ...

    async def registrar_pagamento(self, pedido_id: str, evento_id: str) -> bool: ...

    async def aguardando_aprovacao_de_nf(self) -> tuple["Pedido", ...]: ...

    async def listar(self, *, limite: int = 50, offset: int = 0) -> tuple[Pedido, ...]: ...

    async def criados_desde(self, desde: datetime) -> tuple[Pedido, ...]: ...

    async def pagos_desde(self, desde: datetime) -> dict[str, datetime]: ...

    async def registrar_emissao(self, pedido_id: str) -> None: ...

    async def registrar_rejeicao(self, pedido_id: str) -> None: ...


class PedidoInexistente(LookupError):
    """Pediram para mexer num pedido que não existe."""


SCHEMA: tuple[str, ...] = (
    """
CREATE TABLE IF NOT EXISTS pedido (
    id            text PRIMARY KEY,
    razao_social  text NOT NULL,
    cnpj          text NOT NULL,
    contato_nome  text NOT NULL,
    contato_email text NOT NULL,
    endereco      jsonb NOT NULL,
    total         numeric(12,2) NOT NULL CHECK (total > 0),
    status        text NOT NULL,
    url_pagamento text,
    criado_em     timestamptz NOT NULL DEFAULT now()
)
""",
    # A S-05 acrescentou a coluna, e `CREATE TABLE IF NOT EXISTS` não a levaria a um
    # banco que já existe — quem rodou `make db-setup` na S-04 ficaria com a tabela
    # antiga e um `INSERT` quebrado. Não há ferramenta de migração neste projeto (e
    # trazer uma é decisão de ADR, não de spec), então a alteração é idempotente e
    # fica ao lado do `CREATE` que ela corrige.
    """
ALTER TABLE pedido ADD COLUMN IF NOT EXISTS inscricao_estadual text
""",
    """
CREATE TABLE IF NOT EXISTS composicao_do_pedido (
    pedido_id            text NOT NULL REFERENCES pedido(id) ON DELETE CASCADE,
    posicao              integer NOT NULL,
    tipo_de_evento       text NOT NULL,
    pessoas              integer NOT NULL CHECK (pessoas > 0),
    orcamento_por_pessoa numeric(10,2),
    restricoes           text[] NOT NULL DEFAULT '{}',
    total                numeric(12,2) NOT NULL,
    valor_por_pessoa     numeric(10,2) NOT NULL,
    PRIMARY KEY (pedido_id, posicao)
)
""",
    """
CREATE TABLE IF NOT EXISTS item_do_pedido (
    pedido_id      text NOT NULL,
    posicao        integer NOT NULL,
    produto_id     text NOT NULL,
    nome           text NOT NULL,
    tipo           text NOT NULL,
    rendimento     integer NOT NULL CHECK (rendimento > 0),
    quantidade     integer NOT NULL CHECK (quantidade > 0),
    preco_unitario numeric(8,2) NOT NULL CHECK (preco_unitario > 0),
    subtotal       numeric(12,2) NOT NULL,
    PRIMARY KEY (pedido_id, posicao, produto_id),
    FOREIGN KEY (pedido_id, posicao)
        REFERENCES composicao_do_pedido(pedido_id, posicao) ON DELETE CASCADE
)
""",
    # A chave primária é a idempotência (RF-2.5). Não há índice a criar depois nem
    # `if` a lembrar de escrever: o banco recusa o segundo insert do mesmo evento.
    """
CREATE TABLE IF NOT EXISTS evento_de_pagamento (
    evento_id   text PRIMARY KEY,
    pedido_id   text NOT NULL REFERENCES pedido(id) ON DELETE CASCADE,
    recebido_em timestamptz NOT NULL DEFAULT now()
)
""",
)


class PostgresPedidos:
    """O pedido no Postgres — três tabelas, e uma transação por operação."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    async def setup(self) -> None:
        async with await psycopg.AsyncConnection.connect(self._dsn, autocommit=True) as conn:
            for statement in SCHEMA:
                await conn.execute(statement.encode())

    async def criar(self, pedido: Pedido) -> Pedido:
        """Grava pedido, composições e itens. Uma transação, tudo ou nada.

        Meio pedido gravado é pior do que nenhum: ele apareceria na fila do
        operador da S-05 com um item faltando e um total que não bate com a soma
        das linhas.
        """
        async with await psycopg.AsyncConnection.connect(self._dsn) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO pedido (id, razao_social, cnpj, inscricao_estadual,"
                    " contato_nome, contato_email,"
                    " endereco, total, status, url_pagamento, criado_em)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        pedido.id,
                        pedido.empresa.razao_social,
                        pedido.empresa.cnpj,
                        pedido.empresa.inscricao_estadual,
                        pedido.empresa.contato_nome,
                        pedido.empresa.contato_email,
                        Json(pedido.empresa.endereco.model_dump()),
                        pedido.total,
                        pedido.status.value,
                        pedido.url_pagamento,
                        pedido.criado_em,
                    ),
                )
                for posicao, composicao in enumerate(pedido.composicoes):
                    await cur.execute(
                        "INSERT INTO composicao_do_pedido (pedido_id, posicao, tipo_de_evento,"
                        " pessoas, orcamento_por_pessoa, restricoes, total, valor_por_pessoa)"
                        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            pedido.id,
                            posicao,
                            composicao.tipo_de_evento.value,
                            composicao.pessoas,
                            composicao.orcamento_por_pessoa,
                            list(composicao.restricoes),
                            composicao.total,
                            composicao.valor_por_pessoa,
                        ),
                    )
                    await cur.executemany(
                        "INSERT INTO item_do_pedido (pedido_id, posicao, produto_id, nome, tipo,"
                        " rendimento, quantidade, preco_unitario, subtotal)"
                        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        [
                            (
                                pedido.id,
                                posicao,
                                item.produto_id,
                                item.nome,
                                item.tipo,
                                item.rendimento,
                                item.quantidade,
                                item.preco_unitario,
                                item.subtotal,
                            )
                            for item in composicao.itens
                        ],
                    )
            await conn.commit()
        return pedido

    async def por_id(self, pedido_id: str) -> Pedido | None:
        async with await psycopg.AsyncConnection.connect(self._dsn, autocommit=True) as conn:
            cabecalho = await (
                await conn.execute(
                    "SELECT id, razao_social, cnpj, contato_nome, contato_email, endereco,"
                    " total, status, url_pagamento, criado_em, inscricao_estadual"
                    " FROM pedido WHERE id = %s",
                    (pedido_id,),
                )
            ).fetchone()
            if cabecalho is None:
                return None

            composicoes = await (
                await conn.execute(
                    "SELECT posicao, tipo_de_evento, pessoas, orcamento_por_pessoa, restricoes,"
                    " total, valor_por_pessoa FROM composicao_do_pedido"
                    " WHERE pedido_id = %s ORDER BY posicao",
                    (pedido_id,),
                )
            ).fetchall()
            itens = await (
                await conn.execute(
                    "SELECT posicao, produto_id, nome, tipo, rendimento, quantidade,"
                    " preco_unitario, subtotal FROM item_do_pedido"
                    " WHERE pedido_id = %s ORDER BY posicao, produto_id",
                    (pedido_id,),
                )
            ).fetchall()

        por_posicao: dict[int, list[ItemDoPedido]] = {}
        for linha in itens:
            por_posicao.setdefault(int(linha[0]), []).append(
                ItemDoPedido(
                    produto_id=linha[1],
                    nome=linha[2],
                    tipo=linha[3],
                    rendimento=int(linha[4]),
                    quantidade=int(linha[5]),
                    preco_unitario=linha[6],
                    subtotal=linha[7],
                )
            )

        return Pedido(
            id=cabecalho[0],
            empresa=Empresa(
                razao_social=cabecalho[1],
                cnpj=cabecalho[2],
                # No fim do SELECT, e não na posição do modelo: a coluna chegou
                # depois (S-05) e um `ALTER TABLE` a acrescenta no fim. Ler pelo
                # índice que a query declara é o que mantém as duas coisas juntas.
                inscricao_estadual=cabecalho[10],
                contato_nome=cabecalho[3],
                contato_email=cabecalho[4],
                endereco=Endereco.model_validate(cabecalho[5]),
            ),
            composicoes=tuple(
                ComposicaoDoPedido(
                    tipo_de_evento=TipoDeEvento(linha[1]),
                    pessoas=int(linha[2]),
                    orcamento_por_pessoa=linha[3],
                    restricoes=tuple(linha[4]),
                    itens=tuple(por_posicao.get(int(linha[0]), ())),
                    total=linha[5],
                    valor_por_pessoa=linha[6],
                )
                for linha in composicoes
            ),
            total=cabecalho[6],
            status=StatusDoPedido(cabecalho[7]),
            url_pagamento=cabecalho[8],
            criado_em=cabecalho[9],
        )

    async def registrar_link(self, pedido_id: str, url: str) -> None:
        async with await psycopg.AsyncConnection.connect(self._dsn, autocommit=True) as conn:
            cursor = await conn.execute(
                "UPDATE pedido SET url_pagamento = %s WHERE id = %s", (url, pedido_id)
            )
        if cursor.rowcount == 0:
            raise PedidoInexistente(pedido_id)

    async def registrar_pagamento(self, pedido_id: str, evento_id: str) -> bool:
        """True se ESTE evento produziu efeito; False se ele já tinha sido visto.

        As duas escritas na mesma transação de propósito. Separadas, um processo
        que morresse no meio deixaria o evento registrado e o pedido parado em
        `aguardando_pagamento` — pago para o gateway, não pago para nós, e sem
        segunda chance porque o reenvio seria recusado como duplicata.
        """
        async with await psycopg.AsyncConnection.connect(self._dsn) as conn:
            async with conn.cursor() as cur:
                existe = await (
                    await cur.execute("SELECT 1 FROM pedido WHERE id = %s", (pedido_id,))
                ).fetchone()
                if existe is None:
                    raise PedidoInexistente(pedido_id)

                inserido = await cur.execute(
                    "INSERT INTO evento_de_pagamento (evento_id, pedido_id) VALUES (%s, %s)"
                    " ON CONFLICT (evento_id) DO NOTHING",
                    (evento_id, pedido_id),
                )
                if inserido.rowcount == 0:
                    await conn.rollback()
                    return False

                await cur.execute(
                    "UPDATE pedido SET status = %s WHERE id = %s AND status = %s",
                    (
                        StatusDoPedido.AGUARDANDO_APROVACAO_NF.value,
                        pedido_id,
                        StatusDoPedido.AGUARDANDO_PAGAMENTO.value,
                    ),
                )
            await conn.commit()
        return True

    async def aguardando_aprovacao_de_nf(self) -> tuple[Pedido, ...]:
        """A fila do operador, do mais antigo para o mais novo (S-05, REQ-2).

        Uma consulta pelos ids e depois um `por_id` por pedido. É N+1, e é a escolha
        certa aqui: a fila do operador tem a ordem de grandeza de "o que chegou hoje"
        (o PRD assume uma loja e um operador), e reescrever a leitura completa do
        pedido — cabeçalho, composições e itens — numa segunda query com três joins
        criaria uma segunda montagem do mesmo objeto. Duas montagens divergem, e a
        que diverge é sempre a que o operador está olhando na hora de aprovar.
        """
        async with await psycopg.AsyncConnection.connect(self._dsn, autocommit=True) as conn:
            linhas = await (
                await conn.execute(
                    "SELECT id FROM pedido WHERE status = %s ORDER BY criado_em",
                    (StatusDoPedido.AGUARDANDO_APROVACAO_NF.value,),
                )
            ).fetchall()

        na_fila = [await self.por_id(linha[0]) for linha in linhas]
        return tuple(pedido for pedido in na_fila if pedido is not None)

    async def _ids(self, sql: str, args: tuple[object, ...]) -> tuple[str, ...]:
        async with await psycopg.AsyncConnection.connect(self._dsn, autocommit=True) as conn:
            linhas = await (await conn.execute(sql, args)).fetchall()
        return tuple(str(linha[0]) for linha in linhas)

    async def _muitos(self, ids: Sequence[str]) -> tuple["Pedido", ...]:
        """Monta cada pedido pelo caminho que já existe.

        É N+1 e é deliberado: `por_id` faz três consultas para montar cabeçalho,
        composições e itens, e uma segunda montagem em lote seria a projeção que
        diverge — exatamente o que `PedidoNaFila` recusa fazer com a nota. A página
        do painel é de 50, e o limite está no contrato para que continue sendo.
        """
        encontrados = [await self.por_id(pedido_id) for pedido_id in ids]
        return tuple(pedido for pedido in encontrados if pedido is not None)

    async def listar(self, *, limite: int = 50, offset: int = 0) -> tuple["Pedido", ...]:
        return await self._muitos(
            await self._ids(
                "SELECT id FROM pedido ORDER BY criado_em DESC LIMIT %s OFFSET %s",
                (limite, offset),
            )
        )

    async def criados_desde(self, desde: datetime) -> tuple["Pedido", ...]:
        return await self._muitos(
            await self._ids(
                "SELECT id FROM pedido WHERE criado_em >= %s ORDER BY criado_em DESC",
                (desde,),
            )
        )

    async def pagos_desde(self, desde: datetime) -> dict[str, datetime]:
        """Quando cada pedido teve o pagamento registrado — é a entrada na fila.

        `MIN` porque um gateway reenvia evento e a idempotência guarda o segundo
        como linha nova de `evento_de_pagamento`: o que interessa é o primeiro, que
        é quando o pedido de fato passou a esperar decisão.
        """
        async with await psycopg.AsyncConnection.connect(self._dsn, autocommit=True) as conn:
            linhas = await (
                await conn.execute(
                    "SELECT pedido_id, MIN(recebido_em) FROM evento_de_pagamento"
                    " WHERE recebido_em >= %s GROUP BY pedido_id",
                    (desde,),
                )
            ).fetchall()
        return {str(linha[0]): linha[1] for linha in linhas}

    async def registrar_emissao(self, pedido_id: str) -> None:
        await self._desfecho_da_nota(pedido_id, StatusDoPedido.NOTA_EMITIDA)

    async def registrar_rejeicao(self, pedido_id: str) -> None:
        await self._desfecho_da_nota(pedido_id, StatusDoPedido.NOTA_REJEITADA)

    async def _desfecho_da_nota(self, pedido_id: str, status: StatusDoPedido) -> None:
        """Tira o pedido da fila. Só a partir de `aguardando_aprovacao_nf`.

        O `AND status = ...` é a transição, e ele é o que impede uma segunda
        chamada de mexer num pedido que já teve desfecho — um pedido rejeitado não
        vira emitido porque alguém chamou a função de novo. Silencioso quando não
        muda nada, de propósito: `fiscal.emitir` é idempotente e chama isto nos dois
        caminhos, e a segunda chamada não tem nada a consertar.
        """
        async with await psycopg.AsyncConnection.connect(self._dsn, autocommit=True) as conn:
            cursor = await conn.execute(
                "UPDATE pedido SET status = %s WHERE id = %s AND status = %s",
                (status.value, pedido_id, StatusDoPedido.AGUARDANDO_APROVACAO_NF.value),
            )
        if cursor.rowcount == 0 and await self.por_id(pedido_id) is None:
            raise PedidoInexistente(pedido_id)


class PedidosEmMemoria:
    """A mesma porta, sem contêiner. Não é stub: é a implementação das duas suítes.

    `gravados` é público de propósito — é o que permite
    `tests/security/test_composicao_invariants.py` afirmar que **nada** foi
    persistido, que é uma asserção sobre ausência e não sobre mensagem de erro.
    """

    def __init__(self) -> None:
        self.gravados: dict[str, Pedido] = {}
        self.eventos: set[str] = set()
        # Quando cada pedido teve o PRIMEIRO pagamento registrado. Separado de
        # `eventos` porque aquele conjunto é a idempotência e um teste afirma o
        # seu conteúdo exato; este é a medida de quando a fila começou a esperar.
        self.pagos: dict[str, datetime] = {}

    async def criar(self, pedido: Pedido) -> Pedido:
        self.gravados[pedido.id] = pedido
        return pedido

    async def por_id(self, pedido_id: str) -> Pedido | None:
        return self.gravados.get(pedido_id)

    async def registrar_link(self, pedido_id: str, url: str) -> None:
        pedido = self.gravados.get(pedido_id)
        if pedido is None:
            raise PedidoInexistente(pedido_id)
        self.gravados[pedido_id] = pedido.model_copy(update={"url_pagamento": url})

    async def registrar_pagamento(self, pedido_id: str, evento_id: str) -> bool:
        pedido = self.gravados.get(pedido_id)
        if pedido is None:
            raise PedidoInexistente(pedido_id)
        if evento_id in self.eventos:
            return False
        self.eventos.add(evento_id)
        self.pagos.setdefault(pedido_id, datetime.now(UTC))
        if pedido.status is StatusDoPedido.AGUARDANDO_PAGAMENTO:
            self.gravados[pedido_id] = pedido.model_copy(
                update={"status": StatusDoPedido.AGUARDANDO_APROVACAO_NF}
            )
        return True

    async def aguardando_aprovacao_de_nf(self) -> tuple[Pedido, ...]:
        return tuple(
            sorted(
                (
                    pedido
                    for pedido in self.gravados.values()
                    if pedido.status is StatusDoPedido.AGUARDANDO_APROVACAO_NF
                ),
                key=lambda pedido: pedido.criado_em,
            )
        )

    async def listar(self, *, limite: int = 50, offset: int = 0) -> tuple[Pedido, ...]:
        ordenados = sorted(
            self.gravados.values(), key=lambda pedido: pedido.criado_em, reverse=True
        )
        return tuple(ordenados[offset : offset + limite])

    async def criados_desde(self, desde: datetime) -> tuple[Pedido, ...]:
        return tuple(
            sorted(
                (p for p in self.gravados.values() if p.criado_em >= desde),
                key=lambda pedido: pedido.criado_em,
                reverse=True,
            )
        )

    async def pagos_desde(self, desde: datetime) -> dict[str, datetime]:
        return {pedido_id: em for pedido_id, em in self.pagos.items() if em >= desde}

    async def registrar_emissao(self, pedido_id: str) -> None:
        await self._desfecho_da_nota(pedido_id, StatusDoPedido.NOTA_EMITIDA)

    async def registrar_rejeicao(self, pedido_id: str) -> None:
        await self._desfecho_da_nota(pedido_id, StatusDoPedido.NOTA_REJEITADA)

    async def _desfecho_da_nota(self, pedido_id: str, status: StatusDoPedido) -> None:
        """A mesma transição guardada do Postgres, à mão.

        A guarda é reproduzida e não simplificada: as duas implementações da porta
        têm que se comportar igual, e é justamente contra as duas que
        `tests/security/test_hitl_invariant.py` roda.
        """
        pedido = self.gravados.get(pedido_id)
        if pedido is None:
            raise PedidoInexistente(pedido_id)
        if pedido.status is StatusDoPedido.AGUARDANDO_APROVACAO_NF:
            self.gravados[pedido_id] = pedido.model_copy(update={"status": status})


def total_de(composicoes: Sequence[ComposicaoDoPedido]) -> Decimal:
    """A soma dos totais das composições, em `Decimal`.

    Uma função e não uma property calculada no `Pedido`: o total é gravado, e o
    momento de somá-lo é o da criação. Recalcular na leitura faria um pedido antigo
    mudar de valor se a regra de soma mudasse — e o pedido é o que foi combinado
    naquele dia.
    """
    return sum((composicao.total for composicao in composicoes), start=Decimal("0.00"))


__all__ = [
    "SCHEMA",
    "ComposicaoDoPedido",
    "Empresa",
    "Endereco",
    "ItemDoPedido",
    "Pedido",
    "PedidoInexistente",
    "Pedidos",
    "PedidosEmMemoria",
    "PostgresPedidos",
    "StatusDoPedido",
    "novo_id",
    "total_de",
]
