"""As tools do checkout — onde o agente escreve, e onde o código recusa o que ele propôs.

Quatro tools, e `criar_pedido` é a razão de o arquivo existir.

**`criar_pedido` revalida a composição do zero.** Ela chega aqui com ids que já
passaram por `validar_composicao` e por isso mesmo não são confiáveis: o veredito
que autorizou a conversa foi produzido para o modelo ler, e entre aquele retorno e
esta chamada existe um caminho — o próprio modelo — que pode ter trocado um item.
Então a tool relê cada produto do Postgres, roda `composicao.validar` de novo e
**recusa o pedido inteiro** se qualquer composição reprovar. É a RF-2.7 literal:
*a validação que passou pelo modelo nunca é a que autoriza* (R10, ADR-013).

Recusar o pedido inteiro, e não a composição ruim, é decisão de produto: *"12 cestas,
2 sem álcool"* é um pedido só, e gravar dez cestas porque duas reprovaram entregaria
metade de um evento sem ninguém ter pedido.

**Dado da empresa é recusado por schema, e a recusa é legível.** A validação mora em
`pedidos.Empresa` — CNPJ com dígitos verificadores, e-mail, UF, CEP. Aqui ela é
*construída* dentro de um `try`, e o erro volta como retorno normal de tool em vez de
exceção: o modelo precisa poder pedir o dado de novo, não travar. Quem decide o que é
CNPJ válido continua sendo o código; muda só a forma como ele diz não (RF-2.2,
`golden-008`).

**O CNPJ volta mascarado.** O retorno de tool é o lugar de onde o modelo copia
números para a resposta, e ele vira trace. `golden-003` e `golden-008` reprovam a
execução que repete o documento em claro, e o ADR-007 pede PII ilegível fora do
processo — então não há de onde copiar (R5).

**`gerar_link_pagamento` é idempotente e degrada com graça.** Chamada duas vezes
para o mesmo pedido, ela devolve o mesmo link em vez de criar uma segunda
preferência: dois links vivos para um pedido é o cliente pagando um enquanto o
financeiro dele vê o outro em aberto. E gateway fora do ar não vira exceção — o
pedido está gravado e continua válido, então o que falta é uma segunda tentativa
(ADR-004, R8).

**O envelope é o `Resultado` de `tools/catalogo.py`.** O portão de groundedness só
enxerga `encontrados` (`evals/groundedness.py`): um retorno com envelope próprio
seria invisível para a régua, e fato invisível para a régua é fato que ninguém está
conferindo.
"""

import logging
from collections.abc import Sequence
from decimal import Decimal

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from vendinha import composicao as motor
from vendinha.budget import TimedOut, run_with_timeout
from vendinha.catalogo import Alergeno, Catalogo, Produto
from vendinha.composicao import TipoDeEvento
from vendinha.documentos import mascarar_cnpj
from vendinha.pagamento import GatewayIndisponivel, PaymentGateway
from vendinha.pedidos import (
    ComposicaoDoPedido,
    Empresa,
    Endereco,
    ItemDoPedido,
    Pedido,
    Pedidos,
    novo_id,
    total_de,
)
from vendinha.tools.catalogo import ItemDeResultado, Resultado
from vendinha.tools.composicao import LIMITE_DE_ITENS, ComposicaoValidada

logger = logging.getLogger(__name__)

NOMES = ("validar_dados_cliente", "criar_pedido", "gerar_link_pagamento", "consultar_pedido")

# Um pedido com mais composições do que isto não é um evento corporativo, é um
# despejo. O teto existe pelo mesmo motivo que o de `validar_composicao`: argumento
# sem limite é o caminho barato para estourar custo por repetição (`adversarial-006`).
LIMITE_DE_COMPOSICOES = 10


# ---------------------------------------------------------------- os argumentos


class EnderecoEntrada(BaseModel):
    """O endereço como o cliente o dita. A validação é de `pedidos.Endereco`."""

    model_config = ConfigDict(frozen=True)

    logradouro: str = Field(description="Rua, avenida ou praça.")
    numero: str = Field(description="O número. 's/n' quando não houver.")
    complemento: str | None = Field(default=None, description="Sala, andar, bloco.")
    bairro: str
    cidade: str
    uf: str = Field(description="A sigla de duas letras, como MG.")
    cep: str = Field(description="Oito dígitos, como 30140-071.")


