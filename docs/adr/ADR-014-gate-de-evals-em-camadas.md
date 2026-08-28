# ADR-014 — Gate de evals em camadas, e o Langfuse como visor

- Status: **aceito** · Data: 2026-08-28
- Decisão relacionada: D17 (docs/decisoes.md) · Riscos: R7, R1, R6
- Complementa o **ADR-006**, que continua valendo em tudo que não está aqui. Não o substitui: a
  régua continua sendo o caso, continua sendo aprovado-ou-reprovado, e continua não existindo
  arquivo de rubric.

> **Nota de cabeçalho, 2026-08-28 — aceito com a entrega da S-06.** O corpo abaixo não mudou; o que
> mudou é que ele deixou de descrever um plano e passa a descrever o que existe. As três camadas, o
> mapa, o terceiro estado do juiz e o Langfuse como visor estão implementados e medidos
> (`docs/specs/relatorios/S-06-suite-completa.md`).
>
> Duas coisas que este ADR previu em prosa e agora têm número: `temperature` pinada leva a variância
> de **5 itens de veredito para 0** entre execuções — com o veredito da suíte inteira virando de
> aprovada para reprovada no lado não pinado (`S-06-variancia-temperature.md`) —, e o terceiro estado
> do juiz fechou os dois casos condicionais que a persuasão por prompt não fechava.
>
> Uma que ele **não** previu, e vale registrar aqui porque é consequência do desenho: o visor engole
> toda exceção por decisão deste ADR, e por isso quebra em silêncio. A primeira execução mandou a
> suíte inteira para o Langfuse com a chamada de dataset run errada e "deu certo", com zero runs do
> outro lado. A resposta não foi deixar a exceção subir — isso poria o portão atrás do SaaS —, e sim
> o runner dizer em voz alta quantos casos chegaram ao visor.
>
> **E a verificação independente da S-06 mostrou que aquela resposta ainda deixava passar o mesmo
> sintoma** (ACH-4): `create_score` aceita `trace_id=None`, então um caso sem trace incrementava o
> contador enquanto o run item era pulado, e o runner imprimia a frase tranquilizadora com zero
> runs do outro lado. O aviso passou a contar as duas coisas — scores e run items — e tem teste.
>
> Fica registrado o que **não** ficou fechado: o job `evals` não foi promovido a required check da
> `main`. O REQ-5 pede isso nominalmente, e ligá-lo com 9 dos 23 casos reprovando bloquearia todo
> PR que tocasse arquivo mapeado, este inclusive. A decisão do PO foi deixar o requisito aberto e
> escrito, em vez de ligar o portão e suspendê-lo no mesmo dia (S-06, DESC-6). O que existe hoje é
> o job rodando e não decidindo; o que falta é uma linha de configuração e as 9 reprovações.

## Contexto

O ADR-006 decidiu que *"o job `evals` vira check obrigatório do PR na S-06"*, e o RF-5.4 escreveu
isso como *"evals rodam em todo PR"*. Três specs depois, a S-06 chegou e o portão não existe —
mas existe experiência com o custo dele, e ela é ruim: os evals viraram atrito recorrente, lentos
demais para rodar e vermelhos sem explicação. A S-05 fechou com a **DESC-8** registrando três
suítes reprovando e a hipótese de que a causa era deriva de modelo.

O PO parou a execução da S-06 e pediu uma medição antes da spec. Ela está em
`docs/harness/medicao-de-evals.md`, e o que ela achou muda três coisas:

1. **Custo e tempo, medidos.** A suíte inteira custa ~US$ 1,35 e passava de uma hora em série,
   contra a métrica de ≤US$ 0,50 e ≤10 min que a S-06 escreveu sem medir. E a conta é **98,8%
   entrada** — histórico reenviado a cada ida ao modelo — o que diz onde uma alavanca de custo
   precisa morder.
2. **A hipótese da DESC-8 estava errada.** A S-03 rodou com o modelo pinado num snapshot datado e
   reprovou os mesmos 6 de 6. Não era deriva: eram quatro casos de conduta do agente, um defeito
   do juiz e um defeito de caso.
3. **A régua se movia sozinha, mas por outro caminho.** `LLM_MODEL` nomeava um alias, e
   `EVALS_JUDGE_MODEL` vazio fazia o agente julgar a própria saída — que a DESC-7 da S-04 mediu
   oscilando em 5 de 7 com os casos reprovados **mudando entre execuções**.

Registro que pertence aqui e não a uma spec, conforme a condição 6 do relatório de verificação da
S-05: **o PR da S-05 foi aberto e mesclado com as três suítes de eval vermelhas**, por decisão do
PO em 2026-08-28. É uma suspensão declarada do guardrail do `CLAUDE.md` que manda rodar os evals
antes do PR, e a justificativa é o A/B da DESC-8 — o vermelho precedia aquela branch. Este ADR é
a resposta a ela.

## Alternativas consideradas

