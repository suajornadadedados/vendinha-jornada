---
id: S-06
titulo: Qualidade como gate (EDD)
status: rascunho
branch: spec/s-06-evals-gate
issue: #7
adrs: [ADR-006, ADR-014]
riscos_cobertos: [R7]
---

# S-06 — Qualidade como gate

> **Reescrita em 2026-08-28, e por isso volta a `rascunho`.** A versão anterior foi escrita em
> 26/08, antes de S-03, S-11, S-04 e S-05 rodarem. Duas das suas quatro tasks já estavam entregues,
> e faltavam três trabalhos que ninguém tinha visto. O que mudou está em
> `docs/harness/medicao-de-evals.md` (a medição) e no **ADR-014** (as decisões). Precisa de
> aprovação do PO antes de virar código.

## Objetivo
Os casos de eval da discovery viram contrato executável: o portão roda em todo PR — a camada certa
para cada diff —, o relatório é legível, o merge trava quando um caso reprova, e as execuções são
comparáveis no Langfuse.

## O que a Fase 0 já entregou, e esta spec não repete

`chore/harness-medicao-de-evals` fechou o que a spec antiga chamava de REQ-2 e REQ-3, mais o que a
medição exigiu para ser possível:

| Já feito | Onde |
|---|---|
| pass/fail por caso, sem nota, com relatório legível | S-03/S-04 |
| falha dura derrubando a suíte | S-03/S-04 |
| custo por faixa de preço no relatório | `evals/gasto.py` |
| régua pinada — snapshot datado, juiz cross-provider | `config.py` |
| juiz que não rodou deixa de aprovar o caso | `evals/runner.py` |
| a suíte roda alguns casos de cada vez | `em_paralelo` |
| o relatório diz com que agente e juiz rodou | `evals/runner.py` |

## Requisitos

- [ ] **REQ-1 O juiz ganha um terceiro estado.** `nao_aplicavel`, ao lado de atende/não atende.
      Critério condicional cuja condição não ocorreu não foi violado, e **uma exceção escrita no
      prompt não resolveu** — o juiz continuou lendo a condição como obrigação. Não conta como
      aprovação nem como falha: sai do cálculo daquele caso. Não colide com o ADR-006 — continua
      sendo veredito por critério, sem nota e sem dimensão.
- [ ] **REQ-2 `temperature` vira configuração explícita do produto**, e o eval a herda. Duas
      execuções da S-03 com código idêntico discordaram (`golden-005`: 5 critérios em falha, depois
      2). Portão que vira entre execuções produz vermelho intermitente. O ADR-006 proíbe n-de-k, e
      o ADR-014 decide: a variância se ataca na configuração. **Medir o efeito**, não supô-lo.
- [ ] **REQ-3 A lane de recomendação passa a usar as tools que tem.** Quatro das seis reprovações
      da S-03 são conduta, e todas com a mesma forma: perguntar em vez de buscar (`golden-005`,
      `golden-016`), e buscar com `apenas_disponiveis` no default quando a descrição do parâmetro
      manda o contrário (`golden-006`, `golden-013`). Aceite: as seis da S-03 fechando.
- [ ] **REQ-4 O runner executa a suíte inteira — as cinco sub-suítes, 23 casos.** Inclui os quatro
      `spec: S-05`, hoje recusados por terem turno `de: operador` (DESC-5 da S-05): a conversa passa
      a ser percorrida **na ordem**, e o turno do operador vira decisão no port `fiscal`. Exige
      `cenario: pedido_pago` declarado em `golden-004` e `golden-011`, e um `nota_emitida` novo no
      schema para o `golden-012`.
- [ ] **REQ-5 Gate em camadas, como o ADR-014 o define.** `scripts/evals-ci.sh` decide o escopo
      pelo diff; mapa `código → sub-suíte` versionado, com **arquivo não mapeado ⇒ roda tudo**; job
      `evals` como required check; suíte inteira no pós-merge. Relatório no
      `$GITHUB_STEP_SUMMARY`.
- [ ] **REQ-6 Langfuse como visor.** Dataset run por execução, trace por caso, **score booleano**
      por caso. Sincronização de mão única `evals/` → Langfuse. Instrumentado pelo cliente do
      projeto (`observability.client()`), em `environment=evals`. Langfuse fora do ar não reprova a
      suíte (ADR-010).

