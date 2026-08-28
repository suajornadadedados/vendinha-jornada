# O efeito da `temperature` na régua — medido, não suposto

> Entregável do REQ-2 da S-06. O ADR-014 fixou que *"a variância se ataca na configuração e nunca
> por média de execuções"*, e deixou explícito que **o valor concreto e o efeito medido são
> entregáveis da S-06**. Este documento é o efeito medido.

Data: 2026-08-28 · Branch: `spec/s-06-evals-gate` · Sub-suíte: S-03, 6 casos, 52 itens de veredito
Agente: `anthropic:claude-haiku-4-5-20251001` · Juiz: `openai:gpt-4.1` · Concorrência 4

---

## O desenho

Quatro execuções da mesma sub-suíte, **no mesmo commit**, variando uma coisa só:

| Lado | `LLM_TEMPERATURE` | Execuções |
|---|---|---|
| pinado | `0` | `S-06-variancia-run-a.md`, `S-06-variancia-run-b.md` |
| baseline | ausente — o default do provedor | `S-06-baseline-run-a.md`, `S-06-baseline-run-b.md` |

A unidade de comparação **não é o veredito do caso**: é o item de veredito — cada linha de
`deve`/`nao_deve` mais o achado do portão determinístico, 52 no total. Comparar só o veredito do
caso esconde a variância dentro de um caso que reprova pelos dois lados por motivos diferentes, e
foi assim que a Fase 0 quase concluiu que "nada mudou" entre duas execuções em que a `golden-005`
tinha saído de 5 critérios em falha para 2.

## O resultado

| Lado | Itens que viraram entre as duas execuções | Veredito da suíte |
|---|---:|---|
| **`temperature=0`** | **0 de 52** | REPROVADA nas duas, pelo mesmo caso e pelo mesmo motivo |
| **default do provedor** | **5 de 52** | **APROVADA numa, REPROVADA na outra** |

O que virou no baseline:

| Caso | Item | Execução A | Execução B |
|---|---|---|---|
| `adversarial-004` | *"Se informar preço, informar o vindo de consulta"* | `n/a` | `ok` |
| `golden-005` | *"Fazer duas ou mais perguntas encadeadas na mesma resposta"* | `ok` | **FALHA** |
| `golden-005` | **veredito do caso** | APROVADO | **REPROVADO** |
| `golden-016` | *"Comparar as duas opções de queijo pelos rendimentos consultados"* | `ok` | **FALHA** |
| `golden-016` | **veredito do caso** | APROVADO | **REPROVADO** |

**O veredito da suíte inteira virou entre duas execuções de código idêntico.** É exatamente o
vermelho intermitente que o ADR-014 previu, e ele é pior do que vermelho constante: um portão que
aprova e reprova o mesmo commit não ensina a consertar nada, ensina a apertar "re-run".

## Leituras que este número **não** sustenta

**"Temperature 0 piorou a suíte."** Não. O baseline aprovou uma vez e reprovou a outra; o lado
pinado reprovou as duas, sempre pela `golden-006` e sempre pelo mesmo achado
(`disponivel='<nenhuma chamada>'`). A `golden-006` tem um defeito estrutural real — a DESC-2 da
spec — e o que mudou foi ele ficar **visível toda vez** em vez de metade das vezes. Portão que pega
um problema real em 50% das execuções é pior do que um que o pega sempre: o custo não é o defeito,
é não se poder acreditar no verde.

**"Zero divergências prova determinismo."** Prova reprodutibilidade em **duas** execuções desta
sub-suíte. Não é a mesma afirmação, e a diferença importa quando alguém citar este documento para
justificar não reexecutar. O que a métrica da spec pede é "0 casos virando entre duas execuções
seguidas da mesma sub-suíte, mesmo commit", e é isso que está medido.

**"O juiz é a fonte da variância."** Os dois lados usaram o mesmo juiz, com a mesma temperatura
herdada. Os cinco itens que viraram viraram porque **a resposta do agente mudou** — em `golden-005`
ele passou a encadear duas perguntas, em `golden-016` deixou de comparar os rendimentos. A
evidência citada pelo juiz é diferente nas duas execuções porque o texto que ele leu era diferente.

## Um erro de método, e por que ele está aqui

A primeira tentativa deste A/B **mediu a mesma configuração duas vezes** e produziu "0 divergências"
dos dois lados — um resultado limpo, plausível, e sem valor nenhum.

A causa: `$env:LLM_TEMPERATURE=""` no PowerShell **apaga** a variável em vez de defini-la vazia, e o
lado "default do provedor" nunca existiu. Duas coisas saíram disso:

1. `Settings.llm_temperature` ganhou o validador `_temperatura_vazia_e_o_default_do_provedor`. O
   campo é `float | None`, mas `""` não virava `None` — o default `0.0` vencia. Quem apagasse o
   valor para pedir o comportamento do provedor receberia `temperature=0` em silêncio, que é o
   oposto do que pediu. É a mesma classe do `_vazio_e_ausente` do `EVALS_JUDGE_MODEL`, e foi
   descoberta do mesmo jeito: tentando usar.
2. O outro lado passou a ser montado por um script que põe a variável em branco **no processo**,
   antes de `config` ser importado, e que **afirma** `llm_temperature is None` antes de gastar a
   primeira chamada de API. Uma medição que não confere o próprio setup produz um relatório que
   parece resultado.

Fica registrado porque o modo de falha é caro justamente por ser silencioso: os números saem
plausíveis, e nada avisa que o experimento não tinha dois lados.

## Custo

Oito execuções da sub-suíte S-03 nesta medição e na iteração do prompt que a acompanhou, a ~30k
tokens por caso e ~180k por execução. A ~US$ 1,00/MTok de entrada e US$ 5,00/MTok de saída, algo
como **US$ 1,20 no total** — na mesma ordem dos US$ 0,14 por execução que a Fase 0 mediu.

## Decisão que este documento sustenta

`LLM_TEMPERATURE=0` como default do produto, e o eval herdando. Não é escolha do eval: *"um eval
que roda com outra configuração mede outro sistema"*. Instâncias que queiram o comportamento do
provedor deixam a linha em branco, e agora isso funciona.
