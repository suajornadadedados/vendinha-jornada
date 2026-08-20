# Funcoes comuns aos scripts de manutencao das skills (ADR-009).
# Nao executar diretamente: e sourced pelos outros scripts.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK="$REPO_ROOT/.claude/skills.lock.json"
SKILLS_DIR="$REPO_ROOT/.claude/skills"

PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  echo "erro: python3 nao encontrado (necessario para ler o lockfile)" >&2
  exit 1
fi

die() { echo "erro: $*" >&2; exit 1; }

[ -f "$LOCK" ] || die "lockfile nao encontrado: $LOCK"

# Emite: nome<TAB>repo<TAB>path<TAB>sha  (uma linha por skill vendorizada)
lock_skills() {
  "$PY" "$REPO_ROOT/scripts/lock_query.py" "$LOCK" skills
}

# Emite: repo<TAB>sha  (uma linha por origem)
lock_sources() {
  "$PY" "$REPO_ROOT/scripts/lock_query.py" "$LOCK" sources
}

# Emite: repo<TAB>sha<TAB>path1 path2 ...  (uma linha por origem)
lock_repo_paths() {
  "$PY" "$REPO_ROOT/scripts/lock_query.py" "$LOCK" repo-paths
}

# Emite os nomes das skills proprias (nao vendorizadas)
lock_own() {
  "$PY" "$REPO_ROOT/scripts/lock_query.py" "$LOCK" own
}

# Materializa um repo num diretorio, no SHA exato, trazendo apenas os paths
# pedidos. Partial clone (--filter=blob:none) + sparse-checkout: sem isso, uma
# skill hospedada num monorepo (shadcn-ui/ui) baixaria o repositorio inteiro a
# cada rodada do CI.
clone_sparse() {
  local repo="$1" sha="$2" dest="$3"
  shift 3
  local paths=("$@")

  git init -q "$dest"
  git -C "$dest" remote add origin "https://github.com/$repo.git"
  git -C "$dest" sparse-checkout init --no-cone
  git -C "$dest" sparse-checkout set --no-cone "${paths[@]}"

  if ! git -C "$dest" fetch -q --depth 1 --filter=blob:none origin "$sha" 2>/dev/null; then
    # Servidor nao permite fetch por SHA: cai para buscar todas as refs.
    git -C "$dest" fetch -q --filter=blob:none origin
  else
    git -C "$dest" checkout -q FETCH_HEAD
    return 0
  fi
  git -C "$dest" checkout -q "$sha"
}
