# Roteiro do vídeo — setup do repositório

Cola de gravação. Uso pessoal, não vai pro repo público.
Repo vazio de um lado, arquivos prontos do outro. Vou trazendo e explicando o porquê.

---

## O arco — a única coisa pra decorar

| # | Cena | A frase que resume |
|---|---|---|
| 1 | **O problema** | O cliente diz o que quer. O requisito é meu. |
| 2 | **Discovery** | O enunciado pergunta; o repositório responde. |
| 3 | **Harness** | Como o agente trabalha dentro disso. |
| 4 | **Portões** | O repositório para de confiar em mim. |
| 5 | **Arquitetura** | O que sobra depois das decisões. |

**A ordem é o argumento:** desejo → documentação → harness → portão → arquitetura.
A stack é a **última** coisa que aparece, e é isso que torna cada escolha defensável.
Nada de código de produto no vídeo inteiro.

**A frase que costura tudo:**
> O modelo decide o que dizer. O código decide o que pode ser feito.

**E a versão dela para o harness (dizer na cena 4):**
> O `CLAUDE.md` pede. O CI impõe.

---

# CENA 1 — O problema

**Tela:** `suajornadadedados/desafio-jornada/desafio-vendas`, README aberto.

**Falo:**

- O enunciado não tem código, stack nem arquitetura. Tem **um cliente falando**. A ausência
  de resposta *é* o enunciado.
- E ele fala em duas listas: oito linhas do que **quer no produto**, seis do que **teme**.
  Nenhuma das catorze é um requisito de engenharia. Traduzir é o trabalho.

**Abro a seção "O que o Cliente Quer no Produto" e leio linha a linha.** É a tabela que
sustenta a cena — e a coluna do meio é toda minha:

| O cliente quer *(literal, do enunciado)* | O que isso me obriga a decidir | No repositório |
|---|---|---|
| "compreender catálogo e recomendar produtos **por necessidade**" | busca semântica sobre o catálogo — filtro de e-commerce não resolve "presente pra minha sogra" | jornada · RF-1 · S-03 |
| "estoque, preço e prazo **sempre sincronizados** com banco de dados" | o modelo **nunca** afirma preço de memória: tool que lê o banco no momento da criação do pedido | R1 · ADR-001 · S-03 |
| "conversa que chegue até o final da venda" | checkout dentro do fluxo do agente, com total calculado por código | RF-2 · S-04 |
| "aprovação de equipe em pontos irreversíveis" | o grafo **pausa** antes de emitir, com estado persistido e aprovação gravada | R3 · ADR-003 · S-05 |
| "auditoria completa dos atendimentos" | trace por sessão desde o commit 1 — não observabilidade como fase de deploy | R5 · ADR-007 · S-02 |
| "visibilidade de custos com IA" | budget cap e timeout por tool, medidos no mesmo trace | R6 · RNF-3 |
| "proteção de dados em todas as camadas" | PII mascarada **na origem**, não limpa na saída | R5 · ADR-007 |
| "sistema que sua equipe consiga colocar para rodar" | quickstart em 10 min com tudo mockado, e o harness versionado junto do código | RNF-1 · ADR-005 |

**⏸ Parar aqui — é a cena que abre o vídeo.** Aponto para uma linha só, a segunda:

> O cliente escreveu **"sempre sincronizadas com banco de dados"**. São cinco palavras.
> Quem decidiu que elas significam *"o modelo não tem permissão de dizer um preço — ele chama
> uma tool que lê o Postgres no momento da criação do pedido"* fui eu.

É esse o salto, e ele se repete nas oito linhas. **O enunciado entrega o desejo; o requisito
é meu** — e a coluna da direita existe pra provar que cada desejo virou arquivo, não intenção.

**Um dos medos dele não tem linha correspondente no produto — e é o mais perigoso:**

> "Proteger contra manipulação conversacional"

Não virou item da lista porque não se vê na tela. E é o único em que a solução óbvia é a
errada: escrever *"nunca dê desconto"* no prompt. Isso some no diff, passa na revisão e
**não garante nada** — prompt é pedido, não garantia.

Minha decisão: **desconto não existe como ação disponível a nenhum agente.** Não é negado,
não está lá. Segurança por arquitetura, não por comportamento do modelo. *(D4 · ADR-002 · R4)*

