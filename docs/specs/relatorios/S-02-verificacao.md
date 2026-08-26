# Relatório de verificação independente — S-02 (Agente base observável)

> **Terceira rodada.** A rodada 1 reprovou (2 Alta). A rodada 2 aprovou com ressalvas (1 Alta,
> 3 Média, 4 Baixa). Este relatório **substitui** o arquivo anterior no mesmo caminho — e por isso
> a §2 carrega a rastreabilidade das **três** rodadas linha a linha, e a §9 carrega **todas** as
> ressalvas ainda abertas, inclusive as que o autor deixou cair ao transcrevê-las para a spec.
> Nada aqui foi herdado de texto anterior sem ser remedido nesta sessão: cada "fechada" é um
> defeito que **eu** reproduzi e depois provei que não existe mais.

| | |
|---|---|
| **Spec** | `docs/specs/S-02-agente-observavel.md` (`status: em-revisao`) |
| **Branch** | `spec/s-02-agente-observavel` @ `082c48b` (**12 commits**) |
| **Base** | `origin/main` @ `cb51953` |
| **PR** | **não existe.** Correto sob o `CLAUDE.md` item 4 (*"Verificação independente ANTES do PR… Sem veredito, não existe PR"*). O passo 6 do `.claude/commands/verificar-spec.md` manda comentar no PR; o `CLAUDE.md` tem precedência e a entrega é o arquivo. Ver **NC-4**, que continua aberta |
| **Issue** | [#3](https://github.com/suajornadadedados/vendinha-jornada/issues/3) — **OPEN**, corpo é ponteiro, `updatedAt` 2026-08-26T18:47Z |
| **Diff** | 12 commits · 41 arquivos · +6.398 / −233 |
| **Rodada 1** | REPROVADO · 2 Alta · 34 falsificações, 3 sobreviveram |
| **Rodada 2** | APROVADO COM RESSALVAS · 1 Alta · 3 Média · 4 Baixa · 13 falsificações, 3 sobreviveram |
| **Rodada 3 (esta)** | **18 falsificações, 4 sobreviveram** · 1 Alta · 4 Média · 3 Baixa |
| **Sessão** | revisora, independente, sem acesso ao histórico da sessão autora nem ao das sessões revisoras anteriores além do arquivo que elas deixaram |
| **Data** | 2026-08-26 |
| **Ambiente** | Windows 11 · Docker · `backend/.venv` = **Python 3.13.2**; medi **também** num venv 3.12 recém-criado a partir de `tests/requirements.txt`, que é a condição exata do job `test` · `make` **não existe** nesta máquina, rodei a linha de dentro de cada alvo |
| **Infra** | `docker compose` no ar: `vendinha-postgres-1` healthy em `127.0.0.1:5433`, `vendinha-qdrant-1` em 6333/6334. A 5432 do host está ocupada por um Postgres nativo |
| **Veredito** | **REPROVADO** |

> **Nota de método sobre o `.env`.** A leitura do `.env` é negada ao agente por regra em
> `.claude/settings.json` e eu não a burlei: em nenhum momento li o arquivo, e nenhum valor de
> credencial aparece neste relatório. Onde precisei de configuração passei variáveis pelo meu
> próprio shell (`DATABASE_URL`, `API_HOST`, `API_PORT`, `APP_ENV`, `SESSION_BUDGET_TOKENS`,
> `LANGFUSE_BASE_URL`, e uma `CONFIG_ENCRYPTION_KEY` gerada por mim). Onde a medição exigia a
> credencial real — subir a API e consultar o trace de volta no Langfuse Cloud — usei
> `vendinha.config.get_settings()` de dentro de um script e imprimi **só o resultado**. Chamadas
> reais à Anthropic, à OpenAI e ao Langfuse Cloud, com custo real e pequeno.

> **Nota sobre o rastro que deixei.** Bancos `vendinha_verif3` e `vendinha_semtabela` criados e
> **derrubados** ao final; o banco `vendinha` do autor não foi tocado (132 checkpoints antes e
> depois, `instance_config.credentials` NULL, `updated_at` anterior a esta sessão). Os **38
> traces** que produzi no Langfuse Cloud (prefixo de sessão `verif3-`) foram enviados para
> exclusão pela API (`DELETE /api/public/traces` → 200); a remoção do Langfuse é assíncrona e
> ainda aparecia pendente no momento em que escrevo. `git status --short` ao final acusa apenas
> este relatório e `docs/workshop/apresentacao.html`, não rastreado, que já existia antes.

---

## 1. Resumo

**Quase tudo que a rodada 2 apontou foi de fato consertado, e eu medi um por um.** O achado Alta
da rodada 2 (**NC-A**) está fechado de verdade: apagar `install_log_redaction()` do `lifespan`
agora **reprova** — e o teste é auto-guardado, porque fazer o próprio `redaction_is_installed()`
mentir também reprova. A senha do DSN é redigida no caminho real do formatter. O cache de modelos
ganhou invalidação e armazenamento testados. O aquecimento no boot tirou 2,4 s do primeiro pedido,
medido. A contagem de testes-âncora bate. A mensagem de commit voltou ao inglês.

**E o mesmo erro apareceu pela terceira vez, no lugar em que ele é mais caro.** A instrução desta
rodada mandava procurar *"o conserto que satisfaz a letra do achado e deixa a mesma pergunta aberta
um nível acima"*. Ele está em `observability.client()`:

```
apaguei  mask_otel_spans=mask_otel_spans  do construtor do cliente Langfuse
suíte    365 passed
trace    CPF, e-mail e telefone EM CLARO no Langfuse Cloud
```

Não é hipótese. Subi a aplicação real com essa única linha removida, mandei uma conversa com CPF,
e-mail e telefone, e li o trace de volta pela API pública: `123.456.789-09`, o e-mail e o telefone
saíram **em texto claro**, sem nenhum `[CPF]`, `[EMAIL]` ou `[TELEFONE]`. A suíte inteira continua
verde. Ver **NC-I**.

A rodada 1 achou que nada provava que o *filtro* era instalado. A rodada 2 achou que nada provava
que a *aplicação* instalava o filtro. Ninguém nunca fez a mesma pergunta sobre a **outra metade do
REQ-4** — a que a spec chama de *invariante de release* e sobre a qual o ADR-010 apoia a decisão de
usar Langfuse Cloud: *o gancho de mascaramento está de fato montado no cliente que exporta?*
Os testes chamam `mask_otel_spans(params=…)` diretamente. Chamam a função. De novo.

**Duas afirmações da spec são falsas por medição.** Não são imprecisões de redação:

1. A **D-14** e a mensagem do commit `082c48b` dizem, sobre a NC-B: *"An infinite TTL, a cache that
   never stores, and a `PUT /config` that never invalidates all passed. **Three tests, three breaks
   that now fail.**"* Medi as três. Duas reprovam. **`MODELS_CACHE_SECONDS = 1e12` — que é
   literalmente a falsificação V9 da rodada 2 — continua deixando a suíte com 365 passed**, porque
   o teste novo monkeypatcha a constante para `0.0` e portanto nunca pode enxergar o valor dela.
   Ver **NC-J**.
2. A tabela de ressalvas da spec diz que a **R-6** está *"Mitigado pela NC-C (a senha agora é
   redigida)"*. Rodei `python -m vendinha.db` com um DSN com senha: a senha saiu **inteira** no
   stderr. `db.py:main()` usa `print`, e `print` não passa por `logging` — a redação da NC-C nunca
   o alcança. Ver **NC-M**.

