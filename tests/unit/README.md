# tests/unit — o que é rápido e determinístico

> Convenção normativa: `docs/testes.md`. Este README é o resumo operacional.

**Teste unitário aqui não nasce de cobertura, nasce de risco.** Se você não consegue dizer
qual linha de `docs/riscos.md` o teste fecha, ele provavelmente não deveria existir.

## O que entra

| Risco | O que se prova | Seam |
|---|---|---|
| **R2** | O subagent de recomendação não possui tool de escrita | o registro `subagent → tools`, lido como dado |
| **R1** | Preço e total saem de código/banco, nunca de texto do modelo | a função de cálculo do pedido |
| **R5** | CPF, e-mail e nome saem mascarados **antes** de virar trace | a função de mascaramento |
| **R6** | Budget cap e timeout por tool são respeitados | a configuração do guard |

## O que não entra

- Qualquer coisa que precise de Postgres, Qdrant ou rede → não existe camada de integração
  aqui: vai para verificação manual no `/verificar-spec` (`docs/testes.md` §1)
- Fronteira de permissão, injeção, PII, HITL → `tests/security/`
- Qualidade da conversa, tom, condução → `evals/`
- Texto literal de prompt → nada protege isso, e não deveria

## Como escrever

```python
@pytest.mark.risco("R2")
@pytest.mark.requires_backend
def test_recommendation_agent_cannot_create_order(tool_registry):
    """R2 — the recommendation subagent has no write tool registered.

    Fails if the permission boundary leaks (ADR-002, RF-1.5).
    """
```

Três regras que o `/verificar-spec` cobra:

1. **O `R#` no docstring**, primeira linha. É o que liga o teste ao risco sem ler a implementação.
2. **Nome descreve comportamento**, não função: `test_recommendation_agent_cannot_create_order`,
   nunca `test_tools_registry`.
3. **Valor esperado vem de fonte independente.** Nada de recalcular no teste a mesma conta que
   o código faz — teste tautológico passa por construção e nunca discorda do código.

Mock só na fronteira de port (ADR-004). Se você precisou mockar um colaborador interno para
testar, o seam está errado.

## Fixtures disponíveis

`produto`, `catalogo`, `cliente` — dados sintéticos, com os mesmos nomes de produto usados em
`evals/golden/`. Preço é `Decimal`, nunca `float`: dinheiro não é ponto flutuante, e um teste
que aceita `float` deixa isso passar.

`@pytest.mark.requires_backend` faz o teste **pular** enquanto `backend/` não existir, em vez de
quebrar no import. Suíte permanentemente vermelha ensina a ignorar suíte vermelha.

## Rodar

```bash
pytest tests/unit
pytest tests/unit -m "risco"          # só os que declaram risco
pytest -k permission_boundary
```
