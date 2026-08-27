---
id: S-11
titulo: Composição de evento
status: aprovada
branch: spec/s-11-composicao
issue: #12
adrs: [ADR-001, ADR-002, ADR-013]
riscos_cobertos: [R1, R10]
---

# S-11 — Composição de evento

> Roda depois da S-10 e antes da S-04. Ver a nota sobre ordinal e ordem de execução na S-10.

## Objetivo
O modelo escolhe os produtos com gosto; o **código** soma em `Decimal`, exige os slots do tipo
de evento e recusa o que estoura orçamento ou viola restrição alimentar. É a regra de ouro
deixando de ser prosa e virando um ida-e-volta visível no trace.

## Requisitos
- [ ] REQ-1 `rendimento` e `contem` atravessando `Produto`, o schema do Postgres e o seed em
      memória, sem que `contem` entre no payload do Qdrant nem no texto embedado (ver §Decisões).
- [ ] REQ-2 `TipoDeEvento` com slots obrigatórios declarados em código: `cafe_da_manha`,
      `happy_hour`, `cesta_de_fim_de_ano`, `kit_boas_vindas`.
- [ ] REQ-3 Motor de regras em `backend/vendinha/composicao.py` — **função pura sobre `Produto`**,
      sem I/O, para a suíte `unit` rodar sem container (`docs/testes.md` §1).
- [ ] REQ-4 Tool `validar_composicao`, **read-only**, registrada no subagent `recomendacao`.
      Devolve veredito com total, valor por pessoa, quantas pessoas a composição atende e a
      lista de problemas em linguagem que o modelo consiga agir em cima.
- [ ] REQ-5 Prompt do subagent reescrito para o comprador corporativo: qualifica por evento,
      pessoas, orçamento por pessoa e restrições antes de montar; nunca afirma total sem
      `validar_composicao`; desconto continua não existindo.
- [ ] REQ-6 `tests/unit/test_composicao.py`: o validador recusa orçamento estourado, slot
      faltando e restrição violada (R10 — ver §Por que R10 nasce em `unit`).
- [ ] REQ-7 Casos de composição do corpus rodando localmente (`make evals-composicao`).

## Fora de escopo
`criar_pedido` e a revalidação server-side (S-04, e é lá que R10 ganha o teste de `security`).
Preço escalonado por volume. Variante por pessoa dentro de uma mesma composição — *"12 cestas,
2 sem álcool"* são **duas composições no mesmo pedido**, e isso não exige entidade nova.

## Decisões de desenho (derivadas, não novas)

**`contem` não entra no payload do Qdrant.** O docstring de `catalogo.py` já cravou a regra: o
payload leva só filtro estrutural (`tipo`, `disponivel`), porque todo campo ali é um fato com
duas moradas — e a segunda cópia é a que fica velha sem ninguém perceber. Alérgeno é o pior fato
possível para ter cópia velha. Filtra no Postgres, junto com preço (R1, R10).

**`contem` também não entra no texto embedado.** O vetor responde *para quem serve este produto*.
Restrição alimentar é corte, não semelhança — quem pede "sem lactose" não quer o queijo
ranqueado mais baixo, quer ele fora.

**Slots são código, não preferência do modelo.** Café da manhã sem café é inválido, e essa
frase precisa ser executável. Sem slots, "montar uma composição" não tem nada objetivo para
recusar, e o validador vira opinião.

| Evento | Slots mínimos |
|---|---|
| `cafe_da_manha` | ≥1 `cafe`, ≥1 `queijo`, ≥1 `doce`, ≥1 `petisco` |
| `happy_hour` | ≥1 (`cachaca` \| `licor`), ≥1 `queijo`, ≥1 `petisco` |
| `cesta_de_fim_de_ano` | ≥3 tipos distintos |
| `kit_boas_vindas` | ≥1 `cafe`, ≥1 `doce` |

**A tool segue a fábrica que já existe.** `ferramentas_de_catalogo()` em
`backend/vendinha/tools/catalogo.py` recebe as portas `Busca` e `Catalogo` injetadas — é o que
permite a suíte unit rodar contra catálogo em memória sem mockar nada interno (ADR-004). A
composição usa a mesma forma, o mesmo `run_with_timeout` e o mesmo model `Resultado`.

## Por que R10 nasce em `unit`, e só vira `security` na S-04
`docs/testes.md` §3.3: teste que nasceu verde não provou nada. Nesta spec ainda não existe
`criar_pedido` — um teste de `security` afirmando *"nenhum pedido viola restrição declarada"*
passaria por **vacuidade**. O que dá para provar agora é que **o validador recusa**, e é isso
que `tests/unit/test_composicao.py` prova.

`tests/security/test_composicao_invariants.py` entra na S-04, quando `criar_pedido` existir e
revalidar no servidor — nunca confiando na validação que passou pelo modelo. É exatamente o
argumento que o docstring de `subagents.py` já usou para o registro de permissão nascer na S-03
e o teste de `security` só na S-04. O precedente está no repositório.

## Tasks (cada uma vira um commit)
1. `feat(s-11): rendimento and contem across catalog and postgres`
2. `feat(s-11): event types and composition rules`
3. `feat(s-11): validar_composicao read-only tool`
4. `feat(s-11): corporate buyer prompt`
5. `test(s-11): composition rules refuse what they must`
6. `eval(s-11): composition cases runnable locally`

## BDD
```gherkin
Cenário: o código recusa o que o modelo propôs
  Dado um café da manhã para 40 pessoas com orçamento de R$35 por pessoa
  Quando o modelo propõe uma composição que sai a R$41 por pessoa
  Então `validar_composicao` reprova, diz de quanto foi o estouro, e o modelo ajusta
  E o trace mostra as duas chamadas

Cenário: restrição alimentar não é responsabilidade do modelo
  Dado um pedido com restrição "sem glúten" declarada
  Quando a composição inclui um item cujo `contem` lista glúten
  Então o veredito é reprovado nomeando o produto e a restrição, mesmo que o texto do
  produto não mencione glúten em lugar nenhum

Cenário: slot obrigatório faltando
  Dado um café da manhã sem nenhum item de tipo `cafe`
  Quando a composição é validada
  Então ela reprova por slot, e não por preço
```

## Métricas de sucesso
| Métrica | Alvo | Como medir |
|---|---|---|
| Total citado ao cliente divergente do validador | 0 | assert no eval de composição |
| Composição aprovada violando restrição declarada | 0 (invariante) | `tests/unit/test_composicao.py` |
| Tools de escrita no subagent `recomendacao` | 0 | `tests/unit/test_subagent_registry.py` |
| Rodadas até uma composição válida, em conversa típica | ≤ 3 | contagem no trace |

## Verificação independente
- Rodar `make evals-composicao`; conferir no Langfuse que todo total dito ao cliente veio de
  `validar_composicao`, e não de aritmética do modelo.
- Tentar em conversa livre: pedir desconto por volume, pedir para "ignorar o orçamento só
  desta vez", e pedir uma composição que viole restrição já declarada.
- Confirmar no registro de subagents que `recomendacao` continua sem tool de escrita.
- Conferir que `contem` não aparece no payload do Qdrant nem no texto embedado.

## Descobertas (preenchido durante a execução)
- (vazio)

## Definition of Done
- [ ] Todos os requisitos CONFORMES no relatório de verificação
- [ ] CI verde (lint, typecheck, testes, evals)
- [ ] PR com evidência (screenshot + trace Langfuse)
- [ ] Relatório /verificar-spec anexado com veredito APROVADO
