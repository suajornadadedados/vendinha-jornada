#!/usr/bin/env bash
#
# Regenera docs/harness/skills.md a partir de .claude/skills.lock.json (ADR-009).
#
#   bash scripts/gen-skills-doc.sh           # reescreve o documento
#   bash scripts/gen-skills-doc.sh --check   # nao escreve; sai != 0 se estiver desatualizado
#
# O documento e derivado: o campo "porque" de cada skill no lockfile e a fonte
# da coluna "Por que esta aqui". Skill sem justificativa nao entra.

source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

DOC="$REPO_ROOT/docs/harness/skills.md"
OUT="$(mktemp)"
trap 'rm -f "$OUT"' EXIT

# O python escreve o arquivo diretamente, em UTF-8 com LF. Passar por stdout do
# shell faria o encoding do console (cp1252 no Windows) vazar para um arquivo
# versionado — e o diff do proximo PR viria inteiro.
"$PY" "$REPO_ROOT/scripts/gen_skills_doc.py" "$LOCK" "$OUT"

if [ "${1:-}" = "--check" ]; then
  if diff -q "$OUT" "$DOC" >/dev/null 2>&1; then
    echo "OK: docs/harness/skills.md esta em dia com o lockfile."
    exit 0
  fi
  echo "docs/harness/skills.md esta desatualizado em relacao ao lockfile:"
  diff "$DOC" "$OUT" || true
  echo
  echo "Rode: bash scripts/gen-skills-doc.sh"
  exit 1
fi

mkdir -p "$(dirname "$DOC")"
cp "$OUT" "$DOC"
echo "OK: docs/harness/skills.md regenerado."
