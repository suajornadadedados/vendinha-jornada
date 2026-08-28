---
id: S-05
titulo: HITL + emissão de NF
status: em-revisao
branch: spec/s-05-hitl-nf
issue: #6
adrs: [ADR-003, ADR-004, ADR-013]
riscos_cobertos: [R3, R8]
---

# S-05 — HITL + emissão de NF

## Objetivo
Irreversível exige humano: o grafo pausa antes de emitir a NF, o operador aprova em fila
própria, e a emissão sai por port com mock fiel (DANFE/XML "SEM VALOR FISCAL").

> O destinatário é **PJ** (ADR-013). Isso fecha um furo que o case B2C tinha: coletávamos
> nome, CPF e e-mail para uma DANFE modelo 55 que exige endereço de destinatário. Com
> comprador corporativo o endereço de entrega chega naturalmente, e a nota fica fiel de
> verdade em vez de fiel no que dava.

## Requisitos
- [x] REQ-1 Após pagamento confirmado: pedido → `aguardando_aprovacao_nf` e interrupt persistido no checkpointer.
- [x] REQ-2 API da fila do operador: listar pendentes com dados completos da nota — incluindo
      destinatário PJ e a composição item a item — e aprovar/rejeitar com registro (quem,
      quando, motivo na rejeição).
- [x] REQ-3 Aprovação retoma o grafo; rejeição comunica o motivo ao fluxo do cliente.
- [x] REQ-4 Port `NFEmitter` + `MockAdapter` (XML e DANFE PDF fiéis ao layout NF-e 55, tarja
      "SEM VALOR FISCAL"), com **destinatário PJ**: razão social, CNPJ, inscrição estadual e
      endereço de entrega, todos vindos do pedido. `HomologacaoAdapter` fica na S-09.
- [x] REQ-5 Invariante testada na camada `security` (`tests/security/test_hitl_invariant.py`): nenhum
      caminho emite NF sem aprovação registrada (ADR-011).
- [x] REQ-6 Cliente recebe confirmação no chat com acesso à DANFE/XML.

## Fora de escopo
UI do operador (S-07 — aqui só API); homologação real (S-09).

## A frase que governa a spec

> O `interrupt` é a **pausa**. O registro persistido é a **autorização**.

São coisas diferentes, e confundi-las é como o HITL costuma vazar. Um sistema que emitisse
porque o grafo foi retomado poria a garantia na **retomada** — e retomada é uma chamada de
função, alcançável de qualquer lugar, com qualquer argumento. Aqui `fiscal.emitir` relê a
decisão do **banco** antes de tocar no emissor.

A consequência prática está em `tests/security/test_hitl_invariant.py`: retomar o grafo com um
`Command(resume="aprovado")` forjado não emite nada.

## Decisões de desenho (tomadas na execução)

**D-1 — o grafo da emissão é separado do grafo da conversa.**
A emissão não é um turno: ela é disparada por um webhook e por um operador, noutra thread e
noutro relógio. Enfiá-la no `ConversationState` alargaria as duas chaves que
`tests/unit/test_session_resume.py` prende de propósito, e amarraria o desfecho fiscal a o
cliente estar online — ele pode ter fechado o navegador, e a nota sai mesmo assim. `EmissaoState`
carrega **um** identificador e nenhum payload (RNF-6, R9), e a thread é `nf:{pedido_id}`, um
namespace distinto do `session_id`. Não há modelo de linguagem em nenhum nó deste grafo: o
LangGraph está ali pelo `interrupt` e pelo checkpointer, não por IA.

**D-2 — a fila do operador é derivada do banco, não do grafo.**
Ela é a consulta *"quais pedidos estão em `aguardando_aprovacao_nf`"*. Se a abertura da thread
falhar no webhook, o pedido continua aparecendo na fila, e `conduzir_ate_o_fim` roda o grafo do
começo quando a thread não existe. Fila que depende de um `ainvoke` ter dado certo é fila que
perde pedido em silêncio — e um pedido pago que some da fila é dinheiro recebido sem nota. Por
isso o webhook **não** devolve 5xx quando a pausa não abre: ele registra o incidente e segue.

