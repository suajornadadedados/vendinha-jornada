---
spec: S-07
veredito: APROVADO COM RESSALVAS
commit: 35591cb71b0a7e47226d76bac29cf743a19ed7a8
branch: fix/s-07-sessao-por-atendimento
data: 2026-08-29
---

# Relatório de verificação independente — S-07, rodada 2 (DESC-10: um atendimento por sessão)

> A rodada 1 (2026-08-28, `spec/s-07-frontend` @ `57f80cb`) está preservada na íntegra no
> fim deste arquivo. Este cabeçalho e este veredito são os da **rodada 2**.

| | |
|---|---|
| **Spec** | `docs/specs/S-07-frontend-integrado.md` (`status: em-revisao`) |
| **Branch** | `fix/s-07-sessao-por-atendimento` @ `35591cb` — **1 commit** sobre `origin/main` |
| **Base** | `origin/main` @ `261a861` — é o merge-base exato; diff não inflado |
| **PR** | **não existe** no momento da verificação |
| **Escopo do diff** | 6 arquivos · +241 / −26 — `app.py`, `observability.py`, a spec, `Widget.tsx`, `useConversa.ts`, `test_observabilidade.py` |
| **Suíte** | **1029 passed**, 0 failed, 0 error, 0 skipped, 122 s (`tests/unit` + `tests/security`) |
| **Lint** | `ruff check .` → *All checks passed* · `ruff format --check .` → 162 arquivos ok |
| **Typecheck** | `mypy` backend 46 arquivos · `mypy` tests 34 arquivos · `tsc -b --noEmit` — os três limpos |
| **Contrato (REQ-1)** | regerei `openapi.json` + `schema.d.ts`: `git diff --exit-code` → 0. **Sem drift** |
| **Build do frontend** | `npm run build` ok — duas entradas, `site` 27,99 kB e `admin` 366,06 kB |
| **Evals** | **nenhuma suíte afetada** — `python -m vendinha.evals.afetadas` devolve vazio, exit 0. Nenhum prompt no diff |
| **Skills** | `bash scripts/vendor-skills.sh --check` → *OK* (fecha a NC-1 bloqueante da rodada 1) |
| **Navegador** | **NÃO EXECUTADO** — ver "Não verificável, e por quê" |
| **Achados** | 2 Alta · 4 Média · 5 Baixa |
| **Veredito** | **APROVADO COM RESSALVAS** |

---

## Enquadramento recebido

A mensagem que iniciou esta sessão continha **apenas o id da spec** (`S-07`). Nada a registrar:
nenhum resultado antecipado, nenhum arquivo apontado, nenhuma restrição de execução. É o
formato que o `CLAUDE.md`, fluxo item 4, descreve.

Registro por completude que a rodada 1 **teve** enquadramento — o prompt daquela sessão proibiu
evals e falsificação — e que aquele relatório o declarou. Nesta rodada não houve.

---

## O que este commit se propõe a fazer

Um conserto em três partes (DESC-10) mais uma mudança que viaja de carona:

1. a persistência do `session_id` em `localStorage` sai;
2. o botão do canto passa a significar "atendimento novo" (`reiniciar()` antes de abrir);
3. um contador de geração cala o stream do atendimento anterior;
4. *(carona)* um filtro que suprime o 404 de `/metrics` no log de acesso do uvicorn.

---

## Conformidade — o que este diff toca

| Item | Veredito | Evidência |
|---|---|---|
| DESC-10 parte 1 — persistência removida | **CONFORME** | `grep -rn "localStorage" frontend/src/` → **zero ocorrências**. O único armazenamento restante é `sessionStorage["vendinha:operador"]` em `api/client.ts`, que é o token do operador e está declarado "fora de escopo" na spec |
| DESC-10 parte 2 — atendimento novo de verdade | **CONFORME** | `reiniciar()` zera `sessaoAtual.current` **e** `sessionId` (`useConversa.ts:343-353`), e `enviar` só monta `corpo["session_id"]` quando a ref é truthy (`:237`). Conferido contra o backend: `app.py:580-581` faz `sessao_nova = payload.session_id is None` / `session_id = payload.session_id or uuid.uuid4().hex` — omitir o campo é mesmo o que abre sessão nova. A afirmação da DESC-10 de que "o backend nunca teve o defeito" é **verdadeira** |
| DESC-10 parte 3 — o stream anterior cala | **CONFORME, e mais forte do que o texto promete** | `minha`/`atual()` guardam o topo do laço (`:243`), o `catch` (`:316`) e o `finally` (`:321`) — as três saídas, não só a do laço. E o `return` antecipado não apenas ignora o stream: sair de um `for await` chama o `return()` do gerador, que executa o `finally` de `sse.ts:78-82` e faz `leitor.cancel()`. A conexão HTTP é de fato cancelada, não deixada correndo. O `setSessionId(null)` ainda derruba a assinatura de `/eventos/sessao/{id}` pelo cleanup do `useEffect` (`assinar` → `vivo=false; controlador.abort()`) |
| Filtro de `/metrics` — a forma do registro | **CONFORME** | O docstring afirma que o uvicorn loga com cinco args posicionais e sem `extra`. Conferi na fonte instalada: `uvicorn/protocols/http/h11_impl.py:481-489` — `'%s - "%s %s HTTP/%s" %d'` com `(client_addr, method, path_with_query, http_version, status)`, na ordem exata que o filtro lê. A afirmação não é decorativa |
| REQ-8 — `session_id` em `localStorage`, F5 não perde a conversa | **NÃO CONFORME** | Ver NC-1 |
| REQ-6 / RF-3.6 — o cliente recebe a NF sem perguntar | **CONFORME durante a sessão viva · REGREDIDO após reload** | Ver NC-2 |
| `riscos_cobertos: []` | **CONFORME** | Cruzado com `docs/riscos.md`: nenhuma linha da matriz R1-R10 atribui risco à S-07. A R9 ("estado corrompido em conversa longa") é da **S-02** e é server-side (checkpointer); este diff não a toca, e `tests/unit/test_session_resume.py` segue verde |
| Segredo / CPF / CNPJ / certificado no diff | **LIMPO** | Varredura por `sk-`, `pk-`, `api_key`, `secret`, `password`, `BEGIN PRIVATE`, máscara de CPF e de CNPJ: zero. O único literal de rede é `127.0.0.1:54895` numa fixture de teste — loopback |
| PII mascarada | **SEM REGRESSÃO** | O filtro novo entra no logger `uvicorn.access`; a redação entra nos *formatters* dos handlers. Ordem em `app.py:221-222` é redação primeiro. Descartar a linha de um 404 de `/metrics` não pode descartar PII que devesse ser logada |
| Fronteira de permissão de subagents | **INTOCADA** | nenhum arquivo de subagent no diff |

