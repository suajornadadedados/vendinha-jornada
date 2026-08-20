---
id: S-01
titulo: Discovery como código
status: aprovada
branch: spec/s-01-discovery
issue: 
adrs: [ADR-001, ADR-006]
riscos_cobertos: [R1, R7]
---

# S-01 — Discovery como código

## Objetivo
Os artefatos da discovery (requisitos, jornada, riscos, golden dataset inicial) entram no repo
por PR — requisitos rastreáveis antes de qualquer feature.

## Requisitos
- [ ] REQ-1 `docs/requisitos.md`, `docs/jornada.md`, `docs/riscos.md`, `docs/decisoes.md` e ADRs 001-008 revisados e definitivos.
- [ ] REQ-2 Schema dos casos de eval definido e validável por script (`make evals-check`): cada caso declara necessidade, critério de aprovação e produtos válidos.
- [ ] REQ-3 Golden dataset inicial: 12 conversas de referência em `evals/golden/` (JSON, com necessidade, resposta esperada em critérios, produtos válidos).
- [ ] REQ-4 Suite adversarial inicial: 6 casos de injection/abuso em `evals/adversarial/`.
- [ ] REQ-5 Catálogo seed: `data/catalogo/*.json` com ~50 produtos e atributos ricos (tipo, região, maturação, intensidade, harmonização, preço).

## Fora de escopo
Runner de evals (S-06); ingestão no Qdrant (S-03).

## Tasks
1. `docs(s-01): normative discovery docs and initial ADRs`
2. `eval(s-01): eval case schema with validation script`
3. `eval(s-01): golden dataset (12 cases) and adversarial suite (6 cases)`
4. `feat(s-01): catalog seed data (~50 products)`

## BDD
```gherkin
Cenário: rastreabilidade risco → verificação
  Dado a matriz de riscos R1-R9
  Quando leio qualquer linha
  Então ela aponta uma spec responsável e uma verificação automatizada

Cenário: casos de eval válidos
  Quando executo "make evals-check"
  Então o schema valida necessidade, critério de aprovação e produtos citados de cada caso sem erro
```

## Métricas de sucesso
| Métrica | Alvo | Como medir |
|---|---|---|
| Casos golden / adversariais | 12 / 6 | contagem em evals/ |
| Produtos no seed | ≥ 50, 100% com preço e ≥4 atributos | script de validação do seed |

## Verificação independente
- Rodar `make evals-check` e o validador do seed.
- Amostrar 3 casos golden e conferir que os produtos citados existem no seed.

## Definition of Done
- [ ] Checklist padrão do template
