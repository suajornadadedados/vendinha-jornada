---
id: S-07
titulo: Frontend integrado e API de observação
status: em-revisao
branch: spec/s-07-frontend
issue: #8
adrs: [ADR-004, ADR-013, ADR-015]
riscos_cobertos: []
---

# S-07 — Frontend integrado e API de observação

> **Reescrita em 2026-08-28, e o escopo mudou de natureza.** A versão anterior tinha 63 linhas e
> pedia uma coisa razoável: chat com SSE, fila do operador, cliente TS gerado. O plano aprovado pelo
> PO pede duas telas e uma demonstração — a landing pública onde o cliente é atendido, e o painel
> onde o operador vê o atendimento acontecer —, e a segunda **não é construível sobre o backend que
> existe**. O ADR-015 registra a decisão e o que ela custa; esta spec é a execução dela.

## Objetivo

Produto usável de ponta a ponta e **observável enquanto acontece**: uma landing pública com
atendimento pelo agente, e um painel onde o operador vê a conversa, a composição sendo validada, a
fila de aprovação de NF e o custo de tudo isso — com os contratos gerados do OpenAPI e nenhuma conta
de dinheiro no navegador.

## A frase que governa a spec

> **A UI não é lugar de garantia. É lugar de honestidade.**
> Toda invariante já está fechada abaixo dela (matriz R1-R10) — por isso `riscos_cobertos` está
> vazio, e não por esquecimento. O que esta spec pode fazer de errado não é deixar passar uma ação
> proibida: é **mentir sobre o que aconteceu**. Um total recalculado em JavaScript, um custo zerado
> por falta de preço, um número congelado exibido como atual depois que a conexão caiu. É contra
> isso que as métricas apontam.

## Requisitos

### A fronteira

- [x] REQ-1 Cliente TypeScript **gerado** do OpenAPI, sem subir servidor (`python -m vendinha.openapi`),
      com o `openapi.json` commitado. O CI regenera e compara: drift de contrato quebra o build.
      Tipos de fronteira escritos à mão: zero.

### O que o backend precisa passar a oferecer

- [x] REQ-2 **Read model** de sessões e turnos: quem conversou, quando, quantos turnos, que modelo,
      quantos tokens, que latência. As mensagens **não são copiadas** — são lidas do checkpointer
      (RNF-6, pointer-not-payload).
- [x] REQ-3 **Barramento de eventos** in-process, com fila limitada por assinante: fila cheia
      descarta o mais antigo e emite um evento de atraso, e nunca bloqueia quem produz. Eventos
      tipados no OpenAPI, para virarem tipos TS como todo o resto.
- [x] REQ-4 Rotas `/admin/*` **read-only** e fail-closed no `X-Operador-Token`: conversas (lista e
      detalhe), pedidos, métricas, prompts, e o stream SSE do barramento.
- [x] REQ-5 **Custo em `Decimal` no backend**, de `data/precos-modelos.json` versionado. Modelo sem
      preço devolve `None`, jamais zero, e a tela diz por quê. O `atualizado_em` da tabela é visível.
- [x] REQ-6 **Push por sessão** (`GET /eventos/sessao/{session_id}`): o cliente **recebe** a
      confirmação da NF sem perguntar. Fecha a ressalva R-2 da verificação da S-05, que registrou o
      RF-3.6 estreitado de "recebe" para "pergunta e o agente consulta".

### As telas

- [x] REQ-7 **Landing pública** da Vendinha: institucional, com identidade própria de empório
      mineiro, os quatro tipos de evento que o agente sabe montar, e um FAB no canto inferior direito
      que abre o atendimento. É o simulador do canal do cliente — não um produto, e sai do bundle sem
      uma linha de JS do painel.
- [x] REQ-8 **Widget de atendimento**: streaming SSE token a token, indicador de digitando, e
      estados honestos com cara própria — montando composição, aguardando pagamento (com o link),
      aguardando aprovação da NF (sem prometer prazo), NF emitida (com DANFE e XML, que **chega
      sozinho**). Erro de stream oferece reenviar e não mostra stack trace. `session_id` em
      `localStorage`: F5 não perde a conversa.
