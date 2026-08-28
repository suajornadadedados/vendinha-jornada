#!/usr/bin/env bash
#
# O portao de evals do CI — a camada 1 do ADR-014.
#
#   bash scripts/evals-ci.sh              # decide o escopo pelo diff contra a main
#   bash scripts/evals-ci.sh --tudo       # a suite inteira (camada 2, pos-merge)
#   bash scripts/evals-ci.sh --diff-de HEAD~3   # confere o mapa num diff qualquer
#
# ESTE SCRIPT SEMPRE SAI 0 OU 1. Nunca deixa o job pulado, e a razao esta escrita
# no ADR-014: um job pulado que e *required* trava a main para sempre. Por isso a
# decisao de "nao ha nada a avaliar neste diff" mora AQUI DENTRO, e nunca num
# `if:` de path filter la no workflow. O ci.yml ja resolveu a metade analoga desse
# problema com o job `detect` (S-00, D-10); esta e a outra metade.
#
# Quem decide o escopo e `vendinha.evals.afetadas`, em Python e com teste
# unitario (tests/unit/test_evals_afetadas.py) — um `case` de shell nao teria
# como ser exercitado pelo pytest, e o ADR-014 exige que o mapa seja testado.
#
# O veredito e o exit code do runner, nunca um limiar de score. O Langfuse e
# visor: se ele estiver fora do ar a suite roda igual (ADR-010, ADR-014).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

BASE="${EVALS_BASE_REF:-origin/main}"
TUDO=0

while [ $# -gt 0 ]; do
  case "$1" in
    --tudo) TUDO=1 ;;
    --diff-de) BASE="$2"; shift ;;
    *) echo "uso: $0 [--tudo] [--diff-de <ref>]" >&2; exit 1 ;;
  esac
  shift
done

# `uv run --project backend`, e nao um python qualquer do PATH: `afetadas` vive
# dentro do pacote `vendinha`, e um interpretador que nao o enxerga falharia com
# ImportError DEPOIS de o job ja ter subido — parecendo problema de codigo em vez
# de problema de ambiente. E a mesma forma que o Makefile usa.
py() { uv run --project backend python "$@"; }

# ---------------------------------------------------------------- que escopo

MAPA_FALHOU=0

if [ "$TUDO" -eq 1 ]; then
  SUITES="$(py -m vendinha.evals.afetadas --todas)" || MAPA_FALHOU=1
  ORIGEM="a suite inteira (camada 2)"
elif ! git rev-parse --verify --quiet "$BASE" >/dev/null; then
  # Sem a base nao da para saber o que mudou, e adivinhar aqui seria escolher
  # entre rodar de menos (buraco no portao) e travar o PR. Roda tudo: e o mesmo
  # lado para o qual a regra do nao-mapeado erra.
  echo "AVISO: nao consegui resolver '$BASE'; assumindo a suite inteira." >&2
  SUITES="$(py -m vendinha.evals.afetadas --todas)" || MAPA_FALHOU=1
  ORIGEM="a suite inteira (base '$BASE' indisponivel)"
else
  # `--diff-filter=d` tira os arquivos APAGADOS. Um arquivo removido nao pode ter
  # mudado o comportamento do agente, e sem o filtro ele cairia em "nao mapeado"
  # depois que o mapa deixasse de o conhecer — encarecendo todo PR que faz
  # limpeza, pelo motivo errado.
  ARQUIVOS="$(git diff --name-only --diff-filter=d "$(git merge-base "$BASE" HEAD)"...HEAD)"
  SUITES="$(printf '%s\n' "$ARQUIVOS" | py -m vendinha.evals.afetadas)" || MAPA_FALHOU=1
  ORIGEM="as sub-suites afetadas pelo diff contra $BASE"
fi

# **Mapa que nao rodou nao e mapa que disse "nada".** Sem esta checagem, um
# ImportError ou um uv ausente deixariam SUITES vazia e o script sairia 0 dizendo
# "nada a avaliar neste diff" — portao verde por nao ter conseguido rodar, que e o
# modo de falha silencioso que o ADR-014 recusa. Aconteceu de verdade na primeira
# versao deste script, no Git Bash do Windows.
if [ "$MAPA_FALHOU" -ne 0 ]; then
  echo "erro: nao consegui decidir o escopo — o mapa de sub-suites nao rodou." >&2
  echo "Confira 'uv run --project backend python -m vendinha.evals.afetadas --todas'." >&2
  exit 1
fi

# --------------------------------------------------- nada a avaliar: sai VERDE

if [ -z "${SUITES// /}" ]; then
  echo "nada a avaliar neste diff: nenhum arquivo tocado pode ter mudado o agente."
  {
    echo "## Evals — nada a avaliar neste diff"
    echo
    echo "Nenhum arquivo deste PR pode ter mudado o comportamento do agente, entao"
    echo "nenhuma sub-suite rodou. O check e **verde**, e nao pulado: job pulado que"
    echo "e required trava a \`main\` para sempre (ADR-014)."
    echo
    echo "A camada 0 — schema do corpus e \`tests/security\` — rodou nos jobs \`test\`"
    echo "e continua sendo a verificacao que **nenhum** PR escapa."
  } >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
  exit 0
fi

echo "vao rodar: $SUITES  ($ORIGEM)"

# ----------------------------------------------- a infraestrutura que a regua pede

# So agora, e nao no topo: subir Postgres, Qdrant e semear o catalogo leva minutos,
# e um PR que so mexe em docs/ ja saiu la em cima sem pagar nada disso.
docker compose up -d --wait || { echo "erro: docker compose nao subiu" >&2; exit 1; }
(cd backend && uv run python -m vendinha.db) || exit 1
(cd backend && uv run python -m vendinha.ingest) || exit 1

# ------------------------------------------------------------------- rodar

RELATORIOS="$(mktemp -d)"
FALHOU=0

for SPEC in $SUITES; do
  echo "::group::evals $SPEC"
  (cd backend && uv run python -m vendinha.evals.runner \
      --spec "$SPEC" --saida "$RELATORIOS/$SPEC.md") || FALHOU=1
  echo "::endgroup::"
done

# O relatorio inteiro no resumo do job, e nao so o veredito: quem abre um check
# vermelho precisa ver QUAL caso reprovou e por que, sem baixar artefato nenhum.
{
  echo "## Evals — $ORIGEM"
  echo
  for SPEC in $SUITES; do
    [ -f "$RELATORIOS/$SPEC.md" ] || continue
    cat "$RELATORIOS/$SPEC.md"
    echo
  done
} >> "${GITHUB_STEP_SUMMARY:-/dev/null}"

if [ "$FALHOU" -ne 0 ]; then
  echo
  echo "REPROVADO. Um caso de eval reprovou — o relatorio acima diz qual e por que."
  echo
  echo "Nao conserte editando o caso: evals/ e protegido por CODEOWNERS exatamente"
  echo "porque um PR com eval vermelho nao pode ficar verde mexendo na regua"
  echo "(ADR-006). Se o caso estiver errado, isso e uma decisao do PO e um commit"
  echo "separado, visivel no diff."
  exit 1
fi

echo "APROVADO. Todas as sub-suites afetadas passaram."
exit 0
