---
spec: S-08
veredito: APROVADO COM RESSALVAS
commit: e0b5015b2a34c557e8c720fbf57ac3c50cc73929
branch: spec/s-08-deploy
data: 2026-09-01
---

# Relatório de verificação independente — S-08 (Deploy, ambiente empacotado)

| | |
|---|---|
| **Spec** | `docs/specs/S-08-producao.md` (`status: em-revisao`) |
| **Branch** | `spec/s-08-deploy` @ `e0b5015` — **6 commits** sobre `origin/main` |
| **Base** | `origin/main` @ `7896040` — é o merge-base exato; diff não inflado |
| **PR** | **não existe** no momento da verificação |
| **Escopo do diff** | 14 arquivos · +1046 / −11 — `deploy/*` (6 novos), `.dockerignore`, `app.py`, `schemas.py`, `openapi.json`, `schema.d.ts`, 2 arquivos de teste, a spec |
| **Suíte** | **1051 passed**, 0 failed, 0 error, 0 skipped, 142,5 s (`tests/unit` + `tests/security`) |
| **Lint** | `ruff check .` → *All checks passed* · `ruff format --check .` → 163 arquivos ok |
| **Typecheck** | `mypy` backend 46 arquivos · `mypy` tests 35 arquivos · `tsc -b --noEmit` — os três limpos |
| **Contrato** | regerei `openapi.json` + `schema.d.ts`: `git diff` vazio nos dois. **Sem drift** (fecha a DESC-0) |
| **Segredos** | `gitleaks v8.29.0` sobre os 201 commits com `.gitleaks.toml` do repo → *no leaks found* |
| **Ambiente** | **SUBIU** — `down` + `up -d --wait` → 5 serviços, todos healthy em **28,1 s** |
| **Evals** | **não executados** — nenhum prompt no diff; ver "Não verificável, e por quê" |
| **Achados** | 1 Alta · 1 Média · 6 Baixa |
| **Veredito** | **APROVADO COM RESSALVAS** |

---

## Enquadramento recebido

A mensagem que iniciou esta sessão continha **apenas o id da spec** (`S-08`). Nada a registrar:
nenhum resultado antecipado, nenhum arquivo apontado, nenhuma restrição de execução, nenhuma
indicação de quanto do trabalho estaria pronto. É o formato que o `CLAUDE.md`, fluxo item 4,
descreve, e é o que permite que o resto deste relatório seja sobre a entrega e não sobre a
moldura.

---

## O que este diff se propõe a fazer

Empacotar o produto num `compose` que sobe do zero: duas imagens multi-stage (`api` e `web`),
um `deploy/docker-compose.yml` com cinco serviços, um `nginx.conf` que serve as duas entradas
do frontend e faz proxy da API sob `/api/`, um `.env.example` próprio e um runbook. Mais dois
consertos de código de produto registrados como descobertas (DESC-0 e DESC-5) e um teste novo
que prende o `qdrant-client` ao minor da imagem.

---

## 1. Conformidade requisito a requisito

