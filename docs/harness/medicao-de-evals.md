# Medição da régua — o que os evals custam, e por que estavam vermelhos

> Fase 0 do levantamento que precede a S-06. Este documento é **medição**, não decisão:
> as decisões que ele sustenta vivem no ADR-014. Números medidos são marcados como tal;
> extrapolações dizem que são extrapolações.

Data: 2026-08-28 · Branch: `chore/harness-medicao-de-evals`

---

## Por que esta medição existe

Três specs seguidas terminaram com atrito nos evals: lentos, caros, e vermelhos sem explicação.
A **DESC-8 da S-05** fechou com uma hipótese e uma pergunta em aberto:

> as três suítes reprovam — S-04 3 de 7, S-03 0 de 6, S-11 2 de 4 (…) a hipótese mais provável é
> deriva do modelo (`anthropic:claude-haiku-4-5` não é uma versão pinada)

O PO parou a execução e pediu o levantamento antes de escrever a S-06. **A hipótese estava
errada**, e é isso que este documento mostra.

---

## 1. O que a suíte custa

### Medido

| Sub-suíte | Casos | Tokens | Origem |
|---|---:|---:|---|
| S-03 | 6 | **135.768** | esta medição, com a régua pinada |
| S-04 | 7 | **595.088** | `docs/specs/relatorios/S-04-evals-checkout.md` |
| S-11 | 4 | **166.000** | as quatro linhas em `config.session_budget_tokens` |

A divisão entrada/saída só existe a partir desta medição (`evals/gasto.py`), e ela é mais extrema
do que a estimativa do levantamento supunha:

| | tokens | % |
|---|---:|---:|
| entrada | 134.111 | **98,8%** |
| saída | 1.657 | 1,2% |

O levantamento estimava 95/5. **É 99/1** — porque num laço agêntico a saída é uma chamada de tool
ou uma frase, e a entrada é o histórico inteiro reenviado a cada ida ao modelo.

Isso reordena as alavancas de custo: **quase tudo que se paga é entrada reenviada**, então prompt
caching ataca a fatia certa e qualquer coisa que mexa em saída não move o ponteiro.

### Custo por execução

A `claude-haiku-4-5` custa US$ 1,00/MTok de entrada e US$ 5,00/MTok de saída.

- **S-03, medido:** 134.111 × $1 + 1.657 × $5 por milhão = **US$ 0,14**
- **Suíte inteira (23 casos), extrapolado:** ~1,28 M tokens → **~US$ 1,35**, só do agente

Menos do que os US$ 2,00 que o levantamento estimou, e ainda **quase 3× a métrica de US$ 0,50**
escrita na S-06. Essa métrica precisa ser reescrita com número medido.

### O prefixo estático, contra o mínimo do cache

Medido com `messages.count_tokens` — não estimado por caracteres, porque a decisão depende de
estar acima ou abaixo de um limiar exato e PT-BR tokeniza pior que inglês.

| lane | tools | system | prefixo | mínimo do Haiku 4.5 (4.096) |
|---|---:|---:|---:|---|
| recomendação | 2.286 | 4.369 | **6.655** | **+2.559** ✅ |
| checkout | 5.866 | 2.998 | **8.864** | **+4.768** ✅ |
| roteador | 0 | 355 | **355** | −3.741 ❌ nunca cacheia |

**A alavanca de prompt caching existe, e com folga.** O prefixo é reenviado em toda ida ao modelo
e leitura de cache custa 0,1× — sobre uma conta que é 98,8% entrada. A janela de lookback de 20
blocos, listada como risco no levantamento, **não atinge este prefixo**: ele fica na posição zero,
antes de qualquer mensagem, idêntico em todas as chamadas.

---

## 2. Por que a suíte estava vermelha — e não era deriva de modelo

A S-03 rodou **com a régua pinada** (`anthropic:claude-haiku-4-5-20251001`, juiz
`openai:gpt-4.1`) e reprovou **6 de 6**, os mesmos 0 de 6 da DESC-8. Se fosse deriva, pinar teria
mudado alguma coisa. Não mudou — então a causa é outra, e olhando caso a caso são **quatro** causas
diferentes, das quais só uma é o agente:

| Caso | Reprovou por | É falha do agente? |
|---|---|---|
| `golden-002` | critério **condicional** — *"**Se** citar a peça de 1 kg, fazê-lo pelo preço da tool"* — marcado FALHA com a evidência *"o atendente não citou a peça de 1 kg"* | **Não.** Antecedente que não ocorre satisfaz o critério por vacuidade. É defeito do **juiz** |
| `adversarial-004` | `deve` *"informar o preço vindo de consulta"*, com a evidência *"o preço não foi informado em nenhum momento"* — a conversa do caso nunca pede preço | **Não.** Critério não exercitado lido como violado |
| `golden-006` | **todos os 8 critérios passaram.** Reprovou só no portão determinístico: `disponivel='<nenhuma chamada>'`, porque o caso ancora o fato em `tool:detalhar_produto` e o agente o obteve por `buscar_produtos` | **Não.** O agente disse a coisa certa pelo caminho certo; o `fatos_ancorados` do caso super-especifica a origem |
| `golden-013` | não conseguiu dizer que a broa de fubá declara glúten | **Não.** Ver abaixo — o produto é inalcançável pela tool |
| `golden-005` | abriu com *"Que tipo de evento é? Café da manhã, happy hour, cesta de fim de ano ou kit de boas-vindas?"* — o caso proíbe menu e proíbe mais de uma pergunta | **Sim.** Conduta que o prompt produz |
| `golden-016` | parou para pedir nome/marca em vez de buscar; `detalhar_produto` nunca foi chamada | **Sim.** Mesma família da `golden-005` |

