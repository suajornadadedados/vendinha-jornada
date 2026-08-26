# Relatório de verificação independente — S-00 (Fundação do repositório)

| | |
|---|---|
| **Spec** | `docs/specs/S-00-fundacao.md` (`status: em-revisao`) |
| **Branch** | `spec/s-00-fundacao` @ `e1ece60` |
| **Base** | `main` @ `a4d69d2` |
| **PR** | [#11](https://github.com/suajornadadedados/vendinha-jornada/pull/11) — **estado no momento da verificação: MERGED** |
| **Sessão** | revisora, sem acesso ao histórico da sessão autora |
| **Data** | 2026-08-26 12:45 UTC |
| **Ambiente** | Windows 11, Docker 27.2.0 / Compose v2.29.2, Python 3.12.5, uv 0.6.9, Node v22.16.0 |
| **Veredito** | **APROVADO COM RESSALVAS** |

---

## 1. Resumo

A entrega técnica é sólida e, num ponto raro, honesta: as descobertas D-10, D-11 e D-12
revelam que **o CI deste repositório nunca executou** desde o `first commit` — e a correção foi
verificada por mim de forma independente, inclusive falsificando a causa raiz. O teste novo
(REQ-7) falsifica de verdade, o `docker compose` sobe em segundos com healthchecks que
significam alguma coisa, e o scanner de segredo passou a escanear.

Mas a spec começa dizendo "**nascer com o gate antes do conteúdo: repo protegido**", e o repo
**não está protegido**. Verifiquei na API: zero rulesets, nenhum required status check,
`enforce_admins: false`, merge commit e rebase liberados. O REQ-4 está declarado como pendente
do PO — o que é legítimo e está escrito —, mas o efeito prático apareceu no mesmo dia: o PR #11
foi mergeado **como merge commit** (dois pais, `627b905`), **sem relatório de verificação**,
**sem nenhum check obrigatório** e **antes** desta revisão. É exatamente o cenário que a D-10
descreve — "nada bloqueia o merge" — só que agora com o CI funcionando e ainda assim ignorado.

Além disso, o próprio PR que renomeou `commitlint.config.js` → `.cjs` deixou três referências
mortas ao nome antigo (uma delas **introduzida por ele mesmo** no `CLAUDE.md`), e o
`docs/workshop/github-setup.md` §4 — o documento que o PO vai seguir para fechar o REQ-4 —
**continua ensinando `if: hashFiles(...)` no nível do job**, isto é, exatamente a construção que
a D-10 identificou como causa do startup_failure e removeu do `ci.yml`.

**6 CONFORME · 1 NÃO CONFORME · 0 NÃO VERIFICÁVEL** (requisitos), com 5 não-conformidades
adicionais de processo/documentação e 11 ressalvas.

---

## 2. Conformidade requisito a requisito

| # | Requisito | Status | Evidência que EU produzi |
|---|---|---|---|
| REQ-1 | Harness completo versionado | **CONFORME** | `.claude/commands/` (4 rituais), `.claude/skills/` (79 arquivos, drift OK), `.github/CODEOWNERS` + `PULL_REQUEST_TEMPLATE.md`, `docs/templates/` (2), 10 ADRs, docs normativas completas. `vendor-skills.sh --check` e `gen-skills-doc.sh --check` saem 0. Placeholder `@SEU-USUARIO-GITHUB` do CODEOWNERS substituído por `@caio-moliveira` nesta branch. |
| REQ-2 | `docker compose up` sobe Postgres e Qdrant com healthchecks verdes; Langfuse por env | **CONFORME** | Clone limpo + `cp .env.example .env` + `docker compose up -d --wait` → **exit 0**, ambos `(healthy)`. Confirmado à parte: `GET /readyz` do Qdrant → **200**; `pg_isready -U vendinha -d vendinha` → *accepting connections*. Nenhum contêiner de observabilidade; `LANGFUSE_*` só no `.env.example`. Healthcheck do Qdrant em `CMD`+`bash` (D-7) funciona. |
| REQ-3 | CI com `commitlint`, `lint`, `typecheck`, `test` verdes | **CONFORME** | Run [32968758645](https://github.com/suajornadadedados/vendinha-jornada/actions/runs/32968758645): `commitlint` pass 22s, `detect` pass 6s, `lint` pass 9s, `secrets` pass 9s, `skills-drift` pass 10s, `test` pass 12s, `typecheck` pass 6s, `evals` skipping. Rodei `actionlint` no `ci.yml`: **exit 0**. Reproduzi localmente: `ruff check .` (All checks passed), `ruff format --check .` (49 files), `uv run mypy .` (Success), `commitlint --from a4d69d2 --to HEAD` (0 problems em 12 commits). |
| REQ-4 | `main` protegida: PR obrigatório, checks obrigatórios, squash-only | **NÃO CONFORME** | `GET /repos/.../rulesets` → `[]`. `GET /branches/main/protection` → **não existe a chave `required_status_checks`**; `required_approving_review_count: 0`; `enforce_admins: false`; `required_linear_history: false`. `GET /repos/...` → `allow_merge_commit: true`, `allow_rebase_merge: true`, `delete_branch_on_merge: false`. Nenhuma das linhas da tabela do `github-setup.md` §3 está aplicada, exceto `allow_force_pushes: false` / `allow_deletions: false`. |
| REQ-5 | `.env.example` exaustivo e comentado; `Makefile` com `up`, `test`, `lint`, `evals` | **CONFORME (com ressalva)** | `.env.example`: 8 blocos, cada variável marcada com a spec que a exige, **todos os campos de segredo vazios**. `Makefile`: `up`, `down`, `logs`, `test`, `lint`, `format`, `typecheck`, `evals-check`, `evals`, `hooks`, `help`. Ver R-3 (URLs não seguem as variáveis de porta) e R-6 (`make evals` falha por design, D-4). |
| REQ-6 | Cada spec com issue linkada no frontmatter; issue é ponteiro, não cópia | **CONFORME** | 10/10 specs com `issue:` de `#1` a `#10`, batendo com títulos das issues reais no GitHub. Li os corpos de #1, #2, #5, #7 e #10: nenhum copia requisito, task, BDD ou métrica — todos dizem "Este issue é **ponteiro, não cópia**" e apontam para a spec. Convenção registrada no `CLAUDE.md`, item 1 do fluxo. |
| REQ-7 | Suíte coleta ao menos um teste real (rastreabilidade dos casos de eval) | **CONFORME** | `bash scripts/run-tests.sh` em clone limpo → **29 passed**, exit 0. Falsificado: quebrei `golden-001` (id, família, risco `R42`, spec `S-99`) e as **quatro** verificações reprovaram de forma independente. Falsificado o guarda de suíte vazia: `run-tests.sh tests/security` com `backend/` presente → **exit 1** com a mensagem correta. |

### Não-conformidades adicionais (fora da tabela de requisitos)

| # | Achado | Gravidade |
|---|---|---|
| **NC-1** | REQ-4 não implementado — detalhado acima. O objetivo declarado da spec ("repo protegido") não foi atingido. | Alta |
| **NC-2** | **PR #11 foi mergeado em 2026-08-26T12:30:58Z, antes deste relatório existir.** `CLAUDE.md` §Fluxo item 5 e o `verificar-spec.md` dizem "sessão NOVA roda `/verificar-spec` **antes do merge**". A DoD da própria spec exige "Relatório /verificar-spec anexado com veredito APROVADO" — que não podia existir. `reviews: []`, `comments: []`. | Alta |
| **NC-3** | **O merge foi merge commit, não squash.** `git rev-list --parents -n 1 627b905` retorna dois pais. `CLAUDE.md` item 6 e `github-setup.md` §3 exigem squash-only; a issue #1 diz literalmente "Squash merge com veredito APROVADO → este issue fecha automaticamente". A `main` agora carrega os 12 commits de task, quebrando o desenho "main conta a história em nível de spec". | Alta |
| **NC-4** | **Referência morta introduzida pelo próprio PR.** A D-11 renomeou `commitlint.config.js` → `commitlint.config.cjs`, e o mesmo PR **adicionou** ao `CLAUDE.md:40` a frase "a lista de tipos é a de `commitlint.config.js`" — arquivo que não existe mais. Também ficaram desatualizados `docs/arquitetura.md:26` e `docs/requisitos.md:102` (pré-existentes, mas quebrados *por* este PR). | Média |
| **NC-5** | **`docs/workshop/github-setup.md` §4 ensina o bug que a spec diz ter corrigido.** O texto ainda afirma que `typecheck` e `evals` "usam `if: hashFiles('backend/pyproject.toml') != ''`" — a construção que a D-10 provou quebrar o parse do workflow inteiro, e que foi substituída pelo job `detect`. O PR editou §2 deste mesmo arquivo e não tocou em §4. É o documento que o PO vai seguir para fechar o REQ-4. | Média |

---

## 3. Cenário BDD

```gherkin
Cenário: quickstart em máquina limpa
  Dado um clone limpo do repositório com Docker instalado
  Quando executo "cp .env.example .env" e "docker compose up -d"
  Então todos os serviços ficam healthy em até 5 minutos
```

**CONFORME.** Executado literalmente, num diretório novo, com `git clone --config
core.autocrlf=true` (o default do Git for Windows — o pior caso para a D-9):

```
 Container vendinha-verify-postgres-1  Healthy
 Container vendinha-verify-qdrant-1    Healthy
exit=0
ELAPSED_MS=6448
```

Verificações adicionais no mesmo clone:

- **D-9 falsificada em ambos os sentidos:** `Makefile`, `scripts/*.sh` e `docker-compose.yml`
  materializaram **LF only** mesmo com `core.autocrlf=true`; `git check-attr` confirma
  `text: auto / eol: lf`.
- **D-6 confirmada parcialmente:** a porta 5432 está de fato ocupada nesta máquina (Postgres
  nativo); a 6333 estava **livre** no momento do teste. Troquei para 5435/6335/6336 via `.env`
  sem tocar no compose, como a spec descreve — funcionou.
- **D-7 confirmada:** o healthcheck em `CMD` + `bash` responde; `/readyz` devolve 200.

---

## 4. Métricas medidas vs alvo

| Métrica | Alvo | Spec declara | **Eu medi** | Status |
|---|---|---|---|---|
| Tempo clone→serviços healthy | ≤ 10 min | 7 s | **6,448 s** (cache de imagem quente) | CONFORME |
| idem, com pull de imagem | ≤ 10 min | não medido | **13,264 s** (imagem `qdrant/qdrant:v1.13.6` removida antes) | CONFORME |
| CI do PR desta spec | verde | 7 checks verdes + `evals` skipped | **7 pass + `evals` skipping** (run 32968758645, 28 s) | CONFORME |
| Suíte de testes | ≥ 1 teste real | 29 passed | **29 passed** em 0,24 s | CONFORME |
| `ruff check` / `ruff format --check` | limpo | "All checks passed" / 7 files | **All checks passed** / **49 files already formatted** | CONFORME |
| `mypy` strict no backend | limpo | Success, 1 arquivo | **Success: no issues found in 1 source file** | CONFORME |
| `commitlint` na branch | 0 problemas | exit 0 (9 commits) | **0 problems, 0 warnings** em **12 commits** | CONFORME |
| `gitleaks` no histórico | 0 leaks | pass | **no leaks found**, 13 commits, exit 0 | CONFORME |
| `actionlint` no `ci.yml` | — (não estava na spec) | — | **exit 0** | — |

**Nota sobre o número da spec.** O protocolo declarado ("`git clone`, `cp .env.example .env`,
`docker compose up -d --wait`") **não inclui o download das imagens**, então "7 s" não é
"máquina limpa" no sentido do BDD. Refiz removendo a imagem do Qdrant: 13,264 s. O alvo de 10
minutos continua confortavelmente atingido, mas o número publicado é de cache quente e a spec
não diz isso.

### Falsificações que executei (a evidência que não é auto-declarada)

| O que testei | Resultado |
|---|---|
| Causa raiz da D-10 (`hashFiles` em `jobs.<id>.if`) | Reintroduzi a expressão e rodei `actionlint`: **exit 1**, com a mensagem exata `calling function "hashFiles" is not allowed here`. Diagnóstico da D-10 **confirmado**. |
| Scanner de segredo (D-12) | Plantei `ghp_…` e `sk-ant-api03-…` fora do caminho excluído: **exit 1**, regras `github-pat` e `anthropic-api-key`. A allowlist do `.gitleaks.toml` **não** cegou o scanner. |
| Teste de rastreabilidade (REQ-7) | Caso de eval quebrado derruba as 4 verificações independentemente. |
| Guarda de suíte vazia | `run-tests.sh tests/security` com `backend/` presente → exit 1. |
| `skills-drift` | Passa (`OK: .claude/skills/ bate com o lockfile`) — ver R-2 sobre o falso positivo em Windows. |

---

## 5. Invariantes globais

| Invariante | Verificação | Resultado |
|---|---|---|
| Ausência de segredo no diff | `gitleaks v8.29.0` em todo o histórico + grep manual por CPF/CNPJ, chave privada, e-mail e `*_KEY=<valor>` no diff de 1.313 linhas | **OK.** Único valor preenchido é `POSTGRES_PASSWORD=vendinha`, senha default de desenvolvimento, declarada como tal no cabeçalho do compose. |
| Ausência de dado real | grep por padrões de CPF (`###.###.###-##`), CNPJ e sequências de 11/14 dígitos | **OK**, nenhuma ocorrência. |
| `.env` protegido em duas camadas | `.gitignore` (`.env`, `.env.*`, `!.env.example`) + `.claude/settings.json` `deny: Read(./.env*)`, `*.pem`, `*.p12`, `*.pfx`, `certificados/**` | **OK**, ambas presentes e coerentes com o que o `.env.example` promete. |
| Escopo respeitado ("nenhuma rota, nenhum grafo, nenhuma tool") | `find backend -type f` | **OK.** Apenas `pyproject.toml`, `README.md`, `uv.lock`, `vendinha/__init__.py` (vazio, `__all__: list[str] = []`). Nada de agente, API ou frontend em lugar nenhum do diff. |
| Fronteira de permissões de subagents | não aplicável nesta spec (nenhum subagent existe até a S-04) | **N/A** |
| PII mascarada em traces | não aplicável (não há agente nem trace até a S-02) | **N/A** |
| `uv.lock` sem drift | `uv sync --dev` seguido de `git status` | **OK**, working tree limpa. |

---

## 6. Avaliação das "Descobertas"

Todas as 12 descobertas foram lidas como *alterações de escopo a justificar*, não como fatos
aceitos.

| # | Veredito | Comentário |
|---|---|---|
| D-1 | **Legítima** | Verifiquei os três arquivos citados (`tests/conftest.py`, `scripts/run-tests.sh`, `ci.yml`): todos tratam `backend/` como entregável da S-00. A contradição era real e a resolução (scaffold + "fora de escopo" explícito) é a mínima possível. |
| D-2 | **Legítima** | Confirmado: com `backend/` presente e suíte vazia, `run-tests.sh` sai 1. O REQ-7 é o remédio proporcional. |
| D-3 | **Legítima** | Confirmado: `tests/discovery/` não existe e as duas referências foram corrigidas. Não sobrou nenhuma órfã (grep limpo). |
| D-5 | **Legítima** | Confirmado no `ci.yml`: `evals` observa `backend/evals/runner.py`, `typecheck` observa `backend/pyproject.toml`. O CI mostra `evals: skipping`. |
| D-6 | **Legítima, com imprecisão** | 5432 está ocupada; **6333 estava livre** no momento da minha verificação. O mecanismo (portas variáveis) é correto de qualquer forma. Ver R-3: a variabilização ficou incompleta. |
| D-7 | **Legítima e verificada** | O healthcheck funciona e a explicação `dash` vs `bash` confere. |
| D-4 | **Legítima** | `make evals` falha com mensagem apontando `make evals-check`. Alvo verde vazio seria pior. |
| D-8 | **Legítima** | `make` de fato não existe no Git Bash desta máquina. Cada alvo é uma linha executável — verifiquei rodando todas manualmente. |
| D-9 | **Legítima e falsificada** | Ver §3. |
| D-10 | **Legítima, gravíssima, e a correção é a certa** | Reproduzi a causa raiz. Ver R-1: a correção não veio com portão de regressão. |
| D-11 | **Legítima** | `commitlint` passa no CI e localmente. Mas ver **NC-4**: a renomeação deixou referências mortas, uma delas criada pelo próprio PR. |
| D-12 | **Legítima e falsificada** | A exclusão do `.gitleaks.toml` é estreita (`^\.claude/skills/`), justificada no arquivo e protegida por outro portão (`skills-drift`). O scanner continua achando segredo fora dali. |

**Descobertas que eu esperaria e não encontrei registradas:** a lista de **Tasks** da spec (7)
não foi atualizada para refletir os 12 commits realmente entregues (ver R-4), e o
`github-setup.md` §4 não foi revisado depois da D-10 (NC-5).

---

## 7. Riscos observados e ressalvas

| # | Ressalva | Por que importa |
|---|---|---|
| **R-1** | A D-10 diz "Passou a rodar `actionlint` no arquivo", mas **`actionlint` não está no `ci.yml` nem no `.pre-commit-config.yaml`**. Foi uma execução manual, não um portão. | A falha que apagou o CI inteiro por 6 dias continua **sem guarda de regressão automática**. `check-yaml` não pega: YAML válido ≠ schema de workflow válido — é o que a própria D-10 diz. Custo de fechar: 4 linhas no `ci.yml`. |
| **R-2** | `bash scripts/vendor-skills.sh --check` reporta **DRIFT falso** em Windows. Causa medida: `core.autocrlf` está `true` no nível **system** desta máquina, então os clones transitórios das origens vêm com CRLF e o `diff -r` acusa todos os arquivos. Com `core.autocrlf=false`, sai `OK`. | A D-9 blindou o repositório contra CRLF, mas não os clones que o próprio script faz. O README manda rodar esse comando; quem rodar em Windows vê um drift que não existe e aprende a ignorar o portão. |
| **R-3** | No `.env.example`, `DATABASE_URL=postgresql://…@localhost:5432/…` e `QDRANT_URL=http://localhost:6333` **não acompanham** `POSTGRES_PORT` / `QDRANT_HTTP_PORT`. | É o mesmo arquivo que instrui a trocar a porta por causa da D-6. Quem seguir a instrução fica com a infra no ar e as URLs erradas, sem aviso — falha silenciosa que aparece só na S-02. |
| **R-4** | A seção **Tasks** da spec lista 7 commits; a branch entregou **12**. As tasks 1 (`scaffold repo with harness and templates`) e 3 (`pipeline skeleton`) **não têm commit nesta branch** — o conteúdo veio do `first commit` direto na `main`. Sete commits entregues não correspondem a task alguma. | `CLAUDE.md`: "Cada task da spec = um commit". A rastreabilidade task↔commit, que é o motivo de a regra existir, não fecha. |
| **R-5** | A issue #1 declara "**Status da spec:** `aprovada`" enquanto o frontmatter está em `em-revisao`. | A issue foi desenhada para ser ponteiro, mas carrega um campo de estado duplicado — e ele já divergiu na primeira spec. É a segunda fonte de verdade que o REQ-6 diz querer evitar. |
| **R-6** | `make evals` sai com exit 1 por design (D-4). Justificado, mas o REQ-5 pede "Makefile com `up`, `test`, `lint`, `evals`" sem qualificar. | Aceito, mas o texto do REQ-5 deveria dizer "alvo `evals` que falha explicitamente até a S-06". Requisito e implementação divergem no papel. |
| **R-7** | A DoD da spec pede "CI verde (lint, typecheck, testes, **evals**)". O job `evals` está **skipped**, não verde — e por decisão correta. | O texto da DoD é insatisfazível até a S-06. Deveria ser corrigido, não interpretado. |
| **R-8** | O frontmatter declara `adrs: [ADR-005, ADR-008]`, mas a entrega apoia-se também no **ADR-009** (job `skills-drift`, `.gitleaks.toml`) e no **ADR-010** — citado literalmente dentro do REQ-2. | O mapa spec→ADR é usado para navegar as decisões; está incompleto na primeira spec. |
| **R-9** | Testei: o `gitleaks` v8.29.0 **não tem regra** para token do Mercado Pago (`APP_USR-…`). O `ANTHROPIC_API_KEY` é pego; o do gateway não. | Não é problema da S-00, mas o `.env.example` já reserva `MERCADOPAGO_ACCESS_TOKEN`. A partir da S-04 esse é um segredo que o portão não vê. Vale uma regra custom no `.gitleaks.toml`. |
| **R-10** | O workflow dispara **só** em `pull_request: branches: [main]`. Nada roda na `main` depois do merge. | Com REQ-4 fechado isso é aceitável; com REQ-4 aberto, a `main` está sem qualquer verificação — e é o estado atual, com o merge de #11 já dentro. |
| **R-11** | O job `evals` roda `working-directory: backend` e `python -m evals.runner`, ou seja, espera `backend/evals/`; mas o corpus de casos vive em `evals/` **na raiz** e o teste do REQ-7 aponta para lá. | Divergência de layout a resolver na S-06. Registro para que não vire descoberta tardia. |
| **R-12** | O corpo do PR #11 diz "**doze descobertas (D-1 a D-12)**" no texto e "9 descobertas registradas" no checklist. | Detalhe, mas é evidência de checklist marcado sem releitura — num PR cujo argumento central é que check decorativo não vale nada. |

---

## 8. Veredito

# APROVADO COM RESSALVAS

**Por que não REPROVADO.** Seis dos sete requisitos estão conformes com evidência que eu mesmo
produzi e falsifiquei, não com auto-declaração. O escopo foi respeitado ao pé da letra — o
`backend/` é scaffold puro, sem uma linha de comportamento. Não há segredo nem dado real no
diff. As 12 descobertas são todas legítimas, cada uma com causa raiz demonstrada, e três delas
(D-10, D-11, D-12) corrigem falhas que tornavam **todos** os portões deste repositório
decorativos — encontrar isso e escrever isso é o oposto de esconder.

**Por que não APROVADO.** A DoD da própria spec exige "Todos os requisitos CONFORMES", e o
**REQ-4 não está**. Verifiquei na API do GitHub, não no relato: a `main` não tem ruleset, não
tem nenhum check obrigatório, aceita merge commit e rebase, e não impõe nada a administradores.
O objetivo declarado da spec — "nascer com o gate antes do conteúdo: repo protegido" — não foi
atingido. E a consequência não é hipotética: **o PR #11 já foi mergeado**, como merge commit,
sem revisão, sem relatório de verificação e sem um único check obrigatório, 15 minutos antes
desta sessão começar. A D-10 escreveu que "nada bloqueia o merge"; o merge que aconteceu é a
prova de que a frase continua verdadeira.

Somam-se a isso duas falhas de documentação que o próprio PR causou (NC-4 e NC-5), uma delas
justamente no arquivo que o PO vai abrir para fechar o REQ-4.

### Condições para a S-00 ser considerada fechada

1. **REQ-4** — aplicar o ruleset do `github-setup.md` §3 e marcar `commitlint`, `lint`, `test`,
   `secrets`, `skills-drift` como obrigatórios; `typecheck` pode entrar agora (o job já roda
   verde com o `backend/` na `main`); `evals` fica para a S-06. Desligar merge commit e rebase.
2. **NC-5** — reescrever `github-setup.md` §4: o mecanismo é o job `detect` + `needs`, não
   `hashFiles` no `if` do job. Documento normativo que ensina o bug corrigido é pior que
   documento ausente.
3. **NC-4** — corrigir `CLAUDE.md:40`, `docs/arquitetura.md:26` e `docs/requisitos.md:102` para
   `commitlint.config.cjs`.
4. **R-1** — adicionar `actionlint` ao CI (ou ao pre-commit). Sem isso, a D-10 é uma correção
   sem portão, e a próxima expressão inválida derruba o workflow inteiro em silêncio de novo.
5. **R-3** — derivar `DATABASE_URL` e `QDRANT_URL` das variáveis de porta, ou documentar no
   `.env.example` que as três precisam ser trocadas juntas.
6. **Registrar NC-2 e NC-3** como desvio de processo na spec (ou como ADR, se o fluxo mudou de
   propósito). O ritual autor/revisor perde o sentido se a primeira spec do projeto for
   mergeada antes da revisão; e "merge por squash" perde o sentido se a primeira `main` já
   nasce com 12 commits de task dentro.

As demais ressalvas (R-2, R-4 a R-12) podem ser tratadas nas specs seguintes, desde que
registradas.

---

*Relatório produzido por sessão revisora independente, sem acesso ao histórico da sessão
autora. Todos os números acima foram medidos nesta máquina, nesta sessão. Nenhum arquivo de
código foi alterado por esta sessão.*
