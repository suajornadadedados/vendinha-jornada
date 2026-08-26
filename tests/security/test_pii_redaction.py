"""R5 — nothing sensitive leaves this process, and the question is reachability.

`docs/testes.md` §1 draws the line these tests sit on: a unit test says the
function redacts correctly, a security test says the un-redacted value has no path
out. Both matter here, and the second is the one that produces a guarantee.

Since ADR-010 the traces go to Langfuse Cloud, so "out of this process" means "out
of our infrastructure". That is why REQ-4 of S-02 is an invariant of release rather
than hygiene: with the export hook broken, the leak is not to a container on the
same machine.

The export tests are the important ones. They do not ask the redactor whether it
works — they build an OpenTelemetry batch shaped like the one Langfuse actually
hands the hook, including a span from a third-party instrumentation scope our code
never touches, and assert that what comes back out is clean. That is the difference
between "we remembered to redact" and "the path does not exist".

Credentials ride along under ADR-012: the provider API key is a second class of
secret inside the process, and D-4 of the spec records why it is tested here rather
than in a file of its own — same seam, same boundary, and `docs/testes.md` §2
already maps that seam to this file.
"""

import logging

import pytest
from langfuse.types import (
    MaskOtelSpansParams,
    MaskOtelSpansResult,
    OtelSpanData,
    OtelSpanIdentifier,
)

from vendinha.observability import RedactingLogFilter, mask_otel_spans
from vendinha.redaction import KNOWN_VALUES, Redactor, redact

# Keys shaped like the real thing and belonging to nobody. The guardrail in
# CLAUDE.md is absolute: no real credential in the repository, not even in a test.
FAKE_PROVIDER_KEY = "sk-ant-api03-" + "A" * 40
FAKE_LANGFUSE_KEY = "sk-lf-" + "b" * 32


def _span(scope: str, **attributes: str) -> tuple[OtelSpanIdentifier, OtelSpanData]:
    identifier = OtelSpanIdentifier(trace_id=f"trace-{scope}", span_id=f"span-{scope}")
    data = OtelSpanData(
        trace_id=identifier.trace_id,
        span_id=identifier.span_id,
        parent_span_id=None,
        name="conversa",
        instrumentation_scope_name=scope,
        instrumentation_scope_version="1.0",
        attributes=dict(attributes),
        resource_attributes={},
    )
    return identifier, data


def _export(**spans: dict[str, str]) -> dict[str, dict[str, str]]:
    """Run one batch through the hook and return the attributes as they would ship."""
    batch = dict(_span(scope, **attrs) for scope, attrs in spans.items())
    result = mask_otel_spans(params=MaskOtelSpansParams(spans=batch))

    shipped: dict[str, dict[str, str]] = {}
    patches = result.span_patches if isinstance(result, MaskOtelSpansResult) else {}
    for identifier, data in batch.items():
        attrs = dict(data.attributes)
        patch = patches.get(identifier)
        if patch is not None:
            for key in patch.delete_attributes:
                attrs.pop(key, None)
            attrs.update(patch.set_attributes)
        assert data.instrumentation_scope_name is not None
        shipped[data.instrumentation_scope_name] = {str(k): str(v) for k, v in attrs.items()}
    return shipped


@pytest.mark.risco("R5")
def test_a_cpf_never_survives_redaction(pii_de_teste: dict[str, str]) -> None:
    """Punctuated or not — the customer types it either way, and both are the CPF."""
    for cpf in (pii_de_teste["cpf"], pii_de_teste["cpf_sem_pontuacao"]):
        redacted = redact(f"pode faturar no CPF {cpf}, por favor")
        assert cpf not in redacted
        assert "[CPF]" in redacted


@pytest.mark.risco("R5")
def test_an_email_never_survives_redaction(pii_de_teste: dict[str, str]) -> None:
    redacted = redact(f"meu email e {pii_de_teste['email']}")
    assert pii_de_teste["email"] not in redacted
    assert "[EMAIL]" in redacted


@pytest.mark.risco("R5")
def test_a_phone_number_never_survives_redaction(pii_de_teste: dict[str, str]) -> None:
    redacted = redact(f"me chama no {pii_de_teste['telefone']}")
    assert pii_de_teste["telefone"] not in redacted
    assert "[TELEFONE]" in redacted


@pytest.mark.risco("R5")
def test_a_known_name_is_masked_even_when_only_the_first_name_appears(
    pii_de_teste: dict[str, str],
) -> None:
    """The honest half of REQ-4, and the reason it is written this way.

    CPF, e-mail, phone and credentials have a shape, so a pattern finds them in any
    text. A name does not. Claiming generic name detection would mean shipping an
    NER model and a promise this project cannot keep — see D-6 in the spec. What
    the code does guarantee: once a name has been collected, that string stops
    leaving the process.

    The first name on its own is the case that matters and the one a naive
    implementation misses. A customer introduces herself as "Marta Ribeiro" once,
    and every reply after that says "Marta" — masking only the full string leaves
    the name in every turn but the first. Removing that half of the implementation
    used to leave this file green; now it does not.
    """
    full_name = pii_de_teste["nome"]
    first_name = full_name.split()[0]

    assert full_name in redact(f"em nome de {full_name}"), "sem contexto, um nome e so um texto"

    redactor = Redactor(known_values=frozenset({full_name}))
    redacted = redactor.text(f"claro, {first_name}! confirmo o pedido de {full_name}")

    assert full_name not in redacted
    assert first_name not in redacted, "o primeiro nome sozinho tambem e o nome"
    assert redacted.count("[NOME]") == 2


