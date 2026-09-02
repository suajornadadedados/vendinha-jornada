# Vendinha — Harness do projeto

## O que é este projeto
Agente de vendas end-to-end (empório mineiro digital vendendo **para empresas**): o cliente
descreve um evento corporativo — café da manhã, happy hour, cesta de fim de ano, kit de
boas-vindas — e o agente monta a composição via RAG, o **código valida** orçamento, slots e
restrições alimentares, e o fluxo segue até o link de pagamento (Mercado Pago sandbox) e a
emissão de NF-e para PJ com aprovação humana (HITL).
Construído como estudo de caso público de decisões de engenharia em projetos com IA.

## Regra de ouro (governa toda decisão de código)
> O LLM decide O QUE DIZER. O código decide O QUE PODE SER FEITO.
- Preço, total, quantidade, desconto, validação de dados: SEMPRE código/banco, NUNCA o modelo.
- Composição de evento: o modelo **propõe** os produtos, o código **valida e recusa**. Total,
  valor por pessoa, slots obrigatórios e corte por alérgeno (`contem`) são de código (R10).
- Side effects só existem como tools tipadas com permissão explícita por subagent.
- Emissão de NF exige aprovação humana registrada (interrupt do LangGraph). Sem exceção.

## Documentos normativos (ler antes de implementar qualquer spec)
- `docs/requisitos.md` — a tradução que fizemos do pedido do cliente; origem de tudo abaixo
- `docs/jornada.md` — onde a IA entra no fluxo e por quê
- `docs/riscos.md` — matriz R1-R10: risco → mitigação → spec → verificação
- `docs/testes.md` — risco → teste: onde cada verificação da matriz vive e o que faz um teste ser aceito
- `docs/decisoes.md` — mapa D1-D18 → ADRs
- `docs/PRD.md` — requisitos do produto
- `docs/specs/S-XX-*.md` — a spec em execução é a fonte da verdade da sessão

> **Ordem de execução ≠ ordem dos ids.** S-10 e S-11 (pivô B2B, ADR-013) rodam **entre a S-03
> e a S-04**. A nota no topo da S-10 explica por que renumerar sairia mais caro que um id
> fora de ordem.

## Fluxo de trabalho (SDD)
1. Cada spec tem uma issue no GitHub, linkada no frontmatter (`issue:`). A issue é **ponteiro**
   para a spec, nunca cópia: requisito e task vivem só na spec. Se as duas discordarem, a spec
   vence — duas fontes de verdade sobre "o que fazer agora" levam a escolher a errada.
2. Cada spec = uma branch `spec/s-XX-nome` a partir da `main` + uma sessão nova do Claude Code.
3. Cada task da spec = um commit (Conventional Commits, em inglês).
4. **Verificação independente ANTES do PR, não antes do merge.** Terminou a implementação, a
   sessão autora para e roda **`/fechar-spec S-XX`**, que dispara o subagente
   **`verificador-de-spec`** passando o id da spec — e nada além disso. Ele gera `docs/specs/relatorios/S-XX-verificacao.md`. Quem implementou já
   sabe que está certo: é esse saber que faz o revisor não olhar. O relatório é **arquivo, não
   comentário de PR** — o PR ainda não existe. Sem veredito, não existe PR.
   > O prompt do revisor vive em `.claude/agents/verificador-de-spec.md`, **versionado**. O autor
   > passa o id da spec e mais nada: instrução escrita à mão pelo autor não é verificação
   > independente, é o autor se avaliando com outra voz. Com o prompt no repositório, enviesar a
   > revisão passa a exigir um commit naquele arquivo — no diff, onde o PO vê.
   >
   > Subagente elimina o **contexto**; sessão nova elimina a **autoria**, e continua sendo o
   > portão mais forte. Vale usar quando o veredito vier bom demais: veredito sem nenhuma
   > ressalva mede o prompt antes de medir a entrega.
5. Corrigir o que a verificação apontou, **na mesma branch e antes do PR** — o PR nasce já com a
   correção dentro. Só então: PR para `main` usando o template, com `Closes #N` e evidência
   (screenshot + trace Langfuse), e o relatório anexado.
6. Merge por squash. A `main` é protegida; os checks do CI são obrigatórios. O squash fecha a issue.

## Convenções
- Python 3.12, FastAPI, LangGraph, Qdrant, Postgres, Langfuse. Frontend React (Vite).
- Código e comentários em inglês; documentação de produto em PT-BR.
- Contratos Pydantic em toda fronteira (rotas, tools, webhooks). Tipos do frontend gerados do OpenAPI.
- Estado do grafo: IDs, não payloads (pointer-not-payload).
- Commits: `feat|fix|test|docs|spec|adr|eval|ci|chore|refactor(escopo): mensagem`.
  Escopo obrigatório (`s-04`, `harness`, `deploy`) — a lista de tipos é a de `commitlint.config.cjs`.

## Guardrails da sessão
- NUNCA commitar secrets, certificados, CNPJ ou dados reais. `.env.example` é a referência.
- NUNCA implementar fora do escopo da spec ativa. Se descobrir necessidade nova: anotar na
  seção "Descobertas" da spec e parar para decisão do PO.
- Toda mudança de prompt exige rodar os evals localmente antes do PR (`make evals`).
- Ao terminar cada task: rodar lint + typecheck + testes antes do commit.
- Atualizar o status da spec (frontmatter) ao concluir.
- Toda spec é encerrada **exclusivamente** por `/fechar-spec`. Numa branch `spec/s-XX-*`, o hook
  `.claude/hooks/gate-pr.py` recusa `gh pr create` sem relatório de verificação aprovado — este
  guardrail é código, não pedido, e é a única linha daqui que não depende de você a ter lido.
