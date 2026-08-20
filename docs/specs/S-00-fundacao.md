---
id: S-00
titulo: Fundação do repositório
status: aprovada
branch: spec/s-00-fundacao
issue: 
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

## Fora de escopo
Qualquer código de agente, API ou frontend.

## Tasks (cada uma vira um commit)
1. `chore(s-00): scaffold repo with harness and templates`
2. `chore(s-00): docker compose with postgres and qdrant`
3. `ci(s-00): pipeline skeleton (commitlint, lint, typecheck, test)`
4. `docs(s-00): env example, makefile and quickstart readme`

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

## Definition of Done
- [ ] Checklist padrão do template
