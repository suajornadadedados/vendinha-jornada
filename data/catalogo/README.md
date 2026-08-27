# data/catalogo/ — o seed, e por que ele é normativo

Este é o catálogo da Vendinha: **65 produtos** artesanais mineiros, divididos em cinco arquivos
por tipo. Não é dado de exemplo — é a **única origem** de preço, atributo, disponibilidade,
**rendimento** e **alérgeno** no projeto inteiro.

## A regra que este diretório existe para sustentar

> O LLM decide o que dizer. O código decide o que pode ser feito.

Aplicada aqui, ela vira uma frase mais curta: **o modelo nunca afirma um número que não tenha
vindo daqui** — e, desde o pivô B2B (ADR-013), isso inclui a **quantidade** e o **total**. Preço, maturação, região, prazo e disponibilidade chegam ao cliente por retorno de
tool que leu este seed (S-03) ou o Postgres semeado a partir dele (S-04) — nunca da memória do
modelo. Um único fato inventado reprova a suíte de evals inteira e trava o release
(ADR-001, ADR-006, R1, RF-1.3).

## Preço é string, e isso é de propósito

```json
"preco": "89.90"
```

JSON não tem tipo decimal. Escrito como número, `89.90` é parseado como `float` e deixa de ser
exatamente 89 reais e 90 centavos — que é precisamente a classe de erro que R1 existe para
impedir. Como string, o valor chega em `Decimal("89.90")` sem perda, e
`tests/unit/test_catalog_seed_is_usable.py` recusa qualquer coisa que não faça esse caminho de
volta intacta (`docs/testes.md` §4: *dinheiro é `Decimal`, nunca `float`*).

## O formato

`schema/produto.schema.json` é **normativo**. Todo produto é validado contra ele por
`tests/unit/test_catalog_seed_is_usable.py`, que roda em `make test` — sem rede, sem agente,
sem chave de API.

Campos obrigatórios em todo produto: `id`, `nome`, `tipo`, `regiao`, `produtor`, `descricao`,
`intensidade`, `harmonizacao`, `ocasiao`, `peso`, `preco`, `disponivel`, `prazo_estimado`,
`rendimento`, `contem`.

Campos condicionais, exigidos pelo `tipo`:

| Tipo | Exige também |
|---|---|
| `queijo` | `maturacao` |
| `cafe` | `torra`, `notas_sensoriais` |
| `cachaca`, `licor` | `maturacao`, `teor_alcoolico` |
| `doce`, `petisco` | nada além dos obrigatórios |

O `id` é o que amarra tudo: é por ele que um caso de eval declara `produtos_validos`, e é ele que
o teste de rastreabilidade do corpus cruza contra este diretório.

## `rendimento` é o que transforma "40 pessoas" em quantidade

```json
"rendimento": 12
```

Quantas pessoas o item atende **num evento** — não quantas porções cabem no pacote. Um queijo
de 500 g numa tábua de café da manhã para o time inteiro rende diferente de um queijo de 500 g
que uma família come no fim de semana, e o número aqui é o do evento.

Ele existe por um motivo só: **quem divide é o código**. Sem `rendimento`, transformar *"café
da manhã para 40 pessoas"* em *"3 pacotes de café e 4 queijos"* seria conta do modelo — que é
exatamente a classe de erro que R1 existe para impedir. Com ele, a quantidade vira divisão
inteira sobre um fato lido do banco (RF-1.6, S-11).

> Os números atuais são estimativa do PO, não medição. `docs/PRD.md` §11 Q4 registra isso como
> questão aberta a conferir contra evento real antes da S-11 fechar.

## `contem` é corte, não ranqueamento

```json
"contem": ["lactose"]
```

Alérgenos declarados, de uma lista fechada: `lactose`, `gluten`, `alcool`, `castanhas`,
`acucar`. Lista vazia significa *nada a declarar*.

Ele é **campo derivado de nada**: não dá para inferir do texto. Doce de leite não se anuncia
como lactose, broa de fubá não avisa que leva trigo, e nenhuma descrição de produto foi escrita
pensando em quem tem doença celíaca. Por isso é declarado, e por isso é obrigatório.

Três consequências que o código respeita:

1. **Não entra no payload do Qdrant.** O payload leva só filtro estrutural (`tipo`,
   `disponivel`), porque todo campo ali é um fato com duas moradas — e a segunda cópia é a que
   fica velha sem ninguém perceber. Alérgeno é o pior fato possível para ter cópia velha.
2. **Não entra no texto embedado.** Quem pede "sem lactose" não quer o queijo ranqueado mais
   baixo; quer ele **fora**. Semelhança é a ferramenta errada para um corte.
3. **É filtrado no Postgres**, junto com o preço, e a composição que violar uma restrição
   declarada reprova nomeando o produto e o alérgeno (R10, `tests/unit/test_composicao.py`).

## `harmonizacao` e `ocasiao` são o produto, não enfeite

Um catálogo com nome e preço é uma tabela de e-commerce, e filtro de e-commerce não resolve
*"um presente pra minha sogra que ama vinho tinto e recebe muita visita"*. Quem responde essa
frase é `ocasiao: ["presente", "receber visita"]` cruzado com
`harmonizacao: ["vinho tinto encorpado", ...]`.

Por isso o validador exige **pelo menos quatro atributos preenchidos** por produto, e não apenas
nome e preço: é o mínimo para a busca semântica da S-03 ter do que puxar.

Desde o pivô B2B, `ocasiao` carrega também o vocabulário de quem organiza evento de empresa:
`café da manhã corporativo`, `happy hour`, `confraternização`, `onboarding`, `reunião com
cliente`, `presente para cliente`, `fim de ano`. São strings livres — o schema não as enumera —,
mas é por elas que *"meu time é jovem, startup, sexta à tarde"* encontra um torresmo e uma
cachaça em vez de uma cesta de chá.

## Dependência dos casos de eval

Os casos em `evals/` citam produtos pelo `id` daqui, no campo `produtos_validos`. Um caso que cite
um `id` inexistente reprova **por falta de dado, não por falha do agente** — que é o pior tipo de
reprovação, porque parece um problema do modelo. `tests/unit/test_eval_corpus_is_traceable.py`
cruza as duas coisas e falha se o vínculo quebrar.

**Ao remover ou renomear um produto, rode `make test`.** O cruzamento é o que impede o seed e o
corpus de divergirem em silêncio.

## Nada aqui é real

Produtores, sítios, fazendas e laticínios são **fictícios**. As regiões e as denominações de
origem (Canastra, Serro, Araxá, Campo das Vertentes, Cerrado Mineiro) são geográficas e públicas.
Nenhum CNPJ, endereço, telefone ou nome de pessoa real entra neste repositório — nem aqui, nem em
fixture (`CLAUDE.md`, guardrails da sessão).

## O que este seed não é

Não é sistema de estoque. `disponivel` e `prazo_estimado` são **campos lidos**, não o resultado de
uma consulta a um ERP. A garantia que o projeto entrega é *"o agente nunca inventa"* — não
*"o estoque está certo em tempo real"*. Está dito assim na nota de escopo de `docs/requisitos.md`
e no `docs/PRD.md` §3, e não escondido aqui.

Cinco produtos estão com `disponivel: false` de propósito: sem eles, o caminho "produto
indisponível" nunca seria exercitado por nenhum caso — e no B2B ele dói mais, porque um item
fora do ar no meio de uma composição obriga o agente a recompor, não só a pedir desculpa.
