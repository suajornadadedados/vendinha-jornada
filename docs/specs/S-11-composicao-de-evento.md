---
id: S-11
titulo: Composição de evento
status: em-revisao
branch: spec/s-11-composicao
issue: #18
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
- [x] REQ-1 `rendimento` e `contem` atravessando `Produto`, o schema do Postgres e o seed em
      memória, sem que `contem` entre no payload do Qdrant nem no texto embedado (ver §Decisões).
- [x] REQ-2 `TipoDeEvento` com slots obrigatórios declarados em código: `cafe_da_manha`,
      `happy_hour`, `cesta_de_fim_de_ano`, `kit_boas_vindas`.
- [x] REQ-3 Motor de regras em `backend/vendinha/composicao.py` — **função pura sobre `Produto`**,
      sem I/O, para a suíte `unit` rodar sem container (`docs/testes.md` §1).
- [x] REQ-4 Tool `validar_composicao`, **read-only**, registrada no subagent `recomendacao`.
      Devolve veredito com total, valor por pessoa, quantas pessoas a composição atende e a
      lista de problemas em linguagem que o modelo consiga agir em cima.
- [x] REQ-5 Prompt do subagent reescrito para o comprador corporativo: qualifica por evento,
      pessoas, orçamento por pessoa e restrições antes de montar; nunca afirma total sem
      `validar_composicao`; desconto continua não existindo.
- [x] REQ-6 `tests/unit/test_composicao.py`: o validador recusa orçamento estourado, slot
      faltando e restrição violada (R10 — ver §Por que R10 nasce em `unit`).
- [x] REQ-7 Casos de composição do corpus rodando localmente (`make evals-composicao`).

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
1. `feat(s-11): rendimento and contem reach the tool surface`
   — o título mudou na execução: catálogo e Postgres já vieram da S-10, e o que faltava
   era a fronteira da tool e o portão de groundedness (ver D-1 em Descobertas).
2. `feat(s-11): event types and composition rules`
3. `feat(s-11): validar_composicao read-only tool`
4. `feat(s-11): corporate buyer prompt`
5. `test(s-11): composition rules refuse what they must`
6. `eval(s-11): composition cases runnable locally`

Acrescentadas na execução, com aprovação do PO, depois que os evals mostraram o teto
de sessão cortando composição legítima (D-8). Ficaram nesta spec, e não numa spec de
custo separada, porque decidir o teto sem antes arrumar o desperdício seria escolher
um número para um fluxo que ia mudar em seguida:

7. `perf(s-11): detalhar_produto answers for a whole composition in one call`
8. `fix(s-11): the ceiling degrades before it truncates`
9. `fix(s-11): set the session ceiling from measurement, not from memory`

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

**D-1 — a task 1 já estava feita pela metade, e a metade que faltava não estava
declarada em lugar nenhum.** A S-10 levou `rendimento` e `contem` até o `Produto`, o
DDL do Postgres e o seed (descoberta D-1 dela). O que ela não podia prever é que os
dois campos **param na fronteira da tool**: `ProdutoEncontrado.de` filtra por
`model_fields`, e `ProdutoDetalhado` não os declarava — então eles eram descartados em
silêncio no caminho até o modelo. Somado a isso, `CAMPO_DA_TOOL` do portão de
groundedness não sabia traduzir nenhum dos dois. Consequência: `golden-013` (alérgeno)
e `golden-016` (rendimento), ambos `spec: S-03`, não tinham como passar na `main`.

