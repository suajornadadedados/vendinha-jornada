---
id: S-01
titulo: Discovery como código
status: em-revisao
branch: spec/s-01-discovery
issue: #2
adrs: [ADR-001, ADR-006, ADR-011]
riscos_cobertos: [R1, R7]
---

# S-01 — Discovery como código

## Objetivo
Os artefatos da discovery (requisitos, jornada, riscos, golden dataset inicial) entram no repo
por PR — requisitos rastreáveis antes de qualquer feature.

## Requisitos
- [x] REQ-1 `docs/requisitos.md`, `docs/jornada.md`, `docs/riscos.md`, `docs/decisoes.md` e ADRs
      001-010 revisados e definitivos: sem referência morta e sem contradição entre normativos.
      O texto original dizia "001-008" — ADR-009 e ADR-010 nasceram das descobertas da S-00.
- [x] REQ-2 Schema dos casos de eval definido e validável por script (`make evals-check`): cada caso
      declara necessidade, critério de aprovação e produtos válidos. O schema, o alvo do Makefile e
      o teste de rastreabilidade chegaram na S-00 (REQ-7 de lá); a S-01 fecha o que faltava — o campo
      `produtos_validos` e o cruzamento contra o seed do catálogo.
- [x] REQ-3 Golden dataset inicial: 12 conversas de referência em `evals/golden/` — YAML validado
      contra `evals/schema/caso.schema.json`, com necessidade, resposta esperada em critérios e
      produtos válidos. (O texto original dizia JSON; o corpus nasceu em YAML na S-00 e o schema
      é JSON Schema, que valida YAML sem conversão.)
- [x] REQ-4 Suite adversarial inicial: 6 casos de injection/abuso em `evals/adversarial/`, no mesmo formato.
- [x] REQ-5 Catálogo seed: `data/catalogo/*.json` com ~50 produtos e atributos ricos (tipo, região,
      maturação, intensidade, harmonização, preço). Somam-se `disponivel` e `prazo_estimado`, que a
      nota de escopo de `docs/requisitos.md` torna campos lidos do seed. Preço é **string decimal**
      (`"89.90"`): JSON não tem tipo decimal, e número vira `float` no parse — exatamente a classe
      de erro que R1 existe para impedir (`docs/testes.md` §4).

## O que R1 e R7 significam aqui

O frontmatter declara `riscos_cobertos: [R1, R7]`, mas **nenhum dos dois testes-âncora da tabela
de `docs/testes.md` §2 é entregável desta spec**: R1 fecha em `tests/unit/test_order_total.py`,
que precisa de pedido e preço (S-03/S-04), e R7 fecha com a suíte inteira rodando contra o agente,
no job `evals` do CI (S-06). Sem isto escrito, a verificação independente reprova a spec por
procurar um arquivo que ela não devia ter.

O que a S-01 entrega são as **pré-condições** dos dois — os artefatos contra os quais R1 e R7 serão
provados depois:

| Risco | Pré-condição entregue aqui | Onde o risco fecha de fato |
|---|---|---|
| R1 | O seed existe, é íntegro e é a **única** origem de preço e atributo. Preço em decimal, nunca float | S-03 (groundedness) · S-04 (`test_order_total.py`) |
| R7 | O corpus é rastreável, validado contra o schema e amarrado ao seed — caso que reprova por falta de dado não é régua | S-06 (runner + job `evals` obrigatório) |

É o mesmo enquadramento que o teste da S-00 já usa no docstring: *"Guards the eval corpus that R7
depends on — without closing R7 itself."*

## Fora de escopo
Runner de evals (S-06); ingestão no Qdrant (S-03).

## Tasks
1. `docs(s-01): normative discovery docs and initial ADRs`
2. `eval(s-01): eval case schema with validation script`
3. `eval(s-01): golden dataset (12 cases) and adversarial suite (6 cases)`
4. `feat(s-01): catalog seed data (~50 products)`

O que a execução entregou, e por que difere da lista:

| # | Commit | Nota |
|---|---|---|
| 1 | `adr(s-01): record two test layers, no integration tier` | Nasceu da descoberta D-1. A task 1 era revisão; a revisão achou uma decisão faltando |
| 1 | `docs(s-01): reconcile the normative docs with the test-layer decision` | A task 1 propriamente dita. Os documentos já existiam — o trabalho foi reconciliar, não escrever |
| 4 | `feat(s-01): catalog seed data (50 products)` | Executada antes da task 2: o cruzamento da 2 precisa do seed para nascer verde |
| 2 | `eval(s-01): bind eval cases to the seed with produtos_validos` | Só a metade que faltava — schema e validador vieram da S-00 |
| 3 | `eval(s-01): golden dataset (12 cases) and adversarial suite (6 cases)` | +8 golden e +3 adversariais sobre os 7 casos que já existiam |
| — | `docs(s-01): record what the spec delivered and what it measured` | Fechamento da spec |
| — | `docs(harness): move independent verification ahead of the PR` | Fora do escopo da S-01, por instrução do PO durante a sessão. Escopo `harness`, commit isolado |
| — | `docs(s-01): fix what the independent verification found` | Correção dos achados do relatório |

Entrega final: **8 commits**. A ordem de execução das quatro primeiras tasks (1 → 4 → 2 → 3) não é
a da lista, para nenhum commit deixar a suíte vermelha atrás de si.

## BDD
```gherkin
Cenário: rastreabilidade risco → verificação
  Dado a matriz de riscos R1-R9
  Quando leio qualquer linha
  Então ela aponta uma spec responsável e uma verificação automatizada

Cenário: casos de eval válidos
  Quando executo "make evals-check"
  Então o schema valida necessidade, critério de aprovação e produtos citados de cada caso sem erro
```

## Métricas de sucesso
| Métrica | Alvo | Como medir | Medido |
|---|---|---|---|
| Casos golden / adversariais | 12 / 6 | contagem em `evals/` | **12 / 6** |
| Produtos no seed | ≥ 50, 100% com preço e ≥4 atributos | `tests/unit/test_catalog_seed_is_usable.py` | **50**, 100% / 100% |
| Riscos com ao menos um caso | — | leitura do campo `riscos` do corpus | **R1-R6 e R8**; R7 é a própria suíte, R9 é restart de processo |
| Suíte local | verde | `pytest tests` | **294 passed** |

## Verificação independente
- Rodar `make evals-check` e o validador do seed (`pytest tests/unit`). Sem `make` na máquina,
  a linha de dentro do alvo é equivalente — está no README, seção Quickstart.
- Amostrar 3 casos golden e conferir que os produtos de `produtos_validos` existem em
  `data/catalogo/`. O cruzamento é automatizado desde esta spec, mas a amostragem à mão continua
  valendo: ela confere se o produto citado *faz sentido* para o caso, o que nenhum teste faz.
- Falsificar os dois validadores: quebrar um caso e um produto do seed e conferir que reprovam de
  forma independente. Feito durante a execução, com resultado nos commits — repetir vale como
  verificação de que o gate não regrediu.
- Ler `docs/riscos.md` e `docs/testes.md` §2 lado a lado: as duas tabelas precisam concordar em
  camada e arquivo, linha a linha. Era exatamente aí que estava a divergência do D-1.

## Descobertas (preenchido durante a execução)

**D-1 — "testado em integração" aparece em oito lugares; a camada de integração não existe.**
A varredura do REQ-1 encontrou uma contradição estrutural entre normativos — não de redação.
(*Ela não era a única: a verificação independente achou depois uma segunda redação do mesmo
problema, no R2. Ver D-5.*)