---

## Leitura dos testes-âncora (o passo 4, sem falsificação)

O commit adiciona 8 testes. Todos os 8 são do filtro de `/metrics`; **nenhum** é do DESC-10.

**`test_so_o_404_de_rota_que_nao_servimos_some_do_log`** — afirma comportamento, não reafirma a
implementação. Ele **não** recalcula `path.split("?")[0] in _UNSERVED_PROBES`: nomeia caminhos
concretos e o resultado esperado de cada um. Não passa por vacuidade — são 6 casos com **dois**
desfechos diferentes (2 esperam `False`, 4 esperam `True`), e os 4 positivos são justamente os
casos vizinhos que um filtro largo demais quebraria: `/metricas` (sem o "s" inglês),
`/admin/metricas` (a rota real do painel), `/chat`, e `/metrics` com status 200. Um filtro que
silenciasse todo 404, ou que casasse por prefixo, reprova em pelo menos um deles.

**`test_forma_inesperada_de_registro_e_logada_em_vez_de_quebrar`** — `args=None` deve degradar
para "loga tudo". Comportamento, e o desfecho seguro é o afirmado.

**`test_o_filtro_e_instalado_no_logger_de_acesso`** — é a tentativa de cobrir a fiação, e cobre
**metade** dela. Ver NC-4.

Um limite honesto dos três: eles montam o `LogRecord` à mão. Provam a lógica do filtro contra a
forma que o autor **acredita** que o uvicorn produz. Conferi essa crença na fonte instalada
(acima) e ela está certa hoje; o que nenhum teste cobre é o dia em que o uvicorn mudar a forma —
aí o filtro vira inerte e a suíte continua verde. O docstring antecipa isso e escolhe degradar
para "loga tudo", que é a escolha certa; só não há teste que perceba a degradação.

---

## Métricas de sucesso da spec — o que este diff mudou

| Métrica | Alvo | Medido nesta rodada | |
|---|---|---|---|
| Contas de dinheiro no frontend | 0 | **0** — o diff não introduz aritmética; `Widget.tsx:144` continua só formatando (`toLocaleString`) o `total` que o backend mandou | ok |
| Tipos de fronteira escritos à mão | 0 | **0** — o diff não cria tipo de fronteira; `Veredito` segue alias de `components["schemas"]` | ok |
| Drift `openapi.json` × cliente TS | 0 | **0** — regerado e `git diff --exit-code` = 0 | ok |
| Mensagens copiadas para tabela nova | 0 | **0** — nenhuma tabela no diff | ok |
| Rotas `/admin/*` sem token | 0 | **0** — `tests/security/test_admin_boundary.py` verde | ok |
| Landing sai do bundle sem uma linha de JS do painel | 0 | **>0** — ver NC-8 | falha |
| Jornada completa sem recarregar | 100% | **não medido** (2ª rodada consecutiva) | aberto |
| Atraso evento → tela | ≤ 1s | **não medido** (2ª rodada consecutiva) | aberto |
| Estados distinguíveis só por matiz | 0 | **não medido** (2ª rodada consecutiva) | aberto |

---

## Achados

### NC-1 — Alta — a REQ-8 continua afirmando, com `[x]`, exatamente o que este commit removeu

A REQ-8 diz, literalmente e ainda marcada como entregue:

> `session_id` em `localStorage`: F5 não perde a conversa.

O commit remove todo o `localStorage` do widget, e o F5 passa a perder a conversa inteira —
inclusive a assinatura de `/eventos/sessao/{id}`. A DESC-10 registra a decisão do PO em prosa,
mas o **texto do requisito não foi emendado**, e o diff da spec (`+33 / −0`) só acrescenta a
Descoberta.

A regra de precedência não deixa margem: a spec diz X, o código faz Y, e é não-conformidade
mesmo quando Y é melhor — e aqui Y **é** melhor, o que faz disto uma ressalva sobre a spec e não
sobre o código. Quem abrir este documento em seis meses lerá um `[x]` afirmando um comportamento
que foi retirado de propósito. Conserto: riscar a cláusula na REQ-8 com nota de emenda apontando
para a DESC-10.

### NC-2 — Alta — o cartão de espera da NF continua prometendo o que o commit deixou de cumprir

`Widget.tsx:176-179`:

> Uma pessoa confere os dados antes de emitir. **Você recebe aqui assim que sair — não precisa
> perguntar.**

Antes deste commit, um F5 nessa tela funcionava: o `sessionId` era semeado do `localStorage` na
montagem, o `useEffect` reassinava `/eventos/sessao/{id}`, e o cartão da NF chegava — numa janela
sem histórico, mas chegava, porque o cartão é renderizado a partir do estado `nota` e não de
`itens`. Depois deste commit, `sessionId` nasce `null`, não há assinatura, e o cartão **nunca
chega**. O mesmo vale para o clique no FAB (NC-6).

A DESC-10 reconhece a perda em prosa — *"o cartão de espera promete 'você recebe aqui assim que
sair'"* — e **não muda a frase da tela**. É a única falha que a frase que governa a spec diz que
esta spec pode cometer:

