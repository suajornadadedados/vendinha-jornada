---
id: S-00
titulo: Fundação do repositório
status: em-revisao
branch: spec/s-00-fundacao
issue: #1
adrs: [ADR-005, ADR-008, ADR-009, ADR-010]
riscos_cobertos: []
---

# S-00 — Fundação do repositório

## Objetivo
Nascer com o gate antes do conteúdo: repo protegido, harness, CI esqueleto e ambiente local
que sobe em um comando.

## Requisitos
- [x] REQ-1 Harness completo versionado (CLAUDE.md, comandos, skills, templates, docs normativas).
- [x] REQ-2 `docker compose up` sobe Postgres e Qdrant com healthchecks verdes. Observabilidade
      é Langfuse Cloud (ADR-010): entra por variável de ambiente, não por contêiner.
- [x] REQ-3 CI com jobs `commitlint`, `lint`, `typecheck`, `test` (verdes mesmo com código mínimo).
- [ ] REQ-4 (**pendente — ação do PO no GitHub, não do agente**) `main` protegida: PR obrigatório, checks obrigatórios, squash-only (ver docs/workshop/github-setup.md).
- [x] REQ-5 `.env.example` exaustivo e comentado; `Makefile` com `up`, `test`, `lint`, `evals`.
- [x] REQ-6 Cada spec tem issue no GitHub, linkada no frontmatter (`issue:`); a issue é ponteiro
      para a spec, nunca cópia dos requisitos. Convenção registrada no `CLAUDE.md`.
- [x] REQ-7 A suíte coleta ao menos um teste real a partir do momento em que `backend/` existe:
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

As tasks 1 e 3 já estavam na `main` antes desta branch (vieram no `first commit`), então não
têm commit próprio aqui. Em compensação, cinco commits nasceram das descobertas e não da lista
acima — `.gitattributes` (D-9), o gatilho do job `evals` (D-5), a correção do startup failure
(D-10) e a dos portões `commitlint` e `secrets` (D-11, D-12). É o comportamento previsto pelo
ADR-005: a branch conta a história em nível de task, e descoberta registrada vira commit.
Entrega final: **12 commits**.

## BDD
```gherkin
Cenário: quickstart em máquina limpa
  Dado um clone limpo do repositório com Docker instalado
  Quando executo "cp .env.example .env" e "docker compose up -d"
  Então todos os serviços ficam healthy em até 5 minutos
```

## Métricas de sucesso
| Métrica | Alvo | Como medir | Medido |
|---|---|---|---|
| Tempo clone→serviços healthy | ≤ 10 min | Cronometrado em clone limpo | **7 s** |
| CI do PR desta spec | verde | GitHub Actions | **7 checks verdes** + `evals` skipped |

Medição do clone limpo: `git clone` da branch em diretório novo, `cp .env.example .env`,
`docker compose up -d --wait`. O `--wait` só retorna quando os healthchecks passam — é o que
torna o número uma medição e não uma estimativa. As portas do host foram trocadas no `.env`
por causa da D-6; nenhuma outra alteração.

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

**D-10 — o CI nunca executou.** O PR desta spec revelou que todos os runs do repositório,
desde o `first commit`, eram **startup_failure**: 0 segundo, nenhum job, nenhum log. Causa:
`hashFiles()` não é permitida em `jobs.<id>.if` — só em contexto de step. Uma expressão inválida
não reprova o job, ela quebra o parse do arquivo inteiro, e o workflow nunca inicia. O efeito
prático é o pior possível: nenhum check reporta, então **nada bloqueia o merge** — e o
`github-setup.md` abre dizendo que "um check que roda e não impede o merge é relatório, não
portão". Aqui nem relatório era.

Corrigido dentro do REQ-3 com um job `detect` que faz checkout e exporta os gatilhos como
outputs, consumidos por `needs.detect.outputs.*`. Isso preserva a semântica desejada (job
*skipped*, nunca vermelho) e é correto também no mérito: no `if` de um job o workspace ainda não
foi clonado, então `hashFiles` responderia vazio de qualquer forma. Passou a rodar `actionlint`
no arquivo — a validação de YAML que já existia aceitava o arquivo sem reclamar, porque YAML
válido não é o mesmo que schema de workflow válido.

> Ressalva R-1 da verificação, e ela estava certa: à época deste texto o `actionlint` só tinha
> sido rodado **à mão**, então a falha que apagou o CI seguia sem portão de regressão. Ele foi
> promovido a passo do job `lint` e a hook de `pre-push` em `fix/s-00-verificacao`. A frase
> acima só passou a ser verdade depois disso.

**D-11 — `commitlint.config.js` era ilegível dentro da action.** O container da
`wagoid/commitlint-github-action` tem `/package.json` com `"type": "module"`, então um
`commitlint.config.js` com `module.exports` é interpretado como ESM e estoura
`module is not defined in ES module scope`. Localmente passava, porque sem `package.json` o
Node trata `.js` como CommonJS — o clássico "na minha máquina funciona", só que ao contrário.
Renomeado para `commitlint.config.cjs`, que é inequívoco nos dois lugares.

**D-12 — o job `secrets` nunca escaneou nada.** `gitleaks/gitleaks-action@v2` exige **licença
paga** quando o repositório pertence a uma organização, e este pertence: falhava com
"[suajornadadedados] is an organization. License key is required". Trocado pelo binário oficial
(`ghcr.io/gitleaks/gitleaks:v8.29.0`), que é livre e faz a mesma varredura de histórico. Ao
ligar, apontou um falso positivo: `LANGSMITH_API_KEY=<your-key>`, placeholder de documentação
numa skill vendorizada — que o ADR-009 proíbe editar à mão. Daí a única exclusão do
`.gitleaks.toml`, restrita a `.claude/skills/` e justificada no próprio arquivo: aquela árvore é
derivada do lockfile e protegida pelo job `skills-drift`. Falsificado: com um segredo plantado
fora do caminho excluído, o scanner sai com exit 1. A versão do hook local foi alinhada à do CI
para não divergirem as regras.

## Definition of Done
- [ ] Todos os requisitos CONFORMES no relatório de verificação
- [x] CI verde: `commitlint`, `detect`, `lint`, `secrets`, `skills-drift`, `test`,
      `typecheck`. O job `evals` permanece *skipped* — o runner é entregável da S-06, e
      exigir verde de um job que não pode existir seria requisito insatisfazível.
- [x] PR com evidência (saída de terminal medida; não há trace Langfuse porque não há
      agente até a S-02)
- [x] Relatório `/verificar-spec` em `docs/specs/relatorios/S-00-verificacao.md`:
      **APROVADO COM RESSALVAS**. As não-conformidades e ressalvas acionáveis foram
      corrigidas na branch `fix/s-00-verificacao`.
