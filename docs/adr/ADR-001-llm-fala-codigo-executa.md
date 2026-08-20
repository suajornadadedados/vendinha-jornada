# ADR-001 — O LLM decide o que dizer; o código decide o que pode ser feito

- Status: aceito · Data: 2026-08-03 · Decisões: D1, D3 · Riscos: R1

## Contexto
O produto mistura etapas conversacionais (alto valor para LLM) com etapas de dinheiro e
documento fiscal (erro inaceitável). Precisamos de um princípio único que decida, para cada
etapa, quem é a autoridade.

## Alternativas consideradas
1. **LLM end-to-end com "prompts cuidadosos"** — máxima flexibilidade; segurança dependente de
   comportamento do modelo; inaceitável para preço/NF.
2. **Fluxo 100% determinístico com NLU raso** — seguro; joga fora o valor central (entender
   necessidade implícita).
3. **LLM posicionado + fatos e ações via tools tipadas** — o modelo conversa; todo fato de
   negócio vem de tool (RAG/banco); toda ação é tool com permissão.

## Decisão
Opção 3. Preço, total e validação nunca saem do modelo. Todo fato afirmado sobre produto tem
origem em tool. A jornada classificada em docs/jornada.md é normativa.

## Consequências
+ Confiança verificável (evals de groundedness); superfície de risco reduzida.
− Mais engenharia de tools; latência de chamadas adicionais (aceita).
