# ADR-005 — SDD com branch por spec e verificação autor/revisor

- Status: aceito · Data: 2026-08-03 · Decisão: D9 · Risco: R7 (parcial)
- Atualizado **apenas quanto ao momento e ao executor da verificação**, sem tocar a decisão:
  onde se lê *"relatório de verificação independente anexado antes do **merge**"*, leia-se
  **antes do PR** — o `CLAUDE.md`, fluxo item 4, é quem manda, e o PR nasce já com a correção
  dentro. E onde se lê *"sessão revisora nova"*, o executor padrão passou a ser o subagente
  **`verificador-de-spec`**, cujo prompt vive versionado em `.claude/agents/`. Sessão nova
  continua valendo e continua sendo o portão mais forte: o subagente elimina o **contexto**, a
  sessão nova elimina a **autoria**.
  O par autor/revisor decidido aqui permanece inteiro — mudou quando o revisor entra e quem ele é.

## Contexto
Trabalho com agente de código tende a escopo elástico e auto-aprovação: quem implementa
"sabe o que quis fazer" e não enxerga o que faltou.

## Alternativas consideradas
1. **Sessão única que implementa e valida** — rápida; viés de autoria não mitigado.
2. **Branch por spec + sessão autora + sessão revisora nova** — a revisora recebe apenas
   spec + diff + roteiro objetivo (/verificar-spec), nunca o histórico da autora.

## Decisão
Opção 2. Cada spec: branch própria, commits por task (conventional), PR com evidência,
relatório de verificação independente anexado antes do merge.

## Consequências
+ Não-conformidades detectadas antes do merge; PRs auditáveis; método replicável.
− Custo de uma sessão extra por spec (aceito: é barato perto de bug em produção).
Nota honesta: sessão nova não elimina viés do modelo — elimina o viés de AUTORIA. É a mesma
razão pela qual code review humano não é feito pelo autor.
