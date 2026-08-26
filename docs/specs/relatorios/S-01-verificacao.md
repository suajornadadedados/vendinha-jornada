# Relatório de verificação independente — S-01 (Discovery como código)

| | |
|---|---|
| **Spec** | `docs/specs/S-01-discovery-como-codigo.md` (`status: em-revisao`) |
| **Branch** | `spec/s-01-discovery` @ `ce8b46f` |
| **Base** | `origin/main` @ `7bbfa86` (PR #12, squash — **um pai só**, ao contrário do #11) |
| **PR** | **não existe ainda.** A branch não foi publicada. É o comportamento correto sob o `CLAUDE.md` desta mesma branch: *"sem veredito, não existe PR"* |
| **Issue** | [#2](https://github.com/suajornadadedados/vendinha-jornada/issues/2) — **OPEN**, corpo é ponteiro puro para a spec |
| **Diff** | 7 commits · 38 arquivos · +2.343 / −52 |
| **Sessão** | revisora, sem acesso ao histórico da sessão autora |
| **Data** | 2026-08-26 15:25 UTC |
| **Ambiente** | Windows 11, Python 3.12.5, uv 0.6.9, Node v22.16.0, Docker 27.2.0, Git 2.46.0. **`make` não existe nesta máquina** (D-3 confirmada) |
| **Veredito** | **APROVADO COM RESSALVAS** |

> **Nota sobre o comando do diff.** A instrução da verificação era `git diff main...spec/s-01-discovery`.
> O ref local `main` está parado em `627b905`; o `origin/main` real está em `7bbfa86` (PR #12 já
> mergeado). Contra o `main` local o diff aparece com 46 arquivos e carrega os commits de correção
> da S-00 por dentro. **Todos os números deste relatório são contra `7bbfa86`**, que é a base
> verdadeira da branch: 38 arquivos, 7 commits, nenhum deles da S-00.

---

## 1. Resumo

A entrega é boa e o núcleo dela se sustenta sob falsificação: rodei **22 quebras deliberadas**
(11 no seed, 11 no corpus) e **as 22 reprovaram**, cada uma no teste certo e por motivo legível.
Os dois validadores que "nasceram verdes" não nasceram vazios — o seed é recusado por preço em
float, por preço com uma casa decimal, por id duplicado, por queijo sem maturação, por queijo
arquivado em `cafes.json`, por produto com menos de 4 atributos e por arquivo novo fora do mapa;
o corpus é recusado por id que não bate com o arquivo, família trocada, spec inexistente, risco
fora da matriz, produto que o catálogo não tem e produto renomeado **no seed** com o caso intacto.
Restaurei todos os arquivos; `git status --short` fica limpo.

As métricas conferem, todas medidas por mim: **50 produtos**, **12 golden / 6 adversariais**,
**100%** com preço decimal em string, **mínimo de 5 atributos** por produto (alvo era ≥4),
**294 passed**. `gitleaks` em 27 commits: `no leaks found`. Amostrei três casos golden à mão e os
produtos citados não só existem — eles *fazem sentido*: os nove ids do `golden-001` têm todos
`vinho tinto` em `harmonizacao` e `presente`/`receber visita` em `ocasiao`; as três alternativas do
`golden-006` estão de fato disponíveis enquanto o Geisha está `disponivel: false`; e as quatro
alternativas do `golden-007` custam todas menos que os `118.00` do Canastra curado.

O que impede o APROVADO limpo é o **REQ-1**, que é o requisito mais amplo da spec e o único que
não se prova com um comando: *"sem contradição entre normativos"*. A varredura achou a
contradição do R3 (a camada de integração que não existe), criou o ADR-011 para resolvê-la e
corrigiu oito lugares — mas a mesma contradição existe para o **R2**, em cinco lugares que
continuam dizendo "teste unitário" onde `docs/riscos.md` e `docs/testes.md` agora dizem `security`.
Um deles é o **REQ-2 da S-04**, isto é, o texto que vai dirigir a próxima sessão a escrever o teste
na camada errada. O autor corrigiu o R2 em `docs/arquitetura.md` §3.1 no mesmo commit — sabia que a
camada tinha mudado — e parou ali. A afirmação da D-1 de ter encontrado *"a única contradição entre
normativos do repositório"* não sobrevive a um grep.

Somam-se: o `riscos_cobertos: [R1, R7]` do frontmatter, que a própria matriz de riscos atribui a
S-03 e S-06; e uma nota de caso de eval que afirma um fato aritmeticamente falso sobre CPF.

**4 CONFORME · 1 NÃO CONFORME · 0 NÃO VERIFICÁVEL** (requisitos), com 5 não-conformidades
adicionais e 11 ressalvas.

---

## 2. Conformidade requisito a requisito

| # | Requisito | Status | Evidência que EU produzi |
|---|---|---|---|
| REQ-1 | `requisitos.md`, `jornada.md`, `riscos.md`, `decisoes.md` e ADRs 001-010 revisados e definitivos: **sem referência morta e sem contradição entre normativos** | **NÃO CONFORME** | A parte de referência morta está OK: varri todo caminho de arquivo citado em `docs/**` e `CLAUDE.md` e o único conjunto "ausente" são arquivos de spec futura (`tests/security/test_hitl_invariant.py`, `backend/evals/runner.py`, …), que são promessa datada, não referência quebrada. A parte de contradição **não**: cinco lugares ainda atribuem ao **R2** a camada `unit`, enquanto `docs/riscos.md` R2 e `docs/testes.md` §2 agora dizem `security`. Ver **NC-1**. |
| REQ-2 | Schema dos casos validável por script (`make evals-check`); cada caso declara necessidade, critério de aprovação e produtos válidos | **CONFORME** | `evals/schema/caso.schema.json` exige `id, familia, titulo, riscos, spec, conversa, criterio`, com `produtos_validos` obrigatório em `golden` via `allOf/if-then` e `additionalProperties: false`. Sem `make` na máquina, rodei a linha de dentro do alvo — `python -m pytest tests/unit/test_eval_corpus_is_traceable.py -q` → **91 passed**. Falsifiquei 11 vezes (§5): as 11 reprovaram. |
| REQ-3 | Golden dataset: **12** conversas em `evals/golden/`, YAML validado contra o schema, com necessidade, critério e produtos válidos | **CONFORME** | `ls evals/golden/*.yaml \| wc -l` → **12**. Os 12 validam contra o schema; os 12 declaram `produtos_validos` (de 1 a 9 ids), e os 12 declaram `criterio.deve` + `criterio.nao_deve`. Cruzei os 40 ids citados contra `data/catalogo/`: **nenhum ausente**. Amostragem manual de 3 casos: ver §1. |
| REQ-4 | Suite adversarial: **6** casos de injection/abuso em `evals/adversarial/`, mesmo formato | **CONFORME** | `ls evals/adversarial/*.yaml \| wc -l` → **6**. Cobrem injeção pelo canal do cliente (001), engenharia social contra o HITL (002), extração de PII (003), **injeção vinda do próprio dado recuperado** (004), pressão social sobre o preço sem injeção nenhuma (005) e abuso de custo/loop (006). Os três novos são os mais interessantes do corpus: 004 e 005 atacam por onde o modelo não desconfia. |
| REQ-5 | Catálogo seed `data/catalogo/*.json` com ~50 produtos, atributos ricos, `disponivel` e `prazo_estimado`, preço como **string decimal** | **CONFORME** | **50 produtos** em 4 arquivos (queijos 13, doces 13, cafés 12, cachaças/licores 12). 50/50 com `preco` string casando `^[0-9]{1,6}\.[0-9]{2}$` e sobrevivendo a `Decimal` sem perda. 50/50 com `disponivel` e `prazo_estimado`. **5 produtos com `disponivel: false`**, exatamente como o README declara — sem eles o caminho "não temos isso agora" não seria exercitável. Faixa de preço `24.00`–`236.00`. Zero id duplicado. |

---

## 3. Cenários BDD

```gherkin
Cenário: rastreabilidade risco → verificação
  Dado a matriz de riscos R1-R9
  Quando leio qualquer linha
  Então ela aponta uma spec responsável e uma verificação automatizada
```

**CONFORME.** Li as nove linhas de `docs/riscos.md` uma a uma. Todas nomeiam spec (S-02 a S-06) e
**camada + arquivo** de teste — o que antes desta spec era texto livre em cinco delas ("dashboard
Langfuse Cloud" no R6, "testes de contrato dos adapters" no R8). Cruzei linha a linha contra
`docs/testes.md` §2: **as duas tabelas concordam nas nove linhas**, em camada e em nome de arquivo.
Esse era o objetivo declarado da D-1 e ele foi atingido *entre esses dois documentos*. O que não foi
atingido é a concordância com o resto do repositório (NC-1).

Ressalva de leitura: o R9 aponta `tests/unit/test_session_resume.py` **mais** verificação manual, e
o R1 aponta um arquivo que só existe na S-04. "Verificação automatizada" no R9 é parcial e no R1 é
futura — mas ambas estão escritas como tal, sem fingimento.

```gherkin
Cenário: casos de eval válidos
  Quando executo "make evals-check"
  Então o schema valida necessidade, critério de aprovação e produtos citados de cada caso sem erro
```

**CONFORME**, com a substituição registrada. `make` não existe nesta máquina — confirmado com
`which make`, saída vazia. Li o `Makefile` e rodei a linha de dentro do alvo `evals-check`:

```
$ python -m pytest tests/unit/test_eval_corpus_is_traceable.py -q
...........................................................................
................                                            91 passed
```

O alvo é uma linha só, como o `README` promete, então a substituição é literal e não um atalho.

---

## 4. Métricas medidas vs alvo

| Métrica | Alvo | Spec declara | **Eu medi** | Status |
|---|---|---|---|---|
| Casos golden / adversariais | 12 / 6 | 12 / 6 | **12 / 6** | CONFORME |
| Produtos no seed | ≥ 50 | 50 | **50** | CONFORME |
| Produtos com preço | 100% | 100% | **50/50**, todos string decimal, todos round-trip em `Decimal` | CONFORME |
| Produtos com ≥ 4 atributos | 100% | 100% | **50/50** — mínimo observado **5**; distribuição 5:13, 6:13, 7:24 | CONFORME |
| Riscos com ao menos um caso | — | R1-R6 e R8 | **R1 (11 casos) · R2 (5) · R3 (3) · R4 (5) · R5 (1) · R6 (1) · R8 (1)** · R7 e R9 sem caso | CONFORME |
| Suíte local | verde | 294 passed | **294 passed em 0,48 s** (`bash scripts/run-tests.sh`) | CONFORME |
| `ruff check` / `ruff format --check` | limpo | — | **All checks passed** / **8 files already formatted** | CONFORME |
| `mypy` strict no backend | limpo | — | **Success: no issues found in 1 source file** | CONFORME (ver R-4) |
| `commitlint` na branch | 0 problemas | — | **0 problems, 1 warning** (`footer-leading-blank`) em 7 commits | CONFORME |
| `gitleaks` no histórico | 0 leaks | — | **no leaks found**, 27 commits, 879 KB, exit 0 | CONFORME |
| Commits entregues | 5 (tabela da spec) | 5 | **7** (6 com escopo `s-01` + 1 `harness`) | ver **NC-4** |

**Sobre `docker compose`.** Não subi contêiner, e registro o porquê em vez de omitir: as duas
camadas deste repositório não usam infraestrutura (`docs/testes.md` §1 e §6: *"nenhuma das duas
camadas precisa de contêiner"*), `scripts/run-tests.sh` não toca em rede, e os dois arquivos de
teste desta spec só leem arquivos já versionados — verifiquei os imports (`json`, `yaml`,
`jsonschema`, `pathlib`, `decimal`, `re`). Subir Postgres e Qdrant não mudaria um único resultado
acima. O `docker` foi usado, sim, mas para o `gitleaks`.

### 4.1 As falsificações que executei

Esta é a evidência que não é auto-declarada. **22 quebras, 22 reprovações.** Em cada uma: quebrei o
arquivo, rodei o guarda, restaurei com `git checkout --`.

**Seed — `tests/unit/test_catalog_seed_is_usable.py`**

| # | O que quebrei | Reprovou em |
|---|---|---|
| S1 | `"preco": "89.90"` → `"preco": 89.90` (número JSON) | `..._matches_the_normative_schema` **e** `..._price_survives_decimal_without_a_float` |
| S2 | `"89.90"` → `"89.9"` (uma casa decimal) | `..._matches_the_normative_schema` |
| S3 | `"89.90"` → `"00.00"` (preço zero) | `..._price_survives_decimal_without_a_float` |
| S4 | dois produtos com o mesmo `id` | `test_no_product_id_is_used_twice` |
| S5 | queijo sem `maturacao` (schema condicional, JSON continua válido) | `..._matches_the_normative_schema`: `'maturacao' is a required property` |
| S6 | campo `"estoque_real": 3` (additionalProperties) | `..._matches_the_normative_schema` |
| S7 | queijo movido para `cafes.json` | `test_product_type_matches_the_file_it_lives_in` |
| S8 | um produto a menos (49) | `test_the_seed_has_enough_products` |
| S9 | produto sem `harmonizacao`/`ocasiao`/`maturacao`/`intensidade` | `..._carries_enough_attributes_to_be_recommended` **e** o schema |
| S10 | arquivo `temperos.json` novo, fora do mapa de tipos | `test_product_type_matches_the_file_it_lives_in` |
| S11 | seed com JSON malformado | reprova, mas por **erro de coleta** — ver R-10 |

**Corpus — `tests/unit/test_eval_corpus_is_traceable.py`**

| # | O que quebrei | Reprovou em |
|---|---|---|
| C1 | `id` diferente do nome do arquivo | `test_case_id_and_family_match_where_the_file_lives` |
| C2 | `familia: golden` → `adversarial` na pasta `golden/` | idem |
| C3 | `spec: S-99` (padrão do schema é **válido**, arquivo não existe) | `test_every_spec_cited_by_a_case_exists` — isolado, o schema passa |
| C4 | `produtos_validos` com `queijo-que-nao-existe` | `..._product_cited_by_a_case_exists_in_the_seed` — isolado |
| C5 | **renomeei o produto no seed**, casos intactos | `..._product_cited_by_a_case_exists_in_the_seed` em 5 casos ao mesmo tempo. É a direção que importa: o vínculo quebra dos dois lados |
| C6 | golden sem `produtos_validos` | `..._matches_the_normative_schema` (o `if-then` funciona) |
| C7 | `criterio` sem `nao_deve` | idem |
| C8 | chave `peso_do_caso` desconhecida | idem |
| C9 | **removi a linha do R8 de `docs/riscos.md`**, caso intacto | `..._risk_cited_by_a_case_exists_in_the_matrix` — isolado. Prova que o valor esperado vem da matriz, não de uma lista recopiada no teste |
| C10 | `riscos: [R42]` | schema **e** matriz |
| C11 | `falha_dura: talvez` | `..._matches_the_normative_schema` |

**Uma quebra passou despercebida** — e não está na lista acima porque não é um dos dois validadores
sob julgamento, mas vale como achado: troquei `requisitos: [RF-1.1, RF-1.2, RF-1.4]` por
`requisitos: [RF-9.9, RNF-99]` no `golden-001` e a suíte inteira **passou** (91 passed). Ver **R-1**.

---

## 5. Invariantes globais

| Invariante | Verificação | Resultado |
|---|---|---|
| Ausência de segredo no diff | `gitleaks v8.29.0` no histórico completo com `.gitleaks.toml` do repo | **OK.** `no leaks found`, 27 commits |
| Ausência de CNPJ, certificado, dado real | grep por CPF/CNPJ formatados, sequências de 11/14 dígitos, `BEGIN PRIVATE KEY`, `sk-`, `ghp_`, `APP_USR-`, `*_TOKEN=`, `*_KEY=` em todo o diff | **OK.** Nenhum CNPJ, nenhum certificado, nenhuma chave. Os únicos números pessoais são dois CPFs de teste — abaixo |
| CPFs são números de teste conhecidos e declarados | `golden-008` usa `111.111.111-11` e `123.456.789-09`; `tests/unit/conftest.py` e `tests/security/conftest.py` (ambos da S-00) usam `123.456.789-09`, com o comentário *"Never a real CPF, in any file, ever"* | **OK quanto ao guardrail.** `123.456.789-09` é o CPF de teste canônico; `111...11` é a sequência repetida clássica. Mas a **justificativa escrita** do `golden-008` está errada: ver **NC-3** |
| Produtores do seed são fictícios | Li os 17 produtores. `Fazenda Boa Sorte`, `Laticínio Serra Dourada`, `Alambique Pé de Serra`, `Doceria Vovó Zulmira`, `Sítio Névoa Alta`… Nenhum CNPJ, endereço, telefone, e-mail ou URL em nenhum produto (grep limpo em `data/catalogo/`) | **OK.** As denominações geográficas (Canastra, Serro, Araxá, Campo das Vertentes, Cerrado Mineiro) são indicações públicas, e o `README` do diretório declara isso |
| Escopo respeitado ("Fora de escopo: runner de evals, ingestão no Qdrant") | `find backend -type f` e diff completo | **OK.** Nenhum runner, nenhum cliente Qdrant, nenhuma rota, nenhum grafo, nenhuma tool. `backend/` continua sendo o scaffold vazio da S-00 |
| Fronteira de permissões de subagents | não aplicável (nenhum subagent existe até a S-04) | **N/A** |
| PII mascarada em traces | não aplicável (não há agente nem trace até a S-02) | **N/A** |
| Suíte restaurada após as falsificações | `git status --short` ao fim de cada bateria | **OK.** Única entrada é `?? docs/workshop/apresentacao.html`, arquivo não rastreado que já existia antes desta sessão e que não pertence à S-01 |

---

## 6. Avaliação das "Descobertas"

Lidas como *alterações de escopo a justificar*, não como fatos aceitos.

| # | Veredito | Comentário |
|---|---|---|
| **D-1** | **Legítima na causa, incompleta na resolução, e o processo foi o certo** | A contradição existe e é estrutural, confirmei os oito lugares. A resolução via ADR novo é o único caminho compatível com o harness: o `ADR-003` está aceito, e verifiquei que ele **não foi reescrito por dentro** — `git diff` mostra exatamente **3 linhas adicionadas no topo**, corpo byte a byte intacto, no mesmo formato que o ADR-007 recebeu do ADR-010 (que confirmei existir, como precedente real do repositório). Sobre a precedência: `docs/riscos.md` (3) está acima de `docs/testes.md` (4), e a resolução **não passou por cima disso** — em vez de declarar o documento inferior vencedor, o autor emendou o superior, que é o movimento correto. O ADR (nível 5) não "venceu" a matriz; ele registrou a decisão que **motivou** a mudança da matriz. Isso é o mecanismo funcionando. **O que falha é a varredura**, não o método: ver NC-1 |
| **D-2** | **Legítima e no escopo** | O `tests/unit/conftest.py` da S-00 dizia literalmente *"when the S-01 seed lands, these names have to exist in it"*. A S-01 fez o seed chegar; consertar a fixture é consequência prevista pelo próprio arquivo, não invasão de escopo. Conferi os três produtos contra o catálogo: `queijo-canastra-meia-cura` `89.90` ✓, `doce-de-leite-cremoso` `32.00` ✓, `cafe-fermentado-anaerobico` `96.00` com `disponivel: false` ✓, `maturacao_dias: 45` bate com `"45 dias"` ✓. A direção do conserto é a certa (`docs/testes.md` §4: valor esperado vem de fonte independente). Ver R-3 sobre o que continua desprotegido |
| **D-3** | **Legítima e confirmada** | `which make` → vazio. Rodei a linha de dentro do alvo e cheguei ao mesmo lugar. O `README` já previa |
| **D-4** | **Legítima** | R7 é a suíte inteira por definição de `docs/testes.md` §2 — nenhum caso individual pode cobri-lo, e um caso que dissesse `riscos: [R7]` seria ruído. R9 exige matar o processo, coisa que nenhuma conversa faz; `docs/testes.md` §1 já o manda para `test_session_resume.py` + verificação manual. **As duas ausências se justificam.** Medi a cobertura e ela bate: R1-R6 e R8 têm caso, R7 e R9 não |

**Descoberta que eu esperaria e não encontrei registrada:** a mesma varredura que achou "integração"
não foi feita para "unitário". Ver NC-1.

---

## 7. Não-conformidades (fora da tabela de requisitos)

| # | Achado | Gravidade |
|---|---|---|
| **NC-1** | **REQ-1: a contradição de camada sobrevive no R2, em cinco lugares.** `docs/riscos.md` R2 e `docs/testes.md` §2 dizem `security` / `tests/security/test_permission_boundary.py`. Continuam dizendo `unit`: `docs/specs/S-04-fronteira-pagamento.md:19` (*"REQ-2 … com **teste unitário** que falha se `recomendacao` ganhar tool de escrita (invariante R2)"*), `docs/specs/S-04-fronteira-pagamento.md:30` (task 2, *"boundary **unit test**"*), `docs/adr/ADR-002-…:13` (*"**teste unitário** trava a fronteira"*), `.claude/skills/vendinha-harness/SKILL.md:45` (*"garantido por **teste unitario** que falha se a fronteira vazar"*) e `docs/img/arquitetura-produto.svg:256` (*"**teste unitário** falha se a fronteira vazar"*). Este último é o diagrama **do próprio `docs/arquitetura.md`**, cujo texto o commit `7b9e07a` corrigiu para `security` na linha 63 — a prosa e a figura do mesmo documento hoje discordam. O caso do `S-04:19` é o mais caro: é texto de **requisito**, e a sessão da S-04 vai lê-lo como fonte da verdade e escrever o teste na camada errada — exatamente o dano que a D-1 existe para impedir. A spec afirma que a D-1 encontrou *"a única contradição entre normativos do repositório"*; um `grep -i "teste unit"` mostra que não. | **Alta** |
| **NC-2** | **`riscos_cobertos: [R1, R7]` sem os testes-âncora, e contra a própria matriz.** `docs/testes.md` §3 item 2: *"Toda spec que declara `riscos_cobertos` entrega os testes da tabela acima… Risco declarado sem teste correspondente não está fechado: está prometido."* A S-01 não entrega `tests/unit/test_order_total.py` nem a suíte rodando. A spec argumenta, em prosa, que entrega "pré-condições" — e o argumento **é bom**, mas ele está no nível 6 da precedência (`docs/specs/`) tentando destravar o nível 4 (`docs/testes.md`). Prosa dentro de uma spec não emenda um normativo superior; o que emenda é ADR ou edição do normativo — mecanismo que esta mesma spec usou muito bem para o ADR-011 e não usou aqui. Pior: `docs/riscos.md` atribui **R1 → S-03** e **R7 → S-06** na coluna "Spec". O frontmatter da S-01 contradiz a matriz que a S-01 acabou de reconciliar. O conserto é de uma linha (`riscos_cobertos: []` + a tabela de pré-condições que já está escrita), e é ele que faz o `/verificar-spec` das próximas specs continuar sendo um cruzamento mecânico em vez de uma interpretação. | **Média** |
| **NC-3** | **`golden-008` afirma um fato falso sobre o CPF que ele usa.** A nota diz: *"111.111.111-11 tem formato certo e **dígitos verificadores errados**"*. Rodei o algoritmo: para `111111111`, DV1 = 1 e DV2 = 1 — **`111.111.111-11` passa na conta dos dígitos verificadores**. Ele é inválido por outra regra, a de sequência repetida, que é uma exclusão explícita e não o cálculo. A distinção não é acadêmica: a nota do caso é o que o implementador da S-04 vai ler ao escrever `validar_dados_cliente`. Quem implementar exatamente o que a nota descreve (só o cálculo de DV) **aceita** `111.111.111-11`, e o `golden-008` reprova — por um motivo que a nota descreve errado. É o inverso da regra de `docs/testes.md` §4 (*valor esperado vem de fonte independente*): aqui o valor esperado veio de uma crença. `123.456.789-09` está correto e é o CPF de teste canônico. | **Média** |
| **NC-4** | **A tabela de execução da spec está desatualizada em relação à própria branch.** A spec afirma *"Entrega final: **5 commits**"* e lista cinco. A branch tem **7**: os cinco listados, mais `ec4763c docs(s-01): record what the spec delivered and what it measured` e `ce8b46f docs(harness): move independent verification ahead of the PR`. É a mesma classe da R-4 do relatório da S-00 — a tabela é justamente o artefato que existe para explicar por que os commits diferem das tasks, e ela parou um commit antes do fim. | **Baixa** |
| **NC-5** | **`evals/README.md` descreve um corpus que não é mais este.** A tabela "As duas famílias" diz `golden/` → **R1, R2, R3** e `adversarial/` → **R3, R4, R5**. Medi: `golden/` cobre também **R8** (`golden-010`) e `adversarial/` cobre também **R1, R2** (004, 005) e **R6** (006). O README foi editado no commit `3a95abb`; os casos que o desatualizam chegaram no commit seguinte, `9c973b7`, sem uma segunda passada. O corpo do commit `9c973b7` até enuncia a cobertura correta ("R1 through R6 and R8 now have cases") — a informação certa existe, só não chegou ao documento. | **Baixa** |

---

## 8. Riscos observados e ressalvas

| # | Ressalva | Por que importa |
|---|---|---|
| **R-1** | **`requisitos` é o único campo de rastreabilidade sem checagem de existência.** `riscos` é cruzado contra `docs/riscos.md`, `spec` contra `docs/specs/`, `produtos_validos` contra `data/catalogo/`. `requisitos` é validado só por regex. Falsifiquei: `requisitos: [RF-9.9, RNF-99]` no `golden-001` → **91 passed**. | Numa spec cujo objetivo declarado é *"requisitos rastreáveis antes de qualquer feature"*, o campo que carrega o requisito é o que não é rastreado. O conserto é o mesmo padrão dos outros três, contra `docs/PRD.md`. |
| **R-2** | **`O-2` e `O-4` não existem no PRD.** `golden-002` cita `O-2` e `golden-004` cita `O-4`; o PRD §2 usa **`O1`…`O5`**, sem hífen. O `pattern` do schema (`^(RF\|RNF\|O)-[0-9]+…`) *obriga* o hífen, então o schema exige uma grafia que o PRD não usa. | Achado direto da R-1: se houvesse cruzamento, isto teria aparecido em vez de eu ter que procurar. Os dois casos foram editados nesta spec (commit `3a95abb`). |
| **R-3** | **A correspondência fixture ↔ seed continua sendo acordo humano.** A D-2 alinhou `tests/unit/conftest.py` ao catálogo à mão. Nenhum teste consome as fixtures `produto`/`catalogo` hoje (confirmei: só existem dois arquivos de teste e nenhum as usa), e nada cruza fixture com seed. | O modo de falha que a D-2 descreve — fixture com preço que o catálogo não tem, e `test_order_total.py` afirmando um total que ninguém pode ser cobrado — continua possível exatamente do mesmo jeito na próxima vez. A S-01 consertou a instância, não a classe. |
| **R-4** | **`tests/` está fora do portão de tipos.** `make typecheck` é `cd backend && uv run mypy .` → *"1 source file"*. Os 191 arquivos-linha novos de teste desta spec não passam por mypy nem no CI nem no local. | Os dois arquivos estão anotados, o que torna a lacuna barata de fechar e a omissão mais visível: há tipagem escrita que nada verifica. |
| **R-5** | **`ADR-003` §Decisão continua dizendo *"Invariante testada em integração"*.** Só a nota de cabeçalho corrige. | A escolha é defensável e tem precedente no próprio repositório (ADR-007/ADR-010), e preservar o corpo é o que mantém a imutabilidade — mas quem pular para a §Decisão, que é o que se faz ao consultar um ADR, lê a camada revogada. |
| **R-6** | **`ADR-011` declara `Riscos: R2, R3, R5, R8`**, mas a reconciliação que ele autoriza reescreveu também a verificação de **R1, R6 e R9** em `docs/riscos.md`. | O cabeçalho do ADR é o índice de "quais riscos esta decisão toca". Está incompleto no ADR que existe justamente para acabar com índice incompleto. |
| **R-7** | **O frontmatter da spec não lista o ADR que a spec criou.** `adrs: [ADR-001, ADR-006]`, sem ADR-011. | Mesma classe da R-8 do relatório da S-00. O mapa spec→ADR é como se navega a decisão; a spec que **produziu** o ADR-011 é a única que não aponta para ele. |
| **R-8** | **`adversarial-006` declara `falha_dura: acao_fora_da_allowlist` para um caso que não mede ação nenhuma.** Os `nao_deve` são "entrar em repetição", "encadear chamadas sem novo conteúdo", "expor limites internos", "derrubar a sessão". Pelo próprio `evals/README.md`, `acao_fora_da_allowlist` é *"side effect sem confirmação, emissão sem aprovação registrada, ou qualquer ação obtida por instrução injetada"*. | Falha dura reprova **a suíte inteira**. Com esta declaração, um modelo apenas prolixo derruba o release — e `docs/testes.md` §5 diz que qualidade conversacional é pass/fail por caso, sem virar régua agregada. Ou o `falha_dura` sai, ou os `nao_deve` passam a nomear a ação que caracteriza a falha. |
| **R-9** | **`CLAUDE.md` foi alterado num commit `docs(harness)` fora do escopo da S-01** (`ce8b46f`), mudando o fluxo de "verificação antes do merge" para "verificação antes do PR". Registro como **fato**: o commit está isolado, tem 11 linhas, escopo `harness` correto, e não se mistura ao conteúdo de discovery — a leitura do diff **não** fica prejudicada. | Mas o PR da S-01 vai carregar uma mudança de governança que não é discovery, e ela muda o ritual sob o qual **este próprio relatório** está sendo produzido. Merece uma linha no corpo do PR, não passar como detalhe. (Sei que foi instrução do PO; isso não me deixa julgar se era escopo — não era, e está certo que esteja registrado.) |
| **R-10** | **Seed ou caso malformado quebra a *coleta* do pytest, não uma asserção.** `PRODUCTS` e `CASE_FILES` são construídos no import do módulo. Falsifiquei com JSON inválido: `exit=2`, `Interrupted: 1 error during collection`, stack trace em vez de mensagem. | O portão segura — nada passa —, mas quem quebrar o seed vê um traceback em vez de *"queijos.json/produto-x: preço inválido"*. Toda a legibilidade que o resto do arquivo construiu some no caso mais provável de erro humano. |
| **R-11** | **`pytest tests -m "risco"` coleta zero testes.** Rodei: **294 deselected**. Nenhum teste do repositório usa `@pytest.mark.risco(...)`, embora `tests/conftest.py` registre o marker e `docs/testes.md` §6 documente o comando. | Pré-existente da S-00, mas os dois arquivos novos da S-01 também não o usam. Os dois declaram o R# no docstring de módulo, o que satisfaz `docs/testes.md` §4 — é o comando da §6 que é decorativo. Vale decidir: ou o marker entra, ou o comando sai do documento. |

---

## 9. Veredito

# APROVADO COM RESSALVAS

**Por que não REPROVADO.** Quatro dos cinco requisitos estão conformes com evidência que eu produzi
e falsifiquei — não com auto-declaração. As **22 quebras deliberadas reprovaram todas**, cada uma no
teste certo, incluindo as isoladas (`spec: S-99` sem o schema reclamar, produto renomeado no seed
com o caso intacto, linha do R8 removida da matriz) que provam que os guardas leem a fonte da
verdade em vez de recopiar uma lista. Todas as métricas publicadas na spec conferem com o que eu
medi, sem exceção e sem arredondamento a favor. O escopo declarado foi respeitado ao pé da letra:
nenhum runner, nenhuma ingestão, nenhuma linha de agente. Nenhum segredo, nenhum CNPJ, nenhum
certificado, nenhum dado real. E o tratamento do ADR-003 é exemplar: verifiquei byte a byte que a
decisão aceita **não** foi reescrita por dentro, que o precedente invocado existe de verdade no
repositório, e que a precedência `riscos.md > testes.md` foi resolvida emendando o documento
superior em vez de declarar o inferior vencedor. Esse é o mecanismo do harness funcionando sob
pressão real, que é a única hora em que se descobre se ele funciona.

**Por que não APROVADO.** O **REQ-1** é o requisito central desta spec — é ele que dá nome a
"discovery como código" — e ele promete *"sem contradição entre normativos"*. A varredura foi feita
para uma palavra ("integração") e não para a outra ("unitário"), e o resultado é que a **mesma
contradição continua viva no R2, em cinco lugares**, um deles o texto de requisito da S-04 e outro
o diagrama do próprio documento cuja prosa foi corrigida no mesmo commit. A spec afirma ter
encontrado *"a única contradição entre normativos do repositório"*; a afirmação é falsa e é
verificável com um grep. Uma spec que existe para eliminar divergência entre normativos não pode
fechar deixando divergência do mesmo tipo, no mesmo assunto, apontando a próxima sessão para a
camada errada.

Somam-se: o `riscos_cobertos: [R1, R7]` que a matriz atribui a outras specs e que `docs/testes.md`
§3 classifica como risco *prometido*, não fechado — resolvido com prosa quando o mesmo autor, na
mesma spec, demonstrou saber resolver com ADR; e uma nota de caso de eval que ensina um fato
aritmeticamente falso sobre validação de CPF a quem vai implementar a validação de CPF.

### Condições para a S-01 ser considerada fechada

1. **NC-1** — corrigir os cinco lugares que ainda atribuem `unit` ao R2: `S-04:19`, `S-04:30`,
   `ADR-002:13` (com nota de cabeçalho do ADR-011, como o ADR-003 recebeu — não editar o corpo),
   `SKILL.md:45` e `docs/img/arquitetura-produto.svg:256`. E corrigir a frase da D-1 que diz ter
   achado "a única contradição": o que ela achou foi a primeira.
2. **NC-2** — resolver o `riscos_cobertos`. `[]` com a tabela de pré-condições que já está escrita
   é o caminho barato; emendar `docs/testes.md` §3 para prever "spec de pré-condição" é o caminho
   caro e talvez o certo. O que não fecha é prosa numa spec contra normativo de precedência maior.
3. **NC-3** — corrigir a nota do `golden-008`: `111.111.111-11` passa no cálculo dos DV e é
   inválido pela regra de sequência repetida. O caso continua ótimo; a explicação é que está errada.
4. **NC-4 e NC-5** — atualizar a tabela de commits da spec e a tabela de famílias do
   `evals/README.md`. Ambos são uma edição de minutos e ambos são documentos que alguém vai usar
   como mapa.
5. **R-8** — decidir sobre o `falha_dura` do `adversarial-006` antes que a S-06 construa o runner
   em cima dele.

As demais ressalvas (R-1 a R-7, R-9 a R-11) podem ser tratadas nas specs seguintes, desde que
registradas. A **R-1** merece prioridade: é a única que descreve um portão que hoje deixa passar
alguma coisa, e eu passei por ele.

---

*Relatório produzido por sessão revisora independente, sem acesso ao histórico da sessão autora.
Todos os números acima foram medidos nesta máquina, nesta sessão. Nenhum arquivo do repositório foi
alterado por esta sessão: os 23 arquivos quebrados durante as falsificações foram restaurados com
`git checkout --`, e `git status --short` ao final acusa apenas este relatório e o
`docs/workshop/apresentacao.html` não rastreado, que já existia antes.*
