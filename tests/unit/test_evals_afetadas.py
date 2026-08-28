"""R7 — o mapa que decide o escopo do portão de evals no PR (ADR-014).

O mapa é o artefato novo que o ADR-014 aceitou como custo, e ele nomeou o risco na
mesma frase: *"um mapa errado num arquivo mapeado deixa de rodar algo que deveria, e
só o pós-merge pega"*. Este arquivo é o que torna esse erro visível antes do merge.

Três propriedades, e a terceira é a que sustenta as outras duas:

1. o eixo é **o código tocado**, nunca a spec do PR;
2. um diff que não pode ter mudado nada não paga a suíte;
3. **arquivo não mapeado roda tudo** — o mapa só erra para o lado caro.

Sem rede, sem agente e sem chave: o mapa é uma função pura sobre nomes de arquivo.
"""

import pytest

from vendinha.evals.afetadas import MAPA, TODAS, sub_suites_afetadas
from vendinha.evals.caso import carregar_casos
from vendinha.evals.runner import EVALS


@pytest.mark.risco("R7")
def test_touching_the_recommendation_prompt_runs_every_suite_that_uses_that_lane() -> None:
    """R7 — é o cenário BDD da spec, e a razão de o eixo ser o código e não a spec.

    `PROMPT_RECOMENDACAO` vive em `subagents.py`, e a lane de recomendação está no
    caminho da S-02, da S-03, da S-11 e da S-04. Um PR que a mude pode ser de
    qualquer spec — inclusive de nenhuma —, e mapear por "de qual spec é este PR"
    deixaria passar exatamente a regressão silenciosa que a R7 nomeia.
    """
    afetadas = sub_suites_afetadas(["backend/vendinha/subagents.py"])

    assert {"S-02", "S-03", "S-11", "S-04"} <= afetadas


@pytest.mark.risco("R7")
def test_a_diff_that_could_not_have_changed_anything_pays_for_nothing() -> None:
    """R7 — rodar um eval que não podia ter mudado não é rigor, é ruído pago.

    E ruído pago é o que ensina a ignorar o portão. O conjunto vazio é o que faz o
    script sair 0 dizendo "nada a avaliar neste diff" — **sem pular o job**, que
    travaria a `main` para sempre por ser required.
    """
    assert sub_suites_afetadas(["docs/specs/S-06-qualidade-como-gate.md"]) == frozenset()
    assert sub_suites_afetadas([".claude/agents/verificador-de-spec.md"]) == frozenset()
    assert sub_suites_afetadas(["docs/adr/ADR-014.md", "frontend/src/App.tsx"]) == frozenset()
    # `tests/` verifica o agente, não o constrói. `tests/security/` parametriza a
    # partir de `evals/adversarial/*.yaml`, mas quem o roda é o job `test` — a
    # camada 0, que roda em todo PR de graça.
    assert sub_suites_afetadas(["tests/unit/test_budget_guard.py"]) == frozenset()


@pytest.mark.risco("R7")
def test_a_file_nobody_classified_runs_everything() -> None:
    """R7 — o mapa só pode errar para o lado caro.

    É a regra que impede o mapa de envelhecer em silêncio. Um módulo novo no
    backend não abre buraco no portão: encarece o PR até alguém classificá-lo, que
    é a pressão certa. A alternativa — não-mapeado significa "nada a rodar" — faria
    um arquivo esquecido virar uma lacuna que só o pós-merge encontraria.
    """
    assert sub_suites_afetadas(["backend/vendinha/modulo_que_ninguem_classificou.py"]) == TODAS


@pytest.mark.risco("R7")
def test_one_unmapped_file_drags_the_whole_diff_to_everything() -> None:
    """R7 — o não-mapeado vence o resto do diff, e não o contrário.

    Um PR que mexe em `docs/` e num arquivo novo tem de rodar tudo. Se a ordem de
    avaliação deixasse o `docs/` decidir, bastaria acompanhar o arquivo novo de uma
    mudança de documentação para o portão não olhar para ele.
    """
    afetadas = sub_suites_afetadas(
        ["docs/PRD.md", "backend/vendinha/coisa_nova.py", "backend/vendinha/fiscal.py"]
    )

    assert afetadas == TODAS