- [x] REQ-9 **A composição é visível enquanto é montada**: itens, quantidades, total e valor por
      pessoa, atualizados a cada veredito, **exatamente como o validador devolveu**. Reprovação
      aparece com o motivo real — orçamento, slot, restrição ou disponibilidade —, nunca genérica.
      É a tela onde a regra de ouro fica visível para quem nunca vai abrir um trace.
- [x] REQ-10 **Painel: conversas ao vivo.** O que acontece no backend aparece na tela em ≤1s, por
      evento e não por polling. Lista, e detalhe com a timeline da conversa ao lado dos vereditos de
      composição, dos turnos com tokens/latência/custo e do pedido vinculado.
- [x] REQ-11 **Painel: fila HITL com notificação.** O `aprovacao_pendente` toca um sino com badge; o
      detalhe traz destinatário PJ completo (razão social, CNPJ, IE, endereço) e composição item a
      item; aprovar e rejeitar com motivo obrigatório; a lista se atualiza pelo evento.
- [x] REQ-12 **Painel: rastreabilidade.** Por conversa, lado a lado, **o que o modelo propôs × o que
      o código validou ou recusou**, com as tools chamadas, a latência e o custo por turno. Deep-link
      do Langfuse só aparece quando há chaves.
- [x] REQ-13 **Painel: pedidos e métricas.** Pedidos com composições, itens de preço congelado,
      status de pagamento e de NF, DANFE e XML. KPIs: conversão, ticket médio, custo por conversa e
      como % do ticket, tokens por modelo, p50/p95 do primeiro token contra o alvo RNF-4, tempo médio
      de atendimento, tempo até a decisão do operador, e **recusas do validador por motivo**.
- [x] REQ-14 **Painel: configurações.** Modelo e credencial via `PUT /config`, com o aviso honesto de
      que `editable:false` fora de `APP_ENV=local` (S-02, D-8). **Prompts em modo leitura**, com
      caminho e sha, e a nota de que prompt muda por PR com evals — nunca pela tela (ADR-015).
- [x] REQ-15 **Sistema visual decidido antes de implementado.** `docs/design/sistema-visual.md`
      commitado antes do primeiro componente: paleta, par tipográfico, escalas de densidade para os
      dois registros, ícones de um set só, e os tipos de gráfico dos KPIs.

## Fora de escopo

- **Autenticação.** O painel pede o `OPERADOR_API_TOKEN` numa tela de conexão e guarda em
  `sessionStorage`. É aceitável numa demo local e **não** num host público — dito em voz alta no
  ADR-015, e é dívida da S-08.
- **Escrita no domínio.** Nenhum CRUD de catálogo, pedido ou composição. As únicas escritas são a
  decisão de HITL e a configuração de modelo, ambas já existentes.
- Responsivo mobile refinado.
- Multi-instância do barramento (`LISTEN/NOTIFY` fica para a S-08).

## Decisões de desenho

**D-1 — A REQ-4 antiga foi reescrita, e vale registrar o que ela dizia.** Ela pedia *"sem framework
de UI pesado; estilo próprio simples"*, enquanto o harness do projeto roteia a S-07 para `shadcn`.
Não é contradição: shadcn é copy-in — o componente entra no repositório como código nosso, sem
dependência de runtime, que é exatamente o que a REQ-4 queria proteger. A leitura adotada, decidida
com o PO: **shadcn no painel, CSS próprio na landing.** Um painel operacional denso — tabelas,
drawers, diálogos de aprovação, toasts — escrito à mão custa muito mais e sai menos acessível; uma
landing de marca escrita com component library sai com cara de dashboard.

**D-2 — Os eventos de conversa e de composição nascem sem tocar no grafo.** A rota `/chat` já recebe
os `ToolMessage` no `astream(stream_mode="messages")` e hoje os **descarta** no filtro de tokens
(`app.py:566-577`). O mesmo laço passa a observar o que descarta: o `ToolMessage` de
`validar_composicao` vira `composicao_avaliada`. A alternativa — um callback dentro da tool, ou um nó
novo no grafo — poria o observador dentro do caminho que a S-04 fechou por arquitetura, para ganhar
nada.

