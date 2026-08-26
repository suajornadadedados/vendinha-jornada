# Vendinha — harness do projeto

Este pacote é a fundação do repositório: harness do Claude Code, documentos normativos,
ADRs, specs, casos de eval e os portões de CI. Comece por:

1. `CLAUDE.md` — regras da sessão e fluxo SDD
2. `docs/requisitos.md` — do pedido do cliente às decisões de engenharia deste projeto
3. `docs/jornada.md` + `docs/riscos.md` + `docs/decisoes.md` — normativos da discovery
4. `docs/testes.md` — risco → teste: o seam de cada verificação e o critério de aceite
5. `docs/PRD.md` — requisitos do produto
6. `docs/arquitetura.md` — os dois diagramas: como o repo nasceu e como o produto se sustenta
7. `docs/specs/` — S-00 a S-09; execute na ordem, uma branch e uma sessão por spec
8. `evals/` — a régua de qualidade do agente, escrita antes do agente existir
9. `docs/workshop/github-setup.md` — proteção da main e configuração de PR/CD

Rituais (comandos do Claude Code em `.claude/commands/`):
`/escrever-spec` · `/entregar-spec` · `/registrar-adr`

A verificação independente não é comando: é o subagente **`verificador-de-spec`**, com o prompt
versionado em `.claude/agents/`. O autor passa o id da spec e mais nada — instrução escrita à mão
por quem implementou não é verificação independente. Ela roda **antes do PR**, e o PR nasce já com
as correções dentro (`CLAUDE.md`, fluxo item 4). O `/verificar-spec` continua existindo como a via
manual, para quando você quiser rodar numa sessão nova de verdade.

## Quickstart

Pré-requisitos: Docker, Python 3.12 e [uv](https://docs.astral.sh/uv/). `make` é conveniência —
cada alvo é uma linha de comando real, e o equivalente direto está ao lado.

```bash
cp .env.example .env       # nada precisa ser preenchido para subir a infra
make up                    # docker compose up -d --wait
make test                  # bash scripts/run-tests.sh
make lint                  # ruff check . && ruff format --check .
make hooks                 # instala os portões locais (pre-commit)
```

`make up` retorna quando Postgres e Qdrant estiverem **healthy** — é o `--wait` que faz isso,
e é por isso que os dois serviços declaram healthcheck. Referência medida: 6 segundos.

**Porta ocupada?** `POSTGRES_PORT`, `QDRANT_HTTP_PORT` e `QDRANT_GRPC_PORT` no `.env` mudam
apenas a porta exposta no host; dentro da rede do compose nada muda. É o caso quando você já
tem um Postgres nativo em 5432 ou outro projeto ocupando 6333.

**Sem `make` no Windows?** O Git Bash não traz `make`. Instale com
`winget install ezwinports.make` (ou use WSL) — ou simplesmente rode o comando que está dentro
do alvo: `make help` lista todos, e `make -n <alvo>` mostra o que ele executaria.

## Verificações que já rodam, antes de existir código de produto

```bash
bash scripts/run-tests.sh           # unit + security (docs/testes.md)
ruff check . && ruff format --check .
bash scripts/vendor-skills.sh --check   # .claude/skills/ bate com o lockfile (ADR-009)
bash scripts/gen-skills-doc.sh --check  # docs/harness/skills.md em dia
```

O harness é versionado junto com o código: quem clona recebe os dois. Editar uma skill
vendorizada à mão faz o CI reprovar o PR — para adaptar comportamento ao projeto, edite
`.claude/skills/vendinha-harness/SKILL.md`.