| Requisito | Veredito | Evidência que eu produzi |
|---|---|---|
| **REQ-1** — Dockerfiles multi-stage, duas entradas, non-root, `qdrant-client` casando com a imagem | **CONFORME** | Ambos os Dockerfiles têm `builder` + `runtime`. Duas entradas: o build falha por construção (`test -f dist/index.html && test -f dist/admin.html` na linha do `RUN`) e em runtime `GET /admin` devolve **200** com `<title>Painel — Vendinha</title>` apontando para `/assets/admin-CbHgobQh.js`. Non-root medido dentro dos contêineres: `api` → `uid=10001(vendinha)`, `nginx` → `uid=101(nginx)` **e o processo master também** (`ps -o user` na imagem `nginx-unprivileged`: `nginx 1 nginx: master process`), que é o ponto que a imagem oficial não cumpre. Pin: `qdrant/qdrant:v1.13.6` nos dois composes vs `qdrant-client>=1.13,<1.14` |
| **REQ-2** — compose com rede/volumes próprios, `restart`, healthchecks, Postgres e Qdrant sem porta publicada | **CONFORME** | `name: vendinha-deploy` → rede `vendinha-deploy_default` e volumes `vendinha-deploy_postgres-data` / `_qdrant-data`, isolados do compose da raiz (`vendinha_*`), que continua existindo na mesma máquina. `restart: unless-stopped` nos quatro serviços longevos; `restart: "no"` no `bootstrap`, que é one-shot e para o qual `unless-stopped` seria errado. Healthcheck nos quatro; todos reportaram `healthy`. Portas: `docker inspect` da stack devolve `PublishedPort: 0` para `postgres`, `qdrant` e `api`, e `0.0.0.0:8099->8080` só para o `nginx` |
| **REQ-3** — nginx serve estáticos, faz proxy da API, roteia `/admin*`, `proxy_buffering off` no chat | **CONFORME, e mais amplo que a letra** | `proxy_buffering off` está no bloco `/api/` **inteiro**, não só no chat — a nota que a spec acrescentou ao requisito descreve o que foi entregue. As três rotas de stream respondem através do prefixo: `POST /api/chat` → 200 SSE, `GET /api/eventos/sessao/{id}` → 200, `GET /api/admin/eventos` → 401 (sem token, correto). Streaming medido: eventos chegando em `+0,052s` (session), `+0,783s`, `+1,048s` (token), `+1,082s` (done) — **não em bloco**. `/admin` → 200 e `/admin/conversas` (o F5 em rota de SPA) → 200 com o HTML do painel. Ver **RS-4** sobre o que o controle negativo *não* conseguiu mostrar |
| **REQ-4** — `deploy/.env.example` com `APP_ENV`, **`API_HOST=0.0.0.0`**, `PUBLIC_BASE_URL`, `CORS_ORIGINS`, `OPERADOR_API_TOKEN` e chaves do Langfuse | **NÃO CONFORME (parcial)** | Cinco dos seis presentes. **`API_HOST` não aparece no arquivo** (`grep -n API_HOST deploy/.env.example` → vazio); ele vive em `deploy/docker-compose.yml:118`. Ver **NC-2** |
| **REQ-5** — runbook: subir do zero, hardening, backup/restore, rollback, região do Langfuse | **NÃO CONFORME (parcial)** | Os cinco tópicos estão escritos e a §8 tem o campo da região EU/US em branco esperando preenchimento, que é o que o ADR-010 endereçava. Mas **o comando de backup da §5 falha executado como está escrito**. Ver **NC-1** |
| **`riscos_cobertos: []`** | **CONFORME** | Cruzado com `docs/riscos.md` §matriz: nenhuma das linhas R1–R10 atribui spec à S-08 (R1→S-03·S-04, R2→S-04, R3→S-05, R4→S-04, R5/R6/R9→S-02, R7→S-06, R8→S-04/S-05, R10→S-11·S-04). `grep "S-08" docs/riscos.md docs/testes.md` → nenhuma ocorrência. Declarar `[]` é o correto, e o `test_deploy_pins.py` argumenta em voz alta por que não inventa um marcador |

## 2. Conformidade cenário a cenário (BDD)

| Cenário | Veredito | Evidência |
|---|---|---|
| **"o ambiente sobe do zero e atende"** | **CONFORME, com ressalva de método** | `docker compose -f deploy/docker-compose.yml down` seguido de `up -d --wait`: os cinco serviços subiram e ficaram healthy em **28,1 s**, com o `bootstrap` saindo com sucesso. `GET /` → 200, `<title>Vendinha — empório mineiro para eventos corporativos</title>`. `GET /api/health` → `{"status":"ok"}`. Streaming token a token confirmado (acima). **Ressalva:** não foi um host *limpo* — o cache de imagens do Docker estava quente e o `deploy/.env` já existia na máquina (criado pela sessão autora, anterior a mim; não o li e não o apaguei) |
| **"o banco não está exposto"** | **CONFORME** | Varredura das portas do host via `/dev/tcp`: 6333, 6334, 8000 e 8080 **fechadas**; 8099 aberta (o nginx, `HTTP_PORT` desta máquina). A 5432 responde, e **não é desta stack** — `docker inspect` mostra `PublishedPort: 0` para o serviço `postgres` do compose; é o Postgres nativo do host, documentado no ambiente |

## 3. Métricas de sucesso da spec

| Métrica | Alvo | Medido |
|---|---|---|
| Host limpo → jornada respondendo | ≤ 15 min | **NÃO VERIFICÁVEL** como escrito — não tenho host limpo. Parcial: build completo com cache quente 11,8 s; `up -d --wait` 28,1 s; jornada exercitada logo em seguida |
| `up -d --wait` até healthy | ≤ 90 s | **28,1 s** — CONFORME, com folga de 3× |
| Primeiro token do chat através do nginx | streaming preservado | **CONFORME** — 4 eventos distribuídos em 1,08 s, com um vão ocioso de 265 ms entre dois deles, maior que o custo do meu próprio laço de medição. Ver **RS-4** |
| Restore do backup | pedido aprovado antes do dump continua lá | **CONFORME**, com método adaptado — ver §5 |

---

## 4. A jornada, exercitada de ponta a ponta através do proxy

Não me limitei a `GET /health`. O que rodou de verdade, tudo pela porta do nginx e pelo prefixo:

1. **Chat com streaming** — `POST /api/chat` com uma mensagem de cliente; o agente respondeu, em
   SSE, com `session_id` no primeiro evento.
2. **Fila do operador e HITL** — havia um pedido em `aguardando_aprovacao_nf` no volume.
   Aprovei via `POST /api/operador/pedidos/{id}/aprovar` com `X-Operador-Token`, e recebi
   `{"decisao":"aprovada","operador":"revisor-s08","numero_nota":1,"chave_da_nota":"3126..."}`.
   A emissão de NF atravessou o proxy inteira. **O token nunca passou pelo meu contexto:** rodei
   o `urllib` de dentro do contêiner da `api`, lendo `os.environ["OPERADOR_API_TOKEN"]`, e o
   `deploy/.env` continua não lido.
