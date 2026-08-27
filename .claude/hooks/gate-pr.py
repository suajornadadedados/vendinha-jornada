#!/usr/bin/env python
"""PreToolUse gate: no PR for a spec branch without an approved verification report.

CLAUDE.md, flow item 4, ends with "Sem veredito, não existe PR." Everything else in the
harness *asks* for that; this file is the only thing that *enforces* it. It is the golden
rule of the project turned on the harness itself: the model decides what to say, the code
decides what can be done.

Wired in .claude/settings.json as a PreToolUse hook on Bash. Reads the hook payload on
stdin, writes a permission decision on stdout. Needs `python` on PATH (3.12, stdlib only).

Three outcomes, on purpose:
  deny  - no report at all, or the verdict is REPROVADO. Nothing to decide.
  ask   - a verdict exists but the evidence no longer matches HEAD, or cannot be read.
          This is the normal CLAUDE.md item 5 path: fixes land after the verdict. A human
          may approve shipping unverified commits; a hook must not approve it silently.
  allow - verified, fresh, committed. The gate stays quiet, which is how it stays alive.

Messages are PT-BR because a person reads them, like the rest of the harness docs. Code
and comments are English, per CLAUDE.md.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

REPORT_DIR = Path("docs/specs/relatorios")
SPEC_BRANCH = re.compile(r"^spec/s-(\d{2})\b", re.IGNORECASE)
PR_COMMANDS = (
    re.compile(r"\bgh\b[^\n]*\bpr\b[^\n]*\bcreate\b"),
    re.compile(r"\bgh\b[^\n]*\bapi\b[^\n]*/pulls\b"),
)
# Longest first: "APROVADO" is a prefix of "APROVADO COM RESSALVAS".
VERDICTS = ("APROVADO COM RESSALVAS", "REPROVADO", "APROVADO")


def decide(kind: str, reason: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": kind,
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )
    sys.exit(0)


def git(root: Path | str, *args: str) -> str:
    try:
        # S603/S607: `git` from PATH with a fixed argv is the point — nothing here comes
        # from the model, and pinning an absolute path would break every other machine.
        done = subprocess.run(  # noqa: S603
            ["git", *args],  # noqa: S607
            cwd=root,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def parse_report(text: str) -> tuple[str | None, str]:
    """Return (verdict, reviewed_commit) from the report.

    Frontmatter is the contract going forward. The fallback reads the header table, so
    reports written before this gate existed still count as evidence instead of blocking.
    """
    front: dict[str, str] = {}
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            for line in text[3:end].splitlines():
                key, sep, value = line.partition(":")
                if sep:
                    front[key.strip().lower()] = value.strip().strip("`*\"'")

    raw = front.get("veredito", "")
    if not raw:
        row = re.search(r"\|\s*\*{0,2}Veredito\*{0,2}\s*\|(.+?)\|", text, re.IGNORECASE)
        raw = row.group(1) if row else ""
    raw = re.sub(r"[*`]", "", raw).strip().upper()
    verdict = next((v for v in VERDICTS if v in raw), None)

    commit = front.get("commit", "")
    if not commit:
        # Header table shape: | **Branch** | `spec/s-03-...` @ `475562d` (9 commits) |
        sha = re.search(r"@\s*`?([0-9a-f]{7,40})`?", text)
        commit = sha.group(1) if sha else ""

    return verdict, commit


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        # A gate that crashes on a malformed payload is a gate that gets removed.
        sys.exit(0)

    if payload.get("tool_name") != "Bash":
        sys.exit(0)
    command = payload.get("tool_input", {}).get("command", "") or ""
    if not any(pattern.search(command) for pattern in PR_COMMANDS):
        sys.exit(0)

    # The payload cwd is authoritative; Path.cwd() covers a caller that omits it.
    top = git(payload.get("cwd") or Path.cwd(), "rev-parse", "--show-toplevel") or git(
        Path.cwd(), "rev-parse", "--show-toplevel"
    )
    root = Path(top) if top else Path.cwd()

    branch = git(root, "rev-parse", "--abbrev-ref", "HEAD")
    if not branch:
        # Fail closed but soft: a PR command whose state we cannot read is exactly the
        # case where a silent "allow" would make this whole file decorative.
        decide(
            "ask",
            f"Não consegui determinar a branch em `{root}` para checar o portão de "
            "verificação. Confirme você se este PR já tem relatório aprovado.",
        )
    match = SPEC_BRANCH.match(branch)
    if not match:
        # The gate guards the spec flow; chore/ and docs/ branches are not it.
        sys.exit(0)
    spec = f"S-{match.group(1)}"

    rel = f"{REPORT_DIR.as_posix()}/{spec}-verificacao.md"
    report = root / rel

    if not report.is_file():
        decide(
            "deny",
            f"PR bloqueado: {spec} não tem relatório de verificação.\n\n"
            f"`{rel}` não existe. Pelo CLAUDE.md (fluxo, item 4) a verificação independente "
            "vem ANTES do PR — sem veredito, não existe PR.\n\n"
            f"Rode `/fechar-spec {spec}`: ele dispara o `verificador-de-spec` e volta com o "
            "relatório. Não contorne este portão abrindo o PR pela web.",
        )

    try:
        text = report.read_text(encoding="utf-8")
    except OSError as err:
        decide("ask", f"Não consegui ler `{rel}`: {err}. Confirme na mão.")

    verdict, reviewed = parse_report(text)

    if verdict == "REPROVADO":
        decide(
            "deny",
            f"PR bloqueado: o veredito de {spec} é REPROVADO.\n\n"
            f"Leia as condições de fechamento em `{rel}`, corrija nesta mesma branch e rode "
            f"`/fechar-spec {spec}` de novo. O PR nasce com a correção dentro (CLAUDE.md, "
            "item 5) — ele não é o lugar de discutir o que a verificação já reprovou.",
        )

    if verdict is None:
        decide(
            "ask",
            f"Não consegui ler o veredito em `{rel}`. Esperava `veredito:` no frontmatter ou "
            "uma linha `| **Veredito** | ... |` na tabela de cabeçalho.\n\n"
            "O portão não vai adivinhar: confirme você se este PR deve sair.",
        )

    dirty = git(root, "status", "--porcelain", "--", rel)
    if dirty:
        decide(
            "ask",
            f"O relatório de {spec} não está commitado (`git status` diz "
            f"`{dirty.splitlines()[0].strip()}`).\n\n"
            f"O PR não vai carregar a evidência que o justifica. Commite `{rel}` antes de abrir.",
        )

    head = git(root, "rev-parse", "HEAD")
    if reviewed and git(root, "cat-file", "-t", reviewed) == "commit":
        # Commits that only touch the report itself are not unverified code.
        since = git(
            root,
            "log",
            "--oneline",
            f"{reviewed}..HEAD",
            "--",
            ".",
            f":(exclude){REPORT_DIR.as_posix()}",
        )
        if since:
            decide(
                "ask",
                f"O relatório de {spec} verificou `{reviewed[:7]}` e o HEAD agora é "
                f"`{head[:7]}`. Estes commits entraram DEPOIS do veredito ({verdict}) e não "
                f"foram verificados:\n\n{since}\n\n"
                "Esse é o caminho normal do CLAUDE.md item 5 — corrigir o que a verificação "
                "apontou, antes do PR. Se a correção mexeu no que foi verificado, rode "
                f"`/fechar-spec {spec}` de novo. Quem aprova código não verificado é você, "
                "não o hook.",
            )
    elif reviewed:
        decide(
            "ask",
            f"O relatório de {spec} cita o commit `{reviewed[:7]}`, que não existe nesta "
            "branch (rebase ou amend depois da verificação?). Não dá para dizer o que foi "
            "verificado.",
        )

    # Verified, fresh, committed. Say nothing and get out of the way.
    sys.exit(0)


if __name__ == "__main__":
    main()
