"""As três tools de leitura do catálogo — e por que elas devolvem JSON.

O ADR-001 divide o trabalho: o modelo decide o que dizer, e o que ele pode dizer
sobre produto entra por aqui. Três decisões dão forma a este arquivo.

**Devolvem JSON, não prosa.** Um retorno em texto corrido ("o Canastra meia-cura
custa 89,90") é indistinguível, no histórico da conversa, de uma frase que o
próprio modelo escreveu. Em JSON, o eval de groundedness consegue perguntar *este
preço saiu de qual tool?* e responder com certeza — e é essa pergunta que a
tabela de métricas da S-03 manda medir.

**Preço é serializado como string.** É o padrão do Pydantic para `Decimal` em
JSON, e é o que queremos: `89.90` como número JSON volta a ser float na primeira
biblioteca que reparsear, e aí a exatidão que o banco guardou se perde no último
metro (`docs/testes.md` §4).

**Duas delas aceitam lista, e isso é economia de verdade.** Cada ida ao modelo
reenvia a conversa inteira, então o custo de um turno não cresce com o número de
tools chamadas — cresce com o número de **voltas** do laço. Detalhar seis produtos
um a um custa seis reenvios do histórico; detalhar os seis numa chamada custa um.
Numa composição de evento essa diferença é o que separa caber no teto de sessão de
estourá-lo com o trabalho já feito (R6, RNF-3).

Repare que isso não afrouxa nada: a regra continua sendo que todo produto citado
passou por `detalhar_produto`. Mudou quantas vezes se bate na porta, não o que
precisa ser perguntado.

**Nenhuma delas escreve.** Não por instrução no prompt — por não existir método
de escrita nas portas que elas recebem (`catalogo.Catalogo` e `catalogo.Busca`).
Uma injeção que peça "aplique 90% de desconto" não encontra o que chamar: a tool
não está negada, ela não está lá (ADR-002, R4, e o caso `adversarial-004`).

O nome das tools e dos argumentos é em português porque o corpus de `evals/` os
cita literalmente (`tools.permitidas: [buscar_produtos, ...]`). Trocar o nome aqui
reprovaria casos que não mudaram.
"""

from decimal import Decimal

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, ConfigDict, Field, SerializeAsAny

from vendinha.budget import run_with_timeout
from vendinha.catalogo import Busca, Catalogo, Produto
from vendinha.tools import ReaisNaEntrada

# Quantos ids pedir ao ranqueador antes de filtrar preço no banco. A faixa de
# preço é aplicada depois — porque dinheiro é `Decimal` e vive no Postgres —, e
# sem folga um pedido de "algo mais em conta" poderia voltar vazio só porque os
# cinco primeiros do ranking eram todos caros.
FOLGA_DE_RANQUEAMENTO = 6
LIMITE_MAXIMO = 8

NOMES = ("buscar_produtos", "detalhar_produto", "consultar_preco")


class ItemDeResultado(BaseModel):
    """A base de tudo o que viaja em `Resultado.encontrados`.

    Existe para que uma tool de outro módulo — `tools/composicao.py` — possa pôr o
    veredito dela no mesmo envelope sem que `Resultado` precise importá-la de volta.
    A alternativa era uma união crescente aqui dentro, e ela criaria um ciclo de
    import no primeiro arquivo de tool que não fosse este.

    Não é só arrumação. O portão de groundedness só enxerga `encontrados`
    (`evals/groundedness.py`): um retorno de tool que inventasse envelope próprio
    ficaria invisível para a régua, e um fato invisível para a régua é um fato que
    ninguém está conferindo.
    """

    model_config = ConfigDict(frozen=True)


class ProdutoEncontrado(ItemDeResultado):
    """Um produto como a busca o apresenta. Tudo aqui veio do Postgres."""

    id: str
    nome: str
    tipo: str
    regiao: str
    descricao: str
    intensidade: str
    harmonizacao: tuple[str, ...]
    ocasiao: tuple[str, ...]
    peso: str
    preco: Decimal
    disponivel: bool
    prazo_estimado: str

    @classmethod
    def de(cls, produto: Produto) -> "ProdutoEncontrado":
        return cls(**produto.model_dump(include=set(cls.model_fields)))


