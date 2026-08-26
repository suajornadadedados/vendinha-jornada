"""Redaction at the source — the only reason Langfuse Cloud is acceptable.

ADR-010 says it in one line: *it is not the hosting that guarantees privacy, it is
the masking.* Self-hosted with a naive trace leaks PII into your own log; cloud
with masking at the source has nothing to leak. That inverts the intuition, and it
is why this module is a precondition of that decision rather than a complement to
it (ADR-007, R5, RF-5.2).

**Two mechanisms, and they guarantee different things.** Worth saying out loud,
because one of them is much weaker than it sounds:

* *By pattern* — CPF, CNPJ, e-mail, phone, credential. These have a shape, so they
  are found in any text, from any source, with nobody registering anything.
* *By known value* — the name. A name has no shape. There is no honest regex for
  "is this a person's name", and pretending otherwise would mean shipping an NER
  model and a promise this project cannot keep. What the process knows, it masks:
  once a customer's name has been collected, that exact string stops leaving. Until
  then, a name is indistinguishable from any other word.

**Over-masking is a real failure, not a safe default.** A trace where the price,
the order id and the model name have all been scrubbed debugs nothing, and a team
that cannot debug turns masking off. The patterns below are deliberately narrow,
and `tests/security/test_pii_redaction.py` asserts that a price survives.

The placeholders are in Portuguese because they are read next to Portuguese
conversations, in the same trace — they are content, like the system prompt, not
code.

Pure, synchronous and dependency-free on purpose: this runs on the OpenTelemetry
export path, where Langfuse's own documentation warns against slow work and async
I/O, and inside a logging filter, where an import cycle would be a delight to
debug at three in the morning.
"""

import re
import threading
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache

# CNPJ before CPF: same digit soup, and the longer one has to win the race.
CNPJ = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]*\w\b")

# Narrow on purpose. A bare eight-digit run is an order number as often as it is a
# phone, so a separator, a DDD in parentheses or the country code has to be there.
PHONE = re.compile(
    r"(?:\+55[\s-]?)?(?:\(\d{2}\)|\b\d{2})[\s-]\d{4,5}[\s-]?\d{4}\b"
    r"|\+55[\s-]?\d{2}[\s-]?\d{4,5}[\s-]?\d{4}\b"
)

# Provider and observability keys (ADR-012). The prefixes are the vendors' own, and
# they are what makes these findable without also matching every long word.
CREDENTIAL = re.compile(
    r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{8,}"
    r"|\bAPP_USR-[A-Za-z0-9_-]{8,}"
    r"|\bghp_[A-Za-z0-9]{16,}"
    r"|\bBearer\s+[A-Za-z0-9._-]{16,}"
)

# The password inside a connection URI. `db.py` prints the DSN on failure and every
# psycopg error carries it, so this is the credential most likely to reach a log
# without anyone deciding to log it. Only the password is replaced: the user, the
# host and the port are what make the line worth reading.
#
# `@127.0.0.1` used to disappear by accident, because the e-mail pattern happened to
# match it. `@postgres` and `@db` — the container forms S-08 will use — did not. An
# accident that covers the local case and drops the deployed one is the worst kind.
DSN_PASSWORD = re.compile(
    r"(?P<esquema>[a-z][a-z0-9+.-]*://)"
    r"(?P<user>[^:/?#@\s]+)"
    r":[^\s]+?@"
    r"(?=[\w.\-\[\]:]+(?:[/?#\s]|$))"
)

PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (DSN_PASSWORD, r"\g<esquema>\g<user>:[CREDENCIAL]@"),
    (CREDENTIAL, "[CREDENCIAL]"),
    (EMAIL, "[EMAIL]"),
    (CNPJ, "[CNPJ]"),
    (CPF, "[CPF]"),
    (PHONE, "[TELEFONE]"),
)

# Below this length a "known value" matches half the dictionary. Masking a name
# like "Ana" everywhere would scrub the syllable inside unrelated words.
MIN_KNOWN_VALUE_LENGTH = 4


