# ADR-007 — Observabilidade desde o commit 1, com PII mascarada

- Status: aceito · Data: 2026-08-03 · Decisão: D10 · Riscos: R5, R6
- Atualizado pelo ADR-010 **apenas quanto à hospedagem** (Langfuse Cloud em vez de
  self-hosted). O mascaramento de PII na origem, decidido aqui, permanece vigente — e é
  pré-condição daquela decisão.

## Contexto
Sem traces, depurar agente é adivinhação. Mas traces ingênuos vazam CPF/e-mail (LGPD).

## Decisão
Langfuse instrumentado na S-02 (antes de qualquer feature): traces de sessão com roteamento,
tools, custo e latência; mascaramento de PII na camada de instrumentação; budget cap por
sessão e timeout por tool configuráveis; resultados dos evals anexados aos traces.

## Consequências
+ Depuração e custo visíveis desde o início; conformidade LGPD by design.
− Instrumentação como pré-requisito atrasa a primeira feature em ~meia spec (aceito).