Fora isso a entrega é sólida e eu a medi contra serviços reais: **os seis requisitos estão
CONFORME**, a suíte é verde na condição exata do CI (**365 passed** num venv 3.12 novo, montado só
com `tests/requirements.txt`, num `git archive` sem `.env`), `ruff` e `mypy --strict` limpos,
`gitleaks` sem achados em 42 commits, `commitlint` com 0 problemas, escopo respeitado ao pé da
letra, nenhum segredo ou dado real no diff, e **14 das 18 falsificações reprovaram no teste certo**.

**6 CONFORME · 0 NÃO CONFORME · 0 NÃO VERIFICÁVEL** (requisitos), com **1 Alta, 4 Média e 3 Baixa**
fora da tabela de requisitos.

---

## 2. Rastreabilidade das três rodadas

Toda linha foi remedida nesta sessão. "Fechada" = eu reproduzi o defeito original e depois provei
que ele não existe mais.

### 2.1 Achados da rodada 1

| # | Rodada 1 | Rodada 2 | **Rodada 3 (medido por mim)** |
|---|---|---|---|
| **NC-1** (Alta) | Suíte `4 failed` em cópia limpa sem `.env` — condição do job `test` | fechada | **CONTINUA FECHADA, e agora na condição real do CI.** A rodada 2 mediu com o venv gordo do autor; eu montei um venv **Python 3.12** novo só com `tests/requirements.txt` sobre um `git archive HEAD` sem `.env` e sem nenhuma variável no shell: **365 passed em 2,13 s**. `vendinha.config.ENV_FILE` aponta para a cópia e `exists() == False`, confirmado |
| **NC-2** (Alta) | `install_log_redaction()` inerte sob uvicorn; filtro sem alcance ao traceback | fechada | **CONTINUA FECHADA.** Reproduzi o caminho de produção (`dictConfig(uvicorn.config.LOGGING_CONFIG)` + `install_log_redaction()` → **8 handlers embrulhados**) e o traceback saiu com `[CREDENCIAL]`, `[CPF]` e a senha do DSN redigida. Falsificações **F12–F16**: 5 quebras, 5 reprovações |
| **NC-3** (Média) | REQ-4 dizia "nome" e ficava `[x]` com nome em claro | fechada | **CONTINUA FECHADA.** Texto do REQ-4 nomeia as duas garantias. Auditei o trace bruto real: `Marta` em claro, exatamente como o requisito passou a declarar |
| **NC-4** (Média) | ADR-005, `verificar-spec.md` §6 e a issue #3 contradizem o `CLAUDE.md` | aberta, adiamento aceito | **ABERTA.** Reconferi os três: `ADR-005` linha 16 continua *"relatório de verificação independente anexado antes do **merge**"*; `verificar-spec.md` passo 6 continua *"Publicar o relatório como comentário no PR"*; o corpo da issue #3 continua com *"3. PR… 4. `/verificar-spec` → relatório anexado ao PR"*. **Terceira sessão revisora seguida que precisa de exceção escrita para executar o próprio ritual.** O adiamento continua bem argumentado; registro que o custo já foi pago três vezes |
| **NC-5** (Baixa) | Tabela de execução um commit atrás | fechada | **REABERTA — terceira ocorrência.** `git rev-list --count origin/main..HEAD` = **12**; a tabela tem **11 linhas** e o texto diz *"11 commits para 7 tasks"*. Falta `082c48b`. Ver **NC-N** |
| **NC-6** (Média) | `dca2419` tirou o deny de `.env.*` | parcialmente fechada | **PARCIAL, inalterada.** O deny enumera oito nomes; o `.gitignore` continua ignorando `.env.*` com `!.env.example`. Ver **NC-G** abaixo |
| **NC-7** (Baixa) | "treze testes-âncora" onde eram 21 | metade fechada, metade regrediu | **FECHADA.** Medi por marker: **26 passed, 339 deselected** — R5 **15**, R6 **7**, R9 **4**. A spec diz exatamente isso. Issue #3 com `ADRs: ADR-001, ADR-007, ADR-010, ADR-012`, igual ao frontmatter |
| **R-1** | Inverter "banco vence ambiente" não quebrava nada | fechada | **CONTINUA FECHADA.** `effective_credentials()` é função pura e o `app.py` a usa. Não refalsifiquei por conta do escopo desta rodada; a rodada 2 mediu as duas quebras (V6, V7) |
| **R-2** | p95 do 1º token com `model` era 3,331 s | fechada no quente | **CONTINUA FECHADA.** p95 medido por mim, n=10 contra a API real: **1,278 s com `model`**, 1,267 s sem. Alvo ≤ 3 s |

### 2.2 Achados da rodada 2

| # | Rodada 2 | **Estado agora** | Como eu medi |
|---|---|---|---|
| **NC-A** (Alta) | Apagar `install_log_redaction()` do `lifespan` deixava a suíte verde | **FECHADA** | Falsificação **F1**: apaguei a chamada → `1 failed`, e o teste que reprova é `test_the_application_turns_redaction_on_when_it_starts`, que sobe `TestClient(create_app(...))` de verdade. Falsificação **F17**: fazer `redaction_is_installed()` devolver `True` sempre **também** reprova, porque o teste afirma `not redaction_is_installed()` antes de subir a app. O teste se auto-guarda — é a melhor peça desta correção |
| **NC-B** (Média) | Cache de modelos entrou sem teste; V8 e V9 sobreviviam | **PARCIALMENTE FECHADA** | **F3** (tirar `models_cache = None` do `PUT /config`) → reprova ✔. **F4** (o cache nunca armazena) → reprova ✔. **F2** (`MODELS_CACHE_SECONDS = 1e12`, a V9 literal) → **365 passed** ✘. A spec e o commit afirmam que as três reprovam. Ver **NC-J** |
| **NC-C** (Média) | Senha dentro do DSN não era redigida | **FECHADA para os casos nomeados; resíduo medido** | Medido **através do formatter real**, não só da função: `@postgres`, `@db`, `@127.0.0.1` e `@vendinha-db.interno` saem como `vendinha:[CREDENCIAL]@host:5432/db`, com usuário, host e porta preservados. **F5** (tirar `DSN_PASSWORD` de `PATTERNS`) reprova. Resíduo em §8.1 **NC-C-r**: senha com `/`, `?` ou `#` vaza inteira |
| **NC-D** (Média) | As ressalvas viviam só no relatório, que o ritual sobrescreve | **PARCIALMENTE FECHADA** | A spec ganhou a tabela *"Ressalvas da verificação da S-02 que ficam para as specs seguintes"* com NC-4 e R-3…R-11. **R-12 e R-13 da §9 da rodada 2 não foram transcritas** — `grep` na spec por `R-12`, `R-13`, `chave de acesso` e `StreamHandler`: nenhuma ocorrência. O mecanismo que a NC-D descreve falhou de novo, dentro do commit que existia para consertá-lo. As duas estão de volta na §9 deste relatório |
| **NC-E** (Baixa) | Contagem de testes-âncora desatualizada | **FECHADA** | 26 = 15 + 7 + 4, idêntico ao que a spec escreve |
| **NC-F** (Baixa) | Mensagem de commit em português | **FECHADA no git; resíduo na spec** | `4bc5a1e` agora é `fix(s-02): address the findings of the independent verification`. `commitlint --from origin/main --to HEAD`: **0 problems**, 4 avisos `footer-leading-blank`. Mas a tabela de execução da spec ainda cita o título antigo, em português. Ver **NC-N** |
| **NC-G** (Baixa) | Resíduo do deny enumerado não estava escrito | **METADE FECHADA** | (a) A spec agora explica a enumeração e o resíduo ✔. (b) O cabeçalho do `.env.example` continua descrevendo as duas garantias como pareadas (*"o .gitignore impede o commit, a regra de permissão impede a leitura"*) sem dizer que a segunda vale para oito nomes ✘. Confirmei que `.env.staging` continua legível pelo agente e git-ignorado |
| **NC-H** (Baixa) | Custo do formatter crescia até 17,28 ms com o registro cheio | **FECHADA no regime permanente; custo novo no churn** | Bancada minha, mesma máquina, mesma string, implementação antiga reconstruída ao lado da nova: **26,15 ms → 0,31 ms com 512 nomes (80×)**. A melhora é real e grande. Duas ressalvas em §8.1: o número publicado (0,065 ms) não reproduz no caminho real (**0,32 ms**), e o caminho de *cache miss* custa **6–17 ms** por nome novo. Ver **NC-H-r** |
| **R-2b** | 1º pedido com `model` custava 4,0 s a frio | **FECHADA e medida** | Com `_warm_models` no lifespan: boot 3,64 s, **1º pedido com `model` em 1,360 s**. Falsificação **F6** (tirar o aquecimento): boot 1,07 s, **1º pedido em 3,801 s**, 2º em 1,045 s. O conserto funciona. **Mas F6 deixa a suíte verde** — ver **NC-L** |

