---
id: S-02
titulo: Agente base observável
status: em-revisao
branch: spec/s-02-agente-observavel
issue: #3
adrs: [ADR-001, ADR-007, ADR-010, ADR-012]
riscos_cobertos: [R5, R6, R9]
---

# S-02 — Agente base observável

## Objetivo
O menor agente possível — porém com observabilidade, privacidade e limites de custo desde o
primeiro trace. Observabilidade no commit 1, não no incidente 1.

## Requisitos
- [x] REQ-1 FastAPI com `POST /chat` (SSE) e sessões; grafo LangGraph mínimo (um nó de conversa).
- [x] REQ-2 Checkpointer em Postgres; estado carrega apenas IDs (pointer-not-payload).
- [x] REQ-3 Langfuse Cloud instrumentado (`LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY`,
      `LANGFUSE_SECRET_KEY`): trace por sessão com tools, custo, latência. Indisponibilidade
      do Langfuse não pode propagar exceção para o atendimento (ADR-010).
      *O texto original dizia `LANGFUSE_HOST`, nome da v3 do SDK. Ver D-1.*
- [x] REQ-4 Mascaramento de PII (CPF, e-mail, nome) na camada de instrumentação **antes** do envio.
      Com Langfuse Cloud o trace sai da infra, então este REQ é invariante de release: sem o
      teste de redação verde, a spec não fecha (ADR-010, R5).
- [x] REQ-5 Budget cap por sessão e timeout por tool via config; exceder = resposta honesta de limite.
      A unidade do cap é **token**, não USD — ver D-2.
- [x] REQ-6 Provedor de LLM agnóstico com credencial configurável em runtime (ADR-012):
      `GET /models` lista os modelos disponíveis a partir das credenciais existentes,
      `GET`/`PUT /config` leem e gravam a configuração da instância, e o campo `model` do
      `POST /chat` é validado contra a allowlist do servidor. A credencial é cifrada em
      repouso, nunca volta pela API e nunca entra em trace ou log. Ver D-3.

## Fora de escopo
- RAG, subagents, tools de negócio.
- **A tela de configuração.** A S-02 entrega o contrato de API (e o OpenAPI de onde os tipos
  TypeScript são gerados, ADR-004); a interface é entregável da S-07.
- **Credencial por usuário.** Não existe usuário nem autenticação nesta spec: o que se
  persiste é uma linha de configuração da instância (ADR-012).

## Tasks (cada uma vira um commit)
1. `adr(s-02): provider-agnostic llm with runtime credentials` — ADR-012, D15 e a emenda da spec
2. `feat(s-02): minimal langgraph graph with postgres checkpointer`
3. `feat(s-02): fastapi chat endpoint with sse and session handling`
4. `feat(s-02): langfuse instrumentation with pii masking`
5. `feat(s-02): session budget cap and per-tool timeout`
6. `feat(s-02): runtime provider config with encrypted credentials`
7. `ci(s-02): extend typecheck to the test suite` — ressalva R-4 da verificação da S-01

> As duas primeiras tasks trocaram de ordem em relação ao texto original da spec (o endpoint
> vinha antes do grafo). Construir o endpoint primeiro exigiria um motor de conversa
> provisório só para ele ter o que transmitir — código descartável na `main` por uma task
> inteira. Com o grafo primeiro, o teste do endpoint injeta o `BaseChatModel` falso na
> fronteira que o ADR-012 já declara como porta, e nada provisório é escrito.

## BDD
```gherkin
Cenário: PII nunca aparece em trace
  Dado uma conversa em que o cliente informa um CPF de teste
  Quando inspeciono o trace da sessão no Langfuse
  Então o CPF aparece mascarado e nunca em texto claro

Cenário: retomada de sessão
  Dado uma conversa interrompida após 3 turnos
  Quando o cliente retorna com o mesmo session_id
  Então o grafo retoma do checkpoint sem perda de contexto

Cenário: a credencial não volta pela porta da frente
  Dado que o operador gravou uma API key pela configuração
  Quando qualquer rota da API é consultada, incluindo a de configuração
  Então nenhuma resposta contém a chave — só `configured: true` e uma dica mascarada
```