**As duas colunas que o enunciado não escreve:**

| Como eu decidi resolver | O que eu recusei |
|---|---|
| **D3** — nunca de memória: catálogo por RAG, preço por consulta ao banco | ✕ pôr o catálogo no prompt e confiar |
| **D4** — registro de tools por subagent; recomendação read-only por construção; desconto não existe | ✕ escrever "nunca dê desconto" no prompt |
| **D5** — o grafo pausa antes de emitir, com estado persistido e aprovação gravada | ✕ avisar por e-mail depois de emitir |
| **D10** — mascaramento na origem, não na saída | ✕ limpar os logs depois |
| **D10 · RNF-3** — budget cap e timeout por tool, medidos no mesmo trace | ✕ olhar a fatura no fim do mês |
| **D10** — trace desde o commit 1, não como fase de deploy | ✕ deixar observabilidade pro final |

> **É essa fronteira que dá origem ao `docs/requisitos.md` e ao `decisoes.md`.** O desafio
> entrega o desejo do cliente; da tradução em diante, o repositório é o único lugar onde a
> decisão existe.

**E existe um segundo problema, que o enunciado não menciona:** construir tudo isso **com um
agente de código**. Três coisas dão errado, e o resto do vídeo é a resposta a elas:

| | O problema | Onde eu resolvo |
|---|---|---|
| **P1** | Contexto volátil — expliquei na segunda, na quinta ele reinventa | cena 3, harness |
| **P2** | Sem portão — plausível ≠ correto, e eu aprovo porque *parece* certo | cena 4, CI |
| **P3** | Processo invisível — o repo mostra o resultado, esconde o raciocínio | cena 2, discovery versionada |

**A última coisa que o enunciado faz é perguntar.** Seis perguntas em "Antes de Codar", e ele
para. Cada documento da discovery é a resposta escrita de uma delas:

| A pergunta do enunciado | O arquivo que responde |
|---|---|
| "Qual é a jornada completa do cliente?" | `docs/jornada.md` |
| "Onde linguagem natural gera valor vs. risco?" | `docs/jornada.md` — a coluna *quem resolve* |
| "O que é irreversível e precisa de aprovação?" | `docs/riscos.md` R3 → ADR-003 |
| "Onde você precisa de garantia absoluta?" | `docs/riscos.md` — a 4ª coluna, *verificação* |
| "Como medir sucesso com números?" | `docs/PRD.md` §2 |
| "O que fica de fora da primeira versão?" | `docs/PRD.md` §3 — com motivo |

> **O enunciado pergunta; o repositório responde.** É por isso que a próxima cena é
> documentação, e não código.

---

# CENA 2 — Discovery

**Tela:** pasta vazia.

```bash
git init -b main
```

**Repositório público desde o commit 1.** O enunciado pede processo visível; esperar ficar
bonito apaga justamente a parte que tem valor.

**Duas recusas de método, antes do primeiro arquivo:**

- **Documento versionado, não Notion.** Fora do diff, em duas semanas código e documento
  discordam sem ninguém notar.
- **Uma spec = uma branch = uma sessão; cada task = um commit.** Recusei a sessão longa:
  contexto degrada e o PR fica irrevisável. *(vira o ADR-005 — volta na cena 4)*

**A ordem importa: cada documento consome o anterior.**

| # | Arquivo | A frase que eu falo | Commit |
|---|---|---|---|
| 1 | `docs/requisitos.md` | As oito linhas do que o cliente quer, com a **minha tradução** ao lado. Origem declarada de todo o resto. | `docs(discovery): requirements translated from the brief` |
| 2 | `docs/jornada.md` | Cada etapa classificada em **quem resolve**: LLM, LLM ancorado, ou código puro. IA não é camada — é componente **posicionado**. | `docs(discovery): customer journey` |
| 3 | `docs/riscos.md` | Risco + tratamento é o mínimo. Eu boto uma 4ª coluna: **verificação automatizada**. | `docs(discovery): risk matrix` |
| 4 | `docs/PRD.md` | Fora de escopo **com motivo**, e toda métrica com número. | `docs(discovery): product requirements` |
| 5 | `docs/decisoes.md` + `docs/adr/` | Índice + argumento. ADR exige 2 alternativas e as consequências **negativas** aceitas. | `docs(discovery): decisions and ADRs` |
| 6 | `docs/specs/` + templates | S-00 a S-09. Cada spec fecha um risco antes do próximo aparecer. | `docs(discovery): specs and templates` |

