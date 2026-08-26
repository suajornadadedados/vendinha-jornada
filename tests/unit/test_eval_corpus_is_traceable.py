"""Guards the eval corpus that R7 depends on — without closing R7 itself.

R7 is closed by the eval suite running against the agent (`evals/`, job `evals`
from S-06 on). What lives here is its precondition: a case that is malformed, or
that points at a risk or a spec which does not exist, silently stops being a
ruler. It still shows up green in a corpus count, so nobody notices the gap.

This is the traceability check the root `pyproject.toml` is named after. It runs
in `tests/unit/` on purpose: `docs/testes.md` section 1 says two layers and only
two, so there is no `tests/discovery/` tier for it to live in.

No network, no agent, no API key — it only reads files already in the repo.
"""

import re
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
EVALS = REPO_ROOT / "evals"
SCHEMA = EVALS / "schema" / "caso.schema.json"
RISK_MATRIX = REPO_ROOT / "docs" / "riscos.md"
SPECS = REPO_ROOT / "docs" / "specs"

FAMILIES = ("golden", "adversarial")

# `| R1 | Modelo alucina ... |` — the first column of the matrix in docs/riscos.md.
RISK_ROW = re.compile(r"^\|\s*(R[1-9])\s*\|", re.MULTILINE)


def _case_files() -> list[Path]:
    return sorted(p for family in FAMILIES for p in (EVALS / family).glob("*.yaml"))


def _load(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


CASE_FILES = _case_files()
CASE_IDS = [p.stem for p in CASE_FILES]


def test_the_corpus_is_not_empty() -> None:
    """An empty corpus would make every check below vacuously true."""
    assert CASE_FILES, f"no eval case found under {EVALS}/{{golden,adversarial}}/"


@pytest.mark.parametrize("case_file", CASE_FILES, ids=CASE_IDS)
def test_every_case_matches_the_normative_schema(case_file: Path) -> None:
    """`evals/schema/caso.schema.json` is normative (evals/README.md)."""
    validator = Draft202012Validator(_load(SCHEMA))
    errors = sorted(validator.iter_errors(_load(case_file)), key=lambda e: e.path)
    assert not errors, "\n".join(
        f"{case_file.name}: {'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}"
        for e in errors
    )


@pytest.mark.parametrize("case_file", CASE_FILES, ids=CASE_IDS)
def test_case_id_and_family_match_where_the_file_lives(case_file: Path) -> None:
    """A case filed under the wrong family is counted in the wrong ruler."""
    case = _load(case_file)
    assert case["id"] == case_file.stem, (
        f"id '{case['id']}' does not match filename '{case_file.stem}'"
    )
    assert case["familia"] == case_file.parent.name, (
        f"familia '{case['familia']}' does not match folder '{case_file.parent.name}'"
    )


@pytest.mark.parametrize("case_file", CASE_FILES, ids=CASE_IDS)
def test_every_risk_cited_by_a_case_exists_in_the_matrix(case_file: Path) -> None:
    """A case pointing at a risk that does not exist proves nothing.

    The expected value comes from docs/riscos.md, not from a list restated here:
    a test that recomputes what it checks never disagrees with it.
    """
    known = set(RISK_ROW.findall(RISK_MATRIX.read_text(encoding="utf-8")))
    assert known, f"no risk row parsed from {RISK_MATRIX} — the matrix format changed"

    cited = set(_load(case_file)["riscos"])
    assert cited <= known, f"{case_file.name} cites risks absent from the matrix: {cited - known}"


@pytest.mark.parametrize("case_file", CASE_FILES, ids=CASE_IDS)
def test_every_spec_cited_by_a_case_exists(case_file: Path) -> None:
    """The `spec` field is what lets /verificar-spec find the cases it must run."""
    known = {p.name.split("-", 2)[0] + "-" + p.name.split("-", 2)[1] for p in SPECS.glob("S-*.md")}
    cited = _load(case_file)["spec"]
    assert cited in known, f"{case_file.name} cites spec '{cited}', which has no file in {SPECS}"