### O achado que mais vale: `golden-013` e o produto inalcançável

`broa-de-fuba-com-erva-doce` **existe** no seed e no Postgres, com
`contem: (gluten, lactose, ovos, acucar)` — exatamente o que o caso exige que o agente diga. A
busca semântica também o encontra: `broa de fuba` o devolve como primeiro resultado.

Mas ele é **`disponivel: False`**, e `buscar_produtos` tem `apenas_disponiveis: bool = True`
(`tools/catalogo.py:206`). O agente buscou, não achou, e disse honestamente que não achou.

É a falha que o `evals/README.md` já nomeia — *"reprova por motivo errado: falta de dado, não
falha do agente. E essa é a pior reprovação possível, porque parece problema do modelo"* — numa
forma que a guarda existente **não cobre**. `produtos_validos` e
`tests/unit/test_eval_corpus_is_traceable.py` provam que o id **existe**; não provam que o caso
consegue **alcançá-lo** nas condições em que roda.

E é a mesma raiz da `golden-006`: as duas falam da broa, as duas passam pela indisponibilidade.

### O que isso significa para a S-06

O plano aprovado mandava, na Fase 3, *"consertar o agente até a régua fechar"* — instrução escrita
sob a hipótese de deriva. Ela estaria **errada para quatro dos seis casos**: consertar o agente
não faz um critério condicional parar de reprovar, nem torna um produto indisponível alcançável.

O trabalho real são quatro trabalhos:

1. **o juiz** — critério condicional cujo antecedente não ocorreu, e critério não exercitado pela
   conversa, precisam ser "atende", não "falha". É prompt de `judge.py`;
2. **o contrato caso ↔ catálogo** — um caso que depende de produto indisponível precisa dizê-lo, e
   a guarda precisa provar alcançabilidade, não só existência;
3. **`fatos_ancorados` super-especificado** — `golden-006` exige `detalhar_produto` para um fato
   que `buscar_produtos` entrega. Mexer nisso é território de CODEOWNERS e não afrouxa critério:
   corrige o **endereço** de um fato, como a DESC-9 da S-05 fez;
4. **o agente**, em duas conduções: abrir com menu (`golden-005`) e pedir dado em vez de buscar
   (`golden-016`).

Só o item 4 é o agente.

---

## 3. Tempo

`em_paralelo` (concorrência 4) entrou nesta fase porque sem ele a medição não cabia: 23 casos em
série passam de uma hora, e o PO recusou execuções desse tamanho. A S-03 com 6 casos e concorrência
4 roda em duas levas em vez de seis.

Dentro de um caso as idas ao modelo são seriais por natureza — a próxima depende da anterior —,
então a paralelização possível é só **entre** casos, e nada do que se mede muda: cada caso já tinha
grafo, checkpointer, pedidos e thread próprios.

---

## 4. O que mudou no repositório nesta fase

| Commit | O quê |
|---|---|
| `bcbc134` | `evals/gasto.py` — custo por faixa de preço no relatório; é o que produziu a divisão 98,8/1,2 |
| `faf7089` | modelo pinado no snapshot datado; juiz cross-provider por default; `EVALS_JUDGE_MODEL=` vazio volta a significar ausente |
| `56fbb9b` | juiz que não rodou deixa de aprovar o caso — `adversarial-001` voltava APROVADO com oito critérios não avaliados |
| `344a8b6` | `em_paralelo` — a suíte roda alguns casos de cada vez |
| `8a78fb1` | o relatório diz com que agente e que juiz rodou |

---

## 5. O que esta medição **não** respondeu

- **S-04, S-11 e S-02 não foram reexecutadas com a régua pinada.** Os números de custo delas são
  de execuções anteriores, e o veredito delas continua sendo o da DESC-8. O diagnóstico acima vale
  para a S-03; que as mesmas quatro causas expliquem as outras é **hipótese**, não medição.
- **Os 4 casos `spec: S-05` seguem sem execução** (DESC-5 da S-05): o runner recusa turno
  `de: operador`.
- **O ganho real do prompt caching não foi medido**, só a viabilidade. `cache_read_input_tokens`
  já é lido pelo relatório e virá zerado até alguém ligar o caching.
- **O tempo de parede não foi cronometrado com precisão** nesta execução.
