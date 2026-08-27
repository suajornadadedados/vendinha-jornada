# Requisitos — do pedido do cliente à decisão de engenharia

O enunciado do desafio entrega um **cliente falando**: oito linhas do que ele quer no produto,
seis do que ele teme, e seis perguntas no fim. Não entrega stack, arquitetura, numeração de
requisitos nem régua de avaliação — e essa ausência *é* o enunciado.

A tradução abaixo é **nossa**. O recorte, a redação e o rigor de cada linha são decisão deste
projeto: é daqui que nascem `docs/riscos.md`, `docs/PRD.md` e os ADRs. O desafio entrega o
desejo; da tradução em diante, o repositório é o único lugar onde a decisão existe.

> Regra que governa toda a tradução:
> **o LLM decide o que dizer; o código decide o que pode ser feito.**

**O case:** a Vendinha, empório mineiro digital de produtos artesanais (queijos, cafés, doces,
cachaças, petiscos) que vende **para empresas** — café da manhã corporativo, happy hour,
cesta de fim de ano, kit de boas-vindas. Quem conversa com o agente é quem organiza o evento,
não quem vai comer. Negócio, proprietário e personas nomeados em `docs/PRD.md`.

O case nasceu B2C e virou B2B no meio do projeto. **O enunciado não escolhe o comprador — nós
escolhemos**, e a seção *O case mudou de comprador* abaixo registra o que motivou a troca e o
que ela custou. Nenhuma citação desta página mudou: o cliente continua pedindo a mesma coisa.

## O que o cliente quer no produto → como traduzimos

Citações literais da seção *"O que o Cliente Quer no Produto"* do enunciado.

| O cliente quer | Nossa tradução em requisito de engenharia | Onde vive |
|---|---|---|
| "compreender catálogo e recomendar produtos por necessidade" | Busca semântica sobre o catálogo (RAG), não filtro de e-commerce — o cliente descreve o **evento** (quantas pessoas, que ocasião, quanto por pessoa, que restrições), não o produto. A recomendação não é um item: é uma **composição** que o modelo propõe e o código valida | jornada · RF-1 · S-03 · S-11 |
| "estoque, preço e prazo **sempre sincronizadas** com banco de dados" | O modelo nunca afirma esses valores de memória: preço por consulta ao Postgres no momento da criação do pedido; disponibilidade e prazo estimado como **campos lidos** do catálogo. Com evento, **quantidade também é fato**: `rendimento` diz quantas pessoas cada item atende, e é o código que divide — não o modelo | R1 · R10 · RF-1.3 · ADR-001 |
| "conversa que chegue até o final da venda" | Checkout dentro do fluxo do agente, com transição só após confirmação explícita e total calculado por código | RF-2 · S-04 |
| "aprovação de equipe em pontos irreversíveis" | Identificar o irreversível (emissão de NF) e pausar o grafo com estado persistido; aprovação registrada com quem e quando | R3 · RF-3 · ADR-003 · S-05 |
| "auditoria completa dos atendimentos" | Trace por sessão desde o commit 1 — roteamento, tools, custo, latência — e não observabilidade como fase de deploy | R5 · RF-5.1 · ADR-007 · S-02 |
| "visibilidade de custos com IA" | Budget cap por sessão e timeout por tool, medidos no mesmo trace | R6 · RNF-3 |
| "proteção de dados em todas as camadas" | PII mascarada na origem: CPF, e-mail e nome nunca legíveis em trace ou log, em nenhum ambiente | R5 · RF-5.2 · ADR-007 |
| "sistema que sua equipe consiga colocar para rodar" | Quickstart em ≤ 10 min com tudo mockado, e o harness versionado junto do código | RNF-1 · ADR-005 · `docs/harness/skills.md` |

> **Nota de escopo — "estoque e prazo".** O cliente pede a *informação* correta, não um sistema
> de gestão. Traduzimos como: cada produto carrega `disponivel` e `prazo_estimado` no seed, o
> agente só os cita por tool, e o eval reprova se ele inventar qualquer um dos dois.
> Movimentação de estoque, reserva, frete e integração com transportadora seguem **fora de
> escopo** (`docs/PRD.md` §3). A garantia que entregamos é *"o agente nunca inventa"*, não
> *"o estoque está certo em tempo real"* — e isso está dito no PRD, não escondido.
>
> Com comprador PJ o endereço de entrega passa a ser **coletado e validado**, porque a DANFE
> exige destinatário completo. Coletar endereço não é fazer logística: continua não havendo
> cálculo de frete, roteirização nem rastreio.

