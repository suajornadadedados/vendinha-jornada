---
name: vendinha-harness
description: Roteia o trabalho da Vendinha para as skills certas e declara a precedencia dos documentos normativos do projeto sobre qualquer skill de terceiros. Use SEMPRE ao iniciar uma spec (S-00 a S-09), ao escolher entre as skills instaladas, e sempre que uma skill sugerir algo que pareca conflitar com a regra de ouro, com os ADRs ou com a matriz de riscos.
---

# Harness da Vendinha — roteamento e precedencia

Esta skill e propria do projeto (nao vendorizada). Ela existe porque skills de terceiros
trazem competencia **generica**: o que torna essa competencia **correta neste projeto** e a
precedencia declarada abaixo.

## Precedencia (nao negociavel)

Quando uma skill de terceiro sugerir algo que contradiga os normativos do projeto,
**o normativo vence**. Registre o conflito na secao "Descobertas" da spec ativa.

1. `CLAUDE.md` — regra de ouro: *o LLM decide o que dizer; o codigo decide o que pode ser feito*
2. `docs/requisitos.md` — a traducao que este projeto fez do pedido do cliente; e dela que
   riscos, PRD e ADRs derivam
3. `docs/riscos.md` — R1 a R9. Risco sem verificacao e desejo, nao requisito
4. `docs/testes.md` — risco -> teste: o seam de cada verificacao e o criterio de aceite
5. `docs/adr/` — decisoes aceitas, imutaveis (mudanca gera novo ADR)
6. `docs/specs/S-XX-*.md` — a spec ativa e a fonte da verdade da sessao
7. skills de terceiros — competencia tecnica, subordinada a tudo acima

## Conflitos ja conhecidos e resolvidos

Leia esta secao antes de aplicar qualquer skill de LangChain/LangGraph.

**`langchain-rag`** ensina a gerar a resposta a partir do contexto recuperado.
Aqui isso vale para *texto de conversa*, nunca para *fato de negocio*: atributo, preco,
disponibilidade e total **nao saem do texto recuperado**. Preco vem de consulta ao Postgres
por tool, no momento da criacao do pedido. Um unico fato inventado reprova a suite de evals
inteira e trava o release (R1, RF-1.3, ADR-001, ADR-006).

**`langgraph-human-in-the-loop`** trata `interrupt` como padrao opcional de UX.
Aqui e **obrigatorio** antes de `emitir_nf`, e nao basta pausar: a aprovacao precisa ser
**persistida com quem e quando**, e a retomada so pode ocorrer a partir desse registro.
E impossivel, por construcao, emitir NF sem aprovacao registrada — e isso e testado
em integracao (ADR-003, R3, RF-3.5).

**`langchain-middleware`** oferece aprovacao e allowlist como configuracao do agente.
Aqui a fronteira de permissao e **estrutural, nao configuracional**: o subagent de
recomendacao possui exclusivamente tools read-only, garantido por teste unitario que falha
se a fronteira vazar. `desconto` nao existe como acao disponivel a nenhum agente — nao e
negado, simplesmente nao existe (ADR-002, R2, R4, RF-2.6).

**`langgraph-persistence`** apresenta varias estrategias de estado.
Aqui a escolha ja esta feita: checkpointer em Postgres e **pointer-not-payload** — o estado
do grafo carrega identificadores, nunca payloads (RNF-6, R9).

**`tdd`** manda **perguntar ao usuario quais sao os seams** antes de escrever qualquer teste.
Aqui essa pergunta ja esta respondida: os seams sao a terceira coluna da tabela de
`docs/testes.md`, derivada da matriz de riscos. Nao reabra a negociacao a cada sessao. Seam que
falta na tabela e **descoberta**, nao improviso — registre e pare.

Outros tres pontos em que o projeto e mais estrito que a skill:

- o **commit continua sendo por task da spec**, nao por ciclo red-green. A `main` conta a
  historia em nivel de spec e a branch em nivel de task (ADR-005);
- todo teste **declara no docstring o R# que fecha**, para `/verificar-spec` cruzar risco e
  prova sem ler a implementacao;
- **R2** (fronteira de permissao vaza) e **R3** (emissao sem aprovacao registrada) nao sao
  cobertura, sao o requisito: nenhuma spec que os toque fecha sem esses testes verdes, e nao
  ha versao "minima" deles.

**`code-review`** cobre padroes de codigo; **`/verificar-spec`** cobre conformidade com a
spec e e o **gate**. Sao complementares: rodar `code-review` nao substitui a verificacao
independente em sessao nova.

**`eval-engineering`** propoe rubricas com dimensoes e thresholds numericos ajustaveis.
Aqui **nao existe arquivo de rubric**: o criterio de aprovacao vive dentro de cada caso em
`evals/`, e o caso passa ou reprova — sem nota agregada e sem media. Afrouxar um caso para
destravar um PR e violacao do ADR-006; `evals/` esta protegido por CODEOWNERS exatamente
por isso (R7).