3. **A DESC-5, reproduzida nos dois sentidos.** A página de checkout mock servida em
   `/api/pagamento/mock/{id}` traz `<form method='post' action='{id}/confirmar'>` — relativo. O
   POST no caminho que o navegador resolve daí → **200**. O POST no caminho que a versão
   anterior gerava (`/pagamento/mock/{id}/confirmar`, na raiz do host) → **405**, exatamente o
   sintoma descrito. Confirmei a origem no histórico: o `git worktree` em `79405b1` tem
   `action='/pagamento/mock/...'`.
4. **`/admin` não é mais ambíguo (DESC-1).** `/admin/conversas` → SPA (200, HTML do painel);
   `/api/admin/pedidos` → API (401 sem token, 200 com). A colisão está resolvida, e sem tocar no
   backend — o `openapi.json` regerado não mudou.

### O nginx sobrevive à API fora do ar (o que `2f86398` afirma)

Medido, porque é a única afirmação do diff que descreve um comportamento de falha:

| Situação | `GET /` | `GET /admin` | `GET /api/health` |
|---|---|---|---|
| API parada, nginx já de pé | 200 | 200 | 502 |
| API parada, **nginx reiniciado do zero** | 200 | — | 502 |

Log do nginx no segundo caso: `[error] api could not be resolved (3: Host not found)` — um erro
por requisição, e o processo continua servindo. Sem o `resolver` + variável, seria
`[emerg] host not found in upstream` na subida e o contêiner em loop de restart. A afirmação se
sustenta. Ver **RS-5** para o que ela ainda não cobre.

---

## 5. Ensaios cronometrados: backup, restore e rollback

**Backup — o comando do runbook falha.** Ver **NC-1**. Com a citação corrigida (aspas simples,
expansão dentro do contêiner) o dump saiu em **0,573 s** / 142.845 bytes.

**Restore — passou, com método adaptado.** O runbook manda restaurar por cima do banco vivo. A
etapa destrutiva que isso exigiria (`truncate` das tabelas de pedido) foi recusada pelo
classificador de permissões desta sessão, então ensaiei de forma não destrutiva e igualmente
conclusiva: `createdb ensaio_restore` → `pg_restore --clean --if-exists` do dump para dentro dele
(**0,823 s**) → contagem. O banco restaurado saiu com `1|1|1|65` (pedidos, aprovações, notas,
produtos), idêntico à origem, e a junção mostrou o pedido que eu tinha acabado de aprovar:

```
d7f44ff3ed8f455ba537bbf32c73fdd7 | nota_emitida | revisor-s08 | 1
```

**O pedido aprovado antes do dump continua lá — a métrica da spec fecha.** O banco de ensaio foi
removido (`dropdb`) e `pg_database` voltou às quatro entradas originais.

**Rollback — passou.** `git worktree` em `79405b1`, `docker build -f deploy/api.Dockerfile` →
**1,657 s** com cache quente, e a imagem reconstruída carrega o código antigo (verificado:
`action='/pagamento/mock/...'` dentro dela). O mecanismo da §6 — voltar o código e reconstruir —
funciona. Imagem de ensaio e worktree removidas.

---

## 6. Leitura dos testes-âncora (o que eles afirmam provar)

### `tests/unit/test_deploy_pins.py` (novo)

**`test_the_qdrant_client_is_pinned_to_the_minor_of_the_image` — afirma comportamento, e morde.**
Ele lê dois artefatos por caminhos independentes (regex sobre o YAML do compose, `tomllib` sobre
o `pyproject.toml`) e compara. Não há conta compartilhada com a implementação, então não pode
passar por construção: se alguém subir a imagem para `v1.14.x` sem tocar no `pyproject`, o piso
deixa de casar e a primeira asserção falha; se alguém afrouxar o teto, a segunda falha. Cobre a
**fiação** — são os arquivos que de fato sobem, não uma constante duplicada. Fecha a RS-6 da
verificação da S-03, que era um acoplamento mantido só por comentário. É o teste certo.

**`test_every_compose_pins_the_same_qdrant_image` — uma das duas parametrizações é tautológica.**
Ver **RS-1**.

**Vacuidade:** nenhuma das duas funções itera sobre coleção possivelmente vazia sem asserção — o
`assert achados` e o `assert len(linhas) == 1` fecham essa porta explicitamente, com mensagem.

### `tests/unit/test_payment_webhook.py::test_the_mock_page_posts_to_a_relative_path…` (novo)

**Afirma comportamento.** A primeira asserção é quase uma transcrição do literal que o código
emite — sozinha, ela seria fraca. A segunda, `assert "action='/" not in pagina.text`, é a que
carrega a **regra** ("nunca absoluto") e é independente de como o caminho relativo é montado:
qualquer regressão para caminho absoluto a derruba, inclusive uma que não seja
`/pagamento/mock/...`. É essa asserção que faz o teste valer.