---

## 3. Conformidade requisito a requisito

| # | Requisito | Status | Evidência que EU produzi nesta rodada |
|---|---|---|---|
| REQ-1 | FastAPI com `POST /chat` (SSE) e sessões; grafo LangGraph mínimo | **CONFORME** | API real (`python -m vendinha`, porta 8231) contra o Postgres do compose e o modelo real. SSE abre com `event: session`, transmite `event: token`, fecha com `event: done`. `GET /models` devolveu **119 modelos** dos dois fornecedores. `POST /chat` com `model` fora da lista → 422 (**F13** reprova quando a allowlist sai) |
| REQ-2 | Checkpointer em Postgres; estado carrega só IDs | **CONFORME** | A metade manual do R9, na versão forte: processo A gravou 2 turnos em `verif3-r9`; **processo novo** (reinício de verdade) respondeu *"Aurélio. É você mesmo."*; sessão diferente (`verif3-r9-outra`) respondeu *"você não me apresentou seu nome ainda"*. 9 checkpoints na thread retomada, 3 na isolada |
| REQ-3 | Langfuse Cloud instrumentado; indisponibilidade não propaga (ADR-010) | **CONFORME** | Trace real consultado de volta pela API pública: `sessionId` preenchido, `latency 2,586`, `totalCost 0,001126`, 3 observações, 13.077 bytes. ADR-010 **provocado**: subi a API com `LANGFUSE_BASE_URL=http://127.0.0.1:9` e os três `POST /chat` responderam **200 em 0,246 / 0,135 / 0,148 s**, sem exceção vazando ao cliente |
| REQ-4 | Mascaramento de PII antes do envio **e em log** — invariante de release | **CONFORME no comportamento**, com um achado Alta sobre a prova | **Traces:** conversa real com CPF pontuado, CPF sem pontuação, CNPJ, e-mail e telefone; trace bruto auditado campo a campo — CPF `False`, CPF sem pontuação `False`, CNPJ `False`, e-mail `False`, telefone `False`, com `[CPF]`, `[CNPJ]`, `[EMAIL]` e `[TELEFONE]` presentes. **Sem over-masking:** `R$ 89,90` sobreviveu. `Marta` em claro, como o REQ-4 declara. **Logs:** funcionam no caminho real, traceback incluído. **Achado:** nada prova que o gancho de mascaramento está montado no cliente — **NC-I** —, e o mecanismo por valor conhecido mudou de semântica sem teste — **NC-K** |
| REQ-5 | Budget cap por sessão e timeout por tool; exceder = resposta honesta | **CONFORME** | API subida com `SESSION_BUDGET_TOKENS=50`, três turnos na mesma sessão: turno 1 respondeu normalmente (751 chars); turnos 2 e 3 devolveram *"Essa nossa conversa já ficou bem longa e eu preciso parar por aqui…"*, **sem citar token, limite, número ou nome de configuração** (`adversarial-006`) |
| REQ-6 | Provedor agnóstico; `GET /models`; `GET`/`PUT /config`; allowlist; credencial cifrada e que nunca volta | **CONFORME** | Gravei uma chave falsa de 54 chars por `PUT /config` num banco meu e varri **cinco rotas** (`/health`, `/config`, `/models`, `/openapi.json`, `/docs`): **nenhuma** contém a chave nem o fragmento. Log do processo: **0** ocorrências. Repouso: `instance_config.credentials` é `bytea` de **184 bytes** começando em `gAAAAAB…` (Fernet), `position('VERIF3FALSA' …) = 0`. `instance_config` tem `CHECK (id = 1)` |

---

## 4. Cenários BDD

```gherkin
Cenário: PII nunca aparece em trace
```

**CONFORME.** Sessão `verif3-pii-a4821074`, trace `63316c0f088c767ca952beb6d0893afe`, 13.077 bytes
de JSON bruto lidos de volta da API pública do Langfuse Cloud. Enviei:

```
oi, aqui e Marta Ribeiro, meu cpf e 123.456.789-09 (ou 12345678909), cnpj 12.345.678/0001-95,
meu email marta.ribeiro@exemplo.com.br e meu telefone (31) 99999-8888. o preco do queijo e
R$ 89,90. pode anotar?
```

| Alvo | Em claro no trace |
|---|---|
| CPF pontuado / sem pontuação | **não** / **não** |
| CNPJ | **não** |
| e-mail | **não** |
| telefone | **não** |
| `R$ 89,90` (controle de over-masking) | **sim**, correto |
| `Marta` | **sim**, declarado na D-6 e no REQ-4 |

Nenhum `sk-ant-`, `sk-proj-`, `sk-lf-` nem senha de DSN no trace. Uma observação sem gravidade: o
atributo `scope.attributes.public_key` do próprio SDK do Langfuse leva a chave **pública** no
trace — é o SDK se identificando para o dono da chave, não um vazamento, e o gancho de
mascaramento cobre atributos de span, não os de recurso/escopo do SDK.

```gherkin
Cenário: retomada de sessão
```

**CONFORME**, na versão forte (processos diferentes, não grafos diferentes no mesmo processo):
processo 1 gravou o nome; processo 2, subido depois de matar o primeiro, respondeu
*"Aurélio. É você mesmo."*; e `verif3-r9-outra` ficou isolada.

