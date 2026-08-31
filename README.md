<p align="center">
  <img src="docs/img/jornada-de-dados.png" alt="Jornada de Dados — Projetos reais de IA e Dados, um desafio por mês" width="820">
</p>

<h1 align="center">Vendinha</h1>

<p align="center">
  <strong>Agente de vendas de ponta a ponta para eventos corporativos.</strong><br>
  Projeto de <strong>agosto de 2026</strong> do <a href="https://github.com/suajornadadedados/desafio-jornada/tree/main/desafio-vendas">Desafio Jornada de Dados</a> — tema do mês: <strong>Vendas</strong>.
</p>

<p align="center">
  <a href="https://github.com/suajornadadedados/vendinha-jornada/actions/workflows/ci.yml"><img src="https://github.com/suajornadadedados/vendinha-jornada/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white" alt="Python 3.12">
  <img src="https://img.shields.io/badge/LangGraph-orquestra%C3%A7%C3%A3o-1C3C3C" alt="LangGraph">
  <img src="https://img.shields.io/badge/evals-23%20casos-0083F9" alt="23 casos de eval">
  <img src="https://img.shields.io/badge/testes-1021%20em%202%20camadas-26D6FC" alt="1021 testes">
</p>

> ### O LLM decide o que dizer. O código decide o que pode ser feito.
>
> Esta frase governa cada decisão do repositório. Preço, total, quantidade, corte por alérgeno
> e emissão de documento fiscal **nunca** passam pelo modelo.

---

## O desafio

