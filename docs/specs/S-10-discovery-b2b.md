---
id: S-10
titulo: Discovery B2B — comprador corporativo e composição de evento
status: em-execucao
branch: spec/s-10-discovery-b2b
issue: #11
adrs: [ADR-013]
riscos_cobertos: []
---

# S-10 — Discovery B2B

> **Ordinal não é ordem de execução.** Esta spec roda entre a S-03 e a S-04. O id é S-10
> porque `evals/schema/caso.schema.json` exige `spec: ^S-[0-9]{2}$` — "S-03B" é inválido por
> schema — e porque renumerar S-04..S-09 quebraria o vínculo de seis issues do GitHub, os
> relatórios de verificação da S-01 e da S-02, e as referências cruzadas em `riscos.md`,
> `testes.md` e `decisoes.md`. Um id fora de ordem custa uma nota de rodapé; renumerar custa
> rastreabilidade, que é o que este repositório está vendendo.

## Objetivo
Trocar o **comprador**, não o domínio: a Vendinha passa a vender para empresas que montam
eventos corporativos. Discovery inteira antes de qualquer código — ADR, normativos, seed e
corpus de eval —, do mesmo jeito que a S-01 fez para o comprador B2C.

## Contexto (por que esta spec existe)
O produto está pronto para ser apresentado, e a apresentação expôs uma fraqueza que não é do
catálogo: **com 50 itens numa tela, a plateia bate o agente no olho**. Uma pergunta de restrição
única — "um presente pra minha sogra" — é respondível por inspeção, e a recomendação parece um
filtro de e-commerce com skin de chat.

Trocar o domínio (peças, componentes, vinhos) foi recusado no ADR-013: reescreveria
`docs/requisitos.md`, que é a origem de toda a cadeia de discovery, e transformaria a
recomendação em *spec matching* — exatamente o que filtro já resolve bem, derrubando a tese do
PRD §1. Trocar o comprador preserva a tese e destrava a **composição sob restrição**, onde o
modelo escolhe com gosto e o código recusa com aritmética.

## Requisitos
- [x] REQ-1 ADR-013 registrado (com as alternativas recusadas) e D16 em `docs/decisoes.md`.
- [x] REQ-2 `docs/requisitos.md` reescrito: a tradução do pedido do cliente passa a ser
      corporativa. `docs/PRD.md` com persona nova, RF-1.6/RF-1.7 (composição) e RF-2.2 em PJ.
      `docs/jornada.md` com a etapa nova — *montar composição: LLM propõe, código valida*.
- [x] REQ-3 **R10** na matriz de `docs/riscos.md` e na tabela risco→teste de `docs/testes.md`,
      com o arquivo de verificação nomeado e a spec responsável. `docs/arquitetura.md` com a
      §3.3 nova (*Onde o código recusa o modelo*) e §3.1, §3.4 e §3.5 atualizadas.
- [x] REQ-4 `data/catalogo/schema/produto.schema.json` com `rendimento` e `contem` obrigatórios
      e `petisco` no enum de `tipo`. `data/catalogo/README.md` explica por que cada um existe.
- [x] REQ-5 Seed enriquecido: todos os produtos com `rendimento` e `contem`, mais petiscos
      mineiros (torresmo, biscoito de polvilho, pão de queijo) e itens de topo de faixa.
      `make test` verde — o teste do seed é o portão.
- [ ] REQ-6 Corpus de evals reescrito para o comprador corporativo: os 12 golden e os 6
      adversariais, mais os casos de composição. `evals/schema/caso.schema.json` aceitando R10.
- [ ] REQ-7 S-04, S-05 e S-07 reescritas (as três estão `aprovada` e não iniciadas): pedido com
      composições, cliente PJ, NF-e para PJ, tela de montagem.
- [ ] REQ-8 S-11 redigida, com o desenho de `TipoDeEvento` e `validar_composicao`.

## Fora de escopo
Qualquer código de produto — `composicao.py`, a tool e o prompt são da **S-11**. Preço escalonado
por volume (decisão do PO: preço unitário único; a pressão por volume vira caso adversarial).
Boleto/faturamento B2B. Merch no kit de boas-vindas. `tipo: embalagem`.

## Tasks (cada uma vira um commit)
1. `spec(s-10): specs s-10 and s-11 for the b2b pivot`
2. `adr(s-10): corporate buyer and event composition`
3. `docs(s-10): retranslate the client request for b2b`
4. `docs(s-10): risk r10 and its verification`
5. `feat(s-10): catalog schema with rendimento and contem`
6. `feat(s-10): enrich seed and add mineiro petiscos` — leva junto o mínimo de
   `backend/vendinha/catalogo.py` para o seed continuar legível (D-1)
7. `eval(s-10): rewrite corpus for the corporate buyer`
8. `spec(s-10): rewrite s-04, s-05 and s-07 for b2b`

