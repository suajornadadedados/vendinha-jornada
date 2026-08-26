# Relatório de verificação independente — S-02 (Agente base observável)

| | |
|---|---|
| **Spec** | `docs/specs/S-02-agente-observavel.md` (`status: em-revisao`) |
| **Branch** | `spec/s-02-agente-observavel` @ `96ecfd6` |
| **Base** | `origin/main` @ `cb51953` (PR #13, squash) |
| **PR** | **não existe ainda.** É o comportamento correto sob o `CLAUDE.md` item 4: *"Verificação independente ANTES do PR, não antes do merge… Sem veredito, não existe PR."* Ver **NC-4** sobre os três normativos que ainda dizem o contrário |
| **Issue** | [#3](https://github.com/suajornadadedados/vendinha-jornada/issues/3) — **OPEN**, corpo é ponteiro para a spec |
| **Diff** | 10 commits · 40 arquivos · +5.461 / −233 |
| **Sessão** | revisora, sem acesso ao histórico da sessão autora |
| **Data** | 2026-08-26 |
| **Ambiente** | Windows 11, Git 2.46.0, Docker 27.2.0, uv 0.6.9, Node v22.16.0, ruff 0.11.7, mypy 2.3.1. **`make` não existe nesta máquina** — rodei a linha de dentro de cada alvo. `backend/.venv` é **Python 3.13.2** (o projeto declara `>=3.12` e o CI usa 3.12; registro a diferença porque ela é minha, não do autor) |
| **Infra** | `docker compose` já no ar: `vendinha-postgres-1` healthy em `127.0.0.1:5433`, `vendinha-qdrant-1` healthy em `6333/6334`. A 5432 do host está ocupada por um Postgres nativo — usei `DATABASE_URL` apontando para a 5433 |
| **Veredito** | **REPROVADO** |

> **Nota de método sobre o `.env`.** A leitura do `.env` é negada ao agente por regra em
> `.claude/settings.json`, e eu não a burlei: em nenhum momento li o arquivo, e nenhum valor
> de credencial aparece neste relatório. Onde precisei de configuração, passei variáveis pelo
> meu próprio shell (`DATABASE_URL`, `CONFIG_ENCRYPTION_KEY` gerada por mim, `API_PORT`,
> `SESSION_BUDGET_TOKENS`, `LANGFUSE_BASE_URL`). Onde a medição exigia a credencial real —
> consultar o trace de volta no Langfuse Cloud — usei `vendinha.config.get_settings()` de
> dentro de um script e imprimi **só o resultado da consulta**, nunca a chave. As chamadas ao
> Langfuse e aos fornecedores foram feitas contra a nuvem real, com custo real e pequeno
> (soma de todos os traces desta sessão: **US$ 0,0082**).

> **Nota sobre o banco.** Não escrevi no banco de trabalho do autor: criei um banco
> `vendinha_verif` no mesmo Postgres para os testes de credencial e o **derrubei** ao final.
> O `make db-setup` e o teste de retomada do R9 rodaram no banco `vendinha` (as tabelas do
> checkpointer são idempotentes); as linhas de checkpoint que criei foram removidas (9 em
> `checkpoints`, 30 no total entre as três tabelas).

---

## 1. Resumo

A entrega é tecnicamente forte e a maior parte dela sobrevive à falsificação: rodei **34
quebras deliberadas** na implementação e **31 reprovaram**, cada uma no teste certo e por
motivo legível. Os invariantes centrais do ADR-012 se sustentam sob medição real: gravei uma
chave falsa por `PUT /config` e ela **não** aparece em `/health`, `/config`, `/models`,
`/openapi.json`, `/docs`, no log do processo nem na coluna `bytea` do Postgres — que veio como
um blob Fernet de 184 bytes sem nenhum `sk-` dentro. O `GET /models` devolveu **119 modelos**
lidos ao vivo dos dois fornecedores, exatamente o número que a D-9 afirma. A retomada de sessão
do R9 foi verificada onde ela realmente importa: **dois processos distintos** (pid 36272 e pid
7688) contra o Postgres do compose, o segundo lendo os turnos que o primeiro escreveu, e uma
sessão diferente isolada. A degradação de budget foi forçada ponta a ponta e responde com
honestidade sem citar token, limite ou configuração. E o ADR-010 foi verificado com o Langfuse
apontado para uma porta morta: **3/3** chamadas a `POST /chat` responderam 200 em 0,97–1,94 s,
com zero traceback no log.

O que reprova a entrega são duas coisas, e a primeira é objetiva a ponto de não admitir
discussão.

**A suíte não é verde fora da máquina do autor.** Exportei o `HEAD` com `git archive` para um
diretório limpo — sem `.env`, que é exatamente a condição do job `test` do CI — e rodei a mesma
suíte: **4 failed, 352 passed**. Os quatro testes que quebram dependem de a máquina ter um
`CONFIG_ENCRYPTION_KEY` no `.env` do autor, porque `PUT /config` responde `503` sem ela. O job
`test` é *required check* da `main`. A métrica publicada na spec (*"356 passed"*) é verdadeira
só onde ela foi medida. E o detalhe que transforma isso de descuido em achado: o próprio autor
descreve essa classe de bug num comentário dentro do mesmo arquivo — *"a test whose answer
depends on whether the developer happens to have a key in `.env` passes on one machine and
fails on the next"* — e corrigiu **uma** instância, deixando quatro.

**A metade "logs" do R5 não existe na aplicação que roda.** A `docs/riscos.md` R5 é *"vazamento
de PII em traces **e logs**"*. A metade "traces" está provada e eu a auditei no trace bruto real
do Langfuse Cloud: CPF com e sem pontuação, e-mail e telefone **ausentes**, com `[CPF]`,
`[EMAIL]` e `[TELEFONE]` no lugar. A metade "logs" é inerte: `install_log_redaction()` anexa o
filtro a `logging.getLogger().handlers`, e sob uvicorn — o único jeito suportado de rodar a API
— **o root não tem handler nenhum**. Medi: `root handlers: []`. O registro emitido por
`vendinha.app` cai no `logging.lastResort` e chega ao stderr **em claro**:
`cliente informou 123.456.789-09`. Some-se que o filtro nunca toca em `record.exc_info`, então o
traceback — o caso que o próprio docstring do módulo nomeia como *"a maneira usual de um segredo
chegar ao log"* — sai inteiro: medi com uma chave de provedor falsa e um CPF de teste, e os dois
aparecem no texto formatado. Apagar a chamada que instala o filtro **deixa a suíte verde**
(falsificação **F14**): nada cobre o alcance, só a função.

**5 CONFORME · 1 NÃO CONFORME · 0 NÃO VERIFICÁVEL** (requisitos), com 7 não-conformidades
adicionais e 11 ressalvas.

---

## 2. Conformidade requisito a requisito

| # | Requisito | Status | Evidência que EU produzi |
|---|---|---|---|
| REQ-1 | FastAPI com `POST /chat` (SSE) e sessões; grafo LangGraph mínimo (um nó) | **CONFORME** | Subi a API de verdade (`python -m vendinha`, porta 8123) contra o Postgres do compose e o modelo real. `POST /chat` devolve `text/event-stream` com `session` primeiro, `token` no meio e `done` no fim; o `session_id` volta no primeiro evento e continua a conversa no turno seguinte. `graph.py` tem um nó (`conversa`), `START → conversa → END`. Falsifiquei 4 vezes (§5.4): as 4 reprovaram |
| REQ-2 | Checkpointer em Postgres; estado carrega apenas IDs | **CONFORME** | A metade que a spec manda verificar à mão: `make db-setup` (linha de dentro do alvo), depois **dois processos Python separados** contra o Postgres do compose — pid 36272 gravou `['meu nome ficou registrado?', 'ok']`, pid 7688 (processo novo, nada compartilhado além do banco) leu de volta e fechou em 4 mensagens; uma terceira sessão com id diferente ficou isolada em 2. `ConversationState.__annotations__` == `{session_id, messages}`. Falsifiquei 3 vezes: as 3 reprovaram |
| REQ-3 | Langfuse Cloud instrumentado: trace por sessão com tools, custo, latência; indisponibilidade não propaga | **CONFORME** | Consultei os traces de volta pela API pública: **11/11** sessões desta verificação têm trace com `latency` e `totalCost` preenchidos. Trace auditado: `name: conversa`, `sessionId` igual ao da API, 3 observações, `GENERATION ChatAnthropic` com `model: claude-haiku-4-5`, `latency: 2.068`, `cost: 0.000801`, `usage: {input 341, output 92, total 433}`. "Tools" não é exercitável na S-02 (não existem tools). A exigência do ADR-010 foi verificada **provocando a falha**, não esperando por ela: subi a API com `LANGFUSE_BASE_URL=http://127.0.0.1:9` (porta morta) e `POST /chat` respondeu **200 em 1940 / 1575 / 967 ms**, com `grep -ci traceback` = **0** no log |
| REQ-4 | Mascaramento de PII (**CPF, e-mail, nome**) na camada de instrumentação **antes** do envio. *"invariante de release: sem o teste de redação verde, a spec não fecha"* | **NÃO CONFORME** | Duas metades, e as duas falham em pontos diferentes. **Traces:** mandei CPF, CPF sem pontuação, e-mail, telefone e nome numa conversa real e busquei o trace bruto no Langfuse Cloud. CPF `False`, CPF sem pontuação `False`, e-mail `False`, telefone `False` — com `[CPF]`, `[EMAIL]` e `[TELEFONE]` presentes. **`Marta Ribeiro` presente em claro, e `Marta` também.** O REQ-4 nomeia "nome" e o código não mascara nome por padrão; a D-6 explica por quê e o argumento é bom, mas **o texto do requisito não foi emendado** e continua marcado `[x]` — ver **NC-3**. **Logs:** inertes na aplicação real — ver **NC-2**, que é o achado grave |
| REQ-5 | Budget cap por sessão e timeout por tool via config; exceder = resposta honesta | **CONFORME** | Subi a API com `SESSION_BUDGET_TOKENS=50` e conversei três turnos na mesma sessão: turno 1 respondeu normalmente; turnos 2 e 3 devolveram *"Essa nossa conversa já ficou bem longa e eu preciso parar por aqui…"*, sem citar token, budget, limite, número ou nome de configuração. A unidade é token (D-2) e `SESSION_BUDGET_USD` não existe mais no `.env.example`. Falsifiquei 6 vezes: as 6 reprovaram, incluindo mover o guarda para **depois** da chamada ao modelo |
| REQ-6 | Provedor agnóstico; `GET /models`; `GET`/`PUT /config`; `model` validado contra allowlist; credencial cifrada, nunca de volta pela API, nunca em trace ou log | **CONFORME**, com duas ressalvas materiais | `GET /models` devolveu **119 modelos** (108 openai + 11 anthropic) lidos ao vivo dos SDKs — não há catálogo escrito neste repositório, confirmado por grep. Gravei `sk-ant-api03-VERIFICACAOFALSA…` por `PUT /config` e varri **cinco rotas**: nenhuma vazou. `bytea` no Postgres: 184 bytes começando em `gAAAAABq…` (Fernet), sem a chave e sem `sk-`. Log do processo: 0 ocorrências. Falsifiquei 7 vezes: **6 reprovaram, 1 passou** — a precedência banco > ambiente (ver **R-1**). E o campo `model`, que é o que este REQ acrescenta, custa 3,3 s de p95 (ver **R-2**) |

---

## 3. Cenários BDD

```gherkin
Cenário: PII nunca aparece em trace
  Dado uma conversa em que o cliente informa um CPF de teste
  Quando inspeciono o trace da sessão no Langfuse
  Então o CPF aparece mascarado e nunca em texto claro
```

**CONFORME.** Sessão `verif-pii-1787768634`, trace `be0d0e12ec37…`, 12.145 bytes de JSON bruto
auditados campo a campo. O `input` do trace veio literalmente assim:

```
"content": "oi, aqui e Marta Ribeiro, meu cpf e [CPF] (ou [CPF]), meu email [EMAIL] e meu telefone [TELEFONE]. pode anotar?"
```

CPF `123.456.789-09`, `12345678909`, e-mail e telefone: **ausentes**. Nenhum `sk-ant`, `sk-proj`,
`sk-lf` nem `ANTHROPIC_API_KEY` no trace. O cenário como escrito fala de CPF, e o CPF passa. O
**nome** não — está no trace em claro, e a spec declara isso de propósito na D-6.

```gherkin
Cenário: retomada de sessão
  Dado uma conversa interrompida após 3 turnos
  Quando o cliente retorna com o mesmo session_id
  Então o grafo retoma do checkpoint sem perda de contexto
```

**CONFORME**, e verificado na versão forte: não um grafo novo no mesmo processo, mas **processos
diferentes**. Rodei três invocações do mesmo script, cada uma abrindo seu próprio
`AsyncPostgresSaver` contra o Postgres do compose:

```
pid=36272 turnos=2  ['meu nome ficou registrado?', 'ok']
pid=7688  turnos=4  ['meu nome ficou registrado?', 'ok', 'e agora, lembra?', 'ok']   ← processo novo
pid=36136 turnos=2  ['nada a ver', 'ok']                                            ← outra sessão
```

É a metade manual que `docs/testes.md` §1 e a própria spec mandam fazer aqui, e ela fecha.

```gherkin
Cenário: a credencial não volta pela porta da frente
  Dado que o operador gravou uma API key pela configuração
  Quando qualquer rota da API é consultada, incluindo a de configuração
  Então nenhuma resposta contém a chave — só `configured: true` e uma dica mascarada
```

**CONFORME.** Gravei a chave falsa e varri `/health`, `/config`, `/models`, `/openapi.json` e
`/docs`: **as cinco limpas**. A resposta do próprio `PUT` — o lugar mais fácil de errar — veio
com `"configured":true,"source":"banco","hint":"…0000"`. Continuei além do cenário e fui ao
repouso: a coluna `credentials` do Postgres é um blob Fernet opaco, e o log do processo tem
**0** ocorrências da chave.

---

## 4. Métricas medidas vs alvo

| Métrica | Alvo | Spec declara | **Eu medi** | Status |
|---|---|---|---|---|
| Sessões com trace completo | 100% | 13/13 | **11/11** (as 11 sessões que eu criei), todas com `latency` e `totalCost` não nulos | CONFORME |
| PII em claro em traces | 0 | 0 | **0 para CPF, e-mail e telefone**; **nome em claro**, como a D-6 declara | ver NC-3 |
| PII em claro em **logs** | 0 (`docs/riscos.md` R5) | não medida | **PII e credencial em claro no stderr da aplicação real** | **NC-2** |
| Credencial em claro em traces/logs/respostas | 0 | 0 | **0** — 5 rotas, log do processo, trace bruto e `bytea` do Postgres | CONFORME |
| p95 primeiro token (sem `model`) | ≤ 3 s | 1,31 s (n=10) | **1,034 s** (n=10, mediana 0,874 s, min 0,591 s) | CONFORME |
| p95 primeiro token (**com `model`**) | ≤ 3 s | não medida | **3,331 s** (n=10, mediana 2,621 s, min 1,843 s) | **estoura o alvo** — ver R-2 |
| Suíte, nesta máquina | verde | 356 passed | **356 passed em 1,61 s** | CONFORME |
| Suíte, em cópia limpa sem `.env` (= CI) | verde | — | **4 failed, 352 passed** | **NC-1** |
| `ruff check` / `ruff format --check` | limpo | limpo | **All checks passed** / **26 files already formatted** | CONFORME |
| `mypy` strict no backend | limpo | limpo | **Success: no issues found in 14 source files** | CONFORME |
| `mypy` strict na suíte | limpo | limpo | **Success: no issues found in 10 source files** | CONFORME (R-4 da S-01 fechada) |
| `pytest tests -m "risco"` | coleta > 0 | "os treze testes-âncora… 21 passed" | **21 passed, 335 deselected** (R5: 10 · R6: 7 · R9: 4) | CONFORME; o "treze" está errado, ver NC-6 |
| `commitlint` na branch | 0 problemas | — | **0 problems** em 10 commits (3 avisos `footer-leading-blank`) | CONFORME |
| `gitleaks` no histórico | 0 leaks | — | **no leaks found**, 40 commits, 1,65 MB, exit 0 | CONFORME |
| Commits entregues | 9 (tabela da spec) | 9 | **10** | ver NC-5 |

### 4.1 A medição que reprova: a suíte fora desta máquina

```
$ git archive HEAD | tar -x -C <scratch>/ci-sim      # cópia limpa, sem .env
$ cd <scratch>/ci-sim && PYTHONPATH=./backend python -m pytest tests
...
FAILED tests/unit/test_provider_config.py::test_writing_a_credential_stores_it_and_never_echoes_it
FAILED tests/unit/test_provider_config.py::test_a_stored_credential_wins_over_the_environment
FAILED tests/unit/test_provider_config.py::test_the_model_list_comes_from_the_provider
FAILED tests/unit/test_provider_config.py::test_chat_refuses_a_model_outside_the_server_list
4 failed, 352 passed in 1.78s
```

Confirmei que `ENV_FILE` apontava para a cópia e que ela não tem `.env`. A cadeia é curta:
os quatro testes fazem `client.put("/config", …)`; `write_config` recusa com **503** quando
`Vault(settings.config_encryption_key).usable` é falso; sem `.env` e sem variável no ambiente,
`config_encryption_key` é `None`. O job `test` do CI faz `checkout` + `pip install` +
`bash scripts/run-tests.sh` — nenhum `.env`, nenhum secret exportado. Reproduzi o mesmo
resultado de um segundo jeito, no próprio repositório, com `CONFIG_ENCRYPTION_KEY=` no shell:
os mesmos quatro.

### 4.2 A medição que expõe o log

```
$ python -c "cfg = uvicorn.Config('vendinha.app:app', …); cfg.configure_logging(); …"
root handlers: []
uvicorn.access handlers: [<StreamHandler <stdout>>] propagate: False
depois de install_log_redaction, filtros no root: []
saida do log: 'cliente informou 123.456.789-09\n'
```

E o caminho do traceback, com o filtro **corretamente** anexado à mão:

```
RuntimeError: auth failed with sk-ant-api03-QQQQ…QQQQ for cpf 123.456.789-09 at postgresql://vendinha:vendinha@127.0.0.1:5432/vendinha
KEY in log: True
CPF in log: True
```

---

## 5. As falsificações que executei

**34 quebras, 31 reprovações, 3 passaram.** Em cada uma: quebrei o arquivo de produto, rodei o
teste-alvo, restaurei com `git checkout --`. Nenhum arquivo de teste foi tocado — quebrar o
teste para ver o teste falhar não prova nada.

### 5.1 R5 — redação (`tests/security/test_pii_redaction.py`)

| # | O que quebrei | Reprovou em |
|---|---|---|
| F1 | removi `(CPF, "[CPF]")` de `PATTERNS` | `test_a_cpf_never_survives_redaction` |
| F2 | removi `(EMAIL, "[EMAIL]")` | `test_an_email_never_survives_redaction` |
| F3 | removi `(PHONE, "[TELEFONE]")` | `test_a_phone_number_never_survives_redaction` |
| F4 | removi `(CREDENTIAL, "[CREDENCIAL]")` | `test_a_provider_credential_never_survives_redaction` |
| F5 | apaguei o laço que mascara **o primeiro nome** isolado | `..._even_when_only_the_first_name_appears` **e** `..._does_not_reach_the_export_either` |
| F6 | `redactor()` passa a ignorar `KNOWN_VALUES` | `test_a_remembered_name_does_not_reach_the_export_either` |
| F7 | mascarei **demais**: `CPF` vira `\b[\d.]{5,}\b` | `..._a_price_is_not_mistaken_for_personal_data` (e o telefone junto) |
| F8 | `mask_otel_spans` sempre devolve `None` ("batch inalterado") | `..._scrubs_every_string_attribute` **e** `..._does_not_reach_the_export_either` |
| F9 | `attributes()` devolve todo atributo, não só os que mudaram | `..._leaves_a_clean_span_untouched` |
| F10 | o hook só redige spans do **nosso** escopo, ignorando `langchain` | `..._scrubs_every_string_attribute` **e** `..._does_not_reach_the_export_either` |
| F11 | `RedactingLogFilter.filter` vira `return True` seco | `test_log_records_are_redacted_before_they_reach_a_handler` |
| F12 | desliguei **só** o caminho `record.args` | idem |

A F8 e a F10 são as que valem: elas atacam o **alcance**, não a função, e as duas foram pegas
pelo teste que constrói um lote com um span de instrumentação de terceiro. Esse par é a melhor
coisa do arquivo.

**As duas que passaram — e ambas são sobre log:**

| # | O que quebrei | Resultado |
|---|---|---|
| **F13** | desliguei a redação de `record.msg` (mantendo `record.args`) | **10 passed** — nada cobre esse ramo, porque os dois `logger.info` do teste passam a PII por `%s` |
| **F14** | fiz `install_log_redaction()` **não anexar nada** | **10 passed** — o teste anexa o filtro à mão num logger que ele mesmo cria. Nada prova que a aplicação instala o filtro. Ver **NC-2** |

### 5.2 R6 — custo e latência (`tests/unit/test_budget_guard.py`)

| # | O que quebrei | Reprovou em |
|---|---|---|
| F15 | `within_budget` sempre `True` | `..._cap_allows_up_to_the_limit…` **e** `..._over_budget_answers_honestly…` |
| F16 | `<=` vira `<` (gastar exatamente o teto passa a ser estouro) | `..._cap_allows_up_to_the_limit_and_refuses_past_it` |
| F17 | `tokens_spent` conta só `output_tokens` | `..._spending_is_read_back_from_the_conversation` |
| F18 | movi o guarda para **depois** da chamada ao modelo | `..._over_budget_answers_honestly_without_calling_the_model` |
| F19 | mensagem de limite passa a dizer *"budget de 60000 token"* | `..._limit_message_never_leaks_configuration` |
| F20 | `TimedOut` perde o nome do que estourou | `..._a_slow_call_is_cut_off_and_a_fast_one_is_not` |

A F18 é a que importa: um guarda que recusa depois de gastar não é guarda, e o teste o pega
porque o modelo falso levanta se for tocado. Isso é asserção sobre **alcance**, do jeito certo.

### 5.3 R9 — retomada e pointer-not-payload (`tests/unit/test_session_resume.py`)

| # | O que quebrei | Reprovou em |
|---|---|---|
| F21 | `builder.compile()` sem checkpointer | `..._resumes_with_the_same_session_id` **e** `..._new_graph_reads_what_the_previous_one_wrote` |
| F22 | `thread_id` fixo em `"unica"` | `test_two_sessions_do_not_share_state` |
| F23 | acrescentei `pedido: dict` ao `ConversationState` | `test_graph_state_carries_identifiers_not_payloads` |

### 5.4 Endpoint e configuração (feature tests)

| # | O que quebrei | Reprovou em |
|---|---|---|
| F24 | evento `session` deixa de ser o primeiro | 5 testes de `test_chat_endpoint.py` |
| F25 | o evento `error` passa a carregar o texto da exceção (com DSN) | `..._becomes_an_event_and_leaks_nothing` |
| F26 | `NonEmptyText` vira `str` puro | `..._empty_message_is_refused_by_the_contract` |
| F27 | `session_id` do cliente é ignorado (id novo a cada turno) | `..._same_session_id_continues_the_same_conversation` |
| F28 | `/config` devolve a chave inteira no lugar da dica | `..._never_returns_the_key` **e** `..._never_echoes_it` |
| F29 | removi a validação de allowlist do `POST /chat` | `test_chat_refuses_a_model_outside_the_server_list` |
| F30 | `models_offered_by` passa a devolver uma lista escrita à mão | `..._model_list_comes_from_the_provider` (e o de allowlist junto) |
| F31 | removi o guarda `APP_ENV != "local"` do `PUT /config` | `..._cannot_be_written_outside_local` |
| F32 | `Vault.seal` grava em claro quando não há chave | `..._writing_is_refused_not_downgraded` |
| F33 | `Vault.hint` devolve o segredo inteiro | 3 testes ao mesmo tempo |

**A que passou:**

| # | O que quebrei | Resultado |
|---|---|---|
| **F34** | inverti a precedência em `_credentials()`: **o ambiente passa a vencer o banco** | **16 passed.** Existe um teste chamado `test_a_stored_credential_wins_over_the_environment` e ele continua verde, porque ele afirma sobre o campo `source` do `/config` — que `read_config` calcula direto de `stored.credentials` — e não sobre a função que decide **qual chave o grafo usa**. Ver **R-1** |

---

## 6. Invariantes globais

| Invariante | Verificação | Resultado |
|---|---|---|
| Ausência de segredo no diff | `gitleaks v8.29.0` no histórico completo com o `.gitleaks.toml` do repo | **OK.** `no leaks found`, 40 commits, 1,65 MB |
| Ausência de CPF/CNPJ/certificado/dado real no diff | grep por CPF e CNPJ formatados, `sk-`/`ghp_`/`APP_USR-`/`BEGIN PRIVATE KEY`, e `*_KEY=`/`*_TOKEN=`/`*_SECRET=` com valor, em todas as linhas `+` | **OK.** Zero CPF, zero CNPJ, zero certificado. Os únicos "segredos" são três constantes obviamente sintéticas: `"sk-ant-api03-" + "A"*40`, `"sk-lf-" + "b"*32`, `"sk-ant-api03-" + "Z"*40` |
| Credencial nunca volta pela API | 5 rotas varridas contra uma chave gravada de verdade | **OK** |
| Credencial cifrada em repouso | `bytea` lido direto do Postgres: 184 bytes, prefixo Fernet, sem `sk-` | **OK** |
| PII mascarada em **traces** | trace bruto real do Langfuse Cloud, 12 KB, campo a campo | **OK** para CPF/e-mail/telefone; **nome em claro** (declarado na D-6) |
| PII mascarada em **logs** | introspecção do logging sob uvicorn + teste de traceback | **FALHA** — ver NC-2 |
| Escopo respeitado ("Fora de escopo: RAG, subagents, tools de negócio; a tela de configuração; credencial por usuário") | `find backend -name "*.py"` + grep por `qdrant`/`embedding`/`retriev`/`subagent`/`@tool`/`StructuredTool`/`StaticFiles`/`HTMLResponse`/`user_id`/`auth` | **OK.** 14 módulos, nenhum cliente Qdrant, nenhuma tool, nenhum subagent, nenhum diretório `frontend/`, nenhuma rota que sirva HTML, nenhuma coluna de usuário. `instance_config` é literalmente uma linha só (`CHECK (id = 1)`) |
| Fronteira de permissões de subagents | não aplicável (o primeiro subagent chega na S-04) | **N/A** |
| Suíte restaurada após as falsificações | `git status --short` ao fim | **OK.** Única entrada é `?? docs/workshop/apresentacao.html`, não rastreado, que já existia antes desta sessão |
| Banco de trabalho do autor restaurado | `DROP DATABASE vendinha_verif`; 30 linhas de checkpoint de teste removidas de `vendinha` | **OK** |

---

## 7. Avaliação das "Descobertas"

Lidas como *alterações de escopo a justificar*, não como fatos aceitos.

| # | Veredito | Comentário |
|---|---|---|
| **D-1** (`LANGFUSE_BASE_URL`) | **Legítima e no escopo** | O código lê `AliasChoices("LANGFUSE_BASE_URL", "LANGFUSE_HOST")` — confirmei que os dois nomes funcionam. A decisão de **não** emendar o ADR-010 é a certa e é consistente com o mecanismo que a S-01 construiu: nome de variável de terceiro é consequência, não decisão. O `.env.example`, o `docker-compose.yml`, o `github-setup.md` e o job `evals` do CI foram todos atualizados junto — varri e não achou sobra |
| **D-2** (cap em token) | **Legítima, decidida pelo PO, e melhor que a alternativa** | `SESSION_BUDGET_USD` não existe mais em lugar nenhum (grep limpo). O argumento — tabela de preço por fornecedor apodrece em silêncio — é reforçado pelo ADR-012, e o teste fica determinístico sem rede. Verifiquei o outro lado da conta: o custo em R$ **está** no Langfuse (`totalCost: 0.000801` no trace que auditei), que é onde o R6 já o colocava |
| **D-3** (ADR-012) | **Legítima, e tratada do jeito certo** | Pedido novo do PO, fora dos cinco requisitos originais, virou ADR + REQ-6 + três invariantes provados por código em vez de implementação silenciosa. Conferi que o ADR-012 não substitui nem reescreve nenhum ADR aceito, e que `docs/decisoes.md` ganhou a linha D15. A frase *"protege contra dump do banco; não protege contra quem já tem o `.env`"* está no ADR e no `.env.example` — é o tipo de honestidade que faz o documento valer |
| **D-4** (sem seam novo para credencial) | **Legítima** | `docs/testes.md` §2 mapeia *"o que atravessa a fronteira do processo"* para `tests/security/test_pii_redaction.py`, e a credencial é exatamente isso. Confirmei que o arquivo tem o caso (`test_a_provider_credential_never_survives_redaction`) e que criar `test_credential_leak.py` seria camada nova. A §3 item 6 manda registrar em vez de improvisar, e foi o que aconteceu |
| **D-5** (`ProactorEventLoop`) | **Legítima e verificável** | `runtime.loop_factory()` usa `os.name == "nt"` e o motivo dado (mypy apaga um ramo de `sys.platform` com `warn_unreachable`) é real. A consequência prática — `python -m vendinha` em vez de `uvicorn vendinha.app:app` — está documentada no `__main__.py`, no `Makefile` e no README do alvo. Usei `runtime.run()` nos meus próprios scripts e o `psycopg` async funcionou; é a prova pela via de uso |
| **D-6** (nome não tem forma) | **Argumento correto, resolução incompleta** | A distinção entre "por padrão" e "por valor conhecido" é honesta e a tabela que a spec acrescenta é o jeito certo de descrever. E o registro ser **do processo** em vez da sessão é decisão bem fundamentada: confirmei que a redação roda na thread de export do OTel, onde um `contextvar` da thread da requisição não estaria. **O que falta é fechar o laço no REQ-4**, que continua dizendo "nome" e continua `[x]`. Ver NC-3. Nota adicional: `KNOWN_VALUES.remember` não tem **nenhum** chamador em produção (grep), então na S-02 o mecanismo é código morto — a spec diz isso, mas vale registrar que a metade testada do REQ-4 é a que nada exercita |
| **D-7** (`localhost` → `::1` pendura) | **Legítima, e corrigida pela própria D-12** | `with_connect_timeout` injeta `connect_timeout=5` sem sobrescrever quem já traz um — li a função e ela faz exatamente isso. A auto-correção na D-12 é o comportamento certo (medir em vez de generalizar) |
| **D-8** (`PUT /config` só em `APP_ENV=local`) | **Legítima, e é a melhor decisão da spec** | Restrição em vez de promessa. Falsifiquei (F31): remover o guarda reprova. `GET /config` continua liberado e devolve `editable: false` fora de local. A consequência para a S-07/S-08 está escrita como consequência, não escondida |
| **D-9** (sem catálogo de modelos) | **Legítima, e o número confere** | **119 modelos** na minha execução, exatamente o que a spec afirma. O argumento (ADR-001 aplicado ao próprio código-fonte) é o melhor raciocínio do documento. Confirmei o fallback: com uma chave inválida o `models.list()` levantou `AuthenticationError`, `models_offered_by` devolveu lista vazia e `GET /models` respondeu 200 com o resto |
| **D-10** (recusa subiu para o endpoint) | **Legítima** | `write_config` checa `Vault(...).usable` antes de chamar o store, e o store mantém a sua como defesa em profundidade. `503` e não `500` está certo. Falsifiquei nos dois níveis (F32) |
| **D-11** (Langfuse caiu no meio da medição) | **Legítima como observação, insuficiente como verificação** | A nota de método — *"esperar a falha acontecer sozinha"* — é boa, mas ela dispensa a verificação em vez de fazê-la, e a exigência do ADR-010 fica dependendo de a nuvem ter uma tarde ruim no dia certo. Eu **provoquei** a falha (`LANGFUSE_BASE_URL` numa porta morta) e o resultado bate: 200 em 0,97–1,94 s, zero traceback. A conclusão do autor está certa; o método de chegar nela não é repetível, e essa é justamente a diferença que a spec cobra dos outros |
| **D-12** (`127.0.0.1` por quem disca + `API_HOST`) | **Legítima, e o achado embutido é o melhor da spec** | A regra "quem disca" está no `.env.example` com o raciocínio de origem/CORS, que é certo. O `API_HOST=0.0.0.0` combinado com a D-8 era de fato uma rota de gravação de credencial exposta na rede local, e o autor registrou como o que é. Confirmei que `Settings.api_host` tem default `127.0.0.1` **no código também**, não só no exemplo — que é o que faz a correção valer para quem não copiou o `.env.example` |

**Descoberta que eu esperaria e não encontrei registrada:** que quatro testes da suíte precisam
de uma variável de ambiente que o CI não tem. É o tipo de coisa que aparece na primeira execução
fora da máquina, e a spec fecha declarando *"Suíte local verde"* — a palavra "local" está lá, e
é exatamente o problema.

---

## 8. Não-conformidades (fora da tabela de requisitos)

| # | Achado | Gravidade |
|---|---|---|
| **NC-1** | **A suíte não passa fora da máquina do autor, e o job que ela quebra é check obrigatório.** Em cópia limpa do `HEAD` sem `.env` — a condição exata do job `test` do CI — dá **4 failed, 352 passed**. Os quatro fazem `PUT /config`, que responde `503` sem `CONFIG_ENCRYPTION_KEY`. Reproduzi por dois caminhos independentes (cópia limpa; e `CONFIG_ENCRYPTION_KEY=` no shell do próprio repo), com o mesmo resultado. Duas coisas agravam. Primeira: o autor **descreve essa classe de bug** num comentário dentro do mesmo arquivo (*"a test whose answer depends on whether the developer happens to have a key in `.env` passes on one machine and fails on the next, and the failure looks like a bug in the code"*) e corrigiu só a instância que o incomodou. Segunda: o `.env.example` distribui `CONFIG_ENCRYPTION_KEY=` **vazio**, então nem quem seguir o quickstart à risca terá a suíte verde. O conserto é uma fixture de três linhas fixando a chave, no mesmo padrão que `test_the_config_response_says_whether_encryption_is_ready` já usa | **Alta** |
| **NC-2** | **A metade "logs" do R5 é inerte na aplicação real, e nada testa isso.** `docs/riscos.md` R5 é *"vazamento de PII em traces **e logs**"*; o REQ-4 é declarado invariante de release. Dois defeitos independentes, e cada um sozinho já basta: **(a)** `install_log_redaction()` percorre `logging.getLogger().handlers`, que sob uvicorn está **vazio** — medi `root handlers: []` — então zero filtro é instalado; o registro cai no `logging.lastResort` e sai em claro (`cliente informou 123.456.789-09`). **(b)** o filtro nunca toca `record.exc_info`, então o traceback sai inteiro — e é o `logger.exception("failed to generate an answer for session %s", …)` do `app.py` que recebe qualquer exceção do SDK do fornecedor ou do psycopg; medi com uma chave falsa e um CPF, os dois presentes na saída formatada. O docstring do módulo nomeia **exatamente** esse caso como o que ele existe para cobrir. A falsificação **F14** (apagar a instalação do filtro) deixa a suíte **verde**, o que é o achado dentro do achado: o teste está no diretório `security`, cuja definição em `docs/testes.md` §1 é *"a ação proibida é alcançável?"*, e ele responde a pergunta da camada `unit` | **Alta** |
| **NC-3** | **REQ-4 diz "nome", o código não mascara nome, e o requisito continua marcado `[x]`.** Medi no trace bruto: `Marta Ribeiro` e `Marta` presentes em claro. A D-6 explica por quê, o argumento está certo e a solução entregue é honesta — mas a resolução parou antes de tocar o texto do requisito. E o próprio autor mostra, na mesma spec, que sabe fazer isso: o REQ-3 recebeu a emenda inline *"O texto original dizia `LANGFUSE_HOST`… Ver D-1."*. O REQ-4 não recebeu nada. Sob o `CLAUDE.md`, a spec é a fonte da verdade da sessão; a sessão da S-04 vai ler *"Mascaramento de PII (CPF, e-mail, nome)"* marcado como entregue e concluir que nome já está coberto — quando o que existe é um registro que **ninguém em produção alimenta** (`KNOWN_VALUES.remember` não tem chamador). É o mesmo dano que a NC-1 do relatório da S-01 descreve: texto de requisito apontando a próxima sessão para a conclusão errada | **Média** |
| **NC-4** | **Três normativos contradizem o `CLAUDE.md` sobre quando a verificação acontece.** O `CLAUDE.md` item 4 (precedência **1**) diz *"Verificação independente ANTES do PR… Sem veredito, não existe PR"*. Continuam dizendo o contrário: `docs/adr/ADR-005-…:16` (*"relatório de verificação independente anexado antes do **merge**"*, precedência **5**), `.claude/commands/verificar-spec.md:27` (passo 6: *"Publicar o relatório como comentário no PR"*, e o arquivo de comando não está na lista de precedência) e o corpo da **issue #3** (*"3. PR com evidência… 4. `/verificar-spec` em sessão nova → relatório anexado ao PR"*). É contradição herdada do commit `ce8b46f` da S-01 — a R-9 daquele relatório sinalizou o commit e **não** a contradição que ele criou. Mas a S-02 é a primeira spec executada sob a ordem nova e não reconciliou, e o efeito é concreto: **esta sessão teve que receber uma exceção escrita ao ritual para poder executá-lo**. Pelo mecanismo do próprio repositório, o ADR-005 pede nota de cabeçalho (como o ADR-003 e o ADR-002 receberam), e o arquivo de comando pede uma edição de uma linha | **Média** |
| **NC-5** | **A tabela de execução declara 9 commits; a branch tem 10.** Falta `96ecfd6 fix(s-02): apply the loopback rule per caller…`, que é justamente o commit da D-12 — a descoberta está escrita, a linha da tabela não. A spec ainda afirma **"9 commits para 7 tasks"** e explica as duas diferenças; são três. É a repetição literal da **NC-4 do relatório da S-01** (*"a tabela parou um commit antes do fim"*), no mesmo artefato e pelo mesmo motivo | **Baixa** |
| **NC-6** | **`.claude/settings.json` perdeu o deny de `.env.*`, e o `.gitignore` discorda dele.** O commit `dca2419` remove `"Read(./.env.*)"` com a justificativa de que a regra cobria o `.env.example` versionado — o que é verdade. Mas o efeito colateral é liberar a leitura de `.env.local`, `.env.dev`, `.env.production`: e o `.gitignore` deste repositório ignora **`.env.*`** com `!.env.example`, ou seja, o repositório já declara que qualquer `.env.*` que não seja o exemplo é segredo. O cabeçalho do próprio `.env.example` descreve as duas garantias como pareadas (*"o `.gitignore` impede o commit, a regra de permissão impede a leitura"*), e elas deixaram de estar pareadas. O conserto é o mesmo movimento, feito na direção certa: negar `.env.*` e permitir `.env.example` | **Média** |
| **NC-7** | **"Os treze testes-âncora da S-02 declaram o marker: 21 passed".** São **21** testes com `@pytest.mark.risco` (R5: 10, R6: 7, R9: 4), não treze — a frase se contradiz dentro dela mesma. Somando: a **issue #3** declara `ADRs: ADR-007` enquanto o frontmatter da spec declara `[ADR-001, ADR-007, ADR-010, ADR-012]`; a issue é ponteiro e a spec vence, mas o ponteiro está desatualizado justamente no campo que a S-02 mais mexeu | **Baixa** |

---

## 9. Riscos observados e ressalvas

| # | Ressalva | Por que importa |
|---|---|---|
| **R-1** | **A precedência "banco vence ambiente" não é testada onde ela decide.** Inverti `_credentials()` para o ambiente ganhar (F34) e a suíte ficou **verde**, incluindo o teste chamado `test_a_stored_credential_wins_over_the_environment` — porque ele afirma sobre o campo `source` do `/config`, que `read_config` calcula direto de `stored.credentials`, e não sobre a função que escolhe a chave entregue ao `resolve_model`. | O ADR-012 chama isso de invariante (*"o que está no banco vence o que está no ambiente"*), e o modo de falha é o pior possível: a UI diz `source: "banco"`, a dica mostra os quatro caracteres da chave nova, e o processo continua gastando na chave velha do `.env`. Um teste que asserte sobre a chave que `_graph_for` recebe fecha isso. |
| **R-2** | **`_allowed_models()` chama os fornecedores em toda requisição de chat que traga `model`.** Medi os dois caminhos na mesma máquina, mesmo modelo, n=10 cada: **sem `model`, p95 = 1,034 s**; **com `model`, p95 = 3,331 s** (mediana 2,621 s). O alvo da spec é ≤ 3 s. | O campo `model` é o que o REQ-6 acrescenta, e a tela da S-07 vai mandá-lo em toda mensagem — o caminho medido pela spec é o que a UI **não** vai usar. Além da latência, são duas chamadas HTTP a fornecedores por turno de conversa, que é superfície de rate limit e de custo dentro do risco R6, que esta mesma spec fecha. Um cache com TTL na lista de modelos resolve os dois de uma vez. |
| **R-3** | **`redact()` — a função pattern-only — não tem consumidor em produção.** Só `Redactor.text` via `redactor()` é chamado pelo código real. Seis das dez asserções do arquivo de `security` exercitam `redact()`. | Não é defeito: as duas de export e a de log cobrem o caminho verdadeiro, e é por isso que F8/F10 foram pegas. Mas vale saber que a maioria do arquivo testa uma função que a aplicação não chama, o que explica por que F13/F14 escaparam. |
| **R-4** | **`Redactor.attributes` só redige valores `str`.** Atributos de OpenTelemetry podem ser sequências de strings, e uma `tuple[str, …]` atravessa o hook intocada. | Hoje não vi nenhum atributo assim nos traces que auditei, então é risco latente e não vazamento observado. Mas o hook é a fronteira, e "hoje o LangChain não emite listas" é uma garantia de terceiro, não nossa. |
| **R-5** | **`LOG_LEVEL` está no `.env.example` marcado `(S-02)` e nenhum código o lê.** `Settings` não tem o campo; grep em `backend/`, `scripts/` e `Makefile` não acha consumidor. | Variável documentada e inerte é pior que variável ausente: quem for depurar vai colocar `LOG_LEVEL=DEBUG` e concluir que não há o que ver. Combina mal com a NC-2, onde justamente o log é o problema. |
| **R-6** | **`vendinha/db.py:main()` imprime o `DATABASE_URL` inteiro no stderr quando falha**, senha incluída. | É CLI local e a intenção (ajudar quem acabou de rodar `make db-setup`) é boa. Mas é o mesmo canal que a NC-2 mostra estar sem redação, e a S-08 vai levar este módulo para uma VPS. Imprimir o DSN com a senha mascarada custa uma linha. |
| **R-7** | **`resolve_model` tem `lru_cache(maxsize=8)` com a `api_key` na chave do cache.** Correto para invalidar em rotação, e significa que a credencial fica num cache de módulo pelo tempo de vida do processo. | Não é vazamento — o segredo já está em memória de qualquer jeito. Registro porque a S-08 vai discutir dump de memória e core dump, e este é o lugar onde a chave persiste mais do que se espera. |
| **R-8** | **`GET /config` é aberto e diz `encryption_ready`, `editable`, os provedores configurados e a dica de 4 caracteres — sem autenticação, em qualquer ambiente.** | A D-8 fechou a escrita e argumenta que a leitura *"não expõe nada"*. Expõe pouco, não nada: para quem faz reconhecimento, a resposta diz que provedor está configurado, se a instância aceita escrita e se falta chave de criptografia. Provavelmente aceitável até a S-08; merece uma linha explícita lá em vez de ser redescoberto. |
| **R-9** | **Ressalvas herdadas da S-01 que continuam abertas: R-3 (fixture ↔ seed é acordo humano), R-5 (corpo do ADR-003 diz "integração"), R-10 (seed malformado quebra a coleta).** Confirmei as três: continuam válidas e a S-02 não piorou nenhuma. | A spec as registra com honestidade e o diagnóstico dela bate com o meu. Nenhum arquivo novo desta spec constrói dado no import de módulo, como ela afirma — verifiquei. |
| **R-10** | **O `README` do quickstart e o `Makefile` mandam `make db-setup` antes de `make api`, e nada sanciona o esquecimento.** `open_checkpointer` não roda `setup()`, por decisão explícita e correta (migração não pertence ao startup). | A decisão está certa; o custo é que quem pular o passo recebe um erro de tabela inexistente na primeira mensagem, não no boot. Uma mensagem de erro que diga *"rode `make db-setup`"* transformaria isso num desvio de trinta segundos. |
| **R-11** | **O `.venv` desta máquina é Python 3.13.2 e o CI usa 3.12.** Todos os meus números vêm do 3.13. | Nada no diff depende de versão menor, e `mypy` está fixado em `python_version = "3.12"` de qualquer jeito. Registro para que ninguém leia "356 passed" como medido no mesmo interpretador do CI. |

---

## 10. Veredito

# REPROVADO

**Por que não APROVADO COM RESSALVAS.** Duas coisas independentes reprovam, e nenhuma delas é
questão de julgamento.

A primeira é a **NC-1**: a suíte não passa numa cópia limpa do repositório. Não é uma previsão
— é uma medição, feita por dois caminhos independentes, com o mesmo resultado: **4 failed, 352
passed**. O job `test` é *required check* da `main`, o `Definition of Done` da própria spec tem
"CI verde no PR" como item, e a métrica publicada — *"356 passed"* — só é verdadeira na máquina
onde foi medida. Uma spec cujo tema é observabilidade e reprodutibilidade não pode fechar com a
suíte dependendo de um arquivo que o `.gitignore` proíbe de existir em qualquer outro lugar. E o
que faz disso reprovação em vez de ressalva é que o autor **já tinha identificado essa classe de
falha por escrito, no mesmo arquivo**, e a corrigiu numa instância enquanto deixava quatro.

A segunda é a **NC-2**, e ela é mais séria do que o número de linhas necessárias para consertá-la.
O REQ-4 é declarado *"invariante de release"* e a `docs/riscos.md` R5 diz *traces **e** logs*. A
metade "traces" é excelente e eu a auditei no serviço real: CPF nas duas formas, e-mail e
telefone saem mascarados de um lote que inclui span de instrumentação de terceiro. A metade
"logs" **não roda**: sob uvicorn o root logger não tem handler, `install_log_redaction()` instala
zero filtros, e o registro sai em claro pelo `lastResort` — medido, não inferido. Mesmo se
instalasse, o traceback continuaria passando, porque `record.exc_info` nunca é tocado — e é o
`logger.exception` do `app.py` que recebe qualquer exceção do SDK do fornecedor ou do psycopg,
isto é, exatamente as que carregam credencial e DSN. E o teste que deveria pegar isso está no
diretório `security`, cuja definição normativa é *"a ação proibida é alcançável?"*: apagar a
instalação inteira do filtro **deixa esse teste verde**. Um invariante de release cuja
verificação não distingue "o código foi escrito" de "o código está no caminho" não é um
invariante.

**Por que não é uma reprovação severa.** É importante dizer, porque a distância entre esta
entrega e uma aprovação é curta. **31 de 34 falsificações reprovaram no teste certo**, incluindo
as que atacam alcance e não função — o hook de export pego quando ignora o span do `langchain`,
o guarda de budget pego quando é movido para depois da chamada ao modelo, o `thread_id` pego
quando deixa de isolar sessões. Todos os invariantes do ADR-012 se sustentaram sob medição
adversarial contra serviços reais: cinco rotas varridas, o `bytea` do Postgres lido, o log do
processo varrido, nenhuma ocorrência da chave. A retomada do R9 foi provada com dois PIDs
diferentes contra Postgres de verdade, que é a versão forte do requisito. O ADR-010 foi
verificado provocando a falha em vez de esperar por ela. O escopo foi respeitado ao pé da letra:
nenhum RAG, nenhum subagent, nenhuma tool, nenhuma tela, nenhum modelo de usuário. Nenhum
segredo, CPF, CNPJ ou dado real no diff, com `gitleaks` limpo em 40 commits. E o conjunto de
decisões registradas — a D-8 acima de todas, que fecha uma rota por ambiente em vez de prometer
consertá-la depois — é de qualidade acima do que a spec precisava entregar.

### Condições para a S-02 ser considerada fechada

1. **NC-1** — fixar `CONFIG_ENCRYPTION_KEY` nos testes que gravam credencial, no mesmo padrão
   que `test_the_config_response_says_whether_encryption_is_ready` já usa. Critério de aceite:
   `git archive HEAD` para um diretório sem `.env`, suíte verde lá.
2. **NC-2** — fazer a redação de log valer na aplicação: instalar o filtro onde os registros
   realmente passam (o `dictConfig` do uvicorn, ou um handler próprio no root), e cobrir
   `record.exc_info`. E acrescentar ao arquivo de `security` o teste de **alcance** que hoje não
   existe: um que reprove se `install_log_redaction()` deixar de instalar alguma coisa.
3. **NC-3** — emendar o texto do REQ-4 como o REQ-3 foi emendado, nomeando as duas garantias da
   tabela da D-6. "Nome" mascarado por valor conhecido, com o registro sem chamador até a S-04.
4. **NC-6** — restaurar o deny de `.env.*` com exceção para `.env.example`, para as duas
   garantias que o próprio `.env.example` descreve voltarem a estar pareadas.
5. **NC-4** — reconciliar os três normativos com o `CLAUDE.md` (nota de cabeçalho no ADR-005,
   uma linha em `.claude/commands/verificar-spec.md`, o corpo da issue #3). É barato e é o que
   impede a próxima sessão revisora de precisar de uma exceção escrita para executar o ritual.
6. **NC-5 e NC-7** — atualizar a tabela de commits (10, não 9), o "treze testes-âncora" (21) e o
   campo `ADRs` da issue #3.

**R-1 e R-2 merecem decisão antes do PR, mesmo que a correção fique para a S-03.** A R-1 descreve
um invariante do ADR-012 que hoje passa por um teste que não o testa — é a única ressalva desta
lista que descreve um portão aberto, e eu passei por ele. A R-2 é a única métrica de sucesso da
spec que eu medi **estourando o alvo**, no caminho que a S-07 vai usar por padrão.

As demais (R-3 a R-11) podem ser tratadas nas specs seguintes, desde que registradas.

---

*Relatório produzido por sessão revisora independente, sem acesso ao histórico da sessão autora.
Todos os números acima foram medidos nesta máquina, nesta sessão, contra o Postgres do compose,
o Langfuse Cloud real e as APIs da Anthropic e da OpenAI reais. Nenhum arquivo do repositório foi
alterado por esta sessão: os arquivos quebrados durante as 34 falsificações foram restaurados com
`git checkout --`, o banco `vendinha_verif` criado para os testes de credencial foi derrubado, as
linhas de checkpoint de teste foram removidas, e `git status --short` ao final acusa apenas este
relatório e o `docs/workshop/apresentacao.html` não rastreado, que já existia antes.*

*Uma nota de processo, registrada porque é achado e não incômodo: o passo 6 do
`.claude/commands/verificar-spec.md` manda publicar este relatório como comentário no PR, e não
existe PR — porque o `CLAUDE.md`, que tem precedência 1, mudou o ritual para verificação **antes**
do PR. A entrega é só o arquivo, por decisão do documento superior. Ver **NC-4**.*