**D-3 — `EventSource` não serve, e por isso há um leitor de SSE escrito à mão.** `/chat` é POST, e
`/admin/eventos` precisa de header — passar o token do operador em query string o colocaria em log de
acesso. Um leitor de `text/event-stream` sobre `fetch` + `ReadableStream` resolve os três streams em
~60 linhas e sem dependência nova.

**D-4 — O OpenAPI é gerado sem subir a API.** `python -m vendinha.openapi` usa `app.openapi()`. O
CI regenera e compara com o arquivo commitado. Depender de um servidor de pé para gerar o cliente
transformaria o portão de contrato num teste de integração — e a ADR-011 recusou essa camada.

## Tasks

1. `adr(s-07): painel de observacao do cliente como entregavel`
2. `spec(s-07): reescreve a s-07 como full-stack`
3. `feat(s-07): read model de sessoes e turnos`
4. `feat(s-07): barramento de eventos in-process com fila limitada`
5. `feat(s-07): custo por modelo em Decimal com tabela de precos versionada`
6. `feat(s-07): rotas de admin — conversas, pedidos, metricas e prompts`
7. `feat(s-07): sse do admin e push de status para a sessao do cliente`
8. `feat(s-07): cors e geracao offline do openapi`
9. `test(s-07): barramento, custo e agregacao de kpis`
10. `test(s-07): rotas de admin fecham sem token e stream nao vaza sessao`
11. `feat(s-07): scaffolding do frontend e cliente typescript gerado`
12. `feat(s-07): sistema visual e landing publica da vendinha`
13. `feat(s-07): widget de atendimento com sse e estados honestos`
14. `feat(s-07): painel de composicao ao vivo com o veredito do validador`
15. `feat(s-07): painel admin — visao geral, conversas e rastreabilidade`
16. `feat(s-07): fila hitl no painel com notificacao e acoes auditadas`
17. `feat(s-07): pedidos, metricas e configuracoes no painel`
18. `chore(s-07): estados vazios e de erro, e roteiro de demo`

## BDD

```gherkin
Cenário: o operador vê o atendimento acontecendo
  Dado o painel aberto numa aba e a landing em outra
  Quando um visitante pede um café da manhã para 40 pessoas pelo widget
  Então a conversa aparece na lista do painel em menos de um segundo
  E as mensagens do agente aparecem no painel enquanto são escritas
  E nenhuma requisição de polling foi feita para isso

Cenário: a recusa do código é legível nas duas telas
  Dado um orçamento de R$35 por pessoa
  Quando a composição montada sai a R$48 por pessoa
  Então o widget mostra o excedente e o item que faltou, e não um erro genérico
  E o painel registra a recusa com o mesmo motivo, na rastreabilidade e no gráfico

Cenário: a NF chega ao cliente sem que ele pergunte
  Dado um pedido pago e aguardando aprovação da nota
  Quando o operador aprova pelo painel
  Então o widget do cliente exibe sozinho o cartão da NF com DANFE e XML
  E o cliente não enviou nenhuma mensagem entre a aprovação e o cartão

Cenário: a conexão cai e a tela não mente
  Dado o painel e o widget abertos com dados na tela
  Quando a API é derrubada
  Então as duas telas exibem o estado desconectado
  E nenhum número antigo continua sendo apresentado como atual
```

## Métricas de sucesso

| Métrica | Alvo | Como medir |
|---|---|---|
| Jornada completa sem recarregar a página | 100% | roteiro manual |
| Tipos da fronteira escritos à mão | 0 | revisão do diff |
| Contas de dinheiro no frontend (total, custo, KPI) | 0 | revisão do diff |
| Atraso entre o evento no backend e a tela do painel | ≤ 1s | cronômetro nas duas abas |
| Requisições de polling no painel | 0 | aba Network, 2 min ociosos |
| Rotas `/admin/*` que respondem sem token | 0 | teste `security` |
| Drift entre `openapi.json` e o cliente TS | 0 | `git diff --exit-code` no CI |
| Componentes shadcn commitados antes de `docs/design/sistema-visual.md` | 0 | ordem no `git log` |
| Estados (aprovado/pendente/rejeitado) distinguíveis só por matiz | 0 | revisão de tela |
| Mensagens da conversa copiadas para tabela nova | 0 | revisão do diff — vêm do checkpointer |