| Onde | O que diz |
|---|---|
| `docs/adr/ADR-003` §Decisão | "Invariante testada **em integração**: nenhum caminho emite NF sem aprovação registrada" |
| `docs/riscos.md` R3 | Verificação: "Teste **de integração** do interrupt/retomada" |
| `docs/decisoes.md` D8 | "Unit → **integração** → evals como gate (EDD)" |
| `docs/PRD.md` RF-3.5 | "invariante testada **em integração**" |
| `docs/arquitetura.md` §3.2 | "isso é testado **em integração**, não prometido em prosa" |
| `docs/specs/S-05` REQ-5 e métricas | "invariante testada **em integração**"; "teste **de integração** + auditoria" |
| `.claude/skills/vendinha-harness` | "e isso e testado **em integracao** (ADR-003, R3, RF-3.5)" |
| **`docs/testes.md` §1** | **"Não existe camada de integração neste repositório."** — e mapeia R3 para `tests/security/test_hitl_invariant.py` |

Todos nasceram no mesmo `first commit`: a discovery escreveu "integração" como sinônimo de
"prova de verdade, não promessa", e o `docs/testes.md` depois fechou a arquitetura de testes em
duas camadas — sem que ninguém voltasse para reconciliar as duas.

O mesmo desalinhamento contamina a coluna "Verificação" de `docs/riscos.md` para além do R3:
R1 omite o teste unitário que `docs/testes.md` exige, R2 diz "teste unitário" onde o mapa manda
`tests/security/`, e R6 aponta um dashboard onde o mapa aponta um arquivo de teste.

**Por que isto não foi conserto de texto:** `ADR-003` está **aceito**, e o `CLAUDE.md` trata ADR
aceito como imutável — *"mudança gera novo ADR"*. Reescrever a linha da Decisão dele para dizer
`security` seria editar decisão aceita por dentro. E a precedência do harness coloca
`docs/riscos.md` (3) **acima** de `docs/testes.md` (4), então "o normativo mais novo vence" não
resolvia sozinho.

**Resolvido pelo PO: `ADR-011` — duas camadas de teste, `unit` e `security`, sem camada de
integração.** O ADR-003 recebeu no topo a mesma nota que o ADR-007 recebeu do ADR-010 — *atualizado
apenas quanto à camada de teste* — com o corpo intocado, preservando a imutabilidade. Os outros sete
lugares passaram a nomear a camada real. A exigência não afrouxou: mudou para um endereço mais forte,
porque um teste de `security/` prova que o caminho proibido **não existe**, enquanto um de integração
provaria só que o caminho feliz funciona.

Efeito colateral tratado junto: a coluna "Verificação" de `docs/riscos.md` era texto livre e
divergia de `docs/testes.md` §2 em cinco linhas além do R3 (R1, R2, R6, R8, R9). Agora cada linha
nomeia camada e arquivo, e o cabeçalho da matriz diz que as duas tabelas são a mesma decisão vista
de dois lados.

Uma ocorrência ficou de fora, deliberadamente: `docs/specs/S-04` §Métricas diz *"eval de
integração"* — ali a palavra descreve um caso de eval ponta a ponta, não um tier de teste. Sentido
diferente, ficou como está.

**D-2 — a fixture da S-00 já apontava para este seed, com outros números.**
`tests/unit/conftest.py` dizia, desde a S-00: *"quando o seed da S-01 chegar, estes nomes têm que
existir nele"*. Quando o seed chegou, dois dos três não existiam (`doce-de-leite-vicosa`) ou tinham
preço diferente (Canastra meia-cura a `78.90` na fixture, `89.90` no catálogo).

Resolvido dentro do escopo, porque a própria fixture tinha previsto o acerto: os ids e os preços
passaram a ser os do seed. Uma fixture que cita preço que o catálogo não tem deixaria um futuro
`test_order_total.py` afirmar um total que nenhum cliente poderia ser cobrado — e ele passaria,
porque teste e fixture concordariam entre si (`docs/testes.md` §4: *valor esperado vem de fonte
independente*). A linha indisponível da fixture trocou de produto para uma que está de fato
indisponível no seed, mantendo o caminho "não temos isso agora" exercitável.

**D-3 — `make` não existe na máquina do PO.** Não é defeito: o `README` já previa
(*"quem não tiver `make` roda a linha de dentro do alvo"*), e todos os alvos são de uma linha só
justamente para isso. Registrado porque a Verificação independente cita `make evals-check`, e o
verificador precisa saber que rodar `pytest tests/unit/test_eval_corpus_is_traceable.py -q` é
a mesma coisa, não um atalho.

