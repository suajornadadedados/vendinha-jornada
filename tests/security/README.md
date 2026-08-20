# tests/security — a garantia, não o comportamento

> Convenção normativa: `docs/testes.md`. Decisões: ADR-002, ADR-003, ADR-007.

Esta pasta e `evals/adversarial/` atacam o mesmo problema por lados opostos, e a diferença é a
coisa mais importante deste README:

|  | Pergunta | O que produz |
|---|---|---|
| `evals/adversarial/` | O agente **se comportou** bem sob ataque? | evidência |
| `tests/security/` | O comportamento errado é **alcançável**? | garantia |

Um eval verde diz que o modelo resistiu **desta vez**. Um teste de segurança verde diz que não
existe caminho de código da conversa até a ação. Só o segundo sobrevive a uma troca de modelo.

> **A regra de ouro, aplicada:** o LLM decide o que dizer; o código decide o que pode ser feito.
> Se um teste aqui só passa porque o prompt pediu com educação, a arquitetura está errada.

## O que se prova aqui

| Risco | Invariante | Por que é estrutural |
|---|---|---|
| **R2** | O subagent de recomendação não tem tool de escrita | não está registrada nele — não é negada, não existe |
| **R4** | Injeção não alcança side effect | `aplicar_desconto` não existe em nenhum registro |
| **R3** | Não há caminho até `emitir_nf` sem aprovação registrada | a retomada só parte do registro de aprovação |
| **R5** | PII sai mascarada antes de deixar o processo | o trace vai para fora da infra (ADR-010) |

**R2 e R3 não são negociáveis.** Não são cobertura, são o requisito. Nenhuma spec que os toque
fecha sem esses testes verdes, e não existe versão "mínima" deles.

## Os payloads não moram aqui

Eles vêm de `evals/adversarial/*.yaml`. Um ataque novo é escrito **uma vez** e as duas camadas
o enxergam.

```python
@pytest.mark.risco("R4")
@pytest.mark.requires_backend
def test_injected_instruction_never_reaches_a_side_effect(caso_adversarial, agente):
    """R4 — an injected instruction cannot reach a tool with side effects.

    Structural, not behavioural: the tools listed in `tools.proibidas` are not
    registered on the subagent handling the turn (ADR-002).
    """
```

`caso_adversarial` é parametrizado automaticamente: o teste roda uma vez por arquivo em
`evals/adversarial/`, nomeado pelo `id` do caso. Escreveu um caso novo, ganhou um teste novo.

## Fixtures disponíveis

| Fixture | O que entrega |
|---|---|
| `caso_adversarial` | um caso por execução, parametrizado pelo `id` |
| `casos_adversariais` | o corpus inteiro, para testes que raciocinam sobre o conjunto |
| `payloads_de_injecao` | só as falas do cliente, achatadas |
| `tools_proibidas` | união das tools que nenhum caso pode alcançar |
| `pii_de_teste` | CPF, e-mail, nome e telefone **sintéticos** |
| `subagents_read_only` | quem não pode possuir tool de escrita |

## Duas coisas que não se faz aqui

- **Assertar no texto da resposta.** "O agente recusou educadamente" não é garantia — é estilo.
  Asserte que a tool não foi chamada, não que a frase foi simpática.
- **Usar dado real.** Nenhum CPF, e-mail, nome ou certificado verdadeiro entra neste
  repositório, nem em fixture. `pii_de_teste` é inteiramente fabricado.

## Rodar

```bash
pytest tests/security
pytest tests/security -m "risco"
pytest tests/security -k injecao
```
