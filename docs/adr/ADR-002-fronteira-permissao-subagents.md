# ADR-002 — Fronteira de permissão via supervisor + subagents

- Status: aceito · Data: 2026-08-03 · Decisão: D4 · Riscos: R2, R4
- Atualizado pelo ADR-011 **apenas quanto à camada de teste**: onde se lê *"teste unitário trava a
  fronteira"*, a invariante é provada em `tests/security/test_permission_boundary.py`. A decisão em
  si — registro explícito de tools por subagent, recomendação read-only por construção — permanece
  vigente e inalterada.

## Contexto
Um único agente com todas as tools torna a segurança dependente do prompt ("só use emitir_nf
quando apropriado"). Prompt injection e erro de roteamento viram risco financeiro/fiscal.

## Alternativas consideradas
1. **Agente único + instruções de quando usar cada tool** — simples; segurança comportamental,
   não estrutural.
2. **Supervisor + subagents com registro explícito de tools por subagent** — a recomendação
   não tem acesso às tools de side effect por construção; teste unitário trava a fronteira.

## Decisão
Opção 2. `recomendacao` = tools read-only. `checkout` = side effects (criar_pedido,
gerar_link_pagamento, emitir_nf). Desconto não existe como ação para nenhum agente.

## Consequências
+ Injection não alcança ações: o subagent nem possui a tool; auditável e testável.
− Roteamento supervisor vira ponto de atenção (coberto por evals de condução).