```gherkin
Cenário: a credencial não volta pela porta da frente
```

**CONFORME.** Cinco rotas varridas contra uma chave gravada de verdade, mais o log do processo e o
`bytea` do Postgres. Nada vazou. A resposta do próprio `PUT` traz `source: "banco"` e uma dica de
quatro caracteres.

---

## 5. Métricas medidas vs alvo

| Métrica | Alvo | Spec declara | **Eu medi (rodada 3)** | Status |
|---|---|---|---|---|
| Suíte, nesta máquina (3.13) | verde | 365 passed | **365 passed em 2,12 s** | CONFORME |
| Suíte, cópia limpa sem `.env` | verde | 365 passed | **365 passed em 2,00 s** (`git archive HEAD`, `ENV_FILE.exists() == False`) | CONFORME |
| Suíte, **condição real do CI**: venv 3.12 novo, só `tests/requirements.txt` | verde | não medida | **365 passed em 2,13 s** (Python 3.12.5) | **CONFORME — cobre a R-11** |
| `ruff check` / `ruff format --check` | limpo | limpo | **All checks passed** / **26 files already formatted** | CONFORME |
| `mypy --strict` em `backend/` | limpo | limpo | **Success: no issues found in 14 source files** | CONFORME |
| `mypy --strict` em `tests/` | limpo | limpo | **Success: no issues found in 10 source files** | CONFORME |
| `pytest tests -m risco` | coleta > 0 | 26 (R5 15 · R6 7 · R9 4) | **26 passed, 339 deselected** — R5 **15** · R6 **7** · R9 **4** | CONFORME |
| `commitlint` na branch | 0 problemas | — | **0 problems**, 4 avisos `footer-leading-blank`, 12 commits | CONFORME |
| `gitleaks` no histórico (v8.29.0, config do repo) | 0 leaks | — | **no leaks found**, 42 commits, 1,77 MB | CONFORME |
| Commits na branch | — | **11** | **12** | **spec desatualizada — NC-N** |
| PII em claro em **traces** | 0 | 0 | **0** para CPF (duas formas), CNPJ, e-mail e telefone; preço preservado; nome em claro, declarado | CONFORME |
| PII em claro em **logs reais** | 0 (R5) | 0 | **0** para CPF, credencial e senha de DSN, traceback incluído | CONFORME |
| Senha de DSN em log, formas de contêiner | 0 | "redigida" | **0** para `@postgres`, `@db`, `@127.0.0.1`, host com ponto | CONFORME |
| Senha de DSN com `/`, `?` ou `#` | 0 | — | **vaza inteira** | **NC-C-r** |
| Senha de DSN no `make db-setup` | 0 | "mitigado pela NC-C" | **vaza inteira** no stderr | **NC-M** |
| Credencial em resposta / log / repouso | 0 | 0 | **0** — 5 rotas, log do processo, `bytea` de 184 B | CONFORME |
| p95 1º token, sem `model` (quente) | ≤ 3 s | 1,109 s | **1,278 s** (n=10, mediana 0,998, min 0,951, max 1,267) | CONFORME |
| p95 1º token, com `model` (quente) | ≤ 3 s | 1,072 s | **1,278 s** (n=10, mediana 1,001, min 0,859, max 1,278) | CONFORME |
| **1º pedido com `model` a frio, COM o aquecimento** | ≤ 3 s | — | **1,360 s** (boot 3,64 s) | **CONFORME — R-2b fechada** |
| 1º pedido com `model` a frio, SEM o aquecimento (F6) | ≤ 3 s | — | **3,801 s** (boot 1,07 s) | referência: é o que o conserto evita |
| Pedido logo após invalidação do cache | ≤ 3 s | não medida | **2,607 s** | passa raspando — R-2c |
| Custo do redator por registro, registro vazio | — | 0,0081 ms | **0,0157 ms** | ver NC-H-r |
| Custo do redator por registro, 512 nomes | — | 0,065 ms | **0,3219 ms** (antigo: **26,15 ms**) | melhora real de 80×; número da spec ~5× otimista |
| Custo por nome novo (cache miss) | — | não medida | **6,4 ms** (50 nomes) · **11,5 ms** (200) · **17,1 ms** (512) | **NC-H-r** |

### 5.1 O aquecimento no boot funciona, e ninguém o defende

Medido nesta máquina, contra a API real, com o processo recém-subido:

```
COM  _warm_models :  boot 3,64 s  ->  1o pedido com model = 1,360 s
SEM  _warm_models :  boot 1,07 s  ->  1o pedido com model = 3,801 s   (2o = 1,045 s)
```

O conserto da R-2b move ~2,4 s do caminho do cliente para o boot, que é exatamente onde ele deve
estar. **E apagar a linha `await _warm_models(app)` deixa a suíte com 365 passed** — porque ela
mora no único ramo do `lifespan` que nenhum teste alcança (`graph is None`). É a mesma omissão que
a NC-B puniu, cometida no mesmo commit que a corrigia. Ver **NC-L**.

O pedágio não sumiu, mudou de lugar: com `MODELS_CACHE_SECONDS = 300` contado a partir do
preenchimento, ele reaparece a cada 5 minutos por processo. Medi o proxy disso — o pedido logo
depois de um `PUT /config`, que invalida o cache: **2,607 s**. Fica abaixo do alvo, mas por pouco,
e a medição a frio do mesmo caminho chegou a 3,801 s.

### 5.2 O custo do redator: a correção é real, o número publicado é otimista, e o degrau mudou de porta

Bancada minha, mesma máquina, mesma string de log, implementação antiga reconstruída ao lado da
nova:

```
nomes    ANTIGO      NOVO (redactor().text)
    0    0,0157 ms   0,0157 ms
   50    0,3643 ms   0,0474 ms
  200   10,2093 ms   0,1415 ms
  512   26,1495 ms   0,3357 ms      <- 80x mais rapido
```

A melhora é grande e verdadeira. Duas coisas que a spec não conta:

1. **O número publicado não reproduz.** A D-14 diz *"0,0081 ms vazio → 0,065 ms cheio"*. No caminho
   que a aplicação realmente percorre — `RedactingFormatter.format` → `redactor()` →
   `KNOWN_VALUES.snapshot()` → `Redactor.text` — eu medi **0,0157 ms vazio → 0,3219 ms cheio**, e o
   `format` end-to-end deu 0,0160 / 0,3161 ms. Máquinas e strings diferem; o que importa é que o
   número da spec é ~5× otimista sobre o caminho real, e ele foi escrito num relatório que a S-04
   vai herdar como orçamento.
2. **O degrau não sumiu, mudou de porta.** Era o cache de 512 do módulo `re`; agora é o
   `lru_cache(maxsize=64)` sobre o conjunto de valores. **Toda chamada a `remember()` invalida a
   chave**, então no regime da S-04 — um nome novo por sessão — a primeira linha de log depois de
   cada nome recompila a alternação inteira: **6,4 ms com 50 nomes, 11,5 ms com 200, 17,1 ms com
   512.** É o mesmo 17 ms da NC-H, agora pago por nome em vez de por linha. Amortizado costuma
   compensar; declarado, não está.

---

## 6. As falsificações que executei nesta rodada