**Não passa por vacuidade:** `pagina.text` é o HTML de uma resposta 200 real do `TestClient` — se
viesse vazio, a primeira asserção falharia antes da segunda.

**Fiação:** cobre a rota via `TestClient`, ou seja, o handler montado no app, não a função
isolada. Não cobre a camada do nginx — mas essa metade eu medi à mão (§4, item 3): 200 no
relativo, 405 no absoluto.

**`@pytest.mark.risco("R8")`:** consistente com o arquivo, que já tem 13 testes marcados R8 e é
âncora declarada da R8 em `docs/testes.md` §2. Não é marcador inflado.

---

## 7. Invariantes globais

| Invariante | Resultado |
|---|---|
| **Escopo** — o "Fora de escopo" foi respeitado? | **SIM.** Nada de TLS, DNS, domínio, CI/CD, registry, múltiplos ambientes, HA ou IaC no diff. Nenhum workflow novo em `.github/`. As três dívidas reetiquetadas **não** foram implementadas: o painel continua com `X-Operador-Token` em `sessionStorage`, `GET /config` continua aberto, o barramento continua in-process — o diff não toca nenhum desses arquivos |
| **Segredo / CPF / CNPJ / certificado no diff** | **LIMPO.** `gitleaks` sobre os 201 commits: *no leaks found*. Varredura manual do diff por máscara de CPF, de CNPJ, `sk-*`, `pk-lf-`, `sk-lf-` e chave de 44 dígitos: zero. `deploy/.env.example` só tem valores não-secretos (`HTTP_PORT`, `APP_ENV`, `LOG_LEVEL`, `PUBLIC_BASE_URL`, `POSTGRES_USER`, `POSTGRES_DB`, `NF_EMITTER`); todos os campos de credencial estão vazios. Verifiquei também **dentro das imagens**: nenhum `.env` em `/app` nem em `/usr/share/nginx/html`, e o `**/.env` do `.dockerignore` é o que garante isso |
| **PII mascarada** | **SEM REGRESSÃO** — o diff não toca instrumentação. `deploy/RUNBOOK.md` §8 registra corretamente que o que torna a nuvem aceitável é o mascaramento na origem (ADR-007) |
| **Fronteira de permissão de subagents** | **INTOCADA** — nenhum arquivo de subagent no diff |
| **`riscos_cobertos` × matriz × arquivos-âncora** | **CONFORME** — `[]` é o correto (§1). Os arquivos-âncora de todas as linhas da matriz continuam verdes: 1051 passed, 0 failed |
| **Bundle do frontend sem endereço de máquina de desenvolvimento** | **CONFORME** — `grep localhost:8000` nos assets da imagem `vendinha-web:local` → zero. `"/api"` presente no chunk compartilhado. É a falha que o `web.Dockerfile` descreve no topo, e ela não aconteceu |

---

## 8. As "Descobertas", julgadas como mudança de escopo

| # | O que é | Julgamento |
|---|---|---|
| **DESC-0** | Frase imprecisa em `schemas.py` citando "(S-08)", com o custo de regerar contrato | **Descoberta legítima e bem resolvida.** É dívida herdada do replanejamento, o custo (drift de contrato) justifica agrupar aqui, e a regeração está no diff e sem drift. Registrada com decisão declarada |
| **DESC-1** | `/admin/*` colide entre SPA e API numa origem só; resolvido com prefixo `/api` no nginx | **Descoberta legítima, e do tipo que só aparece no ambiente empacotado.** É desenho novo, foi declarado como tal, e a resolução respeita a precedência: não tocou no backend, não mudou o `openapi.json`, não destravou nenhum normativo. A alternativa recusada está registrada. Exemplar |
| **DESC-2** | `PUBLIC_BASE_URL` passa a terminar em `/api` | **Consequência, não escopo novo.** Documentada em três lugares (`.env.example`, `nginx.conf`, RUNBOOK §7), o que é proporcional a uma falha que é silenciosa e status 200 |
| **DESC-3** | O `bootstrap` exige `OPENAI_API_KEY` para o ambiente **subir** | **Descoberta legítima, e a decisão de não consertar está certa.** O conserto seria mudar `ingest.py`, que é código de produto fora do escopo. Registrada no runbook §7 e §9. Medida, não presumida, e a medição está no texto |
| **DESC-4** | O `.dockerignore` não pode excluir `deploy/` | **Registro de tentativa, não mudança de escopo.** Bem colocado: o argumento ("reincluir um arquivo de um diretório excluído quebra quando aparecer o segundo") é o tipo de coisa que se re-descobre caro |
| **DESC-5** | O botão do checkout mock postava na raiz do host | **Conserto correto, registro discutível.** Ver **RS-3** |

