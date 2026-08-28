"""R5, R7 — o visor de evals exporta pelo cliente do projeto, e nunca derruba a régua.

Duas garantias, e as duas são exigidas nominalmente pelo ADR-014.

**A primeira é de vazamento.** *"O runner instrumenta pelo cliente Langfuse do
projeto (`observability.client()`), que é o que carrega `mask_otel_spans`; um
cliente default exportaria as conversas de eval, com CNPJ e e-mail sintéticos, sem
redação nenhuma. Um teste afirma isso."* Este é o teste.

Está na camada `security` e não em `unit` porque a pergunta que ele responde é a
dessa camada: *existe caminho de código até a ação proibida?* A ação proibida aqui
é exportar uma conversa por um cliente sem o gancho de redação — e desde o ADR-010
o Langfuse é Cloud, então esse caminho sai da infraestrutura.

**A segunda é de disponibilidade.** *"Langfuse indisponível não reprova a suíte
(ADR-010): a instrumentação loga e segue."* Uma execução que já custou dinheiro não
pode virar vermelha porque um SaaS não respondeu — e um portão que reprova por
motivo alheio ao código é a definição de vermelho em que ninguém acredita.
"""

import logging
from typing import Any

import pytest

from vendinha import observability
from vendinha.evals import visor
from vendinha.evals.caso import carregar_casos
from vendinha.evals.groundedness import Transcricao, Veredito
from vendinha.evals.judge import VeredictoDeCriterio, VeredictoDoJuiz
from vendinha.evals.runner import EVALS, Resultado


def _resultado(
    aprovado: bool, trace_id: str | None = "0af7651916cd43dd8448eb211c80319c"
) -> Resultado:
    caso = next(iter(carregar_casos(EVALS, spec="S-03")))
    return Resultado(
        caso=caso,
        transcricao=Transcricao(respostas=(), chamadas=()),
        portao=Veredito(achados=()),
        juiz=VeredictoDoJuiz(
            vereditos=[
                VeredictoDeCriterio(
                    criterio="um critério",
                    tipo="deve",
                    veredito="atende" if aprovado else "nao_atende",
                    evidencia="a evidência",
                )
            ]
        ),
        trace_id=trace_id,
    )


def _chamadas_de(modulo: Any) -> set[str]:
    """Os nomes que o módulo de fato CHAMA, lidos da árvore sintática.

    `ast`, e não `"Langfuse(" in fonte`: a primeira versão deste teste procurava a
    string no texto e reprovava por causa da própria docstring, que explica por que
    não se deve construir um `Langfuse()` aqui. Um teste que não distingue código
    de comentário é um teste que proíbe explicar a regra.
    """
    import ast
    import inspect

    achadas: set[str] = set()
    for no in ast.walk(ast.parse(inspect.getsource(modulo))):
        if not isinstance(no, ast.Call):
            continue
        alvo = no.func
        if isinstance(alvo, ast.Name):
            achadas.add(alvo.id)
        elif isinstance(alvo, ast.Attribute) and isinstance(alvo.value, ast.Name):
            achadas.add(f"{alvo.value.id}.{alvo.attr}")
            achadas.add(alvo.attr)
    return achadas


class _ClienteEspiao:
    """Um Langfuse falso que registra o que recebeu — a fronteira do fornecedor."""

    def __init__(self) -> None:
        self.scores: list[dict[str, Any]] = []
        self.itens: list[Any] = []
        self.datasets: list[str] = []
        self.esvaziou = False

    def create_dataset(self, **kwargs: Any) -> None:
        self.datasets.append(kwargs["name"])

    def create_dataset_item(self, **kwargs: Any) -> None:
        self.itens.append(kwargs)

    def create_score(self, **kwargs: Any) -> None:
        self.scores.append(kwargs)

    def flush(self) -> None:
        self.esvaziou = True

    @property
    def api(self) -> Any:
        espiao = self

        class _Runs:
            # A assinatura espelha a real de `DatasetRunItemsClient.create`, de
            # propósito. A primeira versão aceitava `**kwargs` e engolia qualquer
            # coisa — e foi assim que a chamada errada (`request=...`) passou pelos
            # testes e só apareceu ao ler o Langfuse de volta, com zero runs do
            # outro lado. Um dublê mais permissivo que o original não testa a
            # fronteira, esconde.
            def create(
                self,
                *,
                run_name: str,
                dataset_item_id: str,
                trace_id: str | None = None,
                run_description: str | None = None,
                metadata: Any = None,
            ) -> None:
                espiao.itens.append(
                    {
                        "run_name": run_name,
                        "dataset_item_id": dataset_item_id,
                        "trace_id": trace_id,
                        "run_description": run_description,
                        "metadata": metadata,
                    }
                )

        class _Api:
            dataset_run_items = _Runs()

        return _Api()


