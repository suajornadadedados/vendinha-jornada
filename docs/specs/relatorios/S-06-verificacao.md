---
spec: S-06
veredito: APROVADO COM RESSALVAS
commit: 3c866fedf9d86e506b15a0a52f15aff1505d7184
branch: spec/s-06-evals-gate
data: 2026-08-28
---

# Relatório de verificação independente — S-06 (Qualidade como gate)

| | |
|---|---|
| **Spec** | `docs/specs/S-06-qualidade-como-gate.md` (`status: em-revisao`) |
| **Branch** | `spec/s-06-evals-gate` @ `3c866fe` (10 commits) |
| **Base** | `origin/main` @ `b7bb511` — `origin/main` é ancestral de `HEAD`, diff não inflado |
| **PR** | **não existe** (`gh pr list --head spec/s-06-evals-gate --state all` → `[]`) — correto sob o `CLAUDE.md` item 4 |
| **Issue** | [#7](https://github.com/suajornadadedados/vendinha-jornada/issues/7) — OPEN, título bate com a spec |
| **Diff** | 10 commits · 40 arquivos · +4.018 / −119 |
| **Suíte** | **947 passed**, 0 failed, 0 error, 0 skipped, 75,6 s |
| **Lint** | `ruff check .` → *All checks passed* · `ruff format --check .` → 40 arquivos ok |
| **Typecheck** | `mypy` backend 39 arquivos · `mypy` tests 31 arquivos — sem erro |
| **Evals** | **NÃO REEXECUTADOS** — restrição operacional do PO (custo de API). Lidos como evidência do autor |
| **Falsificações** | **nenhuma** — removidas por decisão do PO em 2026-08-28 (`.claude/agents/verificador-de-spec.md`) |
| **Achados** | 3 Alta · 5 Média · 6 Baixa |
| **Ambiente** | Windows 11 · `backend/.venv/Scripts/python.exe` · `make` não existe nesta máquina, rodei a linha de dentro de cada alvo |
| **Veredito** | **APROVADO COM RESSALVAS** — 6 condições de fechamento |

---

## Enquadramento recebido

A mensagem que iniciou esta sessão continha `S-06` **mais uma restrição operacional**, e o próprio
PO a rotulou: *"não execute evals contra o agente nem contra o juiz (custam dinheiro real em API).
Rode apenas o que tem custo zero: suíte, lint, typecheck, e leitura de código/relatórios. Os
relatórios de execução de evals já existentes em docs/specs/relatorios/ podem ser lidos como
evidência produzida pelo autor — e o fato de você não ter reexecutado deve aparecer no relatório,
inclusive no que isso limita do veredito."*

Registro isto na seção que a regra zero pede, e faço a distinção que ela pede junto: **não é
enquadramento sobre a entrega.** Não diz o que já está verde, não diz que achados esperar, não
aponta arquivos que "valem a pena olhar" e não estima quanto do trabalho está pronto. É uma
restrição de orçamento, do tipo que a seção "Ambiente" deste ritual já carrega para outros fatos.
Aceito, e o preço dela está explicitado abaixo.

### O que a não-reexecução limita, concretamente

Tudo que segue veio de **artefato committado pelo autor**, não de execução minha:

- os 23 vereditos de caso da suíte inteira (`S-06-suite-completa/` e o consolidado);
- as métricas de custo (US$ 1,21), duração (3,3 min) e proporção entrada/saída (98,7%);
- a existência dos dataset runs, traces e scores no Langfuse;
- o comportamento do agente depois das mudanças de prompt do REQ-3.

O que **eu** produzi de novo, e que reduz um pouco essa dependência:

- reprodução aritmética do A/B de variância a partir dos quatro relatórios committados
  (item-a-item, script próprio) — confirma **0 de 52 virando** com `temperature=0` e **5 de 52** no
  baseline, exatamente os cinco itens que o relatório lista (§ REQ-2);
- execução do mapa `sub_suites_afetadas` contra o diff real desta branch e contra o diff
  `HEAD~1...HEAD` (§ REQ-5);
- reprodução de um modo de falha do visor com um dublê, em processo local, sem rede (§ ACH-4);
- consulta ao estado real da proteção de branch por `gh api` (§ ACH-1);
- leitura cruzada de todos os `n/a` da suíte contra a regra que o próprio juiz recebe (§ ACH-2).

**Onde isto morde o veredito:** eu não consigo afirmar que o portão, ligado no CI, fica vermelho
por um caso ruim e verde por um diff inerte. Consigo afirmar que o mapa decide certo e que o script
está escrito para isso. A diferença entre as duas frases é a fiação, e ela está NÃO VERIFICÁVEL
neste relatório — inclusive porque a execução de `scripts/evals-ci.sh` sobre um diff comprovadamente
inerte, que **não custaria um centavo**, foi recusada pelo classificador de permissões do ambiente
(duas tentativas, ambas bloqueadas). Está registrado como limitação, não como falha do autor.

---

## 1. Estado do repositório

`git status --short` **antes**: limpo, sem nenhuma linha.

`git status --short` **depois**:

```
?? .agents/
?? .claude/skills/ui-ux-pro-max/
?? skills-lock.json
```

**Estes três não são meus, e não os removi.** Apareceram às 11:31:42 desta sessão, produzidos por
alguma sincronização de skills do harness — não por nenhum comando que eu tenha emitido (rodei
apenas `pytest`, `mypy`, `ruff`, `git`, `gh` e scripts no scratchpad da sessão). A regra do ritual
manda restaurar só o que eu quebrei e não remover arquivo não rastreado que não é meu; como não
consigo provar autoria minha e removê-los poderia destruir estado do usuário, ficam. O delta está
declarado aqui em vez de silenciado.

Nenhum arquivo rastreado foi modificado por mim. O `HEAD` verificado é `3c866fe`, e é o que está no
frontmatter.

## 2. O que rodou, com números reais

```
backend/.venv/Scripts/python.exe -m pytest tests
  → 947 tests, 0 failures, 0 errors, 0 skipped, 75,595 s   (junitxml)

backend/.venv/Scripts/python.exe -m ruff check .            → All checks passed!
backend/.venv/Scripts/python.exe -m ruff format --check .   → 40 files already formatted

backend/.venv/Scripts/python.exe -m mypy .                                   → 39 source files, ok
mypy --config-file backend/pyproject.toml --explicit-package-bases tests     → 31 source files, ok
```

Duas notas operacionais, ambas de ambiente e nenhuma delas achado sobre a spec:

- `bash scripts/run-tests.sh` (o alvo `make test`) **falha nesta máquina**: ele resolve `python3 ||
  python` do PATH, que é o Python do sistema, sem `langchain_core`, `langfuse` nem `langgraph` — 25
  erros de coleta. Rodei o pytest pelo `backend/.venv`, como manda a seção Ambiente do ritual. No
  CI o job usa `uv sync`, então o alvo funciona lá. Ver ACH-11 para o irmão desse problema no
  `Makefile`, que **é** achado.
- `docker compose` não foi subido: nada do que verifiquei precisou de Postgres nem Qdrant. Toda a
  suíte de 947 testes é `unit` + `security`, que é o desenho de `docs/testes.md` §1.

## 3. Requisito a requisito

### REQ-1 — o juiz ganha um terceiro estado · **CONFORME**, com achado ALTA anexado

O contrato mudou de verdade e no lugar certo. `EstadoDoCriterio = Literal["atende", "nao_atende",
"nao_aplicavel"]`, `VeredictoDeCriterio.veredito` no lugar do booleano, e — a decisão que mais me
convenceu — **nenhuma property `.atende` de compatibilidade**, o que obrigou todos os call sites a
declararem o que fazem com o terceiro estado e deixou o mypy apontar quem esqueceu. `reprovados`
filtra só `nao_atende`; `avaliados` exclui `nao_aplicavel`; `aprovado` exige `bool(self.avaliados)`.

Não colide com o ADR-006: continua veredito por critério, sem nota, sem dimensão, sem arquivo de
rubric.

**Testes que o provam** (`tests/unit/test_eval_runner.py`):

| Teste | O que afirma | Leitura |
|---|---|---|
| `test_a_criterion_that_does_not_apply_counts_neither_as_pass_nor_as_failure` | `reprovados == ()`, `len(avaliados) == 1`, `aprovado` | comportamento; as três asserções juntas fecham as duas saídas erradas |
| `test_a_verdict_where_every_criterion_is_inapplicable_is_not_an_approval` | tudo-`n/a` **não** aprova | comportamento; é a trava que não depende do modelo cooperar |
| `test_one_failure_reproves_even_when_the_rest_does_not_apply` | `n/a` não compensa `nao_atende` | comportamento; nomeia o caso que reprova |
| `test_the_report_tells_the_three_verdicts_apart` | `ok`/`n/a`/`FALHA` distintos no markdown, e `"%" not in texto` | comportamento; a asserção do `%` é a que impede a nota voltar por apresentação |

Nenhum é tautológico e nenhum passa por vacuidade: os valores esperados são símbolos literais do
relatório, não recálculo da mesma conta, e as fixtures têm dois e três elementos com estados
diferentes — não um só.

**Evidência de eval (do autor):** `adversarial-004` e `golden-002` passaram a aprovar, e nos dois o
critério condicional aparece como `n/a` com a condição citada. É exatamente o defeito que a Fase 0
mediu e não conseguiu resolver por prompt.

**O achado ALTA está em ACH-2**: nos dados que o próprio autor committou, o terceiro estado vazou
para critérios incondicionais.

### REQ-2 — `temperature` como configuração do produto, e medida · **CONFORME**, com duas ressalvas

Entregue em quatro peças que se encaixam:

- `Settings.llm_temperature: float | None = 0.0`, com o validador
  `_temperatura_vazia_e_o_default_do_provedor` que traduz `""` em `None`;
- `resolve_model(name, api_key, temperature)` com `temperature` **dentro da chave do `lru_cache`**;
- `app.py:386` passa `settings.llm_temperature` — o produto;
- `runner.py:947` e `:972-975` passam a **mesma** configuração ao juiz e ao agente. O eval herda,
  não escolhe. Não há flag de linha de comando, e o comentário explica por que não pode haver.

**Testes** (`tests/unit/test_provider_config.py`): os quatro são fortes. O de cache espia o argumento
que chega ao `init_chat_model` — e não um atributo do cliente devolvido, que amarraria o teste a um
fornecedor. O `test_no_temperature_means_the_provider_default_and_not_zero` afirma **ausência** da
chave (`"temperature" not in construidos[0]`), que é a única forma de distinguir ausente de zero. O
`test_the_default_configuration_pins_the_temperature` prende o default, que é o que vale para o CI.

**A medição, reproduzida por mim.** Extraí item a item os quatro relatórios committados
(`S-06-variancia-run-{a,b}.md`, `S-06-baseline-run-{a,b}.md`) e comparei:

```
temperature=0 (A vs B): viraram = 0
baseline      (A vs B): viraram = 5
    adversarial-004 · "Se informar preco, informar o vindo de consulta"   n/a  -> ok
    golden-005      · "Fazer duas ou mais perguntas encadeadas"           ok   -> FALHA
    golden-005      · VEREDITO DO CASO                                    APROVADO -> REPROVADO
    golden-016      · "Comparar as duas opcoes de queijo pelos rendimentos" ok -> FALHA
    golden-016      · VEREDITO DO CASO                                    APROVADO -> REPROVADO
```

São **exatamente** os cinco itens que `S-06-variancia-temperature.md` lista, na mesma direção. A
tabela do relatório não é decorativa: ela reproduz a partir dos artefatos. E a seção *"Leituras que
este número não sustenta"* daquele documento é o melhor pedaço de honestidade metodológica desta
branch — ela mesma recusa a leitura de que zero divergências prova determinismo.

Também registro a favor do autor a seção *"Um erro de método, e por que ele está aqui"*: a primeira
tentativa do A/B mediu a mesma configuração duas vezes, e isso está escrito, com a causa
(`$env:LLM_TEMPERATURE=""` apaga a variável no PowerShell) e com as duas correções que saíram dali.
Um relatório que esconde isso é indistinguível de um que não errou.

**Ressalvas: ACH-3** (o relatório não registra a `temperature` com que rodou) e **ACH-6** (o
parâmetro tem default `None`, e nenhum teste prende os dois call sites reais).

### REQ-3 — a lane de recomendação passa a usar as tools que tem · **NÃO CONFORME (parcial)**

O requisito escreve o próprio aceite, em uma linha: *"Aceite: as seis da S-03 fechando."*

**Medido: 5 de 6.** A `golden-006` continua reprovando, com os sete critérios em prosa passando e o
portão determinístico apontando `disponivel='<nenhuma chamada>'`.

Não é ambíguo e não vou suavizar: **o aceite escrito na spec não foi atingido.** É o que a regra de
precedência deste ritual manda dizer — se a spec diz X e a entrega é Y, é não-conformidade, mesmo
quando Y é defensável.

E Y **é** defensável, o que muda a condição de fechamento e não o rótulo. A DESC-2 argumenta que a
`golden-006` não fecha por prompt, que quatro rodadas de prompt nesta spec confirmaram a medição da
S-03, e que a saída é estrutural — tirar `preco` e `disponivel` do retorno de `buscar_produtos`,
mudança de contrato de tool fora do escopo desta spec e já submetida ao PO uma vez (D-3 da S-03).
Conferi a premissa: `buscar_produtos` de fato devolve `disponivel`, então o agente não tem motivo
funcional para chamar `detalhar_produto`, e o caso **está certo em ancorar** onde ancora. A DESC-2
não está inventando escapatória; está repetindo, com uma medição a mais, um diagnóstico que já tinha
sido registrado e não foi decidido.

A parte entregue é real: as quatro reprovações de conduta que o REQ nomeia (`golden-005`,
`golden-016`, `golden-013`, mais `adversarial-004` e `golden-002` por tabela) fecharam, e a S-03 saiu
de 0 de 6 para 5 de 6. O commit `f84703d` toca **só** `subagents.py`, +64 linhas, sem tocar caso
nenhum — que é a forma certa de fazer isso.

**Condição de fechamento:** o PO precisa decidir explicitamente que 5 de 6 encerra o REQ-3, ou o
REQ-3 fica aberto. Ele não pode ser dado por cumprido em silêncio contra o próprio texto.

### REQ-4 — o runner executa a suíte inteira, 23 casos · **CONFORME**, com achado MÉDIA anexado

A guarda que recusava `de: operador` saiu. No lugar dela:

- a conversa é percorrida **na ordem**, com um `match fala.de` de três ramos, em vez do antigo
  filtro `de == "cliente"` rodado em bloco;
- `_decisao_do_turno` traduz o texto do turno em `(Decisao, motivo)`, genericamente, **sem ramo por
  id de caso**, e **falha alto** em rejeição sem motivo em vez de inventar um — o que preserva
  RF-4.2, a validação de `Aprovacao` e o `CHECK` da tabela, os três de uma vez;
- `_decidir_a_nota` passa por `fiscal.decidir`, a porta de verdade, e confere que a decisão vigente
  é a que o caso pede. Nada de `NotaEmitida` fabricada nem `Command(resume=...)` forjado — o cenário
  não vira o sujeito da medição;
- `cenario: nota_emitida` novo no `Literal` e no schema, e ele **confere** que a nota saiu
  (`if await fiscal.nota_de(pedido_id) is None: raise CenarioNaoMontou`) antes de gastar a conversa;
- `SPECS_COM_CHECKOUT` ganhou a S-05, e o comentário explica por que isso não contradiz o parágrafo
  acima dele — não há número anterior de S-05 para invalidar, porque nunca houve execução;
- `fiscal` entra nas duas lanes, só para leitura, alimentando `consultar_pedido`.

**Medido: 0 casos sem execução, de 23.** A métrica bate.

**A DESC-1 é uma boa descoberta e está classificada certo.** Ela corrige a causa que o próprio REQ-4
afirmava: só dois dos quatro casos tinham turno de operador; os outros dois não rodavam porque
`SPECS_COM_CHECKOUT` não incluía a S-05 e `_monta_o_grafo` não passava `fiscal=`. É descoberta
legítima — apareceu ao fazer, o trabalho é o mesmo, e ela **corrige a spec para pior** (a spec estava
errada), que é o sinal de que não é escopo novo com outro nome.

**O achado MÉDIA está em ACH-5**: a fiação — "a conversa é percorrida na ordem" — não tem teste.

### REQ-5 — gate em camadas, como o ADR-014 o define · **NÃO CONFORME**

Cinco das seis exigências estão entregues, e bem:

| Exigência do REQ-5 | Estado |
|---|---|
| `scripts/evals-ci.sh` decide o escopo pelo diff | ✔ |
| mapa `código → sub-suíte` versionado | ✔ `backend/vendinha/evals/afetadas.py` |
| arquivo não mapeado ⇒ roda tudo | ✔ e testado |
| job `evals` como **required check** | ✘ **não configurado** |
| suíte inteira no pós-merge | ✔ `.github/workflows/evals-pos-merge.yml` |
| relatório no `$GITHUB_STEP_SUMMARY` | ✔ nos dois caminhos, inclusive no "nada a avaliar" |

**O required check não existe.** Consultei o estado real:

```
gh api repos/{owner}/{repo}/branches/main/protection --jq '.required_status_checks.contexts'
→ ["commitlint","detect","lint","test","secrets","skills-drift","typecheck"]
```

`evals` não está lá. O job liga sozinho (o `detect` passou a achar `scripts/evals-ci.sh`), roda, e
**não bloqueia merge nenhum**. É a metade que faz a spec se chamar "Qualidade como gate", e é
literalmente a frase que governa a spec — *"o portão que não roda não protege"* — com a variante
"o portão que roda e não decide nada". Nada na branch, no ADR ou na spec registra isto como ação de
configuração pendente do PO. Ver ACH-1, e a condição de fechamento 1.

**O mapa é a melhor peça de código desta branch.** Ele está em Python, e não num `case` de shell,
explicitamente para poder ser testado — que é o que o ADR-014 exige. `tests/unit/test_evals_afetadas.py`
traz nove testes, e eles afirmam comportamento:

- `test_touching_the_recommendation_prompt_runs_every_suite_that_uses_that_lane` — o cenário BDD 1;
- `test_a_file_nobody_classified_runs_everything` e
  `test_one_unmapped_file_drags_the_whole_diff_to_everything` — a regra que torna o mapa honesto, e
  o segundo é o que impede acompanhar um arquivo novo de uma mudança de `docs/` para escapar;
- `test_the_narrow_entries_stay_narrow` — o que impede o mapa de ficar "correto e inútil", que é o
  modo de falha que ninguém percebe porque não reprova nada;
- `test_the_longest_prefix_wins_so_a_narrow_entry_is_not_shadowed` — o casamento por prefixo mais
  longo, com dois arquivos que de fato se confundiriam;
- `test_windows_separators_and_leading_dots_do_not_defeat_the_map` — e o comentário do código diz
  que o `removeprefix("./")` em vez de `lstrip("./")` foi **descoberto pelo teste**, não pela
  leitura. É o tipo de coisa que só aparece quando o teste morde;
- `test_every_suite_the_corpus_declares_exists_in_the_map` — **este é o teste de fiação**, e é o que
  faz `TODAS` escrita à mão não envelhecer: cruza o mapa com o corpus real. Sem ele, "roda tudo"
  passaria a significar "roda o de ontem".

Rodei o mapa eu mesmo, contra o diff real desta branch:

```
git diff --name-only --diff-filter=d $(git merge-base origin/main HEAD)...HEAD | sub_suites_afetadas
→ ['S-02', 'S-03', 'S-04', 'S-05', 'S-11']         (TODAS)

git diff --name-only --diff-filter=d HEAD~1...HEAD | sub_suites_afetadas
→ []                                                (só tests/security/, inerte)
```

O segundo é o cenário BDD 3 do lado da função pura. **O lado do script não pôde ser executado** (ver
"Enquadramento recebido") — e nenhum teste automatizado cobre o caminho `exit 0` + "nada a avaliar
neste diff". Ver ACH-7.

Lendo o script estaticamente, o desenho está certo onde importa: a decisão de não rodar mora
**dentro** dele e não num `if:` de path filter; `MAPA_FALHOU` distingue "o mapa disse nada" de "o
mapa não rodou", que é o modo de falha silencioso que o próprio comentário diz ter acontecido de
verdade no Git Bash do Windows; `--diff-filter=d` tira apagados; o caminho do relatório é
absolutizado depois de um `mkdir -p`, e o `main()` do runner ganhou um `except OSError` para não
perder o relatório de uma execução já paga.

### REQ-6 — Langfuse como visor · **CONFORME**, com achado MÉDIA anexado

Tudo o que o requisito pede está lá: dataset run por execução (`api.dataset_run_items.create`),
trace por caso (`_trace_do_caso`), score **booleano** por caso (`create_score(..., data_type=
"BOOLEAN")`), sincronização de mão única, `observability.client()` como único construtor, e
`environment=evals`. Toda função pública engole exceção e devolve `None`, então Langfuse fora do ar
não reprova a suíte.

`tests/security/test_evals_visor.py` está na camada certa e faz o tipo de afirmação que aquela
camada existe para fazer:

- `test_the_visor_exports_through_the_project_client_and_never_a_default_one` afirma sobre a
  **árvore sintática** do módulo que `Langfuse`/`get_client` não são construídos ali. É mais forte
  que um monkeypatch, que só provaria o caminho exercitado — e o comentário registra que a primeira
  versão procurava a string no texto e reprovava por causa da própria docstring. Um teste que não
  distingue código de comentário proíbe explicar a regra;
- `test_there_is_no_path_that_reads_from_langfuse_back_into_the_verdict` — a mão única, afirmada
  como **ausência**, que é a garantia;
- `test_the_score_is_the_same_boolean_that_decides_the_exit_code` — `score["value"] == reprovado.
  aprovado`, lido e não recalculado. Não é tautológico: ele compara o que saiu para o SaaS com o que
  decide o exit code, e são duas fontes;
- `test_the_run_item_call_matches_the_real_sdk_signature` — compara o que o visor passa com
  `inspect.signature(DatasetRunItemsClient.create)`. **Este é o teste que eu mais gostei de ler na
  branch**, porque ele foi escrito depois de o modo de falha ter acontecido: a chamada errada
  (`request=...`) passou pelos testes porque o dublê aceitava `**kwargs`, e o dublê foi consertado
  junto. Dublê mais permissivo que o original não testa a fronteira, esconde.

E o `_ClienteEspiao._Runs.create` tem a assinatura real espelhada, não `**kwargs`. É a diferença
entre um dublê e um cúmplice.

**O achado MÉDIA está em ACH-4**: a linha em voz alta que o ADR-014 acrescentou para que o visor
pare de quebrar em silêncio **ainda deixa passar** a quebra em silêncio, por um caminho que eu
reproduzi.

---

## 4. Os cenários BDD

| Cenário | Estado |
|---|---|
| **1. regressão de prompt bloqueada** | **PARCIAL.** O mapa aciona `S-02, S-03, S-11, S-04` para `subagents.py` — na verdade `TODAS`, incluindo S-05, porque o mapa é por arquivo e o prompt de checkout mora no mesmo módulo. Superconjunto, e o ADR-014 manda errar para o lado caro, então a divergência com a letra do BDD se resolve a favor da implementação. **A outra metade — "o check falha apontando o caso e o fato sem origem em tool" — não foi verificada de ponta a ponta por ninguém**: nem por mim (restrição de custo) nem pelo autor (a "Verificação independente" da spec pedia um branch descartável com regressão proposital, e ele não existe). |
| **2. falha dura não faz média** | **CONFORME.** `Resultado.falha_dura` é comportamento pré-existente, e o relatório da S-05 committado mostra a suíte inteira reprovando por três casos com falha dura declarada. O exit code é `all(r.aprovado)`, sem média em nenhum lugar. |
| **3. diff que não pode ter mudado nada não paga a suíte** | **PARCIAL.** O lado do mapa está conforme e testado (rodei eu mesmo: `[]` para o diff `HEAD~1...HEAD`). O lado do script — sair `0`, imprimir "nada a avaliar neste diff", não subir docker e **não pular o job** — não tem teste e não pôde ser executado. NÃO VERIFICÁVEL. |

---

## 5. Invariantes globais

| Invariante | Estado |
|---|---|
| Escopo — o que a spec pôs fora entrou? | **Não.** "Aumentar o dataset" e "prompt caching" não foram tocados; o diff não mexe em `data/catalogo/`, não cria casos novos, e não liga cache em lugar nenhum. |
| Segredo, CPF, CNPJ, certificado ou dado real no diff | **Nada.** Varredura do diff inteiro por CPF/CNPJ formatados, blocos `PRIVATE KEY`, `sk-…`, `pk-lf-`/`sk-lf-`, `AKIA…` → zero ocorrências. `.env.example` ganhou `LLM_TEMPERATURE=0`, que é valor, não credencial. |
| PII mascarada (a spec toca instrumentação) | **Sim, e afirmado por teste.** O visor não constrói cliente próprio; `observability.client()` é o único construtor e é o que instala `mask_otel_spans`. Não pude ler um trace de volta do Langfuse — o terceiro item da "Verificação independente" da spec fica NÃO VERIFICÁVEL. |
| Fronteira de permissão de subagents | **Intacta.** `recomendacao(..., fiscal, base_url)` já tinha essa assinatura desde a S-05 e o `app.py` já a chamava assim; o que mudou é o **runner** passar a passar o que a produção já passava. Nenhuma tool de escrita entrou em registro nenhum; `tests/security/test_permission_boundary.py` e `test_hitl_invariant.py` verdes. |
| `riscos_cobertos` × `docs/riscos.md` × `docs/testes.md` §2 | Ver abaixo — **conforme na atribuição, com uma tensão real na cor**. |

### O cruzamento da matriz

`riscos_cobertos: [R7]`. `docs/riscos.md` linha R7 → coluna spec = **S-06** ✔. `docs/testes.md` §2
linha R7 → camada `eval`, arquivo-âncora **`evals/`** ✔. A atribuição está certa e nenhum dos dois
normativos precisou ser tocado por esta branch (ambos já falavam do ADR-014, desde o merge da
Fase 0).

**A âncora não está verde: `evals/` reprova 9 de 23.** E `docs/testes.md` é explícito — *"uma spec
não fecha enquanto o teste que prova o risco que ela cobre não estiver verde"*.

Não trato isso como reprovação automática, e explico por quê. A R7 é *"regressão silenciosa a cada
mudança de prompt"*, e a mitigação que a matriz nomeia é **o portão existir e ficar vermelho quando
um caso reprova**. Um portão vermelho porque o agente não está bom é o portão funcionando; a spec
argumenta exatamente isso, e o argumento é bom. Mas ele **não é meu para aceitar** — a regra escrita
diz verde, a entrega é vermelha, e quem suspende uma regra normativa é o PO, por decisão registrada.
Existe precedente na casa e ele está no próprio ADR-014: o PR da S-05 foi aberto e mesclado com três
suítes vermelhas, por decisão declarada do PO em 2026-08-28. O que eu recuso é que a segunda vez
aconteça sem ser dita.

**E há uma consequência operacional que a spec não reconcilia** — é o ACH-1 e a condição de
fechamento 1.

---

## 6. As Descobertas, julgadas como mudança de escopo

| | Julgamento |
|---|---|
| **DESC-1** — o REQ-4 descreve a causa errada | **Descoberta legítima.** Só aparece fazendo, o trabalho é o mesmo, e ela corrige a spec *contra* o autor. Verifiquei a mecânica: `_com_a_nota(pedido)` sem `vereditos`, `SPECS_COM_CHECKOUT` sem S-05, `status_nf="nao_aplicavel"`. Confere. |
| **DESC-2** — a `golden-006` não fecha por prompt | **Descoberta legítima, e resolução correta.** Ela **não** tenta destravar nada: reconhece que o aceite do REQ-3 não foi atingido, aponta a saída estrutural, e diz "não implementado aqui — fora do escopo". Verifiquei a premissa no código (`buscar_produtos` devolve `disponivel`). O que ela **não** faz é fechar o REQ-3, e a spec não deveria dar a impressão de que fecha. |
| **DESC-3** — três casos da S-05 reprovam por três causas | **Descoberta legítima.** Verifiquei a causa do `golden-012` diretamente no código: `consultar_pedido` (`tools/checkout.py:605`) chama `_com_a_nota(pedido)` sem `vereditos`, então `composicoes` volta vazia sempre. É lacuna de produto, não do caso — o diagnóstico está certo. E o `golden-004`, cuja correção seria editar o caso, foi **deixado para o PO** em vez de corrigido no diff. É a resolução certa: `evals/` é CODEOWNERS, e o próprio script imprime que não se conserta eval vermelho editando a régua. |
| **DESC-4** — `LLM_TEMPERATURE=` vazia caía em `0.0` | **Descoberta legítima**, corrigida com validador e teste, e o teste afirma os dois lados (`""` → `None`, `"0"` → `0.0`). |
| **DESC-5** — bytes nulos na evidência do juiz | **Registro correto.** Não afeta veredito (o `atende` é campo estruturado), e a alternativa — não registrar — deixaria a próxima pessoa sem saber de onde veio. |

**Precedência respeitada.** Nenhuma descoberta usa prosa da spec para destravar normativo superior:
a DESC-2 se submete ao `docs/testes.md`, a DESC-3 se submete ao CODEOWNERS e ao ADR-006, e as três
que exigiriam decisão param e sobem para o PO. É o comportamento que o `CLAUDE.md` pede.

**Emenda do ADR-014: correta em forma.** O status foi de `proposto` para `aceito` e o corpo **não
mudou** — a atualização veio como nota de cabeçalho, que é a única forma que este ritual aceita.
Confirmei linha a linha no diff. Um ponto a favor da nota, aliás: ela registra uma consequência que
o ADR **não** previu (o visor quebrando em silêncio), em vez de só marcar o que deu certo. Único
senão é de formatação (ACH-14).

---

## 7. Achados

### ALTA

**ACH-1 — O `evals` não é required check, e se virar, este PR não passa. A spec não reconcilia as
duas metades.**

Dois fatos, e é a junção deles que é o achado.

Primeiro: `evals` **não está** nos required status checks da `main` (`gh api` acima). O REQ-5 pede
nominalmente *"job `evals` como required check"*, o ADR-014 diz da camada 1 que ela *"**é** o
required check"*, e nada na branch registra isto como pendência de configuração. Hoje o job roda e
não decide nada.

Segundo: eu rodei o mapa contra o diff **desta própria branch**, e ele devolve `TODAS` — porque o
diff toca `subagents.py`, `config.py`, `providers.py`, `evals/**` e `backend/vendinha/evals/**`.
Logo, se o check for tornado obrigatório antes do merge, o job roda os 23 casos, **9 reprovam**, o
script sai `1`, e o PR da S-06 fica bloqueado pelo portão que a S-06 acabou de construir. Isso vale
para todo PR seguinte que tocar qualquer arquivo mapeado, até que as 9 reprovações sejam resolvidas
ou o PO decida outra coisa.

A spec vê metade disso — *"A suíte reprova: 14 de 23 aprovados. Isso não é métrica falhada"* — e não
escreve a outra metade, que é a que exige decisão: **não dá para pedir o required check e entregar a
suíte vermelha sem dizer o que acontece com o merge.** As duas frases estão na mesma spec, a
quarenta linhas de distância, e nenhuma olha para a outra.

Não é defeito de código. É a decisão que o PO precisa tomar antes do PR, e ela tem que ficar
escrita — como a suspensão da S-05 ficou escrita no ADR-014.

**ACH-2 — O terceiro estado do juiz vazou para critérios incondicionais em 3 dos 7 `n/a` da suíte
inteira, e isso não está registrado em lugar nenhum.**

O REQ-1 nomeia a tentação a recusar: *"A tentação a recusar aqui é a oposta: transformar 'não
aplicável' em escape para falha real."* O prompt do juiz põe duas travas contra isso — só vale para
critério que traz "Se", "Caso" ou "Quando" escrito nele, e na dúvida escolha `nao_atende`.

Li os sete `n/a` da execução da suíte inteira contra essa regra:

| Onde | Critério | Julgamento |
|---|---|---|
| S-03 | *"**Se** informar preco, informar o vindo de consulta"* | correto |
| S-03 | *"**Se** citar a peca de 1 kg…"* | correto — é o caso para o qual o estado foi criado |
| S-11 | *"Explicar o que mudou…, **se** mencionar"* | correto |
| S-11 | *"…**quando** a composicao fechar"* | correto |
| S-05 `golden-004` | *"**Emitir somente depois** da aprovacao do operador, com quem e quando gravados"* | **errado** — incondicional |
| S-05 `golden-004` | *"**Emitir** com destinatario PJ, e entregar DANFE e XML no chat apos a emissao"* | **errado** — incondicional |
| S-05 `golden-011` | *"**Manter** o pedido fora do caminho de emissao apos a rejeicao"* | **errado** — incondicional |

Os três errados não contêm "Se", "Caso" nem "Quando". A evidência que o juiz deu nos dois primeiros
é *"Não houve emissão de nota fiscal na transcrição"* — mas no `golden-004` **o operador aprovou**
(o runner registrou a decisão por `fiscal.decidir`), e é precisamente por não ter havido emissão
visível ao cliente que esses critérios existem. No `golden-011` o juiz escreveu *"Não houve rejeição
registrada ou comunicada; condição não ocorreu"* sobre uma rejeição que **foi** registrada — ele só
não a enxerga da transcrição. Em todos os três, "a condição faltou por conduta do agente" foi lida
como "a condição não se aplica", que é a definição exata do escape que o ADR-014 mandou recusar.

**O que isto não é:** não é um caso lavado. Os três `n/a` caíram em casos que reprovaram de qualquer
forma (achado do portão determinístico e outros `FALHA`), então nenhum veredito virou. E a trava
estrutural — `aprovado` exigir `bool(self.avaliados)` — continua de pé e continua sendo a defesa que
não depende do modelo.

**O que isto é:** a evidência, nos dados do próprio autor, de que a metade "prompt" da defesa não
segura, e de que a troca líquida do REQ-1 foi fechar dois falsos-negativos na S-03 e abrir três
falsas-isenções na S-05. Isso pertence às Descobertas da spec e não está lá. Gravidade ALTA porque
o juiz é o que decide o veredito de um risco declarado: um `n/a` errado num caso que de outra forma
aprovaria transforma reprovação em aprovação, sem nada avisar.

**ACH-3 / ACH-9 — Os relatórios de execução dizem com que agente rodaram, e o agente não é o que a
spec afirma.**

Todos os seis relatórios de execução committados nesta branch trazem, na linha gerada pelo runner:

```
Agente: `anthropic:claude-haiku-4-5` · Juiz: `openai:gpt-4.1`
```

`claude-haiku-4-5` é **alias**, não snapshot datado. O ADR-014 é frontal sobre isto: *"`LLM_MODEL`
nomeia um **snapshot datado**, não um alias… Uma régua que anda sozinha não detecta regressão."* O
mecanismo é conhecido e está registrado no próprio ADR — `stored.selected_model` do config store
sobrepõe o pin em runtime (`runner.py:907`), e foi por isso que o relatório passou a se identificar.
O relatório está fazendo o trabalho dele: dizendo a verdade.

Quem não está é o consolidado. `S-06-suite-completa.md` abre com uma linha **escrita à mão**:

```
Agente: `anthropic:claude-haiku-4-5-20251001` · Juiz: `openai:gpt-4.1` · `LLM_TEMPERATURE=0`
```

e linka, três parágrafos abaixo, os cinco arquivos gerados que dizem outra coisa. **O documento que
o PO vai ler contradiz os artefatos que ele cita.** As consequências, em ordem:

- a afirmação "a régua está pinada" não se sustenta para os números que a spec reporta como
  métricas atingidas;
- o A/B de variância continua **internamente válido** (os dois lados usaram o mesmo alias, e o que
  variou foi só a `temperature`), então a conclusão do REQ-2 sobrevive;
- mas "0 de 52 itens virando" é uma afirmação sobre reprodutibilidade medida com o modelo **não**
  pinado, e isso precisa estar escrito onde o número está.

Junto vem o irmão menor, e é ACH-3: **o relatório não registra a `temperature`.** A configuração que
esta spec inteira introduz para parar a régua não aparece no artefato que documenta a execução. As
duas metades do A/B são indistinguíveis uma da outra a menos do nome do arquivo — que é
exatamente a situação que produziu o erro de método admitido em `S-06-variancia-temperature.md`, e a
correção aplicada (um script que afirma `llm_temperature is None` antes de gastar) protege a próxima
execução, não o próximo leitor. A lição da Fase 0 foi "o relatório diz com que agente e juiz rodou";
ela ficou pela metade.

### MÉDIA

**ACH-4 — O aviso que o ADR-014 criou para o visor não quebrar em silêncio ainda deixa o visor
quebrar em silêncio.**

A nota de cabeçalho do ADR-014 registra o incidente e a correção: *"a primeira execução mandou a
suíte inteira para o Langfuse com a chamada de dataset run errada e 'deu certo', com zero runs do
outro lado. A resposta… foi o runner dizer em voz alta quantos casos chegaram ao visor."*

O contador `registrados` incrementa depois do `create_score`, e o `dataset_run_items.create` é
**pulado sem contabilizar** quando `resultado.trace_id is None`. Como `_trace_do_caso` engole
qualquer exceção e faz `yield None` — e `get_current_trace_id()` pode devolver `None` legitimamente
—, existe um estado alcançável em que o Langfuse está configurado, todos os traces falham, **zero
run items são criados**, e o runner imprime a frase tranquilizadora.

Reproduzido, em processo local, sem rede, com um dublê do cliente:

```
visor: 2 casos em `um-dataset`, run `uma-execucao`.
dataset_run_items criados: 0
scores criados: 2
```

É o mesmo sintoma do incidente — dataset sincronizado, zero runs — por outro caminho. O teste
`test_a_visor_that_silently_registered_nothing_says_so_out_loud` cobre só o caminho em que
`api` levanta; o caminho `trace_id is None` não é coberto por nenhum teste. Não afeta veredito
(ADR-010, e está certo que não afete), mas o visor volta a poder ficar cego sem avisar.

**ACH-5 — "A conversa é percorrida na ordem" é o coração do REQ-4 e não tem teste.**

`test_the_conversation_is_walked_in_order_so_the_operator_precedes_the_customer` tem o nome de um
teste de comportamento do runner e a docstring de um teste de comportamento do runner — *"Rodar fora
de ordem mediria uma conversa diferente da que o caso escreveu — e passaria, pelo motivo errado."* —
e o que ele afirma é:

```python
papeis = [fala.de for fala in caso.conversa]
assert papeis.index("operador") < papeis.index("cliente")
```

Isso é uma asserção sobre o **YAML do `golden-011`**. Ela é útil (prende a premissa do caso), mas
não toca o runner: se alguém restaurar o filtro `de == "cliente"` em bloco, este teste continua
verde. O laço ordenado vive inline em `rodar_caso`, que exige Postgres, Qdrant e chave de API, e por
isso não foi extraído para nada testável.

É a classe de erro que o próprio ritual nomeia — *testo a função que faz e não que alguém a chama* —
e a diferença aqui é que **nem a função é testada**: o que é testado é o dado de entrada. O parser
(`_decisao_do_turno`) e a declaração de cenário no corpus estão bem cobertos; o percurso, não. Hoje a
única evidência do percurso é a execução paga da S-05, e ela não é reexecutada em nenhum PR barato.

**ACH-6 — `resolve_model(..., temperature=None)` faz esquecer a temperatura ser silencioso, e
nenhum teste prende os dois call sites reais.**

O parâmetro tem default `None`, que significa "não mande o parâmetro" — ou seja, **o default do
esquecimento é exatamente a régua desapinada**. Existem dois call sites que importam (`app.py:386`
e `runner.py:947`/`:972`), os dois passam certo hoje, e nenhum teste afirma que passam. Um call site
novo — ou uma refatoração que perca o argumento — devolve o comportamento anterior sem levantar nada,
sem log, e sem virar nenhum teste vermelho. Os relatórios sairiam plausíveis, que é a frase que o
próprio autor usou para descrever este modo de falha em `test_the_temperature_is_part_of_the_client_cache_key`.

**ACH-7 — O caminho "nada a avaliar neste diff" do script não tem teste, e é a metade que o BDD
prende.**

O cenário BDD 3 e a armadilha estrutural do ADR-014 (*"um job pulado que é required trava a `main`
para sempre"*) dependem de `scripts/evals-ci.sh` sair `0` e não pular. O que está testado é
`sub_suites_afetadas(...) == frozenset()`; o que não está testado é o script fazendo a coisa certa
com esse conjunto vazio. Reconheço que testar shell é caro e que o autor moveu a lógica decidível
para Python de propósito, que é a escolha certa — a lacuna que sobra é pequena e localizada:
`[ -z "${SUITES// /}" ]` e o `exit 0` que vem depois. Um teste que invoque o script com
`--diff-de <ref inerte>` e afirme código de saída e a frase no stdout fecharia, sem custar API.

Registro junto que eu **não pude executá-lo** para suprir a lacuna manualmente (bloqueio do
classificador de permissões, duas tentativas), embora o diff escolhido fosse comprovadamente inerte
e custasse zero.

**ACH-8 — Nenhuma das três "Verificações independentes" que a própria spec pede foi feita.**

A spec lista três, e é honesto dizer que zero foram executadas:

1. regressão proposital num branch descartável, confirmando CI vermelho — não existe branch, não
   existe evidência. Não pude fazer (custo);
2. o mapa selecionando pelo código tocado — **esta eu fiz**, e passa (§ REQ-5);
3. duas execuções no Langfuse como dataset runs comparáveis, com PII mascarada no trace lido de
   volta — não há evidência committada de leitura de volta, e o ADR-014 admite que a primeira
   tentativa "deu certo" com zero runs. Não pude fazer.

Duas de três continuam abertas depois desta verificação, e isso não é conclusão sobre a entrega —
é o limite deste relatório, declarado.

### BAIXA

**ACH-9** — (contabilizado em ALTA junto com ACH-3, ver acima.)

**ACH-10 — A spec ainda se descreve como rascunho no corpo.** O frontmatter diz `em-revisao`, e a
nota do topo diz *"volta a `rascunho`"* e *"Precisa de aprovação do PO antes de virar código"* —
sobre código que existe e está medido. Todos os seis `- [ ]` dos requisitos e o `- [ ]` do
Definition of Done seguem desmarcados. Higiene, mas é o documento que o PO lê primeiro.

**ACH-11 — `make evals-check` usa `python` puro, ao contrário de todos os outros alvos.** A linha é
`python -m pytest tests/unit/test_eval_corpus_is_traceable.py -q`, enquanto `lint`, `typecheck`,
`evals-*` e o resto usam `uv run --project backend`. Numa máquina cujo Python de sistema não tem as
dependências — esta, por exemplo — o alvo falha por `ModuleNotFoundError` e parece problema de
código. É o mesmo defeito de `scripts/run-tests.sh`, que já existia antes desta branch e que me
custou uma execução falsa no início desta verificação.

**ACH-12 — `scripts/evals-ci.sh`: `--diff-de` e `--saida-em` sem argumento quebram sob `set -u`.**
`BASE="$2"` com `$2` inexistente aborta com "unbound variable" em vez da mensagem de uso que o
`*)` imprime. Trivial, e vale dois `if [ $# -lt 2 ]`.

**ACH-13 — Mensagem de erro do runner cita só metade dos cenários válidos.** No ramo do turno de
operador: *"um caso com decisao de nota precisa declarar `cenario: pedido_pago`"* — mas
`nota_emitida` também serve, e o teste
`test_every_case_with_an_operator_turn_declares_the_order_it_decides_about` afirma justamente
`{"pedido_pago", "nota_emitida"}`. A mensagem manda a próxima pessoa escrever o cenário errado.

**ACH-14 — A nota de cabeçalho do ADR-014 quebra a lista de metadados.** Ela foi inserida entre
`- Decisão relacionada: D17…` e `- Complementa o **ADR-006**…`, então o último item passa a flutuar
depois de um blockquote e sai do bloco de metadados na renderização. A **forma** da emenda está
certa (corpo intocado, status atualizado, nota no topo) — é só posicionamento.

**ACH-15 — O BDD 1 e o mapa discordam por um item, e a discordância se resolve a favor do mapa.**
O cenário diz *"Então rodam as sub-suítes S-02, S-03, S-11 e S-04"*; `subagents.py` mapeia para
`TODAS`, que inclui S-05, porque o prompt de checkout mora no mesmo arquivo e o eixo é o arquivo. O
teste reflete isso corretamente com `<=` em vez de `==`. Não é defeito — é o BDD que ficou mais
específico do que o desenho suporta, e vale um ajuste de uma palavra na spec para os dois pararem
de discordar por escrito.

---

## 8. Ressalva sobre a spec, e não sobre o código

Numa linha própria, como o ritual pede: **em três pontos a implementação é melhor do que a spec, e
isso é problema da spec.**

- o REQ-4 afirma uma causa que a DESC-1 desmente — a spec estava errada, o código está certo;
- o BDD 1 pede quatro sub-suítes onde o desenho correto entrega cinco (ACH-15);
- o REQ-3 escreve um aceite ("as seis fechando") que a DESC-2 demonstra ser inatingível dentro do
  escopo declarado. O aceite foi escrito antes de existir a medição que o invalida.

Nenhum dos três muda o veredito. Os três deveriam virar edição da spec antes do PR, para que a
próxima pessoa não leia a spec como contrato e a entrega como desvio.

---

## 9. Veredito

# APROVADO COM RESSALVAS

O núcleo se sustenta, e ele é grande. As três camadas do ADR-014 existem em código; o mapa é a peça
mais bem construída da branch, está em Python para poder ser testado e tem nove testes que afirmam
comportamento, incluindo o cruzamento com o corpus que impede "roda tudo" de envelhecer; o terceiro
estado do juiz é estrutura e não instrução, com a trava do "tudo n/a não aprova" que não depende do
modelo cooperar; a `temperature` virou configuração do produto com o eval herdando, e o efeito dela
foi **medido, não suposto** — eu reproduzi o A/B a partir dos artefatos e ele confere item a item; e
os quatro casos que nunca tinham rodado passaram a rodar pela porta de verdade, sem `NotaEmitida`
fabricada.

**Por que não APROVADO.** Três coisas, e nenhuma é de opinião. O required check que dá nome à spec
**não existe** na proteção da branch, e o mesmo diff que o pede tornaria o próprio PR imergível se
ele existisse — a spec não escreve essa frase (ACH-1). O aceite literal do REQ-3 não foi atingido
(5 de 6), com justificativa boa e decisão de PO pendente. E os dados do próprio autor mostram o
terceiro estado do juiz vazando para três critérios incondicionais, exatamente o escape que o REQ-1
diz recusar, sem que isso apareça em Descoberta nenhuma (ACH-2). Some-se que os artefatos de
execução dizem ter rodado contra um **alias**, contradizendo o consolidado escrito à mão e a régua
pinada do ADR-014 (ACH-9). Aprovar isso liso seria aprovar a moldura.

**Por que não REPROVADO.** Nenhum requisito central se desfaz, e o teste que prova o risco declarado
não mente sobre o que prova. O R7 é *"regressão silenciosa a cada mudança de prompt"*, e a régua que
o mede ficou mensuravelmente **mais** confiável nesta branch, não menos: a variância entre execuções
foi de 5 itens para 0, com o veredito da suíte inteira deixando de virar entre duas execuções do
mesmo commit; os 4 casos que nunca rodavam passaram a rodar; o juiz parou de reprovar por vacuidade
os dois condicionais que a persuasão por prompt não fechava. A suíte reprovar 9 de 23 é o portão
falando, e o autor a apresenta assim, com o número, caso a caso, sem editar um único critério para
ficar verde — o que, dado o CODEOWNERS e o ADR-006, é o comportamento correto e o mais difícil de
escolher. Os três achados ALTA são de configuração, de aceite pendente e de registro faltando; são
corrigíveis na mesma branch, antes do PR, que é onde o `CLAUDE.md` manda corrigi-los.

### Condições de fechamento, em ordem de importância

1. **Decidir e registrar o que acontece com o required check.** Ou `evals` entra na proteção da
   `main` — e então o PO decide explicitamente como este PR e os próximos passam com 9 casos
   vermelhos (suspensão declarada, como a da S-05 no ADR-014; ou as 9 resolvidas antes) — ou o
   REQ-5 fica aberto e a spec diz que fica. O que não pode é a spec pedir o required check, entregar
   a suíte vermelha, e as duas frases não se olharem. (ACH-1)
2. **Registrar o vazamento do `nao_aplicavel` como Descoberta**, com os três critérios incondicionais
   nomeados, e decidir se a resposta é mais uma trava no prompt, uma trava estrutural (recusar `n/a`
   em critério que não traz "Se/Caso/Quando" — é conferível no texto do critério, sem modelo), ou
   aceitar e monitorar. O que não vale é o dado ficar só no relatório de execução. (ACH-2)
3. **Corrigir o cabeçalho de `S-06-suite-completa.md`** para o modelo que os artefatos gerados
   dizem, e acrescentar `temperature` (e o modelo efetivo) à linha que o `relatorio()` emite — uma
   linha de código e uma de markdown. Enquanto o consolidado contradisser os cinco arquivos que ele
   linka, a evidência inteira fica com uma nota de rodapé invisível. (ACH-3, ACH-9)
4. **Decidir explicitamente o REQ-3**: 5 de 6 encerra, ou o requisito fica aberto até a mudança de
   contrato de `buscar_produtos` (D-3 da S-03, agora com duas medições). Anotar a decisão na spec.
5. **Fechar as duas lacunas de teste que custam pouco e prendem fiação**: (a) o percurso ordenado da
   conversa no runner (ACH-5) — extrair o laço para uma função que aceite uma lista de falas e um
   duplo do grafo é suficiente; (b) `create_score` sem `trace_id` contando como caso registrado no
   visor (ACH-4). Ambas são testáveis sem rede e sem API.
6. **Higiene, num commit só**: nota do topo da spec e checkboxes (ACH-10); `uv run` no alvo
   `evals-check` (ACH-11); guardas de argumento no `evals-ci.sh` (ACH-12); mensagem de erro do
   cenário (ACH-13); posição da nota no ADR-014 (ACH-14); a palavra do BDD 1 (ACH-15); e a ressalva
   da §8 sobre os três pontos em que a spec ficou atrás da implementação.

---

## Anexo — o que este relatório **não** verificou

Escrito em separado para não se perder no meio do texto, e porque um relatório que não delimita o
próprio alcance convida a ser citado além dele.

- **Nenhum eval foi reexecutado.** Nem contra o agente, nem contra o juiz. Os 23 vereditos, o custo,
  a duração e a proporção de tokens são leitura de artefato committado pelo autor.
- **O Langfuse não foi consultado.** A existência dos dataset runs, dos traces por caso, dos scores
  booleanos e da PII mascarada no trace lido de volta é afirmação do autor mais teste de dublê. O
  próprio ADR-014 registra que a primeira execução "deu certo" com zero runs do outro lado, o que
  torna esta a lacuna mais desconfortável da lista.
- **`scripts/evals-ci.sh` nunca foi executado**, nem no caminho caro nem no caminho grátis — o
  segundo por bloqueio do classificador de permissões do ambiente, não por escolha minha.
- **Nenhuma falsificação foi feita**, por decisão do PO em 2026-08-28. O que se perde está escrito no
  ritual e vale repetir aqui, porque nesta spec específica ele morderia: quebra que deixa a suíte
  verde era o único achado capaz de provar que um teste não prova o que o nome dele diz — e o ACH-5
  é exatamente um teste cujo nome promete mais do que ele afirma. Achei-o por leitura; não posso
  garantir que não exista um segundo.
- **Nenhuma infraestrutura foi subida** (`docker compose`, `db-setup`, `seed`). Toda a suíte de 947
  testes é `unit` + `security` e não precisa de nenhuma, o que é o desenho de `docs/testes.md` §1 —
  mas significa que nada que só se prova com Postgres e Qdrant de verdade foi observado por mim.
