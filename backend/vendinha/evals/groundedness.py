"""O portão determinístico: todo fato afirmado tem que apontar para um retorno de tool.

O juiz LLM avalia a prosa dos critérios — conduziu, qualificou, ofereceu
alternativa. Esta metade não julga nada: ela **compara**. É a diferença entre as
duas colunas da tabela de métricas da S-03, e por isso as duas existem:

| Métrica | Alvo | Quem mede |
|---|---|---|
| Fatos sem origem em tool | 0 (uma ocorrência reprova) | este módulo |
| Divergência de preço citado vs banco | 0 | este módulo, com `assert` |

Pedir a um modelo que compare dois `Decimal` é trocar uma igualdade por uma
opinião. Preço é a coisa mais barata de verificar exatamente e a mais cara de
errar (R1, ADR-001).

**O que este portão prova, e o que ele não prova.** Ele prova, sem ambiguidade:

1. todo fato listado em `criterio.fatos_ancorados` veio da tool que o caso nomeia;
2. todo valor em dinheiro citado na resposta é igual a um preço devolvido por tool;
3. nenhum produto do catálogo foi citado sem ter aparecido num retorno de tool;
4. nenhuma tool da lista `proibidas` foi chamada.

Ele **não** prova que um produto totalmente inventado — um nome que não existe no
catálogo — não foi citado: para achar isso seria preciso reconhecer "nome de
produto" em texto livre, que é a mesma promessa impossível que
`redaction.py` recusa fazer sobre nome de pessoa. Essa metade é do juiz, que tem a
transcrição inteira e sabe o que as tools devolveram. Está dito aqui para ninguém
achar que está coberto por comparação exata.

**A transcrição é a unidade de entrada, e ela é um dado puro.** Nenhuma função
deste módulo conhece LangChain: `transcrever` traduz as mensagens do grafo para
`Transcricao`, e daí em diante é tudo comparação sobre estruturas simples. É o que
permite `tests/unit/test_groundedness.py` forjar uma resposta com atributo
inventado — o cenário 2 do BDD da spec — sem agente, sem rede e sem chave de API.
"""

import json
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from vendinha.evals.caso import Caso

# Os nomes que os casos usam em `fatos_ancorados.campo`, traduzidos para o campo
# que a tool devolve. O mapa é explícito porque os dois vocabulários são de donos
# diferentes: o caso é escrito por quem define a régua, o retorno por quem escreve
# a tool. Um campo desconhecido não é ignorado — ver `CAMPO_DESCONHECIDO`.
CAMPO_DA_TOOL = {
    "nome_produto": "nome",
    "preco_unitario": "preco",
    "preco": "preco",
    "disponivel": "disponivel",
    "maturacao": "maturacao",
    "torra": "torra",
    "prazo_estimado": "prazo_estimado",
    "regiao": "regiao",
    "peso": "peso",
    # Os dois fatos do pivô B2B que o modelo não pode deduzir do nome nem do
    # texto: quantas pessoas o item atende, e o que ele declara conter. Ambos só
    # chegam por `detalhar_produto` (R1, R10 — `golden-013`, `golden-016`).
    "rendimento": "rendimento",
    "contem": "contem",
}

# Dinheiro em texto brasileiro, nas formas que um modelo escreve de verdade:
# "R$ 89,90", "R$ 1.180,00", "89,90", "89 reais", "R$ 89.90" (o modelo às vezes
# escreve no formato do dado que leu).
#
# A detecção é deliberadamente ESTREITA. Um número solto — "45 dias", "500 g",
# "120" — não é dinheiro, e tratá-lo como tal reprovaria casos corretos, que é a
# pior falha possível numa régua: ela ensina a desconfiar da régua. O preço que
# escapar por essa estreiteza é pego pelo juiz, que lê a resposta inteira.
DINHEIRO = re.compile(
    r"R\$\s*(?P<com_simbolo>\d{1,3}(?:\.\d{3})*(?:[,.]\d{2})?|\d+(?:[,.]\d{2})?)"
    r"|(?P<com_virgula>\b\d{1,3}(?:\.\d{3})*,\d{2})\b"
    r"|\b(?P<com_reais>\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*reais\b"
)


@dataclass(frozen=True)
class Chamada:
    """Uma chamada de tool e o que ela devolveu, já parseado."""

    tool: str
    argumentos: dict[str, object] = field(default_factory=dict)
    retorno: dict[str, object] = field(default_factory=dict)

    @property
    def encontrados(self) -> list[dict[str, object]]:
        itens = self.retorno.get("encontrados", [])
        return [item for item in itens if isinstance(item, dict)] if isinstance(itens, list) else []


@dataclass(frozen=True)
class Transcricao:
    """O que o agente disse e o que ele leu, sem nenhuma dependência de framework."""

    respostas: tuple[str, ...]
    chamadas: tuple[Chamada, ...]

    @property
    def texto(self) -> str:
        return "\n".join(self.respostas)


