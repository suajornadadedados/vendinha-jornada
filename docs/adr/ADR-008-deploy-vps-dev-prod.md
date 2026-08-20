# ADR-008 — Deploy em VPS própria com stacks DEV/PROD e CD com aprovação

- Status: aceito · Data: 2026-08-03 · Decisão: D11

## Contexto
O público precisa ver um caminho de produção reprodutível e barato, sem cloud gerenciada.

## Decisão
Uma VPS, duas stacks Compose isoladas (redes/volumes/envs próprios); Caddy com TLS e
subdomínios; imagens buildadas no CI e publicadas no GHCR; deploy = `compose pull && up -d`
via SSH (zero build na VPS). Merge na main → DEV automático; tag v* → PROD com aprovação
manual (GitHub Environments). Postura mínima: ufw, SSH por chave, non-root, backup Postgres.

## Consequências
+ Pipeline inteiro visível e replicável; rima pedagógica (HITL no pipeline).
− Uma VPS é ponto único de falha (aceito para o escopo).
