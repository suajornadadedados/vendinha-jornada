---
id: S-07
titulo: Frontend integrado
status: aprovada
branch: spec/s-07-frontend
issue: 
adrs: [ADR-004]
riscos_cobertos: []
---

# S-07 — Frontend integrado

## Objetivo
Produto usável de ponta a ponta: chat com streaming e estados honestos + fila do operador,
com contratos gerados do OpenAPI (nada digitado à mão na fronteira).

## Requisitos
- [ ] REQ-1 Cliente TypeScript gerado do OpenAPI no build (drift de contrato quebra o build).
- [ ] REQ-2 Chat: streaming SSE, estados honestos (digitando, aguardando pagamento, aguardando aprovação da NF), link de pagamento renderizado, DANFE acessível.
- [ ] REQ-3 Fila do operador: pendentes com detalhe completo, aprovar/rejeitar (motivo), atualização após ação.
- [ ] REQ-4 UI enxuta e apresentável em demo (sem framework de UI pesado; estilo próprio simples).

## Fora de escopo
Autenticação; responsivo mobile refinado.

## Tasks
1. `feat(s-07): typed api client generated from openapi`
2. `feat(s-07): chat ui with sse streaming and honest states`
3. `feat(s-07): operator queue ui with audited actions`
4. `chore(s-07): demo polish and empty/error states`

## BDD
```gherkin
Cenário: jornada completa no navegador
  Dado o ambiente local de pé
  Quando percorro necessidade → recomendação → checkout → pagamento teste → aprovação do operador
  Então cada etapa exibe seu estado real e a DANFE fica acessível ao final
```

## Métricas de sucesso
| Métrica | Alvo | Como medir |
|---|---|---|
| Jornada completa sem recarregar a página | 100% | teste manual roteirizado |
| Tipos da fronteira escritos à mão | 0 | revisão do diff |

## Verificação independente
- Percorrer a jornada num navegador limpo; derrubar o backend no meio e avaliar a honestidade dos estados de erro.

## Definition of Done
- [ ] Checklist padrão do template
