# Arquitetura — Vendinha

> Este documento vem **depois** de `docs/requisitos.md`, `docs/jornada.md`, `docs/riscos.md`,
> `docs/PRD.md` e dos ADRs — nessa ordem, e não por acaso. A arquitetura aqui não é ponto de
> partida: é **consequência**. Cada linha de stack desta página aponta para uma decisão que já
> estava registrada antes de existir código.

**Regra que governa o desenho inteiro:**
> O LLM decide o que dizer. O código decide o que pode ser feito.

---

## 1. Como o repositório foi construído — antes da primeira linha de código

![Fluxo de construção do repositório: pedido do cliente, discovery, harness, portões e só então código](img/fluxo-discovery.svg)

O enunciado entrega um cliente falando. Da tradução em diante, o repositório é o único lugar
onde a decisão existe. As quatro fases acima aconteceram **inteiras** antes de qualquer código
de produto:

| Fase | O que entra no repositório | O que isso resolve |
|---|---|---|
| **0 · O pedido** | nada ainda — só a leitura do enunciado | separar desejo de requisito |
| **1 · Discovery** | `requisitos.md` → `jornada.md` → `riscos.md` → `PRD.md` → `decisoes.md` + `adr/` → `specs/` | cada documento consome o anterior; risco sem verificação é desejo |
| **2 · Harness** | `CLAUDE.md`, `.claude/commands/`, `.claude/skills/` | **P1** — contexto volátil: o que eu expliquei uma vez vira artefato versionado |
| **3 · Portões** | `.github/`, `commitlint.config.cjs`, CODEOWNERS, `main` protegida | **P2** — sem portão: o `CLAUDE.md` pede, o CI impõe |
| **4 · Execução** | S-00 → S-08, uma spec por branch e por sessão | **P3** — processo invisível: o histórico vira o argumento |

---

## 2. A stack — e a decisão que obrigou cada linha

| Camada | Escolha | A decisão que a exigiu | Alternativa recusada |
|---|---|---|---|
| Linguagem | **Python 3.12** | Ecossistema de agente e RAG maduro; contratos Pydantic em toda fronteira (RNF-5) | Node no backend: tipagem boa, ecossistema de agente mais raso |
| Orquestração | **LangGraph** | D5 · ADR-003 — `interrupt` com estado **persistido** em checkpointer. A pausa antes da NF não é UX, é primitivo | Agente em loop com um `if` no meio: pausa que morre junto com o processo |
| Observabilidade | **Langfuse Cloud** | D10 · ADR-007 — trace por sessão com mascaramento de PII **na origem**; D13 · ADR-010 — é o mascaramento que garante a privacidade, não a topologia, então a hospedagem vira questão de custo operacional | LangSmith: com mascaramento na origem a PII não sai de nenhum jeito — o que falta é a saída. Langfuse é open-source: trocar nuvem por self-hosted é variável de ambiente, não reescrita |
| API | **FastAPI** | ADR-004 — Pydantic → OpenAPI → cliente TypeScript gerado; SSE nativo para o streaming do chat | Flask/Django: OpenAPI não sai de graça |
| Dados | **PostgreSQL + Qdrant** | Postgres é a fonte da verdade de preço, `rendimento` e `contem` **e** o checkpointer do grafo (RNF-6); Qdrant carrega o catálogo semântico e nenhum fato | pgvector: um serviço a menos, mas fundiria busca semântica com fonte da verdade |
| Frontend | **React + Vite** | Dois consumidores da mesma API: chat do cliente e fila do operador (RF-4) | Next/SSR: nada aqui precisa de SEO |
| Empacotamento | **Docker + compose** | *"sistema que sua equipe consiga colocar para rodar"*: um comando, tudo mockado (RNF-1) | Instruções de instalação num README |
| Pagamento | **Mercado Pago sandbox** | Requisito do enunciado: só ambiente de teste. Port + adapter (ADR-004) | Gateway real: dinheiro de verdade num projeto de demonstração |
| Documento fiscal | **NFEmitter: Mock, e só ele** | ADR-004 — mock fiel ao layout NF-e modelo 55, com tarja SEM VALOR FISCAL. O port continua sendo port: `NF_EMITTER=homologacao` é um nome válido que **recusa alto** por não ter adapter, em vez de cair no mock em silêncio | Emissão real: certificado e CNPJ no caminho do quickstart |

---

## 3. O desenho do produto

![Arquitetura do produto: React+Vite, FastAPI, LangGraph com supervisor e subagents, Postgres, Qdrant, Mercado Pago sandbox, emissor de NF e Langfuse, tudo em Docker](img/arquitetura-produto.svg)

