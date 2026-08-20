#!/usr/bin/env bash
#
# Atualiza os SHAs de origem em .claude/skills.lock.json para o HEAD atual de
# cada repositorio (ADR-009).
#
#   bash scripts/pin-skills.sh              # atualiza os SHAs e mostra o que mudou
#   bash scripts/pin-skills.sh --dry-run    # so mostra, nao escreve
#
# Depois de rodar: revise o diff, rematerialize com vendor-skills.sh, regenere a
# documentacao com gen-skills-doc.sh e leia o diff das skills antes de commitar.
# Atualizacao silenciosa e exatamente o que o ADR-009 existe para impedir.

source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

declare -A NEW_SHAS
CHANGED=0

while IFS=$'\t' read -r repo sha; do
  [ -n "$repo" ] || continue
  head_sha="$(git ls-remote "https://github.com/$repo.git" HEAD | cut -f1)"
  [ -n "$head_sha" ] || die "nao consegui ler o HEAD de $repo"
  NEW_SHAS["$repo"]="$head_sha"
  if [ "$head_sha" = "$sha" ]; then
    printf '    %-40s ja esta em %s\n' "$repo" "${sha:0:12}"
  else
    printf '    %-40s %s -> %s\n' "$repo" "${sha:0:12}" "${head_sha:0:12}"
    CHANGED=1
  fi
done < <(lock_sources)

if [ "$CHANGED" = "0" ]; then
  echo "Nada a fazer: todas as origens ja estao no HEAD."
  exit 0
fi

if [ "$DRY" = "1" ]; then
  echo "--dry-run: lockfile nao foi alterado."
  exit 0
fi

MAPPING=""
for repo in "${!NEW_SHAS[@]}"; do
  MAPPING="$MAPPING$repo=${NEW_SHAS[$repo]}"$'\n'
done

printf '%s' "$MAPPING" | "$PY" - "$LOCK" <<'PYEOF'
import json, sys, collections
lock_path = sys.argv[1]
mapping = {}
for line in sys.stdin.read().splitlines():
    if "=" in line:
        repo, sha = line.split("=", 1)
        mapping[repo] = sha

with open(lock_path, encoding="utf-8") as f:
    lock = json.load(f, object_pairs_hook=collections.OrderedDict)

for repo in lock["sources"]:
    if repo in mapping:
        lock["sources"][repo] = mapping[repo]

with open(lock_path, "w", encoding="utf-8", newline="\n") as f:
    json.dump(lock, f, ensure_ascii=False, indent=2)
    f.write("\n")
PYEOF

echo
echo "Lockfile atualizado. Proximos passos, nesta ordem:"
echo "  1. bash scripts/vendor-skills.sh"
echo "  2. bash scripts/gen-skills-doc.sh"
echo "  3. leia o diff de .claude/skills/ antes de commitar"