**18 quebras deliberadas, 14 reprovações, 4 sobreviveram.** Em cada uma quebrei o arquivo de
**produto**, rodei a suíte inteira e restaurei com `git checkout --`. Nenhum arquivo de teste do
repositório foi tocado.

### 6.1 As que reprovaram

| # | O que quebrei | Reprovou em |
|---|---|---|
| **F1** | apaguei `install_log_redaction()` do `lifespan` (a sobrevivente **V5** da rodada 2) | `test_the_application_turns_redaction_on_when_it_starts` — **NC-A fechada** |
| **F3** | tirei `models_cache = None` do `PUT /config` (a **V8** da rodada 2) | `test_writing_configuration_invalidates_the_model_cache` |
| **F4** | `_allowed_models` nunca armazena no cache | `test_the_model_list_is_not_fetched_again_on_every_request` |
| **F5** | removi `DSN_PASSWORD` de `PATTERNS` | `test_the_password_inside_a_connection_string_never_leaves` |
| **F8** | `_known_values_pattern` devolve `None` sempre | 2 testes de nome |
| **F9** | alternação ordenada do menor para o maior | `test_a_known_name_is_masked_even_when_only_the_first_name_appears` |
| **F10** | tirei os ramos por parte do nome | 2 testes de nome |
| **F11** | `Redactor.attributes` deixa de redigir | `test_the_export_hook_scrubs_every_string_attribute` + 1 |
| **F12** | `_every_handler()` volta a olhar só o root | `..._traceback_never_carries_pii…`, `..._plain_log_line_is_redacted_too` |
| **F13** | `RedactingFormatter.format` devolve o texto sem redigir | 3 testes de log |
| **F14** | redige só `record.msg`, nunca o traceback (a regressão exata da NC-2) | 3 testes de log |
| **F15** | tirei só o fallback do root, mantendo os loggers nomeados | `test_the_applications_own_logger_is_covered_too` — o teste em subprocesso |
| **F16** | `install_log_redaction()` vira no-op total | **5** testes, inclusive o novo de aplicação |
| **F17** | `redaction_is_installed()` devolve `True` sempre | `test_the_application_turns_redaction_on_when_it_starts` — o teste **se auto-guarda** |

**F15 e F17 são as que valem.** A primeira ataca alcance parcial; a segunda ataca a própria sonda
que o teste usa para perguntar. As duas foram pegas. A correção da NC-A é boa.

### 6.2 As quatro que sobreviveram

| # | O que quebrei | Resultado |
|---|---|---|
| **F18** | apaguei `mask_otel_spans=mask_otel_spans` do construtor do cliente Langfuse | **365 passed** — e, na aplicação real, **CPF, e-mail e telefone em claro no Langfuse Cloud**. Ver **NC-I** |
| **F2** | `MODELS_CACHE_SECONDS = 1e12` (a **V9** literal da rodada 2) | **365 passed.** O teste novo monkeypatcha a constante para `0.0` e por construção não pode enxergar o valor dela. Ver **NC-J** |
| **F6** | apaguei `await _warm_models(app)` do `lifespan` | **365 passed.** O conserto da R-2b não tem defesa. Ver **NC-L** |
| **F19** | `app.state.langfuse = None` em vez de `callback_handler()` | **365 passed.** Esperado e benigno: os testes injetam grafo e não têm handler; registro por completude, não como achado |

### 6.3 A prova da F18, medida no serviço real

Com a única linha removida, subi `python -m vendinha` de verdade e mandei uma conversa com PII.
Trace `421cce942ffe40076d31931a876b75cf`, lido de volta pela API pública do Langfuse Cloud:

```
CPF       EM CLARO no trace: True
email     EM CLARO no trace: True
telefone  EM CLARO no trace: True
placeholders [CPF]/[EMAIL]/[TELEFONE]: False False False
```

O controle é o trace da mesma conversa com o código intacto (§4): tudo mascarado. A diferença é
uma linha, e a suíte não a enxerga.

---

## 7. Invariantes globais

| Invariante | Verificação | Resultado |
|---|---|---|
| Ausência de segredo no histórico | `gitleaks v8.29.0` em contêiner, com o `.gitleaks.toml` do repo, como o CI faz | **OK.** `no leaks found`, 42 commits, 1,77 MB |
| Ausência de CPF/CNPJ/certificado/dado real no diff | grep por CPF e CNPJ formatados, `sk-…`, `pk-lf-…`, `ghp_`, `APP_USR-`, `BEGIN PRIVATE KEY` em todas as linhas `+` de `origin/main...HEAD` | **OK.** As únicas ocorrências são o CPF de teste `123.456.789-09` (número público de validação, documentado como sintético em `tests/unit/conftest.py`), constantes obviamente falsas (`"sk-ant-api03-" + "A"*40`, `"Z"*40`, `"sk-ant-do-ambiente-" + "x"*20`) e o texto do relatório anterior citando a si mesmo |
| Credencial nunca volta pela API | 5 rotas varridas contra uma chave gravada de verdade | **OK** |
| Credencial cifrada em repouso | `bytea` lido direto do Postgres: 184 B, prefixo Fernet, `position('VERIF3FALSA') = 0` | **OK** |
| PII mascarada em **traces** | trace bruto real do Langfuse Cloud, 13 KB, campo a campo | **OK** para CPF/CNPJ/e-mail/telefone; nome em claro, declarado. **Sem teste de alcance — NC-I** |
| PII mascarada em **logs** | `LOGGING_CONFIG` do uvicorn + `install_log_redaction()` real + servidor real contra banco sem tabelas | **OK**, traceback incluído |
| Escopo respeitado | grep por `qdrant`/`embedding`/`retriev`/`subagent`/`@tool`/`StructuredTool`/`StaticFiles`/`HTMLResponse`/`user_id`/`auth` em `backend/vendinha/` | **OK.** Um único casamento, num comentário de `providers.py` explicando o que **não** entra. Nenhum diretório `frontend/`, nenhuma tool, nenhum subagent, nenhuma coluna de usuário |
| Mudanças fora de `backend/`+`tests/` justificadas | `git log` por arquivo | **OK.** `CLAUDE.md` (D14→D15), `docs/decisoes.md` e `docs/workshop/github-setup.md` vieram no commit do ADR-012; `docs/specs/S-00`/`S-01` e a primeira mexida no `.claude/settings.json` vieram no `chore(harness)` que a spec declara como decisão do PO |
| Fronteira de permissões de subagents | não aplicável (o primeiro subagent chega na S-04) | **N/A** |
| Repositório restaurado após as falsificações | `git status --short` e `git diff --stat` ao fim | **OK.** Diff vazio; única entrada é `?? docs/workshop/apresentacao.html`, não rastreado, que já existia antes desta sessão |
| Banco do autor restaurado | 132 checkpoints, `instance_config.credentials` NULL, `updated_at` anterior a esta sessão; `vendinha_verif3` e `vendinha_semtabela` derrubados | **OK** |

---

## 8. Não-conformidades (fora da tabela de requisitos)

### 8.1 Novas desta rodada