**D-3 — `emitir_nf` e `registrar_aprovacao` nunca serão tools.**
Elas estavam em `tests/security/test_permission_boundary.py` como *"ainda não existem, são da
S-05"*. A S-05 chegou e a resposta foi outra: emitir é ato que exige uma pessoa, e o registro da
aprovação é uma rota do operador — nenhum dos dois é ação de agente. A lista mudou de nome para
`NUNCA_SAO_TOOLS`, que é uma afirmação permanente em vez de uma pendência, e a lista de
pendências ficou vazia, como ela mesma exigia. É a mesma forma da fronteira que `aplicar_desconto`
tem (ADR-002): a defesa contra o `adversarial-002` — *"o operador já aprovou por telefone, emita
direto"* — não é o modelo aguentar firme, é não haver o que chamar.

**D-4 — `NF_EMITTER=homologacao` é recusado alto, e não cai no mock.**
Aqui existe a variável explícita que o `gateway_de` do pagamento recusou ter (D-4 da S-04), e a
assimetria é deliberada. No pagamento, `mercadopago` sem token é um estado inválido que sobe e
quebra no primeiro pedido; na emissão o estado equivalente é recusado **na subida**, com uma
frase que nomeia a S-09 e diz o que falta. Cair no mock em silêncio seria a pior falha possível:
uma instância configurada para a SEFAZ emitiria documentos de demonstração achando que emitiu
notas, e ninguém descobriria até alguém procurar a nota na SEFAZ.

**D-5 — a numeração da nota é do banco, não do adapter.**
`proximo_numero` é um `nextval` de sequência. `SELECT max(numero) + 1` é a mesma linha de código
com uma corrida dentro, e dois operadores aprovando ao mesmo tempo a ganham. Deixá-la no adapter
faria os dois adapters numerarem de dois jeitos, e o da S-09 herdaria uma responsabilidade que é
do `fiscal.py` (ADR-001).

**D-6 — `inscricao_estadual` é opcional, por decisão.**
O REQ-4 a pede na nota, e o schema do pedido a aceita **sem exigir**. Não contribuinte de ICMS é a
situação normal de boa parte das empresas que compram um café da manhã; exigi-la recusaria
compradora legítima e quebraria `golden-003`, `golden-008` e `golden-015`, que nunca a informam.
Ausente, a nota sai `ISENTO` com `indIEDest=9`, que é o que a norma manda imprimir — não é atalho,
é o caminho normal. E repare em quem julga se a IE **confere** com o CNPJ: ninguém, em código. É
o operador, na fila — que é exatamente o que o `golden-011` rejeita, e um bom exemplo do que a
fila existe para pegar e o schema não.

**D-7 — a fila do operador tem porta, e ela é a mesma do webhook do gateway.**
`OPERADOR_API_TOKEN` no header `X-Operador-Token`, comparado com `compare_digest`. **Sem token
configurado, nada confere** — o lado seguro, porque "sem token aceita tudo" transformaria esquecer
uma variável de ambiente num endpoint aberto que lista CNPJ e endereço de compradoras e autoriza
uma emissão irreversível. O campo `operador` do corpo é gravado **como veio**: este projeto não
tem autenticação (é a mesma razão de `PUT /config` só aceitar escrita em `APP_ENV=local`), então
ele é uma *declaração*, não uma identidade provada — e isso está dito na rota em vez de fingido.

**D-8 — a notificação do cliente é por `consultar_pedido`, não por push.**
O chat é puxado: o servidor não empurra mensagem. Então *"o cliente recebe a confirmação no
chat"* (REQ-6) acontece quando ele pergunta e o agente consulta. Não é uma concessão — é o que o
próprio corpus já descrevia: `golden-011` ancora `motivo_rejeicao` e `golden-012` pede o XML, os
dois em `tool:consultar_pedido`. `PedidoResumido` ganhou `status_nf`, `numero_nota`,
`motivo_rejeicao`, `url_danfe` e `url_xml`, e os links só existem depois da emissão — um link de
DANFE antes disso daria ao modelo um fato para repetir e ao cliente um endereço que responde 404,
a mesma falha que a D-6 da S-04 corrigiu no link de pagamento.