@pytest.mark.risco("R5")
def test_a_provider_credential_never_survives_redaction() -> None:
    """ADR-012 put a third-party secret inside the process; this is half of its price."""
    for key in (FAKE_PROVIDER_KEY, FAKE_LANGFUSE_KEY):
        redacted = redact(f"Authorization: Bearer {key}")
        assert key not in redacted
        assert "[CREDENCIAL]" in redacted


@pytest.mark.risco("R5")
def test_the_export_hook_scrubs_every_string_attribute(pii_de_teste: dict[str, str]) -> None:
    """The reachability test: a batch shaped like the real one, and nothing gets out.

    The `langchain` span matters more than ours. It is written by an instrumentation
    we do not control, carrying whatever the callback handler saw — and it ships
    through the same client and the same hook.
    """
    cpf = pii_de_teste["cpf"]
    email = pii_de_teste["email"]

    shipped = _export(
        **{
            "langfuse-sdk": {
                "langfuse.observation.input": f"cliente: {cpf}",
                "langfuse.session.id": "sessao-42",
            },
            "langchain": {
                "gen_ai.prompt.0.content": f"meu email e {email} e meu cpf {cpf}",
                "gen_ai.completion.0.content": f"confirmado, {cpf}",
                "gen_ai.request.model": "claude-haiku-4-5",
            },
        }
    )

    everything = " ".join(value for span in shipped.values() for value in span.values())
    for secret in (cpf, email, pii_de_teste["cpf_sem_pontuacao"]):
        assert secret not in everything, f"{secret!r} chegaria ao Langfuse em claro"

    assert "[CPF]" in everything and "[EMAIL]" in everything
    # Redaction is not deletion: a trace where every attribute is gone debugs
    # nothing, and the session id is what makes a trace findable at all.
    assert shipped["langfuse-sdk"]["langfuse.session.id"] == "sessao-42"
    assert shipped["langchain"]["gen_ai.request.model"] == "claude-haiku-4-5"


@pytest.mark.risco("R5")
def test_a_remembered_name_does_not_reach_the_export_either(
    pii_de_teste: dict[str, str],
) -> None:
    """The known-value half has to hold at the boundary, not only in the function.

    The export runs on the OpenTelemetry worker thread, with no request context —
    which is exactly why the registry is process-wide instead of a `contextvar`. A
    test that only exercised `Redactor` directly would never notice the difference,
    and the difference is the whole guarantee.
    """
    full_name = pii_de_teste["nome"]
    first_name = full_name.split()[0]

    KNOWN_VALUES.clear()
    try:
        KNOWN_VALUES.remember(full_name)
        shipped = _export(
            **{"langchain": {"gen_ai.completion.0.content": f"claro, {first_name}, ja anotei"}}
        )
        content = shipped["langchain"]["gen_ai.completion.0.content"]
        assert first_name not in content
        assert "[NOME]" in content
    finally:
        KNOWN_VALUES.clear()


@pytest.mark.risco("R5")
def test_the_export_hook_leaves_a_clean_span_untouched() -> None:
    """No patch for spans with nothing to hide — churn hides the real edits."""
    batch = dict([_span("langchain", **{"gen_ai.request.model": "gpt-5-mini"})])
    result = mask_otel_spans(params=MaskOtelSpansParams(spans=batch))
    assert result is None or not result.span_patches


@pytest.mark.risco("R5")
def test_a_price_is_not_mistaken_for_personal_data() -> None:
    """Over-masking is the failure mode nobody reports: the trace is clean and useless.

    Prices, order ids and quantities look like digits to a careless pattern, and a
    trace that redacts them is a trace nobody can debug — which is how a team ends
    up turning masking off entirely.
    """
    text = "o Canastra meia-cura sai por 89.90 e o pedido 100234 tem 3 itens"
    assert redact(text) == text


@pytest.mark.risco("R5")
def test_log_records_are_redacted_before_they_reach_a_handler(
    pii_de_teste: dict[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    """`docs/riscos.md` R5 says traces AND logs. A log file is an export too."""
    logger = logging.getLogger("vendinha.teste-de-redacao")
    logger.addFilter(RedactingLogFilter())

    with caplog.at_level(logging.INFO, logger=logger.name):
        logger.info("cliente informou %s", pii_de_teste["cpf"])
        logger.info("falha ao autenticar com %s", FAKE_PROVIDER_KEY)

    written = "\n".join(record.getMessage() for record in caplog.records)
    assert pii_de_teste["cpf"] not in written
    assert FAKE_PROVIDER_KEY not in written
    assert "[CPF]" in written and "[CREDENCIAL]" in written