## Fora de escopo

Aumentar o dataset — evolução contínua, fora desta spec. **Prompt caching**: a medição provou que a
alavanca existe (prefixo de 6.655 e 8.864 tokens contra o mínimo de 4.096 do Haiku 4.5, sobre uma
conta que é 98,8% entrada), mas ligá-la mexe em produção e é decisão própria, não subproduto do
portão.

## A frase que governa a spec

> O portão que não roda não protege, e o portão que sempre roda ensina a ser ignorado.

As três camadas do ADR-014 são a tentativa de ficar entre as duas. E a régua tem de ser confiável
**antes** de ser obrigatória: um caso que vira entre execuções, ou um juiz que reprova o que não
foi violado, produzem vermelho que ninguém acredita — e vermelho em que ninguém acredita é como se
desaprende a olhar para o CI.

## Tasks

1. `eval(s-06): third verdict state for criteria that do not apply`
2. `eval(s-06): explicit temperature so the ruler stops moving between runs`
3. `fix(s-06): the recommendation lane uses the tools it has`
4. `eval(s-06): operator turns and nota_emitida scenario in the runner`
5. `eval(s-06): one-way dataset sync, per-case trace and score in langfuse`
6. `ci(s-06): evals-ci.sh, the affected-suite map and the required check`

**A ordem não é a dos ids dos requisitos, e o motivo é o mesmo da D-9 da S-05.** As tasks 1 e 2
tornam a régua confiável; sem elas, a task 3 mediria a conduta do agente misturada com o defeito do
juiz e com a variância. Consertar o agente contra uma régua que treme é escolher qual execução
acreditar.

## BDD

```gherkin
Cenário: regressão de prompt bloqueada
  Dado um PR que altera PROMPT_RECOMENDACAO e faz o agente citar preço divergente do banco
  Quando o CI executa o job de evals
  Então rodam as sub-suítes S-02, S-03, S-11 e S-04 — todas as que usam aquela lane —
  e o check falha apontando o caso e o fato sem origem em tool

Cenário: falha dura não faz média
  Dado um PR em que um único caso adversarial consegue executar ação fora da allowlist
  Quando o CI executa o job de evals
  Então a suíte inteira reprova, mesmo com todos os demais casos aprovados

Cenário: diff que não pode ter mudado nada não paga a suíte
  Dado um PR que só altera arquivos em docs/
  Quando o CI executa o job de evals
  Então o script sai com sucesso dizendo "nada a avaliar neste diff", e o check fica VERDE —
  nunca pulado, porque check pulado obrigatório trava a main para sempre
```

## Métricas de sucesso

Medidas na Fase 0, não estimadas — as da versão anterior (≤10 min, ≤US$ 0,50) foram escritas antes
de existir medição e não se sustentam.

| Métrica | Alvo | Como medir |
|---|---|---|
| Custo da suíte inteira | ≤ US$ 2,00 | soma do `gasto` no relatório (~US$ 1,35 hoje, extrapolado de 897k tokens medidos em 17 casos) |
| Duração do job, camada 1 | ≤ 25 min | CI, com concorrência 4 |
| Duração do PR que não toca o agente | ≤ 1 min | CI — o script sai cedo |
| Variância entre execuções | 0 casos virando | duas execuções seguidas da mesma sub-suíte, mesmo commit (REQ-2) |
| Casos sem execução | 0 de 23 | hoje são 4 (REQ-4) |

## Verificação independente

- Introduzir uma regressão proposital num branch descartável — um prompt que faça o agente citar
  preço divergente do banco — e confirmar CI vermelho com o relatório apontando o caso e o fato sem
  origem em tool.
- Conferir que o mapa seleciona pelo **código tocado** e não pela spec do PR: um diff em
  `PROMPT_RECOMENDACAO` tem de acionar S-02, S-03, S-11 e S-04.
- Conferir no Langfuse duas execuções como dataset runs comparáveis, trace por caso, score
  booleano, e PII mascarada no trace lido de volta.

> **Sem falsificações nesta spec**, por decisão do PO em 2026-08-28: o custo de tempo não se paga.
> Ficam os testes unitários e os evals. O ritual foi ajustado junto — ver
> `.claude/agents/verificador-de-spec.md`.

## Definition of Done

- [ ] Checklist padrão do template
