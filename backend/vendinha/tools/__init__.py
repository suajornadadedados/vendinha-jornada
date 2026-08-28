"""As tools do agente — a única forma de um fato entrar na conversa.

Um pacote, e não um módulo, porque a fronteira de permissão do ADR-002 é
territorial: `tools/catalogo.py` é read-only e a S-04 traz `tools/checkout.py`
com side effect. Manter os dois em arquivos diferentes não *cria* a garantia — o
registro de `subagents.py` é que faz isso — mas torna visível, ao abrir o
diretório, onde mora cada metade.
"""

from decimal import Decimal
from typing import Annotated

from pydantic import WithJsonSchema

# Dinheiro que o MODELO informa numa tool — um teto por pessoa, um filtro de faixa
# de preço. Continua `Decimal` em Python: o que muda é só o JSON Schema que descreve
# o argumento para o fornecedor.
#
# **Por que o schema precisa ser escrito à mão.** O Pydantic descreve `Decimal` como
# `anyOf: [number, string]`, e na variante string ele põe um `pattern` com
# *lookahead*: `^(?!^[-+.]*$)[+-]?0*\\d*\\.?\\d*$`. O validador de schema de tool da
# OpenAI recusa lookaround, e a chamada morre com um 400 —
# *"regex lookaround is not supported"* — apontando o campo. O atendimento inteiro
# cai no primeiro turno, com uma tool que está perfeitamente correta.
#
# **Não se perde garantia nenhuma.** O `pattern` é orientação para o modelo, nunca
# validação: quem valida é o Pydantic quando o argumento chega, e ele continua
# valendo palavra por palavra. É a regra de ouro a nosso favor — o schema sugere, o
# código decide.
#
# As duas variantes ficam de pé de propósito. A de número é a que o modelo usa na
# prática; a de string é a que preserva o decimal exato quando ele a escolhe, e
# trocar as duas por `number` só jogaria essa fora.
ReaisNaEntrada = Annotated[
    Decimal,
    WithJsonSchema({"anyOf": [{"type": "number"}, {"type": "string"}]}),
]

__all__: list[str] = ["ReaisNaEntrada"]