## Verificação independente (instruções para a sessão revisora)

1. Percorrer a jornada num navegador limpo, com as duas abas abertas: evento → composição validada →
   checkout → pagamento mock → fila HITL → aprovação → NF.
2. **Derrubar o backend no meio** e julgar a honestidade dos estados de erro nas duas telas. Um
   número congelado apresentado como atual é não-conformidade, não detalhe.
3. Conferir no diff que nenhum total, custo ou KPI é somado em JavaScript.
4. Conferir que as mensagens do painel vêm do checkpointer, e não de uma tabela nova.
5. Percorrer **todas** as rotas `/admin/*` sem token e com token errado.
6. Tentar ver, por `GET /eventos/sessao/{id}`, um evento de outra sessão.
7. Conferir a ordem dos commits: `docs/design/sistema-visual.md` antes do primeiro componente shadcn.
8. Conferir que a tela de configurações não oferece edição de prompt em nenhum ambiente.

## Descobertas (preenchido durante a execução)

- **DESC-9 — A primeira conversa longa de verdade mostrou dois defeitos da janela do
  chat, e um terceiro que não é desta spec.** Um atendimento real — café da manhã, 30
  pessoas, R$ 50 por cabeça, três variações por restrição alimentar — expôs:

  1. **A tabela da composição ficava presa no rodapé, e as falas novas nasciam acima
     dela.** O veredito era um estado à parte (`Veredito | null`) renderizado num slot
     fixo depois do `falas.map`. O mesmo desenho fazia cada veredito **sobrescrever** o
     anterior: com três variações, o cliente via só a última — a recusada. A REQ-9 diz
     "atualizados a cada veredito", e a leitura literal dela era um cartão só; **o PO
     decidiu por um cartão por veredito**, na posição cronológica em que aconteceu.
     A conversa virou uma lista ordenada só, fala e composição no mesmo `map`.

  2. **O agente narrava o próprio trabalho, e cada narração virava um balão.** *"Agora
     vou detalhar os produtos"*, *"vou consultar os preços e validar"*, *"só um segundo,
     estou finalizando"*. São `AIMessage` com texto **e** `tool_calls`, e o campo `fala`
     que a S-07 introduziu (commit `a6608e7`) passou a dar um balão para cada uma —
     fiel ao que o modelo produziu, e péssimo de ler. Corrigido em **duas camadas**, por
     decisão do PO: o prompt proíbe o preâmbulo (reduz na origem) e o código garante
     (novo evento `preambulo` no `/chat`, que desfaz o balão e devolve o indicador de
     digitando). Só o prompt não teria rede embaixo; só o código pagaria os tokens de
     saída de uma narração que ninguém lê.

  3. **O atendimento terminou com a frase de teto de budget, e isso NÃO é desta spec.**
     Não foi janela de contexto: foi `LIMIT_REACHED_MESSAGE` — o teto de 250k de
     `tokens_spent`, que soma o histórico reenviado a cada ida ao modelo e portanto
     cresce de forma quadrática. Vira a **S-12**, junto com prompt caching: hoje o
     prefixo estático (6.655 tokens na recomendação, 8.864 no checkout) é reenviado e
     recobrado inteiro em toda chamada, sem nenhum `cache_control` no repositório.

- **DESC-7 — Visão geral e Métricas nasceram dizendo a mesma coisa, e o PO perguntou
  qual era a diferença.** As duas liam a mesma consulta e repetiam quatro KPIs, o
  bullet de latência e o gráfico de recusas inteiro. Duas telas que dizem o mesmo
  treinam a pessoa a abrir só uma. O corte que entrou: **Visão geral é a loja**
  (vendido, conversão, valor médio, duração do atendimento completo, o que a
  conferência barrou, os últimos atendimentos) e **Métricas é a máquina** (custo de
  IA, custo sobre o vendido, tokens por modelo, tempo até o primeiro token). Zero
  bloco repetido entre as duas. A REQ-13 continua conforme: nenhum KPI que ela pede
  saiu do painel — eles foram **distribuídos** em vez de empilhados numa tela só.