**Emenda de ADR:** o ADR-008 foi **emendado por nota de cabeçalho** (`Status: aceito · Revisto em
2026-08-31`) mais uma seção "Revisão de 2026-08-31" que declara o que sai e o que fica. **O corpo
da decisão original de 2026-08-03 está preservado intacto.** É a forma aceita — não é reescrita
de corpo. O argumento de por que emendar em vez de substituir ("a resposta anterior nunca chegou
a existir em código") é verificável e verdadeiro: não há nada de `deploy/` em `origin/main`.

---

## 9. Achados

### NC-1 · **ALTA** · REQ-5: o comando de backup do RUNBOOK §5 falha executado como está escrito

O runbook manda:

```bash
docker compose -f deploy/docker-compose.yml exec -T postgres \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom \
  > backup-$(date +%F-%H%M).dump
```

`$POSTGRES_USER` e `$POSTGRES_DB` são expandidos pelo shell **do host**, onde não existem: eles
moram em `deploy/.env`, e o runbook nunca manda exportá-los. Executei verbatim, como faria quem
só tem este documento:

```
pg_dump: error: connection to server on socket "/var/run/postgresql/.s.PGSQL.5432" failed:
FATAL:  role "root" does not exist
exit=1
-rw-r--r--  0 backup-runbook.dump
```

Dois motivos para isto ser Alta e não Média:

1. **Falha para o lado silencioso.** O redirecionamento `>` cria o arquivo *antes* de o comando
   rodar, então o operador fica com um `.dump` de **0 byte**. Automatizado no `cron` — que é o
   que o próprio runbook sugere duas linhas abaixo — isso produz uma pasta de backups que
   *parece* uma pasta de backups. O documento diz, na mesma seção, *"backup nunca testado é
   backup que não existe"*; o comando dele é o exemplo.
2. **É exatamente o que a spec pediu para eu testar.** *"Subir o ambiente do runbook, sem usar
   conhecimento desta sessão. Runbook que só funciona para quem o escreveu não passou."* Quem
   escreveu tinha as variáveis no shell; quem lê, não.

O comando de **restore** da mesma seção tem o mesmo defeito, pelo mesmo motivo.

O conserto é a citação: aspas simples, para a expansão acontecer dentro do contêiner, onde o
serviço `postgres` já define as três variáveis. Verifiquei que funciona (0,573 s, 142.845 bytes):

```bash
docker compose -f deploy/docker-compose.yml exec -T postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' > backup-$(date +%F-%H%M).dump
```

### NC-2 · **MÉDIA** · REQ-4: `API_HOST=0.0.0.0` não está em `deploy/.env.example`

O REQ-4 nomeia o campo literalmente, e com ênfase: *"`API_HOST=0.0.0.0` (é aqui que `0.0.0.0` é
a resposta certa — ver S-02 D-8)"*. Ele não está no arquivo; está em
`deploy/docker-compose.yml:118`. O comportamento em runtime está correto — o nginx alcança a API,
logo ela escuta em `0.0.0.0` —, mas o requisito é sobre **onde a variável é declarada**, e ela
não está onde foi pedida.

> **Ressalva sobre a spec, em linha própria:** a escolha entregue é provavelmente melhor que a
> pedida. `environment:` tem precedência sobre `env_file:` no compose, então com `API_HOST` no
> compose um operador **não consegue** quebrar a subida copiando `API_HOST=127.0.0.1` do
> `.env.example` da raiz — e essa é uma confusão plausível, já que os dois arquivos são lidos
> lado a lado. O cabeçalho do `deploy/.env.example` até declara a regra que produz essa escolha
> ("`DATABASE_URL` e `QDRANT_URL` NÃO estão aqui: o compose as monta"), só não a estendeu ao
> `API_HOST` por escrito. **Se a decisão for manter como está, o conserto é emendar o REQ-4, não
> mexer no código** — e uma linha no `.env.example` explicando por que `API_HOST` não aparece ali
> apesar de ser a diferença mais famosa entre local e deploy.

### RS-1 · Baixa · Uma das duas parametrizações de `test_every_compose_pins_the_same_qdrant_image` é `assert x == x`

```python
@pytest.mark.parametrize("compose", COMPOSES, ids=lambda caminho: caminho.parent.name)
def test_every_compose_pins_the_same_qdrant_image(compose: Path) -> None:
    assert _minor_da_imagem(compose) == _minor_da_imagem(COMPOSES[0])
```

`COMPOSES[0]` é o compose da raiz, e ele também é um dos casos parametrizados. Nesse caso a
asserção compara o arquivo consigo mesmo e passa por construção. O relatório do pytest mostra
**dois** casos com ids distintos, sugerindo duas verificações independentes onde existe uma.

Não é grave — a asserção que morde de verdade está no outro teste, que cruza compose contra
`pyproject.toml`, e o que sobra aqui (o caso `deploy`) é real. Mas é a forma exata que a leitura
de testes procura: fixture parametrizada em que um elemento não prova nada. Uma referência
constante fora da lista parametrizada resolve.

### RS-2 · Baixa · `test_deploy_pins.py` não declara `R#`, e `docs/testes.md` §4 manda declarar