Decisão do PO no pre-flight: fechar como task 1 desta spec. É o REQ-1 ("atravessando
`Produto`") lido até o fim, e pré-condição do REQ-4 — `contem` que não chega ao modelo
não corta nada.

**D-2 — `docs/riscos.md` atribui o R1 a "S-03 · S-04" e não cita a S-11**, enquanto o
frontmatter desta spec declara `riscos_cobertos: [R1, R10]`. `/verificar-spec` cruza as
duas coisas. Não foi alterado: mudança em documento normativo é decisão de PO e merece
diff próprio, não um commit de código carregando junto.

**D-3 — a S-10 está mergeada na `main` com `status: em-revisao`**, Definition of Done
toda desmarcada e sem `docs/specs/relatorios/S-10-verificacao.md`. A S-11 executa
exatamente sobre a base normativa que ela escreveu. Decisão do PO no pre-flight: seguir,
registrar, e não tocar na S-10 nesta branch.

**D-4 — o veredito precisou devolver o teto e o excedente, e não só o total.** Não é
enfeite: `groundedness._precos_divergentes` reprova todo valor em dinheiro citado ao
cliente que nenhuma tool tenha devolvido. O BDD manda o veredito *"dizer de quanto foi o
estouro"*, e `golden-007` espera que o agente fale do teto — os dois seriam preço sem
origem se não voltassem no retorno. `precos_das_tools` passou a ler as chaves de dinheiro
do veredito, inclusive um nível dentro de `itens`.

**D-5 — recusa por indisponibilidade entrou no validador.** A spec nomeia orçamento,
slots e restrição; disponibilidade não está na lista. Foi incluída assim mesmo, e o
motivo é que a alternativa é pior: aprovar uma composição com item fora do ar devolve um
total exato para uma cesta invendável, e o `data/catalogo/README.md` já diz que no B2B
esse caminho *"obriga o agente a recompor, não só a pedir desculpa"*. Fica registrado
como julgamento de execução, para o PO derrubar se discordar.

**D-6 — `Resultado.encontrados` passou a tipar sobre uma base com `SerializeAsAny`.**
O veredito tem que viajar dentro do envelope, porque é o único lugar em que o portão de
groundedness procura. Com a união literal que existia, `tools/composicao.py` precisaria
ser importada por `tools/catalogo.py` e o ciclo de import apareceria no primeiro arquivo
de tool que não fosse aquele.

**D-8 — o teto de sessão de 60.000 tokens trunca o fluxo de composição, e não é
desta spec mudá-lo.** `session_budget_tokens` (`backend/vendinha/config.py:92`) foi
dimensionado na S-02 para o fluxo B2C de três tools. A composição é mais longa por
desenho: buscar, detalhar cada produto, consultar preço, validar — e, quando o
veredito reprova, **tudo de novo**. Em `golden-007` e `golden-014` o agente chegou a
uma composição aprovada e foi cortado pelo `LIMIT_REACHED_MESSAGE` antes de escrever
a resposta, com o mecanismo funcionando e o cliente sem ver nada.

A S-11 empurrou o consumo para cima nas duas pontas: o prompt ficou mais longo e o
fluxo ganhou uma chamada (`consultar_preco`, exigida pelo `fatos_ancorados` do
`golden-001`). Mas o teto é **R6/RNF-3**, decisão da S-02, e trocar um limite de
custo é decisão de PO — não commit de spec de código. Registrado e **parado aqui**.

**D-9 — `--saida` gravava em utf-8, o `print` do relatório não.** No Windows o
stdout nasce em cp1252 e um `→` vindo da evidência do juiz derrubava o comando com
`UnicodeEncodeError` **depois** de a suíte inteira ter rodado — perdendo o resultado
de uma corrida paga. Corrigido em `runner.py` porque bloqueava o REQ-7 ("rodando
localmente"); é portabilidade do runner, não mudança de régua.

**D-10 — três reparos de prompt saíram da primeira rodada de evals, e nenhum é
ajuste de régua.** O `consultar_preco` faltava na receita de composição e o modelo
pulava a tool que o `golden-001` ancora; o modelo calculava a sobra do orçamento
("sobram R$ 25,27") e o rendimento por item, que são conta e caem na mesma regra do
ADR-001; e um veredito reprovado resolvido em silêncio deixa o cliente com uma
composição que ele não reconhece. Nenhum caso de `evals/` foi tocado (ADR-006).

**D-11 — a suíte da S-03 já estava 0 de 6 na `main`, e a S-11 a melhorou.** Essa
medição faltava desde o começo e é o que reenquadra tudo: durante boa parte da
execução eu comparei os resultados contra uma linha de base **imaginada** como verde.
Rodando `make evals-groundedness` no commit `5e0efdb` (a `main`, sem esta branch):

| | aprovados | critérios reprovados |
|---|---|---|
| `main` (5e0efdb) | **0 de 6** | 13 |
| `spec/s-11-composicao` | 0 a 1 de 6 | **8** |

Ou seja: a reescrita do prompt **não** quebrou a S-03 — ela já estava quebrada, e a
task 1 desta spec (`contem` e `rendimento` atravessando a tool) removeu falhas do
portão determinístico que na `main` eram estruturais e insanáveis.

*O que a S-11 quebrou e consertou no caminho:* a regra nova sobre números deixou o
modelo receoso de **dizer** número consultado — ele proibia calcular e o modelo leu
como proibição de relatar. E o prompt, reescrito para o comprador corporativo,
cresceu de ~110 para 242 linhas com treze "regras mecânicas" competindo entre si;
casos que passavam havia duas specs começaram a falhar em regras que continuavam no
texto, intocadas. Consolidado para 162 linhas, `golden-002` e `golden-005` voltaram —
o defeito era o comprimento, não uma regra específica. A lição vale registrar: no
prompt, justificativa é para quem lê o código, não para o modelo.

*O que continua aberto:* 8 critérios, concentrados em `detalhar_produto` não ser
chamada em conversa que não é de composição. Não é regressão desta branch, é dívida
que a S-03 deixou e que só ficou visível agora que o portão determinístico parou de
mascará-la.

*O que não é sinal:* os vereditos do juiz oscilam entre rodadas do **mesmo** código —
`golden-005` aprovou numa e reprovou na seguinte, e uma conversa de composição custou
13k tokens numa rodada e 91k na outra. Afinar prompt contra uma régua que se move é
como se overfita sem perceber, e foi por isso que parei o laço aqui em vez de seguir
uma rodada paga por vez.

**D-12 — o portão de groundedness não pega categoria inventada.** No `golden-014` o
agente ofereceu *"temos chocolate quente, chá e suco"* — nenhum dos três existe no
catálogo — e o portão não viu, porque ele só confere **nome de produto real** citado
sem origem (o próprio docstring de `groundedness.py` declara esse limite). O prompt
ganhou a regra ("categoria também é catálogo"), mas a régua continua cega para essa
classe. Não foi mexido: `evals/` é CODEOWNERS e a decisão é de PO.

**D-7 — o `Makefile` não roda no shell deste ambiente sem ajuste.**
`scripts/run-tests.sh` escolhe `python3`, que aqui resolve para um shim do pyenv sem as
dependências do backend; a suíte foi rodada com o interpretador de `backend/.venv`. É
questão de ambiente local, não do repositório — nada foi alterado.

## Definition of Done
- [ ] Todos os requisitos CONFORMES no relatório de verificação
- [ ] CI verde (lint, typecheck, testes, evals)
- [ ] PR com evidência (screenshot + trace Langfuse)
- [ ] Relatório /verificar-spec anexado com veredito APROVADO