**D-4 — R9 continua sem caso de eval, e é assim que deve ser.** O corpus fechou com R1-R6 e R8
cobertos. R7 é a suíte inteira, por definição — nenhum caso individual o cobre. R9 (estado
corrompido em conversa longa) exige reiniciar o processo, coisa que nenhum caso conversacional
faz: fica com `tests/unit/test_session_resume.py` e com a verificação manual, exatamente como
`docs/testes.md` §1 já declarava. Registrado para o `/verificar-spec` não ler a ausência como falha.

**D-5 — a verificação independente achou a segunda metade da D-1, e um portão que ela mesma
atravessou.** A sessão revisora rodou antes do PR (regra nova do `CLAUDE.md`, item 4) e reprovou
o REQ-1 com razão. Achados corrigidos nesta spec:

| Achado | O que era | Correção |
|---|---|---|
| **NC-1** | A D-1 corrigiu *"testado em integração"* em oito lugares, mas a **mesma** contradição tinha uma segunda redação: *"teste unitário trava a fronteira"* para o R2, viva em `S-04:19`, `S-04:30`, `ADR-002:13`, na skill do harness e no texto do diagrama `arquitetura-produto.svg` | ADR-011 passa a cobrir as duas redações; ADR-002 recebe a nota de cabeçalho que o ADR-003 já tinha; os cinco lugares nomeiam `security` |
| **NC-3** | A nota do `golden-008` afirmava que `111.111.111-11` tem dígitos verificadores errados. **Ele passa no cálculo** (DV1=1, DV2=1) — é inválido por sequência repetida | Nota corrigida, e o caso ficou mais forte: o número existe justamente para pegar validador que só confere o dígito |
| **NC-4 / NC-5** | Tabela de commits e tabela de famílias do `evals/README.md` desatualizadas | Atualizadas contra o medido |
| **R-1** | `requisitos` era o único campo de rastreabilidade sem cruzamento. O revisor falsificou: `RF-9.9` passava | Quarto cruzamento entrou, contra o `docs/PRD.md`. Falsificado de novo: agora reprova |
| **R-2** | `O-2` e `O-4` não existem no PRD, que usa `O1`…`O5`. O schema exigia um hífen que o PRD não escreve | Pattern e casos alinhados ao PRD. Era achado direto da R-1 — com o cruzamento, teria aparecido sozinho |
| **R-6 / R-7** | O ADR-011 declarava menos riscos do que tocou; a spec que criou o ADR-011 não o listava no frontmatter | Ambos corrigidos |
| **R-8** | `adversarial-006` declarava `falha_dura` num caso que não mede ação nenhuma — um modelo prolixo derrubaria a suíte inteira | `falha_dura: null`, com o porquê na nota |

O que a verificação prova sobre o método: **o autor não enxerga a segunda ocorrência do próprio
achado.** A D-1 encontrou uma contradição e eu a tratei como se fosse a contradição — a frase
"a única contradição do repositório" estava na spec, e era falsa. Um `grep` a desmentia.

Ficam registradas para as specs seguintes, sem correção aqui: **R-3** (fixture↔seed continua
acordo humano; a S-01 consertou a instância, não a classe), **R-4** (`tests/` fora do `mypy`),
**R-5** (o corpo do ADR-003 ainda diz "integração"; só o cabeçalho corrige — é o preço da
imutabilidade), **R-10** (seed malformado quebra a coleta do pytest com traceback em vez de
mensagem) e **R-11** (`pytest tests -m "risco"` coleta zero: ou o marker entra nos testes, ou o
comando sai do `docs/testes.md` §6).

## Definition of Done
- [x] Todos os requisitos com evidência nesta spec (REQ-1 a REQ-5)
- [x] Suíte local verde: `ruff check` · `ruff format --check` · `pytest tests` (294 passed)
- [ ] CI verde no PR
- [ ] PR com evidência e `Closes #2`
- [ ] Relatório `/verificar-spec` anexado com veredito APROVADO