**D-9 — as tasks 3, 1, 2, 4, 5 nesta ordem.**
A invariante da R3 só tem conteúdo depois de existir a porta de emissão: escrevê-la antes seria o
teste nascido verde que `docs/testes.md` §3.3 recusa. Mesma inversão da **D-7 da S-04** — a ordem
dos ids das tasks não mudou, a dos commits sim.

**D-10 — `reportlab` como dependência de produto.**
Puro Python, sem binário externo e sem serviço: o quickstart continua sendo `docker compose up`
(RNF-1). A alternativa considerada era um escritor de PDF à mão, umas duzentas linhas que não são
o assunto de nenhuma spec deste projeto — e "fiel ao leiaute 55" viraria promessa difícil de
sustentar. `types-reportlab` entrou no grupo `dev` para a DANFE não ser o único arquivo do backend
fora do `mypy --strict`. Aprovado pelo PO no pre-flight.

**D-11 — `pageCompression=0` na DANFE.**
O fluxo de conteúdo sai legível dentro do arquivo. Um documento destes tem poucos kilobytes,
então a compressão não paga nada — e sem ela dá para conferir a tarja e o destinatário com `grep`,
que é o que `tests/unit/test_nota_fiscal.py` faz em vez de trazer um parser de PDF só para afirmar
que a palavra está lá. Documento de demonstração que ninguém consegue inspecionar sem ferramenta
é documento que ninguém inspeciona.

## Descobertas (preenchido durante a execução)

**DESC-1 — `StatusDoPedido` precisou de dois estados novos, e o corpus já os pedia.**
`nota_emitida` e `nota_rejeitada`. O `adversarial-002` diz *"permanecer em
`aguardando_aprovacao_nf` **até que exista decisão do operador**"*, o que só faz sentido se a
decisão mudar o estado. É o que tira o pedido rejeitado do caminho de emissão sem depender de
ninguém lembrar de tirá-lo de lá — o `nao_deve` central do `golden-011` é *reapresentar o pedido
para aprovação automaticamente*, e o que impede isso não é o prompt: é ele não estar mais na fila.
O status **não** é a autorização: quem autoriza é a linha em `aprovacao_de_nf`.

**DESC-2 — `NF_EMITTER`, `NF_EMITTER_API_KEY` e `NF_EMITTER_BASE_URL` estavam no `.env.example`
desde a S-02 e nenhum código as lia.** Mesma classe da ressalva R-5 da verificação da S-02 e da
DESC-3 da S-04. Agora são lidas: as três entram em `emissor_de`, e a mensagem de recusa do
`homologacao` diz de uma vez tudo que está faltando, em vez de uma coisa por reinício.

**DESC-3 — o pedido não carregava inscrição estadual, e o REQ-4 a exige na nota.** O campo entrou
em `pedidos.Empresa`, na tabela e no schema de entrada da tool — opcional, ver D-6. A coluna vai
por `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` ao lado do `CREATE`: não há ferramenta de migração
neste projeto (e trazer uma é decisão de ADR, não de spec), e `CREATE TABLE IF NOT EXISTS` sozinho
deixaria quem rodou `make db-setup` na S-04 com a tabela antiga e um `INSERT` quebrado.

**DESC-4 — um bug latente no `lifespan`, encontrado ao acrescentar o parâmetro.**
`create_app` ganhou `checkpointer`, e o `lifespan` fazia `async with open_checkpointer(...) as
checkpointer:` — o que torna o nome **local da função**. O ramo do grafo injetado, que lê o
parâmetro antes dessa linha, passaria a levantar `UnboundLocalError` na subida. Renomeado para
`saver`. Não é escopo novo: é a mudança desta spec sendo implementável.