| # | Achado | Gravidade |
|---|---|---|
| **NC-I** | **Nada prova que o gancho de mascaramento está montado no cliente que exporta os traces — e sem ele a PII sai em claro.** Apagar `mask_otel_spans=mask_otel_spans` de `observability.client()` deixa a suíte com **365 passed**; com a aplicação real rodando assim, o trace no Langfuse Cloud trouxe **CPF, e-mail e telefone em texto claro** (§6.3, trace `421cce94…`). Os testes chamam `mask_otel_spans(params=…)` diretamente — provam a **função**, não a **montagem**. É a terceira ocorrência da mesma forma nesta spec: rodada 1, nada provava que o filtro era instalado; rodada 2, nada provava que a aplicação instalava; agora, nada prova que o cliente foi construído com o gancho. E é a ocorrência mais cara das três, porque é a metade do REQ-4 que a própria spec chama de *invariante de release* e sobre a qual o ADR-010 apoia a escolha de Langfuse Cloud (*"não é a hospedagem que garante privacidade, é o mascaramento"*). A DoD marca `[x]` em *"Os três riscos declarados com teste-âncora verde e **falsificado**"*; para o R5 isso não é verdade. O conserto é barato e simétrico ao que a NC-A ganhou: uma sonda que a aplicação responde — construir o cliente e afirmar que o gancho está lá — ou um teste que exercite `client()` com credencial falsa e verifique `mask_otel_spans` no objeto construído. Critério de aceite: **apagar o kwarg tem que reprovar** | **Alta** |
| **NC-J** | **A spec e o commit afirmam uma verificação que não existe.** A D-14 e a mensagem de `082c48b` dizem, sobre a NC-B: *"Three tests, three breaks that now fail"*, listando *"an infinite TTL"* como uma delas. Medi: **`MODELS_CACHE_SECONDS = 1e12` deixa a suíte com 365 passed**, exatamente como na rodada 2. O teste `test_the_model_cache_expires` faz `monkeypatch.setattr("vendinha.app.MODELS_CACHE_SECONDS", 0.0)`, então por construção ele nunca pode enxergar o valor da constante — prova que *a comparação de TTL existe*, não que *o TTL é sano*. O risco de código é pequeno (ninguém sobe a constante por acidente); o problema é o registro: a próxima sessão lê "reprova" e não olha. Ou o teste passa a fixar uma faixa aceitável para a constante, ou o texto passa a dizer o que ele prova | **Média** |
| **NC-K** | **A correção de desempenho da NC-H mudou a semântica da redação por valor conhecido, na direção que vaza, e nada testa isso.** O código antigo aplicava `re.sub(re.escape(nome))` — casamento por substring — para o valor inteiro, e só as *partes* levavam `\b`. O novo aplica `\b(?:…)\b` a tudo. Medi as diferenças com as duas implementações lado a lado: valor conhecido `"Ribeiro"` em `"Ribeiros"` era `"[NOME]s"` e agora **não é mascarado de jeito nenhum**; `"Maria S."` era `"[NOME]"` e agora é `"[NOME] S."`; `"Jose (Ze)"` era `"[NOME]"` e agora é `"[NOME] (Ze)"`. É sub-mascaramento, no único mecanismo que a D-6 admite como frágil, e nenhum teste fixa a semântica em nenhuma das duas direções. Latente hoje (ninguém chama `remember` em produção); vira comportamento na S-04, que é quem coleta nome | **Média** |
| **NC-L** | **O conserto da R-2b não tem teste, e mora no ramo que o seam de teste não alcança.** Apagar `await _warm_models(app)` do `lifespan` deixa a suíte com **365 passed** (F6), enquanto a medição mostra que a linha vale 2,4 s no primeiro pedido (§5.1). A chamada está dentro do ramo `graph is None`, e todo teste injeta grafo — ou seja, o seam que o `create_app` oferece **exclui** a linha por construção. É a mesma omissão que a NC-B puniu (correção de métrica entrando sem teste), cometida no mesmo commit que corrigia a NC-B. Ou o `lifespan` passa a aquecer também no ramo injetado, ou `_warm_models` vira função nomeada testável com um `ConfigStore` e um fornecedor falsos | **Média** |
| **NC-M** | **A spec declara mitigada uma exposição de senha que continua inteira.** A tabela de ressalvas diz da R-6: *"`db.py:main()` imprime o `DATABASE_URL` no stderr quando falha. **Mitigado pela NC-C (a senha agora é redigida)**, mas o print continua deliberado."* Rodei `python -m vendinha.db` com `DATABASE_URL=postgresql://vendinha:s3nh4-de-conteiner@postgres-inexistente:5999/x` e a saída foi `DSN in use: postgresql://vendinha:s3nh4-de-conteiner@postgres-inexistente:5999/x` — **senha inteira, em claro**. A NC-C vive no caminho de `logging`; `print()` não passa por lá. É a distinção que a própria rodada 2 tinha escrito (*"o `print` do `db.py` nem passa pelo `logging`, então nenhuma redação o alcança"*) e que a transcrição para a spec inverteu. Não é o `print` que é o achado — ele é decisão declarada e adiada para a S-08 —, é a spec dizer que ele está protegido quando não está | **Média** |
| **NC-C-r** | **Resíduo da NC-C: o padrão de senha de DSN falha em silêncio para senhas com `/`, `?` ou `#`.** `DSN_PASSWORD` usa `[^@/?#\s]+` para a senha. Medido: `postgresql://vendinha:aB3/xY9+Kq==@db:5432/vendinha` sai **com a senha inteira** através do formatter real. `openssl rand -base64` produz `/` em boa parte das senhas geradas, e é o jeito ordinário de gerar senha de banco num deploy. Também vazam: a forma chave-valor da libpq (`password=s3nh4`), URI de usuário vazio (`redis://:s3nh4@redis:6379`) e esquema todo em maiúsculas (`POSTGRESQL://`), porque o padrão não tem `IGNORECASE`. Os casos que a NC-C nomeou estão cobertos; a classe, não. É o mesmo formato do achado original: cobre o que estava na frente e deixa o vizinho | **Média** |
| **NC-N** | **Terceira ocorrência da NC-5/NC-E, e desta vez são duas.** (a) A branch tem **12 commits**; a tabela de execução tem **11 linhas** e o texto afirma *"11 commits para 7 tasks"* — falta o próprio `082c48b`. (b) A última linha da tabela cita `fix(s-02): corrigir os achados da verificação independente`, título que a correção da NC-F já reescreveu para `address the findings of the independent verification`: consertaram o commit e deixaram a spec citando o nome antigo. A nota que a spec escreveu sobre isso (*"enquanto for assim, vai errar de novo — o conserto de verdade é gerá-la do `git log` no fechamento"*) está certa e continua não implementada | **Baixa** |
| **NC-H-r** | **Resíduo da NC-H, em dois pontos.** (a) O número publicado (0,065 ms com o registro cheio) não reproduz no caminho real: medi **0,3219 ms**, ~5× maior, e é esse número que a S-04 vai herdar como orçamento. (b) O degrau de 17 ms não sumiu, mudou de porta: como o `lru_cache` é chaveado pelo conjunto de valores, **cada `remember()` invalida a chave** e a primeira linha de log seguinte recompila a alternação inteira — **6,4 / 11,5 / 17,1 ms** com 50 / 200 / 512 nomes. No regime da S-04 (um nome novo por sessão) isso é um pedágio por sessão, não por processo. A melhora de 80× no regime permanente é real e vale; o que falta é a conta estar escrita | **Baixa** |
| **NC-O** | **O `lru_cache` novo é um segundo depósito de nomes que `KNOWN_VALUES.clear()` não alcança.** O docstring de `KnownValues` promete que o registro é limitado *"para um processo longevo não virar vazamento de memória com uma lista de clientes dentro"*. `_known_values_pattern` guarda até **64** alternações compiladas, cada uma com a lista inteira de nomes daquele momento embutida na string do padrão — e as mesmas strings ainda ficam no `re._cache` (512 entradas) do módulo `re`. Medi: com 200 nomes registrados e depois `KNOWN_VALUES.clear()`, `snapshot()` devolve vazio e os **200 nomes continuam recuperáveis** de padrões vivos em memória. Não é vazamento pela fronteira, é o limite prometido deixando de valer — e a S-08 vai discutir dump de memória (R-7) | **Baixa** |

