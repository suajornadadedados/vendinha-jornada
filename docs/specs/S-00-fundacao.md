---
id: S-00
titulo: Fundação do repositório
status: em-execucao
branch: spec/s-00-fundacao
issue: #1
adrs: [ADR-005, ADR-008]
riscos_cobertos: []
---

# S-00 — Fundação do repositório

## Objetivo
Nascer com o gate antes do conteúdo: repo protegido, harness, CI esqueleto e ambiente local
que sobe em um comando.

## Requisitos
- [ ] REQ-1 Harness completo versionado (CLAUDE.md, comandos, skills, templates, docs normativas).
- [ ] REQ-2 `docker compose up` sobe Postgres e Qdrant com healthchecks verdes. Observabilidade
      é Langfuse Cloud (ADR-010): entra por variável de ambiente, não por contêiner.
- [ ] REQ-3 CI com jobs `commitlint`, `lint`, `typecheck`, `test` (verdes mesmo com código mínimo).
- [ ] REQ-4 `main` protegida: PR obrigatório, checks obrigatórios, squash-only (ver docs/workshop/github-setup.md).
- [ ] REQ-5 `.env.example` exaustivo e comentado; `Makefile` com `up`, `test`, `lint`, `evals`.
- [ ] REQ-6 Cada spec tem issue no GitHub, linkada no frontmatter (`issue:`); a issue é ponteiro
      para a spec, nunca cópia dos requisitos. Convenção registrada no `CLAUDE.md`.
- [ ] REQ-7 A suíte coleta ao menos um teste real a partir do momento em que `backend/` existe:
      rastreabilidade dos casos de `evals/` contra `evals/schema/caso.schema.json`.

## Fora de escopo
Qualquer código de agente, API ou frontend. O `backend/` desta spec é scaffold de build
(pyproject + configuração de mypy) — nenhuma rota, nenhum grafo, nenhuma tool.

## Tasks (cada uma vira um commit)
1. `chore(s-00): scaffold repo with harness and templates`
2. `chore(s-00): docker compose with postgres and qdrant`
3. `ci(s-00): pipeline skeleton (commitlint, lint, typecheck, test)`
4. `docs(s-00): env example, makefile and quickstart readme`
5. `test(s-00): traceability test for eval cases against schema`
6. `chore(s-00): backend scaffold with pyproject and mypy config`
7. `docs(s-00): link specs to github issues`

## BDD
```gherkin
Cenário: quickstart em máquina limpa
  Dado um clone limpo do repositório com Docker instalado
  Quando executo "cp .env.example .env" e "docker compose up -d"
  Então todos os serviços ficam healthy em até 5 minutos
```

## Métricas de sucesso
| Métrica | Alvo | Como medir |
|---|---|---|
| Tempo clone→serviços healthy | ≤ 10 min | Cronometrado em clone limpo |
| CI do PR desta spec | verde | GitHub Actions |

## Verificação independente
- Clonar em diretório limpo e executar o quickstart cronometrando.
- Confirmar que a main rejeita push direto (tentar e capturar a recusa).
- Conferir que `bash scripts/run-tests.sh` coleta ao menos um teste (não pode sair pelo
  atalho de suíte vazia, já que `backend/` passa a existir nesta spec).
- Conferir que o `issue:` das 10 specs aponta para a issue correspondente e que nenhuma issue
  duplica requisito ou task da spec.

## Descobertas (preenchido durante a execução)

**D-1 — `backend/` é entregável da S-00, mas nenhuma spec dizia isso.** Três arquivos de infra
já tratavam a pasta como entregável desta spec (`tests/conftest.py`, `scripts/run-tests.sh`,
os jobs condicionais de `ci.yml`), e o `docs/workshop/github-setup.md` §4 manda marcar
`typecheck` como obrigatório "depois da S-00" — o que exige `backend/pyproject.toml` existindo.
Nenhuma spec mencionava `backend/`. Resolvido pelo PO: a S-00 cria o scaffold de build, e o
"fora de escopo" foi explicitado para deixar claro que scaffold ≠ código de produto.

