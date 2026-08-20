---
id: S-08
titulo: Produção (DEV/PROD na VPS)
status: aprovada
branch: spec/s-08-deploy
issue: 
adrs: [ADR-008]
riscos_cobertos: []
---

# S-08 — Produção

## Objetivo
Cerimônia proporcional ao risco: merge → DEV automático; tag → PROD com aprovação manual.
Zero build na VPS.

## Requisitos
- [ ] REQ-1 `deploy/compose.dev.yml` e `deploy/compose.prod.yml` com redes, volumes e envs isolados; Caddy com TLS e subdomínios.
- [ ] REQ-2 CI builda imagens e publica no GHCR com tags por commit e por release.
- [ ] REQ-3 Workflow de CD: merge na main → deploy DEV via SSH (`compose pull && up -d`); tag `v*` → PROD condicionado a aprovação no Environment.
- [ ] REQ-4 Secrets por GitHub Environment; nenhum secret em arquivo versionado.
- [ ] REQ-5 Runbook `deploy/RUNBOOK.md`: provisionamento da VPS, hardening mínimo (ufw, SSH por chave, non-root), backup/restore do Postgres, rollback (retag + redeploy).

## Fora de escopo
Alta disponibilidade, múltiplas VPS, IaC completo.

## Tasks
1. `feat(s-08): dev and prod compose stacks with caddy tls`
2. `ci(s-08): image build and push to ghcr`
3. `ci(s-08): cd workflows for dev on merge and prod on tag with approval`
4. `docs(s-08): vps runbook with hardening, backup and rollback`

## BDD
```gherkin
Cenário: PROD exige aprovação
  Dado uma tag v1.0.0 criada
  Quando o workflow de CD chega ao job de PROD
  Então ele aguarda aprovação no Environment e só então atualiza a stack de produção
```

## Métricas de sucesso
| Métrica | Alvo | Como medir |
|---|---|---|
| Merge → DEV atualizado | ≤ 5 min | timestamps do workflow |
| Rollback seguindo o runbook | ≤ 10 min | ensaio cronometrado |

## Verificação independente
- Acompanhar um deploy DEV real; criar tag de teste e confirmar o bloqueio por aprovação.
- Executar o rollback do runbook em DEV.

## Definition of Done
- [ ] Checklist padrão do template
