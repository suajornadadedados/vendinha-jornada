"""R2 — o subagent de recomendação não possui tool de escrita. Não é negada: não está lá.

Este é o arquivo que `docs/riscos.md` e `docs/testes.md` §2 nomeiam para a linha R2,
e é o arquivo que **não podia existir antes desta spec**. Enquanto `criar_pedido` era
promessa, afirmar aqui que a recomendação não a possui seria verdade por acidente —
`docs/testes.md` §3.3: *teste que nasceu verde não provou nada*. Agora existe uma tool
de escrita de verdade no repositório, e a afirmação passa a ter conteúdo.

**A diferença para `tests/unit/test_subagent_registry.py`.** Lá se prova que o
*mecanismo* recusa, com uma tool forjada. Aqui se prova que a *configuração real* do
produto está do lado certo da fronteira, sobre as tools que o `app.py` monta. As duas
metades são necessárias: um mecanismo correto que ninguém usou não protege nada, e uma
configuração correta por acaso não sobrevive à próxima tool.

**R2 não é cobertura, é o requisito** (`docs/testes.md` §2). Nenhuma spec que o toque
fecha sem este arquivo verde, e não existe versão mínima dele.
"""

from pathlib import Path
from typing import Any

import pytest

from vendinha.catalogo import BuscaEmMemoria, CatalogoEmMemoria, Produto, carregar_seed
from vendinha.pagamento import MockPaymentAdapter
from vendinha.pedidos import PedidosEmMemoria
from vendinha.subagents import (
    CHECKOUT,
    PROMPT_RECOMENDACAO,
    RECOMENDACAO,
    SOMENTE_LEITURA,
    Ferramenta,
    FronteiraDePermissaoViolada,
    Subagent,
    checkout,
    recomendacao,
    registrar,
)

pytestmark = pytest.mark.requires_backend

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOGO = REPO_ROOT / "data" / "catalogo"

SEM_TIMEOUT = 30.0

# Tools que não existem em registro nenhum deste repositório. `aplicar_desconto` é a
# principal: o `adversarial-001` e o `adversarial-005` a listam em `tools.proibidas`,
# e a defesa contra os dois não é o modelo recusar — é não haver o que chamar
# (ADR-002, RF-2.6, ADR-013).
INEXISTENTES = frozenset({"aplicar_desconto", "aplicar_cupom", "ajustar_preco"})


@pytest.fixture(scope="module")
def seed() -> tuple[Produto, ...]:
    return carregar_seed(CATALOGO)


@pytest.fixture
def le(seed: tuple[Produto, ...]) -> Subagent:
    return recomendacao(
        BuscaEmMemoria(seed), CatalogoEmMemoria(seed), PedidosEmMemoria(), SEM_TIMEOUT
    )


@pytest.fixture
def escreve(seed: tuple[Produto, ...]) -> Subagent:
    return checkout(
        BuscaEmMemoria(seed),
        CatalogoEmMemoria(seed),
        PedidosEmMemoria(),
        MockPaymentAdapter("http://localhost:8000"),
        SEM_TIMEOUT,
    )


@pytest.mark.risco("R2")
def test_the_recommendation_agent_owns_no_write_tool_that_exists_in_this_repository(
    le: Subagent, escreve: Subagent
) -> None:
    """R2, RF-1.5, ADR-002 — a fronteira, afirmada sobre as tools reais do produto.

    A lista de escritoras é lida do **checkout**, e não escrita à mão aqui: uma
    tool de escrita nova entra neste teste sozinha no dia em que for registrada.
    Uma constante paralela envelheceria em silêncio, e o teste continuaria verde
    afirmando sobre um conjunto que já não é o do produto.
    """
    assert escreve.escritoras, "nenhuma tool de escrita registrada — o teste seria vacuoso"

    do_recomendacao = {tool.name for tool in le.tools}

    assert le.escritoras == ()
    assert do_recomendacao.isdisjoint(escreve.escritoras)


@pytest.mark.risco("R2")
def test_registering_any_real_write_tool_on_the_recommendation_agent_is_refused(
    escreve: Subagent,
) -> None:
    """R2, ADR-002 — a recusa é na construção, para cada tool de escrita que existe.

    Não há janela entre "foi montado errado" e "alguém percebeu": o subagent com
    poder de escrita não chega a existir em memória.
    """
    escritoras = [f for f in escreve.ferramentas if f.escreve]
    assert escritoras

    for ferramenta in escritoras:
        with pytest.raises(FronteiraDePermissaoViolada, match=ferramenta.tool.name):
            registrar(RECOMENDACAO, PROMPT_RECOMENDACAO, [ferramenta])


@pytest.mark.risco("R4")
def test_a_discount_action_does_not_exist_in_any_registry(le: Subagent, escreve: Subagent) -> None:
    """R4, RF-2.6, ADR-013 — desconto não é negado, é ausente.

    Comprador corporativo pede desconto por volume o tempo todo, e o `adversarial-005`
    é exatamente isso: argumento plausível, ameaça real. A defesa não é o modelo
    aguentar firme — é não existir ação com que ceder.
    """
    registradas = {tool.name for tool in (*le.tools, *escreve.tools)}

    assert registradas.isdisjoint(INEXISTENTES)
    assert not any("desconto" in nome or "cupom" in nome for nome in registradas)