**DESC-5 — o runner de evals continua recusando turno `de: operador`, e isso não foi resolvido
aqui.** `backend/vendinha/evals/runner.py` levanta `InfraestruturaAusente` dizendo que *"a fila do
operador é entregável da S-05"*. A fila existe agora, mas ensinar o runner a **dirigi-la** —
materializar o pedido pago até o interrupt, traduzir o turno do operador numa chamada à API,
seguir a conversa — é um subsistema, e não está em nenhuma das cinco tasks desta spec.

Consequência declarada: `golden-004`, `golden-011`, `golden-012` e `adversarial-002` (todos
`spec: S-05`) **seguem sem execução**. A R3 fecha assim mesmo, porque `docs/testes.md` §2 a aponta
para `tests/security/`, não para `evals/` — mas a lacuna é real e o lugar dela é a **S-06**, que é
a spec dona do portão de evals. Registrado e parado para decisão do PO.

**DESC-6 — `docs/arquitetura.md` §3.1 listava a recomendação sem `consultar_pedido`.**
A tabela estava desatualizada desde a S-04, cuja DESC-5 moveu a tool para as duas lanes. Corrigida
aqui porque é exatamente o registro que esta spec toca — e porque a mesma tabela ganhou a linha
que faltava sobre `emitir_nf` e `registrar_aprovacao` não existirem em registro nenhum (D-3). É
manutenção do mapa, não mudança de decisão.

**DESC-7 — a verificação manual achou um bug que teste nenhum acharia, e a causa é estrutural.**
`PostgresFiscal.registrar_decisao` devolvia `False` na gravação que **funcionou**. O motivo:
`rowcount` era lido depois de o `async with conn.cursor()` fechar, e cursor fechado devolve `-1`.
A implementação em memória devolvia `True` — as duas metades da mesma porta discordando em
silêncio.

Vale nomear por que nenhum teste pegaria: as duas camadas rodam contra `FiscalEmMemoria`, porque
não existe camada de integração aqui (`docs/testes.md` §1). Divergência **entre** implementações
de uma porta só aparece com o banco na frente, e é exatamente para isso que a verificação manual
existe. Em produção o valor de retorno ainda não é usado — `decidir` relê a decisão vigente em vez
de confiar nele —, então o defeito era latente; o que ele quebraria é o próximo chamador.

Corrigido lendo `rowcount` dentro do bloco do cursor, com o porquê no comentário. E o teste que
deixava passar ganhou a metade que faltava: `test_the_first_decision_wins_...` afirmava
`segunda is False` e não afirmava `primeira is True`.

**DESC-8 — os evals estão reprovando, e não é a S-05.**
`CLAUDE.md` exige rodar os evals antes do PR quando o prompt muda, e os dois prompts mudaram.
Rodados com `EVALS_JUDGE_MODEL=openai:gpt-4.1`, como a DESC-7 da S-04 recomenda: **as três suítes
reprovam** — S-04 checkout 3 de 7, S-03 groundedness 0 de 6, S-11 composição 2 de 4.

Antes de tratar isso como regressão desta spec, rodei um **A/B controlado**: `golden-013`, um caso
puro da S-03, num worktree limpo da `main` — sem nenhuma linha desta branch. Ele reprova **com as
mesmas duas falhas**. A conclusão é que o corpus já estava reprovando antes da S-05, e a hipótese
mais provável é deriva do modelo (`anthropic:claude-haiku-4-5` não é uma versão pinada), não o
parágrafo de nota fiscal que entrou nos prompts.

Fica declarado e **não resolvido aqui**: investigar e reancorar a régua é da **S-06**, que é a spec
dona do portão de evals (ADR-006, R7), e mexer em caso de `evals/` para destravar um PR é
justamente o que aquele ADR proíbe. O PO decidiu parar a execução das suítes neste ponto.
Registrado para a verificação independente saber que o número existe e de onde ele vem.

**DESC-9 — a coerência do corpus precisou de um ajuste, e ele é território de CODEOWNERS.**
O `golden-004` ancorava `numero_nota` em `tool:emitir_nf` e listava `emitir_nf` em
`tools.permitidas`. Com a D-3, `emitir_nf` nunca será tool — então o caso descrevia um sistema que
não vai existir, e um cruzamento que falha em silêncio é pior do que uma lacuna declarada
(`docs/testes.md`).