> A UI não é lugar de garantia. É lugar de honestidade. […] O que esta spec pode fazer de errado
> […] é **mentir sobre o que aconteceu**.

Há ainda tensão com um normativo **acima** da spec: o ADR-015 escreve, nas consequências
positivas, que com o push por sessão *"o verbo 'receber' do RF-3.6 volta a ser verdade"*, sem
qualificar "desde que não recarregue". Registrar a dívida num documento não torna a tela honesta.
O conserto cabe numa oração ("mantenha esta janela aberta"), e é mais barato do que a rota nova
que a DESC-10 corretamente adia.

### NC-3 — Média — o conserto que dá nome ao commit não tem teste nenhum, e a falta de camada não virou Descoberta

`docs/testes.md` §3.1 — precedência 4, **acima** da spec:

> Toda feature nova nasce com teste unitário. […] Se a task não tem teste, ela não está pronta —
> e não vira commit.

Os 8 testes deste commit cobrem integralmente a mudança **incidental** (o filtro de `/metrics`).
O DESC-10 — mudança de comportamento de estado do cliente, com um caminho destrutivo agora
irreversível — tem **zero**. A proporção está invertida: o que dá nome ao commit é o não testado.

Não há como testá-lo com o que existe: `frontend/package.json` não tem vitest, jest ou runner
algum, e `find frontend/src -name "*.test.*" -o -name "*.spec.*"` devolve vazio — o frontend
nunca teve camada de teste. Isso é condição estrutural preexistente, não defeito deste commit.
Mas `docs/testes.md` §3.6 diz o que fazer nesse caso:

> Descobriu que precisa de um seam que não está na tabela? Isso é descoberta. Registre em
> "Descobertas" na spec e **pare** para decisão do PO.

A DESC-10 não menciona teste em nenhuma linha. O buraco de cobertura entrou sem ser nomeado.

### NC-4 — Média — nada prova que a aplicação liga o filtro, e o docstring do próprio teste cita a lição que não seguiu

`test_o_filtro_e_instalado_no_logger_de_acesso` chama `observability.silence_unserved_probes()`
e confere que o filtro apareceu em `uvicorn.access`. Isso prova **função → logger**. Nada prova
**aplicação → função**: `grep -rn "silence_unserved_probes" tests/` devolve uma única
ocorrência, que é essa chamada direta. Apagar `app.py:222` deixa os 1029 testes verdes.

O que torna isto um achado e não um esquecimento é que o repositório já resolveu exatamente este
problema, uma linha acima no mesmo `app.py`. Para a redação existem os dois níveis:
`redaction_is_installed()` — um predicado sobre a *aplicação* — e
`test_the_application_turns_redaction_on_when_it_starts`, que sobe um `TestClient(create_app(...))`
com a fixture `logging_como_o_uvicorn_monta`. O docstring daquele teste diz, textualmente, *"A
lição, registrada porque já aconteceu três vezes nesta spec: testar a função que faz não é testar
que alguém a chama."*

O docstring do teste **novo** cita nominalmente essa lição — *"É a mesma lição de
`redaction_is_installed` — rodada 2 da verificação da S-02"* — e implementa a versão que a lição
diz ser insuficiente. O remédio já está escrito e testado ao lado; faltou aplicá-lo.

A consequência real aqui é cosmética: uma linha de log. O padrão não é, e é o que a S-02 pagou
três vezes.

### NC-5 — Média — o filtro de `/metrics` é escopo que nenhum requisito pede e nenhuma Descoberta registra

`CLAUDE.md`, precedência 1:

> NUNCA implementar fora do escopo da spec ativa. Se descobrir necessidade nova: anotar na seção
> "Descobertas" da spec e parar para decisão do PO.

