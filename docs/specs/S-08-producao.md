---
id: S-08
titulo: Deploy — ambiente empacotado (api, frontend e nginx)
status: aprovada
branch: spec/s-08-deploy
issue: #9
adrs: [ADR-008]
riscos_cobertos: []
---

# S-08 — Deploy

> **Reescrita em 2026-08-31, e o escopo encolheu de propósito.** A versão anterior pedia
> duas stacks isoladas (DEV e PROD), Caddy com TLS e subdomínios, imagens no GHCR e CD
> disparado por merge e por tag com aprovação em GitHub Environment. O PO cortou: um
> ambiente só, sem denominação, sem DNS e sem TLS. O ADR-008 foi editado no lugar e
> explica por que editar valia mais que substituir — nada daquela decisão chegou a existir
> em código.

## Objetivo

Empacotar o produto inteiro num `compose` que sobe do zero: `api`, `frontend`, `nginx`,
`postgres` e `qdrant`, com o nginx servindo os estáticos e fazendo proxy da API. O
entregável é **um ambiente reprodutível, não uma URL pública** — e essa distinção é o que
governa tudo abaixo.

## A frase que governa a spec

> **Isto empacota o produto; não o publica.**
> Sem TLS e sem autenticação real, este host não vai para a internet aberta. A spec que
> tentasse as duas coisas ao mesmo tempo entregaria mal as duas: um proxy com certificado
> e um painel protegido por token digitado à mão é uma porta trancada ao lado de uma
> janela aberta. Empacotar primeiro, e dizer em voz alta o que falta para publicar, é mais
> honesto que uma URL com cadeado verde na frente de um `GET /config` aberto.

## Requisitos

- [x] REQ-1 `Dockerfile` do backend e do frontend, multi-stage. O do frontend produz os
      estáticos com as **duas entradas** que a S-07 criou (`index.html` e `admin.html`) —
      um build que esqueça a segunda entrega um painel que responde 404 só em produção.
      Containers **non-root** (RNF-9), e a versão do `qdrant-client` casando com a imagem
      do Qdrant (RS-6 da verificação da S-03, que apontava justamente para cá).
- [x] REQ-2 `deploy/docker-compose.yml` com `api`, `nginx`, `postgres` e `qdrant`: rede
      própria, volumes próprios, `restart: unless-stopped`, healthchecks, e as portas de
      Postgres e Qdrant **não publicadas** — só o nginx expõe porta no host.
- [x] REQ-3 Configuração do nginx: serve os estáticos, faz proxy da API, e roteia
      `/admin*` para `admin.html`. **`proxy_buffering off` na rota do chat** — sem isso o
      SSE do atendimento chega em bloco no fim e o streaming morre silenciosamente, com
      todos os testes verdes. É a falha mais provável desta spec inteira.
      > Entregue com o buffer desligado no bloco `/api/` **inteiro**, e não só no chat: são
      > três streams (`/chat`, `/eventos/sessao/{id}`, `/admin/eventos`) e o do chat é o
      > único sem heartbeat. Acertar a rota difícil e deixar as outras duas a uma
      > refatoração de distância não era o que o requisito queria dizer.
- [x] REQ-4 `deploy/.env.example` próprio, com o que muda em relação ao local: `APP_ENV`,
      `API_HOST=0.0.0.0` (é aqui que `0.0.0.0` é a resposta certa — ver S-02 D-8),
      `PUBLIC_BASE_URL`, `CORS_ORIGINS`, `OPERADOR_API_TOKEN` e as chaves do Langfuse.
      Nenhum secret versionado; o gitleaks do CI continua sendo o portão.
- [x] REQ-5 `deploy/RUNBOOK.md`: subir do zero, hardening mínimo (ufw, SSH por chave,
      containers non-root), backup e restore do Postgres, rollback, e a **região do
      projeto Langfuse (EU/US)** — pendência que o ADR-010 endereça explicitamente ao
      runbook e que só tem onde morar aqui.

## Fora de escopo — e o que isso significa

TLS, DNS, domínio, CI/CD, registry de imagens, múltiplos ambientes, alta disponibilidade
e IaC. Nada disso é omissão: o ADR-008 revisto registra cada corte.

**Três dívidas foram endereçadas a esta spec por documentos anteriores, e esta spec não as
paga.** Elas foram escritas quando "S-08" significava *host público*; com o escopo atual,
significam outra coisa, e continuar apontando para cá seria fingir que têm dono.

| Dívida | Onde foi escrita | Passa a valer |
|---|---|---|
| Autenticação real do painel (hoje um token digitado à mão em `sessionStorage`) | ADR-015 · S-07 | **quando o host for público** |
| `GET /config` aberto em qualquer ambiente; `db.py:main()` imprimindo o DSN; `api_key` na chave do `lru_cache` | S-02, ressalvas R-6/R-7/R-8 | **quando o host for público** |
| Barramento in-process (`LISTEN/NOTIFY` no lugar) | ADR-015 · S-07 | **quando existir mais de uma instância de API** — e este compose sobe uma |

Nenhuma spec deste roteiro torna o host público. Se isso mudar, muda por decisão do PO, e
a decisão vira ADR antes de virar branch.

## Tasks (cada uma vira um commit)
1. `feat(s-08): dockerfiles for api and frontend` — multi-stage, non-root, duas entradas.
2. `feat(s-08): deploy compose with nginx serving frontend and proxying api` — inclui o
   `proxy_buffering off` do SSE e o `.env.example` de deploy.
3. `docs(s-08): deploy runbook with hardening, backup and rollback`

## BDD