**⏸ Parar em `requisitos.md`:** são duas tabelas, e a segunda é a que interessa —
**o que eu recusei em cada linha**. É o único lugar do repositório onde a alternativa
descartada fica visível ao lado da adotada. Sem ela, toda decisão parece óbvia em retrospecto.

**⏸ Parar em `riscos.md`:** a frase que governa o documento é
**"risco sem verificação é desejo, não requisito"**. Sem a 4ª coluna, o documento envelhece em
silêncio — alguém muda o prompt, o risco volta, e o papel continua dizendo que está mitigado.

**⏸ Parar em `ADR-006`:** o que define qualidade aqui **não é um número numa tabela** — é um
conjunto de casos, cada um carregando o critério que o reprova. Fato inventado ou ação fora da
allowlist reprovam a suíte inteira, sem média e sem negociação. Guardar essa ponta: ela volta
na cena 4.

**⏸ Parar nas specs:** observabilidade é a **S-02, não a S-08**. Inversão deliberada —
depurar agente sem trace é adivinhação. Rastreabilidade não é feature, é pré-requisito
pra trabalhar.

**⏸ E o que quase ninguém faz na discovery — abro `evals/`:**

Sete arquivos YAML, quatro golden e três adversariais, escritos **antes de existir agente**.
Cada um carrega o critério que o reprova dentro dele mesmo — não existe arquivo de rubric
neste repositório, e isso é decisão registrada, não esquecimento *(ADR-006)*.

Abro `evals/adversarial/adversarial-001-injecao-de-desconto.yaml` e leio o bloco
`tools.proibidas`. Tem `aplicar_desconto` ali. **Essa tool não existe em lugar nenhum do
sistema** — e o caso serve exatamente para provar que ela continua não existindo.

> A pergunta que fecha a cena: *como você sabe que o atendimento está bom?* Se a resposta só
> aparece depois que o agente existe, ela vai ser escrita para caber no que o agente já faz.
> Por isso a régua vem antes. **A métrica de qualidade é artefato de discovery.**

Commit: `eval(discovery): golden and adversarial seed cases`

**Fecho a cena com o diagrama:** `docs/img/fluxo-discovery.svg`, tela cheia.

```
requisitos → jornada → riscos → PRD → ADRs → specs → | linha do código | → S-00..S-09
```

É esse encadeamento, não os arquivos soltos, que atende ao "processo visível". E a linha
tracejada do diagrama é o argumento inteiro do vídeo em uma imagem: **tudo isso aconteceu
antes da primeira linha de código de produto.**

---

# CENA 3 — Harness

*A cena 2 produziu documentos corretos. Nada garante que o agente vá lê-los.*

**Abro pelo enunciado:** no meio dos entregáveis tem uma linha discreta —
*"Repositório preparado: com harness de agentes, contexto e processos visíveis"*.
É a decisão que não aparece na demo e define a qualidade de tudo o que vem depois. **P1.**

### `CLAUDE.md`

**A decisão é sobre o que NÃO está nele.** ~40 linhas, de propósito: esse arquivo é carregado
inteiro em **toda** sessão. Cada linha é imposto fixo sobre o contexto.

Só entra o que é verdade em 100% das sessões: o que é o projeto, a regra de ouro, **ponteiros**
para os normativos (não o conteúdo), o fluxo, os guardrails.

> **Regra prática:** se a instrução começa com *"quando"*, é skill. Se começa com *"sempre"* ou
> *"nunca"*, é `CLAUDE.md`.

### `.claude/commands/` — quatro rituais

Cada `.md` vira um `/comando` que **eu** disparo.

| Comando | Pra quê |
|---|---|
| `/escrever-spec` | Obriga todas as seções, inclusive métrica com número |
| `/entregar-spec` | Fora do escopo → registra em *Descobertas* e **não implementa** |
| `/verificar-spec` | **O mais importante do repositório** |
| `/registrar-adr` | Exige 2 alternativas e as consequências negativas |

