# Skills do harness

> Gerado por `scripts/gen-skills-doc.sh` a partir de `.claude/skills.lock.json`.
> Nao edite este arquivo a mao. Decisao: ADR-009.

As skills sao **vendorizadas**: copiadas para `.claude/skills/` e versionadas.
Quem clona o repositorio recebe o harness junto com o codigo — e o que torna o setup
reproduzivel (docs/requisitos.md) e a condicao para o padrao autor/revisor do ADR-005
valer, ja que autor e revisor precisam rodar com exatamente as mesmas skills.

## Origens fixadas

| Repositorio | SHA |
|---|---|
| [mattpocock/skills](https://github.com/mattpocock/skills) | `8b36d4fb2635` |
| [langchain-ai/langchain-skills](https://github.com/langchain-ai/langchain-skills) | `f3ea282efb82` |
| [langfuse/skills](https://github.com/langfuse/skills) | `9cee84e588ec` |
| [shadcn-ui/ui](https://github.com/shadcn-ui/ui) | `b1c580c637f4` |

## Skills instaladas (23)

### mattpocock/skills

| Skill | Por que esta aqui |
|---|---|
| `tdd` | S-02..S-06 — red-green-refactor nos seams; teste antes do codigo de agente |
| `code-review` | complementa /verificar-spec no eixo padroes (o ritual cobre conformidade com a spec) |
| `codebase-design` | S-04 — modulos profundos: a fronteira de permissao precisa de interface estreita |
| `diagnosing-bugs` | loop disciplinado em bug nao-deterministico de agente (o pior tipo) |
| `grill-with-docs` | S-01 — entrevista que endurece a spec ANTES de virar codigo |
| `grill-me` | questionar plano de spec antes de aprovar |
| `grilling` | primitivo de entrevista usado por grill-me e grill-with-docs |
| `domain-modeling` | vocabulario unico: pedido, nota, aprovacao, sessao — evita sinonimos no codigo |
| `writing-for-agents` | meta-skill: escrever specs e ADRs que agentes leem sem ambiguidade |
| `research` | Q1 do PRD — spike do emissor de NF contra fontes primarias |
| `resolving-merge-conflicts` | resolucao por intencao; specs em paralelo tocam docs comuns |
| `handoff` | sessao por spec: compactar contexto ao trocar de sessao sem perder decisoes |

### langchain-ai/langchain-skills

| Skill | Por que esta aqui |
|---|---|
| `ecosystem-primer` | LangChain vs LangGraph vs Deep Agents — escolha registrada em ADR |
| `langgraph-fundamentals` | S-02 — StateGraph, nodes, edges, reducers |
| `langgraph-persistence` | RNF-6 e R9 — checkpointer Postgres, pointer-not-payload, retomada de sessao |
| `langgraph-human-in-the-loop` | S-05 e R3 — interrupt/resume; nucleo do requisito de aprovacao humana no irreversivel |
| `langchain-fundamentals` | tools tipadas e structured output nas fronteiras |
| `langchain-middleware` | S-04 — aprovacao e allowlist como middleware, nao como prompt |
| `langchain-rag` | S-03 e R1 — grounding sobre Qdrant; fato inventado reprova a suite de evals |
| `langchain-dependencies` | matriz de versoes; evita import inventado pelo modelo |
| `eval-engineering` | S-06 e R7 — construir e auditar evals; criterio de aprovacao declarado por caso |

### langfuse/skills

| Skill | Por que esta aqui |
|---|---|
| `langfuse` | S-02, R5, RF-5 — traces, datasets, scores e mascaramento de PII via API |

### shadcn-ui/ui

| Skill | Por que esta aqui |
|---|---|
| `shadcn` | S-07 — componentes acessiveis via CLI oficial em vez de JSX inventado |

## Skill propria

| Skill | Papel |
|---|---|
| `vendinha-harness` | Roteia spec -> skills e declara a precedencia dos normativos do projeto sobre skills de terceiros. Nao e vendorizada: e o codigo-fonte do harness. |

## Rejeitadas (e por que)

A lista do que foi recusado diz mais sobre o criterio do que a lista do que foi aceito.

| Candidata | Origem | Motivo da recusa |
|---|---|---|
| ask-matt, triage, to-tickets, wayfinder, implement, setup-matt-pocock-skills | mattpocock/skills | pressupoem issue tracker e fluxo de tickets proprio, que compete com o SDD do ADR-005 (spec -> branch -> PR). Duas fontes de verdade sobre 'o que fazer agora' levam o agente a escolher a errada. |
| *-quickstart (6 skills) | langchain-ai/langchain-skills | tutoriais hello-world; o repositorio ja tem specs como ponto de partida |
| deep-agents-*, managed-deep-agents, swarm, langgraph-cli, langsmith-online-eval-engineering | langchain-ai/langchain-skills | fora da stack decidida (LangGraph auto-hospedado + Langfuse). LangSmith conflita com ADR-007. |
| ui-ux-pro-max, frontend-slides | plugins locais | contem CLI e assets binarios (16 MB). ADR-009: vendoriza-se markdown, nao se vendoriza software. Permanecem como plugin e sao roteadas pela skill vendinha-harness. |
| migrate-radix-to-base | shadcn-ui/ui | migracao de codebase existente; o frontend da S-07 nasce do zero |

## Manutencao

```bash
bash scripts/vendor-skills.sh    # materializa .claude/skills/ a partir do lock
bash scripts/pin-skills.sh       # atualiza os SHAs de origem para o HEAD atual
bash scripts/gen-skills-doc.sh   # regenera este documento
```

`.claude/skills/` e **derivado**. Editar uma skill vendorizada a mao faz o job
`skills-drift` do CI reprovar o PR. Para adaptar comportamento ao projeto, edite
`.claude/skills/vendinha-harness/SKILL.md` — nunca a skill de terceiro.