```gherkin
Cenário: o ambiente sobe do zero e atende
  Dado um host limpo com Docker e o repositório clonado
  Quando executo "cp deploy/.env.example deploy/.env" e "docker compose -f deploy/docker-compose.yml up -d --wait"
  Então todos os serviços ficam healthy
  E a landing responde na porta publicada pelo nginx
  E uma mensagem no chat volta em streaming, token a token, e não de uma vez só

Cenário: o banco não está exposto
  Dado o ambiente no ar
  Quando varro as portas publicadas no host
  Então só a do nginx responde, e Postgres e Qdrant não são alcançáveis de fora
```

## Métricas de sucesso
| Métrica | Alvo | Como medir |
|---|---|---|
| Host limpo → jornada respondendo | ≤ 15 min | cronometrado, com o runbook na mão e nada além dele |
| `docker compose up -d --wait` até healthy | ≤ 90 s | timestamp do comando |
| Primeiro token do chat através do nginx | streaming preservado | comparar com a mesma conversa em `localhost:8000`; se chegar em bloco, o REQ-3 falhou |
| Restore do backup do Postgres | pedido aprovado antes do dump continua lá | ensaio, registrado no relatório |

## Verificação independente (instruções para a sessão revisora)
- Subir o ambiente **do runbook**, sem usar conhecimento desta sessão. Runbook que só
  funciona para quem o escreveu não passou.
- Conferir o streaming atravessando o nginx — é o requisito que mais provavelmente passa
  despercebido por não quebrar nada visível nos testes.
- Confirmar que Postgres e Qdrant não têm porta publicada, e que os containers não rodam
  como root.
- Ensaiar o restore do backup e o rollback, cronometrados.
- Cruzar o "Fora de escopo" desta spec com o ADR-015 e a S-07: as três dívidas devem estar
  reetiquetadas aqui, e **não** implementadas.

## Descobertas (preenchido durante a execução)

- **DESC-0 (herdada do replanejamento).** `backend/vendinha/schemas.py` descreve o campo
  `Operador` como *"autenticação: é declaração, não identidade provada (S-08)"*. A frase
  ficou imprecisa com o corte de escopo, e corrigi-la exige regerar `openapi.json` e
  `frontend/src/api/schema.d.ts` — o CI compara e drift de contrato quebra o build. Esta
  spec já toca contrato; corrigir aqui, junto.

- **DESC-1 — `/admin/*` existe duas vezes, e ninguém tinha percebido.** São rotas do painel
  (`/admin/conversas`, `/admin/pedidos`, `/admin/metricas`, roteadas no navegador pelo
  react-router com `basename="/admin"`) **e** rotas da API (`admin.py`, os mesmos caminhos,
  literalmente). Em desenvolvimento nunca colidiu porque são duas origens: o Vite serve a
  página em `:5173` e o front chama `:8000`. Numa origem só — que é o que o nginx cria — um
  `location /admin` com fallback engole a API, e um com proxy engole a SPA.

  **Resolvido sem tocar no backend:** a API é servida sob `/api/`, e o `rewrite` do nginx
  remove o prefixo antes do proxy. O FastAPI continua vendo `/admin/conversas`, e o
  `openapi.json` não muda. O frontend é buildado com `VITE_API_BASE_URL=/api`.

  Foi decisão do PO nesta sessão, e é **desenho novo que a spec aprovada não previa** —
  registrado aqui, e não implementado em silêncio. A alternativa recusada (publicar a API
  numa segunda porta) contrariava o REQ-2 e mantinha o CORS como portão.

- **DESC-2 — `PUBLIC_BASE_URL` passa a ter que terminar em `/api`.** Consequência direta da
  DESC-1, e vale registrar porque a falha é silenciosa: é dessa variável que saem o link de
  pagamento entregue ao cliente, o `notification_url` do gateway e os links de DANFE e XML do
  painel. Sem o prefixo, o cliente clica no link de pagamento e recebe a landing — com status
  200, sem erro em log nenhum.

- **DESC-3 — o ambiente inteiro depende da chave de embedding para SUBIR, e não só para
  semear.** O `bootstrap` roda `db.py` e `ingest.py`; o segundo exige `OPENAI_API_KEY`
  (S-03, D-1). Como a `api` depende de `service_completed_successfully`, uma chave ausente ou
  expirada impede a subida — mesmo que o Qdrant já esteja indexado de uma subida anterior.

  Medido, não presumido: o bootstrap gravou os 65 produtos no Postgres e saiu com **código 1**
  na embedagem. A ordem do `ingest` (Postgres antes do Qdrant) funcionou como projetada — o
  banco ficou correto com a segunda metade falhando.

  **Não consertado, e está no runbook §7.** O conserto seria o seed detectar que a coleção já
  está indexada e pular a embedagem, e isso é mudança de comportamento em `ingest.py` —
  código de produto, fora do escopo desta spec. Decisão do PO.

- **DESC-4 — o `.dockerignore` não pode excluir `deploy/`.** Tentativa registrada porque o
  erro é instrutivo: excluir o diretório inteiro parecia higiene, e quebrou o build da imagem
  do frontend, que copia `deploy/nginx.conf`. Reincluir um arquivo de um diretório excluído
  funcionaria hoje e quebraria quando aparecesse o segundo. O segredo continua protegido pelo
  `**/.env`, que é onde essa proteção de fato mora.

## Definition of Done
- [ ] Todos os requisitos CONFORMES no relatório de verificação
- [ ] CI verde (lint, typecheck, testes, evals)
- [ ] PR com evidência (screenshot + trace Langfuse)
- [ ] Relatório /verificar-spec anexado com veredito APROVADO