**⏸ Parar em `/verificar-spec`:** não é um pedido de revisão, é a definição de um **papel com
poderes restritos**. Declara "você é o REVISOR, não é o autor", lista o que pode ler (spec,
diff, testes que ele mesmo rodar), e **proíbe corrigir o código**. Revisor que conserta vira
autor — e aí ninguém revisou.

### `.claude/skills/` — 24 diretórios

**Por que existe:** eu não sei o jeito idiomático de usar `interrupt` no LangGraph. O modelo
tem uma noção, geralmente desatualizada.

| Mecanismo | Carrega quando | Serve pra |
|---|---|---|
| `CLAUDE.md` | Sempre | Invariante universal |
| Comando | **Eu** digito `/nome` | Ritual que eu inicio |
| **Skill** | **O modelo** julga relevante | Competência condicional |

Skill carrega sob demanda (**progressive disclosure**): o modelo só lê `name` + `description`
até precisar. Por isso dá pra ter 24 com custo quase zero — e por isso a `description` é a
parte mais importante da skill.

**A decisão que vira ADR: vendorizar, não plugar.** Skills copiadas pro repo, com SHA fixado.

- **O cliente pediu que o time conseguisse replicar:** com plugin, quem clona recebe o código
  e **não** recebe o harness.
- **Fecha com a Decisão 3:** plugin que auto-atualiza pode mudar o comportamento **entre a
  implementação e a verificação da mesma spec** — e aí a divergência pode ser da skill, não do
  código. SHA fixado é o que torna `/verificar-spec` uma comparação honesta.
- **Limite:** vendoriza-se markdown, não se vendoriza software (o de 16 MB fica como plugin).

**De onde vieram:** `mattpocock` (disciplina: tdd, code-review, grill-with-docs) ·
`langchain-ai` (HITL, persistence, RAG, middleware, evals) · `langfuse` (traces, PII) ·
`shadcn-ui` (frontend).

**⏸ Parar no que eu recusei** — diz mais sobre o critério que a lista do que aceitei:
`ask-matt`/`triage`/`to-tickets` pressupõem issue tracker, que **compete** com o SDD;
`langsmith-*` **conflita com o ADR** que escolheu Langfuse — skill que empurra a concorrente é
pior que skill ausente.

**⏸ E a skill própria (`vendinha-harness`):** as 23 estão certas isoladamente e nenhuma sabe
das decisões deste projeto. O exemplo que justifica ela inteira: `langchain-rag` ensina
"gere a resposta a partir do contexto recuperado" — aplicado a **preço**, isso viola a regra de
ouro, com código idiomático e revisão limpa. A skill própria declara a precedência
(normativo > skill) e resolve o conflito antes dele acontecer.

### `docs/testes.md` — o pedido que eu **não** faço

*Aqui está a parte do harness que mais mudou meu resultado, e é a menos glamourosa.*

O jeito comum de pedir teste para um agente é: *"escreve os testes"*. Isso produz cobertura
de superfície — teste do que é fácil testar, não do que é caro errar. E, pior: **cada sessão
nova reinventa a estratégia**. É o P1 outra vez, aplicado a teste.

Abro `docs/testes.md` e mostro a tabela. Nove linhas, uma por risco:

> | Risco | Tipo | Seam — onde se observa | Arquivo |
> |---|---|---|---|
> | **R2** Executa ação indevida | unit | o registro `subagent → tools`, lido como dado | `test_permission_boundary.py` |

**A frase da cena:**

> Eu não peço "escreva testes". Eu declaro **o seam** e **o risco que cada teste fecha**.

Isso sai direto da 5ª coluna do `riscos.md` — o documento já dizia qual era a verificação de
cada risco. O `testes.md` só responde *onde ela mora*.

**E aqui a skill própria trabalha de novo.** A skill `tdd` do Matt Pocock manda **perguntar ao
usuário quais são os seams** antes de escrever qualquer teste. É um bom conselho genérico — e
aqui é uma pergunta já respondida. A `vendinha-harness` declara isso, e economiza uma rodada
de negociação por sessão. Duas linhas da tabela não são negociáveis: **R2** e **R3**. Não são
cobertura — são o requisito.

**Último detalhe, que parece burocracia e não é:** todo teste declara no docstring o `R#` que
fecha. É o que deixa o `/verificar-spec` responder *"quais riscos esta spec fecha e qual teste
prova cada um"* sem precisar ler a implementação.

