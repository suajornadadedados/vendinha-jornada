# Vendinha — Harness do projeto

## O que é este projeto
Agente de vendas end-to-end (empório mineiro digital): recomendação via RAG, checkout com
link de pagamento (Mercado Pago sandbox) e emissão de NF-e com aprovação humana (HITL).
Construído como estudo de caso público de decisões de engenharia em projetos com IA.

## Regra de ouro (governa toda decisão de código)
> O LLM decide O QUE DIZER. O código decide O QUE PODE SER FEITO.
- Preço, total, desconto, validação de dados: SEMPRE código/banco, NUNCA o modelo.
- Side effects só existem como tools tipadas com permissão explícita por subagent.
- Emissão de NF exige aprovação humana registrada (interrupt do LangGraph). Sem exceção.

## Documentos normativos (ler antes de implementar qualquer spec)
- `docs/requisitos.md` — a tradução que fizemos do pedido do cliente; origem de tudo abaixo
- `docs/jornada.md` — onde a IA entra no fluxo e por quê
- `docs/riscos.md` — matriz R1-R9: risco → mitigação → spec → verificação
- `docs/testes.md` — risco → teste: onde cada verificação da matriz vive e o que faz um teste ser aceito
- `docs/decisoes.md` — mapa D1-D14 → ADRs
- `docs/PRD.md` — requisitos do produto
- `docs/specs/S-XX-*.md` — a spec em execução é a fonte da verdade da sessão

## Fluxo de trabalho (SDD)
1. Cada spec tem uma issue no GitHub, linkada no frontmatter (`issue:`). A issue é **ponteiro**
   para a spec, nunca cópia: requisito e task vivem só na spec. Se as duas discordarem, a spec
   vence — duas fontes de verdade sobre "o que fazer agora" levam a escolher a errada.
2. Cada spec = uma branch `spec/s-XX-nome` a partir da `main` + uma sessão nova do Claude Code.
3. Cada task da spec = um commit (Conventional Commits, em inglês).
4. Ao final: PR para `main` usando o template, com `Closes #N` e evidência (screenshot + trace
   Langfuse). O squash merge fecha a issue.
5. Verificação independente: sessão NOVA roda `/verificar-spec` antes do merge (ver comando).
6. Merge por squash. A `main` é protegida; os checks do CI são obrigatórios.

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