## BDD
```gherkin
Cenário: o seed sustenta a aritmética por pessoa
  Dado o catálogo enriquecido
  Quando `make test` roda o teste do seed
  Então todo produto tem rendimento > 0 e uma lista `contem` declarada, e nenhum preço
  sobrevive a uma travessia por float

Cenário: nenhum caso de eval cita produto que não existe
  Dado o corpus reescrito para o comprador corporativo
  Quando `make evals-check` cruza `produtos_validos` contra `data/catalogo/`
  Então nenhum id fica órfão — um caso reprovaria por falta de dado, não por falha do agente
```

## Métricas de sucesso
| Métrica | Alvo | Como medir |
|---|---|---|
| Ids órfãos entre corpus e seed | 0 | `make evals-check` |
| Produtos sem `rendimento` ou `contem` | 0 | `tests/unit/test_catalog_seed_is_usable.py` |
| Referências mortas nos normativos após a reescrita | 0 | grep por RF/RNF/R#/ADR removidos |
| Casos golden que ainda descrevem comprador pessoa física | 0 | revisão do diff |

## Verificação independente
- Cruzar `docs/requisitos.md` contra `docs/PRD.md`: todo requisito do PRD nasce de uma linha da
  tradução, e nenhuma linha da tradução ficou sem requisito.
- Conferir que R10 aparece nos **três** lugares (riscos, testes, e a spec que o fecha) e que o
  arquivo de teste nomeado é o mesmo nos três.
- Rodar `make evals-check` e `make test` num clone limpo da branch.
- Procurar por requisito órfão: `grep -rn "RF-\|RNF-\|R[0-9]\|ADR-" docs/` e conferir que todo
  id citado existe.

## Descobertas (preenchido durante a execução)

**D-1 · O seed e o modelo `Produto` são uma mudança só, não duas.**
O plano previa `rendimento` e `contem` no seed (S-10) e no `backend/vendinha/catalogo.py`
(S-11, task 1). Não dá: `Produto` é `extra="forbid"`, então o primeiro campo novo no JSON
derruba `carregar_seed` — e com ele `test_catalog_ingestion.py`, que roda em `make test`. Um
commit de seed que deixa a suíte vermelha viola o guardrail de sessão do `CLAUDE.md`.

A S-01 conseguiu criar o seed sem tocar em código porque `catalogo.py` **ainda não existia** —
ele nasceu na S-03. A partir do momento em que existe um leitor com contrato fechado, seed e
leitor deixam de ser separáveis.

Resolvido dentro do escopo: a task 6 leva junto o mínimo de `catalogo.py` para o seed ser
legível — `Produto`, o `Alergeno` `Literal`, as colunas do Postgres e os dois docstrings que
explicam o que ficou de fora do Qdrant. Nada de busca, filtro ou tool: isso continua na S-11,
cuja task 1 encolheu para *usar* os campos em vez de *criá-los*.

**D-2 · A lista fechada de alérgenos estava errada, e o próprio catálogo provou.**
O enum proposto era `lactose | gluten | alcool | castanhas | acucar`. Ao atribuir os valores,
dois produtos que já estavam no seed não couberam: `pacoca-de-amendoim` (amendoim é leguminosa,
não castanha — e é alérgeno de declaração obrigatória própria na RDC 26/2015) e
`broa-de-fuba-com-erva-doce` (leva ovo). Forçá-los em `castanhas` ou deixá-los com `contem: []`
seria declarar errado num campo cuja resposta errada machuca alguém.

Enum corrigido para `lactose | gluten | ovos | castanhas | amendoim | alcool | acucar`, nos três
lugares que precisam concordar: schema do seed, `Alergeno` em `catalogo.py`, e a constante
`ALERGENOS` do teste — que existe justamente para os três não divergirem em silêncio.

`castanhas` fica no enum sem nenhum produto usando. É deliberado: um comprador corporativo
pergunta por castanha, e a restrição precisa ser expressável mesmo quando a resposta é *"nenhum
item da composição contém"*.

**D-3 · `biscoito-de-polvilho` nunca foi um doce.**
Estava em `doces.json` por falta de categoria melhor. Com `petisco` no enum ele foi para
`petiscos.json`, **mantendo o id** — os casos de eval que o citam continuam válidos. E ele
virou o exemplo mais útil do catálogo: polvilho é mandioca, então é **sem glúten**, enquanto a
broa de fubá ao lado leva trigo. Um celíaco pode comer um e não o outro, e nenhuma das duas
descrições diz isso — que é exatamente o argumento para `contem` ser declarado e não inferido.

**D-4 · Sem sistema de migração, `CREATE TABLE IF NOT EXISTS` não basta.**
Um banco de desenvolvimento que já tem a tabela `produto` nunca veria as colunas novas, e o
próximo `make seed` falharia com *coluna inexistente* em vez de dizer o que aconteceu. `SCHEMA`
virou tupla de statements, com dois `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` ao lado do
`CREATE`. As duas formas são idempotentes, então `setup()` continua podendo rodar à vontade.

## Definition of Done
- [ ] Todos os requisitos CONFORMES no relatório de verificação
- [ ] CI verde (lint, typecheck, testes, evals)
- [ ] PR com evidência (screenshot + trace Langfuse)
- [ ] Relatório /verificar-spec anexado com veredito APROVADO
