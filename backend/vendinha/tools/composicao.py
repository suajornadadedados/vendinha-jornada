"""`validar_composicao` — a tool com que o modelo submete a proposta dele ao código.

É o ida-e-volta que o ADR-013 descreve: *o modelo propõe uma cesta de R$163, o
código recusa contra um teto de R$150, o modelo ajusta — e as duas chamadas ficam no
mesmo trace.* Sem esta tool, "o código valida" seria uma frase num documento.

**Read-only, e registrada no subagent `recomendacao`.** Propor não é side effect, e a
fronteira do ADR-002 não se move por causa dela: a tool não tem como escrever porque
a porta que ela recebe (`catalogo.Catalogo`) não tem método de escrita. Quem autoriza
uma venda é `criar_pedido`, na S-04, e ele **revalida no servidor** — a validação que
passou pelo modelo nunca é a que autoriza (RF-2.7).

**Os produtos são relidos do banco, sempre.** A tool recebe ids, não payload. Se ela
aceitasse preço, rendimento ou `contem` vindos do argumento, o modelo poderia validar
uma composição contra números que ele mesmo escreveu — e o veredito passaria a
carimbar a alucinação em vez de pegá-la (R1, R10).

**Um id desconhecido não vira uma composição menor.** Ele volta em `nao_encontrados`
e nada é validado: aprovar a parte que existe seria devolver um total exato para uma
cesta que ninguém pediu, e o modelo leria isso como sucesso.

**O veredito viaja em `Resultado.encontrados`**, como todo retorno de tool aqui. É o
que o portão de groundedness enxerga (`evals/groundedness.py`), e um total fora dali
seria um número que o cliente ouve e a régua não confere.
"""

from decimal import Decimal

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, ConfigDict, Field

from vendinha import composicao
from vendinha.budget import run_with_timeout
from vendinha.catalogo import Alergeno, Catalogo
from vendinha.composicao import TipoDeEvento
from vendinha.tools import ReaisNaEntrada
from vendinha.tools.catalogo import ItemDeResultado, Resultado

NOMES = ("validar_composicao",)

# Uma composição maior do que isto não é um evento, é um pedido de despejo do
# catálogo. O limite existe pelo mesmo motivo que o de `consultar_preco`: um
# argumento sem teto é o caminho barato para estourar custo por repetição
# (`adversarial-006`, R6).
LIMITE_DE_ITENS = 20


class ItemDaComposicao(BaseModel):
    """Uma linha da composição, com a quantidade que o código derivou."""

    model_config = ConfigDict(frozen=True)

    produto_id: str
    nome: str
    tipo: str
    rendimento: int
    quantidade: int
    preco_unitario: Decimal
    subtotal: Decimal


class ProblemaDaComposicao(BaseModel):
    """Um motivo de recusa, com o `motivo` tipado ao lado da frase.

    O motivo separado da mensagem é o que deixa `golden-014` ser verificável: uma
    reprovação por slot precisa ser distinguível de uma reprovação por preço sem que
    alguém tenha que interpretar o texto.
    """

    model_config = ConfigDict(frozen=True)

    motivo: str
    mensagem: str
    produto_id: str | None = None


class ComposicaoValidada(ItemDeResultado):
    """O veredito, do jeito que o modelo o lê.

    Os nomes `total_composicao`, `valor_por_pessoa` e `problemas_composicao` são os
    que o corpus de `evals/` já usa em `fatos_ancorados` — o vocabulário do caso é de
    quem define a régua, e a tool se ajusta a ele, não o contrário.

    `orcamento_por_pessoa` e `excedente_por_pessoa` voltam no retorno de propósito.
    São dinheiro, e todo valor em dinheiro que o modelo disser ao cliente tem que ter
    saído de uma tool: o teto e o estouro repetidos de memória seriam preço sem
    origem, mesmo quando certos (`groundedness._precos_divergentes`, RF-1.3).
    """

    aprovada: bool
    tipo_de_evento: str
    pessoas: int
    atende_pessoas: int
    itens: tuple[ItemDaComposicao, ...]
    total_composicao: Decimal
    valor_por_pessoa: Decimal
    orcamento_por_pessoa: Decimal | None = None
    excedente_por_pessoa: Decimal | None = None
    problemas_composicao: tuple[ProblemaDaComposicao, ...] = ()

    @classmethod
    def de(cls, veredito: composicao.Veredito) -> "ComposicaoValidada":
        return cls(
            aprovada=veredito.aprovada,
            tipo_de_evento=veredito.tipo_de_evento.value,
            pessoas=veredito.pessoas,
            atende_pessoas=veredito.atende_pessoas,
            itens=tuple(
                ItemDaComposicao(
                    produto_id=item.produto_id,
                    nome=item.nome,
                    tipo=item.tipo,
                    rendimento=item.rendimento,
                    quantidade=item.quantidade,
                    preco_unitario=item.preco_unitario,
                    subtotal=item.subtotal,
                )
                for item in veredito.itens
            ),
            total_composicao=veredito.total,
            valor_por_pessoa=veredito.valor_por_pessoa,
            orcamento_por_pessoa=veredito.orcamento_por_pessoa,
            excedente_por_pessoa=veredito.excedente_por_pessoa,
            problemas_composicao=tuple(
                ProblemaDaComposicao(
                    motivo=problema.motivo.value,
                    mensagem=problema.mensagem,
                    produto_id=problema.produto_id,
                )
                for problema in veredito.problemas
            ),
        )