@pytest.mark.risco("R4")
def test_no_tool_a_case_forbids_ever_lands_on_the_recommendation_agent(
    le: Subagent, tools_proibidas: set[str]
) -> None:
    """R4 — o corpus adversarial declara o que não pode ser alcançado, e não é.

    A lista vem de `evals/adversarial/*.yaml`, então um ataque novo escrito lá
    aparece aqui sem ninguém editar este arquivo. As proibidas incluem
    `criar_pedido` e `gerar_link_pagamento`, que existem — no checkout. O que este
    teste afirma é que elas não estão **aqui**, que é a fronteira que o ADR-002
    descreve.
    """
    assert tools_proibidas

    assert {tool.name for tool in le.tools}.isdisjoint(tools_proibidas)


@pytest.mark.risco("R2")
def test_the_read_only_list_is_the_adr_and_the_checkout_is_not_in_it(
    subagents_read_only: set[str],
) -> None:
    """R2 — quem é somente-leitura está declarado, e a regra não é "ninguém escreve".

    Sem esta metade, um registro que recusasse escrita em qualquer subagent passaria
    nos testes acima e quebraria a S-04 inteira — sem nada a ver com o ADR-002.
    """
    assert set(SOMENTE_LEITURA) == subagents_read_only
    assert CHECKOUT not in SOMENTE_LEITURA


@pytest.mark.risco("R2")
def test_a_write_tool_marked_read_only_is_the_declared_blind_spot(
    escreve: Subagent,
) -> None:
    """R2 — `escreve` é declarado por quem registra, e o registro confia nisso.

    Está assim de propósito: inferir por nome ("começa com `criar_`") seria segurança
    comportamental dentro do nosso próprio código. O limite fica documentado por um
    teste em vez de descoberto como surpresa — e a linha que o guarda é a revisão,
    via CODEOWNERS.
    """
    criar_pedido = next(f.tool for f in escreve.ferramentas if f.tool.name == "criar_pedido")

    mentiroso = registrar(
        RECOMENDACAO, PROMPT_RECOMENDACAO, [Ferramenta(tool=criar_pedido, escreve=False)]
    )

    assert mentiroso.escritoras == ()


@pytest.mark.risco("R2")
def test_the_checkout_can_read_the_catalogue_because_the_boundary_is_about_acting(
    le: Subagent, escreve: Subagent
) -> None:
    """R2, D-1 — "recomendação não escreve" nunca significou "checkout não lê".

    `golden-003` e `golden-015` listam as tools de leitura em `tools.permitidas` ao
    lado de `criar_pedido`. Sem elas, um turno de checkout que precisasse reconferir
    um preço teria que voltar de lane, e o cliente veria a conversa recuar.
    """
    do_checkout = {tool.name for tool in escreve.tools}

    assert {tool.name for tool in le.tools} <= do_checkout
    assert {
        "criar_pedido",
        "gerar_link_pagamento",
        "validar_dados_cliente",
        "consultar_pedido",
    } <= do_checkout


@pytest.mark.risco("R2")
def test_every_adversarial_case_names_tools_that_this_repository_recognises(
    casos_adversariais: list[dict[str, Any]], le: Subagent, escreve: Subagent
) -> None:
    """R2 — a régua e o produto falam do mesmo conjunto de nomes.

    Um caso que proíbe `criar_pedidos` (com S) passaria para sempre, sobre uma tool
    que não existe, e ninguém notaria. Aqui o corpus é conferido contra o registro:
    toda tool citada ou existe hoje, ou é de uma spec que ainda não chegou — e essas
    estão nomeadas, uma a uma.
    """
    # `emitir_nf` e `registrar_aprovacao` são da S-05; `aplicar_desconto` e as
    # irmãs não existem por decisão (RF-2.6) e são cobertas pelo teste acima.
    ainda_nao_existem = {"emitir_nf", "registrar_aprovacao"} | INEXISTENTES
    registradas = {tool.name for tool in (*le.tools, *escreve.tools)}

    # A lista de pendências tem que se esvaziar sozinha: no dia em que
    # `gerar_link_pagamento` for registrada, esta linha reprova até alguém tirá-la
    # daqui. Sem ela, um nome ficaria na lista para sempre e o teste passaria a
    # tolerar exatamente o que existe para pegar.
    assert registradas.isdisjoint(ainda_nao_existem), (
        "uma tool desta lista já existe no registro: tire o nome de `ainda_nao_existem`"
    )

    citadas = {
        nome
        for caso in casos_adversariais
        for chave in ("permitidas", "proibidas")
        for nome in (caso.get("tools", {}).get(chave) or [])
    }

    assert citadas <= registradas | ainda_nao_existem
