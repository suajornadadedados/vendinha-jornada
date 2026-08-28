# ADR-015 — O painel de observação é entregável, e o Langfuse não vai para o cliente

- Status: **aceito** · Data: 2026-08-28
- Decisão relacionada: D18 (docs/decisoes.md) · Riscos: nenhum novo — o painel não é lugar de garantia
- Revoga um não-objetivo do PRD (§3, *"multi-tenancy e painel administrativo completo"*), e só a
  metade depois do "e". Multi-tenancy continua fora.

## Contexto

O PRD escreveu "painel administrativo completo" como não-objetivo quando o entregável imaginado era
o agente, e a interface era a prova de que o agente funcionava. Duas coisas mudaram desde então, e
nenhuma delas foi de opinião.

**O pivô B2B (ADR-013)** trocou o comprador. O ticket saiu da casa das dezenas para a casa dos
milhares, e a aprovação de NF deixou de ser detalhe de compliance para virar decisão humana com
consequência financeira. Quem decide precisa de um lugar para ver o que está decidindo — a S-05
entregou a fila como API e escreveu, na própria spec, *"UI do operador (S-07 — aqui só API)"*.

**A S-05 deixou uma dívida nomeada.** A ressalva R-2 do relatório de verificação registrou que o
RF-3.6 — *"o cliente **recebe** a confirmação no chat"* — tinha sido estreitado para *"o cliente
pergunta e o agente consulta"*, e que isso *"a S-07 deveria fechar de verdade"*. Fechar de verdade
significa o servidor empurrar um evento para a sessão do cliente. E um servidor que empurra evento
para o cliente já tem, pronto, o mecanismo de que o operador precisa para ver a conversa
acontecendo.

Fica o fato incômodo que motiva o resto deste documento: **hoje o operador não tem como observar
nada.** Existem `POST /chat`, `GET /operador/fila` e as duas rotas de decisão. Não há listar
conversas, ler as mensagens de uma sessão, stream de eventos, métrica, preço de token — nem CORS, o
que significa que nenhum navegador fala com esta API. Uma S-07 "de frontend" construída sobre o que
existe entrega um chat e uma tabela de pendências, e não entrega a coisa que dá sentido ao pedido:
**ver o agente trabalhando enquanto ele trabalha.**

## Alternativas consideradas

1. **Dar Langfuse ao cliente.** Tentador porque o dado já está lá, mascarado, e custaria zero
   backend: bastava criar um usuário. Recusado por três razões, e a terceira é a que decide. O
   Langfuse é ferramenta de engenharia — traces, spans, prompts, latência por observação — e expõe o
   *interior* do sistema a quem não tem contexto para lê-lo; um span vermelho de retry bem-sucedido
   vira chamado de suporte na segunda-feira. Exige conta e chaves que o cliente não tem, e o ADR-010
   aceitou o SaaS com a cláusula explícita de que ele nunca derruba o atendimento — pôr a única
   visão do cliente atrás dele é romper essa cláusula por outra porta. E o dado que o cliente
   precisa **não é o do Langfuse**: ele quer taxa de conversão, ticket médio e custo por conversa;
   o Langfuse tem custo por trace.

2. **Manter o não-objetivo e entregar só a fila.** É a leitura literal do PRD e sai barato.
   Recusado porque a fila sem contexto obriga a decidir no escuro: o operador vê um CNPJ e um total,
   e a pergunta que ele realmente tem — *"essa conversa fez sentido?"* — não tem onde ser
   respondida. E porque o não-objetivo protegia contra um CRUD administrativo genérico, não contra a
   capacidade de observar; manter a letra aqui seria obedecer à palavra contra a razão dela.

3. **Painel de observação como entregável de primeira classe, com read model próprio.** O backend
   ganha superfície de leitura e um barramento de eventos; a UI só exibe. Custo: a S-07 deixa de ser
   spec de frontend e vira full-stack, com um artefato novo para manter (o read model) e uma peça
   que não sobrevive a mais de uma instância (o barramento in-process).

## Decisão

**Opção 3.** O painel de observação é entregável. Três regras o delimitam.

### 1. A UI não é lugar de garantia

Toda invariante do produto já está fechada abaixo dela — a matriz R1-R10 não ganha nem perde uma
linha com esta decisão, e por isso `riscos_cobertos` da S-07 continua vazio. O painel **exibe**; não
valida, não recalcula, não decide.

A consequência prática é dura, e é métrica da spec: **nenhuma conta de dinheiro acontece em
JavaScript.** Total, valor por pessoa, custo de tokens, ticket médio, taxa de conversão — tudo
somado em `Decimal` no backend e transportado pronto. A regra de ouro do projeto não tem uma versão
relaxada para a camada de apresentação; tem, na apresentação, a sua forma mais fácil de furar sem
ninguém notar, porque um `reduce` que soma preços parece inofensivo no diff.

### 2. A única escrita continua sendo a decisão humana e a configuração