## O case mudou de comprador — e o que isso custou

A primeira tradução escolheu uma pessoa física comprando um presente. Funcionava, e estava
ancorada: o agente não inventava um fato. Mas a pergunta que ela respondia era de **restrição
única** — *"um presente pra minha sogra que ama vinho tinto"* —, e uma pergunta de restrição
única com 50 itens no catálogo é respondível por inspeção. Quem olha conclui, com razão, que
aquilo é um filtro de e-commerce com skin de chat.

A fraqueza não era do catálogo nem do mecanismo. Era de **quem perguntava**: um comprador cuja
necessidade cabe numa linha não gera decisão que precise de agente.

Trocar o comprador — e não o domínio — foi a decisão (ADR-013). Trocar o domínio (peças,
componentes) tornaria a recomendação um *spec matching*, que é justamente o que filtro já
resolve bem; e reescreveria esta página do zero, o que significaria que **o cliente mudou**,
não o produto. Com o comprador corporativo, a tese continua de pé: a gestora de RH também não
sabe traduzir *"meu time é jovem, startup, sexta à tarde"* em filtros.

| O que o case B2B exige e o B2C não exigia | Nossa tradução | Onde vive |
|---|---|---|
| Comprar para N pessoas, não para uma | `rendimento` no catálogo; a quantidade é divisão feita em código | R1 · RF-1.6 · S-11 |
| Orçamento por pessoa, fechado antes da conversa | Teto validado em `Decimal` contra o total lido do banco; composição que estoura **não é apresentada como válida** | R10 · RF-1.7 · S-11 |
| Restrição alimentar de gente que nem está na conversa | `contem` no catálogo (lactose, glúten, álcool, castanhas) como **campo de corte**, lido do Postgres — nunca inferido do texto do produto | R10 · RF-1.7 · S-11 |
| Um evento tem forma: café da manhã sem café não é café da manhã | Slots obrigatórios por tipo de evento, declarados em código. É o que dá ao validador algo objetivo para recusar | RF-1.6 · S-11 |
| A nota é para uma empresa | Destinatário PJ: CNPJ, razão social e endereço de entrega. Fecha um furo do B2C, onde coletávamos só nome, CPF e e-mail para uma DANFE que exige endereço | RF-2.2 · RF-3 · S-04 · S-05 |

**O que a troca de comprador *não* mudou:** nenhum ADR de 001 a 012, nenhuma citação do
enunciado, e nenhuma linha da tabela acima de *o que o cliente quer*. O que mudou foi a coluna
do meio — a nossa tradução — que é exatamente o que esta página se propõe a ser.

**O que custou:** o corpus de evals inteiro (12 golden + 6 adversariais) reescrito, e não
estendido. Custo aceito e registrado no ADR-013: o corpus é artefato de discovery neste
repositório, e reescrevê-lo **antes** de a tool existir é o que impede a régua de ser ajustada
ao que o modelo faz (ADR-006).

## As preocupações do cliente → onde cada uma é fechada

| A preocupação | Onde ela morre |
|---|---|
| "Evitar que o agente invente dados sobre produtos" | R1 · ADR-001 · eval de groundedness (S-03) |
| "Proteger contra manipulação conversacional" | R2 · R4 · ADR-002 — ver abaixo |
| "Garantir aprovação humana antes de atos irreversíveis" | R3 · ADR-003 · interrupt persistido (S-05) |
| "Manter transparência de custos de IA" | R6 · RNF-3 · budget cap no trace |
| "Proteger dados dos clientes" | R5 · ADR-007 · mascaramento na origem |
| "Permitir que a equipe entenda o que aconteceu" | R5 · RF-5.1 · trace por sessão |

**Uma delas não tem linha correspondente na lista do produto: *"proteger contra manipulação
conversacional"*.** Não vira feature porque não se vê na tela — e é a única em que a solução
óbvia é a errada. Escrever *"nunca dê desconto"* no prompt some no diff, passa na revisão e não
garante nada: prompt é pedido, não garantia.