class EmpresaEntrada(BaseModel):
    """Os dados do comprador PJ, como o cliente os informou — ainda não validados.

    Separado de `pedidos.Empresa` de propósito. Este é o que o modelo preenche; o
    outro é o que o código aceita. Fossem o mesmo, um CNPJ com dígito errado viraria
    `ValidationError` na fronteira da tool e o modelo receberia um traceback em vez
    de uma frase que ele consegue transformar em pergunta ao cliente.
    """

    model_config = ConfigDict(frozen=True)

    razao_social: str = Field(description="A razão social, como está no cartão CNPJ.")
    cnpj: str = Field(description="Como o cliente informou. Não corrija, não complete.")
    contato_nome: str = Field(description="Quem está falando com você.")
    contato_email: str
    endereco: EnderecoEntrada


class ComposicaoProposta(BaseModel):
    """Uma composição do pedido, nos mesmos termos de `validar_composicao`.

    Sem quantidade e sem total: os dois saem do código, aqui como lá. Aceitar
    qualquer um dos dois devolveria ao modelo exatamente a aritmética que a RF-1.6
    e o ADR-013 tiraram dele.
    """

    model_config = ConfigDict(frozen=True)

    tipo_de_evento: TipoDeEvento
    pessoas: int = Field(ge=1, description="Quantas pessoas — ou quantas cestas/kits.")
    produto_ids: list[str] = Field(min_length=1, max_length=LIMITE_DE_ITENS)
    orcamento_por_pessoa: Decimal | None = Field(
        default=None, description="O teto por pessoa (ou por cesta), em reais."
    )
    restricoes: list[Alergeno] = Field(
        default_factory=list,
        description="TODAS as restrições declaradas para ESTA composição.",
    )


class ValidarDadosCliente(BaseModel):
    """O que `validar_dados_cliente` aceita: a empresa inteira, de uma vez."""

    empresa: EmpresaEntrada


class CriarPedido(BaseModel):
    """O que `criar_pedido` aceita."""

    empresa: EmpresaEntrada
    composicoes: list[ComposicaoProposta] = Field(
        min_length=1,
        max_length=LIMITE_DE_COMPOSICOES,
        description=(
            "Uma composição por grupo com restrições diferentes. '12 cestas, 2 sem "
            "álcool' são DUAS composições: uma com pessoas=10 e outra com pessoas=2."
        ),
    )


class ConsultarPedido(BaseModel):
    pedido_id: str = Field(description="O id que criar_pedido devolveu.")


class GerarLinkPagamento(BaseModel):
    pedido_id: str = Field(description="O id que criar_pedido devolveu.")


# ------------------------------------------------------------------- o que volta


class DadosDoClienteValidados(ItemDeResultado):
    """O veredito sobre os dados da empresa. Nenhum documento em claro aqui dentro."""

    cnpj_valido: bool
    cnpj: str = Field(description="Mascarado — os quatro últimos dígitos e mais nada.")
    razao_social: str
    contato_nome: str
    dados_completos: bool
    problemas: tuple[str, ...] = ()


class PedidoResumido(ItemDeResultado):
    """O pedido do jeito que o modelo o lê — e a única origem do total.

    `total_pedido` é o nome que `golden-003` e `golden-015` usam em
    `fatos_ancorados`. O vocabulário é de quem define a régua, e a tool se ajusta a
    ele.
    """

    pedido_id: str
    status_pedido: str
    total_pedido: Decimal
    razao_social: str
    cnpj: str
    url_pagamento: str | None = None
    composicoes: tuple[ComposicaoValidada, ...] = ()


def _resumir(pedido: Pedido, vereditos: Sequence[motor.Veredito] = ()) -> PedidoResumido:
    return PedidoResumido(
        pedido_id=pedido.id,
        status_pedido=pedido.status.value,
        total_pedido=pedido.total,
        razao_social=pedido.empresa.razao_social,
        cnpj=mascarar_cnpj(pedido.empresa.cnpj),
        url_pagamento=pedido.url_pagamento,
        composicoes=tuple(ComposicaoValidada.de(veredito) for veredito in vereditos),
    )