## Métricas de sucesso
| Métrica | Alvo | Medido |
|---|---|---|
| Sessões com trace completo | 100% | **13/13** consultadas de volta pela API do Langfuse Cloud |
| PII em claro em traces/logs | 0 ocorrências | **0** — trace bruto da sessão `auditoria-pii-01` auditado campo a campo |
| Credencial em claro em traces/logs/respostas | 0 ocorrências | **0** — resposta da API e coluna `bytea` do Postgres inspecionadas |
| p95 primeiro token | ≤ 3s | **1,31 s** (n=10, mediana 0,95 s) |
| Suíte | verde | **356 passed**, `ruff` limpo, `mypy --strict` limpo em `backend/` e em `tests/` |

Medições feitas nesta máquina contra o Postgres do compose, o Langfuse Cloud real e a API da
Anthropic e da OpenAI reais. Os scripts de medição não entram no repositório: eles não são
entregável desta spec, e a verificação independente vai querer medir por conta própria.

## Tabela de execução

| Task | Commit | Nota |
|---|---|---|
| — | `chore(harness): close out s-00 and s-01 and narrow the env deny rule` | Fora do escopo da S-02, por decisão do PO. Commit isolado, escopo `harness` |
| 1 | `adr(s-02): provider-agnostic llm with runtime credentials` | ADR-012, D15, REQ-6, `.env.example` |
| 2 | `feat(s-02): minimal langgraph graph with postgres checkpointer` | R9 |
| 3 | `feat(s-02): fastapi chat endpoint with sse and session handling` | REQ-1 |
| — | `refactor(s-02): put the code back in english` | Correção de convenção do próprio autor; nenhuma mudança de comportamento |
| 4 | `feat(s-02): langfuse instrumentation with pii masking` | R5, REQ-3, REQ-4 |
| 5 | `feat(s-02): session budget cap and per-tool timeout` | R6, REQ-5 |
| 6 | `feat(s-02): runtime provider config with encrypted credentials` | REQ-6 |
| 7 | `ci(s-02): extend typecheck to the test suite` | Ressalva R-4 da verificação da S-01 |

**9 commits para 7 tasks.** As duas diferenças estão explicadas acima e nenhuma é escopo novo:
uma é governança que o PO mandou entrar isolada, a outra é o autor consertando a própria
derrapada de convenção antes que ela virasse padrão.

## Verificação independente
- Enviar CPF/e-mail de teste e auditar o trace bruto.
- Forçar estouro de budget e verificar a degradação honesta — e que a resposta **não** revela
  valor de configuração nem nome de limite (`evals/adversarial/adversarial-006`).
- Gravar uma chave falsa pela API e varrer resposta, log e trace atrás dela em claro.
- Reiniciar o processo de verdade e retomar a sessão pelo mesmo `session_id` — é a metade
  manual do R9, declarada em `docs/testes.md` §1 porque não existe camada de integração.

## Descobertas (preenchido durante a execução)

**D-1 — `LANGFUSE_HOST` é o nome da v3; o SDK atual documenta `LANGFUSE_BASE_URL`.**
O REQ-3, o `.env.example`, o comentário do `docker-compose.yml` e a §Consequências do
ADR-010 nomeiam `LANGFUSE_HOST`. A documentação do SDK Python v4 (`langfuse 4.x`, reescrito
sobre OpenTelemetry) usa `LANGFUSE_BASE_URL` em todos os exemplos e não menciona o nome
antigo em `docs/observability/sdk/overview`.

Resolvido dentro do escopo: o código lê `LANGFUSE_BASE_URL` e aceita `LANGFUSE_HOST` como
fallback — quem já tem um `.env` escrito não quebra. O `.env.example` e o REQ-3 passam a
documentar o nome atual. **O ADR-010 não foi tocado:** a decisão que ele registra é *Langfuse
Cloud em vez de self-hosted*, e ela continua inteira; o que mudou foi o nome de uma variável
de terceiro, que é consequência e não decisão. Emendar um ADR aceito por causa disso
gastaria o mecanismo que a S-01 construiu para mudanças que de fato revogam decisão.