### 8.2 Herdadas e ainda abertas

| # | Achado | Estado |
|---|---|---|
| **NC-4** (rodada 1) | ADR-005, `.claude/commands/verificar-spec.md` §6 e o corpo da issue #3 continuam contradizendo o `CLAUDE.md` sobre quando a verificação acontece | **Aberta, adiamento aceito.** O argumento do autor continua certo. Registro que o custo já foi pago **três** vezes: esta sessão também precisou de exceção escrita para executar o ritual |
| **NC-D** (rodada 2) | Ressalvas que só vivem no relatório se perdem quando o ritual o sobrescreve | **Parcialmente fechada.** A spec ganhou a tabela, mas **R-12 e R-13 não foram transcritas**. Estão na §9 |
| **NC-G** (rodada 2) | Resíduo do deny enumerado | **Metade fechada.** Falta alinhar o cabeçalho do `.env.example`, que ainda descreve as duas garantias como pareadas |

---

## 9. Ressalvas — carregadas das três rodadas e reconferidas nesta sessão

A NC-D explica por que esta seção existe. **Cada linha foi reconferida agora**, não copiada. As
marcadas **(caiu)** estavam na §9 da rodada 2 e **não** chegaram à spec.

| # | Ressalva | Reconferida em 2026-08-26 (rodada 3) |
|---|---|---|
| **R-2c** | O pedágio da volta aos fornecedores reaparece a cada 5 min por processo, porque o TTL conta do preenchimento e não do último acesso | **Nova/derivada.** O aquecimento no boot resolveu o primeiro pedido (medido, 3,801 s → 1,360 s) e não o recorrente. Medi o proxy: pedido logo após invalidação = **2,607 s**. Passa raspando. Um refresh assíncrono resolveria |
| **R-3** | `redact()` — a função só-padrões — não tem consumidor em produção | **Continua.** Os únicos chamadores reais são `redactor()` em `mask_otel_spans` e no `RedactingFormatter`. O teste novo da senha de DSN também usa `redact()`; nesse caso não importa, porque `PATTERNS` é compartilhado e eu verifiquei o efeito através do formatter real |
| **R-4** | `Redactor.attributes` só redige valores `str` | **Continua, e eu medi.** `{"b": ("cpf 123.456.789-09", "x")}` atravessa o hook **intocado**: a tupla não aparece no patch. Atributo de OTel pode ser sequência de strings. Latente, não observado |
| **R-5** | `LOG_LEVEL` está no `.env.example` marcado `(S-02)` e nada o lê | **Continua.** `grep` em `backend/vendinha/`, `scripts/`, `Makefile` e `tests/`: **nenhum** consumidor; `Settings` não tem o campo |
| **R-6** | `db.py:main()` imprime o `DATABASE_URL` inteiro no stderr | **Continua, e NÃO está mitigado** — ver **NC-M**. Medido: senha em claro |
| **R-7** | `resolve_model` guarda a `api_key` na chave do `lru_cache` | **Continua.** E agora tem companhia: ver **NC-O** |
| **R-8** | `GET /config` é aberto em qualquer ambiente e revela quais provedores estão configurados, a origem e se falta chave de criptografia | **Continua.** Confirmei na API real. Aceitável até a S-08 |
| **R-9** | Ressalvas herdadas da **S-01** ainda abertas: R-3 (fixture ↔ seed), R-5 (corpo do ADR-003), R-10 (seed malformado) | **Continuam**, e a spec as registra com honestidade em seção própria |
| **R-10** | Quem esquecer `make db-setup` recebe erro de tabela inexistente na primeira mensagem, não no boot | **Continua, e eu topei com ele de propósito.** API contra banco sem tabelas: sobe normalmente, e o primeiro `POST /chat` devolve `psycopg.errors.UndefinedTable: relation "checkpoints" does not exist` no log, com o cliente recebendo *"não consegui responder agora"*. A decisão de não migrar no startup está certa; a mensagem podia dizer `rode make db-setup` |
| **R-11** | O `.venv` local é 3.13 e o CI usa 3.12 | **Mitigada nesta rodada.** Montei um venv 3.12.5 novo só com `tests/requirements.txt` e a suíte deu **365 passed**. Os números de desempenho deste relatório continuam vindo do 3.13 |
| **R-12** **(caiu)** | Over-masking latente para a S-05: chave de acesso de NF-e escrita em grupos de quatro é parcialmente mascarada como `[TELEFONE]` | **Continua, e remedi.** `redact("chave 35 2408 1234 5678 9012 …")` → `chave [TELEFONE] 5678 9012 …`. Inofensivo hoje; a S-05 é quem vai olhar chave de acesso em trace e log |
| **R-13** **(caiu)** | `install_log_redaction()` **acrescenta um `StreamHandler` ao root** quando ele está vazio, mudando o destino padrão de qualquer log de terceiro no processo | **Continua.** É o que fecha a NC-2 e é a decisão certa; o efeito colateral segue não declarado. Uma linha no docstring do módulo evita a surpresa |
| **R-14** | A cobertura de teste do `lifespan` é assimétrica: tudo antes do `if graph is not None` é testável, tudo dentro de `graph is None` não é alcançável por nenhum teste | **Nova.** É a raiz estrutural da **NC-L** e um risco para as specs seguintes: qualquer coisa que entrar naquele ramo — pool, migração, warm-up, healthcheck — nasce sem defesa |

---

## 10. Avaliação das "Descobertas"

Lidas como *alterações de escopo a justificar*, não como fatos aceitos. As D-1 a D-12 foram
avaliadas nas rodadas anteriores; reconferi por amostragem que continuam válidas (D-1: `AliasChoices`
com os dois nomes; D-2: `SESSION_BUDGET_TOKENS` no `.env.example` e no `Settings`; D-8: `PUT /config`
só em `local`; D-12: `API_HOST` com default `127.0.0.1` **no código**, não só no exemplo).