**Commits:** `docs(harness): CLAUDE.md` · `docs(harness): rituals as slash commands` ·
`chore(harness): vendor skills with pinned sources` · `adr(harness): ADR-009 vendored skills` ·
`docs(harness): testing convention mapping risks to seams`

---

# CENA 4 — Portões

*Até aqui é tudo instrução, e o agente "geralmente" obedece. Geralmente não é garantia.*

> **O `CLAUDE.md` pede. O CI impõe.**

### Por que existe uma pasta `.github/`

É o único lugar onde eu escrevo arquivos que **o GitHub executa por mim** — inclusive quando eu
não quero. É a fronteira entre "eu prometi" e "o sistema exige".

| Arquivo | O que ele garante |
|---|---|
| `PULL_REQUEST_TEMPLATE.md` | PR que conta uma história, com evidência anexada |
| `workflows/ci.yml` | *"validações automáticas que **bloqueiam**"* — literal no enunciado |
| `CODEOWNERS` | a qualidade não regride em silêncio |
| `commitlint.config.js` *(raiz)* | histórico legível: qual spec produziu cada mudança |

**PR template:** exige screenshot **e link do trace**. Screenshot prova que a tela apareceu;
trace prova o que o agente decidiu, consultou, executou e gastou — que é o que
"rastreabilidade total do atendimento" significa na prática.

**commitlint:** escopo **obrigatório** (`s-04`, `harness`). Com ele, `git log --oneline` mostra
qual spec produziu cada mudança. Tipos `spec`, `adr`, `eval` fazem o processo aparecer no log.

**CI — quais validações e por quê:**

| Job | Barra |
|---|---|
| `commitlint` | Histórico ilegível |
| `lint` | Estilo e erro estático, na raiz inteira |
| **`test`** | **`unit` + `security` — regressão funcional e de fronteira** |
| `secrets` | Credencial no diff |
| `skills-drift` | Skill editada à mão fora do lockfile |
| `typecheck` | Tipo quebrado (a partir da S-00) |
| **`evals`** | **Regressão de qualidade do agente (a partir da S-06)** |

**⏸ Parar em `test` — e explicar por que ele tem DUAS pastas e não três.**

Abro `tests/` e mostro: `unit/` e `security/`. A diferença é a cena inteira:

> `unit/` pergunta *"a conta está certa?"*. `security/` pergunta *"a conta errada é sequer
> **alcançável**?"*

Um teste unitário verde diz que o total foi somado direito. Um teste de segurança verde diz
que o subagent de recomendação **não possui** a tool de escrita — não que foi instruído a não
usá-la. **Só o segundo sobrevive a uma troca de modelo.**

E o detalhe que vale falar em voz alta: **não existe camada de integração aqui.** É escolha com
preço. O que só se prova com infraestrutura de verdade — retomada após restart real do processo
— é verificado **à mão** no `/verificar-spec`, e isso está escrito no `docs/testes.md` para
ninguém achar que está automatizado. A troca: o job `test` do CI não sobe contêiner nenhum e
roda em segundos.

**⏸ E mostrar o `scripts/run-tests.sh`,** que é uma decisão de dez linhas com opinião dentro.
O pytest sai com código 5 quando não coleta nada. Tratar isso como sucesso em silêncio é o
check decorativo que este repo recusa; tratar como falha deixaria o CI vermelho até a S-02.

A regra que escrevi: **suíte vazia é aceitável enquanto `backend/` não existe, e vira falha no
instante em que ele existir.** O portão se aperta sozinho quando o código chega.

### O portão local: `pre-commit`

**O CI é o portão remoto. O `pre-commit` é o local** — barra antes de virar PR.

Ruff, ruff-format, detecção de segredo, commitlint no `commit-msg`. E uma decisão pequena que
importa: **o `pytest` fica no `pre-push`, não no `pre-commit`**. Hook lento treina a usar
`--no-verify`, e aí você desativou o portão local inteiro para ganhar dois segundos.

Outra: `.claude/skills/` está **excluído** de todo hook que reescreve arquivo. Um hook
bem-intencionado arrumando espaço em branco lá dentro criaria exatamente o drift que o
`skills-drift` existe para reprovar. O portão brigando com o portão.

### A decisão sobre check vermelho