@pytest.mark.risco("R5")
def test_the_visor_exports_through_the_project_client_and_never_a_default_one() -> None:
    """R5, ADR-014 — o cliente do projeto é o que carrega `mask_otel_spans`.

    Afirmado sobre o **código-fonte** do módulo, e é deliberado. A alternativa —
    monkeypatch em `observability.client` e conferir que ele foi chamado — provaria
    que aquele caminho usa o cliente certo, e deixaria passar um `Langfuse(...)`
    construído noutra função do mesmo arquivo. O que precisa ser verdade é mais
    forte: **não existe** construção de cliente aqui dentro.

    Um `Langfuse()` default exportaria as conversas de eval — que carregam o CNPJ e
    o e-mail de `EMPRESA_DO_CENARIO`, e tudo que o cliente sintético disser — sem
    redação nenhuma, para fora da infra (ADR-010).
    """
    chamadas = _chamadas_de(visor)

    assert "observability.client" in chamadas, (
        "o visor não passa por `observability.client()`, que é o único construtor "
        "que instala `mask_otel_spans`"
    )
    for proibida in ("Langfuse", "langfuse.Langfuse", "get_client", "langfuse.get_client"):
        assert proibida not in chamadas, (
            f"o visor chama `{proibida}`: esse cliente sai sem o gancho de "
            f"mascaramento, e toda conversa de eval seria exportada em claro"
        )


@pytest.mark.risco("R7")
def test_the_visor_tags_every_eval_trace_as_the_evals_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R7, ADR-014 — trace de eval não polui a métrica de produção.

    Sem isso, 23 conversas sintéticas por execução entrariam na mesma janela do
    atendimento de verdade, e a latência média do produto passaria a incluir a
    régua medindo o produto.
    """
    assert visor.AMBIENTE == "evals"

    espiao = _ClienteEspiao()
    monkeypatch.setattr(observability, "client", lambda: espiao)
    visor.registrar([_resultado(aprovado=True)], "S-03", "uma-execucao", "um-dataset")

    assert espiao.scores[0]["environment"] == "evals"


@pytest.mark.risco("R7")
def test_the_score_is_the_same_boolean_that_decides_the_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R7, ADR-006 — um booleano por caso, e ele é lido, não recalculado.

    Recalcular o veredito aqui criaria a segunda conta que a regra de ouro existe
    para não ter, e a divergência apareceria do pior jeito possível: alguém dizendo
    "o Langfuse diz que passou" sobre um caso que o portão reprovou.

    E é **booleano**, não numérico: um score contínuo é um limiar esperando para
    ser escrito, e o ADR-006 recusou a rubric de frente.
    """
    espiao = _ClienteEspiao()
    monkeypatch.setattr(observability, "client", lambda: espiao)
    reprovado = _resultado(aprovado=False)
    visor.registrar([reprovado], "S-03", "uma-execucao", "um-dataset")

    score = espiao.scores[0]
    assert score["name"] == "aprovado"
    assert score["value"] is False
    assert score["data_type"] == "BOOLEAN"
    assert score["value"] == reprovado.aprovado
    # E o motivo viaja junto: booleano vermelho sem motivo manda a pessoa de volta
    # ao markdown, e o ponto de estar no visor é não precisar.
    assert "criterio nao atendido" in score["comment"]


