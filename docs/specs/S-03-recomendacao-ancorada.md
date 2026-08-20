---
id: S-03
titulo: Recomendação ancorada (RAG)
status: aprovada
branch: spec/s-03-recomendacao
issue: 
adrs: [ADR-001, ADR-002]
riscos_cobertos: [R1]
---

# S-03 — Recomendação ancorada

## Objetivo
O modelo conversa; o catálogo afirma. Subagent de recomendação com tools read-only sobre
Qdrant e banco, e o primeiro eval de groundedness pegando alucinação.

## Requisitos
- [ ] REQ-1 Ingestão do seed no Qdrant (embeddings + payload estruturado para filtros).
- [ ] REQ-2 Tools read-only: `buscar_produtos` (semântica+filtros), `detalhar_produto`, `consultar_preco` (Postgres).
- [ ] REQ-3 Subagent `recomendacao` registrado com exclusivamente tools read-only.
- [ ] REQ-4 Prompt proíbe afirmar fato sem origem em tool; preço citado = preço retornado por `consultar_preco`.
- [ ] REQ-5 Eval de groundedness executável localmente (`make evals-groundedness`) sobre 6 casos golden.

## Fora de escopo
Checkout, supervisor completo (roteamento binário simples é suficiente aqui).

## Tasks
1. `feat(s-03): catalog ingestion into qdrant with structured payload`
2. `feat(s-03): read-only recommendation tools`
3. `feat(s-03): recommendation subagent with grounding prompt`
4. `eval(s-03): groundedness eval runnable locally`

## BDD
```gherkin
Cenário: necessidade implícita vira recomendação ancorada
  Dado o catálogo ingerido
  Quando o cliente pede "um presente pra minha sogra que ama vinho tinto"
  Então a resposta recomenda somente produtos existentes, com preços idênticos ao banco

Cenário: alucinação plantada é detectada
  Dado um caso de eval com resposta que inventa um atributo
  Quando executo o eval de groundedness
  Então o caso reprova e o relatório aponta o atributo sem origem no catálogo
```

## Métricas de sucesso
| Métrica | Alvo | Como medir |
|---|---|---|
| Fatos sem origem em tool nos 6 casos | 0 (uma ocorrência reprova) | eval local |
| Divergência de preço citado vs banco | 0 | assert no eval |

## Verificação independente
- Rodar o eval; tentar 3 conversas livres buscando induzir atributo inventado; auditar traces.
- Confirmar no registro de subagents que `recomendacao` não possui tool de escrita.

## Definition of Done
- [ ] Checklist padrão do template
