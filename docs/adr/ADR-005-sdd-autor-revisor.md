# ADR-005 — SDD com branch por spec e verificação autor/revisor

- Status: aceito · Data: 2026-08-03 · Decisão: D9 · Risco: R7 (parcial)

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