@pytest.mark.risco("R7")
def test_a_langfuse_that_is_down_does_not_reprove_the_suite(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R7, ADR-010 — o visor não participa do veredito, nem para derrubá-lo.

    Uma execução da suíte custa dinheiro e dezenas de minutos. Deixar uma exceção
    do SaaS escapar daqui transformaria uma indisponibilidade de terceiro em
    suíte vermelha — vermelho por motivo alheio ao código, que é exatamente o que
    ensina a ignorar o CI.

    Este teste exercita as duas funções públicas contra um cliente que levanta em
    tudo. O que ele afirma é a ausência de exceção; o log é a evidência de que a
    falha não passou em silêncio.
    """

    class _ClienteQuebrado:
        def __getattr__(self, _: str) -> Any:
            raise RuntimeError("Langfuse fora do ar")

    monkeypatch.setattr(observability, "client", lambda: _ClienteQuebrado())
    with caplog.at_level(logging.WARNING):
        casos = carregar_casos(EVALS, spec="S-03")
        dataset = visor.sincronizar(casos, "S-03")
        visor.registrar([_resultado(aprovado=True)], "S-03", "uma-execucao", dataset)

    assert dataset is None, "sem dataset, `registrar` não tem o que fazer e sai cedo"
    assert any("seguindo" in registro.message for registro in caplog.records), (
        "a falha do visor precisa aparecer no log: falhar em silêncio esconderia "
        "que a régua parou de ser observável"
    )


@pytest.mark.risco("R7")
def test_the_run_item_call_matches_the_real_sdk_signature() -> None:
    """R7 — o dublé não pode ser mais permissivo que o fornecedor.

    A primeira versão chamava `dataset_run_items.create(request=...)`, que não
    existe: o SDK recebe os campos direto. O `except` do visor engoliu o
    `TypeError`, a suíte inteira "deu certo", e o Langfuse ficou com o dataset
    sincronizado e **zero runs**. Só apareceu ao ler de volta à mão.

    Este teste compara o que o visor chama com o que o SDK aceita, na função de
    verdade — é a única forma de a próxima divergência de API reprovar antes de
    custar uma execução. `docs/testes.md` §4 permite ficar na fronteira do
    fornecedor, e é exatamente onde isto está.
    """
    import inspect

    from langfuse.api.dataset_run_items.client import DatasetRunItemsClient

    aceitos = set(inspect.signature(DatasetRunItemsClient.create).parameters)
    usados = {"run_name", "dataset_item_id", "trace_id", "run_description", "metadata"}

    assert usados <= aceitos, (
        f"o visor passa argumentos que o SDK não aceita: {sorted(usados - aceitos)}"
    )


@pytest.mark.risco("R7")
def test_a_visor_that_silently_registered_nothing_says_so_out_loud(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R7 — engolir exceção é a regra aqui, e o preço dela é quebrar em silêncio.

    Aconteceu de verdade nesta spec: a primeira execução mandou a suíte inteira
    para o Langfuse com a chamada de dataset run errada, o `except` a engoliu, e a
    execução "deu certo" com **zero runs** do outro lado. Só apareceu porque
    alguém foi conferir à mão — que é exatamente o trabalho que o visor existe
    para poupar.

    A correção não pode ser deixar a exceção subir: isso poria o portão atrás do
    SaaS, e o ADR-010 recusa. É esta linha no stderr, e é ela que este teste prende.
    """

    class _MetadeQuebrada(_ClienteEspiao):
        @property
        def api(self) -> Any:
            raise RuntimeError("dataset run recusado")

    monkeypatch.setattr(observability, "client", lambda: _MetadeQuebrada())
    visor.registrar(
        [_resultado(aprovado=True), _resultado(aprovado=False)],
        "S-03",
        "uma-execucao",
        "um-dataset",
    )

    aviso = capsys.readouterr().err
    assert "AVISO" in aviso
    assert "0 de 2" in aviso
    assert "NAO depende" in aviso, (
        "o aviso precisa dizer que o veredito não depende do visor, ou alguém vai "
        "ler um problema de observabilidade como suíte reprovada"
    )


@pytest.mark.risco("R7")
def test_a_case_without_a_trace_id_is_not_counted_as_reaching_the_run(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R7, ADR-014 — o mesmo incidente por outro caminho, e sem exceção nenhuma.

    O teste vizinho cobre o caminho em que `api` levanta. Este cobre o que a
    verificação independente da S-06 encontrou (ACH-4) e que nenhum teste tocava:
    `create_score` aceita `trace_id=None` sem reclamar, então o caso incrementava
    o contador enquanto o `dataset_run_items.create` era pulado em silêncio. Com o
    Langfuse configurado e todos os traces falhando — `_trace_do_caso` engole a
    exceção e faz `yield None`, e `get_current_trace_id()` também devolve `None`
    legitimamente — o resultado era **zero run items** e a frase tranquilizadora.

    Que é, literalmente, o sintoma do incidente que o aviso foi criado para pegar:
    dataset sincronizado, run vazio, suíte "deu certo".
    """
    espiao = _ClienteEspiao()
    monkeypatch.setattr(observability, "client", lambda: espiao)

    visor.registrar(
        [_resultado(aprovado=True, trace_id=None), _resultado(aprovado=False, trace_id=None)],
        "S-03",
        "uma-execucao",
        "um-dataset",
    )

    # Os scores foram — e é por isso que contar só eles mentia.
    assert len(espiao.scores) == 2
    assert espiao.itens == []

    aviso = capsys.readouterr().err
    assert "AVISO" in aviso
    assert "0 de 2" in aviso, "o aviso precisa dizer que NENHUM caso entrou no run"
    assert "NAO depende" in aviso


@pytest.mark.risco("R7")
def test_there_is_no_path_that_reads_from_langfuse_back_into_the_verdict() -> None:
    """R7, ADR-014 — a sincronização é de mão única, e a ausência é a garantia.

    O dataset é uma projeção do corpus. Editar um item na UI não pode mudar
    veredito nenhum: o portão lê o YAML do repositório, que é o que o CODEOWNERS
    protege. Uma leitura aqui — `get_dataset`, `get_dataset_run` — seria a porta
    por onde a régua passaria a morar fora do repositório.
    """
    chamadas = _chamadas_de(visor)

    for leitura in ("get_dataset", "get_dataset_run", "get_dataset_runs", "run_experiment"):
        assert leitura not in chamadas, (
            f"`{leitura}` no visor abre a mão de volta: o dataset do Langfuse "
            f"passaria a poder influenciar o veredito, e ele é projeção, não fonte"
        )
