# Testes — como se testa nesta casa

> Documento normativo. Vale para toda spec, e tem precedência sobre a skill `tdd` vendorizada
> sempre que os dois discordarem (ADR-009).

**Teste aqui não nasce de cobertura, nasce de risco.**

`docs/riscos.md` já declara, na quinta coluna, a verificação de cada risco de R1 a R9 — e a
frase que governa aquele documento é *"risco sem verificação é desejo, não requisito"*. Este
documento é a outra metade: onde cada verificação vive, em que fronteira ela observa o sistema,
e o que faz um teste ser aceito.

A consequência é dura e vale repetir: **uma spec não fecha enquanto o teste que prova o risco
que ela cobre não estiver verde.** Não é o número de testes que qualifica a entrega — é a
correspondência com a matriz.

---

## 1. Duas camadas, e só duas

```
tests/
├── unit/        rápido, sem I/O, sem contêiner — o comportamento está correto?
└── security/    a fronteira — o comportamento errado é sequer alcançável?
```

A diferença entre elas é a coisa mais importante deste documento:

| | Pergunta | O que produz |
|---|---|---|
| `unit/` | A função faz a conta certa? | correção |
| `security/` | Existe caminho de código até a ação proibida? | **garantia** |

Um teste unitário verde diz que o total foi somado direito. Um teste de segurança verde diz que
o subagent de recomendação **não possui** a tool de escrita — não que ele foi instruído a não
usá-la. Só o segundo sobrevive a uma troca de modelo ou a uma reescrita de prompt.

> **A regra de ouro, aplicada a teste:** o LLM decide o que dizer; o código decide o que pode ser
> feito. Se um teste de segurança só passa porque o prompt pediu com educação, a arquitetura está
> errada — conserte a arquitetura, não o teste.

**Não existe camada de integração neste repositório.** É uma escolha, com preço: o que só se
prova com infraestrutura de verdade — retomada de sessão após restart real do processo, adapter
contra o sandbox do gateway — é verificado **à mão** no `/verificar-spec`, com resultado
registrado no relatório. Está declarado aqui para ninguém achar que está automatizado.

---

## 2. O mapa — risco → teste

O `riscos_cobertos` do frontmatter de cada spec diz quais linhas desta tabela aquela spec
precisa fechar. `/verificar-spec` cruza as duas coisas.

| Risco | Camada | O que se prova | Arquivo |
|---|---|---|---|
| **R1** Alucina atributo, preço ou estoque | `unit` + eval | preço e total saem de código/banco, nunca de texto | S-03: `test_recommendation_tools.py`, `test_catalog_ingestion.py`, `test_groundedness.py` · S-04: `test_order_total.py` |
| **R2** Executa ação indevida | **`security`** | o registro `subagent → tools` não tem escrita na recomendação | `tests/security/test_permission_boundary.py` |
| **R3** Side effect irreversível sem supervisão | **`security`** + `unit` | não há caminho até `emitir_nf` sem aprovação registrada; e a fila do operador registra quem, quando e o motivo | `tests/security/test_hitl_invariant.py` · `tests/unit/test_operator_queue.py` |
| **R4** Prompt injection | **`security`** + eval | payload injetado não alcança tool com side effect | `tests/security/test_injection.py` |
| **R5** Vazamento de PII | **`security`** + `unit` | PII sai mascarada **antes** de deixar o processo | `tests/security/test_pii_redaction.py` |
| **R6** Custo/latência descontrolados | `unit` | budget cap e timeout por tool são respeitados | `tests/unit/test_budget_guard.py` |
| **R7** Regressão silenciosa de prompt | eval | as sub-suítes que o diff pode ter mudado, no job `evals` do PR; a suíte inteira no pós-merge (ADR-014) | `evals/` |
| **R8** Falha de integração externa | `unit` | mock e adapter real satisfazem a mesma interface; o webhook verifica origem e não duplica efeito; e o documento que o mock de NF produz é fiel | `tests/unit/test_ports.py` · `tests/unit/test_payment_webhook.py` · `tests/unit/test_nota_fiscal.py` |
| **R9** Estado corrompido em conversa longa | `unit` + verificação manual | retomada a partir do checkpoint | `tests/unit/test_session_resume.py` |
| **R10** Composição estoura orçamento ou viola restrição | `unit` (S-11) → **`security`** (S-04) | que o validador recusa; e depois, que não há caminho até pedido com composição inválida | `tests/unit/test_composicao.py` · `tests/security/test_composicao_invariants.py` |