**D-2 — `backend/` existindo com suíte vazia reprova o CI.** `scripts/run-tests.sh` falha de
propósito quando `backend/` existe e o pytest não coleta nada. Como a S-00 não cobre risco
algum (`riscos_cobertos: []`), a matriz de `docs/testes.md` não lhe devia teste nenhum.
Resolvido pelo PO com o REQ-7: o teste de rastreabilidade dos casos de eval — já prometido
pelo `evals/README.md`, independente de agente e de rede.

**D-3 — `tests/discovery/` era referência órfã.** `ruff.toml` e `evals/README.md` citavam a
pasta, que nunca existiu, e `docs/testes.md` §1 diz "duas camadas, e só duas". Resolvido pelo
PO: o normativo vence, o teste vive em `tests/unit/` e as duas referências foram corrigidas.
Nenhuma terceira camada foi criada.

**D-5 — o job `evals` do CI estava pendurado no gatilho errado.** `typecheck` e `evals`
usavam a mesma condição (`hashFiles('backend/pyproject.toml')`), escrita presumindo que o
scaffold do backend e o runner de evals chegariam juntos. Com a S-00 criando o scaffold, o
job `evals` sairia do estado *skipped* e tentaria executar um runner que só existe na S-06 —
CI vermelho por construção. Corrigido dentro do REQ-3 (o requisito é justamente "CI com jobs
verdes mesmo com código mínimo"): `evals` passa a observar `backend/evals/runner.py`. A
intenção já estava escrita no próprio arquivo — "vira required check a partir da S-06".

**D-6 — as portas default colidem na máquina do PO.** O BDD desta spec fala em "máquina
limpa", e é para ela que o `.env.example` traz 5432 e 6333. Na máquina de desenvolvimento
usada aqui as duas estão ocupadas — 5432 por um Postgres nativo do Windows (fora do Docker) e
6333 pelo Qdrant de outro projeto. Por isso as portas do host são variáveis (`POSTGRES_PORT`,
`QDRANT_HTTP_PORT`, `QDRANT_GRPC_PORT`): quem tiver colisão troca no `.env`, sem tocar no
compose. Verificado com 5435/6335/6336: ambos os serviços `healthy` em 6 segundos.

**D-7 — healthcheck do Qdrant não pode usar `CMD-SHELL`.** A imagem `qdrant/qdrant` não traz
`curl` nem `wget` (verificado, não presumido) — traz `bash`, cujo `/dev/tcp` faz o papel de
cliente HTTP. Mas `CMD-SHELL` executa `/bin/sh`, que ali é `dash`, e `/dev/tcp` é bashism: o
healthcheck falhava com "Directory nonexistent" enquanto o `/readyz` respondia 200. Corrigido
para a forma `CMD` com `bash` explícito.

**D-4 — `make evals` não tem runner até a S-06.** Resolvido pelo PO: o alvo existe e falha com
mensagem explícita apontando para `make evals-check`. Alvo verde que não executou o agente
seria check decorativo.

**D-8 — `make` não existe na máquina do PO.** O REQ-5 pede Makefile, e é o certo: é o que
roda no CI e em Linux/WSL. Mas o Git Bash do Windows não traz `make`, então o quickstart não
executa nesta máquina sem instalar (`winget install ezwinports.make`) ou usar WSL. Em vez de
inventar um segundo executor de tarefas, cada alvo ficou sendo **uma linha de comando real** e o
README documenta o equivalente direto. O Makefile foi validado dentro de um contêiner Alpine,
já que não dava para executá-lo aqui.

**D-9 — clone limpo em Windows quebrava os scripts.** Sem `.gitattributes`, um clone com
`core.autocrlf=true` (default do Git for Windows) materializa `Makefile` e `scripts/*.sh` com
CRLF: shebang vira `bad interpreter: /usr/bin/env bash^M` e o `make` recusa as recipes. Como o
BDD desta spec é justamente "clone limpo", entrou `.gitattributes` com `* text=auto eol=lf`.
Verificado com um clone real forçando `autocrlf=true`.

## Definition of Done
- [ ] Todos os requisitos CONFORMES no relatório de verificação
- [ ] CI verde (lint, typecheck, testes, evals)
- [ ] PR com evidência (screenshot + trace Langfuse)
- [ ] Relatório /verificar-spec anexado com veredito APROVADO