`typecheck` e `evals` dependem de `backend/`, que só nasce na S-00. A saída preguiçosa é deixar
vermelho até lá. Mostro a linha:

```yaml
if: ${{ hashFiles('backend/pyproject.toml') != '' }}
```

Eles ficam **skipped** em vez de vermelhos, e ligam sozinhos quando a S-00 entrar.

> Check vermelho permanente não é rigor: é treino. Você aprende a ignorar CI vermelho, e no dia
> em que um ficar vermelho **de verdade**, você ignora também.

**⏸ Parar em `evals`:** CI que roda teste unitário é higiene. CI que roda o **golden dataset**
contra o agente inteiro e reprova quando um caso quebra é outra coisa. É a única forma de
garantir que mudar um prompt não degrade o atendimento sem ninguém notar.
*(Só vira check obrigatório na S-06, junto com o código que o deixa verde — check vermelho
permanente treina a ignorar CI vermelho.)*

### Proteção da `main`

PR obrigatório · checks obrigatórios · **squash-only** · branch deletada no merge.

**Squash-only:** a `main` conta a história em nível de **spec**, a branch em nível de **task**.

**Zero aprovações humanas exigidas — e isso é honesto.** Sou o único humano; exigir aprovação
em repo solo produz teatro. A revisão real está no `/verificar-spec` em sessão nova, com
relatório anexado ao PR e cobrado no checklist.

**⏸ Parar no CODEOWNERS — aqui ele deixa de ser burocracia.** Ele protege `evals/`,
`docs/adr/`, `PRD.md` e `.claude/`.

> Sem isso, um PR com eval vermelho ficaria verde **editando o caso que reprovou**.
> O gate só é real se os arquivos que o definem forem protegidos.

*(É a ponta que ficou solta lá na cena 2.)*

### O portão em funcionamento — uma volta do loop

Portão que nunca barrou nada é decoração, então eu mostro a volta inteira, ao vivo:

```
1. Sessão nova → /entregar-spec S-00
2. Peço algo FORA do escopo → mostro a recusa + registro em "Descobertas"
3. PR com o template preenchido
4. CI roda → mostro os checks travando o merge
5. SESSÃO NOVA → /verificar-spec S-00          ← ponto alto
6. Relatório vira comentário no PR
7. Merge por squash
```

**O passo 5 sustenta a cena.** Uma sessão que nunca viu a implementação lê a spec, roda os
testes e emite veredito. **Se ela reprovar algo que eu achava pronto, não corto.** É o
**P2** resolvido: deixei de ser eu aprovando o que *parece* certo.

**Commits:** `docs(harness): PR template requiring trace evidence` ·
`ci(harness): validation pipeline that blocks` · `chore(harness): branch protection and codeowners`

---

# CENA 5 — Arquitetura

**Tela:** `docs/img/arquitetura-produto.svg`, tela cheia (abrir no navegador — é vetor, dá zoom
sem borrar).

**Abro assim:** *"Repare que eu cheguei na cena 5 sem citar um framework."* A arquitetura é a
última coisa do vídeo **de propósito**. Ela não foi escolhida no começo — ela **caiu por
gravidade** das decisões das quatro cenas anteriores. Se eu tivesse aberto por aqui, cada
escolha seria gosto pessoal. Depois das decisões, cada uma tem um *porque*.

### A stack — e a decisão que obrigou cada linha

| Camada | Escolha | A decisão que a exigiu | O que recusei |
|---|---|---|---|
| Linguagem | **Python 3.12** | ecossistema de agente e RAG maduro; contrato Pydantic em toda fronteira (RNF-5) | ✕ Node no backend: tipagem boa, ecossistema de agente mais raso |
| Orquestração | **LangGraph** | D5 · ADR-003 — `interrupt` com **estado persistido** em checkpointer. A pausa antes da NF não é UX, é primitivo | ✕ agente em loop com um `if` no meio: pausa que morre junto com o processo |
| Observabilidade | **Langfuse Cloud** | D10 · ADR-007 — trace por sessão e mascaramento de PII **na origem**; D13 · ADR-010 — é o mascaramento que garante privacidade, não a topologia | ✕ LangSmith: não porque "a PII sairia da infra", e sim porque não tem saída — Langfuse é open-source |
| API | **FastAPI** | ADR-004 — Pydantic → OpenAPI → cliente TS **gerado**; SSE nativo pro streaming do chat | ✕ Flask/Django: OpenAPI não sai de graça |
| Dados | **Postgres + Qdrant** | Postgres é a fonte da verdade de preço **e** o checkpointer do grafo (RNF-6); Qdrant carrega o catálogo semântico | ✕ pgvector: um serviço a menos, mas fundiria a busca semântica com a fonte da verdade — quero essa fronteira visível |
| Frontend | **React + Vite** | dois consumidores da mesma API: chat do cliente e fila do operador (RF-4) | ✕ Next/SSR: nada aqui precisa de SEO |
| Empacotamento | **Docker + compose** | *"sistema que sua equipe consiga colocar para rodar"*: um comando, tudo mockado (RNF-1) | ✕ instruções de instalação num README |