**Um risco pode ter mais de um arquivo, e a linha diz de qual spec é cada um.** A R8 é o
segundo caso, e duas das três metades são da S-04: o contrato compartilhado pelos dois adapters
(`test_ports.py`) e a rota que recebe a confirmação (`test_payment_webhook.py`). Um port
correto atrás de um webhook que aceita qualquer POST não fecha o risco. A R1 é o
primeiro caso: a S-03 prova que nenhum fato chega ao cliente sem ter vindo de tool, e a S-04
prova que o total de um pedido sai do banco. As duas metades são o mesmo risco, e nenhuma
sozinha o fecha. A verificação independente da S-03 pegou esta linha apontando para um arquivo
que ainda não existia — cruzamento que falha em silêncio é pior do que lacuna declarada.

**A R8 ganhou uma terceira metade na S-05, e uma lacuna declarada junto.** `test_nota_fiscal.py`
prova que o documento do `MockNFAdapter` é fiel — destinatário PJ campo a campo, chave de acesso
com dígito verificador que fecha, tarja nos dois artefatos. O que ele **não** prova é a metade
que o ADR-004 chama de contrato: *dois* adapters satisfazendo a mesma interface. Existe um
emissor, e vai continuar existindo um só — o adapter de homologação saiu do escopo do projeto
(ADR-004) —, e uma fixture parametrizada com um elemento passaria por vacuidade (§3.3). A
lacuna está escrita aqui e no topo de `test_ports.py`, em vez de coberta por um teste que não
prova nada. **Ela não é uma dívida esperando spec: é o preço declarado de não emitir nota de
verdade**, e a metade da R8 que este repositório fecha para o `NFEmitter` é outra — que a
escolha do emissor é configuração, e que uma configuração impossível é recusada alto em vez de
cair no mock em silêncio.

**A R3 também tem duas metades, e elas respondem a perguntas diferentes.**
`test_hitl_invariant.py` responde *"existe caminho até a emissão sem aprovação registrada?"* —
é a garantia, e é `security`. `test_operator_queue.py` responde *"a fila registra quem, quando e
o motivo, e recusa quem não tem token?"* — é correção, e é `unit`. Uma invariante correta
guardando uma fila que perde pedido não fecha o risco; uma fila impecável na frente de uma
emissão alcançável, muito menos.

**R10 nasce em `unit` e migra para `security`, de propósito.** Na S-11 ainda não existe
`criar_pedido`: um teste de `security` afirmando *"nenhum pedido viola restrição declarada"*
passaria por **vacuidade**, e a §3.3 é explícita sobre isso. O que dá para provar na S-11 é que o
validador recusa. Quando a escrita existir, na S-04, o invariante ganha o teste de `security` que
o fecha. É o mesmo argumento que fez o registro de permissão nascer na S-03 e
`test_permission_boundary.py` só na S-04.

**R2 e R3 não são negociáveis.** Não são cobertura, são o requisito. Um sistema em que o
subagent de recomendação consegue escrever, ou em que existe caminho de emissão sem aprovação
registrada, está errado mesmo com todo o resto verde.

---

## 3. A regra para o agente de código

Esta seção é endereçada ao Claude Code, e é cobrada no `/verificar-spec`.

1. **Toda feature nova nasce com teste unitário.** Não existe task de spec que entregue
   comportamento sem entregar o teste que o descreve. Se a task não tem teste, ela não está
   pronta — e não vira commit.
2. **Toda spec que declara `riscos_cobertos` entrega os testes da tabela acima**, na camada
   indicada. Risco declarado sem teste correspondente não está fechado: está prometido.
3. **Red antes de green.** Escreva o teste, veja-o falhar, então implemente o mínimo que o
   satisfaz. Teste que nasceu verde não provou nada — pode estar afirmando o que já era
   verdade por acaso.
4. **O commit continua sendo por task da spec**, não por ciclo red-green (ADR-005). O ciclo é
   ritmo de trabalho, não unidade de histórico.
