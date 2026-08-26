# ADR-003 — HITL por interrupt nativo antes da emissão de NF

- Status: aceito · Data: 2026-08-03 · Decisão: D5 · Risco: R3
- Atualizado pelo ADR-011 **apenas quanto à camada de teste**: a invariante abaixo é provada em
  `tests/security/test_hitl_invariant.py`, não em uma camada de integração — que não existe neste
  repositório (`docs/testes.md` §1). A decisão em si permanece vigente e inalterada.

## Contexto
Emitir NF é irreversível e tem consequência fiscal. Critério: reversibilidade × impacto.
Pagamento é confirmado pelo próprio cliente; NF exige supervisão da operação.

## Alternativas consideradas
1. **Confirmação no próprio chat** — o mesmo canal sujeito a injection aprovaria o side effect.
2. **Nenhum HITL, só logs** — auditoria post-mortem não desfaz nota emitida.
3. **Interrupt do LangGraph + fila do operador** — o grafo pausa com estado persistido
   (checkpointer Postgres); aprovação registrada (quem/quando) retoma o fluxo.

## Decisão
Opção 3. Invariante testada em integração: nenhum caminho emite NF sem aprovação registrada.

## Consequências
+ Garantia estrutural; demo pedagógica clara; trilha de auditoria.
− Latência entre pagamento e NF (aceita e comunicada ao cliente no chat).