class ProdutoDetalhado(ProdutoEncontrado):
    """O produto inteiro, incluindo o que só o tipo dele tem.

    **`rendimento` e `contem` só aparecem aqui, e não em `ProdutoEncontrado`.**
    É a mesma regra mecânica que o prompt já aplica a maturação e torra: a busca
    serve para escolher, o detalhe é o que autoriza descrever. Descrever pela
    lembrança de um resultado de busca é como um atributo inventado entra numa
    frase que parece ancorada — e para alérgeno essa frase não custa uma
    recomendação ruim, custa alguém passar mal (R10, `golden-013`).

    Os dois campos existem no `Produto` desde a S-10, mas `ProdutoEncontrado.de`
    filtra por `model_fields`: exposição aqui é opt-in, e um campo que ninguém
    declarou some em silêncio no caminho até o cliente.
    """

    produtor: str
    rendimento: int
    contem: tuple[str, ...] = ()
    maturacao: str | None = None
    torra: str | None = None
    notas_sensoriais: tuple[str, ...] = ()
    teor_alcoolico: str | None = None


class PrecoDoCatalogo(ItemDeResultado):
    """A resposta de `consultar_preco`: o valor, e se dá para vender.

    `disponivel` vem junto de propósito. Preço sem disponibilidade é o convite
    para o agente cotar com precisão um produto que a loja não tem — ancorado e
    errado ao mesmo tempo (`golden-006`).
    """

    id: str
    nome: str
    preco: Decimal
    disponivel: bool


class Resultado(BaseModel):
    """O envelope de toda resposta de tool.

    `nao_encontrados` existe para que "não temos esse produto" seja um dado, e não
    uma lista mais curta que o modelo pode interpretar como quiser. Um id que não
    voltou some silenciosamente; um id em `nao_encontrados` é uma afirmação.

    `SerializeAsAny` porque o campo é declarado pela base: sem ele o Pydantic
    serializaria cada item pelo tipo **declarado** e um `ProdutoDetalhado` sairia
    daqui com os campos de `ProdutoEncontrado` só — que é o mesmo sumiço silencioso
    que `extra="forbid"` no `Produto` existe para impedir, um andar acima.
    """

    encontrados: tuple[SerializeAsAny[ItemDeResultado], ...] = ()
    nao_encontrados: tuple[str, ...] = ()
    observacao: str | None = None


class BuscarProdutos(BaseModel):
    """O que `buscar_produtos` aceita."""

    necessidade: str = Field(
        description=(
            "O que o cliente descreveu, com as palavras dele. 'presente pra minha "
            "sogra que ama vinho tinto' funciona melhor aqui do que 'queijo'."
        )
    )
    tipo: str | None = Field(
        default=None,
        description="queijo | cafe | doce | cachaca | licor. Deixe vazio se não souber.",
    )
    preco_minimo: ReaisNaEntrada | None = Field(default=None, description="Em reais.")
    preco_maximo: ReaisNaEntrada | None = Field(default=None, description="Em reais.")
    apenas_disponiveis: bool = Field(
        default=True,
        description="False só quando o cliente perguntou por um item específico que pode faltar.",
    )
    limite: int = Field(default=4, ge=1, le=LIMITE_MAXIMO)


class DetalharProduto(BaseModel):
    produto_ids: list[str] = Field(
        description=(
            "Um ou mais ids, como vieram de buscar_produtos. Peça TODOS de uma vez: "
            "os produtos que você pretende citar ou montar numa composição."
        ),
        min_length=1,
        max_length=LIMITE_MAXIMO,
    )


class ConsultarPreco(BaseModel):
    produto_ids: list[str] = Field(
        description="Um ou mais ids. Peça todos de uma vez para comparar preços.",
        min_length=1,
        max_length=LIMITE_MAXIMO,
    )