**D-2 — o `.env.example` declarava `SESSION_BUDGET_USD`; o cap é por token.**
Medir custo em USD exigiria uma tabela de preço por modelo dentro do repositório — e, agora
que o provedor é configurável (ADR-012), seriam várias, desatualizando em silêncio. O
`usage_metadata` do LangChain dá contagem de token normalizada entre fornecedores, o que
torna `tests/unit/test_budget_guard.py` determinístico e sem rede. O custo em R$ continua
visível no dashboard do Langfuse, que é exatamente onde `docs/riscos.md` R6 já o colocava.
Decidido pelo PO na abertura da spec. `SESSION_BUDGET_USD` vira `SESSION_BUDGET_TOKENS`.

**D-3 — provedor agnóstico e chave pela UI: decisão do PO, registrada em ADR-012.**
O pedido — *"funcionar com Anthropic, OpenAI ou outro provedor; o usuário só coloca a chave
dele, e o modelo é configurável na UI"* — não cabia em nenhum dos cinco requisitos originais
e cria uma classe nova de segredo dentro do processo. Foi tratado como decisão de
arquitetura, não como implementação silenciosa: **ADR-012** (D15), REQ-6 na spec, e três
invariantes que o código prova — allowlist no servidor, credencial que nunca volta pela API,
credencial que nunca entra em trace ou log. A cifra em repouso protege contra dump do banco
e **não** contra quem já tem o `.env`; está escrito assim no ADR de propósito.

**D-4 — a credencial não ganha seam novo.**
O caso "a chave não sai deste processo" entra em `tests/security/test_pii_redaction.py`, e
não em arquivo próprio. O seam é o mesmo que o R5 já ocupa — *o que atravessa a fronteira do
processo* — e `docs/testes.md` §2 mapeia esse seam para aquele arquivo. Criar
`test_credential_leak.py` seria inventar camada no meio da execução, que a §3 item 6 manda
registrar em vez de improvisar. Registrado para o `/verificar-spec` não ler a ausência do
arquivo como lacuna.

**D-5 — `psycopg` async não roda no event loop default do Windows.**
O `ProactorEventLoop`, default do asyncio no Windows desde o 3.8, é recusado pelo `psycopg`
em modo async: *"Psycopg cannot use the 'ProactorEventLoop' to run in async mode"*. O erro
chega na primeira chamada ao banco, não no startup, e fala de event loop para quem está
pensando em Postgres.

Importa mais do que parece: o desenvolvimento acontece no Windows e o deploy vai para uma VPS
Linux (ADR-008) — a plataforma que quebra é justamente a que o CI nunca executa.

E o conserto óbvio não funciona. Definir a *policy* do asyncio resolve o CLI e **não** resolve
o servidor: o uvicorn constrói o loop por um factory próprio, não pela policy, então quando
qualquer código da aplicação roda o loop já é o errado — inclusive dentro do `lifespan`. O que
funciona é ser dono da chamada a `asyncio.run`. Por isso existe `python -m vendinha`
(`make api`) em vez de `uvicorn vendinha.app:app`: o entrypoint monta o `uvicorn.Server` à mão
e o entrega a `runtime.run()`, que é o único lugar que decide o tipo de loop do processo.

Detalhe de tipagem que veio junto: o teste é `os.name == "nt"` e não `sys.platform == "win32"`
porque o mypy trata `sys.platform` como constante de compilação e apaga um dos dois ramos —
com `warn_unreachable` ligado, um ramo diferente em cada plataforma vira erro.

Verificado ponta a ponta contra o Postgres do compose: dois processos separados retomando o
mesmo `session_id`, e a API real respondendo em SSE com o modelo real.

