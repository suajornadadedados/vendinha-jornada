#!/usr/bin/env bash
#
# Zera o que uma demonstracao produziu, e SO isso.
#
#   bash scripts/limpar-demo.sh          # pergunta antes
#   bash scripts/limpar-demo.sh --sim    # nao pergunta (use em script)
#
# Existe porque testar o painel exige olhar uma tela vazia: KPI com dado velho de
# uma conversa de ontem esconde exatamente o comportamento que a S-07 quis provar —
# que ausencia aparece como traco e nunca como zero.
#
# O QUE APAGA: sessoes, turnos, vereditos, pedidos, itens, composicoes, eventos de
# pagamento, notas fiscais, aprovacoes, e o historico do checkpointer do LangGraph.
#
# O QUE PRESERVA, de proposito e por nome:
#   produto          — o catalogo, que custa `make seed` e uma chamada de embedding
#                      para reconstruir. Apagar aqui transformaria "limpar a demo"
#                      em "quebrar o agente", e a pessoa so descobriria na primeira
#                      pergunta do cliente.
#   instance_config  — o modelo escolhido e a credencial. Zerar isso mandaria o
#                      operador reconfigurar a cada teste.
#   checkpoint_migrations — controle de versao do schema, nao dado de conversa.
#
# O Qdrant tambem nao e tocado: a colecao dele e catalogo, nao conversa.
#
# NAO use isto fora de uma maquina de desenvolvimento. Nao ha confirmacao de
# ambiente aqui porque nao ha ambiente aqui: o compose deste repositorio sobe um
# Postgres local em 127.0.0.1:5433 e e contra ele que este script fala.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

TABELAS="turno veredito_de_composicao sessao item_do_pedido composicao_do_pedido \
evento_de_pagamento nota_fiscal aprovacao_de_nf pedido \
checkpoint_writes checkpoint_blobs checkpoints"

psql() { docker compose exec -T postgres psql -U vendinha -d vendinha -v ON_ERROR_STOP=1 "$@"; }

echo "Antes:"
psql -c "SELECT 'conversas' AS o_que, count(*) FROM sessao
   UNION ALL SELECT 'turnos', count(*) FROM turno
   UNION ALL SELECT 'vereditos', count(*) FROM veredito_de_composicao
   UNION ALL SELECT 'pedidos', count(*) FROM pedido
   UNION ALL SELECT 'notas', count(*) FROM nota_fiscal
   UNION ALL SELECT 'checkpoints', count(*) FROM checkpoints
   UNION ALL SELECT 'produtos (preservado)', count(*) FROM produto;"

if [ "${1:-}" != "--sim" ]; then
  # `read` de um terminal. Sem terminal (CI, pipe), aborta em vez de assumir sim.
  [ -t 0 ] || { echo "erro: sem terminal para confirmar. Use --sim se e isso mesmo." >&2; exit 1; }
  printf "\nApagar tudo acima, menos os produtos? [s/N] "
  read -r resposta
  case "$resposta" in
    s | S | sim | SIM) ;;
    *) echo "cancelado."; exit 0 ;;
  esac
fi

# TRUNCATE numa transacao so: ou some tudo, ou nao some nada. Um DELETE em cascata
# parcial deixaria turno orfao de sessao, que e um estado que o painel nao sabe
# desenhar — e que ninguem ia entender de onde veio.
# shellcheck disable=SC2086
psql -c "BEGIN; TRUNCATE TABLE $(echo $TABELAS | tr ' ' ',') RESTART IDENTITY CASCADE; COMMIT;"

echo
echo "Depois:"
psql -c "SELECT 'conversas' AS o_que, count(*) FROM sessao
   UNION ALL SELECT 'turnos', count(*) FROM turno
   UNION ALL SELECT 'vereditos', count(*) FROM veredito_de_composicao
   UNION ALL SELECT 'pedidos', count(*) FROM pedido
   UNION ALL SELECT 'notas', count(*) FROM nota_fiscal
   UNION ALL SELECT 'checkpoints', count(*) FROM checkpoints
   UNION ALL SELECT 'produtos (preservado)', count(*) FROM produto;"

echo
echo "Pronto. Recarregue o painel: os KPIs devem aparecer como traco, nunca como zero."
echo "O widget do cliente guarda o session_id em localStorage — limpe o storage da aba"
echo "da landing, ou abra uma janela anonima, para comecar uma conversa nova."