`docs/testes.md` §4, primeira linha: *"Declare o `R#` na primeira linha do docstring."* O arquivo
novo não declara, e argumenta bem por quê — não há risco da matriz para declarar, e um marcador
falso inverteria o mapa de §2. Concordo com o argumento.

O achado é de precedência, não de mérito: `docs/testes.md` é normativo e está **acima** da spec
na ordem. Uma exceção a um normativo não se cria por prosa dentro do arquivo que a exerce; ela
se cria emendando o normativo. Uma linha em §4 — *"testes de invariante de infraestrutura, que
não fecham risco, declaram a ausência e o motivo no docstring do módulo"* — transforma um desvio
em regra e resolve o mesmo caso para a próxima spec.

### RS-3 · Baixa · A DESC-5 reivindica exceção a um guardrail do `CLAUDE.md` por autoridade própria

O `CLAUDE.md` (precedência 1) é categórico: *"NUNCA implementar fora do escopo da spec ativa. Se
descobrir necessidade nova: anotar na seção 'Descobertas' da spec e **parar para decisão do
PO**."* A DESC-5 é a única descoberta desta spec cujo título é literalmente *"Por que isto foi
consertado aqui **em vez de** virar decisão do PO"*. A DESC-1 e a DESC-3 dizem "decisão do PO";
esta não diz.

**O conserto em si está certo e eu o validei nos dois sentidos** (§4, item 3) — não estou pedindo
para desfazê-lo. Dois pontos sobre o registro:

