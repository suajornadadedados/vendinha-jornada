# Mapa de decisões (D1-D18) → ADRs

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
| D11 | Como ir pra produção? | Um ambiente único, sem denominação: Compose com api, frontend e nginx; deploy manual pelo runbook | ADR-008 |
| D12 | Como o harness chega em quem clona? | Skills vendorizadas no repo, origem fixada por SHA em `.claude/skills.lock.json` | ADR-009 |
| D13 | Onde a observabilidade é hospedada? | Langfuse Cloud; o mascaramento na origem é o que torna a nuvem aceitável | ADR-010 |
| D14 | Quantas camadas de teste automatizado existem? | Duas, e só duas: `unit` (a conta está certa?) e `security` (a ação proibida é alcançável?) | ADR-011 |
| D15 | De quem é a escolha do modelo, e onde mora a chave? | Provedor agnóstico (`init_chat_model`); modelo escolhido de allowlist do servidor; credencial cifrada no banco, editável em runtime | ADR-012 |
| D16 | Para quem a loja vende, e quem monta a composição? | Empresas montando eventos; o modelo propõe a composição e o código valida orçamento, slots e restrições | ADR-013 |
| D17 | Quando o portão de evals roda, e sobre o quê? | Em camadas: determinística sempre, sub-suítes afetadas pelo diff no PR, suíte inteira no pós-merge; Langfuse é visor, não portão | ADR-014 |
| D18 | O cliente enxerga o agente por onde? | Painel de observação próprio, read-only, com custo em `Decimal` no backend; o Langfuse fica como visor interno | ADR-015 |