class ValidarComposicao(BaseModel):
    """O que `validar_composicao` aceita.

    Repare no que **não** está aqui: quantidade. Ela é derivada do `rendimento` de
    cada produto, e aceitá-la devolveria ao modelo a conta que a RF-1.6 tirou dele.
    """

    tipo_de_evento: TipoDeEvento = Field(
        description=(
            "O evento que o cliente descreveu. Cada tipo exige itens diferentes: "
            "café da manhã pede bebida quente, queijo, doce e petisco; happy hour "
            "pede destilado ou licor, queijo e petisco."
        )
    )
    pessoas: int = Field(
        ge=1, description="Quantas pessoas o evento atende. Pergunte antes de chutar."
    )
    produto_ids: list[str] = Field(
        description=(
            "Os ids dos produtos que você está propondo, como vieram de "
            "buscar_produtos. Não informe quantidade: ela sai do rendimento de cada item."
        ),
        min_length=1,
        max_length=LIMITE_DE_ITENS,
    )
    orcamento_por_pessoa: ReaisNaEntrada | None = Field(
        default=None,
        description="O teto por pessoa, em reais. Deixe vazio se o cliente ainda não disse.",
    )
    restricoes: list[Alergeno] = Field(
        default_factory=list,
        description=(
            "Restrições alimentares declaradas nesta conversa. Informe TODAS as que o "
            "cliente já mencionou, mesmo que tenha sido em uma mensagem anterior."
        ),
    )


def ferramentas_de_composicao(catalogo: Catalogo, timeout_seconds: float) -> tuple[BaseTool, ...]:
    """Constrói `validar_composicao` contra a porta recebida.

    Mesma forma de `ferramentas_de_catalogo`: fábrica, e não tool de módulo, porque a
    porta é injetada — é o que permite o eval e a suíte unitária rodarem contra
    `CatalogoEmMemoria` sem mockar nada interno (ADR-004).
    """

    async def validar_composicao(
        tipo_de_evento: TipoDeEvento,
        pessoas: int,
        produto_ids: list[str],
        orcamento_por_pessoa: Decimal | None = None,
        restricoes: list[Alergeno] | None = None,
    ) -> str:
        produtos = await run_with_timeout(
            catalogo.por_ids(produto_ids), timeout_seconds, "leitura da composição"
        )

        ausentes = tuple(pid for pid in produto_ids if pid not in produtos)
        if ausentes:
            return Resultado(
                nao_encontrados=ausentes,
                observacao=(
                    "nenhuma composição foi validada: corrija ou remova os ids acima e "
                    "chame de novo"
                ),
            ).model_dump_json(exclude_none=True)

        veredito = composicao.validar(
            tipo_de_evento=tipo_de_evento,
            pessoas=pessoas,
            # A ordem é a que o modelo propôs; `por_ids` devolve um mapa.
            produtos=[produtos[pid] for pid in produto_ids],
            orcamento_por_pessoa=orcamento_por_pessoa,
            restricoes=restricoes or (),
        )
        return Resultado(encontrados=(ComposicaoValidada.de(veredito),)).model_dump_json(
            exclude_none=True
        )

    return (
        StructuredTool.from_function(
            coroutine=validar_composicao,
            name="validar_composicao",
            description=(
                "Valida a composição que você montou: soma o total, deriva as "
                "quantidades do rendimento de cada item, confere os slots obrigatórios "
                "do evento e corta o que viola restrição alimentar. Use SEMPRE antes de "
                "apresentar qualquer composição ou qualquer total ao cliente — o total e "
                "o valor por pessoa que você disser são os que ela devolveu. Se ela "
                "reprovar, troque itens e valide de novo."
            ),
            args_schema=ValidarComposicao,
        ),
    )
