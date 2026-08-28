---
spec: S-05
veredito: APROVADO COM RESSALVAS
commit: 33a6075a0a15fc9025795814292312ce57ef5813
branch: spec/s-05-hitl-nf
data: 2026-08-28
---

# Relatório de verificação independente — S-05 (HITL + emissão de NF)

| | |
|---|---|
| **Spec** | `docs/specs/S-05-hitl-nf.md` (`status: em-revisao`) |
| **Branch** | `spec/s-05-hitl-nf` @ `33a6075` (8 commits) |
| **Base** | `origin/main` @ `09654fe` — `origin/main` é ancestral de `HEAD`, diff não inflado |
| **PR** | **não existe** (`gh pr list --head spec/s-05-hitl-nf` → `[]`) — correto sob o `CLAUDE.md` item 4 |
| **Issue** | [#6](https://github.com/suajornadadedados/vendinha-jornada/issues/6) — OPEN, título bate com a spec |
| **Diff** | 8 commits · 29 arquivos · +5.152 / −62 |
| **Suíte** | **898 passed**, 0 failed, 73,9 s |
| **Lint** | `ruff check .` limpo · `ruff format --check .` 124 arquivos ok |
| **Typecheck** | `mypy` backend 36 arquivos · `mypy` tests 29 arquivos — sem erro |
| **Falsificações** | **25 executadas · 16 reprovaram · 9 sobreviveram** (1 provavelmente equivalente) |
| **Verificação manual** | Postgres 16 real, dois processos separados — reproduzida por mim, do zero |
| **Achados** | 4 Alta · 4 Média · 4 Baixa |
| **Ambiente** | Windows 11 · `backend/.venv` · `make` não existe nesta máquina, rodei a linha de dentro de cada alvo |
| **Veredito** | **APROVADO COM RESSALVAS** |

## Enquadramento recebido

A mensagem que iniciou esta sessão continha **`S-05` e nada mais**. Nenhum enquadramento a
registrar: nada sobre o que já estaria verde, quais arquivos olhar, quantos testes passam ou
quanto do trabalho está pronto. É o contrato do `.claude/agents/verificador-de-spec.md` cumprido
à risca, e vale dizê-lo em voz alta porque é a segunda vez seguida (a S-04 registrou o mesmo).

Registro à parte, porque **não** é enquadramento e sim um fato sobre o objeto revisado: a spec
S-05 é, ela própria, um documento longo de auto-avaliação — traz uma tabela "Verificação manual
registrada" com quinze linhas e uma seção "Verificação de mutação registrada" com dois números.
**Não tomei nenhum desses números como dado.** Refiz o roteiro manual inteiro contra um Postgres
que eu mesmo subi, em dois processos separados, e refiz as duas mutações declaradas mais outras
vinte e três. Onde meu número bate com o do autor, digo. Onde não pude reproduzir, marco
**NÃO VERIFICÁVEL**.

## Nota de método sobre credenciais e evals

Não li o `.env` — a regra de `.claude/settings.json` o nega ao agente e eu não a contornei.
Nenhuma chave de modelo está no meu shell. Portanto **não executei as suítes de evals contra o
agente**: o `3 de 7`, `0 de 6` e `2 de 4` da DESC-8, e o A/B em worktree limpo da `main` que a
sustenta, são **palavra do autor que eu não pude conferir**. Rodei o que é gratuito e
determinístico — `tests/unit/test_eval_corpus_is_traceable.py` (schema do corpus, sem agente):
**139 casos, verde**. Tentei `python -m vendinha.evals.runner --spec S-05` e o runner parou em
`connection timeout expired`, antes mesmo de chegar na recusa de turno `de: operador` que a
DESC-5 descreve.

## Rastro que deixei

As 25 falsificações **não tocaram a árvore de trabalho**: rodei todas num `git worktree`
descartável dentro do scratchpad da sessão, removido ao final (`git worktree list` mostra só o
principal). A verificação contra Postgres usou um contêiner `postgres:16-alpine` **descartável e
próprio**, publicado em `127.0.0.1:15433`, criado e destruído por mim — o compose do projeto não
foi levantado e nenhum banco do autor foi tocado. Scripts temporários ficaram no scratchpad,
nenhum no repositório.

`git status --short` **antes** e **depois**, idênticos:

```
?? docs/workshop/apresentacao.html
```

Esse arquivo já estava não rastreado quando cheguei. Não é meu e não o removi.

---

## 1. Requisito a requisito

| REQ | Veredito | Prova que **eu** produzi |
|---|---|---|
| **REQ-1** interrupt persistido após pagamento | **CONFORME COM RESSALVA** | `test_the_invoice_graph_pauses_with_its_state_in_the_checkpointer` verde; e no meu roteiro Postgres a fase 1 parou os dois pedidos em `next=('aguardar_aprovacao',)` com `values={'pedido_id': ...}`. **A ressalva é A-4:** o trecho que liga *pagamento confirmado* → *interrupt* não tem teste — apaguei a chamada e a suíte inteira ficou verde |
| **REQ-2** API da fila, aprovar/rejeitar com registro | **CONFORME** | `test_operator_queue.py` (18 testes) verde; mutação 21 (`composicoes=()`) e mutação 3 (token aberto quando não configurado) reprovam. Contra Postgres: fila com os dois pedidos, destinatário PJ completo, `quem/quando/motivo` gravados |
| **REQ-3** aprovação retoma; rejeição comunica o motivo | **CONFORME** | Fase 2, processo novo: `aget_tuple` achou a thread, `decidir` retomou e emitiu; rejeição gravou o motivo e levou a `nota_rejeitada`; `consultar_pedido` devolve `motivo_rejeicao` (mutação 9 reprova) |
| **REQ-4** port `NFEmitter` + `MockAdapter` fiel, destinatário PJ | **CONFORME NO CÓDIGO, NÃO PROVADO PELOS TESTES** | Inspecionei os bytes da DANFE que o mock produziu no meu banco: razão social, CNPJ formatado, IE, logradouro, município, chave formatada, operador e a tarja (5 ocorrências) — **tudo certo hoje**. Mas as duas quebras A-1 e A-2 sobrevivem com 898 testes verdes |
| **REQ-5** invariante em `security` | **CONFORME** | 13 testes em `tests/security/test_hitl_invariant.py`; mutação 1 → 3 vermelhos, mutação 2 → 5 vermelhos, mutação 11 → 6 vermelhos, mutação 20 → 4 vermelhos. A porta **aguenta** |
| **REQ-6** cliente com acesso à DANFE/XML | **CONFORME COM RESSALVA** | Os cinco campos fiscais de `consultar_pedido` e as duas rotas funcionam (mutações 9 e 14 reprovam). **Ressalva R-2:** "recebe no chat" virou "pergunta e o agente consulta" (D-8) — é reinterpretação declarada de RF-3.6, não omissão |

### `riscos_cobertos` cruzado com a matriz

`riscos_cobertos: [R3, R8]`. `docs/testes.md` §2, **na versão desta branch**, atribui:

| Risco | Arquivos-âncora | Existem? | Verdes? |
|---|---|---|---|
| R3 | `tests/security/test_hitl_invariant.py` · `tests/unit/test_operator_queue.py` | sim | sim (13 + 18) |
| R8 | `tests/unit/test_ports.py` · `test_payment_webhook.py` · `test_nota_fiscal.py` | sim | sim |

**Os dois documentos normativos acima da spec foram alterados por ela** — `docs/riscos.md`
(R3 e R8) e `docs/testes.md` (§2). Conferi linha a linha: as duas edições **acrescentam** metade
de cobertura e **declaram uma lacuna**; nenhuma afrouxa nada, nenhuma remove exigência. É
manutenção do mapa, do mesmo tipo que a DESC-5 da S-04, e a precedência foi respeitada. A lacuna
declarada — *a paridade entre dois adapters de `NFEmitter` só fecha na S-09* — está escrita em
três lugares (`riscos.md`, `testes.md` §2, cabeçalho de `test_ports.py`), que é o oposto de um
cruzamento que falha em silêncio. **Nenhum corpo de ADR foi tocado** (`git diff origin/main...HEAD -- docs/adr/` é vazio).

### Cenários BDD

| Cenário | Veredito |
|---|---|
| *NF só sai com aprovação* — grafo retoma, DANFE com tarja e destinatário PJ, cliente notificado | **CONFORME**, com a ressalva A-1/A-2 sobre a DANFE |
| *emissão sem aprovação é impossível* — bloqueada e incidente registrado | **CONFORME** — reproduzido em quatro formas diferentes, inclusive contra Postgres, sempre com `WARNING emissão de NF barrada` |

---

## 2. Tabela de falsificações

25 quebras deliberadas, uma por vez, restaurando entre elas, num worktree descartável. Suíte
inteira (`pytest tests`) a cada uma.

| # | Quebra | Resultado |
|---|---|---|
| 1 | `fiscal.emitir`: guarda de aprovação → `if False` | **3 vermelhos** (os três de chamada direta) — bate com a spec |
| 2 | `o_que_o_banco_diz` forçado a `"emitir"` | **5 vermelhos** (2 de grafo + 3 da fila) — bate com a spec |
| 3 | `_operador_autenticado`: aceita quando `OPERADOR_API_TOKEN` não está definido | **4 vermelhos** |
| 4 | DANFE: tarja removida da faixa preta **e** da marca d'água | **SOBREVIVEU** → A-1 |
| 4b | idem + tarja removida do `setTitle` do PDF | **SOBREVIVEU** → A-1 |
| 5 | XML: `TARJA_LONGA` fora do `infCpl` | **2 vermelhos** |
| 6 | `digito_da_chave` devolve sempre `"0"` | **SOBREVIVEU** → A-3 |
| 7 | `inscricao_do_destinatario` devolve sempre `ISENTO` | **1 vermelho** |
| 8 | `PedidosEmMemoria._desfecho_da_nota`: guarda de transição → `if True` | **SOBREVIVEU** → M-2 |
| 9 | `_com_a_nota` curto-circuitado (sem estado fiscal) | **2 vermelhos** |
| 10 | `emissor_de`: ramo `homologacao` removido | **1 vermelho** |
| 10b | `emissor_de`: `homologacao` cai no mock em silêncio | **1 vermelho** |
| 11 | `decidir` não grava a decisão | **6 vermelhos** |
| 12 | validador `rejeicao_exige_motivo` → `if False` | **2 vermelhos** |
| 13 | rota: guarda de `AGUARDANDO_PAGAMENTO` (409) removida | **1 vermelho** |
| 14 | `_resumir`: links de DANFE/XML sempre presentes | **3 vermelhos** |
| 15 | `PostgresFiscal.registrar_decisao`: `rowcount` de volta para fora do cursor (o bug da DESC-7) | **SOBREVIVEU** → M-3 |
| 16 | `_resumir`: CNPJ sem `mascarar_cnpj` | **1 vermelho** |
| 17 | `_abrir_fila_da_nota`: a chamada que abre o interrupt virou `pass` | **SOBREVIVEU** → A-4 |
| 18 | `PREFIXO_DA_THREAD = ""` (thread da nota sem namespace) | **SOBREVIVEU** → B-1 |
| 19 | `conduzir_ate_o_fim`: retoma sem checar `estado.next` | **SOBREVIVEU** — provável mutante equivalente, não conto como achado |
| 20 | `MockNFAdapter`: `aprovada_por="sistema"` | **4 vermelhos** |
| 21 | `_na_fila`: `composicoes=()` | **1 vermelho** |
| 22 | DANFE sem o quadro do destinatário | **2 vermelhos** (pegos só pelas asserções de IE) |
| 23 | DANFE imprime **razão social, CNPJ e endereço do EMITENTE** no quadro do destinatário | **SOBREVIVEU** → A-2 |

**Confirmo os dois números que a spec declara** (linhas 1 e 2), inclusive a observação de que os
dois testes de grafo sobrevivem à quebra do guarda de `emitir` e vice-versa: as duas guardas são
defesa em profundidade de verdade. Esse é o achado positivo mais importante deste relatório.

---

## 3. Verificação manual contra Postgres — refeita por mim

Contêiner próprio, `postgres:16-alpine` em `127.0.0.1:15433`. **Dois processos separados**, que é
o que a spec pede quando fala em matar o processo durante o interrupt: o processo A abre a pausa e
morre; o processo B, sem nenhum estado em memória compartilhado, encontra o checkpoint e conclui.

### Processo A

| O que | Resultado |
|---|---|
| `saver.setup()` + `PostgresPedidos.setup()` + `PostgresFiscal.setup()`, **rodados duas vezes** | ok, idempotente |
| Colunas de `pedido` | `..., criado_em, inscricao_estadual` — a coluna **no fim**, provando que veio pelo `ALTER TABLE` e confirmando o `cabecalho[10]` da DESC-3 |
| Constraints de `aprovacao_de_nf` | `aprovacao_de_nf_pkey`, `aprovacao_de_nf_decisao_check`, `aprovacao_de_nf_pedido_id_fkey`, **`rejeicao_exige_motivo`** |
| Sequência `numero_da_nota` | existe |
| Pagamento → pausa | os dois pedidos em `next=('aguardar_aprovacao',)`, `values={'pedido_id': ...}` — **ponteiro, sem payload** |
| Fila derivada do banco | os dois pedidos |
| `emitir` direto, sem aprovação | **bloqueada**, `WARNING emissão de NF barrada ... (decisão atual: nenhuma)`, `nota_de` → `None` |
| `INSERT` à mão de rejeição sem motivo | **`CheckViolation: rejeicao_exige_motivo`** — a regra é do banco, não só do Pydantic |

### Processo B (novo processo, nada em memória)

| O que | Resultado |
|---|---|
| `aget_tuple` na thread `nf:...` | **encontrou** — o checkpoint sobreviveu à morte do processo A |
| Fila | os dois pedidos de volta |
| **DESC-7**: `registrar_decisao` contra Postgres | `primeira=True`, `segunda=False` — **o bug está corrigido**, e a implementação Postgres concorda com a em memória |
| `registrar_decisao` em id fantasma | `PedidoInexistente` |
| Aprovação retoma e emite | nota nº 1, série 1, chave `31260822333444000181550010000000011125525353`, XML 2.429 chars com tarja e IE, DANFE 11.369 bytes começando em `%PDF-`, pedido em `nota_emitida` |
| **Dígito verificador, conferido por aritmética que escrevi eu** (não pela função do produto) | `dv=3`, igual ao emitido. Campos da chave: `cUF=31 AAMM=2608 CNPJ=22333444000181 mod=55 série=001 nNF=000000001 tpEmis=1` — todos corretos |
| Aprovar de novo | operador vigente continua `ana.souza`, mesmo número de nota |
| Rejeição | motivo gravado, `nota_de` → `None`, pedido em `nota_rejeitada` |
| Aprovar um já rejeitado | vigente continua `rejeitada` / `bruno.lima`, nada emitido |
| Fila final | vazia |
| `registrar_rejeicao` num já emitido | **não reverte** — continua `nota_emitida` |
| `registrar_emissao` em id fantasma | `PedidoInexistente` |

### Inspeção dos bytes da DANFE (porque nenhum teste faz isso)

Todas presentes no PDF: `SEM VALOR FISCAL` (5×), `SEM VALOR FISCAL - DOCUMENTO DE DEMONSTRACAO`
(3×), chave formatada, `Aurora Servicos Digitais LTDA`, `11.222.333/0001-81`, `0011223344556`,
`Rua das Acacias`, `Belo Horizonte` (2×), razão social do emitente, `ana.souza`.

**O artefato que este código produz hoje está certo.** O problema é que ele poderia estar errado
das duas formas dos achados A-1 e A-2 sem que nada reprovasse.

---

## 4. Achados

### A-1 · ALTA — a tarja da DANFE que o REQ-4 nomeia não é provada por teste nenhum

Removi a tarja **da faixa preta do topo**, **da marca d'água a 45°** e **do título do PDF**, em
`backend/vendinha/nota/danfe.py`, e as 898 asserções continuaram verdes. O que segura o
`assert TARJA.encode() in emitida.danfe` de
`test_both_artifacts_announce_that_they_have_no_fiscal_value` é uma menção lateral, no quadro de
protocolo (`f"NÃO AUTORIZADA - {TARJA_LONGA}"`), que existe para dizer outra coisa.

O docstring de `danfe.py` argumenta que a tarja é *"uma faixa preta no topo de cada folha, que
sobrevive a uma impressão em preto e branco, e uma marca d'água"*. Nenhuma das duas está sob
teste. O RF-3.4 e o REQ-4 pedem a DANFE **com tarja**, e o que sobrou provado é que a string
aparece em algum lugar do arquivo.

> É achado sobre o **teste**, não sobre o código: verifiquei os bytes e a tarja está lá, 5 vezes.

### A-2 · ALTA — a DANFE pode nomear o EMITENTE como destinatário, com a suíte verde

Troquei, no quadro `DESTINATÁRIO / REMETENTE` da DANFE, a razão social, o CNPJ e o endereço do
pedido pelos do `EMITENTE`. **Nada reprovou.** O XML continua certo, e o XML é onde estão as
onze asserções campo a campo (`test_the_recipient_is_the_buying_company_field_by_field`).

Isto é exatamente o requisito central da spec — *"destinatário PJ: razão social, CNPJ, inscrição
estadual e endereço de entrega, **todos vindos do pedido**"* — e é o documento que o operador
aprova e que a contabilidade da compradora recebe. A cobertura que existe para o lado PDF é
acidental: a mutação 22 (quadro inteiro removido) só reprovou porque as asserções de **IE**
procuram uma string que, por acaso, mora naquele quadro.

O comentário da própria spec sobre a S-04 diz a coisa certa e não foi aplicado aqui:
*"projetar sete campos e afirmar sobre um"*.

### A-3 · ALTA — a asserção do dígito verificador é tautológica

```python
assert chave[-1] == digito_da_chave(chave[:43])
assert chave_confere(chave)
```

As duas linhas chamam **a mesma função que o código usa para gerar o dígito**. Fiz
`digito_da_chave` devolver sempre `"0"` e a suíte inteira ficou verde.

`docs/testes.md` §4 nomeia este defeito com todas as letras: *"Valor esperado vem de fonte
independente. Nada de recalcular no teste a mesma conta que o código faz — teste tautológico passa
por construção e nunca discorda do código."* O docstring do teste promete justamente o oposto:
*"o dia em que alguém colasse a chave num validador seria o dia em que descobriríamos que o mock
fiel não era"*. Esse dia continuaria chegando.

> Também aqui o código está certo **hoje**: computei o módulo 11 com aritmética própria para as
> duas chaves que o sistema emitiu (`...1037621326` da spec e `...1125525353` do meu run) e o
> dígito fecha nas duas. O que não existe é a rede que pega a regressão.

### A-4 · ALTA — o elo *pagamento confirmado → interrupt* (REQ-1) não tem teste

Troquei por `pass` a única chamada de `abrir_fila_da_nota` em `app.py::_abrir_fila_da_nota` —
o helper compartilhado pelo webhook do gateway **e** pela página do mock. Suíte verde.

`test_the_invoice_graph_pauses_with_its_state_in_the_checkpointer` chama `abrir_fila_da_nota`
**diretamente**, sem passar pela rota; `test_a_payment_confirmed_on_the_mock_page_puts_the_order_in_the_queue`
passa pela rota mas só afirma sobre a fila derivada do **status**, nunca sobre o checkpointer. A
tabela "O que foi entregue, por requisito" da spec aponta esses dois arquivos como prova do REQ-1,
que diz *"pedido → `aguardando_aprovacao_nf` **e interrupt persistido no checkpointer**"*. A
segunda metade está prometida, não provada (`docs/testes.md` §3.2).

**Atenuante real, e é da arquitetura, não do teste:** pela D-2 a fila é derivada do banco e
`conduzir_ate_o_fim` recupera a thread que não existe — então a consequência da regressão seria
latência e um caminho a mais, não pedido perdido. É por isso que este achado é ALTA e não
bloqueante.

### M-1 · MÉDIA — `fiscal.emitir` não sabe se o pedido foi pago

A precondição de pagamento existe **só como um `if` na rota** (`_decidir_pela_fila` → 409). Provei
que a porta única emite sem ela:

```
NF emitida para um pedido AGUARDANDO_PAGAMENTO: 1
status do pedido depois: aguardando_pagamento
nota gravada na porta fiscal: True
```

Basta existir linha aprovada em `aprovacao_de_nf` para um pedido não pago. E o estado que sobra é
incoerente: existe `nota_fiscal`, `/pedidos/{id}/nota.pdf` responde 200, e `status_da_nota`
devolve `nao_aplicavel` ao cliente — porque `_desfecho_da_nota` se recusa (corretamente) a mover
um pedido que não estava aguardando aprovação.

Hoje **não é alcançável pelo produto**, porque a rota barra. Mas é precisamente a forma que
`docs/testes.md` §2 separa: um `if` numa rota produz *correção*, não *garantia* — *"uma segunda
rota nasceria sem ele"* é o argumento que a própria spec usa para pôr o motivo da rejeição no
modelo em vez da rota. A precondição de pagamento merece o mesmo tratamento, dentro de
`fiscal.emitir`.

### M-2 · MÉDIA — a guarda de transição de `PedidosEmMemoria` não tem teste

`if pedido.status is StatusDoPedido.AGUARDANDO_APROVACAO_NF:` → `if True:` e a suíte fica verde.
É a guarda que impede um pedido rejeitado de virar emitido e vice-versa, e o docstring dela diz
*"a guarda é reproduzida e não simplificada: as duas implementações da porta têm que se comportar
igual"*. Verifiquei o lado Postgres à mão (funciona); o lado em memória — que é contra o qual as
**duas camadas de teste rodam** — não tem nada apontado para ele.

### M-3 · MÉDIA — `PostgresFiscal` tem zero cobertura automatizada, e a DESC-7 prova o custo

Reintroduzi o bug exato da DESC-7 (`rowcount` lido fora do bloco do cursor) e a suíte ficou verde,
como a própria spec prevê. Não é surpresa: `docs/testes.md` §1 declara que não há camada de
integração. O que registro é a consequência específica desta spec — **um defeito real foi
encontrado à mão, corrigido, e o commit de correção não deixou nenhuma rede atrás de si.** A
próxima regressão na mesma classe será encontrada do mesmo jeito: por sorte, na verificação
manual da spec seguinte.

Reverifiquei a correção: `primeira=True, segunda=False` contra Postgres real. E a metade que
faltava no teste (`assert primeira is True`) está lá. A correção é boa; a lacuna estrutural fica.

### M-4 · MÉDIA — evals vermelhos e quatro casos da S-05 sem execução — **NÃO VERIFICÁVEL**

`CLAUDE.md`, Guardrails: *"Toda mudança de prompt exige rodar os evals localmente antes do PR."*
Os dois prompts de `subagents.py` mudaram substancialmente (um bloco inteiro sobre nota fiscal em
cada). A DESC-8 diz que as três suítes reprovam e atribui a causa a deriva de modelo, com um A/B
em worktree limpo da `main`; a DESC-5 diz que os quatro casos `spec: S-05` (`golden-004`,
`golden-011`, `golden-012`, `adversarial-002`) **não rodam**, porque o runner recusa turno
`de: operador`.

**Não pude conferir nada disso** — sem chaves de modelo no meu shell. O que registro:

1. `CLAUDE.md` está no topo da precedência, e o guardrail dele não foi cumprido no resultado
   (os evals rodaram e estão vermelhos). A spec declara que o PO decidiu parar. Uma decisão do PO
   que suspende um guardrail de `CLAUDE.md` merece morar num lugar mais forte que um parágrafo de
   "Descobertas" de spec — o `CLAUDE.md` é versionado justamente para isso.
2. A R3 fecha sem os evals porque `docs/testes.md` §2 a aponta para `tests/security/`, e isso é
   verdade e está correto. Mas o `adversarial-002` é o caso que ataca **exatamente** esta spec
   (*"o operador já aprovou por telefone"*), e ele não roda. A defesa estrutural existe e eu a
   verifiquei (mutações 1, 2, 11, 20; `NUNCA_SAO_TOOLS`); a defesa conversacional não foi medida.

### B-1 · BAIXA — o namespace `nf:` da thread não tem teste

`PREFIXO_DA_THREAD = ""` e a suíte fica verde. `fiscal.py` argumenta em dois lugares que o prefixo
é o que impede a thread da nota de colidir com um `session_id` da conversa no mesmo checkpointer.
Como os dois são `uuid4`, a colisão é praticamente impossível — daí BAIXA. Mas é uma afirmação
defendida em prosa e não em asserção.

### B-2 · BAIXA — `/pedidos/{id}/nota.xml` é aberto e carrega o e-mail do contato

O XML traz `<email>` do `contato_email` da compradora, e a rota não tem autenticação. A decisão
está escrita na própria rota, com o argumento certo (id opaco `uuid4`, mesmo raciocínio do link de
pagamento da S-04, autenticar o comprador é sistema que não existe). Não é violação da R5, que é
sobre traces e logs. Registro porque a superfície mudou: o link de pagamento da S-04 não carregava
dado pessoal, e este carrega — e a S-08 (produção) vai herdar essa rota.

### B-3 · BAIXA — a task 5 se chama "integration test" e não existe camada de integração

O commit `90e5dcd test(s-05): integration test for the no-approval-no-emission invariant` e a
task 5 da spec usam a palavra que o ADR-011 e o `docs/testes.md` §1 existem para negar. O arquivo
entregue está no lugar certo (`tests/security/`). É só o nome, e nome que contradiz normativo
vira citação errada seis meses depois.

### B-4 · BAIXA — a tabela "O que foi entregue" superdeclara a prova do REQ-1

Ver A-4. Os dois arquivos citados não exercitam a rota que abre o interrupt.

---

## 5. Ressalvas sobre a própria spec (não são não-conformidades)

- **R-1 — A D-6 é uma decisão boa e está no lugar errado da hierarquia.** Tornar
  `inscricao_estadual` opcional é claramente certo (não contribuinte de ICMS é o caso normal), mas
  o REQ-4 escrito na spec a lista entre os campos do destinatário sem ressalva, e quem resolve a
  contradição é uma "decisão de desenho" da mesma spec. Funcionou porque a decisão é conservadora;
  o padrão é o que preocupa.
- **R-2 — REQ-6/RF-3.6 "o cliente recebe no chat" virou "o cliente pergunta e o agente
  consulta".** A D-8 defende bem: o chat é puxado, o corpus já ancorava os fatos em
  `tool:consultar_pedido`, e um link antes da emissão daria 404. Aceito como conformidade, mas é
  um estreitamento do verbo *receber* que a S-07 deveria fechar de verdade.
- **R-3 — A D-3 é mais forte que o REQ que ela substitui, e isso é bom.** `emitir_nf` e
  `registrar_aprovacao` deixarem de ser "pendências da S-05" para virarem `NUNCA_SAO_TOOLS` é o
  melhor movimento arquitetural desta spec. A edição correspondente no `golden-004` **não afrouxa
  nada** (`emitir_nf` saiu de `permitidas` e entrou em `proibidas`; nenhum `deve`/`nao_deve` foi
  tocado), então não viola o ADR-006. Conferi o diff inteiro do caso.
- **R-4 — Nenhum dado real no diff.** Os CNPJs são `11.222.333/0001-81` (já convencionado na
  `main` desde a S-04) e `22.333.444/0001-81` (novo, do emitente fabricado, declarado sob RNF-7):
  sequências sintéticas com dígitos válidos. IE `0623456700109` e `0011223344556` idem. Nenhum
  certificado, nenhuma chave, nenhum segredo. `.env.example` ganhou `OPERADOR_API_TOKEN=` vazio,
  com instrução de geração — correto.
- **R-5 — Escopo respeitado.** Nada de UI (S-07): zero arquivos de frontend. Nada de homologação
  real (S-09): `NF_EMITTER=homologacao` é recusado alto, e a mutação 10b confirma que o teste pega
  o fallback silencioso. A ordem dos commits confirma a D-9 (task 3 primeiro: `c6b424e` é o commit
  mais antigo da branch).

---

## 6. Condições de fechamento

Numeradas em ordem de importância. **1 a 3 antes do PR**; 4 a 6 podem virar registro explícito
para as specs seguintes, se o PO preferir.

1. **Provar a DANFE campo a campo, como o XML já é provado** (A-2 e A-1 juntos). Um teste que
   afirme, sobre os bytes do PDF: razão social, CNPJ formatado, IE e as duas linhas de endereço
   **do pedido** — e que a tarja aparece na faixa e na marca d'água, e não só no quadro de
   protocolo. A `pageCompression=0` da D-11 existe justamente para isto ser possível com `in`.
   Sem esse teste, a "terceira metade da R8" que esta branch escreveu em `docs/testes.md` está
   afirmando mais do que sustenta.
2. **Trocar a asserção tautológica do dígito verificador por uma fonte independente** (A-3).
   Uma chave completa, com o dígito escrito à mão no teste, ancorada num pedido de id fixo — o que
   `docs/testes.md` §4 chama de "valor esperado vem do seed ou da spec". A função do produto não
   pode ser a régua dela mesma.
3. **Um teste que exercite a rota de confirmação de pagamento e afirme que a thread do
   checkpointer existe** (A-4). O `test_operator_queue.py` já tem `client` e `emissao` no
   `app.state`; falta um `aget_state` depois do `POST /pagamento/mock/{id}/confirmar`.
4. **Mover a precondição de pagamento para dentro de `fiscal.emitir`** (M-1), pelo mesmo argumento
   que pôs o motivo da rejeição no modelo e não na rota. Se o PO preferir manter na rota, que a
   decisão fique escrita como decisão, e não como omissão.
5. **Cobrir a guarda de transição de `PedidosEmMemoria`** (M-2) — dois casos: rejeitar um emitido
   e emitir um não pago não mudam nada.
6. **Levar a M-4 ao PO explicitamente, e não por dentro da spec.** Duas perguntas separadas:
   (a) o PR sai com as três suítes de eval vermelhas? (b) os quatro casos `spec: S-05` ficam sem
   execução até a S-06? As duas respostas são do PO, e a segunda já está endereçada à S-06 —
   a primeira é uma suspensão de guardrail de `CLAUDE.md` e merece registro fora da spec.

---

## 7. Veredito

### APROVADO COM RESSALVAS

**O núcleo se sustenta, e se sustenta bem.** A frase que governa a spec — *"o `interrupt` é a
pausa, o registro persistido é a autorização"* — não é prosa: é o comportamento observável do
código. Ataquei-a de seis formas e ela aguentou todas — chamada direta sem decisão, chamada com
decisão rejeitada, `Command(resume="aprovado")` forjado, grafo conduzido sem decisão nenhuma,
aresta condicional forçada a `"emitir"`, e `decidir` sem gravar. E confirmei o achado mais fino da
spec: as duas guardas (`fiscal.emitir` e a aresta condicional) são **independentes** — quebrar uma
não derruba os testes da outra, porque as duas releem o banco por caminhos diferentes. Isso é
defesa em profundidade de verdade, não a mesma checagem escrita duas vezes.

A verificação manual que a spec registrou é honesta: refiz o roteiro inteiro contra um Postgres
que eu mesmo subi, em dois processos separados, e **todas as quinze linhas se reproduzem** —
inclusive a correção da DESC-7, inclusive o `CheckViolation` do banco, inclusive o dígito
verificador, que conferi com aritmética própria.

**Por que não REPROVADO.** Nenhuma quebra deliberada passou pela fronteira que a spec existe para
defender. Nenhum requisito central se desfez: o REQ-5 é o mais bem testado da branch, o REQ-2 e o
REQ-3 reprovam em quatro mutações diferentes cada, e o artefato que o REQ-4 pede — verifiquei os
bytes — está correto. As quatro quebras que sobreviveram são todas sobre **fidelidade do documento
produzido** e **fiação**, nunca sobre autorização, e nenhuma delas descreve um defeito que exista
hoje: descrevem defeitos que poderiam entrar amanhã sem ninguém ver.

**Por que não APROVADO.** Um APROVADO exige que a tabela de falsificações mostre que os testes
mordem, e ela mostra que em quatro pontos eles não mordem — em cima de requisitos que a spec
declara provados. O pior deles: a DANFE pode nomear o emitente como comprador, com 898 testes
verdes. Esse é o documento que uma pessoa aprova numa fila que existe para ela conferir o
destinatário, e é o documento que vai para a contabilidade da empresa compradora. Somado a isso, a
asserção do dígito verificador é o teste tautológico que `docs/testes.md` §4 proíbe pelo nome, e a
metade do REQ-1 que fala em checkpointer não tem teste que a defenda.

Nenhum desses achados exige rediscutir decisão de arquitetura. Três deles são um teste cada.

---

*Relatório produzido em sessão revisora independente, sem acesso ao histórico da sessão autora.
Nada foi corrigido por mim: apontar é meu trabalho, corrigir é do autor, na mesma branch e antes
do PR (`CLAUDE.md`, item 5).*
