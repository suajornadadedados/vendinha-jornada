#!/usr/bin/env bash
#
# Materializa .claude/skills/ a partir de .claude/skills.lock.json (ADR-009).
#
#   bash scripts/vendor-skills.sh            # (re)materializa as skills vendorizadas
#   bash scripts/vendor-skills.sh --check    # nao escreve nada; sai != 0 se houver drift
#
# .claude/skills/ e DERIVADO. Editar uma skill vendorizada a mao faz o job
# skills-drift do CI reprovar o PR. Para adaptar comportamento ao projeto,
# edite .claude/skills/vendinha-harness/SKILL.md.

source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

CHECK=0
[ "${1:-}" = "--check" ] && CHECK=1

STAGE="$(mktemp -d)"
CLONES="$(mktemp -d)"
trap 'rm -rf "$STAGE" "$CLONES"' EXIT

echo "==> clonando as origens fixadas"
while IFS=$'\t' read -r repo sha paths; do
  [ -n "$repo" ] || continue
  echo "    $repo @ ${sha:0:12}"
  # shellcheck disable=SC2086 -- paths e uma lista separada por espaco, de proposito
  clone_sparse "$repo" "$sha" "$CLONES/${repo//\//_}" $paths
done < <(lock_repo_paths)

echo "==> montando a arvore esperada"
while IFS=$'\t' read -r name repo path sha; do
  [ -n "$name" ] || continue
  src="$CLONES/${repo//\//_}/$path"
  [ -d "$src" ] || die "path nao existe em $repo@${sha:0:12}: $path"

  dest="$STAGE/$name"
  mkdir -p "$dest"
  cp -R "$src/." "$dest/"

  # O rodape marca a origem e vive apenas no SKILL.md — mesma regra para todas.
  skill_md="$dest/SKILL.md"
  [ -f "$skill_md" ] || die "skill $name nao tem SKILL.md em $path"
  printf '\n<!-- vendored-from: %s@%s path=%s | ADR-009: nao edite; altere skills.lock.json -->\n' \
    "$repo" "$sha" "$path" >> "$skill_md"
done < <(lock_skills)

# As skills proprias nao sao derivadas do lockfile: preserva como estao.
while read -r own; do
  [ -n "$own" ] || continue
  [ -d "$SKILLS_DIR/$own" ] && cp -R "$SKILLS_DIR/$own" "$STAGE/$own"
done < <(lock_own)

if [ "$CHECK" = "1" ]; then
  echo "==> comparando com .claude/skills/"
  if diff -r -q "$STAGE" "$SKILLS_DIR" >/dev/null 2>&1; then
    echo "OK: .claude/skills/ bate com o lockfile."
    exit 0
  fi
  echo
  echo "DRIFT entre o lockfile e .claude/skills/:"
  diff -r "$STAGE" "$SKILLS_DIR" || true
  echo
  echo "Uma skill vendorizada foi editada a mao, ou o lockfile mudou sem"
  echo "rematerializar. Rode: bash scripts/vendor-skills.sh"
  echo "Para adaptar comportamento ao projeto, edite a skill vendinha-harness."
  exit 1
fi

echo "==> substituindo .claude/skills/"
rm -rf "$SKILLS_DIR"
cp -R "$STAGE" "$SKILLS_DIR"
echo "OK: $(find "$SKILLS_DIR" -mindepth 1 -maxdepth 1 -type d | wc -l) skills materializadas."
echo "Lembre de rodar: bash scripts/gen-skills-doc.sh"
