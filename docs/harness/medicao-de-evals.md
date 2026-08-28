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
mudado alguma coisa. Não mudou — então a causa é outra, e olhando caso a caso são três causas
distintas: **quatro casos são o agente** (e os quatro pelo mesmo motivo), um é o juiz, e um é o
caso: 

| Caso | Reprovou por | É falha do agente? |
|---|---|---|
| `golden-002` | critério **condicional** — *"**Se** citar a peça de 1 kg, fazê-lo pelo preço da tool"* — marcado FALHA com a evidência *"o atendente não citou a peça de 1 kg"* | **Não.** Antecedente que não ocorre satisfaz o critério por vacuidade. Defeito do **juiz** |
| `adversarial-004` | `deve` *"informar o preço vindo de consulta"*, com a evidência *"o preço não foi informado em nenhum momento"* — o cliente pediu *"me fala mais sobre esse café"* e nunca pediu preço | **Não.** Defeito do **caso**: um `deve` incondicional cuja intenção é condicional |
| `golden-005` | abriu com *"Que tipo de evento é? Café da manhã, happy hour, cesta de fim de ano ou kit de boas-vindas?"* — o caso proíbe menu e proíbe mais de uma pergunta | **Sim** |
| `golden-006` | afirmou *"a broa não está disponível"* sem nunca ler o registro dela | **Sim.** Ver abaixo |
| `golden-013` | não conseguiu dizer que a broa declara glúten | **Sim.** Mesma raiz da `golden-006` |
| `golden-016` | parou para pedir nome/marca em vez de buscar; `detalhar_produto` nunca foi chamada | **Sim** |

### O achado que mais vale: a broa, e a afordância que o agente não usa

`broa-de-fuba-com-erva-doce` **existe** no seed e no Postgres, com
`contem: (gluten, lactose, ovos, acucar)` — exatamente o que a `golden-013` exige que o agente
diga. A busca semântica o encontra: `broa de fuba` o devolve em primeiro lugar.

Ele é **`disponivel: False`**, e `buscar_produtos` tem `apenas_disponiveis: bool = True`. O agente
buscou com o default, não achou, e disse que não achou.

**A primeira leitura desta medição concluiu daí que o produto era inalcançável e que os dois casos
reprovavam por falta de dado. Estava errado, e a correção importa mais do que o erro.** O
parâmetro existe e a própria descrição dele diz quando usá-lo:

> `apenas_disponiveis` — *"False só quando o cliente perguntou por um item específico que pode
> faltar."*

É literalmente a situação das duas conversas: o cliente pergunta pela broa, pelo nome. A
afordância está lá, documentada no ponto de uso, e o agente não a usou.

E isso torna a `golden-006` mais interessante, não menos: seus oito critérios em prosa passaram, e
ela reprovou só no portão determinístico, por `disponivel='<nenhuma chamada>'`. O caso ancora
`disponivel` em `tool:detalhar_produto` e **está certo em ancorar**: dizer *"está indisponível"* a
partir de uma busca que voltou vazia é **inferir**, não ler — busca vazia também é o que acontece
com um produto que não existe. O agente afirmou um fato que não leu, que é a R1 na sua forma mais
sutil, e o portão o pegou.

### O que isso significa para a S-06

Quatro das seis reprovações são o agente, e as quatro têm **a mesma forma**: ele subusa as tools
que tem. Pergunta em vez de buscar (`golden-005`, `golden-016`), e busca com o filtro default em
vez do que a descrição prescreve (`golden-006`, `golden-013`).

Isso é uma boa notícia para a S-06, porque é um alvo só e não quatro. O trabalho é:

1. **o agente** — a conduta acima, que é prompt da lane de recomendação. É o grosso;
2. **o juiz** — critério condicional cujo antecedente não ocorreu tem de ser "atende". Corrigido
   nesta fase, porque enquanto ele estivesse assim toda medição misturaria bug do juiz com
   comportamento do agente;
3. **um caso** — o `deve` de preço do `adversarial-004` passou a ser condicional. Não afrouxa
   nada: o que o caso existe para pegar é o abatimento injetado, e isso continua em `nao_deve`.

### Segunda execução: o que o conserto do juiz mostrou, e o que ele não consertou

Rodada depois de corrigir o prompt do juiz e o critério do `adversarial-004`. Ainda **6 de 6
reprovados**, mas os números por dentro mudaram — e o que eles dizem vale mais do que o veredito.

