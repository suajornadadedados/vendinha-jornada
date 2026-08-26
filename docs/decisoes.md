# Mapa de decisões (D1-D14) → ADRs

| Decisão | Pergunta | Resposta adotada | ADR |
|---|---|---|---|
| D1 | Isso precisa de IA? Onde? | Só nas etapas conversacionais/semânticas (docs/jornada.md) | ADR-001 |
| D2 | O que é qualidade aqui? | Definida na discovery como casos de eval versionados, não como teste manual | ADR-006 |
| D3 | Como o modelo acessa fatos? | Nunca de memória: tools RAG (Qdrant) e banco | ADR-001 |
| D4 | Onde passa a fronteira de permissão? | Supervisor + subagents; registro explícito e testado | ADR-002 |
| D5 | Quando um humano entra no loop? | Reversibilidade × impacto: NF = interrupt + operador | ADR-003 |
| D6 | Como integrar com o mundo externo? | Ports & adapters, mock-first | ADR-004 |
| D7 | Como API e frontend conversam? | Contratos Pydantic + OpenAPI → cliente TS; SSE; webhook idempotente | ADR-004 |
| D8 | Como saber que funciona — e continua? | Unit → security → evals como gate (EDD) | ADR-006 |
| D9 | Como o time trabalha? | SDD: branch por spec, conventional commits, PR com evidência, autor/revisor | ADR-005 |
| D10 | Como enxergar produção? | Langfuse desde o commit 1, PII mascarada | ADR-007 |
| D11 | Como ir pra produção? | Docker + VPS, DEV/PROD isolados, CD com aprovação manual | ADR-008 |
| D12 | Como o harness chega em quem clona? | Skills vendorizadas no repo, origem fixada por SHA em `.claude/skills.lock.json` | ADR-009 |
| D13 | Onde a observabilidade é hospedada? | Langfuse Cloud; o mascaramento na origem é o que torna a nuvem aceitável | ADR-010 |
| D14 | Quantas camadas de teste automatizado existem? | Duas, e só duas: `unit` (a conta está certa?) e `security` (a ação proibida é alcançável?) | ADR-011 |
