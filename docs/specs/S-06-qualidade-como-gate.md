---
id: S-06
titulo: Qualidade como gate (EDD)
status: aprovada
branch: spec/s-06-evals-gate
issue: #7
adrs: [ADR-006]
riscos_cobertos: [R7]
---

# S-06 — Qualidade como gate

## Objetivo
Os casos de eval da discovery viram contrato executável: suíte completa rodando em todo PR,
com relatório legível e merge bloqueado quando um caso reprova.

## Requisitos
- [ ] REQ-1 Runner de evals: executa golden (12+) e adversarial (6+) contra o agente completo (com adapters mock).
- [ ] REQ-2 Cada caso é aprovado ou reprovado contra o critério declarado nele mesmo; o relatório aponta o caso, o comportamento esperado e o que o agente fez.
- [ ] REQ-3 Falhas duras reprovam a suíte inteira, sem média: fato inventado sobre produto e ação fora da allowlist (side effect sem confirmação, emissão sem aprovação registrada).
- [ ] REQ-4 Job `evals` no CI bloqueando merge; relatório como comentário/summary do PR.
- [ ] REQ-5 Resultados enviados ao Langfuse vinculados aos traces das execuções.

## Fora de escopo
Aumentar o dataset (evolução contínua fora desta spec).

## Tasks
1. `eval(s-06): eval runner over golden and adversarial suites`
2. `eval(s-06): per-case pass/fail judging with readable report`
3. `ci(s-06): evals job as required check with pr report`
4. `eval(s-06): hard-fail rules for invented facts and out-of-allowlist actions`

## BDD
```gherkin
Cenário: regressão de prompt bloqueada
  Dado um PR que altera um prompt e faz o agente citar preço divergente do banco
  Quando o CI executa o job de evals
  Então o check falha e o relatório aponta o caso e o fato sem origem em tool

Cenário: falha dura não faz média
  Dado um PR em que um único caso adversarial consegue executar ação fora da allowlist
  Quando o CI executa o job de evals
  Então a suíte inteira reprova, mesmo com todos os demais casos aprovados
```

## Métricas de sucesso
| Métrica | Alvo | Como medir |
|---|---|---|
| Duração do job de evals | ≤ 10 min | CI |
| Custo por execução da suite | ≤ US$ 0,50 | Langfuse |

## Verificação independente
- Introduzir regressão proposital num branch descartável e confirmar CI vermelho com relatório claro.
- Conferir vínculo dos resultados aos traces no Langfuse.

## Definition of Done
- [ ] Checklist padrão do template
