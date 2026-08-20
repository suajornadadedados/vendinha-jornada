#!/usr/bin/env bash
#
# Roda a suite de testes (tests/unit e tests/security) e decide o que fazer
# quando ela esta vazia.
#
#   bash scripts/run-tests.sh            # tudo
#   bash scripts/run-tests.sh tests/unit # so uma camada
#
# Por que este wrapper existe: o pytest sai com codigo 5 quando nao coleta
# nenhum teste. Tratar isso como sucesso em silencio seria exatamente o tipo de
# check decorativo que este repositorio recusa; tratar como falha deixaria o CI
# vermelho de forma permanente antes da S-02, e check vermelho permanente treina
# a ignorar CI vermelho.
#
# A regra: suite vazia e ACEITAVEL enquanto backend/ nao existe, e e FALHA
# depois que ele existe — porque a partir dai toda feature nasce com teste
# (docs/testes.md, secao 3).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PY="$(command -v python3 || command -v python || true)"
[ -n "$PY" ] || { echo "erro: python nao encontrado" >&2; exit 1; }

TARGET=("${@:-tests}")

"$PY" -m pytest "${TARGET[@]}"
STATUS=$?

if [ "$STATUS" -ne 5 ]; then
  exit "$STATUS"
fi

echo
if [ -d "$REPO_ROOT/backend" ]; then
  echo "FALHA: nenhum teste coletado, e backend/ ja existe."
  echo
  echo "docs/testes.md, secao 3: toda feature nova nasce com teste unitario, e"
  echo "toda spec que declara riscos_cobertos entrega os testes da tabela."
  echo "Suite vazia com codigo de produto no repositorio nao e um estado valido."
  exit 1
fi

echo "AVISO: nenhum teste coletado em ${TARGET[*]}."
echo "Esperado por enquanto — backend/ ainda nao existe (entregavel da S-00)."
echo "A partir do momento em que backend/ existir, suite vazia passa a reprovar."
exit 0