`/admin/*` é read-only. As duas escritas do painel são as que já existiam: a decisão de HITL
(`POST /operador/pedidos/{id}/aprovar|rejeitar`) e a configuração de modelo/credencial
(`PUT /config`, que continua 403 fora de `APP_ENV=local` por S-02 D-8). **Não há CRUD de catálogo,
de pedido ou de composição** — é aí que mora o "painel administrativo completo" que o PRD recusou, e
ele continua recusado.

**Prompt é read-only, e esta é a parte não-negociável.** O painel exibe os prompts vigentes com
caminho e sha, e não os edita. Um campo de texto que altera `PROMPT_RECOMENDACAO` em runtime
contorna o portão inteiro do ADR-014 — mudança de prompt é exatamente o evento que a R7
("regressão silenciosa a cada mudança de prompt") existe para pegar, e o `CLAUDE.md` exige rodar os
evals antes do PR. Prompt editável pela UI transforma a S-06 em decoração: a régua continua verde no
CI enquanto o sistema em pé roda outro prompt. **Prompt muda por PR, com evals, ou não muda.**

### 3. O custo é calculado aqui, com preço versionado

O cliente não tem Langfuse; logo o painel não pode depender dele para nada que o cliente precise
ver. Tokens, latência e modelo são gravados por turno em Postgres — verdade que este sistema possui
— e o custo sai de `data/precos-modelos.json`, versionado, em `Decimal`, no backend.

O risco conhecido dessa escolha é a tabela de preços desatualizar em silêncio. Ele é atacado de duas
formas, e nenhuma delas é confiar na disciplina de quem mantém: modelo sem preço cadastrado devolve
custo **`None`, jamais zero** — a tela escreve "modelo sem preço cadastrado" em vez de exibir
R$ 0,00, porque um zero mentiroso é pior que um vazio honesto —, e o `atualizado_em` da tabela fica
visível na tela de configurações.

O Langfuse continua sendo o visor **interno** (ADR-010, ADR-014). O deep-link para o trace aparece
no painel só quando há chaves configuradas, e some quando não há, em vez de virar link quebrado.

## Consequências

**Positivas**

- A regra de ouro fica visível para quem nunca vai abrir um trace: a tela de rastreabilidade mostra
  lado a lado o que o modelo propôs e o que o código validou ou recusou, com o motivo real do
  validador.
- A dívida R-2 da S-05 fecha de verdade. Com o push por sessão, aprovar a NF no painel faz o cartão
  da DANFE aparecer sozinho no chat do cliente: o verbo "receber" do RF-3.6 volta a ser verdade.
- O read model responde perguntas que hoje não têm onde ser feitas — custo por conversa, tempo até a
  decisão do operador, recusas do validador por motivo — sem consultar um terceiro.

**Negativas, aceitas**

- **A S-07 deixa de ser uma spec de frontend.** Ganha backend, tabelas e testes de segurança
  próprios, e fica grande. O corte de emergência, se precisar, é adiar as telas de Pedidos e
  Métricas — conversas ao vivo, HITL e rastreabilidade são o núcleo.
- **O barramento é in-process e não sobrevive a mais de uma instância de API.** Com duas, cada uma
  vê só os próprios eventos. Está isolado atrás de um Protocol para que a troca por `LISTEN/NOTIFY`
  no Postgres não toque nas rotas, e fica registrado como dívida explícita da **S-08**, que é onde a
  segunda instância pode aparecer.
- **Duplicação parcial com o Langfuse.** Duas fontes medem custo. A do painel é a que o cliente vê; a
  do Langfuse é a que a engenharia usa. Divergirem é possível, e a resposta é que a nossa é derivada
  de `usage_metadata` do provedor com preço versionado — auditável linha a linha — enquanto a do
  Langfuse é conveniência interna.
- **O painel depende de um token digitado à mão.** Não há login; está fora do escopo da S-07 por
  decisão anterior. Precisa ser dito em voz alta: **este painel não vai para a internet aberta antes
  de a S-08 resolver autenticação.** Um `X-Operador-Token` em `sessionStorage` é aceitável numa demo
  local e não é aceitável num host público.

**O que passa a ser exigido do código**

- Toda rota `/admin/*` é fail-closed no `X-Operador-Token`, reusando `_operador_autenticado` — e há
  teste `security` que percorre **todas** elas sem token e com token errado.
- `GET /eventos/sessao/{session_id}` emite apenas os eventos daquela sessão, e há teste `security`
  afirmando que um id não vê o evento de outro.
- As mensagens da conversa **não são copiadas** para tabela nova: são lidas do checkpointer. A RNF-6
  (pointer-not-payload) vale para o read model como vale para o estado do grafo.
- O barramento tem fila **limitada** por assinante: fila cheia descarta o mais antigo e emite um
  evento de atraso. Um painel lento nunca segura a resposta de um cliente.
- Nenhum evento do barramento carrega mais PII do que a fila do operador já expõe.
- O `openapi.json` é gerado sem subir servidor e é commitado; o CI regenera e compara. Drift de
  contrato quebra o build.
