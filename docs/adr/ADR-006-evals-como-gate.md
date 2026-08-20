# ADR-006 — Evals golden e adversariais como gate de PR

- Status: aceito · Data: 2026-08-03 · Decisões: D2, D8 · Riscos: R1, R4, R7

## Contexto
Mudança de prompt ou de modelo degrada qualidade em silêncio: nada quebra, o teste unitário
continua verde e o atendimento piora. "Testei na mão e ficou bom" não é processo. Ao mesmo
tempo, este é um projeto de demonstração com um único mantenedor — uma régua de avaliação
pesada demais não sobrevive ao segundo mês.

## Alternativas consideradas
1. **Rubric versionada com dimensões, âncoras e thresholds numéricos por dimensão**, pontuada
   por LLM-as-judge com política de catraca — mede nuance de atendimento e produz série
   histórica; em compensação, exige calibrar o judge, defender cada número na revisão e
   manter um arquivo que compete com as specs como definição de "bom".
2. **Conjunto versionado de casos, cada um carregando seu próprio critério de aprovação** —
   a régua é o caso, não uma tabela separada. Menos granular, muito mais barato de manter,
   e o critério fica ao lado do exemplo que o motivou.

## Decisão
Opção 2. Golden dataset e suite adversarial versionados em `evals/`; o runner executa contra
o agente completo com adapters mock; o job `evals` vira check obrigatório do PR na S-06.

Cada caso declara o comportamento esperado e é aprovado ou reprovado — sem nota agregada.
Duas famílias de falha reprovam a suíte inteira, sem média e sem negociação:

- **fato inventado** — atributo, preço ou disponibilidade que não existe no catálogo/banco;
- **ação indevida** — side effect sem confirmação, emissão sem aprovação registrada, ou
  qualquer ação fora da allowlist obtida por instrução injetada.

Não existe arquivo de rubric neste repositório. A definição de qualidade vive nos casos de
`evals/` e nos critérios de aceite das specs.

## Consequências
+ Regressão de qualidade bloqueada no PR, não descoberta em produção.
+ Critério lido junto com o exemplo: quem abre um caso entende por que ele reprova.
+ Sem número para afrouxar quando o CI incomoda — mexer no gate exige mexer no caso, e
  `evals/` é protegido por CODEOWNERS.
− Perde-se a série histórica de score por dimensão: sabemos que passou ou reprovou, não se
  o atendimento ficou "um pouco melhor" (aceito para o escopo deste release).
− Qualidade conversacional fina (tom, condução) fica coberta por julgamento humano na
  verificação independente, não por métrica automatizada.
− Custo de API no CI (mitigado com modelo econômico e dataset enxuto).
