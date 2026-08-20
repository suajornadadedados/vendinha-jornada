"""Render docs/harness/skills.md from .claude/skills.lock.json (ADR-009).

Invoked by scripts/gen-skills-doc.sh. The lockfile is the source of truth: the
`porque` field of every skill becomes the "Por que esta aqui" column, so a skill
without a justification cannot be documented — and therefore should not exist.
"""

import json
import sys
from collections import OrderedDict
from pathlib import Path

DASH = "—"  # em dash, as used across the project docs

INTRO = [
    "# Skills do harness",
    "",
    "> Gerado por `scripts/gen-skills-doc.sh` a partir de `.claude/skills.lock.json`.",
    "> Nao edite este arquivo a mao. Decisao: ADR-009.",
    "",
    "As skills sao **vendorizadas**: copiadas para `.claude/skills/` e versionadas.",
    f"Quem clona o repositorio recebe o harness junto com o codigo {DASH} e o que torna o setup",
    "reproduzivel (docs/requisitos.md) e a condicao para o padrao autor/revisor do ADR-005",
    "valer, ja que autor e revisor precisam rodar com exatamente as mesmas skills.",
    "",
]

OWN_ROW = (
    "| `vendinha-harness` | Roteia spec -> skills e declara a precedencia dos normativos do "
    "projeto sobre skills de terceiros. Nao e vendorizada: e o codigo-fonte do harness. |"
)

MAINTENANCE = [
    "## Manutencao",
    "",
    "```bash",
    "bash scripts/vendor-skills.sh    # materializa .claude/skills/ a partir do lock",
    "bash scripts/pin-skills.sh       # atualiza os SHAs de origem para o HEAD atual",
    "bash scripts/gen-skills-doc.sh   # regenera este documento",
    "```",
    "",
    "`.claude/skills/` e **derivado**. Editar uma skill vendorizada a mao faz o job",
    "`skills-drift` do CI reprovar o PR. Para adaptar comportamento ao projeto, edite",
    f"`.claude/skills/vendinha-harness/SKILL.md` {DASH} nunca a skill de terceiro.",
    "",
]


def render(lock: OrderedDict) -> str:
    lines = list(INTRO)

    lines += ["## Origens fixadas", "", "| Repositorio | SHA |", "|---|---|"]
    for repo, sha in lock["sources"].items():
        lines.append(f"| [{repo}](https://github.com/{repo}) | `{sha[:12]}` |")
    lines.append("")

    skills = lock["skills"]
    lines += [f"## Skills instaladas ({len(skills)})", ""]

    by_repo: OrderedDict = OrderedDict()
    for skill in skills:
        by_repo.setdefault(skill["repo"], []).append(skill)

    for repo, items in by_repo.items():
        lines += [f"### {repo}", "", "| Skill | Por que esta aqui |", "|---|---|"]
        for skill in items:
            lines.append(f"| `{skill['name']}` | {skill['porque']} |")
        lines.append("")

    lines += ["## Skill propria", "", "| Skill | Papel |", "|---|---|", OWN_ROW, ""]

    lines += [
        "## Rejeitadas (e por que)",
        "",
        "A lista do que foi recusado diz mais sobre o criterio do que a lista do que foi aceito.",
        "",
        "| Candidata | Origem | Motivo da recusa |",
        "|---|---|---|",
    ]
    for entry in lock["rejeitadas"]:
        lines.append(f"| {entry['name']} | {entry['repo']} | {entry['porque_nao']} |")
    lines.append("")

    lines += MAINTENANCE
    return "\n".join(lines) + "\n"


def main() -> None:
    lock_path, dest = Path(sys.argv[1]), Path(sys.argv[2])
    with lock_path.open(encoding="utf-8") as handle:
        lock = json.load(handle, object_pairs_hook=OrderedDict)
    # newline="\n" e explicito: no Windows o modo texto gravaria CRLF e o
    # arquivo versionado mudaria inteiro no proximo diff.
    with dest.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(render(lock))


if __name__ == "__main__":
    main()