@dataclass(frozen=True)
class Redactor:
    """Patterns always; known values when the process has learned them."""

    known_values: frozenset[str] = field(default_factory=frozenset)

    def text(self, value: str) -> str:
        """Redact one string. Idempotent — running it twice changes nothing."""
        for pattern, placeholder in PATTERNS:
            value = pattern.sub(placeholder, value)

        known = _known_values_pattern(self.known_values)
        if known is not None:
            value = known.sub("[NOME]", value)
        return value

    def attributes(self, attributes: Mapping[str, object]) -> dict[str, str]:
        """Redact string-valued attributes, reporting only what actually changed.

        Returning just the differences keeps the OpenTelemetry patch sparse, which
        is what the Langfuse contract asks for — and it keeps a trace diff readable,
        because an attribute that shows up in a patch really did change.
        """
        changed: dict[str, str] = {}
        for key, value in attributes.items():
            if isinstance(value, str):
                redacted = self.text(value)
                if redacted != value:
                    changed[key] = redacted
        return changed


@lru_cache(maxsize=64)
def _known_values_pattern(known_values: frozenset[str]) -> re.Pattern[str] | None:
    """One compiled alternation for every known value, cached by the value set.

    Was one `re.sub` per name and per name part, per string redacted. That is fine
    with three names and quadratic-feeling with five hundred: measured at 0,0065 ms
    with an empty registry and 17,28 ms with it full, on every log line and every
    exported span attribute. The registry only fills up from S-04, so this was a
    latent cost — the kind that shows up as "the app got slow" two specs later, with
    nothing in the diff to blame.

    Alternation ordered longest first: "Marta Ribeiro" has to be consumed before
    "Marta", or the surname survives on its own. The first name still gets its own
    branch, because a customer introduces herself once and is greeted by first name
    in every reply after that.
    """
    pieces: set[str] = set()
    for value in known_values:
        if len(value) < MIN_KNOWN_VALUE_LENGTH:
            continue
        pieces.add(value)
        pieces.update(part for part in value.split() if len(part) >= MIN_KNOWN_VALUE_LENGTH)

    if not pieces:
        return None

    ordered = sorted(pieces, key=len, reverse=True)
    # Sem `\b`, de propósito. Para NOME a direção segura é mascarar demais: `\b`
    # deixava de cobrir o nome grudado em outro texto, e um nome que escapa é
    # vazamento de PII, enquanto um "Ribeiros" mascarado é só um log menos bonito.
    # A terceira verificação pegou essa troca de semântica acontecendo em silêncio,
    # dentro de uma reescrita que era só de desempenho.
    return re.compile(
        "(?:" + "|".join(re.escape(piece) for piece in ordered) + ")",
        flags=re.IGNORECASE,
    )


class KnownValues:
    """Bounded, process-wide registry of exact strings that must never leave.

    Process-wide rather than session-scoped, and that is a decision rather than an
    oversight. The redaction that matters runs on the OpenTelemetry export worker
    thread, which has no request context and never will — a `contextvar` set on the
    request thread is simply not there when the batch ships. A registry the export
    path can read is the only thing that makes the guarantee hold *at the boundary*,
    which is the entire point of a security test.

    The cost is over-masking: a name collected in one session is masked in every
    trace while it is remembered. That is the safe direction, and it is bounded —
    the oldest entries fall off, so a long-lived process does not quietly turn this
    into a memory leak with a customer list inside it.
    """

    def __init__(self, maxsize: int = 512) -> None:
        self._maxsize = maxsize
        self._lock = threading.Lock()
        self._values: OrderedDict[str, None] = OrderedDict()

    def remember(self, value: str) -> None:
        """Register a value collected from a customer — a name, typically."""
        cleaned = value.strip()
        if len(cleaned) < MIN_KNOWN_VALUE_LENGTH:
            return
        with self._lock:
            self._values.pop(cleaned, None)
            self._values[cleaned] = None
            while len(self._values) > self._maxsize:
                self._values.popitem(last=False)

    def snapshot(self) -> frozenset[str]:
        with self._lock:
            return frozenset(self._values)

    def clear(self) -> None:
        with self._lock:
            self._values.clear()
        # O `lru_cache` guarda o padrão compilado por conjunto de valores, então sem
        # isto um `clear()` esvazia o registro e deixa os nomes vivos dentro do cache
        # do módulo — um dos lugares onde a terceira verificação foi procurar.
        _known_values_pattern.cache_clear()


KNOWN_VALUES = KnownValues()
_PATTERNS_ONLY = Redactor()


def redactor() -> Redactor:
    """The redactor to use at a boundary: patterns plus whatever the process knows."""
    return Redactor(known_values=KNOWN_VALUES.snapshot())


def redact(value: str) -> str:
    """Pattern-only redaction, for callers with no collected values to consider."""
    return _PATTERNS_ONLY.text(value)
