# ADR-008 — Deploy num ambiente único, empacotado por Compose

- Status: aceito · Data: 2026-08-03 · **Revisto em 2026-08-31** · Decisão: D11

## Contexto
O público precisa ver um caminho de produção reprodutível e barato, sem cloud gerenciada.

## Decisão (2026-08-03)
Uma VPS, duas stacks Compose isoladas (redes/volumes/envs próprios); Caddy com TLS e
subdomínios; imagens buildadas no CI e publicadas no GHCR; deploy = `compose pull && up -d`
via SSH (zero build na VPS). Merge na main → DEV automático; tag v* → PROD com aprovação
manual (GitHub Environments). Postura mínima: ufw, SSH por chave, non-root, backup Postgres.

## Revisão de 2026-08-31 — o que fica valendo

O PO cortou o escopo, e este ADR foi editado no lugar em vez de substituído por um novo:
a **pergunta** de D11 não mudou, e a resposta anterior nunca chegou a existir em código —
não há `deploy/`, não há Dockerfile, não há workflow de CD. Substituir um ADR serve para
registrar que uma decisão *implementada* deixou de valer; aqui não havia o que preservar.

**Sai:** duas stacks isoladas, os nomes DEV e PROD, Caddy, TLS, DNS e subdomínios, GHCR,
deploy por SSH, CD por merge e por tag, GitHub Environments.

**Fica valendo:** um **ambiente único e sem denominação**, empacotado num
`deploy/docker-compose.yml` que sobe `api`, `frontend`, `nginx`, `postgres` e `qdrant` —
o nginx serve os estáticos e faz proxy da API. A imagem é buildada na máquina que
hospeda; o deploy é manual, pelo runbook. A postura mínima **permanece**: ufw, SSH por
chave, containers non-root, backup do Postgres.

**O que isso muda de verdade, e não é o número de arquivos:** o entregável deixa de ser
*uma URL pública* e passa a ser *um ambiente empacotado e reprodutível*. Sem TLS e sem
autenticação real, este host não vai para a internet aberta — e é essa frase, não uma
promessa de spec futura, que responde às dívidas nomeadas na S-07 e no ADR-015
(autenticação do painel, `GET /config` aberto, barramento in-process). Elas passam a
valer *quando o host for público*, e nenhuma spec deste roteiro o torna público.

## Consequências
+ Pipeline de subida inteiro visível e replicável num arquivo que cabe na tela: quem
  clona vê o produto empacotado, não um pipeline que exige uma conta de nuvem para ler.
+ O quickstart (RNF-1) e o deploy passam a divergir só no que precisam divergir — o
  `docker-compose.yml` da raiz continua sendo a máquina do desenvolvedor.
− Sem CI publicando imagem, o build acontece no host: mais lento, e sujeito ao que
  estiver instalado lá. Aceito — o runbook fixa as versões.
− Sem TLS e sem CD, não há demonstração de "aprovação humana no pipeline", que era a
  rima pedagógica da decisão original com o HITL do produto. Perda real, aceita: o HITL
  que importa é o da emissão de NF, e esse é testado (ADR-003, R3).
− Um host é ponto único de falha (aceito para o escopo).
