"""R1 — o seed atravessa a ingestão sem que nenhum fato mude de valor.

`test_catalog_seed_is_usable.py` já garante que o seed é íntegro no disco. Este
arquivo cobre o trecho seguinte, que é onde um fato pode mudar sem ninguém ver: a
travessia do JSON até a linha do Postgres e até o documento que vira vetor.

Três coisas são vigiadas aqui, e cada uma corresponde a uma forma de o R1
acontecer sem alucinação nenhuma do modelo:

1. **Preço que vira float.** O modelo pode estar perfeitamente ancorado e ainda
   assim dizer 89,90000000000001 se a conversão perdeu a exatidão no caminho.
2. **Id de ponto instável.** Se `make seed` sortear ids, rodar duas vezes duplica
   o catálogo — e a busca passa a devolver o mesmo produto duas vezes como se
   fossem opções diferentes.
3. **Preço dentro do documento embedado ou do payload do Qdrant.** Preço com duas
   moradas é preço que vai discordar de si mesmo, e o índice é a morada que
   ninguém lembra de atualizar.

Sem rede, sem contêiner, sem chave de API: só lê o seed que já está no repositório.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from vendinha.catalogo import (
    COLUNAS,
    PostgresCatalogo,
    Produto,
    QdrantIndice,
    carregar_seed,
    colunas_de,
    payload_de,
    ponto_de,
    texto_para_embedding,
)

pytestmark = pytest.mark.requires_backend

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOGO = REPO_ROOT / "data" / "catalogo"


@pytest.fixture(scope="module")
def produtos() -> tuple[Produto, ...]:
    return carregar_seed(CATALOGO)


@pytest.mark.risco("R1")
def test_the_whole_seed_loads_into_the_domain_model(produtos: tuple[Produto, ...]) -> None:
    """R1 — todo produto do seed vira `Produto`, ou a ingestão para.

    `extra="forbid"` no modelo é o que torna este teste útil: um campo novo no seed
    reprova aqui em vez de sumir silenciosamente antes de chegar ao cliente.
    """
    assert len(produtos) >= 50, f"{len(produtos)} produtos carregados, o seed tem >= 50"


@pytest.mark.risco("R1")
def test_every_price_is_a_decimal_with_the_exact_cents_of_the_seed() -> None:
    """R1 — dinheiro é `Decimal`, nunca float (`docs/testes.md` §4).

    O valor esperado vem do seed, não de um recálculo: `docs/testes.md` §4 recusa
    teste que refaz no teste a mesma conta que o código faz.
    """
    do_disco: dict[str, str] = {}
    for arquivo in sorted(CATALOGO.glob("*.json")):
        with arquivo.open(encoding="utf-8") as handle:
            for linha in json.load(handle):
                do_disco[linha["id"]] = linha["preco"]

    for produto in carregar_seed(CATALOGO):
        assert isinstance(produto.preco, Decimal)
        assert str(produto.preco) == do_disco[produto.id], (
            f"{produto.id}: preço {produto.preco} não bate com o seed ({do_disco[produto.id]})"
        )


@pytest.mark.risco("R1")
def test_a_price_written_as_a_json_number_is_refused() -> None:
    """R1 — número JSON vira float no parse, e float perde centavos.

    A recusa é na fronteira porque o dano só apareceria bem longe daqui: no total
    de um pedido, com o modelo perfeitamente ancorado e o número errado.
    """
    with pytest.raises(ValidationError, match="float"):
        Produto.model_validate(
            {
                "id": "queijo-de-teste",
                "nome": "Queijo de teste",
                "tipo": "queijo",
                "regiao": "Serra da Canastra, MG",
                "produtor": "Sítio Fictício",
                "descricao": "Descrição comprida o bastante para o schema do seed aceitar.",
                "intensidade": "media",
                "harmonizacao": ["vinho tinto"],
                "ocasiao": ["presente"],
                "peso": "500 g",
                "preco": 89.90,
                "disponivel": True,
                "prazo_estimado": "3 a 5 dias úteis",
                "maturacao": "45 dias",
            }
        )


@pytest.mark.risco("R1")
def test_the_point_id_is_derived_from_the_product_id_and_never_changes() -> None:
    """R1 — id de ponto sorteado faria `make seed` duplicar o catálogo a cada run.

    Um catálogo duplicado devolve o mesmo produto duas vezes na busca, e o agente o
    apresenta como se fossem duas opções. O valor esperado é fixo no teste de
    propósito: ele trava o namespace, então mudá-lo reprova aqui em vez de
    silenciosamente reindexar tudo sob ids novos.
    """
    assert ponto_de("queijo-canastra-meia-cura") == ponto_de("queijo-canastra-meia-cura")
    assert ponto_de("queijo-canastra-meia-cura") != ponto_de("queijo-canastra-curado")
    assert ponto_de("queijo-canastra-meia-cura") == "fb1f8864-48ca-55af-83a8-f136b1c948f5"


@pytest.mark.risco("R1")
def test_no_money_reaches_the_vector_index(produtos: tuple[Produto, ...]) -> None:
    """R1 — o Qdrant ranqueia; quem afirma preço é o Postgres.

    Preço no payload ou no documento embedado é uma segunda cópia do preço, e a
    segunda cópia é a que ninguém lembra de atualizar.
    """
    for produto in produtos:
        payload = payload_de(produto)
        assert set(payload) == {"id", "tipo", "disponivel"}, (
            f"{produto.id}: payload do Qdrant ganhou campo além dos três de filtro: {payload}"
        )
        documento = texto_para_embedding(produto)
        assert str(produto.preco) not in documento, (
            f"{produto.id}: o preço entrou no documento embedado"
        )
        assert produto.prazo_estimado not in documento, (
            f"{produto.id}: o prazo entrou no documento embedado"
        )


@pytest.mark.risco("R1")
def test_the_embedded_document_carries_what_answers_an_implicit_need(
    produtos: tuple[Produto, ...],
) -> None:
    """R1 — sem `harmonizacao` e `ocasiao` no vetor, a busca vira filtro de e-commerce.

    É o que `data/catalogo/README.md` chama de "o produto, não enfeite": filtro não
    resolve "um presente pra minha sogra que ama vinho tinto" (RF-1.2, RF-1.4).
    """
    for produto in produtos:
        documento = texto_para_embedding(produto)
        for termo in (*produto.harmonizacao, *produto.ocasiao, produto.nome, produto.descricao):
            assert termo in documento, f"{produto.id}: '{termo}' ficou fora do documento"


@pytest.mark.risco("R1")
def test_the_document_crosses_occasion_and_pairing_the_way_a_customer_asks(
    produtos: tuple[Produto, ...],
) -> None:
    """R1 — é o que separa 0/4 de 3/4 na consulta que o produto existe para responder.

    Medido: com `harmonizacao` e `ocasiao` como duas listas separadas, *nenhum*
    dos nove queijos que harmonizam com tinto aparecia no top-4 de "presente para
    quem ama vinho tinto" — o vetor via "presente" e trazia licor. Com a cruzada
    escrita como frase, três dos quatro primeiros são queijo. Trocar o modelo de
    embedding não mudou nada; a forma da frase mudou.

    O teste trava a forma, não o número: a medição está no docstring de
    `texto_para_embedding` e não se reproduz sem rede. Sem a frase cruzada no
    documento, a busca volta a errar exatamente onde o RF-1.2 existe.
    """
    for produto in produtos:
        documento = texto_para_embedding(produto)
        esperada = (
            f"{produto.ocasiao[0].capitalize()} para quem gosta de {produto.harmonizacao[0]}."
        )
        assert esperada in documento, f"{produto.id}: falta a frase cruzada '{esperada}'"

    # Toda combinação, não só a primeira: é o cruzamento que faz "tábua de frios"
    # e "vinho tinto" encontrarem o mesmo queijo por caminhos diferentes.
    um = next(p for p in produtos if len(p.ocasiao) > 1 and len(p.harmonizacao) > 1)
    documento = texto_para_embedding(um)
    for ocasiao in um.ocasiao:
        for harmonizacao in um.harmonizacao:
            assert f"{ocasiao.capitalize()} para quem gosta de {harmonizacao}." in documento


@pytest.mark.risco("R1")
def test_the_postgres_row_matches_the_declared_column_order(produtos: tuple[Produto, ...]) -> None:
    """R1 — `COLUNAS` e `colunas_de` desalinhados gravariam preço na coluna errada.

    São duas listas paralelas escritas à mão, e o banco aceitaria a troca sem
    reclamar sempre que os dois campos tiverem o mesmo tipo — nome e região, por
    exemplo. O erro só apareceria como um produto respondendo o atributo do vizinho.
    """
    produto = next(p for p in produtos if p.id == "queijo-canastra-meia-cura")
    linha = dict(zip(COLUNAS, colunas_de(produto), strict=True))

    assert linha["id"] == produto.id
    assert linha["nome"] == produto.nome
    assert linha["preco"] == produto.preco
    assert linha["disponivel"] is produto.disponivel
    assert linha["harmonizacao"] == list(produto.harmonizacao)
    assert linha["notas_sensoriais"] == list(produto.notas_sensoriais)


@pytest.mark.risco("R1")
async def test_an_empty_catalogue_is_refused_instead_of_written() -> None:
    """R1 — gravar catálogo vazio apagaria o catálogo inteiro sem aviso.

    `substituir_tudo` apaga o que saiu do seed. Com a lista vazia, "o que saiu do
    seed" é tudo — um seed que não carregou viraria uma loja sem produtos, e o
    agente diria "não encontrei nada" com toda a sinceridade.
    """
    with pytest.raises(ValueError, match="vazio"):
        await PostgresCatalogo("postgresql://nao-conecta/x").substituir_tudo([])


@pytest.mark.risco("R1")
async def test_indexing_refuses_a_vector_count_that_does_not_match_the_products() -> None:
    """R1 — vetores fora de ordem indexariam cada produto com o texto de outro.

    O `zip` pareia por posição. Um vetor a menos deslocaria todo o resto, e a busca
    passaria a devolver o produto errado para cada consulta — sem erro nenhum.
    """
    produtos = carregar_seed(CATALOGO)
    with pytest.raises(ValueError, match="vetores"):
        await QdrantIndice("http://127.0.0.1:1", "catalogo").reindexar(produtos, [[0.1, 0.2]])