5. **Antes de cada commit:** `ruff check` · `ruff format --check` · `pytest tests`.
6. **Descobriu que precisa de um seam que não está na tabela?** Isso é descoberta. Registre em
   "Descobertas" na spec e **pare** para decisão do PO. Não invente camada nova no meio da
   execução.

### Os seams já estão acordados

A skill `tdd` manda perguntar ao usuário quais são os seams antes de escrever qualquer teste. É
bom conselho genérico, e aqui é pergunta **já respondida**: os seams são a tabela da seção 2.
Não reabra a negociação a cada sessão.

---

## 4. O que faz um teste ser aceito

- **Declare o `R#` na primeira linha do docstring.** É o que deixa o `/verificar-spec` responder
  *"quais riscos esta spec fecha e qual teste prova cada um"* sem ler a implementação.
- **Nome descreve comportamento, não função:** `test_recommendation_agent_cannot_create_order`,
  nunca `test_tools_registry`.
- **Valor esperado vem de fonte independente.** Nada de recalcular no teste a mesma conta que o
  código faz. Preço esperado vem do seed ou da spec — teste tautológico passa por construção e
  nunca discorda do código.
- **Mock só na fronteira de port** (ADR-004). Gateway de pagamento e emissor de NF são mockados;
  colaborador interno, nunca. Se precisou mockar algo interno, o seam está errado.
- **Dinheiro é `Decimal`, nunca `float`.** Um teste que aceita `float` deixa passar exatamente a
  classe de erro que R1 existe para impedir.
- **Nenhum dado real.** CPF, e-mail, nome, CNPJ ou certificado verdadeiro não entram no
  repositório, nem em fixture.

```python
@pytest.mark.risco("R2")
@pytest.mark.requires_backend
def test_recommendation_agent_cannot_create_order(tool_registry):
    """R2 — the recommendation subagent has no write tool registered.

    Fails if the permission boundary leaks (ADR-002, RF-1.5).
    """
```

`@pytest.mark.requires_backend` faz o teste **pular** enquanto `backend/` não existir, em vez de
quebrar no import. Suíte permanentemente vermelha ensina a ignorar suíte vermelha.

---

## 5. O que deliberadamente não se testa

- **Qualidade conversacional** — tom, condução, simpatia. Isso é `evals/`, e mesmo lá é
  pass/fail por caso, sem nota (ADR-006). Julgamento fino fica com a verificação independente.
- **Texto literal de prompt.** Prompt muda; comportamento é que não pode regredir — e quem
  protege isso é a suíte de evals.
- **Detalhe interno de módulo profundo.** Teste que quebra quando você refatora sem mudar
  comportamento é dívida, não segurança.
- **A biblioteca de terceiro.** Não testamos que o LangGraph faz `interrupt`; testamos que **o
  nosso fluxo** não emite sem aprovação registrada.

---

## 6. A pipeline de PR

Todo pull request para a `main` roda a suíte inteira, e o merge fica bloqueado enquanto algum
check estiver vermelho.

| Onde | O que roda | Quando |
|---|---|---|
| `pre-commit` (local) | ruff, ruff-format, segredo, commitlint | a cada commit |
| `pre-push` (local) | `pytest tests` | a cada push |
| CI, job `test` | `pytest tests` — unit + security | a cada PR |
| CI, job `evals` | golden + adversarial contra o agente, nas sub-suítes afetadas pelo diff | a partir da S-06 |
| CI, job `evals` (pós-merge) | a suíte inteira | a partir da S-06 |

O `pre-commit` é o portão local; o CI é o remoto. O `pytest` fica no `pre-push` e não no
`pre-commit` de propósito: hook lento treina a usar `--no-verify`, e aí o portão local inteiro
morre para ganhar dois segundos.

```bash
pip install -r tests/requirements.txt
pytest tests                  # tudo
pytest tests/unit             # só correção
pytest tests/security         # só a fronteira
pytest tests -m "risco"       # só o que declara risco
```

Detalhe que vale saber: **nenhuma das duas camadas precisa de contêiner.** É consequência de
não existir camada de integração — o job `test` do CI sobe em segundos, sem `docker compose`.