- **DESC-8 — A navegação do painel virou rota, e a decisão de desenho anterior era
  o oposto.** O comentário no topo do `Admin.tsx` argumentava que um roteador só
  serviria para URLs compartilháveis que ninguém tinha pedido. O PO pediu. Cada seção
  tem endereço (`/admin`, `/admin/conversas`, …) e uma conversa aberta é
  `/admin/conversas/<id>`. O custo é a reescrita de `/admin/*` para `admin.html`, no
  `vite.config.ts` hoje e no servidor de estáticos na S-08.

  > E o custo cobrou: o middleware entrou instalado **depois** dos internos do Vite,
  > então `/admin/conversas` respondia **200 servindo a landing**. O primeiro teste
  > olhou só o status e passou. Só apareceu quando abri um navegador de verdade —
  > registro aqui porque é a evidência mais barata de que status 200 não é resposta
  > certa, e de que a verificação em navegador da própria spec não era formalidade.


- **DESC-2 — A paleta de partida reprovou em contraste, e a régua era do próprio style.**
  O `ui-ux-pro-max` devolveu *Accessible & Ethical* com contraste 4.5:1 como requisito, e o
  ocre `#B4711F` dos diagramas do repositório mede **3.72** sobre papel — reprova em texto,
  e "pendente" é um badge com palavra dentro, na tela onde se emite documento fiscal. Virou
  dois tokens: `#8A5714` para texto (5.74) e o original só para preenchimento.

- **DESC-3 — A paleta de marca não é escala categórica, e a resposta não foi consertá-la.**
  O validador da `dataviz` reprovou os cinco tons: ΔE 4.0 entre cinza e vermelho em protan.
  Re-escaloná-los teria sido a correção óbvia e errada — olhando de novo, **nenhum dos três
  gráficos tem mais de uma série**: a categoria das recusas está no eixo, não na cor. Uma
  cor por gráfico, nenhuma paleta categórica.

- **DESC-4 — Dois bugs que só a execução contra o Postgres mostrou.** Uma constante de SQL
  reusada nas duas formas do agregado (a por sessão não trazia `session_id` no SELECT, e a
  lista de conversas mostrava custo `—` enquanto as métricas mostravam US$ 0,069 para o
  mesmo turno); e `ultima_atividade` tocada só na abertura da sessão, exibindo uma conversa
  de 19 segundos como *"atendimento médio: 0 ms"*. **Nenhum dos dois seria pego pela
  suíte**: a implementação em memória não executa SQL, e a ADR-011 não tem camada de
  integração de propósito. O guarda que entrou afirma a **forma** da consulta, que é onde o
  erro estava. Fica registrado que este é o custo declarado da ADR-011, e que a verificação
  manual roteirizada foi o que o cobriu — exatamente como a spec previa.

- **DESC-5 — O gerador do cliente TypeScript encontrou um erro de contrato.**
  `EventoDoPainel` é um alias com discriminador, não um `BaseModel`: o Pydantic não cria um
  `$def` para ele, e o `$ref` por nome apontava para nada. O `openapi-typescript` parou o
  build. É o portão de contrato funcionando antes de existir tela.

- **DESC-6 — `python -m vendinha.openapi > openapi.json` corrompia o arquivo no Windows.**
  O stdout do console é cp1252, e a redireção quebrava no primeiro `ç` de uma descrição de
  campo. O comando passou a escrever o arquivo com encoding explícito. Um portão de contrato
  que só funciona em metade das máquinas do time é pior do que nenhum.

- **DESC-1 — `ui-ux-pro-max` foi vendorizado, e o ADR-009 diz que ele fica como plugin.** A skill
  apareceu em `.claude/skills/ui-ux-pro-max/` (3,6 MB, 70 arquivos) junto com um `skills-lock.json`
  **na raiz**, que duplica o `.claude/skills.lock.json` que o ADR-009 estabeleceu como fonte única
  da origem fixada por SHA. São duas questões separadas: (a) vendorizar ou manter como plugin — o
  ADR-009 recusou vendorizar por causa do volume de assets binários, e 3,6 MB é menos do que os
  16 MB que ele cita, então a premissa mudou e o ADR pode ser revisitado; (b) o lockfile duplicado,
  que é uma segunda fonte de verdade sobre a mesma coisa e precisa sumir de um dos dois lugares.
  **Parado para decisão do PO** — não commitado nesta branch.

