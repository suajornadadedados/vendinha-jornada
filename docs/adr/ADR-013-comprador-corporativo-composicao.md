# ADR-013 — Comprador corporativo e composição de evento

- Status: aceito · Data: 2026-08-27 · Decisão: D16 · Riscos: R1, R10

## Contexto
O produto B2C funciona e está ancorado: a recomendação nunca inventa um fato. Mas a pergunta
que ele responde — *"um presente pra minha sogra que ama vinho tinto"* — é de **restrição
única**, e com 50 itens numa tela ela é respondível por inspeção. Quem assiste consegue bater o
agente no olho, e a conclusão honesta de quem olha é que aquilo é um filtro de e-commerce com
skin de chat.

A fraqueza não está no catálogo nem no mecanismo. Está em **quem pergunta**: um comprador cuja
necessidade cabe numa linha não gera decisão que precise de agente.

## Alternativas consideradas
1. **Trocar o domínio** (peças automotivas, componentes eletrônicos, vinhos) — ticket maior e
   vocabulário mais técnico; mas em peça e componente a recomendação vira *spec matching*, que
   é precisamente o que filtro já resolve bem. Derruba a tese do PRD §1 (*o cliente não sabe
   traduzir necessidade em filtro*) e obriga a reescrever `docs/requisitos.md`, que é a origem
   de toda a cadeia de discovery — o cliente teria mudado, não o produto.
2. **Manter B2C e só aumentar o catálogo** — mais itens não muda a natureza da pergunta.
   Duzentos produtos com restrição única continuam sendo uma lista maior para filtrar.
3. **Trocar o comprador para empresa** — a necessidade passa a ser *composição sob restrição*:
   N pessoas, orçamento por pessoa, ocasião, restrições alimentares, prazo. A tese do PRD §1
   sobrevive intacta (a gestora de RH também não sabe traduzir *"meu time é jovem, startup,
   sexta à tarde"* em filtros), e nenhum ADR anterior precisa mudar.
4. **B2B e B2C ao mesmo tempo** — dobra prompt, corpus de evals, telas e caminhos de NF (CPF e
   CNPJ) para provar a mesma tese duas vezes.

## Decisão
Opção 3: **B2B puro**. A Vendinha vende para empresas que montam eventos corporativos — café da
manhã, happy hour, cesta de fim de ano, kit de boas-vindas. O catálogo mineiro permanece; muda
quem compra e quanto isso exige de aritmética.

Três consequências de desenho decorrem disso e não são negociáveis:

**A composição é proposta pelo modelo e validada pelo código.** O LLM escolhe os produtos —
isso ele faz bem, e é onde o valor dele está. O código soma em `Decimal`, exige os slots
obrigatórios do tipo de evento e recusa o que estoura orçamento ou viola restrição alimentar.
É o ADR-001 aplicado a uma decisão maior que "qual é o preço".

**`rendimento` é campo do catálogo.** Quantas pessoas cada item atende num evento é o que
transforma "40 pessoas" em "3 pacotes de café e 4 queijos". Sem ele, a quantidade viraria conta
do modelo — que é exatamente a classe de erro que R1 existe para impedir.

**Preço continua unitário e único.** Comprador corporativo pede desconto por volume o tempo
todo; a resposta continua sendo que desconto **não existe como ação** para nenhum agente
(ADR-002, RF-2.6). Preço escalonado por faixa de quantidade foi considerado e recusado no MVP:
seria legítimo (tabela no banco, não negociação), mas daria a R1 uma segunda forma de estar
errado em troca de realismo que a demonstração não precisa.

## Consequências
+ A regra de ouro deixa de ser prosa e vira comportamento observável: o modelo propõe uma cesta
  de R$163, o código recusa contra um teto de R$150, o modelo ajusta — e as duas chamadas ficam
  no mesmo trace.
+ O projeto ganha um **segundo invariante de segurança** (R10) além do HITL. Restrição
  alimentar violada é dano real, e a garantia passa a ser estrutural em vez de cuidado do
  modelo.
+ A NF-e passa a ter destinatário PJ, com CNPJ, razão social e endereço de entrega — o que
  fecha um furo que o B2C tinha: a RF-2.2 coletava só nome, CPF e e-mail, e a DANFE modelo 55
  exige endereço.
+ Ticket sobe de dezenas para milhares de reais, o que dá peso real à fila de aprovação do
  operador.
− O corpus de evals (12 golden + 6 adversariais) é **reescrito**, não estendido. Custo aceito:
  o corpus é artefato de discovery neste repositório (nasceu na S-01), e reescrevê-lo **antes**
  de a tool existir é o que impede a régua de ser ajustada ao que o modelo faz (ADR-006).
− A `main` fica com um catálogo B2C entre a S-03 e a S-10. Aceito, e deliberadamente visível:
  requisito mudando no meio do projeto é a coisa mais real que existe, e o histórico mostrando
  o processo absorvendo isso vale mais do que um repositório que finge que a discovery
  acertou de primeira.

## O que passa a ser exigido do código
- `validar_composicao` é **read-only** e vive no subagent `recomendacao` — proposta não é side
  effect, e a fronteira do ADR-002 não se move.
- `criar_pedido` (S-04) **revalida a composição no servidor**. A validação que passou pelo
  modelo nunca é a que autoriza.
- `contem` (alérgenos) não entra no payload do Qdrant nem no texto embedado: é fato de corte,
  lido do Postgres. Um alérgeno com duas moradas é a falha de R1 com consequência física.