@pytest.mark.risco("R7")
def test_the_narrow_entries_stay_narrow() -> None:
    """R7 — se tudo rodasse tudo, a camada 1 seria a camada 2 com outro nome.

    O valor do mapa está nas entradas estreitas: elas são o que faz um PR de HITL
    custar quatro casos em vez de vinte e três. Um mapa que alargasse por descuido
    ficaria correto e inútil ao mesmo tempo — e ninguém perceberia, porque um
    portão caro demais falha do lado que não reprova nada.
    """
    assert sub_suites_afetadas(["backend/vendinha/fiscal.py"]) == frozenset({"S-05"})
    assert sub_suites_afetadas(["backend/vendinha/supervisor.py"]) == frozenset({"S-04"})
    assert sub_suites_afetadas(["backend/vendinha/redaction.py"]) == frozenset({"S-02"})
    assert sub_suites_afetadas(["backend/vendinha/composicao.py"]) == frozenset({"S-11", "S-04"})


@pytest.mark.risco("R7")
def test_the_ruler_measuring_itself_runs_everything() -> None:
    """R7, ADR-006 — mexer num caso, no juiz ou no portão reavalia a suíte inteira.

    Vale para as duas moradas da régua: o corpus em `evals/` e o runner em
    `backend/vendinha/evals/`. Mapear só a primeira deixaria uma mudança no juiz —
    que decide o veredito de TODOS os casos — passar sem reexecutar nada.
    """
    assert sub_suites_afetadas(["evals/golden/golden-002-preco-vem-do-banco.yaml"]) == TODAS
    assert sub_suites_afetadas(["evals/schema/caso.schema.json"]) == TODAS
    assert sub_suites_afetadas(["backend/vendinha/evals/judge.py"]) == TODAS


@pytest.mark.risco("R7")
def test_the_longest_prefix_wins_so_a_narrow_entry_is_not_shadowed() -> None:
    """R7 — `tools/catalogo.py` e `tools/checkout.py` não podem se confundir.

    O casamento é por prefixo, e prefixo curto que casasse primeiro daria a um
    arquivo o conjunto de outro. Aqui as duas entradas convivem e cada uma responde
    o seu — o catálogo roda tudo, o checkout roda dois.
    """
    assert sub_suites_afetadas(["backend/vendinha/tools/catalogo.py"]) == TODAS
    assert sub_suites_afetadas(["backend/vendinha/tools/checkout.py"]) == frozenset(
        {"S-04", "S-05"}
    )


@pytest.mark.risco("R7")
def test_windows_separators_and_leading_dots_do_not_defeat_the_map() -> None:
    """R7 — o portão não pode depender de em que máquina o caminho foi escrito.

    `git diff --name-only` devolve `/` em todo lugar, mas o script também é rodado
    à mão para conferir o mapa, e ali a barra invertida aparece. Um caminho que não
    casasse cairia em "não mapeado" e rodaria tudo — caro, não inseguro, mas o
    suficiente para alguém concluir que o mapa não funciona.
    """
    assert sub_suites_afetadas([r"backend\vendinha\fiscal.py"]) == frozenset({"S-05"})
    assert sub_suites_afetadas(["./docs/riscos.md"]) == frozenset()
    assert sub_suites_afetadas([""]) == frozenset()


@pytest.mark.risco("R7")
def test_every_suite_the_corpus_declares_exists_in_the_map() -> None:
    """R7 — "roda tudo" tem de significar o corpus inteiro, e não o de ontem.

    `TODAS` é escrita à mão de propósito: derivá-la do corpus faria uma `spec`
    digitada errado num caso novo inventar uma sub-suíte que ninguém decidiu, e ela
    rodaria vazia e verde. O preço dessa escolha é este teste, que é quem avisa
    quando uma spec nova entra no corpus e o mapa não soube.
    """
    do_corpus = {caso.spec for caso in carregar_casos(EVALS)}

    assert do_corpus == TODAS, (
        "o corpus e o mapa discordam sobre quais sub-suítes existem — "
        "um caso novo entrou sem que 'roda tudo' passasse a incluí-lo"
    )
    assert all(alvo <= TODAS for alvo in MAPA.values())