- A DESC-5 diz que o texto do PO encontrou o defeito (*"Encontrado pelo PO percorrendo a jornada
  no ambiente empacotado"*), o que na prática coloca o PO no circuito. Se houve decisão, a frase
  que falta é a mesma das outras duas descobertas, e ela custa uma linha.
- A justificativa técnica está mal ancorada: *"é a REQ-3 não estando cumprida"*. A REQ-3 é a
  configuração do nginx, e ela **estava** cumprida — o buffering, o `try_files`, o proxy, tudo.
  O que o defeito quebrava era o **Objetivo** da spec e o primeiro cenário BDD ("o ambiente sobe
  do zero e **atende**"). Ancorar num requisito que não era o violado enfraquece um argumento
  que, ancorado no lugar certo, é forte.

### RS-4 · Baixa · A REQ-3 é declarada "a falha mais provável desta spec inteira", e o controle negativo não reproduz

A spec e o `nginx.conf` afirmam que sem `proxy_buffering off` o SSE "chega em bloco no fim e o
streaming morre silenciosamente". Tentei produzir esse estado, porque uma afirmação de risco que
ninguém mediu vira folclore de repositório.

Subi dois nginx de controle na mesma rede do compose, contra a **mesma** API:

| Configuração | Chegada dos eventos |
|---|---|
| `deploy/nginx.conf` (buffering off) | +0,052 / +0,783 / +1,048 / +1,082 s |
| controle: `proxy_buffering on` + `proxy_http_version 1.1` | +0,049 / +0,761 / +0,793 / +0,823 / +1,011 / +1,048 s |
| controle: nginx **100 % default** (HTTP/1.0 ao upstream, buffering on) | +0,055 / +0,958 / +1,203 / +1,236 s |

**Os três transmitiram evento a evento.** Não consegui construir a falha. A explicação provável é
o tamanho da resposta: nesta jornada o agente devolve poucos kilobytes e o nginx repassa cada
buffer assim que o preenche, então o efeito só apareceria com respostas grandes ou cliente lento.

Isto **não** é um achado contra a entrega: `proxy_buffering off` está certo, é barato, e é a
diretiva que torna o comportamento independente do tamanho da resposta em vez de dependente dele.
O achado é sobre a **calibração da prosa**: a spec ordena ao revisor conferir esse ponto como o
mais provável de falhar, e a medição diz que ele não era. Registro para que a próxima spec que
copiar essa frase saiba que ela nunca foi observada acontecendo neste projeto.

### RS-5 · Baixa · No cold start, o `depends_on: service_healthy` do nginx desfaz a "falha parcial" que o `resolver` conquistou

O comentário do `nginx.conf` defende a resolução em runtime dizendo que ela troca falha total por
falha parcial, e que *"um `depends_on` esconde isso na PRIMEIRA subida"*. Correto — e o compose
**mantém** `depends_on: api: condition: service_healthy` no nginx.

A consequência: numa subida a frio em que a `api` nunca fica healthy — e a DESC-3 diz que a causa
mais provável de primeira subida falha, uma `OPENAI_API_KEY` ausente, produz exatamente isso, via
`bootstrap` → `service_completed_successfully` → `api` nunca inicia — o nginx **também** não sobe,
e o operador não recebe nem a landing, que é estática e não depende de nada. A propriedade que o
`resolver` comprou só está disponível depois que o ambiente subiu certo pelo menos uma vez.

**Medido para o caso já-de-pé** (§4: 200/200/502, e `restart nginx` com a API fora também
funciona, porque `restart` não honra `depends_on`). **Não medido para o cold start** — exigiria
quebrar deliberadamente o `bootstrap`; a conclusão é leitura do compose, e está declarada como
tal. Se a intenção é que a landing sempre suba, o `depends_on` do nginx deveria ser
`service_started` (ou sair).

### RS-6 · Baixa · O RUNBOOK §5 nunca manda parar a `api` antes do restore

A sequência da §5 é `up -d --wait postgres` → `pg_restore --clean --if-exists` → `up -d --wait`.
Ela pressupõe, sem dizer, que a stack esteja parada: se a `api` estiver de pé e conectada, o
`--clean` vai tentar derrubar tabelas debaixo de uma aplicação viva. **Não medi** — a etapa
destrutiva foi recusada pelo classificador de permissões desta sessão —, e registro como leitura,
não como observação. Uma linha `docker compose ... stop api` antes, e `start api` depois, fecha.

### RS-7 · Baixa · As três dívidas foram reetiquetadas em uma direção só

A spec pede ao revisor: *"Cruzar o 'Fora de escopo' desta spec com o ADR-015 e a S-07: as três
dívidas devem estar reetiquetadas aqui."* Estão — a tabela existe e é boa. Mas o cruzamento
**inverso** não foi feito, e é o que um leitor percorre na prática:

| Documento | Precedência | O que ainda diz |
|---|---|---|
| `docs/adr/ADR-015…:121` | 5 (ADR) | *"fica registrado como dívida explícita da **S-08**"* |
| `docs/adr/ADR-015…:129` | 5 (ADR) | *"antes de a S-08 resolver autenticação"* |
| `docs/specs/S-07…:103` | 6 (spec) | *"é dívida da S-08"* |
| `docs/specs/S-07…:107` | 6 (spec) | *"`LISTEN/NOTIFY` fica para a S-08"* |
| `docs/specs/S-07…:230-232` | 6 (spec) | *"no **host público da S-08**"* — e a S-08 deixou de ser host público |

Pela ordem de precedência deste relatório, o ADR-015 está **acima** da spec S-08. Quem abrir o
ADR-015 vai concluir que a S-08 deve autenticação, e a S-08 diz que não deve. O ADR-008 revisto
resolve o conflito no texto dele, mas o ADR-015 não carrega nota nenhuma apontando para lá.

É a **mesma classe de defeito que a DESC-0 consertou** — um ponteiro pendurado para "S-08" num
documento que a mudança de escopo tornou falso. A DESC-0 consertou o ponteiro em `schemas.py`, que
custava caro (regerar contrato); os que custam uma linha ficaram. Nota de cabeçalho no ADR-015
("Revisto em … — as dívidas endereçadas à S-08 passam a valer quando o host for público, ver
ADR-008") resolve os dois primeiros; os da S-07 são spec fechada e podem ficar, desde que o
ADR — que é o normativo — aponte para o lugar certo.

---

## 10. Não verificável, e por quê

| Item | Motivo |
|---|---|
| **Host limpo em ≤ 15 min** | Não tenho host limpo. Cache de imagens quente e `deploy/.env` pré-existente. O que dá para afirmar: com cache quente, build 11,8 s + subida 28,1 s |
| **Evals** | Não rodados. Nenhum prompt no diff — as únicas mudanças em `backend/` são um `description` de campo Pydantic e o `action` de um formulário HTML. `CLAUDE.md` exige evals para mudança de prompt, e não houve |
| **`ufw` e SSH por chave (RUNBOOK §4)** | Windows. Os comandos são padrão e corretos para Ubuntu/Debian, mas não executei nenhum. O que **verifiquei** da §4 são as duas linhas testáveis aqui: `exec api id` → `uid=10001(vendinha)` e `exec nginx id` → `uid=101(nginx)`, ambas batendo com o que o documento promete |
| **Restore por cima do banco vivo** | Etapa destrutiva recusada pelo classificador de permissões. Ensaiei em banco separado; ver §5 e RS-6 |
| **Cold start com `bootstrap` falhando** | Exigiria invalidar deliberadamente uma credencial no `deploy/.env`, que não posso ler nem editar. Ver RS-5 |
| **Navegador** | Não executado. Toda a jornada foi exercitada por HTTP, incluindo SSE com cronometragem por evento |

---

## 11. Estado do repositório

```
git status --short   (ANTES)   →  (vazio)
git status --short   (DEPOIS)  →  (vazio)
HEAD  e0b5015b2a34c557e8c720fbf57ac3c50cc73929   branch  spec/s-08-deploy
```

**O que eu criei e desfiz:** contêineres de controle `control-nginx` e `control2` (removidos);
imagem `vendinha-api:rollback-ensaio` (removida); worktree em scratchpad no commit `79405b1`
(removida, `git worktree list` volta a ter só a principal); banco `ensaio_restore` (removido,
`pg_database` de volta a `postgres/template0/template1/vendinha`). Dumps e scripts ficaram no
scratchpad da sessão, fora do repositório.

**Um artefato que apareceu e não consegui atribuir:** um `uv.lock` de 300 linhas na raiz do
repositório (`attrs`, `jsonschema`, `pytest`), **ausente** no `git status` inicial e diferente do
`backend/uv.lock`. Como o status inicial estava limpo, ele nasceu durante esta sessão; removi.
Registro porque ele **não é ignorado pelo git** — aparecia como `??` — e um `git add .` distraído
o levaria para um commit.

**O que eu mudei e NÃO consigo desfazer:** exercitei o HITL de verdade no volume
`vendinha-deploy_postgres-data`. O pedido `d7f44ff3…` saiu de `aguardando_aprovacao_nf` para
`nota_emitida`, com `operador = "revisor-s08"` e nota nº 1. É dado de volume local de
desenvolvimento, não do repositório, e o caminho de reset já existe: `bash scripts/limpar-demo.sh`
(zera conversas, pedidos e notas, preserva catálogo e config) ou
`docker compose -f deploy/docker-compose.yml down -v`. **Não rodei nenhum dos dois**, para não
apagar estado que não é meu.

**Contêineres:** deixei os cinco em `Exited`, que é como os encontrei (`docker compose stop`, não
`down -v` — os volumes estão intactos).

---

## Veredito: **APROVADO COM RESSALVAS**

**Por que não REPROVADO.** Todo o núcleo da spec foi medido funcionando, não inferido. O compose
sobe do zero em 28 s com os cinco serviços healthy; Postgres e Qdrant não publicam porta e a
varredura confirma; os dois contêineres rodam non-root, inclusive o processo master do nginx; o
SSE atravessa o proxy chegando evento a evento; a colisão `/admin` que a DESC-1 descobriu está
resolvida sem tocar no backend e sem drift de contrato; e a jornada foi ao fim pelo prefixo —
chat com streaming, aprovação de nota fiscal com token de operador, emissão de NF e o botão de
pagamento que a DESC-5 consertou, com o defeito antigo reproduzido a partir do histórico para
confirmar que o conserto é real. O teste que prende o `qdrant-client` à imagem afirma
comportamento e morde. Nenhum requisito central se sustenta sobre promessa.

**Por que não APROVADO.** Dois requisitos não fecham pela letra, e um deles falha justamente no
eixo que a spec encarregou o revisor de testar. A REQ-5 entrega um runbook cujo comando de backup
**não funciona** para quem só tem o runbook — e falha produzindo um arquivo de 0 byte, que é a
forma mais cara de falhar num procedimento de backup. A REQ-4 pede um campo nominalmente e ele
não está lá. Some-se a isso o cruzamento de dívidas feito numa direção só, deixando o ADR-015 —
que tem precedência sobre a spec — afirmando que a S-08 deve autenticação de painel.

### Condições de fechamento, em ordem de importância

1. **Corrigir os comandos de backup e restore do `RUNBOOK.md` §5** para que a expansão das
   variáveis aconteça dentro do contêiner (`sh -c '…'` com aspas simples). É o achado ALTA, e é o
   que separa "documentado" de "funciona". Bônus barato no mesmo lugar: um `set -o pipefail` ou
   uma checagem de tamanho do dump, para que a falha nunca mais deixe um arquivo vazio para trás.
2. **Resolver a REQ-4**, das duas maneiras possíveis, mas explicitamente: colocar
   `API_HOST=0.0.0.0` em `deploy/.env.example`, **ou** emendar o REQ-4 registrando que a variável
   vive no compose e por quê (precedência de `environment:` sobre `env_file:`). O que não pode
   ficar é a spec dizendo uma coisa e o arquivo outra.
3. **Nota de cabeçalho no ADR-015** reetiquetando as dívidas para "quando o host for público",
   com ponteiro para a revisão do ADR-008. Corpo preservado — a mesma forma que o ADR-008 usou.
4. **Fechar a DESC-5 no registro**: a linha "decisão do PO" que as DESC-1 e DESC-3 têm, e trocar
   a âncora de "REQ-3 não cumprida" para o Objetivo / primeiro cenário BDD, que é o que o defeito
   de fato violava.
5. **`test_every_compose_pins_the_same_qdrant_image`**: comparar contra uma referência fora da
   lista parametrizada, para que os dois casos do relatório do pytest sejam dois casos.
6. **Registrar para as specs seguintes** (não bloqueia o PR): o `depends_on: service_healthy` do
   nginx e a ausência de `stop api` no restore (RS-5, RS-6), e a calibração da REQ-3 (RS-4) — a
   falha de buffering que a spec chama de mais provável não foi reproduzível neste projeto.
7. **Emendar `docs/testes.md` §4** para acomodar testes de invariante de infraestrutura sem `R#`,
   em vez de deixar a exceção morar na prosa do teste.

---

*Verificação executada em 2026-09-01 sobre `spec/s-08-deploy` @ `e0b5015`, em sessão sem contexto
da implementação. Ambiente: Windows 11, Docker 27.2.0 / Compose v2.29.2, `backend/.venv`.*