def _para_o_banco(veredito: motor.Veredito, proposta: ComposicaoProposta) -> ComposicaoDoPedido:
    """O veredito do código vira a composição persistida, item a item.

    A conversão parte do VEREDITO e não da proposta: quantidade, preço unitário,
    subtotal e total são os que `composicao.validar` calculou sobre produtos lidos
    do banco. Da proposta sobra o que é intenção do cliente — evento, pessoas, teto
    e restrições.
    """
    return ComposicaoDoPedido(
        tipo_de_evento=veredito.tipo_de_evento,
        pessoas=veredito.pessoas,
        orcamento_por_pessoa=veredito.orcamento_por_pessoa,
        restricoes=tuple(proposta.restricoes),
        itens=tuple(
            ItemDoPedido(
                produto_id=item.produto_id,
                nome=item.nome,
                tipo=item.tipo,
                rendimento=item.rendimento,
                quantidade=item.quantidade,
                preco_unitario=item.preco_unitario,
                subtotal=item.subtotal,
            )
            for item in veredito.itens
        ),
        total=veredito.total,
        valor_por_pessoa=veredito.valor_por_pessoa,
    )


def _empresa_ou_problemas(entrada: EmpresaEntrada) -> tuple[Empresa | None, tuple[str, ...]]:
    """Constrói a `Empresa` validada, ou devolve o que impede de construí-la.

    Erro de schema vira lista de frases em vez de exceção: o caminho de conserto é
    o modelo perguntar de novo ao cliente, e para isso ele precisa receber o
    problema como dado.
    """
    try:
        empresa = Empresa(
            razao_social=entrada.razao_social,
            cnpj=entrada.cnpj,
            contato_nome=entrada.contato_nome,
            contato_email=entrada.contato_email,
            endereco=Endereco(**entrada.endereco.model_dump()),
        )
    except ValidationError as invalido:
        return None, tuple(
            f"{'.'.join(str(parte) for parte in erro['loc'])}: {erro['msg']}"
            for erro in invalido.errors()
        )
    return empresa, ()