1. **A suíte inteira em todo PR** — a letra do RF-5.4. Simples de explicar e impossível de
   afrouxar por engano. Em troca: ~US$ 1,35 e ~20 min (já paralelizado) em **todo** PR, inclusive
   num que só mexe em `docs/`. O problema principal não é o dinheiro — é que rodar um eval que não
   podia ter mudado não é rigor, é ruído pago, e ruído pago é o que ensina a ignorar o portão.

2. **A suíte inteira só ao fim de todas as specs** — barato e tentador. Recusado, e a razão é o
   próprio requisito: a R7 é *"regressão silenciosa **a cada mudança de prompt**"*, e
   `docs/requisitos.md` explica por que ela existe — *"nada quebra, o teste unitário continua verde
   e o atendimento piora"*. Um portão que roda depois de tudo não bloqueia a regressão: descobre-a
   tarde, com a mudança que a causou enterrada sob outras dez. Vira auditoria post-mortem, que é
   exatamente o *"testei na mão e ficou bom"* contra o qual o ADR-006 foi escrito.

3. **Camadas: determinística sempre, sub-suítes afetadas no PR, suíte inteira no pós-merge.**
   Mantém o espírito do RF-5.4 — nenhum PR passa sem o eval que **poderia** tê-lo pego — e muda a
   letra. O preço é uma peça nova para manter: um mapa de código para sub-suíte, que pode ficar
   errado.

## Decisão

**Opção 3.** O portão passa a ter três camadas.

| Camada | O que roda | Quando | Custo |
|---|---|---|---|
| **0 — determinística** | `evals-check` (schema), `test_eval_corpus_is_traceable`, e `tests/security/`, que **já parametriza a partir de `evals/adversarial/*.yaml`** | todo PR, sempre | segundos, US$ 0 |
| **1 — sub-suítes afetadas** | as sub-suítes que o diff pode ter mudado, pelo mapa abaixo | todo PR — **é o required check** | 0 a ~US$ 1,35 |
| **2 — suíte inteira** | os 23 casos, em paralelo | pós-merge na `main`, e sob demanda | ~US$ 1,35 |

A camada 0 já roda hoje e ninguém a contava como eval. Vale dizê-lo alto, porque muda a leitura do
risco: **nenhum PR fica sem verificação do corpus**, mesmo quando a camada 1 não tem o que rodar.

### O mapa, e a regra que o torna honesto

O eixo é **que código o diff tocou**, nunca de qual spec o PR é: uma mudança em
`PROMPT_RECOMENDACAO` afeta os casos da S-03, da S-11 e da S-04, porque as três usam aquela lane.

| Se o diff toca | Rodam |
|---|---|
| `subagents.py`, `graph.py`, `budget.py`, `providers.py`, `config.py` | todas |
| `catalogo.py`, `tools/catalogo.py`, `ingest.py`, `data/catalogo/` | todas — todo fato sai do catálogo |
| `evals/**` (runner, juiz, portão, casos, schema) | todas |
| `supervisor.py` | S-04 |
| `composicao.py`, `tools/composicao.py` | S-11, S-04 |
| `pedidos.py`, `pagamento.py`, `tools/checkout.py` | S-04, S-05 |
| `fiscal.py`, `nota/` | S-05 |
| `redaction.py`, `observability.py` | S-02 |
| `docs/`, `.claude/`, frontend | nenhuma |

> **Arquivo não mapeado ⇒ roda tudo.** O mapa só pode errar para o lado caro, nunca para o
> permissivo. Um arquivo novo que ninguém classificou não abre buraco no portão — encarece o PR até
> alguém classificá-lo, que é a pressão certa. E a camada 2 no pós-merge é o contra-cheque: se o
> mapa estiver errado, a `main` fica vermelha e todo mundo vê, em vez de o buraco aparecer meses
> depois.

### Uma armadilha estrutural que o desenho evita

**Um job pulado que é *required* trava a `main` para sempre.** Logo, a decisão de "não rodar nada
neste diff" mora **dentro** de `scripts/evals-ci.sh` — que sai `0` dizendo *"nada a avaliar neste
diff"* — e **nunca** num `if:` de path filter no job. O `ci.yml` já resolveu a metade análoga desse
problema com o job `detect` (S-00, D-10); esta é a outra metade.

### O Langfuse é o visor, não o portão

Os resultados vão para o Langfuse — dataset run por execução, trace por caso, score **booleano**
por caso — porque comparar execuções é o que se faz com esses relatórios, e hoje não há onde. Duas
regras:

- **A sincronização é de mão única: `evals/` → Langfuse, nunca de volta.** O dataset lá é uma
  projeção do corpus, indexada pelo `id` do caso. Editar um item na UI não muda veredito nenhum: o
  portão lê o YAML do repositório, que é o que o CODEOWNERS protege.
