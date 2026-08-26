---
id: S-01
titulo: Discovery como código
status: aprovada
branch: spec/s-01-discovery
issue: #2
adrs: [ADR-001, ADR-006]
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
- [ ] REQ-2 Schema dos casos de eval definido e validável por script (`make evals-check`): cada caso
      declara necessidade, critério de aprovação e produtos válidos. O schema, o alvo do Makefile e
      o teste de rastreabilidade chegaram na S-00 (REQ-7 de lá); a S-01 fecha o que faltava — o campo
      `produtos_validos` e o cruzamento contra o seed do catálogo.
- [ ] REQ-3 Golden dataset inicial: 12 conversas de referência em `evals/golden/` — YAML validado
      contra `evals/schema/caso.schema.json`, com necessidade, resposta esperada em critérios e
      produtos válidos. (O texto original dizia JSON; o corpus nasceu em YAML na S-00 e o schema
      é JSON Schema, que valida YAML sem conversão.)
- [ ] REQ-4 Suite adversarial inicial: 6 casos de injection/abuso em `evals/adversarial/`, no mesmo formato.
- [ ] REQ-5 Catálogo seed: `data/catalogo/*.json` com ~50 produtos e atributos ricos (tipo, região,
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
| Métrica | Alvo | Como medir |
|---|---|---|
| Casos golden / adversariais | 12 / 6 | contagem em evals/ |
| Produtos no seed | ≥ 50, 100% com preço e ≥4 atributos | script de validação do seed |

## Verificação independente
- Rodar `make evals-check` e o validador do seed.
- Amostrar 3 casos golden e conferir que os produtos citados existem no seed.

## Descobertas (preenchido durante a execução)

**D-1 — "testado em integração" aparece em oito lugares; a camada de integração não existe.**
A varredura do REQ-1 encontrou a única contradição entre normativos do repositório, e ela é
estrutural, não de redação:

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

## Definition of Done
- [ ] Checklist padrão do template
