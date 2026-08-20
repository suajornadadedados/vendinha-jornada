---
id: S-02
titulo: Agente base observável
status: aprovada
branch: spec/s-02-agente-observavel
issue: 
adrs: [ADR-007]
riscos_cobertos: [R5, R6, R9]
---

# S-02 — Agente base observável

## Objetivo
O menor agente possível — porém com observabilidade, privacidade e limites de custo desde o
primeiro trace. Observabilidade no commit 1, não no incidente 1.

## Requisitos
- [ ] REQ-1 FastAPI com `POST /chat` (SSE) e sessões; grafo LangGraph mínimo (um nó de conversa).
- [ ] REQ-2 Checkpointer em Postgres; estado carrega apenas IDs (pointer-not-payload).
- [ ] REQ-3 Langfuse Cloud instrumentado (`LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`,
      `LANGFUSE_SECRET_KEY`): trace por sessão com tools, custo, latência. Indisponibilidade
      do Langfuse não pode propagar exceção para o atendimento (ADR-010).
- [ ] REQ-4 Mascaramento de PII (CPF, e-mail, nome) na camada de instrumentação **antes** do envio.
      Com Langfuse Cloud o trace sai da infra, então este REQ é invariante de release: sem o
      teste de redação verde, a spec não fecha (ADR-010, R5).
- [ ] REQ-5 Budget cap por sessão e timeout por tool via config; exceder = resposta honesta de limite.

## Fora de escopo
RAG, subagents, tools de negócio.

## Tasks
1. `feat(s-02): fastapi chat endpoint with sse and session handling`
2. `feat(s-02): minimal langgraph graph with postgres checkpointer`
3. `feat(s-02): langfuse instrumentation with pii masking`
4. `feat(s-02): session budget cap and per-tool timeout`

## BDD
```gherkin
Cenário: PII nunca aparece em trace
  Dado uma conversa em que o cliente informa um CPF de teste
  Quando inspeciono o trace da sessão no Langfuse
  Então o CPF aparece mascarado e nunca em texto claro

Cenário: retomada de sessão
  Dado uma conversa interrompida após 3 turnos
  Quando o cliente retorna com o mesmo session_id
  Então o grafo retoma do checkpoint sem perda de contexto
```

## Métricas de sucesso
| Métrica | Alvo | Como medir |
|---|---|---|
| Sessões com trace completo | 100% | Langfuse |
| PII em claro em traces/logs | 0 ocorrências | teste automatizado de redação |
| p95 primeiro token | ≤ 3s | métrica no trace |

## Verificação independente
- Enviar CPF/e-mail de teste e auditar o trace bruto.
- Forçar estouro de budget e verificar a degradação honesta.

## Definition of Done
- [ ] Checklist padrão do template