- **O veredito é o exit code do runner, não um limiar de score.** O Langfuse oferece uma action de
  CI que levanta `RegressionError` sobre threshold — recusada por duas razões deste repositório:
  o veredito sairia do repositório para dentro de um número (a rubric que o ADR-006 recusou de
  frente), e o merge passaria a depender da disponibilidade de um SaaS. O ADR-010 aceitou um
  terceiro na observabilidade **com** a cláusula de que ele nunca derruba o atendimento; pôr o
  portão atrás dele seria a mesma aposta sem a mesma cláusula.

O agregado que a UI mostra é artefato de visor. **Não é veredito**, e está escrito assim aqui
porque um "87%" na tela é exatamente o número que alguém vai citar um dia para liberar um PR
vermelho.

### A régua é pinada — e pinar o modelo não basta

`LLM_MODEL` nomeia um **snapshot datado**, não um alias, e `EVALS_JUDGE_MODEL` tem default de
**outro provedor**. Uma régua que anda sozinha não detecta regressão: produz vermelho aleatório, e
vermelho aleatório treina a ignorar o CI. Fica registrado que `selected_model` do config store
ainda sobrepõe o pin em runtime — por isso o relatório passou a dizer com que agente e que juiz
rodou.

Mas a medição mostrou que isso **não basta**: duas execuções da S-03 com código idêntico deram
números diferentes (a `golden-005` saiu de 5 critérios em falha para 2). A variância é do agente —
nada no projeto fixa `temperature`, e `init_chat_model` usa o default do provedor. Um portão em
que um caso vira entre execuções produz vermelho intermitente, que é o mesmo mal uma camada abaixo.

O ADR-006 fecha a saída fácil: rodar *n* vezes e exigir *k* aprovações é a rubric com threshold
entrando pela porta dos fundos. Então **o caminho é reduzir a variância, não medi-la**, e a decisão
é: **`temperature` passa a ser configuração explícita do produto**, e o eval a herda. Não é escolha
do eval — *"um eval que roda com outra configuração mede outro sistema"* (`_monta_o_grafo`). O valor
concreto e o efeito medido são entregáveis da S-06; o que este ADR fixa é que a variância se ataca
na configuração e nunca por média de execuções.

### O juiz precisa de um terceiro estado, e não de mais instrução

Um critério condicional — *"Se citar a peça de 1 kg, fazê-lo pelo preço da tool"* — cuja condição
não ocorreu **não foi violado**. O juiz o reprovava. Uma exceção escrita no prompt, em português
claro, **não resolveu**: ele continuou lendo a condição como obrigação (*"faltou citar a peça
apesar de ela aparecer na busca"*).

Fica decidido que a correção é **estrutural**: `VeredictoDeCriterio` ganha um terceiro estado —
atende, não atende, **não aplicável** — em vez de espremer três situações em um booleano. Isso não
cria nota nem dimensão, e portanto não colide com o ADR-006: continua sendo veredito por critério,
e "não aplicável" não conta como aprovação nem como falha, apenas sai do cálculo daquele caso.

A tentação a recusar aqui é a oposta: transformar "não aplicável" em escape para falha real. Um
critério **não** vira condicional porque o agente deixou de chamar a tool que o acionaria — aí a
condição faltou por conduta dele, e é exatamente isso que o critério existe para pegar.

## Consequências

**Positivas**

- Nenhum PR sem verificação: a camada 0 é grátis e sempre roda.
- O PR paga só pelo eval que poderia tê-lo pego, e o pós-merge cobre o resto.
- O portão fica reproduzível: modelo e juiz fixos, e o relatório se identifica.
- Comparar duas execuções deixa de ser leitura de dois arquivos lado a lado.

**Negativas, aceitas**

- **Um artefato novo para manter e para errar:** o mapa. A regra do não-mapeado e a camada 2
  limitam o dano, não o eliminam — um mapa errado num arquivo *mapeado* deixa de rodar algo que
  deveria, e só o pós-merge pega.
- **A letra do RF-5.4 muda.** "Rodam em todo PR" passa a significar "as afetadas rodam em todo PR".
  Quem ler só o PRD vai achar que é mais do que é; por isso está aqui.
- **Custo de API no pós-merge**, agora em toda entrega na `main` e não só nos PRs.
- **Dependência de um terceiro para inspecionar** a régua, ainda que não para julgá-la. Sem
  Langfuse continua-se com o markdown do runner, que é o que sempre houve.

**O que passa a ser exigido do código**

- `scripts/evals-ci.sh` decide o escopo por diff e **sempre sai 0 ou 1**, nunca deixa o job pulado.
- O mapa é versionado e tem teste unitário: dada uma lista de arquivos, devolve as sub-suítes —
  incluindo o caso "não mapeado ⇒ tudo".
- O runner instrumenta pelo cliente Langfuse **do projeto** (`observability.client()`), que é o que
  carrega `mask_otel_spans`; um cliente default exportaria as conversas de eval, com CNPJ e e-mail
  sintéticos, sem redação nenhuma. Um teste afirma isso.
- Os traces de eval vão em `environment=evals`, para não poluírem as métricas de produção.
- Langfuse indisponível **não reprova a suíte** (ADR-010): a instrumentação loga e segue.
