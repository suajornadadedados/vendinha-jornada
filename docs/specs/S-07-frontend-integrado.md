---
id: S-07
titulo: Frontend integrado
status: aprovada
branch: spec/s-07-frontend
issue: #8
adrs: [ADR-004, ADR-013]
riscos_cobertos: []
---

# S-07 — Frontend integrado

## Objetivo
Produto usável de ponta a ponta: chat com streaming e estados honestos + fila do operador,
com contratos gerados do OpenAPI (nada digitado à mão na fronteira).

## Requisitos
- [ ] REQ-1 Cliente TypeScript gerado do OpenAPI no build (drift de contrato quebra o build).
- [ ] REQ-2 Chat: streaming SSE, estados honestos (digitando, aguardando pagamento,
      aguardando aprovação da NF), link de pagamento renderizado, DANFE acessível.
- [ ] REQ-3 Fila do operador: pendentes com detalhe completo — destinatário PJ e composição
      item a item —, aprovar/rejeitar (motivo), atualização após ação.
- [ ] REQ-4 UI enxuta e apresentável em demo (sem framework de UI pesado; estilo próprio simples).
- [ ] REQ-5 A composição é **visível enquanto é montada**: itens, quantidades, total e valor
      por pessoa, atualizados a cada veredito. Reprovação aparece com o motivo que o
      validador devolveu — orçamento, slot ou restrição —, e não como mensagem genérica.
      É a tela onde a regra de ouro fica visível para quem nunca vai abrir um trace.

## Fora de escopo
Autenticação; responsivo mobile refinado.

## Tasks
1. `feat(s-07): typed api client generated from openapi`
2. `feat(s-07): chat ui with sse streaming and honest states`
3. `feat(s-07): operator queue ui with audited actions`
4. `feat(s-07): live composition panel with validation feedback`
5. `chore(s-07): demo polish and empty/error states`

## BDD
```gherkin
Cenário: jornada completa no navegador
  Dado o ambiente local de pé
  Quando percorro evento → composição → validação → checkout → pagamento teste → aprovação
  Então cada etapa exibe seu estado real e a DANFE fica acessível ao final

Cenário: a recusa do código é legível na tela
  Dado um orçamento de R$150 por cesta
  Quando a composição montada soma R$163
  Então a tela mostra o estouro e o item que faltou, e não um erro genérico
```

## Métricas de sucesso
| Métrica | Alvo | Como medir |
|---|---|---|
| Jornada completa sem recarregar a página | 100% | teste manual roteirizado |
| Tipos da fronteira escritos à mão | 0 | revisão do diff |
| Totais renderizados a partir de conta no frontend | 0 | revisão do diff — o total vem do backend |

## Verificação independente
- Percorrer a jornada num navegador limpo; derrubar o backend no meio e avaliar a honestidade dos estados de erro.

## Definition of Done
- [ ] Checklist padrão do template