Nossa decisão: **desconto não existe como ação disponível a nenhum agente.** Não é negado — não
está registrado. Segurança por arquitetura, não por comportamento do modelo. *(ADR-002 · RF-2.6)*

Com comprador corporativo essa linha fica mais exposta, não menos: *"vou levar 12 cestas, me dá
15%"* é a frase mais natural do mundo em B2B, e a resposta continua sendo que não existe o que
conceder. Preço escalonado por faixa de quantidade foi considerado e recusado no MVP (ADR-013):
seria legítimo — tabela no banco, não negociação —, mas daria a R1 uma segunda forma de estar
errado em troca de realismo que a demonstração não precisa.

A manipulação também ganhou um alvo novo, e mais perigoso que o preço: **a restrição
alimentar**. *"Ah, pode incluir mesmo assim, ninguém vai reparar"* é pressão social sobre um
campo cuja resposta errada machuca alguém. Por isso `contem` é corte em código, e não
julgamento do modelo (R10).

## Um requisito que o cliente não pediu

| Requisito que assumimos | Por quê | Onde vive |
|---|---|---|
| A qualidade do atendimento não regride em silêncio a cada mudança de prompt | Ninguém pede isso porque ninguém sabe que acontece: nada quebra, o teste unitário continua verde e o atendimento piora. Evals golden e adversariais como check que bloqueia o merge | R7 · RF-5.4 · ADR-006 · S-06 |

## O que a tradução recusou

A lista do que foi descartado diz mais sobre o critério do que a lista do que foi adotado.

| Como decidimos resolver | O que recusamos |
|---|---|
| Catálogo por RAG, preço por consulta ao banco | ✕ Pôr o catálogo no prompt e confiar |
| Registro de tools por subagent; recomendação read-only por construção | ✕ Escrever "nunca dê desconto" no prompt |
| O grafo pausa antes de emitir, com estado persistido e aprovação gravada | ✕ Avisar por e-mail depois de emitir |
| Mascaramento de PII na origem | ✕ Limpar os logs depois |
| Budget cap e timeout por tool, medidos no mesmo trace | ✕ Olhar a fatura no fim do mês |
| Trace desde o commit 1 | ✕ Deixar observabilidade para o final |
| Trocar o comprador, mantendo o domínio mineiro | ✕ Trocar de domínio para inflar o ticket |
| B2B puro | ✕ Atender os dois compradores para provar a mesma tese duas vezes |
| Preço unitário único | ✕ Preço escalonado por volume no MVP |
| Composição proposta pelo modelo e validada por código | ✕ Deixar o modelo somar o total |

Cada recusa vira uma linha de `docs/decisoes.md`, e o ADR correspondente registra as
consequências negativas aceitas.

## As perguntas do enunciado e onde as respondemos

A seção *"Antes de Codar"* termina em seis perguntas. Cada documento da discovery é a resposta
escrita de uma delas — é por isso que este repositório começa por documentação.

| A pergunta | O arquivo que responde |
|---|---|
| "Qual é a jornada completa do cliente?" | `docs/jornada.md` |
| "Onde linguagem natural gera valor vs. risco?" | `docs/jornada.md` — a coluna *quem resolve* |
| "O que é irreversível e precisa de aprovação?" | `docs/riscos.md` R3 → ADR-003 |
| "Onde você precisa de garantia absoluta?" | `docs/riscos.md` — a 4ª coluna, *verificação* |
| "Como medir sucesso com números?" | `docs/PRD.md` §2 |
| "O que fica de fora da primeira versão?" | `docs/PRD.md` §3 — com motivo por item |

## A estrutura de trabalho exigida

| O enunciado pede | Onde está |
|---|---|
| "Case próprio: negócio, cliente, produto e personas com nomes reais" | `docs/PRD.md` §1 e §4 |
| "PRD, SPECs e ADRs" | `docs/PRD.md` · `docs/specs/` · `docs/adr/` |
| "Arquitetura explicada: quantos agentes, onde entra o humano, gestão de falhas" | `docs/arquitetura.md` §3 (com diagrama) · ADR-002 · ADR-003 · ADR-004 |
| "Repositório preparado: com harness de agentes, contexto e processos visíveis" | `CLAUDE.md` · `.claude/` · `docs/harness/skills.md` |
| "Processo de versionamento: branches, PRs, validações automáticas" | ADR-005 · `.github/` · `commitlint.config.cjs` |
