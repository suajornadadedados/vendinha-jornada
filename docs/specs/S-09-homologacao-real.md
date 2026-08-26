---
id: S-09
titulo: (Opcional) Homologação real de NF-e
status: rascunho
branch: spec/s-09-homologacao
issue: #10
adrs: [ADR-004]
riscos_cobertos: [R8]
---

# S-09 — Homologação real de NF-e (opcional, fora do quickstart)

## Objetivo
Provar o valor do port: plugar o `HomologacaoAdapter` (ambiente de homologação SEFAZ via
emissor com API) trocando apenas configuração — sem tocar no domínio.

## Requisitos
- [ ] REQ-1 Spike + ADR escolhendo o emissor (Focus NFe / NFE.io / eNotas): custo, DX, ambiente de homologação.
- [ ] REQ-2 `HomologacaoAdapter` cumprindo o mesmo contrato do mock (testes de contrato compartilhados).
- [ ] REQ-3 Certificado e credenciais exclusivamente via env/secrets; guia de configuração em `docs/`.
- [ ] REQ-4 Nada desta spec entra no caminho do quickstart.

## BDD
```gherkin
Cenário: troca por configuração
  Dado o fluxo completo funcionando com o MockAdapter
  Quando altero NF_EMITTER=homologacao com credenciais válidas
  Então a mesma jornada emite uma NF-e autorizada em homologação, sem mudança de código de domínio
```

## Métricas de sucesso
| Métrica | Alvo | Como medir |
|---|---|---|
| Diff fora de adapters/config | 0 linhas | revisão do PR |

## Verificação independente
- Rodar os testes de contrato contra ambos adapters e revisar o diff quanto a vazamento de detalhes do emissor para o domínio.

## Definition of Done
- [ ] Checklist padrão do template