def ferramentas_de_checkout(
    catalogo: Catalogo,
    pedidos: Pedidos,
    gateway: PaymentGateway,
    timeout_seconds: float,
) -> tuple[BaseTool, ...]:
    """Constrói as tools do checkout contra as portas recebidas.

    Fábrica, como `ferramentas_de_catalogo` e `ferramentas_de_composicao`: é o que
    permite as duas camadas de teste rodarem contra `CatalogoEmMemoria` e
    `PedidosEmMemoria` sem mockar nada interno (ADR-004, `docs/testes.md` §4).
    """

    async def _revalidar(
        propostas: Sequence[ComposicaoProposta],
    ) -> tuple[list[motor.Veredito], Resultado | None]:
        """As composições relidas do banco e validadas de novo — ou a recusa.

        Devolver `(vereditos, recusa)` em vez de levantar mantém as duas saídas no
        mesmo tipo de retorno de tool. O modelo lê `problemas_composicao` e
        recompõe; uma exceção viraria mensagem de erro técnica, que é justamente o
        que `adversarial-006` reprova.
        """
        vereditos: list[motor.Veredito] = []
        for proposta in propostas:
            produtos = await run_with_timeout(
                catalogo.por_ids(proposta.produto_ids),
                timeout_seconds,
                "leitura da composição",
            )
            ausentes = tuple(pid for pid in proposta.produto_ids if pid not in produtos)
            if ausentes:
                return [], Resultado(
                    nao_encontrados=ausentes,
                    observacao=(
                        "nenhum pedido foi criado: os ids acima não existem no catálogo; "
                        "corrija a composição e chame de novo"
                    ),
                )
            na_ordem: list[Produto] = [produtos[pid] for pid in proposta.produto_ids]
            vereditos.append(
                motor.validar(
                    tipo_de_evento=proposta.tipo_de_evento,
                    pessoas=proposta.pessoas,
                    produtos=na_ordem,
                    orcamento_por_pessoa=proposta.orcamento_por_pessoa,
                    restricoes=proposta.restricoes,
                )
            )

        if all(veredito.aprovada for veredito in vereditos):
            return vereditos, None

        # A recusa devolve TODAS as composições, aprovadas e reprovadas. O modelo
        # precisa saber qual delas quebrou — devolver só as ruins o obrigaria a
        # adivinhar a correspondência com o que ele mandou.
        return [], Resultado(
            encontrados=tuple(ComposicaoValidada.de(v) for v in vereditos),
            observacao=(
                "nenhum pedido foi criado: a revalidação no servidor reprovou. Veja "
                "problemas_composicao, troque os itens e valide de novo antes de fechar"
            ),
        )

    async def validar_dados_cliente(empresa: EmpresaEntrada) -> str:
        entrada = _como_empresa(empresa)
        validada, problemas = _empresa_ou_problemas(entrada)
        return Resultado(
            encontrados=(
                DadosDoClienteValidados(
                    cnpj_valido=validada is not None,
                    cnpj=mascarar_cnpj(entrada.cnpj),
                    razao_social=entrada.razao_social,
                    contato_nome=entrada.contato_nome,
                    dados_completos=validada is not None,
                    problemas=problemas,
                ),
            ),
            observacao=(
                None
                if validada is not None
                else (
                    "os dados acima não passam na validação; peça de novo ao cliente. "
                    "Não corrija, não complete e não aceite um valor provisório"
                )
            ),
        ).model_dump_json(exclude_none=True)

    async def criar_pedido(empresa: EmpresaEntrada, composicoes: list[ComposicaoProposta]) -> str:
        entrada = _como_empresa(empresa)
        propostas = [_como_proposta(proposta) for proposta in composicoes]

        validada, problemas = _empresa_ou_problemas(entrada)
        if validada is None:
            return Resultado(
                encontrados=(
                    DadosDoClienteValidados(
                        cnpj_valido=False,
                        cnpj=mascarar_cnpj(entrada.cnpj),
                        razao_social=entrada.razao_social,
                        contato_nome=entrada.contato_nome,
                        dados_completos=False,
                        problemas=problemas,
                    ),
                ),
                observacao=(
                    "nenhum pedido foi criado: os dados da empresa não passam na validação. "
                    "Peça o dado correto ao cliente"
                ),
            ).model_dump_json(exclude_none=True)

        vereditos, recusa = await _revalidar(propostas)
        if recusa is not None:
            return recusa.model_dump_json(exclude_none=True)

        do_banco = tuple(
            _para_o_banco(veredito, proposta)
            for veredito, proposta in zip(vereditos, propostas, strict=True)
        )
        pedido = await pedidos.criar(
            Pedido(
                id=novo_id(),
                empresa=validada,
                composicoes=do_banco,
                total=total_de(do_banco),
            )
        )
        return Resultado(encontrados=(_resumir(pedido, vereditos),)).model_dump_json(
            exclude_none=True
        )

    async def gerar_link_pagamento(pedido_id: str) -> str:
        pedido = await run_with_timeout(
            pedidos.por_id(pedido_id), timeout_seconds, "leitura do pedido"
        )
        if pedido is None:
            return Resultado(
                nao_encontrados=(pedido_id,),
                observacao="não existe pedido com esse id; crie o pedido antes de cobrar",
            ).model_dump_json(exclude_none=True)

        # Link já gerado é devolvido, e não gerado de novo. Duas preferências para o
        # mesmo pedido são dois links vivos: o cliente paga por um, o financeiro
        # dele vê o outro em aberto, e a conciliação vira telefonema.
        if pedido.url_pagamento:
            return Resultado(encontrados=(_resumir(pedido),)).model_dump_json(exclude_none=True)

        try:
            link = await run_with_timeout(
                gateway.criar_preferencia(pedido), timeout_seconds, "criação do link de pagamento"
            )
        except (GatewayIndisponivel, TimedOut) as fora_do_ar:
            # Degradação graciosa (ADR-004, R8): o pedido está gravado e continua
            # válido, então o que falta é uma segunda tentativa — não um pedido
            # novo. A observação é escrita para o cliente ler e não carrega nome de
            # fornecedor, código de status nem configuração (`adversarial-006`).
            logger.warning("o gateway de pagamento falhou para %s: %s", pedido_id, fora_do_ar)
            return Resultado(
                encontrados=(_resumir(pedido),),
                observacao=(
                    "não consegui gerar o link de pagamento agora. O pedido está "
                    "registrado; avise o cliente e tente de novo em seguida"
                ),
            ).model_dump_json(exclude_none=True)

        await pedidos.registrar_link(pedido.id, link.url)
        atualizado = pedido.model_copy(update={"url_pagamento": link.url})
        return Resultado(encontrados=(_resumir(atualizado),)).model_dump_json(exclude_none=True)

    async def consultar_pedido(pedido_id: str) -> str:
        pedido = await run_with_timeout(
            pedidos.por_id(pedido_id), timeout_seconds, "leitura do pedido"
        )
        if pedido is None:
            return Resultado(
                nao_encontrados=(pedido_id,),
                observacao="não existe pedido com esse id",
            ).model_dump_json(exclude_none=True)
        return Resultado(encontrados=(_resumir(pedido),)).model_dump_json(exclude_none=True)

    return (
        StructuredTool.from_function(
            coroutine=validar_dados_cliente,
            name="validar_dados_cliente",
            description=(
                "Confere os dados da empresa — razão social, CNPJ, contato e endereço de "
                "entrega — contra o schema do sistema. Use ANTES de criar o pedido, assim "
                "que o cliente informar os dados. Quem decide se um CNPJ é válido é esta "
                "tool, nunca você: não corrija dígito, não complete número e não aceite "
                "valor provisório."
            ),
            args_schema=ValidarDadosCliente,
        ),
        StructuredTool.from_function(
            coroutine=criar_pedido,
            name="criar_pedido",
            description=(
                "Cria o pedido com uma ou mais composições. Revalida cada composição no "
                "servidor contra o catálogo antes de gravar, e recusa o pedido inteiro se "
                "alguma reprovar. Os preços são lidos do banco no momento da criação e o "
                "total que você apresentar é o total_pedido que ela devolver. Use apenas "
                "depois de o cliente confirmar explicitamente."
            ),
            args_schema=CriarPedido,
        ),
        StructuredTool.from_function(
            coroutine=gerar_link_pagamento,
            name="gerar_link_pagamento",
            description=(
                "Cria o link de pagamento de um pedido já criado e devolve a URL. "
                "Chamar duas vezes para o mesmo pedido devolve o MESMO link — nunca um "
                "segundo. O link que você apresentar é o url_pagamento que ela devolver."
            ),
            args_schema=GerarLinkPagamento,
        ),
        StructuredTool.from_function(
            coroutine=consultar_pedido,
            name="consultar_pedido",
            description=(
                "O estado atual de um pedido: status, total e link de pagamento. Use antes "
                "de afirmar qualquer coisa sobre um pedido já criado — inclusive para "
                "responder se houve ou não cobrança."
            ),
            args_schema=ConsultarPedido,
        ),
    )


def _como_empresa(valor: object) -> EmpresaEntrada:
    """O argumento chega como modelo ou como dicionário, conforme o provedor.

    Normalizar aqui, e não confiar no que veio, é o que faz a tool ter o mesmo
    comportamento com Anthropic e com OpenAI — o ADR-012 diz que o código não
    conhece fornecedor, e isto é uma das costuras em que "não conhecer" custa
    duas linhas.
    """
    if isinstance(valor, EmpresaEntrada):
        return valor
    return EmpresaEntrada.model_validate(valor)


def _como_proposta(valor: object) -> ComposicaoProposta:
    if isinstance(valor, ComposicaoProposta):
        return valor
    return ComposicaoProposta.model_validate(valor)


__all__ = [
    "LIMITE_DE_COMPOSICOES",
    "NOMES",
    "ComposicaoProposta",
    "CriarPedido",
    "DadosDoClienteValidados",
    "EmpresaEntrada",
    "EnderecoEntrada",
    "PedidoResumido",
    "ferramentas_de_checkout",
]