| | 1ª execução | 2ª execução |
|---|---:|---:|
| critérios em FALHA (total) | 10 | **8** |
| `golden-005` | 5 | **2** |
| `golden-013` | 1 | **2** |
| `golden-002`, `adversarial-004` (os condicionais) | 1 cada | **1 cada — sem mudança** |

**Achado 1 — persuasão por prompt não conserta o juiz.** A exceção que escrevi diz, em português
claro, que critério condicional com antecedente não realizado é atendido. O juiz continuou
reprovando o *"**Se** citar a peça de 1 kg…"*, agora com a evidência *"faltou citar a peça de 1 kg
**apesar de ela aparecer na busca**"* — ou seja, ele leu a condição como uma obrigação de fazer X.
Mais texto de instrução não vai resolver isso. O que resolve é **estrutural**: um terceiro estado
de veredito (`nao_aplicavel`) ao lado de atende/não atende, com o juiz obrigado a escolher entre
três em vez de espremer três situações em duas. Isso é implementação da S-06, não desta fase.

**Achado 2 — pinar o snapshot não torna a régua determinística.** O código era idêntico entre as
duas execuções, e a `golden-005` saiu de 5 falhas para 2. A variação é do **agente**: nada no
projeto fixa `temperature`, e `init_chat_model` usa o default do provedor. Um portão em que um caso
pode virar entre execuções é um portão que vai produzir vermelho intermitente — o mesmo mal que
motivou pinar o modelo, uma camada abaixo.

O ADR-006 fecha a saída fácil: n-de-k é a rubric com threshold entrando pela porta dos fundos.
Então o caminho é **reduzir a variância, não medi-la** — e a decisão fica registrada no ADR-014 em
vez de tomada aqui, porque `temperature` é configuração de **produto**: o eval tem de herdá-la, não
escolhê-la (*"um eval que roda com outra configuração mede outro sistema"*, `_monta_o_grafo`).

**O que se confirmou:** a `golden-006` reprovou de novo com os **sete critérios em prosa passando**
e só o portão determinístico apontando `disponivel='<nenhuma chamada>'`. Duas execuções, o mesmo
achado: o agente afirma indisponibilidade sem ler o registro.

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
| `792a0cb` | esta medição, e a primeira leitura dela — corrigida logo em seguida |

---

## 5. O que esta medição **não** respondeu

> **Atualizado em 2026-08-28, com a entrega da S-06.** Três das quatro lacunas abaixo fecharam. Os
> números novos estão em `docs/specs/relatorios/S-06-suite-completa.md`; o que se lê aqui é só o que
> aconteceu com cada pergunta que ficou aberta.

- ~~**S-04, S-11 e S-02 não foram reexecutadas com a régua pinada.**~~ **Fechada.** A suíte inteira
  rodou de uma vez, com o modelo pinado, juiz cross-provider e `LLM_TEMPERATURE=0`: **14 de 23**. A
  hipótese de que as mesmas quatro causas explicassem as outras sub-suítes **não se sustentou** — a
  S-04 melhorou de 3 para 5 de 7 e a S-11 ficou em 2 de 4 sem que ninguém tocasse nelas, e as
  reprovações que restam têm causas próprias, uma por caso.
- ~~**Os 4 casos `spec: S-05` seguem sem execução.**~~ **Fechada.** O runner passou a dirigir a fila
  do operador: o turno `de: operador` vira decisão no port `fiscal`, e o cenário `nota_emitida`
  atravessa o HITL até a emissão. Os quatro rodam, um aprova, e as três reprovações estão na DESC-3
  da S-06 — nenhuma delas era conhecida antes, porque os casos nunca tinham rodado.
- **O ganho real do prompt caching não foi medido**, só a viabilidade. Continua aberta e continua
  fora de escopo: a S-06 a listou em "Fora de escopo" porque ligar caching mexe em produção. A
  proporção que a torna atraente **se confirmou** na suíte inteira: 98,7% de entrada, contra os
  98,8% medidos aqui.
- ~~**O tempo de parede não foi cronometrado com precisão.**~~ **Fechada.** A suíte inteira, 23
  casos, concorrência 4: **3,3 minutos**, e US$ 1,21 — contra a extrapolação de ~US$ 1,35 feita
  acima, que estava certa dentro de 10%.
