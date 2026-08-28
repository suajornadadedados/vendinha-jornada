---
id: S-06
titulo: Qualidade como gate (EDD)
status: em-revisao
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

| Métrica | Alvo | Como medir | **Medido** |
|---|---|---|---|
| Custo da suíte inteira | ≤ US$ 2,00 | soma do `gasto` no relatório (~US$ 1,35 hoje, extrapolado de 897k tokens medidos em 17 casos) | **US$ 1,21** (1,15 M tokens, 98,7% entrada) |
| Duração do job, camada 1 | ≤ 25 min | CI, com concorrência 4 | **3,3 min** para a suíte INTEIRA |
| Duração do PR que não toca o agente | ≤ 1 min | CI — o script sai cedo | **segundos**: sai antes de subir a infra |
| Variância entre execuções | 0 casos virando | duas execuções seguidas da mesma sub-suíte, mesmo commit (REQ-2) | **0 de 52 itens** de veredito |
| Casos sem execução | 0 de 23 | hoje são 4 (REQ-4) | **0** |

Os relatórios estão em `docs/specs/relatorios/S-06-suite-completa.md` (consolidado),
`S-06-variancia-temperature.md` (o A/B) e `S-06-suite-completa/` (caso a caso).

**A suíte reprova: 14 de 23 aprovados.** Isso não é métrica falhada — é o portão dizendo, pela
primeira vez sobre o corpus inteiro e com número reprodutível, onde o agente não está bom. A S-03
saiu de 0 de 6 para 5 de 6; as outras oito reprovações são medição nova, não regressão desta branch,
e o que fazer com cada uma é decisão do PO. Nenhuma se conserta editando caso (ADR-006, CODEOWNERS).

## Descobertas

**DESC-1 — o REQ-4 descreve a causa errada, e o trabalho é o mesmo.** Ele diz que os quatro casos
`spec: S-05` estavam *"recusados por terem turno `de: operador`"*. Só **dois** têm (`golden-004` e
`golden-011`). O `golden-012` e o `adversarial-002` passariam pela guarda e mesmo assim não rodavam,
por uma razão estrutural: `SPECS_COM_CHECKOUT` não incluía a S-05, então `--spec S-05` montava só a
lane de recomendação, e `_monta_o_grafo` não passava `fiscal=` — com isso `consultar_pedido` devolvia
`status_nf="nao_aplicavel"` e os `fatos_ancorados` reprovavam por campo ausente. Corrigido junto; o
registro fica porque a spec afirmava uma causa que não era a única.

**DESC-2 — a `golden-006` não fecha por prompt, e a DESC-1 da S-03 já dizia por quê.** Ela é o
único caso da S-03 que continua reprovando, com os **sete critérios em prosa passando** e só o portão
determinístico apontando `disponivel='<nenhuma chamada>'`. O caso ancora `disponivel` em
`tool:detalhar_produto` e **está certo em ancorar**. O problema é que `buscar_produtos` já devolve
`disponivel`, então o agente não tem motivo funcional para chamar o detalhe — e quatro rodadas de
prompt nesta spec confirmaram o que a S-03 mediu: *"não são corrigíveis por prompt, e tentar
corrigi-las por prompt é exatamente o que `docs/testes.md` recusa"*.

A saída que a DESC-1 da S-03 nomeou continua sendo a única: **tirar `preco` e `disponivel` do
retorno de `buscar_produtos`**, tornando a regra estrutura em vez de instrução. O PO decidiu manter o
D-3 na S-03; a decisão volta à mesa com uma medição a mais. **Não implementado aqui** — é mudança de
contrato de tool, fora do escopo desta spec.

**DESC-3 — três casos da S-05 rodaram pela primeira vez e reprovam, por três causas distintas.**
Nenhuma delas é o portão errado; todas são achado que só apareceu porque os casos passaram a rodar.

- `golden-012`: `consultar_pedido` **nunca devolve as composições do pedido**. `_com_a_nota(pedido)`
  é chamada sem `vereditos` (`tools/checkout.py`), então o campo volta vazio sempre. O agente não
  sabe quais produtos o pedido contém e não tem como chamar `detalhar_produto` para o
  `prazo_estimado` que o caso exige. É lacuna de produto, não do caso.
- `golden-011`: o agente responde *"a nota está em conferência"* a partir de um `consultar_pedido` de
  um turno anterior, sem reconsultar depois da rejeição. **Três variantes de prompt foram medidas e
  nenhuma mudou o comportamento** — inclusive uma regra mecânica no mesmo formato das que
  funcionaram. O texto foi removido em vez de ficar no prompt sem efeito: a Fase 0 já tinha
  estabelecido que instrução que não muda comportamento é peso morto num prefixo que é 98,7% do
  custo. É a mesma classe da DESC-2, e provavelmente pede a mesma resposta estrutural.
- `golden-004`: o caso ancora `numero_nota`, mas **a conversa dele não tem turno depois da
  aprovação** — o operador aprova na última fala. Não existe momento em que o agente possa reportar o
  número. É defeito de caso, do tipo que a S-04 já corrigiu uma vez movendo o fato de lugar (P-4), e
  a correção seria acrescentar uma fala de cliente ao final. **Editar caso é decisão do PO**, e por
  isso está aqui e não no diff.

**DESC-4 — `LLM_TEMPERATURE=` vazia caía no default `0.0` em vez de significar ausente.** Mesma
classe do `EVALS_JUDGE_MODEL` vazio, e descoberta do mesmo jeito: tentando usar. Corrigido nesta spec
com validador e teste, porque a primeira tentativa de medir o efeito da temperatura **rodou duas
vezes a mesma configuração** e produziu um A/B sem dois lados — limpo, plausível e sem valor.

**DESC-5 — o juiz devolveu bytes nulos no lugar de acentos numa execução.** Uma das quatro
execuções da S-03 gravou 23 `\x00` dentro da evidência (`est\x00 dispon\x00vel`), e as outras não.
Vem do provedor do juiz, não do runner — `--saida` grava em UTF-8 e as demais execuções saíram
limpas. Não afeta veredito nenhum: o `atende`/`nao_atende` é campo estruturado, e só a prosa da
evidência degrada. Registrado porque um relatório com nulo dentro é desagradável de ler e ninguém
saberia de onde veio.

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
