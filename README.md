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
`/escrever-spec` · `/entregar-spec` · `/verificar-spec` (sessão nova!) · `/registrar-adr`

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