**D-6 — o REQ-4 pede mascarar "nome", e não existe versão honesta disso por padrão.**
CPF, CNPJ, e-mail, telefone e credencial têm forma, então um padrão os encontra em qualquer
texto, de qualquer origem. **Nome não tem forma.** Não existe regex para "isto é nome de
pessoa", e prometer detecção genérica seria vender um NER que este projeto não tem.

O que foi entregue são duas garantias diferentes, e a spec passa a nomear as duas:

| Mecanismo | Garantia | Alcance |
|---|---|---|
| Por padrão | absoluta, sem ninguém registrar nada | CPF, CNPJ, e-mail, telefone, credencial |
| Por valor conhecido | a partir do momento em que a sessão coletou o dado | nome |

O registro é **do processo, não da sessão** — e isso também é decisão. A redação que importa roda
na thread de export do OpenTelemetry, que não tem contexto de requisição e nunca vai ter: um
`contextvar` gravado na thread da requisição simplesmente não está lá quando o lote embarca. Um
registro que o export consegue ler é a única coisa que faz a garantia valer **na fronteira**, que
é o que um teste de `security` existe para provar. O preço é mascarar demais (um nome coletado
numa sessão some das outras enquanto estiver lembrado) e é limitado por tamanho, para um processo
longevo não virar vazamento de memória com uma lista de clientes dentro.

Na S-02 nada é coletado, então o nome aparece em claro no trace — **verificado, e registrado
aqui de propósito**. A auditoria do trace real da sessão `auditoria-pii-01` no Langfuse Cloud:
CPF, CPF sem pontuação, e-mail e telefone **ausentes**, com `[CPF]`, `[EMAIL]` e `[TELEFONE]` no
lugar; `Marta` presente. Quem coleta o nome é a S-04, e é ela que chama `KNOWN_VALUES.remember`.

**D-7 — pendurar é pior que dar erro, e foi o que aconteceu.**
O startup da API travou em *"Waiting for application startup"* com o Postgres saudável. Causa: o
`DATABASE_URL` do `.env` usava `localhost`, que no Windows resolve para `::1` antes de
`127.0.0.1` — e o compose publica só em IPv4. A libpq não recusa: ela **espera**, sem timeout
default.

Duas correções, e a segunda é a que importa:

1. o `.env.example` passou a usar `127.0.0.1` (feito na task 1, antes de o bug aparecer);
2. `open_checkpointer` agora injeta `connect_timeout=5` em qualquer DSN que não traga um.

O detalhe que vale registrar: com o timeout, o `localhost` **passa a funcionar** — a libpq
desiste do `::1` e cai para IPv4. O bound converteu um travamento infinito num sucesso lento, e
sucesso lento é o bug mais difícil de notar: cinco segundos em toda conexão, sem nenhum erro
para investigar. Por isso o `.env.example` fixa `127.0.0.1` em vez de confiar no fallback.

**D-8 — não existe autenticação, e `PUT /config` guarda credencial.**
O REQ-6 entrega uma rota que grava a API key do provedor. Não há usuário, sessão de operador
nem autenticação em nenhuma spec até a S-08 — então essa rota, aberta, é uma porta para gravar
credencial de terceiro em qualquer host que a exponha.

Resolvido por restrição em vez de por promessa: **a escrita só é aceita com `APP_ENV=local`**.
Em `dev` ou `prod` o `PUT /config` responde `403` e o `GET /config` devolve `editable: false`.
Leitura continua liberada porque ela não expõe nada — `configured`, a origem (`banco` /
`ambiente` / `nenhuma`) e uma dica de quatro caracteres.

Isso deixa uma consequência explícita para a S-07 e a S-08: **a tela de configuração não
funciona fora do ambiente local até existir autenticação.** É a intenção. "Depois a gente
protege" é como uma rota assim nunca é protegida.

**D-9 — não existe catálogo de modelos neste repositório, e é de propósito.**
A escolha do modelo na UI precisa de uma lista. A saída óbvia — uma constante com os ids de
cada fornecedor — é exatamente o que o ADR-001 proíbe o agente de fazer: afirmar um fato que
não foi lido de uma fonte. Uma lista escrita de memória está desatualizada na semana seguinte e
nada avisa.