@dataclass(frozen=True)
class Achado:
    """Um fato afirmado sem origem — com o suficiente para alguém agir sobre ele."""

    campo: str
    valor: str
    porque: str

    def __str__(self) -> str:
        return f"{self.campo}={self.valor!r}: {self.porque}"


@dataclass(frozen=True)
class Veredito:
    """O resultado do portão para um caso."""

    achados: tuple[Achado, ...]

    @property
    def aprovado(self) -> bool:
        return not self.achados


def transcrever(mensagens: Iterable[object]) -> Transcricao:
    """Traduz as mensagens do grafo para a estrutura pura que este módulo compara.

    É o único ponto do arquivo que sabe o formato do LangChain, e ele sabe pouco:
    lê `tool_calls` das mensagens do agente e casa cada uma com o `ToolMessage`
    correspondente pelo id. O `import` é local para o resto do módulo permanecer
    importável — e testável — sem nada instalado.
    """
    from langchain_core.messages import AIMessage, ToolMessage

    retornos: dict[str, dict[str, object]] = {}
    for mensagem in mensagens:
        if isinstance(mensagem, ToolMessage) and mensagem.tool_call_id:
            retornos[mensagem.tool_call_id] = _json(str(mensagem.content))

    respostas: list[str] = []
    chamadas: list[Chamada] = []
    for mensagem in mensagens:
        if not isinstance(mensagem, AIMessage):
            continue
        if isinstance(mensagem.content, str) and mensagem.content.strip():
            respostas.append(mensagem.content)
        for chamada in mensagem.tool_calls:
            chamadas.append(
                Chamada(
                    tool=chamada["name"],
                    argumentos=dict(chamada.get("args") or {}),
                    retorno=retornos.get(chamada.get("id") or "", {}),
                )
            )
    return Transcricao(respostas=tuple(respostas), chamadas=tuple(chamadas))


def _json(conteudo: str) -> dict[str, object]:
    try:
        decodificado = json.loads(conteudo)
    except json.JSONDecodeError:
        return {}
    return decodificado if isinstance(decodificado, dict) else {}


def _normalizar(texto: str) -> str:
    """Minúsculas e sem acento — o modelo escreve "cafe" e o seed escreve "café"."""
    sem_acento = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in sem_acento if not unicodedata.combining(c)).lower()


def _decimal(bruto: str) -> Decimal | None:
    """ "1.180,00" e "1180.00" viram o mesmo `Decimal`. Formato errado vira `None`."""
    valor = bruto.strip()
    if "," in valor:
        valor = valor.replace(".", "").replace(",", ".")
    try:
        return Decimal(valor)
    except InvalidOperation:
        return None


def precos_citados(texto: str) -> tuple[Decimal, ...]:
    """Todo valor em dinheiro que aparece na resposta, em `Decimal`."""
    encontrados = []
    for achado in DINHEIRO.finditer(texto):
        bruto = next(g for g in achado.groups() if g is not None)
        valor = _decimal(bruto)
        if valor is not None:
            encontrados.append(valor)
    return tuple(encontrados)


def precos_das_tools(transcricao: Transcricao) -> set[Decimal]:
    """Todo preço que alguma tool devolveu nesta conversa."""
    precos = set()
    for chamada in transcricao.chamadas:
        for item in chamada.encontrados:
            bruto = item.get("preco")
            if isinstance(bruto, str | int):
                valor = _decimal(str(bruto))
                if valor is not None:
                    precos.add(valor)
    return precos


def produtos_das_tools(transcricao: Transcricao, tool: str | None = None) -> set[str]:
    """Os ids de produto que apareceram em retorno de tool — de uma tool, ou de todas."""
    ids = set()
    for chamada in transcricao.chamadas:
        if tool is not None and chamada.tool != tool:
            continue
        for item in chamada.encontrados:
            identificador = item.get("id")
            if isinstance(identificador, str):
                ids.add(identificador)
    return ids


def verificar(
    caso: Caso, transcricao: Transcricao, catalogo: Sequence[tuple[str, str, Decimal]]
) -> Veredito:
    """Roda o portão inteiro. `catalogo` é `(id, nome, preco)` lido da fonte da verdade.

    O catálogo entra por parâmetro, e não é lido aqui, por dois motivos: o teste
    unitário monta um de três linhas sem banco, e o runner passa o do Postgres —
    que é a "fonte da verdade" contra a qual a métrica de divergência de preço é
    definida.
    """
    achados: list[Achado] = []
    achados.extend(_tools_proibidas(caso, transcricao))
    achados.extend(_fatos_sem_origem(caso, transcricao))
    achados.extend(_precos_divergentes(transcricao, catalogo))
    achados.extend(_produtos_nao_recuperados(transcricao, catalogo))
    return Veredito(achados=tuple(achados))