### 3.1 Quantos agentes, e por que essa divisão

Um **supervisor** roteia a conversa e **dois subagents** executam. A divisão não é organizacional
— é a **fronteira de permissão** (ADR-002):

| Agente | Tools registradas | Pode escrever? |
|---|---|---|
| `supervisor` | roteamento | não |
| `recomendacao` | `buscar_produtos`, `detalhar_produto`, `consultar_preco`, `validar_composicao`, `consultar_pedido` | **não** — só read-only |
| `checkout` | as quatro acima, mais `validar_dados_cliente`, `consultar_pedido`, `criar_pedido`, `gerar_link_pagamento` | sim, com schema rígido |

`desconto` **não existe** como tool em nenhum registro. Não é uma ação negada por prompt: ela
não está lá. Um teste da camada `security` falha se qualquer tool de escrita vazar para o
registro do subagent de recomendação (R2, R4).

**`emitir_nf` e `registrar_aprovacao` também não existem, e nunca vão existir** (S-05, D-3).
Emitir nota é ato que exige uma pessoa e o registro da aprovação é uma rota do operador —
nenhum dos dois é ação de agente. A emissão é disparada pela retomada do grafo fiscal a partir
da decisão gravada; o agente **lê** o desfecho por `consultar_pedido`, e é só.

`consultar_pedido` está nas duas lanes desde a S-04 (DESC-5 daquela spec): ler pedido é
leitura, e deixá-la só no checkout fazia quem voltava para perguntar sobre um pedido antigo
cair na lane que não sabia responder — sem composição aprovada nesta conversa, não havia
handoff. Na S-05 ela passou a carregar também o estado da nota.

**O checkout também lê, e isso não move a fronteira.** O que o ADR-002 protege é a *ação*,
nunca a *consulta*: a invariante é "`recomendacao` não escreve", jamais "`checkout` não lê".
Um turno de checkout em que o cliente troca um item precisa reconferir preço e revalidar a
composição — sem as tools de leitura ele teria que voltar de lane, e o cliente veria a conversa
recuar. É o que o corpus já declarava: o `tools.permitidas` de `golden-003` e `golden-015`
lista as quatro de leitura ao lado de `criar_pedido` (S-04, D-1).

**Só a lane que atende o turno tem as tools ligadas.** O supervisor escolhe uma das duas na
porta do grafo, e cada lane carrega o próprio `ToolNode`: enquanto o turno corre na
recomendação, as tools de escrita não estão ligadas no modelo que fala. Um nó de tools
compartilhado ligaria a união das duas listas e a fronteira teria vazado pelo grafo com os
dois registros ainda descrevendo-a como correta.

**A transição para o checkout tem pré-condição de código.** O supervisor só consulta o modelo
sobre a rota depois que a transcrição já contém um veredito `aprovada: true` de
`validar_composicao` — fato produzido por `composicao.validar` sobre produtos lidos do
Postgres. E o roteador é obrigado a **citar** a fala que confirmou, conferida literalmente
contra as mensagens do cliente: um "pode fechar" plantado na descrição de um produto não é
fala de cliente e não abre nada (RF-2.1, R4).

`validar_composicao` fica no subagent **read-only** e isso não é descuido: propor não é side
effect. Ela não persiste nada — recebe uma lista de produtos e devolve um veredito com total,
valor por pessoa, quantas pessoas a composição atende e a lista de problemas. Quem escreve é
`criar_pedido`, no `checkout`, e ele **revalida** em vez de confiar (R10).

### 3.2 Onde entra o humano

Um ponto, e só um: **antes de `emitir_nf`**.

1. Pagamento confirmado por webhook (zero IA, idempotente, origem verificada).
2. O pedido entra em `aguardando_aprovacao_nf` e o grafo **pausa** — `interrupt` com estado
   persistido no checkpointer Postgres.
3. O operador vê a fila com os dados completos da nota e aprova ou rejeita.
4. A decisão é gravada com **quem e quando**; a retomada só existe a partir desse registro.

É impossível, por construção, emitir NF sem aprovação registrada — e isso é testado na camada
`security`, não prometido em prosa (ADR-003, ADR-011, RF-3.5, R3).

### 3.3 Onde o código recusa o modelo

O comprador é uma empresa e o pedido é um **evento**: N pessoas, orçamento por pessoa,
restrições alimentares, prazo (ADR-013). Isso parte a recomendação em duas responsabilidades
que não se misturam:

| Quem | O quê |
|---|---|
| **LLM** | Escolher *quais* produtos combinam com o time, a ocasião e o tom da empresa |
| **Código** | Somar em `Decimal`, derivar quantidade a partir do `rendimento`, exigir os slots do tipo de evento, cortar por `contem` |

O fluxo típico tem ida e volta, e é essa a intenção: o modelo propõe uma composição de R$163,
`validar_composicao` reprova contra um teto de R$150 nomeando o estouro e o slot faltante, o
modelo ajusta. As duas chamadas ficam no mesmo trace — a fronteira do ADR-001 deixa de ser
prosa e vira algo que dá para **assistir**.

Dois cortes valem ser explícitos:

- **`contem` (alérgenos) não entra no payload do Qdrant nem no texto embedado.** O payload leva
  só filtro estrutural, porque todo campo ali é um fato com duas moradas — e a segunda cópia é
  a que fica velha sem ninguém perceber. Alérgeno é o pior fato possível para ter cópia velha.
- **Slots são código.** *Café da manhã sem café* precisa ser uma frase executável; sem eles, o
  validador não teria nada objetivo para recusar e viraria opinião.

### 3.4 Gestão de falhas

| Falha | Comportamento |
|---|---|
| Gateway ou emissor fora do ar | Port + adapter: degradação graciosa e testes de contrato por adapter (ADR-004, R8) |
| Webhook duplicado | Idempotência por chave do evento — o efeito acontece uma vez só (RF-2.5) |
| Conversa longa / processo reiniciado | Checkpointer em Postgres; estado carrega identificadores, nunca payloads (RNF-6, R9) |
| Tool travada ou custo escalando | Timeout por tool e budget cap por sessão, medidos no mesmo trace (RNF-3, R6) |
| Modelo tentando ação fora da allowlist | A ação não existe no registro do subagent; a suite adversarial cobre a tentativa (R4) |
| Composição estourando orçamento ou violando restrição | `validar_composicao` reprova com motivo; `criar_pedido` revalida no servidor e recusa (R10) |
| Regressão de qualidade após mudar prompt | Evals golden e adversariais bloqueiam o merge (ADR-006, R7) |

### 3.5 Fluxo de dados, em uma passada

```
compradora corporativa → chat (SSE) → supervisor
   ├─ recomendação → Qdrant (semântica) + Postgres (preço, rendimento, contem)
   │        ↕ validar_composicao (código: total, slots, restrições)  ... o modelo propõe, o código recusa
   └─ checkout     → Postgres (pedido) + Mercado Pago sandbox (link)
                          ↓
                  webhook de pagamento (código puro)
                          ↓
                  ⏸ interrupt → operador aprova (registrado)
                          ↓
                  emitir_nf → NFEmitter (mock por padrão, destinatário PJ)
                          ↓
                  cliente recebe DANFE/XML no chat

  Langfuse Cloud observa tudo acima, desde o commit 1, com PII mascarada na origem (ADR-010).
```

---

## 4. O que esta arquitetura deliberadamente **não** faz

- Não guarda catálogo no prompt — nem parcialmente.
- Não calcula preço, total, quantidade ou desconto no modelo.
- Não deixa restrição alimentar depender do cuidado do modelo: `contem` é corte em código.
- Não permite emissão de documento fiscal sem registro de aprovação humana.
- Não escreve PII legível em trace ou log, em nenhum ambiente.
- Não sobe para produção sem os checks obrigatórios do CI verdes.

Cada item acima corresponde a uma linha de `docs/riscos.md` com uma verificação automatizada.
Risco sem verificação é desejo, não requisito.

---

## 5. Como regenerar as imagens

A fonte de cada diagrama é o **SVG** em `docs/img/` — texto, não binário, então o diff mostra
exatamente o que mudou. Os `.png` ao lado são exportações em 2x (3200×2120 e 3280×2160),
para slides e thumbnail de vídeo.

| Arquivo | Uso |
|---|---|
| `img/fluxo-discovery.svg` · `.png` | como o repositório nasceu, antes do código |
| `img/arquitetura-produto.svg` · `.png` | arquitetura do produto com a stack |

Depois de editar um SVG, regere os PNGs:

```bash
chrome --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2 \
  --window-size=1600,1060 --screenshot=docs/img/fluxo-discovery.png \
  docs/img/fluxo-discovery.svg

chrome --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2 \
  --window-size=1640,1080 --screenshot=docs/img/arquitetura-produto.png \
  docs/img/arquitetura-produto.svg
```
