"""As tools do agente — a única forma de um fato entrar na conversa.

Um pacote, e não um módulo, porque a fronteira de permissão do ADR-002 é
territorial: `tools/catalogo.py` é read-only e a S-04 traz `tools/checkout.py`
com side effect. Manter os dois em arquivos diferentes não *cria* a garantia — o
registro de `subagents.py` é que faz isso — mas torna visível, ao abrir o
diretório, onde mora cada metade.
"""

__all__: list[str] = []
