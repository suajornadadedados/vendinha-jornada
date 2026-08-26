# Relatório de verificação independente — S-02 (Agente base observável)

> **Segunda rodada.** A primeira reprovou a entrega (2 achados de gravidade Alta). O autor
> corrigiu e a spec registra as correções na **D-13**. Este relatório **substitui** o anterior no
> mesmo caminho e carrega a rastreabilidade das duas rodadas: o que era da rodada 1, o que foi
> de fato corrigido (medido, não aceito), o que continua aberto e o que apareceu de novo.
> Nada aqui foi herdado do texto anterior sem ser remedido nesta sessão.

| | |
|---|---|
| **Spec** | `docs/specs/S-02-agente-observavel.md` (`status: em-revisao`) |
| **Branch** | `spec/s-02-agente-observavel` @ `06d2fd8` (11 commits) |
| **Base** | `origin/main` @ `cb51953` |
| **PR** | **não existe.** Correto sob o `CLAUDE.md` item 4 (*"Verificação independente ANTES do PR… Sem veredito, não existe PR"*). O passo 6 do `.claude/commands/verificar-spec.md` manda comentar no PR; o `CLAUDE.md` tem precedência e a entrega é o arquivo. Ver **NC-4**, que continua aberta |
| **Issue** | [#3](https://github.com/suajornadadedados/vendinha-jornada/issues/3) — **OPEN**, corpo é ponteiro; campo `ADRs` atualizado pelo autor (`updated_at` 2026-08-26T18:47Z) |
| **Diff** | 11 commits · 41 arquivos · +6.178 / −233 |
| **Rodada 1** | REPROVADO · 2 Alta · 34 falsificações, 3 sobreviveram |
| **Rodada 2 (esta)** | 13 falsificações, **3 sobreviveram** · 1 Alta (sobre o teste) · 3 Média · 4 Baixa |
| **Sessão** | revisora, independente, sem acesso ao histórico da sessão autora nem ao da sessão revisora anterior além do arquivo que ela deixou |
| **Data** | 2026-08-26 |
| **Ambiente** | Windows 11 · Docker 27.x · `backend/.venv` = **Python 3.13.2** (o CI usa 3.12; registro porque a diferença é minha) · `make` **não existe** nesta máquina, rodei a linha de dentro de cada alvo |
| **Infra** | `docker compose` no ar: `vendinha-postgres-1` healthy em `127.0.0.1:5433`, `vendinha-qdrant-1` em 6333/6334. A 5432 do host está ocupada por um Postgres nativo |
| **Veredito** | **APROVADO COM RESSALVAS** |

> **Nota de método sobre o `.env`.** A leitura do `.env` é negada ao agente por regra em
> `.claude/settings.json` e eu não a burlei: em nenhum momento li o arquivo e nenhum valor de
> credencial aparece neste relatório. Onde precisei de configuração passei variáveis pelo meu
> próprio shell (`DATABASE_URL`, `CONFIG_ENCRYPTION_KEY` gerada por mim, `API_PORT`, `API_HOST`,
> `APP_ENV`, `SESSION_BUDGET_TOKENS`, `LANGFUSE_BASE_URL`). Onde a medição exigia a credencial
> real — subir a API e consultar o trace de volta no Langfuse Cloud — usei
> `vendinha.config.get_settings()` de dentro de um script e imprimi **só o resultado**. Chamadas
> reais à Anthropic, à OpenAI e ao Langfuse Cloud, com custo real e pequeno.

> **Nota sobre o banco.** Não deixei rastro no banco de trabalho do autor. Criei
> `vendinha_verif2` e `vendinha_semtabela` para os testes de credencial e de falha, e **derrubei
> os dois** ao final. As sessões de chat que rodei contra o banco `vendinha` foram removidas:
> **27 threads · 62 checkpoints · 62 blobs · 90 writes**, identificadas por `checkpoint->>'ts'`
> posterior ao início desta sessão. A `instance_config` do banco do autor não foi tocada
> (`updated_at` continua anterior a esta sessão, `credentials` NULL). Sobraram 132 checkpoints,
> que são os do autor.

---

## 1. Resumo

**Os dois achados de gravidade Alta que reprovaram a rodada 1 estão corrigidos, e eu medi os
dois.** Não aceitei a afirmação do autor em nenhum: reproduzi a condição de falha original,
verifiquei a correção e depois tentei quebrá-la.

**NC-1 (suíte vermelha fora da máquina do autor) — fechada.** `git archive HEAD` para um
diretório sem `.env`, com `CONFIG_ENCRYPTION_KEY` fora do ambiente: **360 passed**. Confirmei que
o `ENV_FILE` resolvido pelo `Settings` é o da cópia e que ele **não existe** — sem isso a medição
não valeria nada. E confirmei que é a fixture nova que fecha o buraco: desativando o `autouse` do
`encryption_key` na cópia limpa, voltam **exatamente os 4 testes** que a rodada 1 nomeou. O
caminho "sem chave → 503" continua coberto por
`test_the_config_response_says_whether_encryption_is_ready`, que sobrescreve a fixture de
propósito — a correção não comprou verde tirando cobertura.

**NC-2 (a metade "logs" do R5 era inerte) — fechada na aplicação que roda.** Verifiquei no
caminho de produção, não no teste: `dictConfig(uvicorn.config.LOGGING_CONFIG)`, depois o
`lifespan` real de `create_app()`. Antes do lifespan, `root handlers: []`; depois,
`[<StreamHandler <stderr>>]` embrulhado. Um `logger.exception` com chave de provedor falsa e CPF
de teste sai assim:

```
RuntimeError: auth falhou com [CREDENCIAL] para o cpf [CPF] em postgresql://vendinha:[EMAIL]:5433/vendinha
cliente informou [CPF] e email [EMAIL]
```

O traceback — o caso que a rodada 1 mostrou passando inteiro — é renderizado e redigido. Subi
também o servidor de verdade (`python -m vendinha`) contra um banco sem tabelas para provocar o
`logger.exception` do endpoint: o traceback aparece formatado no log do processo e o cliente
recebe só `"não consegui responder agora"`. Quatro falsificações no módulo, **quatro
reprovações**, mais uma quinta que reintroduz a regressão exata da NC-2 e também reprova.

**O que impede o APROVADO limpo é uma coisa só, e ela tem a forma exata que a instrução desta
rodada mandava procurar.** Apagar a chamada `install_log_redaction()` do `lifespan` do `app.py`
deixa a suíte **verde: 360 passed**. O teste novo
(`test_installing_log_redaction_actually_installs_something`) responde *"a função instala alguma
coisa?"* — não *"a aplicação instala?"*. É o **F14 da rodada 1 movido um nível acima**: antes
nada provava que a função cobria os handlers; agora nada prova que alguém a chama. O autor
entregou literalmente o que a condição de aceite pedia — e a pergunta de alcance continua sem
resposta. Ver **NC-A**.

Além disso: a correção da ressalva **R-2** (cache da lista de modelos) entrou **sem nenhum
teste** — remover a invalidação no `PUT /config` deixa a suíte verde, e tornar o TTL infinito
também. E a redação de traceback **não cobre a senha do DSN**, que o próprio docstring do
`RedactingFormatter` nomeia como alvo: ela só some hoje porque o host `127.0.0.1` casa por
acidente com o regex de e-mail. Com `@postgres:5432` — a forma que a S-08 vai usar — a senha sai
em claro.

Fora isso, a entrega continua sólida sob medição adversarial: **10 de 13 falsificações reprovaram
no teste certo**, os seis requisitos estão conformes contra serviços reais, o escopo foi
respeitado ao pé da letra, `gitleaks` limpo em 41 commits e nenhum CPF, CNPJ, certificado ou
credencial real no diff.

**6 CONFORME · 0 NÃO CONFORME · 0 NÃO VERIFICÁVEL** (requisitos), com 1 achado Alta, 3 Média e 4
Baixa fora da tabela de requisitos.

---

## 2. Achados da rodada 1, um a um

Cada linha foi remedida nesta sessão. "Fechada" significa que **eu** reproduzi o defeito original
e depois provei que ele não existe mais.

| # | Rodada 1 | Estado agora | Como eu medi |
|---|---|---|---|
| **NC-1** (Alta) | Suíte `4 failed` em cópia limpa sem `.env` — condição do job `test`, check obrigatório | **FECHADA** | `git archive HEAD` → diretório sem `.env`, `CONFIG_ENCRYPTION_KEY` fora do shell: **360 passed em 1,76 s**. Confirmei que `vendinha.config.ENV_FILE` aponta para a cópia e `exists() == False`. Falsificação **V10**: desativando o `autouse` da fixture nova, voltam os **mesmos 4 testes** nomeados na rodada 1 |
| **NC-2** (Alta) | `install_log_redaction()` inerte sob uvicorn (root sem handler) e filtro sem alcance ao traceback | **FECHADA na aplicação** | Caminho de produção reproduzido (`LOGGING_CONFIG` + lifespan real): root ganha handler embrulhado, traceback sai com `[CREDENCIAL]` e `[CPF]`. Servidor real contra banco sem tabelas: `logger.exception` formatado, cliente sem vazamento. Falsificações **V1–V4** e **V11**: 5 quebras, 5 reprovações. **Mas ver NC-A** — o alcance da *chamada* continua sem teste |
| **NC-3** (Média) | REQ-4 dizia "nome" e ficava `[x]` com nome saindo em claro | **FECHADA** | REQ-4 emendado inline, no mesmo padrão do REQ-3, nomeando as duas garantias (padrão / valor conhecido) e dizendo que a S-04 é quem alimenta o registro. Auditei o trace bruto: `Marta Ribeiro` continua em claro — e agora o texto do requisito diz isso |
| **NC-4** (Média) | ADR-005, `.claude/commands/verificar-spec.md` e a issue #3 contradizem o `CLAUDE.md` sobre quando a verificação acontece | **ABERTA — adiada com motivo registrado** | Reconferi os três: `ADR-005` §Decisão continua *"relatório… anexado antes do **merge**"*, sem nota de cabeçalho; `verificar-spec.md` passo 6 continua *"Publicar o relatório como comentário no PR"*; o corpo da issue #3 continua com *"3. PR com evidência… 4. `/verificar-spec` → relatório anexado ao PR"*. **Esta sessão precisou da mesma exceção escrita ao ritual que a anterior.** O argumento do autor (governança vai em PR de harness próprio, não dentro do PR de uma spec) é o certo e é o mesmo que a R-9 da S-01 cobra — aceito o adiamento, registro que o custo já foi pago duas vezes |
| **NC-5** (Baixa) | Tabela de execução com 9 commits, branch com 10 | **FECHADA** | `git rev-list --count origin/main..HEAD` = **11**; a tabela tem **11 linhas** e o texto diz "11 commits para 7 tasks". Bate hoje. A própria spec anota que vai errar de novo enquanto a tabela for escrita antes do último commit existir — e ela tem razão: ver **NC-E** |
| **NC-6** (Média) | `dca2419` tirou o deny de `.env.*`, liberando `.env.local`/`.env.prod` enquanto o `.gitignore` os trata como segredo | **PARCIALMENTE FECHADA** | O deny agora enumera oito nomes (`.env`, `.env.local`, `.env.*.local`, `.env.dev`, `.env.development`, `.env.prod`, `.env.production`, `.env.test`). O `.gitignore` continua ignorando **`.env.*`** com `!.env.example`. Ver **NC-G**: a receita literal da rodada 1 (negar `.env.*` + permitir `.env.example`) **não é implementável** — no Claude Code o `deny` vence o `allow` —, então a enumeração é resposta defensável; o que sobra é o resíduo, e ele não está escrito em lugar nenhum |
| **NC-7** (Baixa) | "treze testes-âncora" onde eram 21; issue #3 com `ADRs: ADR-007` | **METADE FECHADA, METADE REGREDIU** | Issue #3: campo `ADRs` agora é `ADR-001, ADR-007, ADR-010, ADR-012`, igual ao frontmatter — **fechada**. Marker: medi `pytest tests -m "risco"` → **24 passed**, 336 deselected (R5: **13** · R6: 7 · R9: 4). A spec diz **21 (R5: 10)**. O número ficou desatualizado **pelo próprio commit de correção**, que acrescentou 3 testes de R5. Ver **NC-E** |
| **R-1** (ressalva) | Inverter "banco vence ambiente" não quebrava nenhum teste | **FECHADA** | `effective_credentials()` é função pura em `providers.py` e o `app.py` a usa em `_credentials`. Falsificação **V6** (inverter os dois lados) → reprova `test_the_stored_key_is_the_one_the_model_actually_gets`. Falsificação **V7** (`_credentials` passa a ignorar o banco) → reprova 2 testes. O portão que eu atravessei na rodada 1 está fechado |
| **R-2** (ressalva) | p95 do 1º token **com** `model` era 3,331 s, acima do alvo | **FECHADA no regime quente; custo frio novo, não declarado** | Medi n=10 em cada caminho contra a API real: **com `model` p95 = 0,992 s** (mediana 0,873), **sem `model` p95 = 0,992 s** (mediana 0,902). Alvo ≤ 3 s: cumprido. **Mas o primeiro pedido depois do boot com `model` levou 4,043 s**, contra 1,197 s sem `model` no mesmo estado frio — a volta aos fornecedores ainda custa ~2,85 s, agora paga uma vez a cada 300 s por processo em vez de a cada requisição. O número publicado na spec (1,072 s) é de cache quente e não diz isso. Ver **NC-B** e **R-2b** |
| **R-3 … R-11** (rodada 1) | Nove ressalvas que o relatório mandou tratar nas specs seguintes *"desde que registradas"* | **NÃO REGISTRADAS** | A seção "Ressalvas herdadas" da spec só cobre as da **S-01**. Nenhuma das nove da S-02 aparece na spec. E elas viviam só no arquivo que este relatório sobrescreve. Ver **NC-D** — e a §9, onde eu as remedi uma a uma e as carrego adiante |

---

## 3. Conformidade requisito a requisito

| # | Requisito | Status | Evidência que EU produzi nesta rodada |
|---|---|---|---|
| REQ-1 | FastAPI com `POST /chat` (SSE) e sessões; grafo LangGraph mínimo | **CONFORME** | API real (`python -m vendinha`, portas 8123–8126) contra o Postgres do compose e o modelo real. SSE abre com `session`, fecha com `done`; o `session_id` do primeiro evento continua a conversa (turno 2 respondeu *"João, claro! A gente estava conversando agora mesmo"*). Mensagem em branco → **422** pelo contrato. Modelo fora da lista → 422 com *"consulte GET /models"*. Falsificação **V12** (tirar a allowlist) reprova |
| REQ-2 | Checkpointer em Postgres; estado carrega só IDs | **CONFORME** | A metade que a spec manda fazer à mão, na versão forte: **três processos distintos** contra o Postgres do compose — `pid=38424` gravou 2 turnos, `pid=35324` (processo novo) leu de volta e fechou em 4, `pid=35012` com outro `session_id` ficou isolado em 2. `ConversationState` continua com `{session_id, messages}` |
| REQ-3 | Langfuse Cloud instrumentado; indisponibilidade não propaga (ADR-010) | **CONFORME** | Consultei os traces de volta pela API pública: **263/263** traces da última hora com `sessionId`, `latency` e `totalCost` preenchidos, todos com `name: conversa`, zero sem `sessionId`. Trace auditado: `67cbe7359356bca5b0c8cc434b46ac73`, 11.568 bytes, 3 observações, `latency 1.32`, `totalCost 0.0006`. ADR-010 **provocado** (não esperado): subi a API com `LANGFUSE_BASE_URL=http://127.0.0.1:9` e `POST /chat` respondeu **200 em 2,118 / 1,195 / 1,199 s**, com `grep -ci traceback` = **0** no log |
| REQ-4 | Mascaramento de PII antes do envio **e em log** — invariante de release | **CONFORME**, com uma ressalva material e um achado sobre o teste | **Traces:** conversa real com CPF pontuado, CPF sem pontuação, e-mail, telefone e nome; trace bruto do Langfuse Cloud auditado campo a campo — CPF `False`, CPF sem pontuação `False`, e-mail `False`, telefone `False`, com `[CPF]`, `[EMAIL]` e `[TELEFONE]` presentes; `Marta Ribeiro` presente, como o texto emendado do REQ-4 agora declara. **Logs:** funcionam no caminho real (§1). **Ressalva:** a senha do DSN escapa quando o host não tem ponto — **NC-C**. **Achado sobre o teste:** nada prova que a aplicação instala a redação — **NC-A** |
| REQ-5 | Budget cap por sessão e timeout por tool; exceder = resposta honesta | **CONFORME** | API subida com `SESSION_BUDGET_TOKENS=50`, três turnos na mesma sessão: turno 1 respondeu normalmente; turnos 2 e 3 devolveram *"Essa nossa conversa já ficou bem longa e eu preciso parar por aqui…"*, **sem citar token, limite, número ou nome de configuração** (`adversarial-006`). Falsificação **V13** (`within_budget` sempre `True`) reprova 2 testes, um deles o que prova que o guarda roda **antes** da chamada ao modelo |
| REQ-6 | Provedor agnóstico; `GET /models`; `GET`/`PUT /config`; allowlist; credencial cifrada e que nunca volta | **CONFORME** | Gravei `sk-ant-api03-VERIFICACAO2FALSA…` (54 chars) por `PUT /config` num banco meu e varri **cinco rotas** — `/health`, `/config`, `/models`, `/openapi.json`, `/docs`: **nenhuma** contém a chave nem o fragmento. Log do processo: **0** ocorrências. Repouso: `instance_config.credentials` é um `bytea` de **184 bytes** começando em `gAAAAABq…` (Fernet), com `position('sk-' …) = 0`. A resposta do próprio `PUT` traz `source:"banco"` e dica de 4 caracteres. Falsificações **V6**, **V7** e **V12** reprovam |

---

## 4. Cenários BDD

```gherkin
Cenário: PII nunca aparece em trace
```

**CONFORME.** Sessão `verif2-pii-e1716a01`, trace `67cbe735…`, 11.568 bytes de JSON bruto lidos de
volta da API pública do Langfuse. O `input` do trace veio literalmente assim:

```
"content": "oi, aqui e Marta Ribeiro, meu cpf e [CPF] (ou [CPF]), meu email [EMAIL] e meu telefone [TELEFONE]. pode anotar?"
```

Nenhum `sk-ant`, `sk-lf`, `sk-proj`, `ANTHROPIC_API_KEY` nem a senha do DSN no trace. O nome está
em claro — declarado na D-6 e agora também no texto do REQ-4.

```gherkin
Cenário: retomada de sessão
```

**CONFORME**, na versão forte (processos diferentes, não grafos diferentes no mesmo processo):

```
pid=38424 sessao=r9-verif2 turnos=2  ['meu nome ficou registrado?', 'ok']
pid=35324 sessao=r9-verif2 turnos=4  ['meu nome ficou registrado?', 'ok', 'e agora, lembra?', 'ok']
pid=35012 sessao=r9-outra  turnos=2  ['nada a ver', 'ok']
```

```gherkin
Cenário: a credencial não volta pela porta da frente
```

**CONFORME.** Cinco rotas varridas contra uma chave gravada de verdade, mais o log do processo e o
`bytea` do Postgres. Nada vazou. Detalhe: `GET /models` **mudou** depois do `PUT` (a chave falsa
derrubou os modelos da Anthropic), o que é evidência de que a invalidação do cache funciona —
embora nada a teste (**NC-B**).

---

## 5. Métricas medidas vs alvo

| Métrica | Alvo | Spec declara | **Eu medi (rodada 2)** | Status |
|---|---|---|---|---|
| Suíte, nesta máquina | verde | 360 passed | **360 passed em 2,09 s** | CONFORME |
| Suíte, cópia limpa sem `.env` (= CI) | verde | 360 passed | **360 passed em 1,76 s** (`git archive HEAD`; `ENV_FILE.exists() == False` confirmado) | **CONFORME — NC-1 fechada** |
| `ruff check` / `ruff format --check` | limpo | limpo | **All checks passed** / **26 files already formatted** | CONFORME |
| `mypy --strict` em `backend/` | limpo | limpo | **Success: no issues found in 14 source files** | CONFORME |
| `mypy --strict` em `tests/` | limpo | limpo | **Success: no issues found in 10 source files** | CONFORME |
| `pytest tests -m "risco"` | coleta > 0 | **21** (R5: 10 · R6: 7 · R9: 4) | **24 passed**, 336 deselected (R5: **13** · R6: 7 · R9: 4) | número da spec **desatualizado** — NC-E |
| `commitlint` na branch | 0 problemas | — | **0 problems**, 3 avisos `footer-leading-blank`, 11 commits | CONFORME |
| `gitleaks` no histórico | 0 leaks | — | **no leaks found**, 41 commits, 1,71 MB | CONFORME |
| Sessões com trace completo | 100% | 13/13 | **263/263** traces da última hora com `sessionId`, `latency` e `totalCost` | CONFORME |
| PII em claro em **traces** | 0 | 0 | **0** para CPF (duas formas), e-mail e telefone; **nome em claro**, declarado | CONFORME |
| PII em claro em **logs da aplicação real** | 0 (R5) | — | **0** para CPF, e-mail, telefone e credencial, inclusive dentro do traceback | **CONFORME — NC-2 fechada** |
| Senha do DSN em log | 0 (implícito no docstring do módulo) | — | **vaza** quando o host não tem ponto (`@postgres`, `@db`, `@localhost`) | **NC-C** |
| Credencial em resposta / log / repouso | 0 | 0 | **0** — 5 rotas, log do processo, `bytea` de 184 B sem `sk-` | CONFORME |
| p95 1º token, sem `model` (cache quente) | ≤ 3 s | 1,109 s | **0,992 s** (n=10, mediana 0,902, min 0,872, max 1,037) | CONFORME |
| p95 1º token, com `model` (cache quente) | ≤ 3 s | 1,072 s | **0,992 s** (n=10, mediana 0,873, min 0,788, max 1,025) | CONFORME |
| 1º token com `model`, **cache frio** | ≤ 3 s | não medida | **4,043 s** (contra 1,197 s sem `model` no mesmo estado frio) | **estoura o alvo** — R-2b |
| Custo do `RedactingFormatter` por registro de log | — | não medida | 0 valores: **0,0065 ms** · 50: **0,30 ms** · 200: **1,42 ms** · 512: **17,28 ms** | **NC-H** |

### 5.1 O número que a spec ainda não conta: o primeiro pedido

O cache resolveu o regime permanente e não o primeiro pedido. Medido nesta máquina, contra a API
real, com o processo recém-subido:

```
COLD com model:  4,043 s     <- estoura o alvo de 3 s
COLD sem model:  1,197 s     <- mesmo estado frio, sem passar por _allowed_models
```

A diferença (~2,85 s) é a ida aos dois fornecedores. Com `MODELS_CACHE_SECONDS = 300` e a
expiração contada **a partir do preenchimento**, não do último acesso, esse pedágio reaparece a
cada 5 minutos por processo, mesmo sob tráfego contínuo. Para uma instância com pouco tráfego —
que é o caso da S-07 em demonstração — uma fração relevante das conversas começa pagando 4 s. A
linha da spec (*"1,072 s (n=10)"*) é verdadeira e é de cache quente; ela não diz isso.

### 5.2 O custo da redação de log cresce com o registro de nomes, e tem um degrau

O `RedactingFormatter` chama `redactor()` **por registro de log**, e `Redactor.text` roda um
`re.sub` para cada valor conhecido mais um por parte do nome. Medido:

```
   0 valores conhecidos ->   0,0065 ms por registro
   1                    ->   0,0136 ms
  10                    ->   0,0667 ms
  50                    ->   0,3032 ms
 200                    ->   1,4203 ms
 512                    ->  17,2828 ms      <- 12x o de 200
```

O degrau em 512 é o cache de padrões do módulo `re` (512 entradas) entrando em thrash: com 512
nomes o redator monta ~1.500 padrões distintos por chamada. E **512 é exatamente o `maxsize`
default de `KnownValues`**. Na S-02 nada alimenta o registro, então o custo real hoje é
0,0065 ms; a partir da S-04, que é quem chama `remember` (D-6), um processo longevo aterrissa no
degrau — e o log de acesso do uvicorn é escrito no event loop, uma linha por requisição. O mesmo
custo vale por atributo de span no hook de export. Ver **NC-H**.

---

## 6. As falsificações que executei nesta rodada

**13 quebras deliberadas, 10 reprovações, 3 sobreviveram.** Em cada uma quebrei o arquivo de
**produto**, rodei a suíte inteira e restaurei com `git checkout --`. Nenhum arquivo de teste do
repositório foi tocado — exceto na **V10**, que é sobre a fixture nova e por isso só faz sentido
ali, e mesmo essa foi feita na cópia limpa fora do repositório.

### 6.1 As que reprovaram

| # | O que quebrei | Reprovou em |
|---|---|---|
| **V1** | `install_log_redaction()` não coleta handler nenhum e não cria o fallback | `..._installing_log_redaction_actually_installs_something`, `..._traceback_never_carries_pii…`, `..._applications_own_logger_is_covered_too`, `..._plain_log_line_is_redacted_too` (4) |
| **V2** | tirei **só** o fallback do root, mantendo os loggers nomeados | `test_the_applications_own_logger_is_covered_too` — o teste em subprocesso, o único que enxerga o caminho do `vendinha.app` |
| **V3** | `RedactingFormatter.format` devolve o texto do formatter interno sem redigir | 3 testes de log |
| **V4** | `_every_handler()` passa a olhar só o root, ignorando os loggers nomeados | 2 testes de log |
| **V6** | inverti `effective_credentials()`: o ambiente passa a vencer o banco | `test_the_stored_key_is_the_one_the_model_actually_gets` — **o portão que eu atravessei na rodada 1 agora fecha** |
| **V7** | `_credentials()` do `app.py` passa a ignorar o banco | `..._model_list_comes_from_the_provider`, `..._chat_refuses_a_model_outside_the_server_list` |
| **V10** | desativei o `autouse` da fixture `encryption_key`, **na cópia limpa sem `.env`** | os **mesmos 4** testes nomeados pela NC-1 da rodada 1 — prova de que é essa fixture que a fecha |
| **V11** | o formatter redige **só** `record.msg`, deixando o traceback intocado (a regressão exata da NC-2) | 3 testes de log |
| **V12** | removi a validação de allowlist do `POST /chat` | `test_chat_refuses_a_model_outside_the_server_list` |
| **V13** | `within_budget` sempre `True` | `..._cap_allows_up_to_the_limit…`, `..._over_budget_answers_honestly_without_calling_the_model` |

A **V2** e a **V4** são as que valem: elas atacam **alcance**, não função, e as duas foram pegas
pelos testes que o autor escreveu para isso — inclusive o que roda em subprocesso porque o plugin
de logging do pytest troca os handlers do root em toda chamada. Esse par é a melhor coisa da
correção.

### 6.2 As três que sobreviveram

| # | O que quebrei | Resultado |
|---|---|---|
| **V5** | apaguei `install_log_redaction()` do `lifespan` do `app.py` — a aplicação nunca instala a redação | **360 passed.** Nada na suíte prova que a aplicação chama a função. Ver **NC-A** |
| **V8** | tirei `request.app.state.models_cache = None` do `PUT /config` — o cache nunca é invalidado | **360 passed.** Ver **NC-B** |
| **V9** | `MODELS_CACHE_SECONDS = 1e12` — o cache nunca expira | **360 passed.** Ver **NC-B** |

Verifiquei à mão que os dois comportamentos da V8/V9 **funcionam** hoje: com o seam de fornecedor
substituído, `GET /models` chamou o fornecedor 1× antes do `PUT`, 2× depois do `PUT` (invalidou) e
continuou em 2× na chamada seguinte (cacheou). O achado é a ausência de teste, não um defeito de
comportamento.

---

## 7. Invariantes globais

| Invariante | Verificação | Resultado |
|---|---|---|
| Ausência de segredo no histórico | `gitleaks v8.29.0` com o `.gitleaks.toml` do repo | **OK.** `no leaks found`, 41 commits, 1,71 MB |
| Ausência de CPF/CNPJ/certificado/dado real no diff | grep por CPF e CNPJ formatados, `sk-…`, `ghp_`, `APP_USR-`, `BEGIN PRIVATE KEY` em todas as linhas `+` de `origin/main...HEAD` | **OK.** As únicas ocorrências são o CPF de teste `123.456.789-09` (número público de validação, documentado como sintético em `tests/unit/conftest.py`) dentro dos testes e do relatório, e três constantes obviamente falsas (`"sk-ant-api03-" + "Z"*40`, `"sk-ant-ambiente-" + "x"*20`, `"sk-openai-" + "y"*20`) |
| Credencial nunca volta pela API | 5 rotas varridas contra uma chave gravada de verdade | **OK** |
| Credencial cifrada em repouso | `bytea` lido direto do Postgres: 184 B, prefixo Fernet, `position('sk-') = 0` | **OK** |
| PII mascarada em **traces** | trace bruto real do Langfuse Cloud, 11,5 KB, campo a campo | **OK** para CPF/e-mail/telefone; nome em claro, declarado |
| PII mascarada em **logs** | `LOGGING_CONFIG` do uvicorn + lifespan real + servidor real | **OK**, exceto a senha do DSN — **NC-C** |
| Escopo respeitado | grep por `qdrant`/`embedding`/`retriev`/`subagent`/`@tool`/`StructuredTool`/`StaticFiles`/`HTMLResponse`/`user_id`/`auth` em `backend/vendinha/` | **OK.** Só comentários casam. Nenhum diretório `frontend/`, nenhuma tool, nenhum subagent, nenhuma coluna de usuário. `instance_config` tem `CHECK (id = 1)` |
| Fronteira de permissões de subagents | não aplicável (o primeiro subagent chega na S-04) | **N/A** |
| Repositório restaurado após as falsificações | `git status --short` e `git diff --stat` ao fim | **OK.** Diff vazio; única entrada é `?? docs/workshop/apresentacao.html`, não rastreado, que já existia antes desta sessão |
| Banco do autor restaurado | 27 threads / 214 linhas removidas; `vendinha_verif2` e `vendinha_semtabela` derrubados; `instance_config` intocada | **OK** |

---

## 8. Não-conformidades (fora da tabela de requisitos)

### 8.1 Novas desta rodada

| # | Achado | Gravidade |
|---|---|---|
| **NC-A** | **Nada prova que a aplicação instala a redação de log.** Apagar `install_log_redaction()` do `lifespan` do `app.py` deixa a suíte **verde: 360 passed**. Os cinco testes de log do arquivo de `security` chamam a função **eles mesmos** — inclusive o de subprocesso, que a executa no script em vez de deixá-la vir pela `create_app`. É o **F14 da rodada 1 movido um nível acima**: antes nada provava que a função cobria os handlers, agora nada prova que alguém a chama. O `docs/testes.md` §1 define a camada `security` como *"a ação proibida é alcançável?"*, e a resposta continua vindo da camada `unit`. O agravante é que a linha apagada é exatamente a que a NC-2 existiu para acrescentar: uma refatoração que a remova reabre o achado Alta da rodada 1 com a suíte verde. O conserto é barato — `tests/unit/test_chat_endpoint.py` já sobe `TestClient(create_app(...))`, que roda o lifespan; basta esvaziar o root, subir a app e afirmar que os handlers ficaram embrulhados | **Alta** (sobre o teste) |
| **NC-B** | **A correção da R-2 entrou sem nenhum teste.** O cache de `_allowed_models` é comportamento novo em `app.py` e **duas falsificações independentes sobrevivem**: remover `request.app.state.models_cache = None` do `PUT /config` (**V8**) e tornar o TTL infinito (**V9**) deixam a suíte verde. Verifiquei à mão que os dois funcionam hoje, então não é defeito — é comportamento não sancionado. E o modo de falha da invalidação é literalmente o da **R-1** que esta mesma rodada fechou: o operador grava a chave nova, o `/config` responde `source: "banco"` com a dica da chave nova, e por até 5 minutos o `GET /models` e o `POST /chat` continuam recusando os modelos do provedor recém-configurado. Uma spec que acabou de aprender que "a vitrine concorda e o processo discorda" é o pior modo de falha não devia fechar reintroduzindo a forma dele | **Média** |
| **NC-C** | **A redação de traceback não cobre a senha do DSN, que o próprio docstring nomeia como alvo.** `RedactingFormatter` diz: *"the provider SDK or psycopg… carry API keys **and DSNs** that nobody chose to log"*. Medi `redact()` em quatro formas de DSN: `postgresql://u:s3nh4@127.0.0.1:5432/db` → mascarado; `…@localhost:5432/…`, `…@db:5432/…`, `…@postgres/…` → **senha em claro**. O único caso que funciona funciona **por acidente**: `s3nh4@127.0.0.1` casa com o regex de `EMAIL` e vira `[EMAIL]`. Host sem ponto é justamente a forma dentro de uma rede Docker, que é o que a S-08 vai usar (ADR-008), e é a forma que aparece em exceção de `psycopg`. Nenhum dos testes de log usa um DSN — os dois afirmam sobre CPF e chave de provedor. Um padrão para `://usuario:senha@` custa uma linha em `PATTERNS` e um caso no arquivo de `security` | **Média** |
| **NC-D** | **As nove ressalvas da rodada 1 (R-3 a R-11) não foram registradas em lugar nenhum.** O relatório anterior condicionou o adiamento delas: *"podem ser tratadas nas specs seguintes, **desde que registradas**"*. A seção "Ressalvas herdadas" da spec cobre só as da S-01. O único lugar onde elas existiam é **este arquivo**, que esta rodada sobrescreve — ou seja, sem a §9 abaixo, o ritual apagaria as próprias descobertas. Não é detalhe de arquivo: é o mecanismo pelo qual o repositório não perde achado, e ele falhou em silêncio. Remedi as nove nesta sessão e as carrego na **§9**, mas o lugar delas é a spec | **Média** |
| **NC-E** | **O número de testes-âncora ficou desatualizado pelo próprio commit de correção.** A spec afirma **"21 (R5: 10, R6: 7, R9: 4)"**; medi **24 (R5: 13, R6: 7, R9: 4)**. O commit `06d2fd8` acrescentou 3 testes de R5 e não mexeu no número que ele mesmo estava consertando. É a repetição da NC-7 dentro da correção da NC-7 — e a própria spec prevê essa classe (*"ela é escrita antes do último commit existir"*), o que reforça que o conserto de verdade é derivar esses números de comando (`pytest -m risco`, `git log`) em vez de escrevê-los à mão | **Baixa** |
| **NC-F** | **A mensagem do commit `06d2fd8` está em português.** O `CLAUDE.md` §Fluxo item 3 e §Convenções mandam *Conventional Commits, **em inglês***. Há precedente na `main` (`7bbfa86 fix(s-00): corrigir os achados da verificação independente`), e o próprio autor tem nesta branch um `refactor(s-02): put the code back in english` corrigindo exatamente essa classe de derrapada — o que torna a reincidência mais visível, não menos. Ou a regra vale e este commit precisa de mensagem em inglês, ou o `CLAUDE.md` abre a exceção por escrito para commits de resposta a verificação | **Baixa** |
| **NC-G** | **O deny de `.env.*` foi fechado por enumeração, e o resíduo não está escrito.** Oito nomes cobertos; o `.gitignore` continua tratando **qualquer** `.env.*` como segredo. `.env.staging`, `.env.hml`, `.env.ci`, `.env.vps` seguem git-ignorados e legíveis pelo agente. Registro em favor do autor que a receita literal da rodada 1 — *"negar `.env.*` e permitir `.env.example`"* — **não funciona**: no Claude Code o `deny` vence o `allow`, então essa combinação bloquearia o próprio exemplo. A enumeração é resposta defensável; o que falta é (a) dizer isso em algum lugar e (b) o cabeçalho do `.env.example` parar de descrever as duas garantias como pareadas quando elas são pareadas só para oito nomes | **Baixa** |
| **NC-H** | **O custo da redação de log cresce com o registro de nomes e tem um degrau em 512, que é o `maxsize` do registro.** Medido (§5.2): 0,0065 ms com o registro vazio, 1,42 ms com 200 valores, **17,28 ms com 512**. A causa do degrau é o cache de padrões do módulo `re`, de 512 entradas, entrando em thrash. Hoje é inofensivo porque `KNOWN_VALUES.remember` não tem chamador em produção — mas a D-6 diz que **a S-04 é quem passa a chamar**, e o `RedactingFormatter` roda em **todo** registro de log, incluindo o de acesso do uvicorn, escrito no event loop. Não é defeito desta spec: é uma conta que a S-04 vai herdar sem saber, e ela precisa estar escrita antes de alguém a descobrir com um p95 estranho | **Baixa** (latente; vira Média na S-04) |

### 8.2 Herdada e ainda aberta

| # | Achado | Estado |
|---|---|---|
| **NC-4** | ADR-005, `.claude/commands/verificar-spec.md` e o corpo da issue #3 continuam contradizendo o `CLAUDE.md` sobre quando a verificação acontece | **Aberta, adiamento aceito.** O motivo registrado na spec é correto: mudança de ritual dentro do PR de uma spec é o padrão que virou a R-9 da S-01. Mas o custo já foi pago duas vezes — esta sessão também precisou de exceção escrita para executar o próprio ritual |

---

## 9. Ressalvas — carregadas da rodada 1 e remedidas nesta sessão

A NC-D explica por que esta seção existe: sem ela, sobrescrever o arquivo apagaria os achados.
**Cada linha foi reconferida agora**, não copiada.

| # | Ressalva | Reconferida em 2026-08-26 (rodada 2) |
|---|---|---|
| **R-2b** | **O primeiro pedido com `model` continua acima do alvo**: 4,043 s frio contra 1,197 s sem `model` | **Nova/derivada da R-2.** O cache resolveu o regime quente e deslocou o custo, não o eliminou. Com TTL contado do preenchimento, reaparece a cada 5 min por processo. Um refresh assíncrono, ou preencher o cache no `lifespan`, tira o pedágio do caminho do cliente |
| **R-3** | `redact()` — a função pattern-only — não tem consumidor em produção | **Continua.** `grep` em `backend/vendinha/`: os únicos chamadores reais são `redactor()` em `mask_otel_spans` e no `RedactingFormatter`. `redact()` só é chamada por testes. Não é defeito; explica por que quebrar `redact` sozinha não diria nada sobre a aplicação |
| **R-4** | `Redactor.attributes` só redige valores `str` | **Continua.** `if isinstance(value, str)` inalterado. Atributo de OTel pode ser sequência de strings, e uma `tuple[str, …]` atravessa o hook intocada. Risco latente, não vazamento observado |
| **R-5** | `LOG_LEVEL` está no `.env.example` marcado `(S-02)` e nada o lê | **Continua.** `grep` em `backend/vendinha/`, `scripts/` e `Makefile`: **nenhum** consumidor; `Settings` não tem o campo. Combina especialmente mal com a NC-2, que era sobre log: quem for depurar redação vai pôr `LOG_LEVEL=DEBUG` e concluir que não há o que ver |
| **R-6** | `vendinha/db.py:main()` imprime o `DATABASE_URL` inteiro no stderr quando falha, senha incluída | **Continua**, e agora conversa com a **NC-C**: é o mesmo segredo, no mesmo canal, e o `print` do `db.py` nem passa pelo `logging`, então nenhuma redação o alcança |
| **R-7** | `resolve_model` tem `lru_cache(maxsize=8)` com a `api_key` na chave do cache | **Continua.** Correto para invalidar em rotação; registro porque a S-08 vai discutir dump de memória |
| **R-8** | `GET /config` é aberto e informa `encryption_ready`, `editable`, provedores configurados e dica de 4 caracteres, sem autenticação, em qualquer ambiente | **Continua.** Aceitável até a S-08; merece uma linha explícita lá em vez de ser redescoberto |
| **R-9** | Ressalvas herdadas da **S-01** ainda abertas: R-3 (fixture ↔ seed), R-5 (corpo do ADR-003), R-10 (seed malformado) | **Continuam**, e a spec as registra com honestidade na seção própria. Reconferi que nenhum arquivo novo desta spec constrói dado no import de módulo |
| **R-10** | `README`/`Makefile` mandam `make db-setup` antes de `make api` e nada sanciona o esquecimento | **Continua**, e eu topei com ele de propósito: apontei a API para um banco sem tabelas e o resultado foi `psycopg.errors.UndefinedTable: relation "checkpoints" does not exist` na primeira mensagem, não no boot. A decisão de não migrar no startup está certa; a mensagem é que podia dizer `rode make db-setup` |
| **R-11** | O `.venv` desta máquina é Python 3.13.2 e o CI usa 3.12 | **Continua**, e vale para os meus números também. `mypy` está fixado em `python_version = "3.12"` de qualquer jeito |
| **R-12** | **Nova.** Over-masking latente para a S-05: uma chave de acesso de NF-e escrita em grupos de quatro (`35 2408 1234 5678`) é parcialmente mascarada como `[TELEFONE]` | Medido. Hoje é inofensivo; a S-05 é a spec que vai olhar chave de acesso em trace e log |
| **R-13** | **Nova.** `install_log_redaction()` **acrescenta um `StreamHandler` ao root** quando ele está vazio. É o que fecha a NC-2 e é a decisão certa — mas muda o destino padrão de qualquer log de terceiro no processo (de `logging.lastResort` para stderr, no nível do root). Verifiquei que **não** duplica saída sob uvicorn (`uvicorn` e `uvicorn.access` têm `propagate: False`) | Efeito colateral correto e não declarado. Uma linha no docstring do módulo ou no `.env.example` evita a surpresa |

---

## 10. Avaliação das "Descobertas" novas

Lidas como *alterações de escopo a justificar*, não como fatos aceitos. As D-1 a D-12 foram
avaliadas na rodada 1 e eu reconferi por amostragem que continuam válidas (D-1: `AliasChoices`
com os dois nomes; D-2: `SESSION_BUDGET_USD` não existe mais em código, exemplo ou docs; D-5:
`runtime.run()` funcionou nos meus scripts com `psycopg` async no Windows; D-8: `PUT /config` só
em `local`; D-12: `Settings.api_host` tem default `127.0.0.1` **no código**, não só no exemplo).

| # | Veredito | Comentário |
|---|---|---|
| **D-13** (a verificação reprovou, e o que ele aprendeu) | **Legítima, honesta, e incompleta em dois pontos** | A tabela descreve corretamente cada achado e cada correção, e o parágrafo sobre o método — *"eu escrevi o comentário que descreve o defeito e consertei só a instância na minha frente"* — é o melhor texto da spec e bate com o que eu medi. Dois problemas: (1) a linha da **R-2** diz *"Medido depois: 1,072 s com `model`"* sem dizer que é cache quente, e o primeiro pedido custa 4,0 s (§5.1); (2) a linha da **NC-2** descreve a correção como *"`install_log_redaction()` devolve quantos cobriu, **para um teste reprovar quando ela virar no-op**"* — verdade, e o que a **V5** mostra é que virar no-op não é o único jeito de a redação sumir. O adiamento da **NC-4** está bem argumentado e eu o aceito |
| **Descoberta que eu esperaria e não encontrei** | — | Que **as ressalvas da própria verificação precisam morar na spec**, e não só no relatório. A D-13 traz para a spec as sete não-conformidades e as duas ressalvas que exigiam código, e deixa as outras nove fora — no arquivo que o ritual sobrescreve. Ver **NC-D** |

---

## 11. Veredito

# APROVADO COM RESSALVAS

**Por que não continua REPROVADO.** As duas coisas que reprovaram a rodada 1 eram objetivas, e as
duas estão objetivamente resolvidas — medidas por mim, do jeito que o relatório anterior pediu
que fossem medidas, e falsificadas depois.

A **NC-1** era *"a suíte não passa numa cópia limpa"*. Passa: **360 passed** num `git archive
HEAD` extraído para um diretório sem `.env`, com o `ENV_FILE` verificado como inexistente e a
variável fora do shell. E a correção não comprou verde tirando cobertura: o caminho `503 sem
chave` continua provado, e desligar a fixture nova reabre **exatamente** os quatro testes que a
rodada 1 nomeou.

A **NC-2** era *"a metade logs do R5 não roda"*. Roda. Reproduzi o caminho de produção
(`LOGGING_CONFIG` do uvicorn + o `lifespan` real) e o traceback saiu com `[CREDENCIAL]` e `[CPF]`
no lugar do segredo e do CPF; subi o servidor de verdade contra um banco quebrado e o
`logger.exception` do endpoint apareceu formatado, com o cliente recebendo só a mensagem vaga. As
cinco quebras que atacam essa correção — inclusive a que remove **só** o fallback do root e a que
redige `record.msg` mas não o traceback — reprovaram todas, cada uma no teste certo.

**Por que não é APROVADO limpo.** Três coisas, e a primeira é a que a instrução desta rodada
mandava procurar: o teste escrito para satisfazer um relatório que passa sem provar o que
importa.

A **NC-A** é isso. O teste novo responde *"a função instala alguma coisa?"*. A pergunta da rodada
1 era *"a redação está no caminho?"*, e ela continua sem resposta um nível acima: **apagar a
chamada no `lifespan` deixa a suíte verde**. Não acuso má-fé — o autor entregou literalmente a
condição de aceite escrita, e a falha é tanto da prescrição quanto da execução. Mas o efeito é
concreto: a linha cuja ausência causou o achado Alta da rodada 1 pode ser removida hoje sem que
nada reclame. Num requisito que a própria spec chama de *invariante de release*, isso é ressalva
de gravidade Alta.

A **NC-B** é a segunda: o cache que fez a R-2 passar é comportamento novo com **zero** teste, e
duas falsificações sobrevivem. O modo de falha da invalidação não testada é o mesmo que a R-1 —
fechada nesta rodada — descreveu como o pior possível: a vitrine concorda e o processo discorda.

A **NC-C** é a terceira, e é a única que toca o código que roda: a redação de traceback não
alcança a senha do DSN, que o docstring do próprio módulo nomeia como alvo. Ela só não vaza hoje
porque o host configurado tem pontos e casa por acidente com o regex de e-mail. Com o host de
contêiner que a S-08 vai usar, vaza.

**Nenhuma das três reprova a entrega**, e é por isso que o veredito é aprovação: os seis
requisitos estão conformes contra serviços reais, a suíte é verde na condição exata do CI, o
escopo foi respeitado ao pé da letra, não há segredo nem dado real no diff, e 10 das 13
falsificações reprovaram no teste certo — incluindo as que atacam alcance, que são as difíceis.

### O que eu faria antes de abrir o PR (barato, e fecha o que sobrou)

1. **NC-A** — um teste de alcance sobre a **aplicação**: esvaziar o root, subir
   `TestClient(create_app(...))` (que já roda o lifespan em `test_chat_endpoint.py`) e afirmar que
   os handlers ficaram embrulhados. Critério de aceite: apagar a chamada no `lifespan` tem que
   reprovar.
2. **NC-E** — trocar "21 (R5: 10…)" por **24 (R5: 13, R6: 7, R9: 4)**, e de preferência passar a
   derivar esse número de `pytest -m risco` em vez de escrevê-lo.
3. **NC-D** — trazer para a spec as ressalvas da verificação que não viram código (a §9 deste
   relatório serve de texto), para o próximo `/verificar-spec` não depender de um arquivo que ele
   mesmo sobrescreve.
4. **NC-F** — decidir: ou a mensagem do commit vai para inglês, ou o `CLAUDE.md` abre a exceção
   por escrito para commits de resposta a verificação.

### O que pode viajar para a spec seguinte, desde que **registrado na spec**

**NC-B** (teste do cache e da invalidação), **NC-C** (padrão para senha de DSN mais um caso no
arquivo de `security`), **NC-G** (dizer que o deny é enumerado e por quê; alinhar o cabeçalho do
`.env.example`), **NC-H** (o custo do redator na S-04), **NC-4** (o PR de harness já previsto) e
as ressalvas **R-2b** e **R-3 a R-13** da §9.

---

*Relatório produzido por sessão revisora independente, sem acesso ao histórico da sessão autora.
Todos os números acima foram medidos nesta máquina, nesta sessão, contra o Postgres do compose, o
Langfuse Cloud real e as APIs da Anthropic e da OpenAI reais. Nenhum arquivo do repositório foi
alterado por esta sessão além deste relatório: os arquivos quebrados durante as 13 falsificações
foram restaurados com `git checkout --`, os bancos `vendinha_verif2` e `vendinha_semtabela` foram
derrubados, as 27 threads de teste criadas no banco `vendinha` foram removidas (214 linhas entre
as três tabelas do checkpointer), e `git status --short` ao final acusa apenas este relatório e o
`docs/workshop/apresentacao.html` não rastreado, que já existia antes.*

*Nota de processo, repetida da rodada 1 porque continua verdadeira: o passo 6 do
`.claude/commands/verificar-spec.md` manda publicar este relatório como comentário no PR, e não
existe PR — porque o `CLAUDE.md`, que tem precedência 1, mudou o ritual para verificação **antes**
do PR. A entrega é o arquivo. Ver **NC-4**.*