O [Desafio Jornada de Dados](https://github.com/suajornadadedados/desafio-jornada) publica, de
agosto a dezembro de 2026, **um pedido de cliente real por mês** — sem stack, sem arquitetura,
sem numeração de requisitos. Quem participa faz o discovery, documenta, decide e constrói no
próprio repositório.

O desafio de agosto é o **Agente de Vendas de Ponta a Ponta**. O cliente chega falando:

> *"Preciso de um presente pra minha sogra, que ama vinho tinto."*
>
> Filtro e categoria não resolvem essa frase. É por isso que existe um agente.

Ele quer oito coisas e teme outras seis. **Nenhum desses pedidos é um requisito de engenharia —
traduzir é o trabalho.** A tradução completa, com o que foi recusado em cada ponto, está em
[`docs/requisitos.md`](docs/requisitos.md).

## O que é a Vendinha

Um empório mineiro digital — queijos, cafés, doces, cachaças, petiscos — que vende **para
empresas**. Quem conversa com o agente é quem organiza o evento: gestora de RH, office manager,
assistente de diretoria. Ela recebeu uma tarefa com número e vai prestar contas ao financeiro.

> *"Café da manhã pra 40 pessoas, R$35 por cabeça, tem uma pessoa celíaca no time, e precisa
> chegar antes de quinta."*

O pedido não é um produto: é um **problema de composição**. O agente investiga o evento, monta a
cesta inteira, o código valida orçamento, slots e restrições, e o fluxo segue até o link de
pagamento e a emissão de NF-e com aprovação humana.

> **O case nasceu B2C e virou B2B no meio do projeto.** Uma pergunta de restrição única com 50
> itens no catálogo é respondível por inspeção — quem assiste conclui, com razão, que aquilo é um
> filtro de e-commerce com skin de chat. Trocar o **comprador** (e não o domínio) foi a decisão:
> [ADR-013](docs/adr/ADR-013-comprador-corporativo-composicao.md).

## A cena que resume o projeto

```
1. O atendente propõe     uma cesta de café da manhã para 40 pessoas
2. validar_composicao     "R$163 por pessoa — o teto é R$150. E faltou bebida quente."
                          ↳ recusado, com motivo. O modelo ajusta.
3. criar_pedido revalida  a mesma conferência roda de novo no servidor, na hora de fechar
```

Escolher *quais* produtos combinam com um time jovem numa sexta à tarde continua sendo do modelo
— é onde ele é insubstituível. O que o código não delega é a **conta** e o **corte**: quanto dá,
quantos atende, e o que não pode entrar. As duas chamadas ficam no mesmo trace: a fronteira deixa
de ser prosa e vira algo que dá para **assistir**.

A validação que passou pelo modelo nunca é a que autoriza.

---

## As duas telas

Duas abas, lado a lado: a mesma API servindo o cliente e o operador.

### `/` — o cliente é atendido

<p align="center">
  <img src="assets/site.png" alt="Landing da Vendinha com o chat aberto: o agente pede o evento, o orçamento por pessoa e as restrições" width="880">
</p>

A conversa começa pedindo o **evento**, não o produto. A landing é o simulador do canal do
cliente, e é honesta sobre o que existe: os tipos de evento são os que o validador conhece
(`composicao.TipoDeEvento`), os produtores e as regiões são os do catálogo real em
`data/catalogo/`, e não há um único número inventado de "clientes atendidos". O `0` de
*composições fora do orçamento apresentadas* é uma invariante testada, não uma meta de marketing.

### `/admin` — o operador vê o atendimento acontecer

<p align="center">
  <img src="assets/admin.png" alt="Painel do operador: visão geral com atendimentos, conversão, valor vendido, notas aprovadas e sugestões barradas na conferência" width="880">
</p>

O painel é **read-only** e atualiza sozinho por stream do barramento — não é polling. Repare em
*Sugestões barradas na conferência*: é a fronteira do ADR-001 exposta como métrica de operação —
quantas composições o código devolveu ao modelo, e por quê.

Num período sem atendimento, conversão e ticket médio aparecem como **traço**, nunca como zero.
Um painel que exibisse `0%` de conversão num dia sem conversa estaria afirmando algo falso sobre
um dia que não aconteceu.

---

## Como rodar

**Pré-requisitos:** Docker, Python 3.12, [uv](https://docs.astral.sh/uv/) e — para as telas —
Node 22. `make` é conveniência: cada alvo é uma linha de comando real, e `make help` lista todos.

### 1 · Infraestrutura e testes — sem nenhuma chave de API

```bash
cp .env.example .env       # nada precisa ser preenchido para subir a infra
make up                    # docker compose up -d --wait     (~6s até healthy)
make test                  # bash scripts/run-tests.sh       (unit + security)
make lint                  # ruff check . && ruff format --check .
make hooks                 # instala os portões locais (pre-commit)
```

### 2 · Conversar com o agente

```bash
make db-setup              # cria as tabelas (checkpointer, config, produto, pedido, nota, telemetria)
make seed                  # carrega os 65 produtos no Postgres e no Qdrant
make api                   # http://127.0.0.1:8000
```

No `.env`: `ANTHROPIC_API_KEY` (ou `OPENAI_API_KEY`) para a conversa, e **`OPENAI_API_KEY` também
para o `make seed`** — a Anthropic não oferece API de embedding, e a S-03 decidiu embedar pela
OpenAI. Isso contraria a letra do RNF-1 ("sem contas externas além da API key do modelo") e está
declarado assim de propósito ([D-1 da S-03](docs/specs/S-03-recomendacao-ancorada.md)).

### 3 · As duas telas

```bash
make web-install           # npm install --prefix frontend
make web                   # http://localhost:5173 (cliente) e /admin (operador)
```

| Aba | Onde | Quem é |
|---|---|---|
| Esquerda | `localhost:5173/` | a compradora corporativa sendo atendida |
| Direita | `localhost:5173/admin` | o operador vendo o atendimento acontecer, e aprovando a nota |

Para **aprovar a nota fiscal** é preciso mais uma linha no `.env`: `OPERADOR_API_TOKEN`. Sem ela,
`GET /operador/fila` e as rotas de aprovar/rejeitar respondem 401 — é o lado seguro, porque essa
fila lista dados de compradoras e autoriza uma emissão irreversível. O token vai no header
`X-Operador-Token`; a nota que sai é um mock fiel ao layout NF-e modelo 55, com tarja **SEM VALOR
FISCAL**, e nenhuma conta externa é necessária para chegar até ela.

▶ **Roteiro completo da demonstração, cena a cena:**
[`docs/specs/S-07-roteiro-de-demo.md`](docs/specs/S-07-roteiro-de-demo.md)

<details>
<summary><strong>Problemas comuns no setup</strong> — porta ocupada, CORS, <code>make</code> no Windows</summary>

<br>

**A API recusa subir dizendo que falta catálogo.** É deliberado: sem catálogo o atendente responde
"não encontrei nada" com toda a sinceridade, o que parece falha do modelo e é falha de setup. A
mensagem diz qual dos dois comandos falta (`make db-setup` ou `make seed`).

**A porta 5173 é fixa (`strictPort`)** porque ela está na allowlist de CORS do backend
(`CORS_ORIGINS` no `.env`). Cair para a 5174 em silêncio produziria um erro de CORS numa API
perfeitamente de pé — a falha mais confusa de diagnosticar do conjunto.

**Porta ocupada?** `POSTGRES_PORT`, `QDRANT_HTTP_PORT` e `QDRANT_GRPC_PORT` no `.env` mudam apenas
a porta exposta no host; dentro da rede do compose nada muda. É o caso quando você já tem um
Postgres nativo em 5432 ou outro projeto ocupando 6333.

**Sem `make` no Windows?** O Git Bash não traz `make`. Instale com
`winget install ezwinports.make` (ou use WSL) — ou rode a linha que está dentro do alvo:
`make -n <alvo>` mostra exatamente o que ele executaria.

**Base suja de teste antes de uma demo?** `make limpar-demo` zera conversas, pedidos e notas e
**preserva** o catálogo e a configuração de modelo.

**O painel não tem autenticação.** O `OPERADOR_API_TOKEN` é pedido numa tela de conexão e vale só
para a aba. É aceitável numa demo local e não é aceitável num host público
([ADR-015](docs/adr/ADR-015-painel-de-observacao-do-cliente.md)).

</details>

---

## Arquitetura

![Arquitetura do produto: React+Vite, FastAPI, LangGraph com supervisor e subagents, Postgres, Qdrant, Mercado Pago sandbox, emissor de NF e Langfuse, tudo em Docker](docs/img/arquitetura-produto.svg)

| Camada | Escolha | A decisão que a exigiu |
|---|---|---|
| Orquestração | **LangGraph** | `interrupt` com estado **persistido** em checkpointer — a pausa antes da NF não é UX, é primitivo ([ADR-003](docs/adr/ADR-003-hitl-interrupt-nf.md)) |
| API | **FastAPI** | Pydantic → OpenAPI → cliente TypeScript gerado; SSE nativo para o chat ([ADR-004](docs/adr/ADR-004-ports-adapters-mock-first.md)) |
| Dados | **PostgreSQL + Qdrant** | Postgres é a fonte da verdade de preço, `rendimento` e `contem` **e** o checkpointer do grafo; Qdrant carrega o catálogo semântico e **nenhum fato** |
| Observabilidade | **Langfuse Cloud** | Trace por sessão com PII mascarada **na origem** ([ADR-007](docs/adr/ADR-007-langfuse-pii.md) · [ADR-010](docs/adr/ADR-010-langfuse-cloud.md)) |
| Frontend | **React + Vite** | Dois consumidores da mesma API: chat do cliente e painel do operador |
| Pagamento | **Mercado Pago sandbox** | Port + adapter; só ambiente de teste, nenhum dinheiro real |
| Documento fiscal | **NFEmitter: Mock (default) / Homologação (opcional)** | Mock fiel ao layout NF-e modelo 55; certificado e CNPJ ficam fora do caminho do quickstart |

Cada linha da tabela aponta para uma decisão registrada **antes** de existir código. A tabela
inteira, com a alternativa recusada em cada linha, está em
[`docs/arquitetura.md`](docs/arquitetura.md).

### Um supervisor, dois subagents — e a fronteira é de permissão

| Agente | Tools registradas | Pode escrever? |
|---|---|---|
| `supervisor` | roteamento | não |
| `recomendacao` | `buscar_produtos`, `detalhar_produto`, `consultar_preco`, `validar_composicao`, `consultar_pedido` | **não** — read-only por construção |
| `checkout` | as cinco acima, mais `validar_dados_cliente`, `criar_pedido`, `gerar_link_pagamento` | sim, com schema rígido |

`desconto` **não existe** como tool em nenhum registro. Não é uma ação negada por prompt: ela não
está lá. `emitir_nf` e `registrar_aprovacao` também não existem e nunca vão existir — emitir nota
é ato que exige uma pessoa, e o registro da aprovação é uma rota do operador. Um teste da camada
`security` falha se qualquer tool de escrita vazar para o registro do subagent de recomendação.

### Onde a IA entra — e onde ela não entra

| Etapa | Quem resolve |
|---|---|
| Entender o evento ("café da manhã pra 40, R$35 por cabeça, tem um celíaco") | **LLM** — o valor está aqui |
| Escolher os produtos da composição | LLM **ancorado em RAG** |
| **Validar a composição** (total, slots, restrições, rendimento) | **Código — nunca o modelo** |
| Informar preço / calcular total | **Código/banco — nunca o modelo** |
| Coletar dados da empresa (razão social, CNPJ, endereço) | LLM coleta, **código valida** |
| Gerar link de pagamento | Tool determinística com permissão |
| Confirmar pagamento | Webhook idempotente — **zero IA** |
| Emitir NF | Tool + **HITL obrigatório** |

A jornada completa está em [`docs/jornada.md`](docs/jornada.md), e é **requisito normativo** do PRD.

---

## O que o cliente pediu, e o que o repositório entrega

| O que ele quis | Onde isso vive |
|---|---|
| Recomenda pelo que o cliente precisa | RAG sobre Qdrant + composição validada em código ([S-03](docs/specs/S-03-recomendacao-ancorada.md) · [S-11](docs/specs/S-11-composicao-de-evento.md)) |
| Preço e estoque sempre do banco | Todo fato por tool; `test_recommendation_tools.py`, `test_groundedness.py` |
| Conversa que fecha a venda | Checkout no fluxo do agente ([S-04](docs/specs/S-04-fronteira-pagamento.md)) |
| Aprovação humana no irreversível | `interrupt` do LangGraph + fila do operador ([S-05](docs/specs/S-05-hitl-nf.md)) |
| Cada atendimento auditável | Trace por sessão desde o commit 1 ([S-02](docs/specs/S-02-agente-observavel.md)) |
| Custo visível e com teto | Budget cap por sessão, timeout por tool, custo somado em `Decimal` no backend |
| Dados de clientes protegidos | Mascaramento de PII na origem, antes do envio |
| Sua equipe coloca para rodar | Quickstart em ≤ 10 min, tudo mockado, harness versionado junto |

| O que ele temeu | O que impede |
|---|---|
| Alucinação de produto, preço ou atributo | `fato_inventado` reprova a **suíte inteira** de evals |
| Manipulação conversacional ("desconto na lábia") | A ação não existe no registro; 7 casos adversariais, 100% de resistência exigida |
| Documento fiscal emitido sem revisão | `tests/security/test_hitl_invariant.py`: não existe caminho até `emitir_nf` sem aprovação registrada |
| Mágica sem rastro | Painel de observação próprio + Langfuse como visor interno |
| Conta de IA fora de controle | Budget cap: chegou no teto, o sistema corta |
| Dado pessoal vazando pelos cantos | `tests/security/test_pii_redaction.py` é invariante de release |

---

## Qualidade: os portões

**Teste aqui não nasce de cobertura, nasce de risco.** A matriz
[`docs/riscos.md`](docs/riscos.md) declara R1–R10 → mitigação → spec → verificação, e
[`docs/testes.md`](docs/testes.md) diz onde cada verificação vive. Risco sem verificação é desejo,
não requisito.

### Duas camadas de teste, e só duas ([ADR-011](docs/adr/ADR-011-duas-camadas-de-teste.md))

| | Pergunta | O que produz | Tamanho |
|---|---|---|---|
| `tests/unit/` | A função faz a conta certa? | correção | 924 casos |
| `tests/security/` | Existe caminho de código até a ação proibida? | **garantia** | 97 casos |

Nenhuma das duas precisa de contêiner — é consequência de **não existir camada de integração**.

Um teste unitário verde diz que o total foi somado direito. Um teste de segurança verde diz que o
subagent de recomendação **não possui** a tool de escrita — não que ele foi instruído a não usá-la.

### 23 casos de eval, escritos antes do agente existir

`evals/` tem **16 casos golden** e **7 adversariais**, versionados e protegidos por CODEOWNERS —
o que impede que um PR com eval vermelho fique verde editando o caso que reprovou. Cada arquivo
carrega o critério que o reprova, ao lado do exemplo que o motivou: **não existe arquivo de rubric
neste repositório** ([ADR-006](docs/adr/ADR-006-evals-como-gate.md)).

Não há nota agregada, não há média, não há "9 de 10 passaram". Duas famílias de falha reprovam a
suíte inteira: **`fato_inventado`** e **`acao_fora_da_allowlist`**.

```bash
make evals-check           # valida os casos contra o schema — sem agente, sem API
make evals-afetadas        # só as sub-suítes que o seu diff pode ter mudado (o que o CI faz no PR)
make evals                 # a suíte inteira, 23 casos (o que o CI faz no pós-merge)
```

O gate roda **em camadas** ([ADR-014](docs/adr/ADR-014-gate-de-evals-em-camadas.md)): a parte
determinística sempre, as sub-suítes afetadas pelo diff no PR, a suíte inteira depois do merge.

### O que o CI exige em todo PR

`commitlint` · `lint` (ruff + actionlint) · `test` (unit + security) · `secrets` (gitleaks) ·
`skills-drift` · `typecheck` (mypy strict no backend **e** na suíte) · `contrato` (OpenAPI e
cliente TS regerados batem com o commitado) · `evals`.

A `main` é protegida e todos são obrigatórios. Mudar um campo no backend sem rodar `make types`
quebra o build, em vez de quebrar a tela.

---

## Como este repositório foi construído

![Fluxo de construção do repositório: pedido do cliente, discovery, harness, portões e só então código](docs/img/fluxo-discovery.svg)

As quatro fases aconteceram **inteiras** antes de qualquer código de produto. O método é parte da
entrega: Spec-Driven Development com autor e revisor separados
([ADR-005](docs/adr/ADR-005-sdd-autor-revisor.md)).

1. Cada spec = uma issue, uma branch `spec/s-XX-nome` e uma sessão nova do Claude Code.
2. Cada task da spec = um commit (Conventional Commits, em inglês).
3. **Verificação independente antes do PR, não antes do merge.** O subagente
   `verificador-de-spec` — com o prompt versionado em `.claude/agents/`, recebendo o id da spec e
   mais nada — gera o relatório em `docs/specs/relatorios/`. Sem veredito, não existe PR.
4. As correções entram na mesma branch. O PR nasce já com elas dentro.
5. Merge por squash, com os checks obrigatórios verdes.

Instrução escrita à mão por quem implementou não é verificação independente. Com o prompt no
repositório, enviesar a revisão passa a exigir um commit naquele arquivo — no diff, onde o PO vê.
O portão é código: `.claude/hooks/gate-pr.py` recusa `gh pr create` numa branch de spec sem
relatório aprovado.

### Roadmap das specs

| Spec | Entrega | Status |
|---|---|---|
| [S-00](docs/specs/S-00-fundacao.md) | Fundação do repositório | ✅ entregue |
| [S-01](docs/specs/S-01-discovery-como-codigo.md) | Discovery como código | ✅ entregue |
| [S-02](docs/specs/S-02-agente-observavel.md) | Agente base observável | ✅ entregue |
| [S-03](docs/specs/S-03-recomendacao-ancorada.md) | Recomendação ancorada (RAG) | ✅ entregue |
| [S-10](docs/specs/S-10-discovery-b2b.md) | Discovery B2B — comprador corporativo | ✅ entregue |
| [S-11](docs/specs/S-11-composicao-de-evento.md) | Composição de evento | ✅ entregue |
| [S-04](docs/specs/S-04-fronteira-pagamento.md) | Fronteira de permissão + pagamento | ✅ entregue |
| [S-05](docs/specs/S-05-hitl-nf.md) | HITL + emissão de NF | ✅ entregue |
| [S-06](docs/specs/S-06-qualidade-como-gate.md) | Qualidade como gate (EDD) | ✅ entregue |
| [S-07](docs/specs/S-07-frontend-integrado.md) | Frontend integrado e API de observação | ✅ entregue |
| [S-08](docs/specs/S-08-producao.md) | Deploy — ambiente empacotado (api, frontend e nginx) | ⏳ aprovada, não iniciada |

> **Ordem de execução ≠ ordem dos ids.** S-10 e S-11 (o pivô B2B) rodaram **entre a S-03 e a
> S-04**. Renumerar sairia mais caro que um id fora de ordem — a nota no topo da S-10 explica.

---

## Mapa da documentação

Leia nesta ordem — cada documento consome o anterior:

| # | Documento | O que resolve |
|---|---|---|
| 1 | [`docs/requisitos.md`](docs/requisitos.md) | Do pedido do cliente em prosa à decisão de engenharia. Separar desejo de requisito |
| 2 | [`docs/jornada.md`](docs/jornada.md) | Onde a IA entra no fluxo, etapa por etapa, e por quê |
| 3 | [`docs/riscos.md`](docs/riscos.md) | Matriz R1–R10: risco → mitigação → spec → verificação |
| 4 | [`docs/PRD.md`](docs/PRD.md) | Requisitos do produto, objetivos e não-objetivos |
| 5 | [`docs/decisoes.md`](docs/decisoes.md) | Mapa D1–D18 → os 15 [ADRs](docs/adr/) |
| 6 | [`docs/arquitetura.md`](docs/arquitetura.md) | Os dois diagramas: como o repo nasceu e como o produto se sustenta |
| 7 | [`docs/testes.md`](docs/testes.md) | Risco → teste: o seam de cada verificação e o critério de aceite |
| 8 | [`docs/specs/`](docs/specs/) | S-00 a S-11, com os [relatórios de verificação](docs/specs/relatorios/) |
| 9 | [`evals/`](evals/) | A régua de qualidade do agente, escrita antes do agente existir |

Complementos: [`docs/harness/skills.md`](docs/harness/skills.md) (o harness versionado),
[`docs/harness/medicao-de-evals.md`](docs/harness/medicao-de-evals.md) (a variância da régua),
[`docs/design/sistema-visual.md`](docs/design/sistema-visual.md),
[`docs/workshop/github-setup.md`](docs/workshop/github-setup.md) (proteção da main e CD).

### O harness também é versionado

Quem clona o repositório recebe as regras da sessão junto com o código: `CLAUDE.md`, os rituais em
`.claude/commands/` (`/escrever-spec` · `/entregar-spec` · `/fechar-spec` · `/verificar-spec` ·
`/registrar-adr`), o prompt do revisor em `.claude/agents/`, o hook `gate-pr.py` e as skills
vendorizadas com origem fixada por SHA
([ADR-009](docs/adr/ADR-009-skills-vendorizadas.md)).

```bash
bash scripts/vendor-skills.sh --check   # .claude/skills/ bate com o lockfile
bash scripts/gen-skills-doc.sh --check  # docs/harness/skills.md em dia
```

Editar uma skill vendorizada à mão faz o CI reprovar o PR. Para adaptar comportamento ao projeto,
edite `.claude/skills/vendinha-harness/SKILL.md`.

---

## Fora de escopo — e por quê

Nada aqui é omissão silenciosa; cada linha tem motivo registrado em
[`docs/PRD.md` §3](docs/PRD.md).

- **NF com validade fiscal real** — apenas o mock fiel; não há adapter de homologação SEFAZ.
  *Certificado e CNPJ reais custam mais do que entregam numa demonstração, e a lacuna que isso
  deixa na R8 está declarada em `docs/testes.md` §2 em vez de coberta por um teste vazio.*
- **Dinheiro real** — apenas sandbox do Mercado Pago.
- **Gestão de estoque, frete e logística** — o cliente pede a *informação* correta, não um sistema
  de gestão. `disponivel` e `prazo_estimado` são campos lidos, e o eval reprova se o agente
  inventar qualquer um dos dois.
- **Autenticação de clientes finais, histórico entre sessões, multi-tenancy.**
- **CRUD administrativo** — o painel do operador é read-only; prompt não é editável pela interface.
- **Preço escalonado por faixa de quantidade** — seria legítimo, mas daria a R1 uma segunda forma
  de estar errado em troca de realismo que a demonstração não precisa.

---

## Créditos

Construído por **Caio Oliveira** como estudo de caso público de decisões de engenharia em projetos
com IA, para o desafio de agosto de 2026 da [Jornada de Dados](https://suajornadadedados.com.br).

- 🎯 Enunciado do desafio: [suajornadadedados/desafio-jornada · desafio-vendas](https://github.com/suajornadadedados/desafio-jornada/tree/main/desafio-vendas)
- 🎬 Deck da apresentação: [`docs/workshop/apresentacao.html`](docs/workshop/apresentacao.html)
- 🧭 Como contribuir com o seu próprio projeto: fork → branch → cartão → pull request → merge

> A conversa é do atendente. A conta, o corte e o documento são do sistema.
> E a palavra final continua sendo da sua equipe.