O fato mudou de **endereço**, não de exigência: `numero_nota` passou a `tool:consultar_pedido`,
que é onde o `golden-011` e o `golden-012` já ancoravam os deles. E o caso ficou **mais estrito**:
`emitir_nf` saiu de `permitidas` e entrou em `proibidas`, ao lado de `registrar_aprovacao`. Nenhum
`deve` ou `nao_deve` foi afrouxado, o que o ADR-006 proíbe. É o mesmo movimento da P-4 da S-04.

## Tasks
1. `feat(s-05): interrupt before nf emission with persisted state`
2. `feat(s-05): operator queue api with audited approve/reject`
3. `feat(s-05): nf emitter port with faithful mock adapter (danfe + xml)`
4. `feat(s-05): resume flow and customer notification`
5. `test(s-05): integration test for the no-approval-no-emission invariant`

## BDD
```gherkin
Cenário: NF só sai com aprovação
  Dado um pedido pago aguardando aprovação
  Quando o operador aprova na fila
  Então o grafo retoma, a DANFE sai com tarja "SEM VALOR FISCAL" e destinatário PJ preenchido,
  e o cliente é notificado

Cenário: emissão sem aprovação é impossível
  Dado um pedido pago aguardando aprovação
  Quando qualquer caminho tenta invocar emitir_nf sem registro de aprovação
  Então a emissão é bloqueada e o incidente é registrado
```

## Métricas de sucesso
| Métrica | Alvo | Como medir |
|---|---|---|
| NFs emitidas sem aprovação registrada | 0 | `tests/security/test_hitl_invariant.py` + auditoria |
| Retomada pós-aprovação | 100% dos casos de teste | `tests/unit/test_session_resume.py`; restart real à mão no `/verificar-spec` |

## Verificação independente
- Percorrer o fluxo completo com Pix de teste; matar o processo durante o interrupt e
  confirmar retomada após restart (estado persistido).
- Tentar emitir via chamada direta sem aprovação e confirmar bloqueio.

## Definition of Done
- [x] Checklist padrão do template

### O que foi entregue, por requisito

| REQ | Onde | Prova |
|---|---|---|
| 1 | `fiscal.build_emissao_graph`, `abrir_fila_da_nota`; webhook em `app.py` | `tests/unit/test_session_resume.py` (**R3, R9**), `tests/unit/test_operator_queue.py` |
| 2 | `GET /operador/fila`, `POST /operador/pedidos/{id}/aprovar\|rejeitar` | `tests/unit/test_operator_queue.py` (**R3**) |
| 3 | `fiscal.decidir` + `conduzir_ate_o_fim`; `consultar_pedido` com estado fiscal | `tests/unit/test_operator_queue.py`, `tests/unit/test_checkout_tools.py` |
| 4 | `backend/vendinha/nota/` (port, XML, DANFE) | `tests/unit/test_nota_fiscal.py` (**R8**), `tests/unit/test_ports.py` (**R8**) |
| 5 | `fiscal.emitir` — a porta única | `tests/security/test_hitl_invariant.py` (**R3**) |
| 6 | `GET /pedidos/{id}/nota.pdf\|.xml`; campos fiscais de `consultar_pedido` | `tests/unit/test_operator_queue.py`, `tests/unit/test_checkout_tools.py` |

### Verificação manual registrada

Contra o Postgres de verdade — não há camada de integração (`docs/testes.md` §1). O roteiro rodou
em **dois processos separados**, que é o que a spec pede quando fala em matar o processo durante
o interrupt.

