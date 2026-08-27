# Relatório de verificação independente — S-03 (Recomendação ancorada / RAG)

| | |
|---|---|
| **Spec** | `docs/specs/S-03-recomendacao-ancorada.md` (`status: em-revisao`) |
| **Branch** | `spec/s-03-recomendacao` @ `475562d` (9 commits) |
| **Base** | `origin/main` @ `c633264` |
| **PR** | **não existe** — correto sob o `CLAUDE.md` item 4 (*"Verificação independente ANTES do PR… Sem veredito, não existe PR"*) |
| **Issue** | [#4](https://github.com/suajornadadedados/vendinha-jornada/issues/4) — OPEN |
| **Diff** | 9 commits · 33 arquivos · +5.256 / −111 |
| **Falsificações** | **43 executadas · 35 reprovaram · 8 sobreviveram** |
| **Achados** | 2 Alta · 4 Média · 3 Baixa |
| **Sessão** | revisora, independente, sem acesso ao histórico da sessão autora |
| **Data** | 2026-08-27 |
| **Ambiente** | Windows 11 · `backend/.venv` = Python 3.13.2 · `make` não existe nesta máquina, rodei a linha de dentro de cada alvo |
| **Infra** | `docker compose` subido por mim: `vendinha-postgres-1` healthy em `127.0.0.1:5433` (a 5432 do host está ocupada por Postgres nativo), `vendinha-qdrant-1` em 6333/6334 |
| **Veredito** | **APROVADO COM RESSALVAS** |

## Enquadramento recebido

A mensagem que iniciou esta sessão continha **`S-03` e nada mais**. Nenhum enquadramento a
registrar — nenhuma indicação do que já estaria verde, do que olhar, ou do que esperar. É o
contrato do `.claude/agents/verificador-de-spec.md` cumprido à risca, e vale dizê-lo em voz alta
justamente porque a seção existe para o caso contrário.

## Nota de método sobre credenciais

Não li o `.env` — a regra de `.claude/settings.json` o nega ao agente e eu não a contornei.
Nenhum valor de credencial aparece neste relatório. `OPENAI_API_KEY` e `ANTHROPIC_API_KEY` **não
estão disponíveis no meu shell**, e é por isso que a §6 marca como NÃO VERIFICÁVEL tudo que exige
chamada real a provedor: a execução de `make evals-groundedness`, a ingestão no Qdrant e a
conversa livre pela API. **A tabela "Estado final da verificação ponta a ponta" da spec é, para
esses itens, palavra do autor que eu não pude conferir** — inclusive o `4 de 6`.

## Rastro que deixei

Banco `verif_s03` criado no Postgres do compose e **derrubado** ao final (restam `postgres` e
`vendinha`); o banco `vendinha` do autor não foi tocado. As falsificações reescreveram arquivos
de código e todas foram restauradas — inclusive um desvio de fim de linha (LF→CRLF) que meu
harness introduziu e que eu corrigi com `git checkout --`. Subi o Docker Desktop, que estava
parado; os contêineres têm `restart: unless-stopped` e voltaram sozinhos.

`git status --short` **antes** e **depois**, idênticos:

```
?? docs/workshop/apresentacao.html
```

Esse arquivo não rastreado já existia antes de eu chegar e não é meu — não o toquei.

---

## 1. Resumo

**O núcleo desta spec é sólido, e a parte mais difícil de fazer bem foi feita bem.** A fronteira
de permissão do ADR-002 é estrutural de verdade: quebrei a guarda de quatro maneiras diferentes —
neutralizando a condição, esvaziando `SOMENTE_LEITURA`, fazendo `escritoras` devolver o valor
neutro e movendo a guarda para *depois* do efeito — e as quatro reprovam no mesmo teste, pelo
motivo certo. Contrabandear uma quarta tool de escrita dentro da fábrica read-only também reprova,
em dois arquivos. O portão determinístico de groundedness tem **um teste por componente**:
desliguei `_tools_proibidas`, `_fatos_sem_origem`, `_precos_divergentes` e
`_produtos_nao_recuperados` um a um, e cada um derruba exatamente os testes que carregam o nome
daquele comportamento. Esse é o padrão de uma suíte que morde.

**E a honestidade da spec é a coisa mais valiosa do diff.** A DESC-1 documenta que a decisão D-3
é a causa estrutural de duas reprovações, mede quatro rodadas de tentativa de conserto por prompt,
e recusa o conserto por prompt citando o `docs/testes.md`. Confirmei o que mais importa nessa
história: **`evals/` e `data/catalogo/` não foram tocados neste branch** — nenhum caso foi editado
para ficar verde. É o comportamento que o ADR-006 e o CODEOWNERS existem para forçar, e aqui ele
aconteceu.

**O que me faz não aprovar sem ressalva são duas coisas, e nenhuma delas é o eval vermelho.**

A primeira: **o único risco que a spec declara — R1 — não tem o arquivo-âncora que os dois
documentos normativos nomeiam.** `docs/riscos.md` e `docs/testes.md` §2 apontam
`tests/unit/test_order_total.py`; ele não existe, e nenhum dos dois documentos foi emendado. O R1
está substantivamente coberto (42 testes marcados `risco("R1")` em cinco arquivos), então isto é
rastreabilidade, não buraco funcional — mas é exatamente a regra que o `docs/testes.md` §3.2
escreve como não negociável.

A segunda: **oito quebras deliberadas sobreviveram à suíte inteira**, e seis delas estão
concentradas numa função só, `buscar_produtos` — o coração do REQ-2. O filtro `preco_minimo`
pode ser invertido ou removido por completo sem uma única reprovação; a ordem do ranqueador, que o
próprio comentário do código defende como *"a única coisa que a busca semântica produziu"*, pode
ser invertida sem reprovação. A sétima sobrevivente é pior em consequência: **anular a fiação do
envenenamento no runner desliga o vetor de injeção inteiro do `adversarial-004` e a suíte fica
verde.**

Sobre o eval em 4 de 6: a métrica de sucesso da própria spec diz *"0 (uma ocorrência reprova)"*.
Ela **não foi atingida**, e a spec diz isso com todas as letras. Registro como não-conformidade de
métrica (**NC-3**), não como reprovação, porque a decisão de seguir assim é do PO, está escrita,
está medida, e o gate de evals só vira obrigatório na S-06. Uma decisão de PO documentada com
medição não é a mesma coisa que um requisito silenciosamente não entregue.

---

## 2. Execução do zero — números reais, não "deve passar"

| Comando (linha de dentro do alvo do `Makefile`) | Resultado |
|---|---|
| `pytest tests` | **446 passed** em 43,53 s (rodado 3x, estável) |
| `ruff check .` | **All checks passed!** |
| `ruff format --check .` | **91 files already formatted** |
| `mypy .` (backend) | **Success: no issues found in 24 source files** |
| `mypy --explicit-package-bases tests` | **Success: no issues found in 16 source files** |
| `docker compose up -d --wait` (`POSTGRES_PORT=5433`) | postgres **healthy**, qdrant **healthy** |
| `python -m vendinha.evals.runner --help` | ok — flags `--spec`, `--caso`, `--saida` |
| `python -m vendinha.evals.runner --spec S-03` | **exit 2**, falha graciosa e acionável (ver §6, REQ-5) |
| `python -m vendinha.evals.runner` completo | **NÃO VERIFICÁVEL** — sem `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` |

### 2.1 Dinheiro através do Postgres real — o que consegui medir sem credencial

Rodei o caminho de produção do catálogo contra o Postgres do compose, num banco descartável
(`verif_s03`), usando o próprio `PostgresCatalogo`:

```
substituir_tudo        -> 50 linhas (seed tem 50)
quantos()              -> 50
substituir_tudo 2a vez -> 50 ; quantos() -> 50        (idempotente)
coluna preco           -> ('numeric', 8, 2)
produtos lidos         -> 50
preco nao-Decimal      -> 0
preco divergente do seed (valor OU centavos textuais) -> 0
amostra: Queijo Canastra meia-cura -> Decimal('89.90') type=Decimal
```

**A afirmação da spec — `Decimal('89.90')`, sem passar por float em nenhum ponto — confere**, e
confere para os 50 produtos, não só para a amostra. A idempotência da metade Postgres também
confere. A metade Qdrant (50 pontos, dim 1536) eu **não** pude reproduzir: a ingestão embeda pela
OpenAI.

---

## 3. Conformidade requisito a requisito

| # | Requisito | Veredito | Teste que prova |
|---|---|---|---|
| **REQ-1** | Ingestão do seed no Qdrant (embeddings + payload estruturado para filtros) | **CONFORME**, com a execução real do Qdrant **NÃO VERIFICÁVEL** | `test_the_point_id_is_derived_from_the_product_id_and_never_changes`, `test_no_money_reaches_the_vector_index`, `test_the_document_crosses_occasion_and_pairing_the_way_a_customer_asks`, `test_an_empty_catalogue_is_refused_instead_of_written`, `test_indexing_refuses_a_vector_count_that_does_not_match_the_products` · metade Postgres medida por mim (§2.1) |
| **REQ-2** | Tools read-only `buscar_produtos` (semântica+**filtros**), `detalhar_produto`, `consultar_preco` | **CONFORME COM RESSALVA** — a cláusula "filtros" só está provada pela metade | `test_a_price_ceiling_excludes_what_costs_more`, `test_a_ceiling_nothing_satisfies_says_so_instead_of_returning_silence`, `test_search_hides_unavailable_products_unless_asked_for_them`, `test_an_unknown_id_is_reported_as_missing_instead_of_dropped`, `test_detail_carries_the_type_specific_attributes`, `test_the_price_a_tool_returns_is_the_price_in_the_seed` — **e nenhum para `preco_minimo`** (NC-2) |
| **REQ-3** | Subagent `recomendacao` registrado com exclusivamente tools read-only | **CONFORME** | `test_registering_a_write_tool_on_the_recommendation_subagent_is_refused`, `test_the_recommendation_subagent_is_registered_with_the_three_read_only_tools`, `test_the_tools_are_the_three_names_the_eval_corpus_cites` · confirmado também por introspecção direta (§5) |
| **REQ-4** | Prompt proíbe afirmar fato sem origem em tool; preço citado = preço de `consultar_preco` | **CONFORME na letra**, **NÃO ATINGIDO no efeito** | O `PROMPT_RECOMENDACAO` contém as proibições, em regra mecânica. O efeito é medido pelo REQ-5 e a própria spec (DESC-1) registra que ele falha em `golden-006`/`golden-007` |
| **REQ-5** | Eval de groundedness executável localmente (`make evals-groundedness`) sobre 6 casos | **CONFORME quanto a "executável"**, **métrica NÃO ATINGIDA** (NC-3) | Alvo existe no `Makefile`; 6 casos declaram `spec: S-03`; `test_the_runner_loads_exactly_the_six_cases_that_declare_spec_s03`. Execução completa NÃO VERIFICÁVEL nesta sessão |

**Nota literal sobre o REQ-5.** Ele diz *"6 casos **golden**"*. O corpus são **5 golden + 1
adversarial** (`adversarial-004`, trazido para o conjunto pela DESC-2). O número bate, a família
não. É NC-9 (Baixa) — mas é o tipo de imprecisão que faz alguém na S-06 procurar um
`golden-00X` que nunca existiu.

---

## 4. Cenários BDD

| Cenário | Veredito | Como conferi |
|---|---|---|
| **1 — necessidade implícita vira recomendação ancorada** | **PARCIAL / NÃO VERIFICÁVEL na ponta** | `test_search_answers_an_implicit_need_with_something_that_pairs_with_red_wine` passa, e o docstring é **honesto sobre o que não mede**: *"A busca em memória não é a do Qdrant, e este teste não mede qualidade de embedding."* Ele prova que `harmonizacao`/`ocasiao` estão no material ranqueado — não que o Qdrant real recupera. O "3/4 depois do D-8" é medição do autor que eu não pude reproduzir. A metade "preços idênticos ao banco" eu **confirmei** para os 50 produtos (§2.1) |
| **2 — alucinação plantada é detectada** | **CONFORME** | `test_an_attribute_the_case_anchors_is_reproved_when_its_tool_was_never_called`, `test_an_anchored_field_missing_from_the_tool_return_is_reproved`, `test_a_catalogue_product_cited_without_being_retrieved_is_reproved`, `test_a_price_that_is_right_but_came_from_memory_is_reproved_too`. Falsifiquei os quatro componentes do portão (B5–B9) e todos reprovam pelo motivo certo. O cenário roda **sem agente, sem rede e sem chave** — que é o que o torna uma régua e não uma promessa |

---

## 5. As falsificações

43 quebras deliberadas, uma por vez, restaurando entre elas. **35 reprovaram, 8 sobreviveram.**

### 5.1 As que reprovaram (35) — amostra representativa

| # | Quebra | Teste que reprovou |
|---|---|---|
| B1 | Guarda de permissão neutralizada (`if False and …`) | `test_registering_a_write_tool_on_the_recommendation_subagent_is_refused` |
| B2 | `SOMENTE_LEITURA = frozenset()` | idem |
| B3 | `escritoras` devolve o valor neutro `()` | idem |
| B4 | Guarda movida para **depois** do efeito (`return` antes do `raise`) | idem |
| B44 | Tool de escrita contrabandeada dentro de `ferramentas_de_catalogo` | `test_the_tools_are_the_three_names_the_eval_corpus_cites` + `test_the_recommendation_subagent_is_registered_with_the_three_read_only_tools` |
| B5 | `verificar()` devolve veredito neutro (sempre aprovado) | 8 testes de `test_groundedness.py` |
| B6 | `_fatos_sem_origem` desligado do portão | `test_an_attribute_the_case_anchors_is_reproved_when_its_tool_was_never_called` + 2 |
| B7 | `_precos_divergentes` desligado | `test_a_price_no_tool_returned_is_reproved_and_named` + 1 |
| B8 | `_produtos_nao_recuperados` desligado | `test_a_catalogue_product_cited_without_being_retrieved_is_reproved` + 1 |
| B9 | `_tools_proibidas` desligado | `test_calling_a_tool_the_case_forbids_is_reproved_as_action_outside_the_allowlist` |
| B10 | Regex `DINHEIRO` não casa nada | `test_money_is_recognised_in_the_shapes_a_model_actually_writes` |
| B11 | Filtro de `ToolMessage` removido do stream | `test_the_stream_never_carries_a_tool_return_to_the_customer` |
| B12 | Preflight de catálogo vazio não falha mais | `test_the_application_refuses_to_start_with_an_empty_catalogue` |
| B13 | Preflight de catálogo ilegível engolido | `test_the_application_refuses_to_start_when_the_catalogue_table_is_missing` |
| B14/B15 | Redação de sequência de strings removida (ressalva **R-4** da S-02) | `test_a_list_valued_attribute_is_scrubbed_like_a_string_one` |
| B16 | `LOG_LEVEL` deixa de ser aplicado (ressalva **R-5** da S-02) | `test_log_level_from_the_environment_is_actually_applied` |
| B17 | `float` aceito como preço | `test_a_price_written_as_a_json_number_is_refused` |
| B19 | Frases cruzadas removidas do documento embedado (D-8) | `test_the_document_crosses_occasion_and_pairing_the_way_a_customer_asks` |
| B22 | `consultar_preco` para de reportar `nao_encontrados` | `test_an_unknown_id_is_reported_as_missing_instead_of_dropped` |
| B23 | `detalhar_produto` devolve o resumo em vez do detalhe | `test_detail_carries_the_type_specific_attributes` |
| B24 | Filtro de **teto** invertido — *controle da B20* | `test_a_price_ceiling_excludes_what_costs_more` + 1 |
| B29 | `apenas_disponiveis` nunca chega na busca | `test_search_hides_unavailable_products_unless_asked_for_them` |
| B30 | Veredito vazio do juiz vira aprovação | `test_an_empty_verdict_is_not_an_approval` |
| B31 | Juiz para de reprovar critério não atendido | `test_the_judge_returns_one_verdict_per_criterion_with_no_score` + 1 |
| B32 | Coerção de lista JSON-em-string removida (D-9) | `test_a_verdict_list_that_arrives_json_encoded_as_a_string_is_accepted` |
| B33 | Juiz não vê mais as chamadas de tool | `test_the_judge_sees_the_tool_calls_and_not_only_the_final_answer` |
| B34/B35 | Abertura do cenário deixa de derivar do caso (DESC-2) | `test_a_system_turn_produces_an_opening_derived_from_the_case_itself` |
| B37 | Catálogo vazio passa a ser escrito | `test_an_empty_catalogue_is_refused_instead_of_written` |
| B38 | Contagem de vetores ≠ produtos deixa de ser recusada | `test_indexing_refuses_a_vector_count_that_does_not_match_the_products` |
| B40/B43 | Preço / descrição entram no payload do Qdrant | `test_no_money_reaches_the_vector_index` |
| B41 | Point id vira aleatório (ingestão perde idempotência) | `test_the_point_id_is_derived_from_the_product_id_and_never_changes` |
| B42 | Ordem das colunas do Postgres embaralhada | `test_the_postgres_row_matches_the_declared_column_order` |

**A B24 é o controle que dá sentido à B20.** O mesmo tipo de quebra, na linha vizinha da mesma
expressão: o teto reprova, o piso não. Não é a suíte sendo fraca em geral — é um caminho
específico que ninguém cobriu.

### 5.2 As oito que sobreviveram

> Sobrevivente é **achado sobre o teste**, não sobre o código. Em todos os oito casos li o código
> e ele está **correto**; o que não existe é a prova de que continuará correto.

| # | Quebra que a suíte inteira não viu | Onde | Gravidade |
|---|---|---|---|
| **B20** | `preco_minimo >=` invertido para `<=` | `tools/catalogo.py` | **Alta** |
| **B25** | `preco_minimo` ignorado por completo (`if True or …`) | `tools/catalogo.py` | **Alta** |
| **B21** | Ordem do ranqueador descartada (reordena por id) | `tools/catalogo.py` | **Alta** |
| **B26** | Ordem do ranqueador **invertida** (`reversed(ids)`) | `tools/catalogo.py` | **Alta** |
| **B27** | `FOLGA_DE_RANQUEAMENTO = 6` → `0` | `tools/catalogo.py` | Média |
| **B28** | `limite` ignorado — devolve todos os candidatos | `tools/catalogo.py` | Média |
| **B36** | `envenenamento = None` em `rodar_caso` | `evals/runner.py` | **Alta** |
| **B18** | Coluna `preco` vira `double precision` | `catalogo.py` (DDL) | Baixa |

Agrupadas viram três achados: **NC-2** (as seis de `buscar_produtos`), **NC-1** (a B36) e
**NC-8** (a B18).

---

## 6. Não-conformidades

### NC-1 — **ALTA** · anular a fiação do envenenamento desliga o `adversarial-004` inteiro, e a suíte fica verde

`rodar_caso` conecta o turno `de: sistema` ao catálogo envenenado nesta linha:

```python
envenenamento = next(
    (fala.texto for fala in caso.conversa if fala.de == "sistema"),
    None,
)
```

Troquei o bloco inteiro por `envenenamento = None`. **446 passed.**

O efeito de `None` é total, não parcial: sem ele o `CatalogoEnvenenado` nunca é montado, o
`_abertura_do_cenario` nunca roda, e o `adversarial-004` passa a exercitar uma conversa comum
contra o catálogo limpo — sem nenhum vetor de injeção. O caso continuaria **aprovando**, e é isso
que o torna perigoso: a spec celebra, com razão, que *"o `adversarial-004` passou a aprovar, com
os sete critérios verdes"*. Depois desta quebra ele aprova pelo motivo errado, e nada avisa.

A causa é conhecida e tem nome nesta casa: `CatalogoEnvenenado` é testado isolado
(`test_the_poisoned_catalogue_replaces_a_description_and_nothing_else`) e `_abertura_do_cenario`
é testado isolado (`test_a_system_turn_produces_an_opening_derived_from_the_case_itself`), mas
**quem os liga não é testado por ninguém**. É literalmente a classe de erro que o relatório da
S-02 nomeou em §10 — *"testo a função que faz e não que alguém a chama"* — reaparecendo em
`evals/runner.py`.

Pesa mais por ser R4: `docs/testes.md` §2 põe R4 na camada `security`, e este é o único lugar do
repositório hoje onde a injeção vinda do dado recuperado é exercitada de verdade.

### NC-2 — **ALTA** · seis quebras em `buscar_produtos` sobrevivem; `preco_minimo` não tem um único teste

`buscar_produtos` é o REQ-2 inteiro, e quatro comportamentos declarados dele não têm prova:

1. **`preco_minimo`** — invertê-lo (B20) ou removê-lo (B25) não reprova nada. `test_a_price_ceiling_excludes_what_costs_more` cobre só `preco_maximo`; a busca por `preco_minimo` em `tests/unit/test_recommendation_tools.py` não retorna **nenhuma** ocorrência. O parâmetro está no contrato Pydantic, documentado ao modelo, e não é verificado.
2. **A ordem do ranqueador** — reordenar por id (B21) ou inverter (B26) não reprova. O comentário do próprio código defende essa linha como a coisa mais importante da função: *"reordenar por id ou por preço aqui jogaria fora a única coisa que a busca semântica produziu"*. Um invariante que o código declara em prosa e nenhum teste sustenta.
3. **`FOLGA_DE_RANQUEAMENTO`** (B27) — zerá-la não reprova, e a constante existe com justificativa escrita (*"sem folga um pedido de 'algo mais em conta' poderia voltar vazio"*).
4. **`limite`** (B28) — devolver todos os candidatos em vez de `na_faixa[:limite]` não reprova.

Contra `docs/testes.md` §3.1 — *"Toda feature nova nasce com teste unitário… Se a task não tem
teste, ela não está pronta"* — e o documento tem precedência sobre a spec.

### NC-3 — **MÉDIA** · a métrica de sucesso da própria spec não foi atingida

| Métrica declarada | Alvo | Medido (pelo autor) |
|---|---|---|
| Fatos sem origem em tool nos 6 casos | **0** — *uma ocorrência reprova* | **2 por execução** (4 de 6 aprovam, e os dois reprovados trocam entre execuções) |

Registro como não-conformidade **de métrica**, não como reprovação, e a distinção é deliberada:
a decisão de seguir está tomada pelo PO, escrita na DESC-1, **medida** (quatro rodadas de ajuste
de prompt, com o efeito de gangorra documentado), e o gate de evals só vira obrigatório na S-06.
O que a torna aceitável é justamente o que a spec fez: isolou a causa (D-3), nomeou o conserto
(tirar `preco` e `disponivel` do retorno de `buscar_produtos`) e recusou o atalho de editar o caso.

Não pude reproduzir o `4 de 6` — sem chave de provedor. **O número é palavra do autor.**

### NC-4 — **MÉDIA** · o arquivo-âncora do único risco declarado não existe

O frontmatter declara `riscos_cobertos: [R1]`. Os dois normativos apontam o mesmo arquivo:

- `docs/riscos.md`, linha R1 → `tests/unit/test_order_total.py`
- `docs/testes.md` §2, linha R1 → `tests/unit/test_order_total.py`

**O arquivo não existe** (`find . -name "test_order_total*"` → vazio), e nem `docs/riscos.md` nem
`docs/testes.md` foram emendados neste branch.

Substantivamente o R1 está coberto — 42 testes marcados `@pytest.mark.risco("R1")` em cinco
arquivos (`test_recommendation_tools`, `test_groundedness`, `test_eval_runner`,
`test_catalog_ingestion`, `test_boot`) —, e "total de pedido" é legitimamente da S-04. Mas
`docs/testes.md` §3.2 é categórico: *"Risco declarado sem teste correspondente não está fechado:
está prometido"*, e §2 diz que `/verificar-spec` cruza as duas coisas. O cruzamento falha.

O conserto certo **não** é criar um `test_order_total.py` artificial: é emendar a linha R1 dos
dois normativos para apontar os arquivos que de fato provam o risco hoje — e ambos são
CODEOWNERS, então a mudança passa pelo PO, que é o ponto.

### NC-5 — **MÉDIA** · o job `evals` do CI aponta para um caminho e um comando que não existem

`.github/workflows/ci.yml`:

```yaml
test -f backend/evals/runner.py && echo "evals=true" >> "$GITHUB_OUTPUT" || echo "evals=false" …
...
- run: uv run python -m evals.runner --report github-summary
```

O runner que a S-03 entregou está em **`backend/vendinha/evals/runner.py`**, e o módulo é
`vendinha.evals.runner`. Três divergências:

1. O detector nunca vai disparar — `backend/evals/runner.py` não existe. Hoje isso é inofensivo (o gate é da S-06), mas o comentário do próprio workflow diz *"este job precisa continuar pulado até a S-06 entregar `backend/evals/runner.py`"*, então a S-06 vai herdar uma heurística que ninguém percebeu que caducou.
2. `python -m evals.runner` está errado — o módulo é `vendinha.evals.runner`.
3. **`--report github-summary` não existe.** Confirmei com `--help`: as flags são `--spec`, `--caso`, `--saida`.

Quando alguém ligar o gate na S-06, o job vai falhar na linha de comando — não na qualidade do
agente. É a definição de check decorativo, que é o que este repositório recusa em voz alta.

### NC-6 — **BAIXA** · o eval não é o gate que o `Makefile` sugere que é

`make evals` sai com `exit 1` e uma mensagem correta apontando para a S-06 — bom. Mas
`make evals-groundedness` hoje **sai 0 mesmo com casos reprovando**? Não pude medir (sem chave),
e por isso registro como pergunta aberta e não como fato: o autor relata "4 de 6" sem dizer o
código de saída. Se o alvo sai 0 com caso vermelho, a S-06 vai precisar mudar mais do que ligar o
job. Vale um `echo $?` na próxima execução do autor.

### NC-7 — **BAIXA** · as caixas de requisito e o DoD da spec continuam desmarcados

Todos os `- [ ] REQ-N` e o `- [ ] Checklist padrão do template` estão desmarcados, com a spec em
`status: em-revisao` e nove commits entregues. O `status` está certo para este estágio; as caixas
não refletem o estado.

### NC-8 — **BAIXA** · o DDL que torna dinheiro exato não é verificável por nenhum teste

Trocar `numeric(8,2)` por `double precision` (B18) sobrevive à suíte inteira. Não é defeito de
disciplina do autor: é a consequência declarada de `docs/testes.md` §1 — *"Não existe camada de
integração neste repositório… o que só se prova com infraestrutura de verdade é verificado à mão
no `/verificar-spec`"*. **Foi o que eu fiz** (§2.1): `('numeric', 8, 2)` confirmado no
`information_schema` do Postgres real, 50/50 preços em `Decimal` exato. Fica registrado que a
garantia é humana e precisa ser refeita a cada rodada.

### NC-9 — **BAIXA** · "6 casos golden" são 5 golden + 1 adversarial

Ver §3, nota literal do REQ-5.

---

## 7. Invariantes globais

| Invariante | Resultado |
|---|---|
| **Escopo** — o que a spec pôs fora do escopo entrou? | **Não.** Nenhuma tool de checkout, nenhum supervisor além do roteamento binário. As tasks 4 e 6 (ressalvas da S-02) são escopo **acrescentado**, mas com decisão de PO registrada (D-4) e rastreável a commits próprios |
| **Segredo / CPF / CNPJ / certificado / dado real no diff** | **Nenhum.** Varri as 5.256 linhas adicionadas por `sk-…`, `sk-ant-`, `AKIA…`, `ghp_…`, `-----BEGIN`, CPF e CNPJ formatados, e-mail e dígitos longos. Único hit: `89,90000000000001`, ilustração de perda de precisão de float num docstring |
| **PII mascarada** | **Sim, e reforçada.** A ressalva R-4 da S-02 (sequência de strings atravessando o hook intocada) está fechada com `_is_string_sequence`, e as duas formas de quebrá-la reprovam (B14, B15) |
| **Fronteira de permissão de subagents** | **Estrutural, e provada.** Introspecção direta: `recomendacao` recebe exatamente `buscar_produtos`, `detalhar_produto`, `consultar_preco`, todas `escreve=False`, `escritoras=()`. Tentativa de registrar `criar_pedido` → `FronteiraDePermissaoViolada` |
| **`riscos_cobertos` × `docs/riscos.md` × `docs/testes.md` §2** | **Divergente** — ver **NC-4**. R1 é o risco certo para esta spec nas duas matrizes; o arquivo-âncora nomeado não existe |
| **Corpus de evals intacto** | **Sim.** `git diff origin/main...HEAD -- evals/` **vazio**. Nenhum caso editado para ficar verde (ADR-006 + CODEOWNERS honrados) |
| **Seed intacto** | **Sim.** `git diff origin/main...HEAD -- data/` **vazio** |
| **ADRs preservados** | **Sim.** `docs/adr/` não aparece no diff. O único arquivo de `docs/` tocado é a própria spec |

### 7.1 As cinco ressalvas da S-02 que a task 6 diz fechar

| Ressalva S-02 | Veredito | Prova |
|---|---|---|
| **R-3** — `redact()` sem consumidor em produção | **Fechada** | O docstring declara o único consumidor (`db.py:main`) e explica por quê; e o conserto real é que `tests/security/test_pii_redaction.py` passou a atravessar `redactor()` — a metade forte — em 9 asserções que antes usavam `redact()`. Conferi o diff linha a linha |
| **R-4** — `Redactor.attributes` só redige `str` | **Fechada** | `_is_string_sequence` + `test_a_list_valued_attribute_is_scrubbed_like_a_string_one`. Duas quebras independentes reprovam (B14, B15) |
| **R-5** — `LOG_LEVEL` sem consumidor | **Fechada** | Aplicado em `install_log_redaction()`, com justificativa de por que ali e não em outro lugar. B16 reprova |
| **R-10** — esquecer `make db-setup` só falha na 1ª mensagem | **Fechada, e melhor do que pedia** | `_conferir_catalogo` recusa subir com tabela ausente **ou vazia**. B12 e B13 reprovam. Conferi que a mensagem é verdadeira: `db.py` de fato cria `produto` via `PostgresCatalogo(dsn).setup()` e imprime *"checkpointer, instance_config and produto ready. next: `make seed`"* |
| **R-14** — cobertura assimétrica do `lifespan` | **Fechada** | O corpo comum saiu para `preparar()`, alcançável pelos dois ramos; o docstring declara com precisão o que sobra sem cobertura (o `async with`). `create_app` ganhou o seam `catalogo` |

Cinco de cinco, com teste que morde em quatro delas e conferência documental na quinta. É o
melhor item deste relatório.

---

## 8. Avaliação das "Descobertas" — mudança de escopo a justificar, não fato aceito

| # | Veredito | Comentário |
|---|---|---|
| **DESC-1** (D-3 colide com o corpus) | **Descoberta legítima, e exemplarmente conduzida** | Não é escopo novo com outro nome: é uma medição que só a execução produz. Respeitou a precedência — citou `docs/testes.md` para **recusar** o conserto por prompt, e citou o ADR-006 para recusar editar o caso. Verifiquei o que dava para verificar: `evals/` intacto. A decisão do PO de manter o D-3 é decisão de PO; a **NC-3** registra que a métrica fica em aberto |
| **DESC-2** (`adversarial-004` presume busca anterior) | **Legítima, com uma ressalva de método** | O diagnóstico está certo e o conserto é o certo — montar o cenário rodando **uma busca de verdade** em vez de fabricar histórico. E a generalização (derivar de `produtos_validos`, não hard-code por caso) é boa engenharia. **Ressalva:** o resultado alegado — *"passou a aprovar, com os sete critérios verdes"* — eu não pude reproduzir; e a **NC-1** mostra que a fiação que produz esse resultado não tem teste |
| **DESC-3** (corpus não distingue "recomendar" de "qualificar") | **Legítima, e corretamente parada** | É exatamente o que o `CLAUDE.md` manda fazer: *"Se descobrir necessidade nova: anotar em Descobertas e parar para decisão do PO"*. A conclusão — *"é uma regra de condução que ainda não está escrita em nenhum documento normativo"* — é a leitura certa. **Nenhuma ação foi tomada unilateralmente**, e é isso que a torna aceitável. Fica para o PO decidir onde ela mora |
| **Escopo disfarçado?** | **Não encontrei** | As tasks 4 e 6 são escopo acrescentado, mas por decisão de PO declarada no pre-flight (D-4) e rastreável a commits isolados. As decisões D-5/D-6 (recusar `langchain-qdrant` e `langsmith`) são **recusas** de dependência com justificativa normativa — reduzem escopo, não aumentam |
| **Emenda de ADR por prosa?** | **Não.** | `docs/adr/` não foi tocado. O D-1 declara que contraria a **letra** do RNF-1 e diz explicitamente *"Se o PO quiser, vira ADR-013"* — ou seja, não se auto-autorizou. Isso é o comportamento correto, e continua sendo uma pendência aberta para o PO (ver Ressalva RS-1) |

---

## 9. Ressalvas para as specs seguintes

| # | Ressalva | Para quem |
|---|---|---|
| **RS-1** | O **D-1** deixa o RNF-1 contrariado na letra: `make seed` e `make evals-groundedness` exigem `OPENAI_API_KEY` numa instância que conversa só por Anthropic. Está declarado em três lugares e **não** virou ADR. Enquanto não virar, o Quickstart do RNF-1 tem uma dependência externa não decidida formalmente | PO / S-08 |
| **RS-2** | A S-06 herda a **NC-3** com a causa isolada (D-3). O conserto nomeado — tirar `preco` e `disponivel` do retorno de `buscar_produtos` — muda um contrato Pydantic que a S-04 vai consumir. Decidir **antes** da S-04, não depois | S-04 / S-06 |
| **RS-3** | `EVALS_JUDGE_MODEL` vazio faz o agente julgar a si mesmo. O runner avisa em voz alta, o que é correto — mas todo número de eval produzido até aqui carrega esse viés, inclusive o `4 de 6` | S-06 |
| **RS-4** | O R2 continua **estruturalmente pendente**: `tests/security/test_permission_boundary.py` não existe, e o `subagents.py` explica bem por quê (não há tool de escrita ainda, o teste passaria por vacuidade). A S-04 **precisa** entregá-lo junto da primeira tool de escrita, ou o R2 fica prometido | S-04 |
| **RS-5** | `Ferramenta.escreve` é **declarado por quem registra**, não inferido. É a decisão certa e está justificada. O que protege o subagent hoje contra um `escreve=False` distraído é a lista de nomes fixada em dois testes (B44) — não o registro. Quando a S-04 registrar tools de escrita, essa proteção não se estende sozinha | S-04 |
| **RS-6** | `qdrant-client` preso ao minor da imagem (D-7): subir a imagem do compose passa a exigir commit nos dois lugares. Não há teste nem check que force isso | S-08 |

---

## 10. Veredito

# APROVADO COM RESSALVAS

O núcleo se sustenta e eu o provei quebrando: a fronteira de permissão é estrutural, o portão
determinístico de groundedness tem um teste por componente e todos mordem, as cinco ressalvas da
S-02 estão realmente fechadas, o corpus de evals e o seed não foram tocados, e o dinheiro
atravessa o Postgres real como `Decimal` exato nos 50 produtos.

### Por que não APROVADO

Três coisas, e a primeira sozinha bastaria:

1. **Oito quebras deliberadas sobreviveram**, e uma delas (**NC-1**) desliga o vetor de injeção inteiro do `adversarial-004` deixando 446 testes verdes. Um APROVADO com uma sobrevivente dessas seria um veredito sobre a suíte, não sobre a entrega.
2. **O único risco declarado não cruza com a matriz** (**NC-4**). `docs/riscos.md` e `docs/testes.md` têm precedência sobre a spec, e os dois nomeiam um arquivo que não existe.
3. **A métrica de sucesso da própria spec não foi atingida** (**NC-3**). Que a decisão seja do PO não a transforma em métrica atingida — transforma em métrica atingida *depois*.

### Por que não REPROVADO

Nenhum requisito central caiu, e **nenhuma quebra deliberada passou pelo caminho que a regra de
ouro protege**. As 35 falsificações que reprovaram cobrem tudo que decide *o que pode ser feito*:
permissão, preço, origem de fato, tool proibida, vazamento de payload no chat, redação de PII. As
oito sobreviventes são todas sobre *qualidade de recuperação e fiação de teste* — nenhuma delas é
um caminho até uma ação indevida, e em todas eu li o código e o encontrei correto.

O eval em 4 de 6 também não reprova, por três motivos que só valem juntos: a decisão é do PO, está
escrita **com a medição que a sustenta**, e o caminho fácil — editar o caso que reprovou — foi
explicitamente recusado e eu **verifiquei** que não foi tomado. Uma spec que entrega o eval
vermelho com a causa isolada vale mais do que uma que entrega verde sem ninguém saber por quê.

---

## 11. Condições de fechamento, em ordem de importância

1. **Testar a fiação do envenenamento em `rodar_caso` (NC-1).** Um teste que prove que um caso com turno `de: sistema` produz um `CatalogoEnvenenado` e uma abertura — e que reprove com `envenenamento = None`. É o achado mais caro deste relatório.
2. **Fechar as seis lacunas de `buscar_produtos` (NC-2)**, prioritariamente `preco_minimo` (nenhum teste) e a preservação da ordem do ranqueador (invariante que o código declara em prosa e ninguém sustenta). `FOLGA_DE_RANQUEAMENTO` e `limite` podem vir junto — são o mesmo arquivo de teste.
3. **Reconciliar a linha R1 de `docs/riscos.md` e `docs/testes.md` §2 (NC-4)** com os arquivos que de fato provam o risco. Ambos são CODEOWNERS: a mudança passa pelo PO, que é o desenho.
4. **Corrigir o job `evals` do CI (NC-5)** — caminho de detecção, módulo (`vendinha.evals.runner`) e a flag `--report github-summary`, que não existe. Ou, se a decisão for deixar para a S-06, **registrar isso na spec** para que a S-06 não herde uma heurística silenciosamente caduca.
5. **Marcar as caixas de REQ e o DoD da spec (NC-7)**, e alinhar o texto do REQ-5 com o corpus real — 5 golden + 1 adversarial (NC-9).
6. **Levar o D-1 ao PO como ADR-013 ou registrar a recusa (RS-1)**, e decidir a RS-2 (contrato de `buscar_produtos`) **antes** da S-04, já que a S-04 consome esse contrato.
7. **Reportar o código de saída de `make evals-groundedness` com caso vermelho (NC-6)** na próxima execução com credencial.

Itens 1 a 3 são correção antes do PR. Itens 4 a 7 admitem registro explícito na spec como
alternativa à correção, desde que o registro seja escrito — não combinado.
