"""O motor de regras da composição — a metade "o código decide" da regra de ouro.

O ADR-013 diz o que este módulo é: *o LLM escolhe os produtos — isso ele faz bem, e
é onde o valor dele está. O código soma em `Decimal`, exige os slots obrigatórios do
tipo de evento e recusa o que estoura orçamento ou viola restrição alimentar.*

**Função pura sobre `Produto`, sem I/O.** É o que permite a suíte `unit` rodar sem
contêiner (`docs/testes.md` §1). Quem lê do banco é a tool em
`vendinha/tools/composicao.py`; aqui só entram objetos já lidos — e é de propósito
que não haja como buscar nada daqui, porque um validador que consulta é um validador
que pode consultar a fonte errada.

**Quantidade não é argumento.** Ela é derivada do `rendimento` de cada produto:
quantas pessoas o item atende num evento é campo do catálogo, e dividir "40 pessoas"
por esse número é conta — logo, do código (RF-1.6, R1). Se a quantidade entrasse pela
tool, o modelo teria de volta exatamente o poder que o pivô B2B tirou dele.

**Slots são código, não preferência do modelo.** *Café da manhã sem café é inválido*,
e essa frase precisa ser executável. Sem slots, "montar uma composição" não tem nada
objetivo para recusar e o validador vira opinião.

**Restrição alimentar é corte, nunca julgamento.** O corte é o campo `contem`, lido do
Postgres — não a descrição, não o nome, não o que o modelo sabe sobre o produto. O
seed guarda o par que prova por que: o biscoito de polvilho é sem glúten e a broa de
fubá ao lado leva trigo, e as duas suposições que alguém faria pelo nome estão erradas
(R10, `golden-013`, `adversarial-007`).

Nada aqui autoriza uma venda. `criar_pedido` revalida no servidor, na S-04: a
validação que passou pelo modelo nunca é a que autoriza (RF-2.7).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_UP, Decimal
from enum import StrEnum

from vendinha.catalogo import Alergeno, Produto, TipoDeProduto

# Dinheiro é sempre duas casas, e o arredondamento do valor por pessoa é **para
# cima**. Não é preciosismo: `golden-007` lista "arredondar o valor por pessoa para
# baixo para caber no teto" como `nao_deve`, e um veredito que arredonda para baixo
# faz a composição parecer mais barata do que ela é. O teto, esse, é conferido contra
# o total exato — ver `_estouro`.
CENTAVOS = Decimal("0.01")
ZERO = Decimal("0.00")


class TipoDeEvento(StrEnum):
    """Os quatro eventos que a Vendinha monta (ADR-013)."""

    CAFE_DA_MANHA = "cafe_da_manha"
    HAPPY_HOUR = "happy_hour"
    CESTA_DE_FIM_DE_ANO = "cesta_de_fim_de_ano"
    KIT_BOAS_VINDAS = "kit_boas_vindas"


@dataclass(frozen=True)
class Slot:
    """Um lugar que o evento exige preenchido, e como se diz isso ao cliente.

    `tipos` é um conjunto porque um slot pode ser satisfeito por mais de um tipo —
    o happy hour aceita cachaça **ou** licor, e exigir os dois recusaria composições
    legítimas. Recusa errada ensina o modelo a desconfiar do validador, que é pior
    do que não ter validador.

    `como_dizer` existe para o problema sair em português de balcão. O slot é o
    `tipo` do catálogo (`cafe`), mas ninguém pede "um item de tipo cafe": pede uma
    bebida quente. É esse o vocabulário que `golden-014` espera na explicação.
    """

    tipos: frozenset[TipoDeProduto]
    como_dizer: str


@dataclass(frozen=True)
class RegraDoEvento:
    """O que um tipo de evento exige.

    Duas formas, porque a cesta de fim de ano não cabe na primeira: ela não pede
    itens nomeados, pede **variedade**. Espremer isso em slots daria uma lista de
    "≥1 de qualquer coisa" repetida três vezes, que descreve a regra errada — dois
    queijos e um café passariam.
    """

    slots: tuple[Slot, ...] = ()
    tipos_distintos: int = 0


# A tabela da S-11 §"Decisões de desenho", em código. É a única fonte dela: mudar um
# slot aqui é mudar o produto, e o diff mostra isso.
REGRAS: Mapping[TipoDeEvento, RegraDoEvento] = {
    TipoDeEvento.CAFE_DA_MANHA: RegraDoEvento(
        slots=(
            Slot(frozenset({"cafe"}), "bebida quente"),
            Slot(frozenset({"queijo"}), "queijo"),
            Slot(frozenset({"doce"}), "doce"),
            Slot(frozenset({"petisco"}), "petisco"),
        )
    ),
    TipoDeEvento.HAPPY_HOUR: RegraDoEvento(
        slots=(
            Slot(frozenset({"cachaca", "licor"}), "destilado ou licor"),
            Slot(frozenset({"queijo"}), "queijo"),
            Slot(frozenset({"petisco"}), "petisco"),
        )
    ),
    TipoDeEvento.CESTA_DE_FIM_DE_ANO: RegraDoEvento(tipos_distintos=3),
    TipoDeEvento.KIT_BOAS_VINDAS: RegraDoEvento(
        slots=(
            Slot(frozenset({"cafe"}), "bebida quente"),
            Slot(frozenset({"doce"}), "doce"),
        )
    ),
}


class Motivo(StrEnum):
    """Por que uma composição reprovou.

    O motivo é campo, e não só prosa, porque `golden-014` exige que uma reprovação
    por slot **não** seja explicada como questão de preço. Com o motivo tipado, a
    diferença é verificável fora do texto.
    """

    COMPOSICAO_VAZIA = "composicao_vazia"
    RESTRICAO = "restricao"
    DISPONIBILIDADE = "disponibilidade"
    SLOT = "slot"
    ORCAMENTO = "orcamento"


@dataclass(frozen=True)
class Problema:
    """Um motivo de recusa, dito de um jeito em que o modelo consiga agir."""

    motivo: Motivo
    mensagem: str
    produto_id: str | None = None


@dataclass(frozen=True)
class Item:
    """Uma linha da composição, com a quantidade já derivada do rendimento."""

    produto_id: str
    nome: str
    tipo: TipoDeProduto
    rendimento: int
    quantidade: int
    preco_unitario: Decimal
    subtotal: Decimal


@dataclass(frozen=True)
class Veredito:
    """O que o código responde sobre a composição que o modelo propôs.

    `atende_pessoas` não é o número que o cliente pediu: é o do item que rende
    menos. Quatro pacotes de um café de rendimento 12 cobrem 48 pessoas, mas se o
    queijo ao lado só chega a 40, a composição atende 40 — e dizer 48 seria
    ancorado e errado ao mesmo tempo.
    """

    aprovada: bool
    tipo_de_evento: TipoDeEvento
    pessoas: int
    atende_pessoas: int
    itens: tuple[Item, ...]
    total: Decimal
    valor_por_pessoa: Decimal
    orcamento_por_pessoa: Decimal | None
    excedente_por_pessoa: Decimal | None
    problemas: tuple[Problema, ...]


def validar(
    *,
    tipo_de_evento: TipoDeEvento,
    pessoas: int,
    produtos: Sequence[Produto],
    orcamento_por_pessoa: Decimal | None = None,
    restricoes: Sequence[Alergeno] = (),
) -> Veredito:
    """Monta as quantidades, soma o total e devolve tudo o que reprova.

    **Devolve todos os problemas, não o primeiro.** A métrica da spec é "≤ 3 rodadas
    até uma composição válida"; um veredito que parasse no primeiro problema
    garantiria uma rodada por problema, e o cliente veria o agente descobrindo
    obstáculos um a um.

    Levanta `ValueError` para `pessoas < 1`: não é composição reprovada, é chamada
    inválida — e o valor por pessoa exigiria dividir por zero.
    """
    if pessoas < 1:
        raise ValueError(f"pessoas precisa ser pelo menos 1, e chegou {pessoas}")

    itens = tuple(_item(produto, pessoas) for produto in _sem_repeticao(produtos))
    total = sum((item.subtotal for item in itens), start=ZERO)
    valor_por_pessoa = (total / pessoas).quantize(CENTAVOS, rounding=ROUND_UP)
    excedente = _excedente(total, pessoas, orcamento_por_pessoa)

    problemas = (
        *_vazia(itens),
        *_restricoes_violadas(itens, produtos, restricoes),
        *_indisponiveis(produtos),
        *_slots_faltando(tipo_de_evento, produtos),
        *_estouro(excedente, orcamento_por_pessoa, total, pessoas),
    )

    return Veredito(
        aprovada=not problemas,
        tipo_de_evento=tipo_de_evento,
        pessoas=pessoas,
        atende_pessoas=min((i.quantidade * i.rendimento for i in itens), default=0),
        itens=itens,
        total=total,
        valor_por_pessoa=valor_por_pessoa,
        orcamento_por_pessoa=orcamento_por_pessoa,
        excedente_por_pessoa=excedente,
        problemas=problemas,
    )


def _sem_repeticao(produtos: Sequence[Produto]) -> tuple[Produto, ...]:
    """O mesmo id duas vezes é uma linha só, na ordem em que apareceu primeiro.

    Repetir não quer dizer "o dobro": a quantidade vem do `rendimento`, não da
    repetição. Se repetir multiplicasse, o modelo teria recuperado por acidente o
    controle da quantidade — que é justamente o que a RF-1.6 tira dele.
    """
    vistos: dict[str, Produto] = {}
    for produto in produtos:
        vistos.setdefault(produto.id, produto)
    return tuple(vistos.values())


def _item(produto: Produto, pessoas: int) -> Item:
    """Quantas unidades deste produto cobrem `pessoas`, e quanto isso custa.

    A divisão é inteira e arredonda para cima (`-(-a // b)`), sem passar por
    `float`: meio pacote de café não atende ninguém, e `math.ceil(40 / 12)` traria
    ponto flutuante para dentro de uma conta de quantidade que vira dinheiro.
    """
    quantidade = -(-pessoas // produto.rendimento)
    return Item(
        produto_id=produto.id,
        nome=produto.nome,
        tipo=produto.tipo,
        rendimento=produto.rendimento,
        quantidade=quantidade,
        preco_unitario=produto.preco,
        subtotal=produto.preco * quantidade,
    )


def _excedente(
    total: Decimal, pessoas: int, orcamento_por_pessoa: Decimal | None
) -> Decimal | None:
    """Quanto passou do teto, por pessoa — ou `None` se não há teto, ou se coube.

    A comparação é contra o **total exato** (`teto vezes pessoas`), e não contra o valor
    por pessoa já arredondado. Comparar o arredondado abriria a fresta de um centavo
    por cabeça: a R$30,004 por pessoa, 25 pessoas passam R$0,10 do teto enquanto o
    número exibido ainda diz R$30,00.
    """
    if orcamento_por_pessoa is None:
        return None
    teto = orcamento_por_pessoa * pessoas
    if total <= teto:
        return None
    return ((total - teto) / pessoas).quantize(CENTAVOS, rounding=ROUND_UP)


def _vazia(itens: Sequence[Item]) -> tuple[Problema, ...]:
    """Composição sem item nenhum custa R$0,00, e R$0,00 cabe em qualquer teto.

    Sem esta recusa, a composição vazia seria a resposta ótima para todo orçamento
    apertado — o pior conselho possível, apresentado como aprovado.
    """
    if itens:
        return ()
    return (
        Problema(
            motivo=Motivo.COMPOSICAO_VAZIA,
            mensagem="a composição está vazia; escolha os produtos antes de validar",
        ),
    )


def _restricoes_violadas(
    itens: Sequence[Item], produtos: Sequence[Produto], restricoes: Sequence[Alergeno]
) -> tuple[Problema, ...]:
    """Todo item cujo `contem` cruza com uma restrição declarada, nomeando os dois.

    Nomear produto e alérgeno é o que torna o problema acionável: sem isso o modelo
    sabe que reprovou e não sabe o que trocar, e a conversa vira tentativa e erro na
    frente do cliente.
    """
    declaradas = set(restricoes)
    if not declaradas:
        return ()

    contem_de = {produto.id: set(produto.contem) for produto in produtos}
    return tuple(
        Problema(
            motivo=Motivo.RESTRICAO,
            mensagem=(
                f"{item.nome} declara {', '.join(sorted(violados))} e a composição tem "
                f"restrição a {', '.join(sorted(declaradas))}; troque este item"
            ),
            produto_id=item.produto_id,
        )
        for item in itens
        if (violados := contem_de.get(item.produto_id, set()) & declaradas)
    )


def _indisponiveis(produtos: Sequence[Produto]) -> tuple[Problema, ...]:
    """Aprovar o que a loja não tem seria um total exato e invendável.

    O seed mantém cinco itens fora do ar de propósito, e no B2B eles doem mais: um
    item indisponível no meio de uma composição obriga a recompor, não só a pedir
    desculpa (`data/catalogo/README.md`, `golden-006`).
    """
    return tuple(
        Problema(
            motivo=Motivo.DISPONIBILIDADE,
            mensagem=f"{produto.nome} não está disponível; escolha outro item no lugar",
            produto_id=produto.id,
        )
        for produto in _sem_repeticao(produtos)
        if not produto.disponivel
    )


def _slots_faltando(
    tipo_de_evento: TipoDeEvento, produtos: Sequence[Produto]
) -> tuple[Problema, ...]:
    """O que o evento exige e a composição não tem — nomeado como o cliente fala.

    A mensagem não menciona dinheiro, e isso é requisito: `golden-014` reprova o
    agente que explica uma falta de slot como se fosse questão de preço.
    """
    regra = REGRAS[tipo_de_evento]
    tipos_presentes = {produto.tipo for produto in produtos}

    faltando = tuple(
        Problema(
            motivo=Motivo.SLOT,
            mensagem=(
                f"falta {slot.como_dizer}: {tipo_de_evento.value.replace('_', ' ')} exige "
                f"pelo menos um item de {' ou '.join(sorted(slot.tipos))}"
            ),
        )
        for slot in regra.slots
        if not (slot.tipos & tipos_presentes)
    )

    if regra.tipos_distintos and len(tipos_presentes) < regra.tipos_distintos:
        faltando = (
            *faltando,
            Problema(
                motivo=Motivo.SLOT,
                mensagem=(
                    f"{tipo_de_evento.value.replace('_', ' ')} exige pelo menos "
                    f"{regra.tipos_distintos} tipos distintos de produto, e esta composição "
                    f"tem {len(tipos_presentes)}"
                ),
            ),
        )
    return faltando


def _estouro(
    excedente: Decimal | None,
    orcamento_por_pessoa: Decimal | None,
    total: Decimal,
    pessoas: int,
) -> tuple[Problema, ...]:
    """De quanto foi o estouro, em valor por pessoa e em total.

    Os dois números vão na mensagem porque o modelo precisa de um deles para
    explicar e do outro para escolher o que cortar — e porque um teto aprovado por
    um financeiro não é sugestão: a saída legítima é recompor, nunca pedir para
    esticar o orçamento nem oferecer abatimento (`golden-007`, ADR-013, RF-2.6).
    """
    if excedente is None or orcamento_por_pessoa is None:
        return ()
    return (
        Problema(
            motivo=Motivo.ORCAMENTO,
            mensagem=(
                f"a composição estoura o orçamento em {excedente} por pessoa: sai a "
                f"{(total / pessoas).quantize(CENTAVOS, rounding=ROUND_UP)} por pessoa contra "
                f"o teto de {orcamento_por_pessoa}, e o total é {total} para um teto de "
                f"{orcamento_por_pessoa * pessoas}; troque itens por opções mais baratas"
            ),
        ),
    )