A mudança altera o log de acesso de produção. Não é coberta por nenhum dos 15 requisitos, não
está em "Fora de escopo", e aparece **só na mensagem de commit** ("Junto vai o silêncio do 404 de
`/metrics`"). A DESC-10, única Descoberta que este commit acrescenta, não a menciona — quem ler a
spec não fica sabendo que ela existe.

Some-se que ela viaja no mesmo commit da correção do widget, misturando duas revisões
independentes num diff só. É a repetição branda do padrão que a rodada 1 apontou como NC-1
(mudança não relacionada de carona num commit).

O mérito técnico da mudança não está em questão — o filtro é estreito, bem argumentado e bem
testado. A questão é que ele entrou pela porta que o `CLAUDE.md` fecha.

**Sub-achado, Baixa:** o comentário defende bem por que não silenciar *todo* 404, e não considera
o outro lado. Uma varredura de `/metrics` em porta local é a assinatura mais barata de scanner
não autenticado. Localmente isso é irrelevante; no host público da S-08 vira ponto cego, e a
S-08 é onde essa porta abre.

### NC-6 — Média — o controle destrutivo é o visualmente dominante, e a destruição virou irreversível neste commit

Depois deste commit, clicar no FAB chama `reiniciar()` **sem confirmação**: zera `itens`,
`pedido`, `nota`, `erro` e `sessionId`. Antes deste commit, esse clique era inócuo.

A geometria, medida em `widget.css`:

- `.fab` (linhas 19-38): círculo de **60 px**, `background: #25d366` saturado, `box-shadow`
  colorido e um anel `.fab__pulso` animado em laço infinito. O próprio comentário no topo do
  arquivo explica que ele é *"o sinal universal de 'fale comigo aqui', e a demo depende de a
  pessoa reconhecê-lo em meio segundo"*.
- `.retomar` (linhas 61-76): pílula de **13 px** em `var(--tinta-suave)` sobre `var(--cartao)`.

Um cliente com `etapa === "aguardando-pagamento"` (link do Mercado Pago na tela) ou
`"aguardando-nf"` que feche a janela e clique no botão óbvio perde o atendimento **sem volta** —
a própria DESC-10 estabelece que *"não há rota que devolva o estado de uma sessão"*. Não há
confirmação, não há desfazer, e não há sinal visual: o `aria-label` mudou de "Abrir o
atendimento" para "Iniciar um atendimento", a tela não mudou nada.

O conserto proporcional é uma confirmação condicionada a `etapa !== "conversando"` — não um
diálogo em todo clique.

### NC-7 — Baixa — a DESC-10 e o comentário do `Widget.tsx` descrevem a tela errado

Os dois textos dizem que o "retomar conversa" fica **"logo abaixo"** do botão do canto. O CSS põe
os dois praticamente na mesma linha, com o `retomar` à **esquerda**: `.fab` em
`right: 24px; bottom: 24px`, `.retomar` em `right: 96px; bottom: 38px`. É detalhe, mas é a spec
afirmando geometria que o CSS contradiz, no parágrafo que justifica a decisão de desenho.

### NC-8 — Baixa — a landing embarca `api/client.ts`, que é o cliente autenticado do painel

A REQ-7 e a tabela de métricas prometem que a landing *"sai do bundle sem uma linha de JS do
painel"*, com alvo **0**. Medido no build de produção:

- `dist/index.html` faz `modulepreload` de `assets/sse-A-N9UOHC.js` (228,68 kB / 71,79 kB gzip);
- esse chunk contém `X-Operador-Token` e `vendinha:operador`, uma ocorrência cada.

Causa: `useConversa.ts:18` importa `BASE_URL` de `../api/client`, e o bundler traz o módulo
inteiro — inclusive as funções que leem e gravam o token do operador.

O que **não** vaza, e medi para não exagerar o achado: nenhuma tela, rota ou consulta do painel.
`/admin/conversas`, `/admin/metricas`, `/admin/eventos`, `aprovacao_pendente` e `operador/fila`
têm **0 ocorrências** fora de `admin-DeERUpHE.js`. Nenhum segredo viaja: o token é lido do
`sessionStorage` do próprio operador, que na aba pública está vazio.

É a métrica sendo literalmente falsa, não um vazamento. Predata este commit — a rodada 1 marcou a
métrica como 0 medindo import no código-fonte em vez de conteúdo do bundle, e essa é a diferença
entre os dois vereditos. Conserto: `BASE_URL` num módulo próprio.

### NC-9 — Baixa — `silence_unserved_probes()` não é idempotente

`addFilter` recebe uma instância nova a cada chamada, e `Logger.addFilter` só deduplica por
identidade. Medido: 5 chamadas → **5 filtros** em `uvicorn.access`. Em produção `create_app` roda
uma vez e o impacto é nulo; na suíte, cada `TestClient(create_app(...))` acumula mais um no logger
global. Sem efeito observável — todos devolvem o mesmo veredito —, mas o `install_log_redaction`
vizinho foi escrito com o cuidado oposto (devolve contagem justamente para poder falhar quando
virar no-op).

### NC-10 — Baixa — o frontmatter da spec segue desalinhado, e nesta branch o portão não dispara

`status: em-revisao` e `branch: spec/s-07-frontend`, enquanto o trabalho está em
`fix/s-07-sessao-por-atendimento`. É a condição 4 da rodada 1, ainda aberta.

Consequência mecânica que vale dizer em voz alta: `.claude/hooks/gate-pr.py` casa
`^spec/s-(\d{2})\b` e comenta *"the gate guards the spec flow; chore/ and docs/ branches are not
it"*. Numa branch `fix/`, **o portão não dispara** — este relatório não será conferido contra o
sha `35591cb` por máquina nenhuma. É o desenho declarado do hook, não um bug; mas significa que a
única execução deste veredito é humana, e que um commit depois deste passaria sem aviso.

### NC-11 — Baixa — `python -m vendinha.openapi` suja o `openapi.json` no Windows

`openapi.py:136` chama `write_text(..., encoding="utf-8")` sem `newline=""`, então em Windows o
arquivo sai com CRLF. Rodei `make types` sem nenhum drift real e o `git status` passou a mostrar
`M openapi.json` — conteúdo idêntico, `git diff --exit-code` sai 0 graças ao `* text=auto eol=lf`
do `.gitattributes`. O CI roda em Linux e não vê. É a mesma classe da DESC-6 ("um portão de
contrato que só funciona em metade das máquinas do time"), meia casa adiante: agora ele funciona,
mas deixa a árvore suja para quem o roda em Windows, e árvore suja por engano é o que treina a
ignorar `git status`.

---

## Condições de fechamento da rodada 1 — situação

| # | Condição | Situação |
|---|---|---|
| 1 | **(era bloqueante)** reverter `57f80cb`, vendorização da `ui-ux-pro-max` e `skills-lock.json` da raiz | **FECHADA** — `bash scripts/vendor-skills.sh --check` → *OK*; `ui-ux-pro-max` ausente de `.claude/skills/`; nenhum `skills-lock.json` na raiz (só `.claude/skills.lock.json`) |
| 2 | rodar o `S-07-roteiro-de-demo.md` com as duas abas e anexar evidência | **ABERTA** — segunda rodada consecutiva |
| 3 | `frontend/tsconfig.tsbuildinfo` no `.gitignore` | **FECHADA** — `.gitignore:57`; o arquivo não é rastreado |
| 4 | atualizar o `status` do frontmatter da spec | **ABERTA** — ver NC-10 |

---

## Não verificável, e por quê

**A jornada em navegador, incluindo os itens 1 e 2 do roteiro de verificação da própria spec.**
Não é escolha: o `POST /chat` exige credencial de modelo, `create_app` responde **503
`CredentialsUnavailable`** sem ela, e o `.env` real é ilegível para agentes por regra em
`.claude/settings.json`. Sem modelo não há conversa, e sem conversa não há jornada, não há
cronômetro de evento→tela e não há teste de backend derrubado.

Isso importa mais nesta rodada do que na anterior, e vale dizer por quê: o DESC-10 é uma mudança
**inteiramente client-side**, e o projeto declarou duas camadas de teste, ambas em Python
(ADR-011). Não existe camada, neste repositório, capaz de exercitar o que este commit mudou. O
navegador não é uma verificação a mais — é a **única** que pode provar o conserto. Por isso a
condição 2 da rodada 1 deixa de ser higiene e vira condição de mérito.

O `S-07-roteiro-de-demo.md` também não foi atualizado para a semântica nova: ele não tem passo
para "FAB = atendimento novo" nem para o F5 no meio, que são justamente os dois comportamentos
que este commit introduz.

---

## Restauração

| Momento | `git status --short` |
|---|---|
| **Antes** | limpo (nenhuma linha) — a árvore já estava limpa em `35591cb` |
| **Depois** | limpo (nenhuma linha) |

O que mexi e devolvi: regerei `openapi.json` e `frontend/src/api/schema.d.ts` para medir o drift
(`git checkout -- openapi.json` desfez a diferença de fim de linha da NC-11; `schema.d.ts` saiu
byte-idêntico). Rodei `npm run build`, que reescreveu `frontend/dist/` — diretório ignorado que
**já existia** antes de eu chegar. Registro um erro meu: cheguei a apagá-lo antes de perceber que
não era meu, e o reconstruí com `npm run build` em seguida. O conteúdo é o mesmo que meu primeiro
build produziu; o original anterior a mim já tinha sido sobrescrito por esse build.

`frontend/tsconfig.tsbuildinfo` foi tocado pelo `tsc -b` — arquivo ignorado, preexistente, deixado
no lugar.

**Fato operacional, não achado da branch:** `bash scripts/run-tests.sh` **falha nesta máquina**
com 28 erros de coleta (`ModuleNotFoundError: langchain_core`). O script resolve o interpretador
com `command -v python3 || command -v python`, e o python do PATH não é o do venv. Rodei a suíte
com `backend/.venv/Scripts/python.exe -m pytest tests`. O CI instala as dependências no ambiente
default e não vê isso.

---

## Veredito

**APROVADO COM RESSALVAS.**

**Por que não REPROVADO.** As três partes do conserto fazem o que dizem, e conferi cada uma contra
a outra ponta em vez de aceitar a prosa: a parte 2 contra `app.py:580-581`, onde `sessao_nova` é
mesmo `payload.session_id is None`; a parte 3 contra `sse.ts:78-82`, onde o `return` antecipado
não só ignora o stream — ele dispara o `finally` do gerador e cancela o `reader`, de modo que a
conexão morre em vez de ficar correndo em silêncio. A parte 3 é, aliás, mais completa do que a
DESC-10 promete: guarda as três saídas do `enviar`, não só a do laço. O filtro de log é estreito,
degrada com segurança, e a afirmação sobre a forma do `LogRecord` do uvicorn — o tipo de coisa que
costuma ser chute — está correta contra a fonte instalada. Nenhum mecanismo central está quebrado,
nenhum risco declarado está em jogo (a matriz não atribui risco à S-07, e o `riscos_cobertos: []`
está certo), e os oito portões que consegui medir estão verdes, incluindo o bloqueante da rodada 1.

**Por que não APROVADO.** Os dois achados Alta são a mesma coisa dita de dois jeitos, e é
exatamente a coisa que esta spec declarou ser a única que ela pode errar. A REQ-8 continua marcada
`[x]` afirmando um comportamento que o commit removeu de propósito, e o cartão da NF continua
dizendo ao cliente "você recebe aqui assim que sair — não precisa perguntar" num cenário em que
ele deixou de receber. A spec escolheu como frase de governo *"a UI não é lugar de garantia, é
lugar de honestidade"*, e depois deixou duas afirmações falsas de pé — uma no documento, outra na
tela. Nenhuma das duas é cara de consertar, e é por isso que elas são condição e não ressalva
solta.

Some-se que o conserto que dá nome ao commit chega sem um único teste, enquanto a mudança que
viajou de carona chega com oito; que a fiação do filtro repete, com a lição citada no docstring, o
buraco que a S-02 pagou três vezes; e que a verificação em navegador — a única capaz de provar
este commit — está aberta pela segunda rodada seguida.

### Condições de fechamento

1. **Emendar a REQ-8.** Riscar a cláusula `localStorage` / "F5 não perde a conversa", com nota
   apontando para a DESC-10. Enquanto o `[x]` estiver como está, a spec afirma como entregue o que
   o commit retirou.
2. **Corrigir a frase do cartão `aguardando-nf`** (`Widget.tsx:176-179`) para não prometer entrega
   que um reload ou um clique no FAB quebram. Uma oração resolve.
3. **Rodar o `S-07-roteiro-de-demo.md`** com as duas abas e anexar a evidência ao PR — e
   acrescentar ao roteiro os dois passos que este commit criou: (a) FAB → atendimento novo, com o
   painel mostrando **duas** conversas; (b) F5 no meio de um pedido → mostrar o que se perde. É a
   condição 2 da rodada 1 e a única prova possível do DESC-10.
4. **Fechar a fiação do filtro:** um teste que suba `create_app` e prove que a aplicação chama
   `silence_unserved_probes()`. A fixture e o padrão já existem em
   `test_the_application_turns_redaction_on_when_it_starts`.
5. **Confirmação no clique do FAB quando `etapa !== "conversando"`**, para que o botão dominante
   pare de descartar um pedido em voo sem aviso.
6. **Registrar o filtro de `/metrics` como Descoberta na spec**, ou tirá-lo deste commit e mandá-lo
   em PR próprio. Do jeito que está, ele existe só na mensagem de commit.
7. **Higiene, cabe no mesmo PR:** `BASE_URL` fora de `api/client.ts` (NC-8); idempotência de
   `silence_unserved_probes()` (NC-9); `newline=""` no gerador do OpenAPI (NC-11); "logo abaixo" →
   "à esquerda" na DESC-10 e no comentário do `Widget.tsx` (NC-7); `status` e `branch` do
   frontmatter da spec (NC-10).

Cumpridas 1, 2 e 3, esta branch está pronta para PR. As demais são correção e higiene, e cabem no
mesmo PR.

---
---

# Apêndice — Rodada 1 (2026-08-28), preservada na íntegra

> Frontmatter original desta rodada, transcrito como bloco de código para não confundir o parser
> do `gate-pr.py`, que lê apenas o primeiro bloco do arquivo:
>
> ```yaml
> spec: S-07
> veredito: APROVADO COM RESSALVAS
> commit: 57f80cb8dc8ef8605fe66177c33bf4064731fea1
> branch: spec/s-07-frontend
> data: 2026-08-28
> ```

# Relatório de verificação independente — S-07 (Frontend integrado e API de observação)

| | |
|---|---|
| **Spec** | `docs/specs/S-07-frontend-integrado.md` (`status: em-revisao`) |
| **Branch** | `spec/s-07-frontend` @ `57f80cb` (16 commits) |
| **Base** | `origin/main` @ `bfd4f3d` — ancestral de `HEAD`, diff não inflado |
| **PR** | **não existe** no momento da verificação — correto sob o `CLAUDE.md` item 4 |
| **Issue** | [#8](https://github.com/suajornadadedados/vendinha-jornada/issues/8) — OPEN, título bate com a spec |
| **Diff** | 144 arquivos · +92.949 / −41 — dos quais **73 arquivos / +23.736 são a entrega da S-07**; o resto é o commit `57f80cb` (ver NC-1) |
| **Suíte** | **1006 passed**, 0 failed, 0 error, 0 skipped, 131 s (`tests/unit` + `tests/security`) |
| **S-07 isolada** | `tests/unit/test_painel.py` + `tests/security/test_admin_boundary.py` → **44 passed** |
| **Lint** | `ruff check .` → *All checks passed* · `ruff format --check .` → 160 arquivos ok |
| **Typecheck** | `mypy` backend 46 arquivos · `mypy` tests 33 arquivos · `tsc -b --noEmit` no frontend — os três sem erro |
| **Contrato (REQ-1)** | regerei `openapi.json` e `schema.d.ts` do zero: `git diff --exit-code` limpo — **sem drift** |
| **Evals / falsificações** | **NÃO EXECUTADOS** — restrição operacional declarada pelo PO nesta rodada |
| **Verificação em navegador** | **NÃO EXECUTADA** — fora do escopo autorizado desta rodada (ver "Não verificável") |
| **Achados** | 1 Alta (bloqueante) · 2 Média · 2 Baixa |
| **Ambiente** | Windows 11 · `uv run --project backend` · Node 22 / `npm --prefix frontend` |
| **Veredito** | **APROVADO COM RESSALVAS** — 1 condição bloqueante antes do merge |

---

## Enquadramento recebido

O prompt desta rodada pediu explicitamente para **não** rodar gates de eval nem falsificação, e
para restringir a execução a testes e lint. Registro isso porque muda o que este relatório pode
afirmar: tudo que depende de navegador aberto, de backend derrubado no meio da jornada, ou de
julgamento de eval está marcado abaixo como **NÃO VERIFICÁVEL nesta rodada**, e não como conforme.
O enquadramento do autor sobre a qualidade da entrega não foi lido nem usado.

---

## Tabela de conformidade

| REQ | O que a spec pede | Onde verifiquei | Veredito |
|---|---|---|---|
| REQ-1 | Cliente TS gerado do OpenAPI, sem subir servidor; CI reprova drift; zero tipo de fronteira à mão | `backend/vendinha/openapi.py`, `frontend/src/api/schema.d.ts`, job `contrato` no `ci.yml` | **CONFORME** — regerei os dois artefatos localmente e o `git diff` saiu vazio. Todo tipo de fronteira em `dados.ts` e `eventos.ts` é alias de `components["schemas"][...]`; os únicos `interface` escritos à mão (`Painel`, `Fala`, `EstadoDoPedido`, `EstadoDaNota`, `EventoBruto`, `OpcoesDoStream`) são estado de UI, não contrato de rede |
| REQ-2 | Read model de sessões/turnos, mensagens lidas do checkpointer | `backend/vendinha/telemetria.py`, `admin.py:149 ler_conversa` | **CONFORME** — o DDL cria `sessao`, `turno` e `veredito_de_composicao`, e **nenhuma** delas tem coluna de conteúdo de mensagem. O detalhe da conversa lê o checkpointer via `ler_conversa(checkpointer, session_id)` |
| REQ-3 | Barramento in-process, fila limitada, descarte do mais antigo, evento de atraso, nunca bloqueia | `backend/vendinha/eventos.py`; `test_painel.py:179 test_a_fila_cheia_descarta_o_antigo_e_avisa`, `:198 test_sair_do_contexto_descadastra_o_assinante` | **CONFORME** |
| REQ-4 | `/admin/*` read-only e fail-closed no `X-Operador-Token` | `backend/vendinha/admin.py`; `tests/security/test_admin_boundary.py` | **CONFORME** — a suíte cobre as três portas (sem token, token errado, e `OPERADOR_API_TOKEN` ausente do ambiente ⇒ fecha inteiro), parametrizadas por rota, mais `test_o_painel_nao_expoe_nenhuma_rota_de_escrita` |
| REQ-5 | Custo em `Decimal` no backend, tabela versionada, `None` e nunca zero | `backend/vendinha/precos.py`, `data/precos-modelos.json`; `test_painel.py:106,120,126,138` | **CONFORME** — quatro testes distintos afirmam que desconhecido / sem preço / sem cotação viram ausência, não zero |
| REQ-6 | Push por sessão: o cliente recebe a NF sem perguntar | `app.py:665 GET /eventos/sessao/{session_id}`; `test_painel.py:155,164`, `test_admin_boundary.py:168` | **CONFORME no código e na suíte** — o isolamento entre sessões é testado nas duas camadas. O comportamento fim-a-fim no widget é NÃO VERIFICÁVEL nesta rodada |
| REQ-7 | Landing pública, identidade própria, FAB, bundle sem JS do painel | `frontend/src/site/Site.tsx`, `site.css`, `vite.config.ts` (duas entradas) | **CONFORME no diff** — entradas separadas, CSS próprio, zero import de `admin/` em `site/`. Aparência NÃO VERIFICÁVEL nesta rodada |
| REQ-8 | Widget com SSE token a token, estados honestos, sem stack trace, `session_id` em `localStorage` | `site/Widget.tsx`, `site/useConversa.ts`, `api/sse.ts` | **CONFORME no diff** — `localStorage` com `try/catch`, estado `desconectado` exposto na UI, reenvio oferecido |
| REQ-9 | Composição visível enquanto montada, exatamente como o validador devolveu, motivo real | `site/Composicao.tsx`; `Veredito = components["schemas"]["ComposicaoValidada"]` | **CONFORME** — o veredito é renderizado a partir do tipo gerado, sem recomposição em JS |
| REQ-10 | Painel ao vivo ≤1s, por evento, zero polling | `admin/dados.ts:78-79`, `useEventos` | **CONFORME quanto a "zero polling"** — `refetchInterval: false`, `refetchOnWindowFocus: false`, e um único assinante SSE que traduz evento em invalidação seletiva. O `setTimeout` em `sse.ts:159` é backoff de reconexão, não poll. **O alvo de ≤1s é NÃO VERIFICÁVEL nesta rodada** (exige cronômetro em duas abas) |
| REQ-11 | Fila HITL com sino, badge, destinatário PJ completo, motivo obrigatório na rejeição | `admin/Telas.tsx` (`Fila`), `dados.ts` (`aviso`, `pendentes`) | **CONFORME no diff** |
| REQ-12 | Rastreabilidade: proposto × validado, tools, latência e custo por turno; Langfuse só com chaves | `Telas.tsx` (`Rastreabilidade`) | **CONFORME no diff** |
| REQ-13 | Pedidos e métricas; KPIs somados no backend | `Telas.tsx`, `backend/vendinha/metricas.py`; `test_painel.py:209-334` | **CONFORME** — janela vazia devolve ausência e não zero (`test_os_kpis_de_uma_janela_vazia_sao_ausencia_e_nao_zero`), divisão sem denominador idem, e recusa com dois motivos conta nos dois |
| REQ-14 | Config via `PUT /config`; prompts em modo leitura, com caminho e sha | `admin.py:353 prompts`, `Telas.tsx` (`Config`); `test_admin_boundary.py:205` | **CONFORME** — `editavel` é literal `False` no contrato, então o tipo TS é `false` e um botão de salvar não compila. É a implementação mais forte possível do ADR-015 aqui |
| REQ-15 | Sistema visual commitado antes do primeiro componente | `git log --diff-filter=A` | **CONFORME** — `docs/design/sistema-visual.md` entrou em `308f775`; o primeiro componente de `frontend/src/components/ui/` entrou em `163477e`, dois commits depois |

---

## Métricas de sucesso — medidas, não estimadas

| Métrica | Alvo | Medido | |
|---|---|---|---|
| Tipos da fronteira escritos à mão | 0 | **0** — varredura de `interface`/`type` em `frontend/src` fora de `schema.d.ts`: todos os que descrevem a API são alias do schema gerado | ✅ |
| Contas de dinheiro no frontend | 0 | **0** — a única aritmética em `Graficos.tsx` é geometria de barra (`valor / escala * 100` para largura em %); o número exibido é o `valor` do backend, sem transformação | ✅ |
| Requisições de polling no painel | 0 | **0 no código** — `refetchInterval: false`, `refetchOnWindowFocus: false`, nenhum `setInterval`. Não medido em aba Network (fora do escopo desta rodada) | ✅ (estático) |
| Rotas `/admin/*` que respondem sem token | 0 | **0** — `test_admin_boundary.py`, parametrizado, 3 formas de ausência de credencial | ✅ |
| Drift entre `openapi.json` e o cliente TS | 0 | **0** — regeração local + `git diff --exit-code` limpo | ✅ |
| Componentes shadcn antes do sistema visual | 0 | **0** — `308f775` < `163477e` | ✅ |
| Mensagens copiadas para tabela nova | 0 | **0** — DDL de `telemetria.py` sem coluna de conteúdo | ✅ |
| Suíte | verde | **1006 passed / 0 failed** | ✅ |
| Lint + typecheck (ruff, mypy ×2, tsc) | verde | os quatro limpos | ✅ |
| Jornada completa sem recarregar a página | 100% | **não medido** — exige navegador | ⚠️ |
| Atraso evento → tela | ≤ 1s | **não medido** — exige duas abas e cronômetro | ⚠️ |
| Estados distinguíveis só por matiz | 0 | **não medido** — exige revisão de tela | ⚠️ |

---

## Achados

### NC-1 — Alta, **bloqueante** — o commit `57f80cb` contradiz a própria spec, o ADR-009, e deixa um check obrigatório vermelho

O último commit da branch, `docs(s-07): adicionei skill de ux`, vendoriza a skill `ui-ux-pro-max`
(70 arquivos, +69.214 linhas) e adiciona um `skills-lock.json` **na raiz**. Quatro problemas, e
nenhum deles é de estilo:

1. **A DESC-1 desta mesma spec diz, por escrito, que isso ficou "Parado para decisão do PO — não
   commitado nesta branch".** O commit veio depois e fez o contrário. Documento normativo e código
   discordando é exatamente o estado que o `CLAUDE.md` manda resolver a favor da spec.
2. **O ADR-009 nomeia `ui-ux-pro-max` como o caso que *não* se vendoriza** ("vendoriza-se markdown,
   não se vendoriza software"). Reverter essa decisão é legítimo; fazê-lo por um commit `docs(...)`
   dentro de uma branch de spec, sem tocar no ADR, não é.
3. **O check obrigatório `skills-drift` fica vermelho.** Rodei `bash scripts/vendor-skills.sh
   --check`: `DRIFT entre o lockfile e .claude/skills/: Only in .claude/skills: ui-ux-pro-max`.
   Este PR não passa no CI como está.
4. **Segunda fonte de verdade sobre a mesma coisa**: `skills-lock.json` na raiz duplica o
   `.claude/skills.lock.json` que o ADR-009 estabeleceu como fonte única — e com formato diferente,
   sem o campo `porque` obrigatório.

Ainda no mesmo commit, uma alteração não relacionada e provavelmente acidental em
`.claude/commands/fechar-spec.md`: `argument-hint: <id da spec, ex.: S-11>` virou
`<id da spec, ex- S-11>`. É dano cosmético num arquivo do harness, entrando de carona num commit
de skill.

**Condição de fechamento:** reverter `57f80cb` nesta branch, devolvendo a decisão à DESC-1 como ela
está escrita, e confirmar com `bash scripts/vendor-skills.sh --check` limpo. Se o PO quiser mesmo
vendorizar a skill, isso é um ADR e um PR próprios — `.claude/skills.lock.json` com o campo
`porque`, `vendor-skills.sh` rematerializando, e um lockfile só.

### NC-2 — Média — `frontend/tsconfig.tsbuildinfo` está commitado

Artefato de build incremental do `tsc`, com caminhos e hashes da máquina de quem compilou. Vai
gerar conflito em todo PR que toque o frontend e não descreve nada do produto. Pertence ao
`.gitignore`. Não bloqueia o merge, mas quanto mais tarde sair, mais atrito acumula.

### NC-3 — Média — três métricas da própria spec continuam sem número

"Jornada completa sem recarregar", "atraso ≤1s" e "estados distinguíveis só por matiz" são alvos
que a spec declarou e que **ninguém mediu ainda** — o autor registrou explicitamente que deixou os
dois primeiros para a verificação independente, e esta rodada foi restringida a testes e lint pelo
PO. Não é falha da entrega; é uma lacuna de evidência que precisa estar visível no PR em vez de ser
lida como conformidade. O roteiro para fechá-la já existe (`S-07-roteiro-de-demo.md`).

### NC-4 — Baixa — o cenário BDD "a conexão cai e a tela não mente" foi lido, não exercido

O código faz a coisa certa: `Admin.tsx:127-130` troca o rótulo para `desconectado — dados de
<hora>` e `painel__main--velho` esmaece o conteúdo, ou seja, número velho aparece **carimbado**
como velho em vez de posar de atual. Isso é leitura de diff, não observação. O cenário só fecha com
a API derrubada e as duas telas abertas.

### NC-5 — Baixa — o `status` da spec ainda é `em-revisao`

Coerente com o momento — é o que a verificação está fazendo —, mas o `CLAUDE.md` pede atualizar o
frontmatter ao concluir. Fica como lembrete para o fechamento.

---

## Invariantes globais

| Invariante | Resultado |
|---|---|
| Secrets no diff | **nenhum** — varredura por chaves de API, chaves privadas e CNPJ no diff da entrega: vazio |
| Regra de ouro (dinheiro é do código) | **respeitada** — nenhum total, custo ou KPI somado em JavaScript; `Decimal` no backend, string no contrato |
| Escrita no domínio a partir do painel | **nenhuma** — `test_o_painel_nao_expoe_nenhuma_rota_de_escrita` afirma isso, e as únicas escritas expostas (decisão HITL, config) já existiam |
| Fronteira de permissões dos subagents | **intocada** — o diff da S-07 não altera `subagents.py` além de ler os prompts vigentes |
| Pointer-not-payload (RNF-6) | **respeitado** — mensagens vêm do checkpointer |
| Escopo da spec | **violado uma vez**, e só em NC-1 |

---

## Não verificável nesta rodada (e por quê)

Por restrição operacional declarada pelo PO, não executei: evals, falsificações, `docker compose
up`, a jornada em navegador, o teste de backend derrubado, e a medição de latência evento→tela.
Os itens 1, 2 e parte do 6 do roteiro de verificação da própria spec permanecem **abertos**.
Nenhum deles foi marcado como conforme acima.

---

## Veredito

**APROVADO COM RESSALVAS.**

A entrega da S-07 propriamente dita — 73 arquivos, backend de observação, contrato gerado e as duas
telas — está **conforme nos 15 requisitos** no que é verificável por código, teste e diff. Os
portões que mais importam nesta spec são justamente os que a spec disse que importariam, e todos
passam com número medido: zero drift de contrato, zero conta de dinheiro no navegador, zero rota de
painel aberta, zero polling, zero mensagem copiada para tabela nova, e a ordem dos commits provando
que o sistema visual veio antes do primeiro componente. 1006 testes verdes, quatro gates de
lint/tipo limpos.

Não é APROVADO liso por dois motivos de natureza diferente. O primeiro é **bloqueante e mecânico**:
o commit `57f80cb` deixa um check obrigatório vermelho e faz o repositório dizer duas coisas
incompatíveis sobre a mesma decisão — a DESC-1 afirma que a skill não foi commitada, e ela está
commitada. Isso se resolve com um `revert`, não com uma discussão. O segundo é **de evidência**:
três das métricas que a própria spec escolheu ainda não têm número, porque medi-las exige o
navegador que esta rodada não abriu.

### Condições de fechamento

1. **(bloqueante)** Reverter `57f80cb` — vendorização da `ui-ux-pro-max` e `skills-lock.json` da
   raiz —, restaurando `.claude/commands/fechar-spec.md`. Confirmar com
   `bash scripts/vendor-skills.sh --check` limpo.
2. Rodar o `S-07-roteiro-de-demo.md` com as duas abas abertas e anexar ao PR: screenshot da
   jornada, o atraso evento→tela cronometrado, e o comportamento com a API derrubada.
3. `frontend/tsconfig.tsbuildinfo` para o `.gitignore`.
4. Atualizar o `status` do frontmatter da spec no fechamento.

Cumprida a condição 1, esta branch está pronta para PR. As condições 2 a 4 são evidência e higiene,
e cabem no mesmo PR.