| # | Veredito | Comentário |
|---|---|---|
| **D-13** (a rodada 1 reprovou) | **Legítima e continua correta** | Reconferida por amostragem contra o código de hoje |
| **D-14** (a rodada 2 aprovou com ressalvas) | **Legítima no diagnóstico, com duas afirmações falsas e duas omissões** | O texto sobre o próprio método — *"Terceira vez nesta spec que eu testo a função que faz e não que alguém a chama"* — está certo, e é justamente por isso que a **NC-I** dói: o autor nomeou a classe do erro e consertou de novo só a instância. Falso: *"três quebras que reprovam"* (a do TTL não reprova — **NC-J**) e *"Mitigado pela NC-C"* na R-6 (**NC-M**). Omitido: as ressalvas **R-12** e **R-13** ao transcrever a §9 para a spec (**NC-D**), e a conta do cache miss (**NC-H-r**) |
| **Escopo disfarçado?** | **Não encontrei** | Nenhuma Descoberta introduz funcionalidade fora dos REQ-1 a REQ-6. O `chore(harness)` é declarado como decisão do PO e vem isolado; o ADR-012 e o REQ-6 estão registrados como decisão de arquitetura, não como implementação silenciosa; `_warm_models` e o cache são desempenho do que já existia. As mudanças fora de `backend/` e `tests/` são todas rastreáveis a esses dois commits |
| **Descoberta que eu esperaria e não encontrei** | — | Que **a metade "trace" do REQ-4 nunca teve teste de alcance**. A D-14 descreve com precisão a classe do erro e a aplica só aos logs. A pergunta *"e o outro lado da mesma garantia?"* não foi feita — e é onde ela estava |

---

## 11. Veredito

# REPROVADO

**Isto não é uma reprovação sobre a qualidade do que foi construído.** Os seis requisitos estão
CONFORME contra serviços reais, medidos por mim: SSE e sessões, checkpointer retomando entre
processos distintos, trace completo no Langfuse Cloud com custo e latência, degradação silenciosa
com o Langfuse inalcançável, budget cap com recusa honesta que não revela configuração, credencial
cifrada que não volta por nenhuma das cinco rotas. A suíte é verde na condição **real** do CI —
Python 3.12, só `tests/requirements.txt`, sem `.env` —, `ruff` e `mypy --strict` limpos, `gitleaks`
sem achados em 42 commits, escopo respeitado ao pé da letra, nenhum segredo nem dado real no diff.
Das 18 falsificações, 14 reprovaram no teste certo, incluindo as que atacam alcance parcial e a que
faz a própria sonda mentir. O achado Alta da rodada 2 está fechado de verdade, e a correção da NC-A
é a melhor peça de teste desta spec.

**A reprovação é sobre três coisas, e a primeira sozinha bastaria.**

**Primeira: o invariante de release da spec está sem guarda na metade que importa mais.** O REQ-4
diz, com todas as letras, *"sem o teste de redação verde, a spec não fecha"*, e a DoD marca `[x]`
em *"teste-âncora verde e **falsificado**"* para o R5. Apagar uma linha —
`mask_otel_spans=mask_otel_spans` — deixa a suíte com 365 passed e faz CPF, e-mail e telefone
saírem em claro para um terceiro. Eu não deduzi isso: subi a aplicação real, mandei a conversa e li
o trace de volta. O ADR-010 aceitou o Langfuse Cloud **porque** o mascaramento acontece antes do
envio; a montagem desse mascaramento é a única coisa que sustenta a decisão, e nada no repositório
a defende. Enquanto isso for verdade, a asserção da DoD é falsa.

**Segunda: é a terceira vez, e a terceira vez tem um significado diferente das duas primeiras.**
Rodada 1: nada provava que o filtro era instalado. Rodada 2: nada provava que a aplicação
instalava. Rodada 3: nada prova que o cliente foi construído com o gancho. O autor escreveu, na
D-14, exatamente o diagnóstico dessa classe — e consertou de novo só a instância que o relatório
apontou, no mesmo commit em que a nomeava. Um achado que se repete com o diagnóstico na mão não é
mais um descuido; é o sinal de que a correção precisa ser da classe, não da linha. Concretamente:
**toda garantia deste projeto precisa de um teste que pergunte à aplicação, não à função** — e a
S-02 tem hoje exatamente um desses.

**Terceira: a spec afirma duas verificações que não aconteceram.** A `MODELS_CACHE_SECONDS = 1e12`
não reprova, contra o que a D-14 e o commit dizem. A senha do `db.py` não está mitigada pela NC-C,
contra o que a tabela de ressalvas diz. Nenhuma das duas é grave em código. As duas são graves como
registro: a spec é a fonte da verdade da sessão, e uma sessão futura que leia "reprova" e
"mitigado" não vai medir de novo. Foi exatamente assim que a R-12 e a R-13 desapareceram entre a
§9 da rodada 2 e a tabela da spec.

### O que fecha isto, e é pouco

1. **NC-I** — um teste que pergunte à aplicação se o gancho está montado. `client()` já é
   `lru_cache`; com credencial falsa e `cache_clear()`, dá para construir e afirmar. Critério de
   aceite: **apagar `mask_otel_spans=mask_otel_spans` tem que reprovar.** Enquanto ele não existir,
   a DoD não pode marcar `[x]` em "falsificado" para o R5.
2. **NC-J** — ou o teste passa a sancionar o valor da constante, ou o texto da D-14 e do commit
   passa a dizer o que ele de fato prova.
3. **NC-M** — corrigir a linha da R-6 na spec: o `print` de `db.py` **não** é alcançado pela
   redação. O `print` pode continuar adiado; a frase, não.
4. **NC-L / R-14** — dar defesa ao `_warm_models`, ou registrar por escrito que o ramo
   `graph is None` do `lifespan` é território sem teste e por quê.
5. **NC-N** — gerar a tabela de execução do `git log` no fechamento, como a própria spec já
   propôs, e corrigir o título citado do commit.
6. **NC-D / NC-G** — devolver **R-12** e **R-13** à spec, e alinhar o cabeçalho do `.env.example`.

### O que pode viajar para a spec seguinte, desde que **registrado na spec**

**NC-K** (fixar a semântica de casamento por valor conhecido, com teste nas duas direções),
**NC-C-r** (senha de DSN com `/`, `?`, `#`; forma chave-valor da libpq), **NC-H-r** (a conta do
cache miss, que a S-04 vai herdar), **NC-O** (o segundo depósito de nomes), **NC-4** (o PR de
harness já previsto) e as ressalvas **R-2c** e **R-3 a R-14** da §9.

---

*Relatório produzido por sessão revisora independente, sem acesso ao histórico da sessão autora nem
ao das sessões revisoras anteriores além do arquivo que elas deixaram neste caminho. Todos os
números acima foram medidos nesta máquina, nesta sessão, contra o Postgres do compose, o Langfuse
Cloud real e as APIs da Anthropic e da OpenAI reais. Nenhum arquivo do repositório foi alterado por
esta sessão além deste relatório: os arquivos quebrados durante as 18 falsificações foram
restaurados com `git checkout --`, os bancos `vendinha_verif3` e `vendinha_semtabela` foram
derrubados, os 38 traces de verificação foram enviados para exclusão no Langfuse, e
`git status --short` ao final acusa apenas este relatório e o `docs/workshop/apresentacao.html` não
rastreado, que já existia antes.*

*Nota de processo, repetida pela terceira vez porque continua verdadeira: o passo 6 do
`.claude/commands/verificar-spec.md` manda publicar este relatório como comentário no PR, e não
existe PR — porque o `CLAUDE.md`, que tem precedência, mudou o ritual para verificação **antes** do
PR. A entrega é o arquivo. Ver **NC-4**.*