**⏸ Parar nessa linha — é a única do vídeo em que eu mostro uma decisão que eu MUDEI.**

O ADR-007 dizia Langfuse **self-hosted**, e o motivo escrito para recusar o LangSmith era
*"a PII sairia da infra"*. Ao montar a S-00 percebi que esse argumento **não sobrevive ao
próprio ADR-007**: se o mascaramento acontece na origem, PII nunca entra no trace — não existe
PII para sair de lugar nenhum. Eu estava me protegendo de um vazamento que a decisão anterior
já tinha eliminado, e pagando por isso com três contêineres a mais no quickstart.

Abro os dois lado a lado — `ADR-007` e `ADR-010`:

> **Não é a hospedagem que garante a privacidade. É o mascaramento.**
> Self-hosted com trace ingênuo vaza PII para o próprio log. Cloud com mascaramento na origem
> não tem o que vazar.

Duas coisas para apontar, e são as que valem a cena:

1. **Eu não editei o ADR-007.** Ele continua lá, com o argumento antigo. O ADR-010 o substitui
   **só no ponto de hospedagem**, e o 007 ganhou uma linha apontando para isso. Editar o
   antigo apagaria a linha do tempo — que é justamente o que o desafio quer visível.
2. **O motivo de recusa do LangSmith teve que ser reescrito.** Se eu tivesse deixado *"a PII
   sairia da infra"* na tabela, a página inteira ficaria incoerente com a própria escolha. O
   motivo honesto é outro: Langfuse é open-source, então trocar nuvem por self-hosted é
   variável de ambiente, não reescrita. **A decisão de hospedagem é reversível; a de
   fornecedor não seria.**

E uma consequência que aparece no `riscos.md`: o teste de redação de PII deixou de ser
conveniência e virou **invariante de release**. Antes, uma falha vazava para um contêiner na
minha máquina. Agora vaza para fora.

> É isso que um ADR compra. Sem ele, essa mudança seria um commit de uma linha trocando uma
> variável de ambiente, e o argumento errado ficaria no repositório para sempre.

### O desenho — quantos agentes e onde entra o humano

```
                        ┌── subagent RECOMENDAÇÃO ──── tools READ-ONLY ──── Qdrant · Postgres
 cliente ──chat(SSE)──▶ supervisor ──┤
                        └── subagent CHECKOUT ──────── tools de escrita ─── Postgres · Mercado Pago (sandbox)
                                     │
                       webhook de pagamento  ← zero IA, idempotente, origem verificada
                                     │
                        ⏸  I N T E R R U P T  ──▶ fila do operador ──▶ aprova / rejeita  (quem + quando)
                                     │
                              emitir_nf ──▶ port NFEmitter ──▶ MockAdapter │ HomologacaoAdapter
```

**Três coisas pra apontar no desenho — e só três:**

1. **A separação dos subagents é a fronteira de permissão.** O de recomendação não tem tool de
   escrita. Não porque o prompt proíbe — porque ela **não está registrada nele**, e um teste
   unitário falha se vazar. *(ADR-002)*
2. **O ⏸ é o único ponto onde o sistema para sozinho.** Estado persistido no Postgres; a
   retomada só existe a partir de um registro de aprovação. Sem registro, não há caminho de
   volta — por construção, não por disciplina. *(ADR-003)*
3. **Tudo que sai pra fora atravessa um port.** Gateway e emissor são adapters, o default é
   mock — é por isso que o quickstart roda sem conta em serviço nenhum. *(ADR-004)*

### Fecho do vídeo