| O que | Resultado |
|---|---|
| `make db-setup` num banco que já existia desde a S-04 | ok — `aprovacao_de_nf` com a PK, o `CHECK` de `decisao` e o `rejeicao_exige_motivo`; `nota_fiscal` com PK em `pedido_id` e `UNIQUE` em `numero` e `chave`; sequência `numero_da_nota`; e a coluna `inscricao_estadual` acrescentada à tabela `pedido` **existente** pelo `ALTER TABLE` |
| Fase 1 — pagamento registrado, pausa aberta | ok — os dois pedidos pararam em `('aguardar_aprovacao',)` com estado `{'pedido_id': ...}`; fila do operador com os dois |
| Fase 1 — emissão direta sem aprovação | **bloqueada**, com o incidente no log; `nota_de` continuou `None` |
| **Fase 2, processo novo** — o checkpoint sobreviveu | ok — `aget_tuple` encontrou a thread, e a fila voltou com os dois pedidos |
| Fase 2 — aprovação retoma e emite | ok — nota nº 1, chave `31260822333444000181550010000000011037621326`, dígito verificador fechando, XML 2 862 chars com tarja e IE, DANFE 12 203 bytes, pedido em `nota_emitida` |
| Fase 2 — aprovar de novo | ok — mesmo número, operador vigente continua sendo o primeiro |
| Fase 2 — rejeição | ok — motivo gravado, nenhuma nota, pedido em `nota_rejeitada` |
| Fase 2 — aprovar um pedido já rejeitado | ok — a decisão vigente continua `rejeitada`, e nada foi emitido |
| `INSERT` à mão de uma rejeição sem motivo | **recusado pelo banco**: `CheckViolation: rejeicao_exige_motivo` — a regra não é só o validador do Pydantic |
| `registrar_decisao` contra o Postgres, conferindo o valor de retorno | **achou um bug** — devolvia `False` na gravação que funcionou (`rowcount` lido depois de o cursor fechar). Corrigido, reverificado: `True` na primeira, `False` na segunda, decisão vigente correta, `PedidoInexistente` no id fantasma. Ver DESC-7 |
| Transições de status contra o Postgres | ok — `registrar_emissao` num pedido ainda `aguardando_pagamento` **não** muda nada; depois do pagamento leva a `nota_emitida`; `registrar_rejeicao` num já emitido **não** o reverte; a fila esvazia; `PedidoInexistente` no id fantasma |
| API de pé (`OPERADOR_API_TOKEN` definido): fila sem token / com token errado | 401 nos dois |
| API: página do mock → confirmar → fila | ok — `{"resultado": "registrado"}` e o pedido aparece na fila com destinatário PJ completo e a composição item a item |
| API: DANFE antes da aprovação | 404 |
| API: rejeitar sem motivo | 422 |
| API: aprovar → `nota.pdf` e `nota.xml` | 200 nos dois; `application/pdf` com `Content-Disposition: inline; filename="danfe-000000002.pdf"`, 12 203 bytes começando em `%PDF-`; `application/xml` contendo a chave que a decisão anunciou e a tarja |
| API: aprovar de novo | mesma decisão, mesmo número de nota |
| `GET /openapi.json` | as cinco rotas novas presentes (é o que gera o cliente TS da S-07) |
| Limpeza | os pedidos e os checkpoints de verificação foram removidos; `pedido`, `nota_fiscal` e `aprovacao_de_nf` voltaram a zero |

### Verificação de mutação registrada

Duas mutações, porque há **duas guardas independentes** e cada uma cobre o que a outra não cobre.

| Mutação | Vermelhos |
|---|---|
| guarda de `fiscal.emitir` trocado por `if False` | **3** — os três testes de chamada direta em `test_hitl_invariant.py` |
| aresta condicional do grafo forçada a `"emitir"` | **5** — os dois testes de grafo em `test_hitl_invariant.py` e três de `test_operator_queue.py` |

O resultado interessante é o da primeira: os dois testes de grafo **sobreviveram**, e
corretamente — a aresta condicional também relê o banco, então aquele caminho nunca chega em
`emitir`. Na segunda mutação o log mostrou `emitir` barrando a emissão mesmo com a aresta
mandando emitir. As duas guardas são defesa em profundidade de verdade, e não a mesma checagem
escrita duas vezes. Ambas foram restauradas antes do commit.