**`langfuse`**: PII **mascarada na origem**. CPF, e-mail e nome nao podem aparecer legiveis
em trace nem em log, em nenhum ambiente (ADR-007, R5, RF-5.2). Desde o ADR-010 o Langfuse e
**Cloud**, e isso eleva a aposta: o trace sai da infra, entao o mascaramento deixou de ser
higiene e virou pre-condicao — e a instrumentacao **nunca propaga excecao** para o atendimento
se o Langfuse estiver indisponivel.

## Roteamento por spec

| Spec | Skills primarias | Normativos obrigatorios |
|---|---|---|
| S-00 Fundacao | — | ADR-005, ADR-008 |
| S-01 Discovery como codigo | `grill-with-docs`, `domain-modeling`, `writing-for-agents` | requisitos, PRD, jornada, riscos |
| S-02 Agente observavel | `langgraph-fundamentals`, `langgraph-persistence`, `langfuse`, `tdd` | ADR-001, ADR-007; R5, R6, R9 |
| S-03 Recomendacao ancorada | `langchain-rag`, `langfuse`, `tdd` | ADR-001; R1; RF-1.3 |
| S-04 Fronteira de pagamento | `langchain-middleware`, `codebase-design`, `tdd` | ADR-002, ADR-004; R2, R4, R8 |
| S-05 HITL e NF | `langgraph-human-in-the-loop`, `langgraph-persistence` | ADR-003; R3, R8 |
| S-06 Qualidade como gate | `eval-engineering`, `langfuse` | ADR-006; R7; RF-5.4 |
| S-07 Frontend integrado | `shadcn` + plugin `ui-ux-pro-max` | ADR-004 (OpenAPI -> cliente TS) |
| S-08 Producao | — | ADR-008; RNF-8, RNF-9 |
| S-09 Homologacao real (opcional) | `research` | ADR-004; RNF-7 |

Transversais, em qualquer spec: `diagnosing-bugs` (bug nao-deterministico),
`resolving-merge-conflicts` (specs paralelas tocam docs comuns), `handoff` (trocar de
sessao sem perder decisoes), `langchain-dependencies` (antes de qualquer import novo),
`ecosystem-primer` (so se a escolha de framework voltar a mesa — ja decidida).

## Skills que vivem como plugin, fora de .claude/skills/

Nao sao vendorizadas por conterem CLI e assets binarios. ADR-009: **vendoriza-se markdown,
nao se vendoriza software**. Estao documentadas em `docs/harness/skills.md`.

- **`ui-ux-pro-max`** — bases de estilos, paletas, tipografia, diretrizes de UX.
  Na S-07: use para **decidir** o sistema visual (paleta, tipografia, densidade, hierarquia).
  Depois use `shadcn` para **implementar** os componentes. Nesta ordem — decidir, entao
  implementar. Inverter produz componente bonito sem sistema.
- **`frontend-slides`** — apresentacoes HTML. Uso exclusivo em `docs/workshop/`.
  Nunca no produto.

Se o plugin nao estiver disponivel na maquina, siga com `shadcn` e registre a limitacao
em "Descobertas" — o plugin e conveniencia, nao dependencia.

## Antes de escrever qualquer codigo

1. Ler a spec ativa inteira, **incluindo "Fora de escopo"**.
2. Ler os normativos que a spec cita (ADRs e riscos listados no frontmatter).
3. Responder: quais riscos (R#) esta spec fecha, e **qual teste prova cada um**?
   A resposta nao e livre: `docs/testes.md` ja diz o tipo, o seam e o arquivo esperado de cada
   R#. Risco sem teste correspondente nao esta fechado — esta prometido.
4. Só entao implementar, task a task, um commit por task.

Descoberta fora do escopo -> registrar em "Descobertas" na spec e **parar** para decisao
do PO. Nao implementar, nem "ja que estamos aqui".

## Manutencao das skills

`.claude/skills/` e **derivado** de `.claude/skills.lock.json` (ADR-009). Nunca edite uma
skill vendorizada a mao: a alteracao seria perdida no proximo `vendor-skills.sh` e o job
`skills-drift` do CI reprova o PR. Para mudar algo:

- **trocar versao de origem** -> `bash scripts/pin-skills.sh` e revisar o diff
- **adicionar ou remover skill** -> editar `skills.lock.json` (campo `porque` obrigatorio)
  e rodar `bash scripts/vendor-skills.sh`
- **ajustar comportamento no contexto do projeto** -> editar **esta** skill, nunca a de
  terceiro. E para isso que a secao "Conflitos ja conhecidos" existe.