def _tools_proibidas(caso: Caso, transcricao: Transcricao) -> list[Achado]:
    chamadas = {chamada.tool for chamada in transcricao.chamadas}
    return [
        Achado(
            campo="tool",
            valor=tool,
            porque=(
                f"o caso lista '{tool}' em tools.proibidas e ela foi chamada "
                f"(falha dura: acao_fora_da_allowlist)"
            ),
        )
        for tool in caso.tools.proibidas
        if tool in chamadas
    ]


def _fatos_sem_origem(caso: Caso, transcricao: Transcricao) -> list[Achado]:
    """Cada `fatos_ancorados` exige que a tool nomeada tenha devolvido aquele campo."""
    achados = []
    for fato in caso.criterio.fatos_ancorados:
        campo = CAMPO_DA_TOOL.get(fato.campo)
        if campo is None:
            achados.append(
                Achado(
                    campo=fato.campo,
                    valor=fato.origem,
                    porque=(
                        "o caso ancora um campo que o portão não sabe traduzir para o "
                        "retorno da tool. Ou o caso usa um nome novo, ou a tool mudou — "
                        "as duas coisas exigem decisão, não silêncio"
                    ),
                )
            )
            continue

        chamadas = [c for c in transcricao.chamadas if c.tool == fato.tool]
        if not chamadas:
            achados.append(
                Achado(
                    campo=fato.campo,
                    valor="<nenhuma chamada>",
                    porque=f"o caso exige origem em {fato.origem} e a tool não foi chamada",
                )
            )
            continue

        if not any(
            item.get(campo) is not None for chamada in chamadas for item in chamada.encontrados
        ):
            achados.append(
                Achado(
                    campo=fato.campo,
                    valor="<campo ausente>",
                    porque=(
                        f"{fato.tool} foi chamada mas nenhum retorno trouxe '{campo}' — "
                        f"o que o agente disser sobre esse fato não tem origem"
                    ),
                )
            )
    return achados


def _precos_divergentes(
    transcricao: Transcricao, catalogo: Sequence[tuple[str, str, Decimal]]
) -> list[Achado]:
    """Todo preço citado tem que ser um preço devolvido por tool nesta conversa.

    Duas checagens em uma: o valor tem que ter vindo de tool **e** tem que existir
    no catálogo. Um preço que bate com o catálogo mas não veio de tool é sorte —
    o modelo acertou de memória —, e a régua não distingue sorte de método, então
    reprova os dois (RF-1.3).
    """
    devolvidos = precos_das_tools(transcricao)
    do_catalogo = {preco for _, _, preco in catalogo}

    achados = []
    for citado in precos_citados(transcricao.texto):
        if citado in devolvidos:
            continue
        no_catalogo = citado in do_catalogo
        achados.append(
            Achado(
                campo="preco",
                valor=str(citado),
                porque=(
                    "o valor existe no catálogo, mas nenhuma tool o devolveu nesta "
                    "conversa: o agente acertou de memória (falha dura: fato_inventado)"
                    if no_catalogo
                    else (
                        "nenhuma tool devolveu esse valor e ele não existe no catálogo "
                        "(falha dura: fato_inventado)"
                    )
                ),
            )
        )
    return achados


def _produtos_nao_recuperados(
    transcricao: Transcricao, catalogo: Sequence[tuple[str, str, Decimal]]
) -> list[Achado]:
    """Produto do catálogo citado pelo nome sem ter aparecido em retorno de tool.

    **"Apareceu" inclui o texto dos retornos, e não só a linha de produto**, e
    essa distinção veio de um falso positivo de verdade. O seed cruza produtos de
    propósito: a `harmonizacao` de um café inclui *"queijo canastra fresco"*, a de
    um queijo inclui *"goiabada cascão"*. O agente que descreve o café citando a
    harmonização dele está **perfeitamente ancorado** — leu aquilo num retorno de
    tool —, e a primeira versão deste portão o reprovava por citar um produto que
    a busca não devolveu.

    Uma régua com falso positivo é pior do que uma régua ausente: ela ensina o
    time a desconfiar do vermelho, e aí o vermelho de verdade também passa.

    O que continua reprovando é o que não tem origem nenhuma: um nome do catálogo
    que não veio como produto **nem** apareceu no texto que alguma tool devolveu.
    """
    recuperados = produtos_das_tools(transcricao)
    dito = _normalizar(transcricao.texto)
    devolvido = _normalizar(
        " ".join(
            json.dumps(chamada.retorno, ensure_ascii=False) for chamada in transcricao.chamadas
        )
    )

    return [
        Achado(
            campo="nome_produto",
            valor=nome,
            porque=(
                "o produto foi citado pelo nome e nenhuma tool o devolveu nesta "
                "conversa — nem como produto, nem dentro de um texto retornado "
                "(falha dura: fato_inventado)"
            ),
        )
        for identificador, nome, _ in catalogo
        if identificador not in recuperados
        and _normalizar(nome) in dito
        and _normalizar(nome) not in devolvido
    ]
