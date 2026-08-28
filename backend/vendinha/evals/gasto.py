"""O que uma conversa de eval custou, separado pelos preços que a cobram.

`budget.tokens_spent` devolve um número só, e foi suficiente enquanto a pergunta
era *"esta conversa estourou o teto de sessão?"*. A pergunta desta medição é outra
— *"quanto custa rodar a suíte?"* — e ela não se responde com um total.

Entrada, saída e leitura de cache têm **três preços diferentes**. Somar os três num
número e multiplicar por um preço é a conta errada com cara de certa: num laço
agêntico a entrada é o histórico reenviado a cada ida ao modelo e domina o volume,
enquanto a saída, que custa várias vezes mais por token, é pequena. A proporção
entre elas é o que decide qual alavanca de custo vale a pena — e um total não a
mostra.

**Por que aqui e não em `budget.py`.** Aquele módulo é o teto de sessão, que é
guarda de produção (R6, RNF-3): mexer nele para servir a um relatório mudaria
código que decide se um atendimento continua. Este é leitura, não guarda. As duas
funções leem o mesmo `usage_metadata` e um teste as prende uma na outra
(`test_the_breakdown_total_agrees_with_the_counter_that_guards_the_ceiling`),
porque duas contagens da mesma coisa que discordam em silêncio é exatamente como a
S-04 descobriu que a régua rodava com um teto diferente do de produção.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from langchain_core.messages import AIMessage


@dataclass(frozen=True)
class Gasto:
    """O consumo de uma conversa, por faixa de preço."""

    entrada: int = 0
    saida: int = 0

    # Fatias de `entrada`, não parcelas somadas a ela. É a convenção do
    # `usage_metadata` do LangChain, e confundi-las contaria a leitura de cache
    # duas vezes — errando o custo para cima justamente quando o cache funciona.
    cache_leitura: int = 0
    cache_escrita: int = 0

    @property
    def entrada_nova(self) -> int:
        """A entrada paga por inteiro: o que não veio nem foi para o cache.

        Sem prompt caching configurado — o estado de hoje — este número é igual a
        `entrada`, e é isso que faz dele a medida honesta de quanto a alavanca de
        caching teria para morder.
        """
        return self.entrada - self.cache_leitura - self.cache_escrita

    @property
    def total(self) -> int:
        """O mesmo número que `budget.tokens_spent` conta, por construção."""
        return self.entrada + self.saida


def gasto_da_conversa(messages: Iterable[object]) -> Gasto:
    """Soma o `usage_metadata` de todas as respostas do modelo numa conversa.

    Aceita `Iterable[object]` pela mesma razão que `budget.tokens_spent`: o runner
    segura a saída do grafo como objetos simples.

    Mensagem sem `usage_metadata` conta zero, como lá. Subcontar é a direção errada
    para um teto — e por isso `tokens_spent` a aceita de olhos abertos —, mas aqui
    o preço é ainda menor, porque isto informa um relatório em vez de guardar uma
    fronteira.
    """
    entrada = saida = leitura = escrita = 0
    for message in messages:
        if not isinstance(message, AIMessage) or not message.usage_metadata:
            continue
        uso = message.usage_metadata
        entrada += uso.get("input_tokens", 0)
        saida += uso.get("output_tokens", 0)
        detalhes = uso.get("input_token_details") or {}
        leitura += detalhes.get("cache_read", 0)
        escrita += detalhes.get("cache_creation", 0)
    return Gasto(entrada=entrada, saida=saida, cache_leitura=leitura, cache_escrita=escrita)


__all__ = ["Gasto", "gasto_da_conversa"]