def ferramentas_de_catalogo(
    busca: Busca, catalogo: Catalogo, timeout_seconds: float
) -> tuple[BaseTool, ...]:
    """Constrói as três tools contra as portas recebidas.

    Fábrica, e não tools de módulo, porque a porta é injetada: é o que permite o
    eval e a suíte unitária rodarem contra `CatalogoEmMemoria` sem mockar nada
    interno (ADR-004, `docs/testes.md` §4).
    """

    async def buscar_produtos(
        necessidade: str,
        tipo: str | None = None,
        preco_minimo: Decimal | None = None,
        preco_maximo: Decimal | None = None,
        apenas_disponiveis: bool = True,
        limite: int = 4,
    ) -> str:
        ids = await run_with_timeout(
            busca.ids_similares(
                necessidade,
                tipo=tipo,
                apenas_disponiveis=apenas_disponiveis,
                limite=limite + FOLGA_DE_RANQUEAMENTO,
            ),
            timeout_seconds,
            "busca semântica no catálogo",
        )
        produtos = await run_with_timeout(
            catalogo.por_ids(ids), timeout_seconds, "leitura do catálogo"
        )

        # A ordem do ranqueador é preservada: o Postgres devolve um mapa, e
        # reordenar por id ou por preço aqui jogaria fora a única coisa que a
        # busca semântica produziu.
        na_ordem = [produtos[pid] for pid in ids if pid in produtos]
        na_faixa = [
            produto
            for produto in na_ordem
            if (preco_minimo is None or produto.preco >= preco_minimo)
            and (preco_maximo is None or produto.preco <= preco_maximo)
        ]

        observacao = None
        if not na_faixa and na_ordem:
            # Dizer que a faixa esvaziou o resultado, em vez de devolver vazio: o
            # modelo precisa saber que existem produtos e que o preço foi o corte,
            # senão ele conclui que a loja não vende nada do gênero.
            observacao = (
                "nenhum produto do catálogo cai nessa faixa de preço; "
                "considere buscar de novo sem o limite"
            )

        return Resultado(
            encontrados=tuple(ProdutoEncontrado.de(p) for p in na_faixa[:limite]),
            observacao=observacao,
        ).model_dump_json(exclude_none=True)

    async def detalhar_produto(produto_ids: list[str]) -> str:
        produtos = await run_with_timeout(
            catalogo.por_ids(produto_ids), timeout_seconds, "leitura do catálogo"
        )
        return Resultado(
            encontrados=tuple(
                ProdutoDetalhado(**produto.model_dump())
                for pid in produto_ids
                if (produto := produtos.get(pid)) is not None
            ),
            nao_encontrados=tuple(pid for pid in produto_ids if pid not in produtos),
        ).model_dump_json(exclude_none=True)

    async def consultar_preco(produto_ids: list[str]) -> str:
        produtos = await run_with_timeout(
            catalogo.por_ids(produto_ids), timeout_seconds, "consulta de preço"
        )
        return Resultado(
            encontrados=tuple(
                PrecoDoCatalogo(
                    id=produto.id,
                    nome=produto.nome,
                    preco=produto.preco,
                    disponivel=produto.disponivel,
                )
                for pid in produto_ids
                if (produto := produtos.get(pid)) is not None
            ),
            nao_encontrados=tuple(pid for pid in produto_ids if pid not in produtos),
        ).model_dump_json(exclude_none=True)

    return (
        StructuredTool.from_function(
            coroutine=buscar_produtos,
            name="buscar_produtos",
            description=(
                "Encontra produtos do catálogo a partir da necessidade do cliente, em "
                "linguagem natural. Use SEMPRE antes de citar qualquer produto: é a única "
                "forma de saber o que a loja vende. Aceita filtro por tipo e faixa de preço."
            ),
            args_schema=BuscarProdutos,
        ),
        StructuredTool.from_function(
            coroutine=detalhar_produto,
            name="detalhar_produto",
            description=(
                "Todos os atributos de um ou mais produtos — maturação, torra, notas "
                "sensoriais, teor alcoólico, prazo, rendimento e alérgenos. Use antes de "
                "afirmar qualquer atributo específico, e peça todos os produtos numa "
                "chamada só: uma lista de seis custa o mesmo que um."
            ),
            args_schema=DetalharProduto,
        ),
        StructuredTool.from_function(
            coroutine=consultar_preco,
            name="consultar_preco",
            description=(
                "O preço vigente no banco e se o produto está disponível. Use antes de dizer "
                "qualquer valor, inclusive para comparar duas opções."
            ),
            args_schema=ConsultarPreco,
        ),
    )
