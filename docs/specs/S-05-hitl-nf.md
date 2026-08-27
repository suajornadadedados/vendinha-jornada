---
id: S-05
titulo: HITL + emissão de NF
status: aprovada
branch: spec/s-05-hitl-nf
issue: #6
adrs: [ADR-003, ADR-004, ADR-013]
riscos_cobertos: [R3, R8]
---

# S-05 — HITL + emissão de NF

## Objetivo
Irreversível exige humano: o grafo pausa antes de emitir a NF, o operador aprova em fila
própria, e a emissão sai por port com mock fiel (DANFE/XML "SEM VALOR FISCAL").

> O destinatário é **PJ** (ADR-013). Isso fecha um furo que o case B2C tinha: coletávamos
> nome, CPF e e-mail para uma DANFE modelo 55 que exige endereço de destinatário. Com
> comprador corporativo o endereço de entrega chega naturalmente, e a nota fica fiel de
> verdade em vez de fiel no que dava.

## Requisitos
- [ ] REQ-1 Após pagamento confirmado: pedido → `aguardando_aprovacao_nf` e interrupt persistido no checkpointer.
- [ ] REQ-2 API da fila do operador: listar pendentes com dados completos da nota — incluindo
      destinatário PJ e a composição item a item — e aprovar/rejeitar com registro (quem,
      quando, motivo na rejeição).
- [ ] REQ-3 Aprovação retoma o grafo; rejeição comunica o motivo ao fluxo do cliente.
- [ ] REQ-4 Port `NFEmitter` + `MockAdapter` (XML e DANFE PDF fiéis ao layout NF-e 55, tarja
      "SEM VALOR FISCAL"), com **destinatário PJ**: razão social, CNPJ, inscrição estadual e
      endereço de entrega, todos vindos do pedido. `HomologacaoAdapter` fica na S-09.
- [ ] REQ-5 Invariante testada na camada `security` (`tests/security/test_hitl_invariant.py`): nenhum
      caminho emite NF sem aprovação registrada (ADR-011).
- [ ] REQ-6 Cliente recebe confirmação no chat com acesso à DANFE/XML.

## Fora de escopo
UI do operador (S-07 — aqui só API); homologação real (S-09).

## Tasks
1. `feat(s-05): interrupt before nf emission with persisted state`
2. `feat(s-05): operator queue api with audited approve/reject`
3. `feat(s-05): nf emitter port with faithful mock adapter (danfe + xml)`
4. `feat(s-05): resume flow and customer notification`
5. `test(s-05): integration test for the no-approval-no-emission invariant`

## BDD
```gherkin
Cenário: NF só sai com aprovação
  Dado um pedido pago aguardando aprovação
  Quando o operador aprova na fila
  Então o grafo retoma, a DANFE sai com tarja "SEM VALOR FISCAL" e destinatário PJ preenchido,
  e o cliente é notificado

Cenário: emissão sem aprovação é impossível
  Dado um pedido pago aguardando aprovação
  Quando qualquer caminho tenta invocar emitir_nf sem registro de aprovação
  Então a emissão é bloqueada e o incidente é registrado
```

## Métricas de sucesso
| Métrica | Alvo | Como medir |
|---|---|---|
| NFs emitidas sem aprovação registrada | 0 | `tests/security/test_hitl_invariant.py` + auditoria |
| Retomada pós-aprovação | 100% dos casos de teste | `tests/unit/test_session_resume.py`; restart real à mão no `/verificar-spec` |

## Verificação independente
- Percorrer o fluxo completo com Pix de teste; matar o processo durante o interrupt e
  confirmar retomada após restart (estado persistido).
- Tentar emitir via chamada direta sem aprovação e confirmar bloqueio.

## Definition of Done
- [ ] Checklist padrão do template