### O que foi entregue, por requisito

| REQ | Onde | Prova |
|---|---|---|
| 1 | `backend/vendinha/openapi.py`, `frontend/src/api/schema.d.ts` | job `contrato` no CI compara e reprova o drift |
| 2 | `backend/vendinha/telemetria.py` | tabelas `sessao` e `turno`; mensagens vêm do checkpointer |
| 3 | `backend/vendinha/eventos.py` | fila limitada, descarte do mais antigo, `AtrasoNoStream` |
| 4 | `backend/vendinha/admin.py` | 7 rotas GET, `tests/security/test_admin_boundary.py` |
| 5 | `backend/vendinha/precos.py`, `data/precos-modelos.json` | `None` e nunca zero; `tests/unit/test_painel.py` |
| 6 | `GET /eventos/sessao/{id}` | cartão da NF aparece no widget sem o cliente perguntar |
| 7 | `frontend/src/site/Site.tsx` | conteúdo do catálogo real; bundle sem JS do painel |
| 8 | `frontend/src/site/Widget.tsx`, `useConversa.ts` | estados honestos, sem prazo prometido |
| 9 | `frontend/src/site/Composicao.tsx` | veredito como o validador devolveu, motivo tipado |
| 10 | `frontend/src/admin/dados.ts` | um assinante, invalidação por evento, zero polling |
| 11 | `frontend/src/admin/Telas.tsx` (`Fila`) | confirmação repete razão social, CNPJ e total |
| 12 | `Telas.tsx` (`Rastreabilidade`) | args da tool ao lado do retorno, por turno |
| 13 | `Telas.tsx` (`Pedidos`, `Metricas`), `metricas.py` | KPIs somados em `Decimal` no backend |
| 14 | `Telas.tsx` (`Config`) | `editavel: false` é literal no contrato |
| 15 | `docs/design/sistema-visual.md` | commitado antes do primeiro componente |

### Verificação manual registrada

Contra a API real, com Postgres e um modelo de verdade (`anthropic:claude-haiku-4-5`):

| O que | Resultado |
|---|---|
| `/admin/*` sem token, com token errado, e sem `OPERADOR_API_TOKEN` no ambiente | 401 nas três |
| `/admin/*` com o token certo | 200 |
| Preflight de CORS de `http://localhost:5173` | `allow-origin` e `X-Operador-Token` liberados |
| Stream do painel durante uma conversa | `sessao_iniciada` → `mensagem` → `composicao_avaliada` → `mensagem`, com heartbeat |
| Veredito no evento | idêntico ao da tool: total 484,00, 12,10/pessoa, teto 35 |
| Read model após a conversa | 1 turno, 63.321 entrada / 1.183 saída, p95 1.208 ms |
| Custo apurado | US$ 0,069236, e o mesmo número na lista e nas métricas |
| Recusas por motivo, após um happy hour a R$20/pessoa | `orcamento: 3`, `slot: 1` |
| Tempo médio de atendimento | 17.331 ms |
| KPIs numa janela vazia | conversão, ticket, p95 e custo **todos `null`**, nenhum zero |
| Prompts | `editavel: false`, sha e caminho por subagent |

**Não verificado por quem implementou, e deliberadamente:** a aparência das duas telas num
navegador e o comportamento de reconexão com o backend derrubado. É a verificação
independente da spec, e o roteiro dela está em `S-07-roteiro-de-demo.md`.

## Definition of Done

- [ ] Todos os requisitos CONFORMES no relatório de verificação
- [ ] CI verde (lint, typecheck, testes, evals)
- [ ] PR com evidência (screenshot das duas abas + trace Langfuse)
- [ ] Relatório `/fechar-spec` anexado com veredito APROVADO