**Amarro nos três problemas da cena 1:** contexto virou artefato (**P1**) · portão virou CI +
verificação independente (**P2**) · processo virou histórico navegável (**P3**).

**E a última frase:**
> A arquitetura é a parte fácil. Ela é o que sobra depois que você decidiu o que o modelo
> **não** tem permissão de fazer.

**Commits:** `docs(arch): architecture diagram and stack rationale`

---

# Cola de gravação

- [ ] Abrir com o **enunciado**, não com o repositório. O vídeo começa no problema.
- [ ] Ler **"O que o Cliente Quer no Produto"** na tela do enunciado, linha a linha, antes de
      abrir qualquer arquivo. É a cena 1 inteira.
- [ ] Bater na linha do **"sempre sincronizadas com banco de dados"** — é o exemplo do salto.
- [ ] `git log --oneline` sempre à mão — o histórico é o argumento.
- [ ] Gravar a **recusa de push direto na `main`**.
- [ ] Gravar a **mesma pergunta antes e depois das skills**: *"como implemento a pausa para
      aprovação?"* — sem skill vira `input()` bloqueante; com skill vira interrupt + registro.
- [ ] Gravar `/verificar-spec` **reprovando** algo, se rolar (cena 4).
- [ ] Deixar o **diagrama pronto e exportado** antes de gravar a cena 5 — não desenhar ao vivo.
- [ ] Chaves fora do terminal visível.
- [ ] Gravar o **`pre-commit` barrando um commit** — meter um segredo falso num arquivo e
      tentar commitar. Portão que nunca barrou nada é decoração (cena 4).
- [ ] Gravar `bash scripts/run-tests.sh` **duas vezes**: como está (avisa que a suíte está
      vazia e passa) e com uma pasta `backend/` vazia criada na hora (reprova, dizendo que
      feature sem teste não é estado válido). É o portão se apertando sozinho (cena 4).
- [ ] Ter `ADR-007` e `ADR-010` abertos lado a lado antes de começar a cena 5.
- [ ] **Trocar `@SEU-USUARIO-GITHUB` no `.github/CODEOWNERS`** antes do push. Handle errado faz
      o GitHub ignorar a regra sem avisar — e o portão fica decorativo na gravação.

**Se travar, as 5 frases-âncora:**
1. O modelo decide o que dizer; o código decide o que pode ser feito.
2. Risco sem verificação é desejo, não requisito.
3. O `CLAUDE.md` pede; o CI impõe.
4. Se começa com "quando" é skill; se começa com "sempre/nunca" é `CLAUDE.md`.
5. Eu não peço "escreva testes" — eu declaro o seam e o risco que cada teste fecha.

---

<details>
<summary><b>Reserva — se perguntarem nos comentários</b></summary>

**Por que não GitFlow?** Existe para múltiplas versões em produção. Aqui há uma. Branch a mais
esconde a história.

**Por que ADR é imutável?** Mudou, novo ADR substitui. Editar o antigo apaga a linha do tempo —
que é o que o desafio quer visível.

**Por que `.github/` tem que estar na raiz?** O GitHub só lê de lá. Numa subpasta o CI nunca
roda **e nunca falha** — você acha que está protegido e não está.

**Por que `settings.json` versionado mas `settings.local.json` não?** O primeiro é comportamento
do projeto (vale pra quem clonar); o segundo é preferência da minha máquina.

**`.gitignore` já não protege o `.env`?** Ele impede o *commit*. A regra de permissão impede a
*leitura* pelo agente — segredo lido entra no contexto, e contexto sai da máquina.

**Por que só 2-3 cenários BDD por spec?** Limite forçado pra obrigar a escolher o essencial.
Spec com 15 cenários ninguém lê e ninguém verifica.

**A Vendinha atende ao "case próprio"?** O enunciado pede negócio, cliente, produto e personas
com nomes reais. A Vendinha é exatamente isso — e está batizada no PRD. Ela é *também* a
referência do workshop: quem participa troca o domínio, o método é idêntico.

**Por que a arquitetura só aparece no fim?** Porque é a única ordem honesta. Escolher LangGraph
antes de saber que existe um ponto irreversível no fluxo é escolher por moda. Depois do
`riscos.md`, `interrupt` com estado persistido deixa de ser preferência e vira requisito.

</details>