`GET /models` pergunta ao próprio fornecedor (`models.list()` de cada SDK), e o resultado
prova o argumento: **119 modelos** vieram na primeira execução real, entre eles alguns que não
estariam numa lista escrita à mão. O seam de teste é `Provider.list_models`, que é o adapter
para a API de terceiro — o lugar onde `docs/testes.md` §4 permite substituir.

Fornecedor fora do ar devolve lista vazia em vez de erro: um seletor que explode porque um
fornecedor teve uma tarde ruim é pior que um seletor com uma opção a menos.

**D-10 — a recusa por falta de chave de criptografia morava no lugar errado.**
O teste do REQ-6 pegou: `CredentialsUnavailable` era levantada dentro do `PostgresConfigStore`,
então a garantia *"sem `CONFIG_ENCRYPTION_KEY`, não se guarda credencial"* dependia de qual
implementação do `ConfigStore` estivesse ligada — com a de memória, a gravação passava. Recusar
é **política**, não persistência. A checagem subiu para o endpoint (`503`, não `500`: o serviço
está bem, o deploy é que está incompleto), e o store manteve a dele como defesa em profundidade.

**D-11 — o Langfuse Cloud caiu no meio da medição, e isso virou verificação.**
Ao consultar os traces de volta para medir a cobertura, a API do Langfuse começou a responder
com `ReadTimeout` desta máquina. O ADR-010 exige que indisponibilidade do Langfuse **não**
derrube o atendimento, e a exigência foi verificada no ambiente real em vez de simulada: com a
nuvem inalcançável, o `POST /chat` respondeu em **1,4 s**, sem exceção, sem degradação visível
ao cliente. A consulta voltou a funcionar na quarta tentativa e a cobertura fechou em 13/13.

Vale como nota de método: essa é a única forma de verificar essa exigência de que eu confio —
esperar a falha acontecer sozinha. Um teste que desliga o Langfuse à mão prova que o código
trata *o caso que o teste imaginou*.

## Ressalvas herdadas da verificação da S-01

O relatório da S-01 deixou cinco ressalvas registradas sem correção. Duas caíam nesta spec e
foram fechadas; as outras três continuam abertas, e ficam registradas aqui para o
`/verificar-spec` não ter que procurá-las no relatório anterior.

| Ressalva | Estado |
|---|---|
| **R-4** — `tests/` fora do `mypy` | **Fechada.** O `typecheck` cobre a suíte, no `make` e no CI. Não foi cosmético: o portão mais largo achou 35 erros reais, entre eles um `dict` sem parâmetro em `tests/security/conftest.py` e um `Returning Any` numa fixture. O pacote `vendinha` ganhou `py.typed` — sem o marcador, todo `import` do produto dentro de `tests/` virava `Any` e a suíte estaria dentro do portão sem aprender nada com isso |
| **R-11** — `pytest tests -m "risco"` coletava zero | **Fechada.** Os treze testes-âncora da S-02 declaram o marker: `21 passed, 335 deselected`. O comando do `docs/testes.md` §6 deixou de ser decorativo |
| **R-3** — fixture ↔ seed continua acordo humano | Aberta. A S-02 não toca no catálogo |
| **R-5** — corpo do ADR-003 ainda diz "integração" | Aberta. É o preço da imutabilidade do ADR, e a nota de cabeçalho corrige |
| **R-10** — seed malformado quebra a coleta do pytest com traceback | Aberta. Nenhum arquivo novo desta spec constrói dado no import de módulo, então a spec não piorou o caso |

## Definition of Done
- [x] Todos os requisitos com evidência medida nesta spec (REQ-1 a REQ-6)
- [x] Suíte local verde: `ruff check` · `ruff format --check` · `mypy` (backend e testes) · `pytest tests` (356 passed)
- [x] Os três riscos declarados com teste-âncora verde e falsificado: R5, R6, R9
- [ ] CI verde no PR
- [ ] PR com evidência (trace Langfuse) e `Closes #3`
- [ ] Relatório /verificar-spec anexado com veredito APROVADO
