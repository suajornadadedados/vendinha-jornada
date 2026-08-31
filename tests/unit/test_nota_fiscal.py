"""R8 — o mock emite um documento fiel, e a fidelidade é afirmada, não prometida.

O ADR-004 pede **mock como cidadão de primeira classe**, e o RF-3.4 diz o que isso
significa aqui: XML e DANFE fiéis ao leiaute NF-e modelo 55, com tarja
`SEM VALOR FISCAL` e destinatário PJ. Este arquivo é a diferença entre ter escrito
isso e ter feito isso.

**O que se afirma, e por que cada coisa.** A S-04 aprendeu na ressalva A-1 que
projetar sete campos e testar um deles é testar nada: o pedido persistido tinha
`preco_unitario` conferido e o resto no escuro. A nota tem a mesma forma de risco —
ela projeta o pedido inteiro para dentro de um documento que sai da empresa — então
aqui o destinatário é conferido **campo a campo**, e cada linha do pedido é
procurada na nota.

**O valor esperado vem da fixture, nunca do código** (`docs/testes.md` §4). Nenhuma
asserção recalcula um total: ela compara com o número que o pedido de teste declara.

**Nada real** (RNF-7). A compradora é a `empresa_valida` de `tests/conftest.py`, o
emitente é fabricado em `nota/documento.py`, e nenhum certificado existe — o mock
não assina, e é exatamente essa a diferença entre este documento e um com valor
fiscal. Ninguém vai preenchê-la: não há segundo adapter (ADR-004).
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from xml.etree import ElementTree as ET

import pytest

from vendinha import runtime
from vendinha.composicao import TipoDeEvento
from vendinha.documentos import formatar_cnpj
from vendinha.nota import (
    EMITENTE,
    ISENTO,
    MODELO,
    SERIE,
    TARJA,
    TARJA_LONGA,
    Autorizacao,
    MockNFAdapter,
    NotaEmitida,
    agora,
    chave_confere,
    formatar_chave,
)
from vendinha.nota.documento import (
    CODIGO_DA_UF,
    IND_IE_CONTRIBUINTE,
    IND_IE_NAO_CONTRIBUINTE,
    chave_de_acesso,
)
from vendinha.nota.xml import NS
from vendinha.pedidos import ComposicaoDoPedido, Empresa, ItemDoPedido, Pedido

pytestmark = pytest.mark.requires_backend

NUMERO = 4242
OPERADOR = "ana.souza"

# As duas linhas do pedido de teste, com os números escritos aqui e em nenhum outro
# lugar. São eles que as asserções comparam — recalcular a partir do que o código
# devolveu seria o teste tautológico que `docs/testes.md` §4 recusa.
LINHAS = (
    ("cafe-moido-tradicional", "Cafe moido tradicional para coador", 2, "39.00", "78.00"),
    ("requeijao-de-corte", "Requeijao de corte", 3, "44.00", "132.00"),
)
TOTAL = Decimal("210.00")
PESSOAS = 20

# A chave de acesso esperada, escrita à mão — e o `EMITIDA_EM` pinado é o que a torna
# escrevível: os quatro dígitos `AAMM` saem da data de emissão, então sem uma data
# fixa o valor esperado mudaria de mês em mês.
#
#   31 | 2608 | 22333444000181 | 55 | 001 | 000004242 | 1 | 60219664 | 8
#   UF   AAMM   CNPJ emitente   mod  série   nNF      tp    cNF       DV
#
# O DV foi conferido FORA do repositório, com o módulo 11 montado de outro jeito —
# lista de pesos explícita em vez de contador incremental: soma 608, resto 3, DV 8.
# É isso que `docs/testes.md` §4 chama de "valor esperado vem de fonte independente",
# e é o que faltava aqui (ressalva A-3 da verificação da S-05).
PEDIDO_DA_CHAVE = "pedido-da-nota"
EMITIDA_EM = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
CHAVE_ESPERADA = "31260822333444000181550010000042421602196648"

# As duas linhas do endereço, como a DANFE as imprime. Literais de propósito: são o
# valor ESPERADO, e derivá-las do mesmo helper que o código usa seria recalcular a
# conta do produto dentro do teste.
ENDERECO_NA_DANFE = (
    "Rua das Acacias, 240 - sala 12 - Savassi",
    "Belo Horizonte/MG  CEP 30140-071",
)


def _itens() -> tuple[ItemDoPedido, ...]:
    return tuple(
        ItemDoPedido(
            produto_id=produto_id,
            nome=nome,
            tipo="cafe",
            rendimento=14,
            quantidade=quantidade,
            preco_unitario=Decimal(preco),
            subtotal=Decimal(subtotal),
        )
        for produto_id, nome, quantidade, preco, subtotal in LINHAS
    )


def _pedido(empresa: Empresa) -> Pedido:
    itens = _itens()
    return Pedido(
        id="pedido-da-nota",
        empresa=empresa,
        composicoes=(
            ComposicaoDoPedido(
                tipo_de_evento=TipoDeEvento.CAFE_DA_MANHA,
                pessoas=PESSOAS,
                itens=itens,
                total=TOTAL,
                valor_por_pessoa=Decimal("10.50"),
            ),
        ),
        total=TOTAL,
    )


@pytest.fixture
def empresa(empresa_valida: dict[str, Any]) -> Empresa:
    """A compradora do `tests/conftest.py`, sem inscrição estadual — o caso comum."""
    return Empresa.model_validate(empresa_valida)


@pytest.fixture
def pedido(empresa: Empresa) -> Pedido:
    return _pedido(empresa)


@pytest.fixture
def emitida(pedido: Pedido) -> NotaEmitida:
    return runtime.run(
        MockNFAdapter().emitir(pedido, NUMERO, Autorizacao(operador=OPERADOR, decidido_em=agora()))
    )


def _raiz(emitida: NotaEmitida) -> ET.Element:
    """O XML parseado. Bytes e não `str`: a declaração diz UTF-8, e ela é verdade.

    O `noqa` é sobre `defusedxml`: aqui a entrada é o XML que o nosso próprio
    emissor acabou de produzir, três linhas acima, e não texto vindo de fora.
    """
    return ET.fromstring(emitida.xml.encode("utf-8"))  # noqa: S314


def _texto(no: ET.Element, caminho: str) -> str:
    encontrado = no.find("/".join(f"{{{NS}}}{parte}" for parte in caminho.split("/")))
    assert encontrado is not None, f"o XML não tem {caminho}"
    return (encontrado.text or "").strip()


def _itens_do_xml(emitida: NotaEmitida) -> Iterator[ET.Element]:
    return iter(_raiz(emitida).iter(f"{{{NS}}}prod"))


# ------------------------------------------------------------ o destinatário PJ


@pytest.mark.risco("R8")
def test_the_recipient_is_the_company_the_order_carries_field_by_field(
    emitida: NotaEmitida, pedido: Pedido
) -> None:
    """R8, RF-3.4, ADR-013 — o destinatário PJ, conferido campo a campo.

    É o furo que o pivô B2B fechou: o case B2C coletava nome, CPF e e-mail para uma
    DANFE modelo 55 que exige endereço de destinatário. Conferir só a razão social
    aqui repetiria a ressalva A-1 da S-04 — projetar sete campos e afirmar sobre um.
    """
    dest = _raiz(emitida).find(f"{{{NS}}}NFe/{{{NS}}}infNFe/{{{NS}}}dest")
    assert dest is not None

    endereco = pedido.empresa.endereco
    assert _texto(dest, "CNPJ") == pedido.empresa.cnpj
    assert _texto(dest, "xNome") == pedido.empresa.razao_social
    assert _texto(dest, "email") == pedido.empresa.contato_email
    assert _texto(dest, "enderDest/xLgr") == endereco.logradouro
    assert _texto(dest, "enderDest/nro") == endereco.numero
    assert _texto(dest, "enderDest/xCpl") == endereco.complemento
    assert _texto(dest, "enderDest/xBairro") == endereco.bairro
    assert _texto(dest, "enderDest/xMun") == endereco.cidade
    assert _texto(dest, "enderDest/UF") == endereco.uf
    assert _texto(dest, "enderDest/CEP") == endereco.cep.replace("-", "")


@pytest.mark.risco("R8")
def test_a_company_without_state_registration_is_issued_as_exempt(
    emitida: NotaEmitida,
) -> None:
    """R8, RF-3.4 — sem IE a nota sai `ISENTO`, e não em branco.

    É a decisão da S-05 de deixar a inscrição estadual opcional: não contribuinte é
    a situação normal de boa parte das compradoras de um café da manhã. Em branco
    seria um campo obrigatório vazio; `ISENTO` é o que a norma manda imprimir.
    """
    dest = _raiz(emitida).find(f"{{{NS}}}NFe/{{{NS}}}infNFe/{{{NS}}}dest")
    assert dest is not None

    assert _texto(dest, "IE") == ISENTO
    assert _texto(dest, "indIEDest") == str(IND_IE_NAO_CONTRIBUINTE)
    assert ISENTO.encode() in emitida.danfe


@pytest.mark.risco("R8")
def test_a_company_with_state_registration_is_issued_as_a_taxpayer(
    empresa: Empresa,
) -> None:
    """R8, RF-3.4 — informada, a IE vai para os dois artefatos e muda o indicador.

    Sem esta metade o teste acima passaria com um emissor que ignorasse a inscrição
    estadual por completo, e o `golden-011` — que rejeita a nota justamente por IE —
    estaria rejeitando um campo que a nota nunca carregou.
    """
    inscricao = "0011223344556"
    contribuinte = empresa.model_copy(update={"inscricao_estadual": inscricao})
    emitida = runtime.run(
        MockNFAdapter().emitir(
            _pedido(contribuinte), NUMERO, Autorizacao(operador=OPERADOR, decidido_em=agora())
        )
    )

    dest = _raiz(emitida).find(f"{{{NS}}}NFe/{{{NS}}}infNFe/{{{NS}}}dest")
    assert dest is not None

    assert _texto(dest, "IE") == inscricao
    assert _texto(dest, "indIEDest") == str(IND_IE_CONTRIBUINTE)
    assert inscricao.encode() in emitida.danfe


# --------------------------------------------------------- a chave e a numeração


@pytest.mark.risco("R8")
def test_the_access_key_is_the_one_written_down_here_digit_by_digit() -> None:
    """R8, RF-3.4 — a chave é calculada, e o esperado NÃO sai do código.

    **Esta asserção era tautológica e a verificação independente da S-05 a derrubou**
    (ressalva A-3): ela fazia `chave[-1] == digito_da_chave(chave[:43])`, chamando a
    mesma função que gera o dígito. Fazer `digito_da_chave` devolver sempre `"0"`
    deixava a suíte inteira verde — exatamente o defeito que `docs/testes.md` §4
    nomeia com todas as letras: *a função do produto não pode ser a régua dela mesma*.

    O que vale agora é `CHAVE_ESPERADA`, escrita à mão neste arquivo. O dígito `8`
    foi conferido fora do repositório, com o módulo 11 montado de outro jeito (lista
    de pesos explícita em vez de contador incremental): soma 608, resto 3, DV 8. Cada
    fatia está comentada, então uma troca de ordem dos campos reprova aqui.

    A data é **pinada** porque a chave carrega o `AAMM` da emissão — sem isso o valor
    esperado mudaria de mês em mês, e um teste que muda sozinho não é uma régua.
    """
    chave = chave_de_acesso(pedido_id=PEDIDO_DA_CHAVE, numero=NUMERO, emitida_em=EMITIDA_EM)

    assert chave == CHAVE_ESPERADA
    assert len(chave) == 44
    assert chave.isdigit()


@pytest.mark.risco("R8")
def test_the_slices_of_the_access_key_are_the_ones_the_norm_defines(
    emitida: NotaEmitida,
) -> None:
    """R8 — as posições, conferidas sobre a chave que o sistema realmente emitiu.

    `chave_confere` continua aqui, e continua sendo tautológico sozinho — é por isso
    que ele **não é a asserção principal de nenhum teste**. Ele vale como afirmação
    de que a chave emitida em runtime tem a mesma forma da que o teste acima prendeu.
    """
    chave = emitida.nota.chave

    assert chave_confere(chave)
    assert chave[:2] == f"{CODIGO_DA_UF:02d}"
    assert chave[6:20] == EMITENTE.cnpj
    assert chave[20:22] == str(MODELO)
    assert chave[22:25] == f"{SERIE:03d}"
    assert chave[25:34] == f"{NUMERO:09d}"


@pytest.mark.risco("R8")
def test_the_access_key_carries_the_issuer_the_model_and_the_invoice_number(
    emitida: NotaEmitida,
) -> None:
    """R8 — as posições da chave são as que a SEFAZ define, e não uma ordem nossa.

    Uma chave com verificador correto e os campos embaralhados passaria no teste
    acima. Aqui as fatias são conferidas uma a uma contra o que a norma põe em cada
    posição.
    """
    chave = emitida.nota.chave

    assert chave[6:20] == EMITENTE.cnpj
    assert chave[20:22] == str(MODELO)
    assert chave[22:25] == f"{SERIE:03d}"
    assert chave[25:34] == f"{NUMERO:09d}"
    assert chave[34] == "1", "tpEmis: emissão normal"


@pytest.mark.risco("R8")
def test_the_invoice_number_comes_from_outside_the_adapter(
    emitida: NotaEmitida,
) -> None:
    """R8, ADR-001 — numeração é fato de banco, e o adapter apenas a recebe.

    Deixá-la no adapter faria dois adapters numerarem de dois jeitos, e qualquer
    emissor herdaria uma responsabilidade que é do `fiscal.py` — onde ela sai de uma
    sequência do Postgres, que é a coisa que processo concorrente faz errado e banco
    faz certo.
    """
    assert emitida.nota.numero == NUMERO
    assert emitida.nota.serie == SERIE

    raiz = _raiz(emitida)
    assert _texto(raiz, "NFe/infNFe/ide/nNF") == str(NUMERO)
    assert _texto(raiz, "NFe/infNFe/ide/mod") == str(MODELO)


@pytest.mark.risco("R8")
def test_the_xml_and_the_danfe_speak_of_the_same_invoice(emitida: NotaEmitida) -> None:
    """R8 — os dois artefatos concordam, que é o que faz o mock ser um documento.

    Uma DANFE cuja chave não bate com a do XML é o artefato que passa despercebido
    numa demo e reprova numa conferência — dois arquivos parecidos em vez de duas
    representações da mesma nota.
    """
    chave = emitida.nota.chave

    inf = _raiz(emitida).find(f"{{{NS}}}NFe/{{{NS}}}infNFe")
    assert inf is not None
    assert inf.get("Id") == f"NFe{chave}", "o Id do XML tem que ser `NFe` + a chave"
    assert _texto(_raiz(emitida), "NFe/infNFe/ide/cDV") == chave[-1]

    # A DANFE imprime a chave em grupos de quatro. Procurar a string formatada é o
    # que prova que é a MESMA chave, e não outra com a mesma forma.
    assert formatar_chave(chave).encode() in emitida.danfe


# ------------------------------------------------------------------- as linhas


@pytest.mark.risco("R8")
def test_every_line_of_the_order_becomes_a_line_of_the_invoice(
    emitida: NotaEmitida,
) -> None:
    """R8, R1 — cada linha da nota é a linha gravada no pedido, campo a campo.

    Os valores esperados vêm de `LINHAS`, declarada no topo — não do pedido que o
    teste construiu nem de uma soma refeita aqui. É a lição da A-1 da S-04: o teste
    que recalcula a mesma conta que o código nunca discorda dele.
    """
    produtos = list(_itens_do_xml(emitida))
    assert len(produtos) == len(LINHAS)

    for produto, (produto_id, nome, quantidade, preco, subtotal) in zip(
        produtos, LINHAS, strict=True
    ):
        assert _texto(produto, "cProd") == produto_id
        assert _texto(produto, "xProd") == nome
        assert Decimal(_texto(produto, "qCom")) == quantidade
        assert Decimal(_texto(produto, "vUnCom")) == Decimal(preco)
        assert Decimal(_texto(produto, "vProd")) == Decimal(subtotal)
        # A coerência interna que denuncia uma linha dizendo "1 unidade a R$ 44,00,
        # subtotal R$ 132,00" — a mesma asserção que fechou a A-1 da S-04.
        assert Decimal(preco) * quantidade == Decimal(subtotal)


@pytest.mark.risco("R8")
def test_the_total_of_the_invoice_is_the_total_of_the_order_and_is_never_recomputed(
    emitida: NotaEmitida,
) -> None:
    """R1, ADR-001 — o total sai do pedido, não de uma soma feita na emissão.

    Somar de novo aqui criaria a segunda conta: o cliente confirmou um número, pagou
    esse número, e a nota sairia com o que a emissão calculou. Duas contas para o
    mesmo fato é a definição do que a regra de ouro existe para impedir.
    """
    raiz = _raiz(emitida)

    assert emitida.nota.total == TOTAL
    assert Decimal(_texto(raiz, "NFe/infNFe/total/ICMSTot/vNF")) == TOTAL
    assert Decimal(_texto(raiz, "NFe/infNFe/total/ICMSTot/vProd")) == TOTAL
    assert Decimal(_texto(raiz, "NFe/infNFe/pag/detPag/vPag")) == TOTAL


# ------------------------------------------------------- a tarja e a auditoria


@pytest.mark.risco("R8")
def test_both_artifacts_announce_that_they_have_no_fiscal_value(
    emitida: NotaEmitida,
) -> None:
    """R8, RF-3.4 — a tarja está nos dois, porque os dois circulam.

    O comprador manda estes arquivos para a contabilidade dele (`golden-012`). Um
    documento de demonstração que não se anuncia é um documento falso — e o XML é
    justamente o que uma máquina lê sem ninguém olhar a marca d'água.
    """
    raiz = _raiz(emitida)

    assert TARJA in _texto(raiz, "NFe/infNFe/infAdic/infCpl")
    assert TARJA.encode() in emitida.danfe
    # Sem "NÃO": no fluxo do PDF os acentuados saem em octal (`\303`), então a
    # asserção fica na parte ASCII da mesma frase. O que ela prova é o mesmo — a
    # faixa de protocolo diz que não há protocolo, em vez de inventar um número
    # plausível, que seria a única mentira do documento inteiro.
    assert b"AUTORIZADA - " + TARJA_LONGA.encode() in emitida.danfe


@pytest.mark.risco("R3")
def test_the_operator_who_approved_travels_inside_the_document(
    emitida: NotaEmitida,
) -> None:
    """R3, ADR-003 — a trilha de auditoria vai junto do artefato, não só na tabela.

    A tabela é nossa e fica aqui; o documento vai embora. Seis meses depois, quem
    abrir o XML longe do nosso banco continua conseguindo responder quem liberou
    aquela emissão.
    """
    raiz = _raiz(emitida)

    assert OPERADOR in _texto(raiz, "NFe/infNFe/infAdic/infCpl")
    assert emitida.nota.aprovada_por == OPERADOR
    assert OPERADOR.encode() in emitida.danfe


@pytest.mark.risco("R8")
def test_the_danfe_is_a_pdf_a_reader_actually_opens(emitida: NotaEmitida) -> None:
    """R8, ADR-004 — `b"pdf falso"` passaria em todo teste de contrato.

    E entregaria ao contador da empresa compradora um arquivo que não abre — que é a
    mesma falha do link de pagamento que terminava em 404 (D-6 da S-04). Aqui se
    afirma a estrutura mínima que um leitor exige.
    """
    assert emitida.danfe.startswith(b"%PDF-")
    assert emitida.danfe.rstrip().endswith(b"%%EOF")
    assert b"/Type /Catalog" in emitida.danfe
    assert b"/Type /Page" in emitida.danfe


@pytest.mark.risco("R8")
def test_the_issuer_is_fabricated_and_printed_on_the_danfe(emitida: NotaEmitida) -> None:
    """RNF-7 — nem o emitente é real, e o documento mostra qual loja está emitindo."""
    assert EMITENTE.razao_social.encode() in emitida.danfe
    assert formatar_cnpj(EMITENTE.cnpj).encode() in emitida.danfe
    assert _texto(_raiz(emitida), "NFe/infNFe/emit/CNPJ") == EMITENTE.cnpj


@pytest.mark.risco("R8")
def test_an_order_with_many_lines_paginates_instead_of_overflowing_the_page(
    empresa: Empresa,
) -> None:
    """R8 — uma nota com muitas linhas vira folhas, e as folhas se numeram.

    Um pedido corporativo com três composições passa fácil de vinte linhas, e uma
    tabela que continuasse desenhando abaixo da margem produziria um PDF em que os
    últimos itens simplesmente não existem — o pior defeito possível num documento
    fiscal, porque ele é invisível.
    """
    itens = tuple(
        ItemDoPedido(
            produto_id=f"produto-{posicao:02d}",
            nome=f"Produto de teste numero {posicao}",
            tipo="cafe",
            rendimento=10,
            quantidade=1,
            preco_unitario=Decimal("10.00"),
            subtotal=Decimal("10.00"),
        )
        for posicao in range(25)
    )
    total = Decimal("250.00")
    grande = Pedido(
        id="pedido-com-muitas-linhas",
        empresa=empresa,
        composicoes=(
            ComposicaoDoPedido(
                tipo_de_evento=TipoDeEvento.CAFE_DA_MANHA,
                pessoas=PESSOAS,
                itens=itens,
                total=total,
                valor_por_pessoa=Decimal("12.50"),
            ),
        ),
        total=total,
    )

    emitida = runtime.run(
        MockNFAdapter().emitir(grande, NUMERO, Autorizacao(operador=OPERADOR, decidido_em=agora()))
    )

    assert emitida.danfe.count(b"/Type /Page\n") >= 2, "a segunda folha não foi criada"
    assert b"FL 1/2" in emitida.danfe
    assert b"FOLHA 2/2" in emitida.danfe
    # O último item existe no papel, e não só no XML.
    assert b"produto-24" in emitida.danfe
    assert len(list(_itens_do_xml(emitida))) == len(itens)


@pytest.mark.risco("R8")
def test_the_endereco_of_the_recipient_survives_a_missing_complement(
    empresa: Empresa,
) -> None:
    """R8 — endereço sem complemento é endereço normal, não endereço incompleto.

    `xCpl` é opcional no leiaute e o schema do pedido também o deixa opcional. Um
    emissor que escrevesse a tag vazia produziria um XML que alguns validadores
    recusam, por um campo que ninguém precisava ter.
    """
    sem_complemento = empresa.model_copy(
        update={"endereco": empresa.endereco.model_copy(update={"complemento": None})}
    )
    emitida = runtime.run(
        MockNFAdapter().emitir(
            _pedido(sem_complemento), NUMERO, Autorizacao(operador=OPERADOR, decidido_em=agora())
        )
    )

    dest = _raiz(emitida).find(f"{{{NS}}}NFe/{{{NS}}}infNFe/{{{NS}}}dest")
    assert dest is not None
    assert dest.find(f"{{{NS}}}enderDest/{{{NS}}}xCpl") is None


# ------------------------------------- a DANFE, provada como o XML já era (A-1, A-2)
#
# A verificação independente da S-05 trocou razão social, CNPJ e endereço do
# destinatário na DANFE pelos do EMITENTE, e as 898 asserções ficaram verdes. O XML
# tinha onze asserções campo a campo; o PDF não tinha nenhuma — a única cobertura era
# acidental, porque a asserção de IE procurava uma string que por acaso mora naquele
# quadro.
#
# É o mesmo defeito que a A-1 da S-04 nomeou — *projetar sete campos e afirmar sobre
# um* — e ele voltou no outro artefato. O que segue fecha os dois lados: o documento
# que a contabilidade da compradora recebe é conferido com o mesmo rigor dos dois
# jeitos em que ele existe.
#
# Os `in` sobre bytes funcionam por causa da D-11 (`pageCompression=0`): o fluxo de
# conteúdo do PDF sai legível. Foi para isto que aquela decisão foi tomada.


@pytest.mark.risco("R8")
def test_the_danfe_prints_the_buying_company_field_by_field(
    emitida: NotaEmitida, pedido: Pedido
) -> None:
    """R8, RF-3.4, ADR-013 — o destinatário do PDF é a compradora, campo a campo.

    A quebra que este teste existe para pegar é sutil e cara: a DANFE nomeando o
    **emitente** no quadro do destinatário. O documento continua bonito, o XML
    continua certo, e o operador aprova uma nota que diz que a Vendinha comprou de si
    mesma. Procurar os dados **da compradora** é o que a pega — eles somem do arquivo
    inteiro quando a troca acontece.
    """
    danfe = emitida.danfe

    assert pedido.empresa.razao_social.encode() in danfe
    assert formatar_cnpj(pedido.empresa.cnpj).encode() in danfe
    assert pedido.empresa.contato_nome.encode() in danfe
    assert pedido.empresa.contato_email.encode() in danfe
    assert ISENTO.encode() in danfe, "sem IE informada, o quadro imprime ISENTO"

    for linha in ENDERECO_NA_DANFE:
        assert linha.encode() in danfe, f"o endereço de entrega não saiu na DANFE: {linha!r}"


@pytest.mark.risco("R8")
def test_the_danfe_carries_the_watermark_and_the_banner_and_not_only_a_footnote(
    emitida: NotaEmitida,
) -> None:
    """R8, RF-3.4 — a tarja está nos dois lugares que o documento promete.

    `danfe.py` argumenta que a tarja aparece duas vezes de propósito: uma **faixa
    preta** no topo, que sobrevive a uma impressão em preto e branco, e uma **marca
    d'água** diagonal, que sobrevive a alguém recortar a folha. A verificação
    independente removeu as duas e a suíte ficou verde — o que segurava a asserção
    antiga era uma menção lateral no quadro de protocolo, que existe para dizer outra
    coisa (ressalva A-1).

    A aritmética é a parte que precisa de explicação, e ela é o que dá precisão:

    * `TARJA_LONGA` sai em **três** lugares — faixa preta, quadro de protocolo e
      dados adicionais;
    * `TARJA` sozinha (fora da longa) sai em **dois** — marca d'água e título do PDF.

    Remover a faixa derruba a primeira contagem; remover a marca d'água ou o título
    derruba a segunda. É isso que a asserção de contagem compra sobre um `in` simples,
    e é por isso que ela vale a rigidez.
    """
    danfe = emitida.danfe
    longas = danfe.count(TARJA_LONGA.encode())
    sozinhas = danfe.count(TARJA.encode()) - longas

    assert longas == 3, "faixa preta, quadro de protocolo e dados adicionais"
    assert sozinhas == 2, "marca d'água diagonal e título do PDF"


@pytest.mark.risco("R8")
def test_the_danfe_prints_the_lines_of_the_order_with_their_numbers(
    emitida: NotaEmitida,
) -> None:
    """R8, R1 — a tabela de produtos do PDF traz as mesmas linhas que o XML.

    Os valores vêm de `LINHAS`, e o formato é o **brasileiro** que a DANFE imprime —
    `78,00` e não `78.00`. Sem isto um erro de formatação de moeda no PDF passaria: o
    XML usa ponto decimal, e nenhuma asserção olhava a vírgula.

    **Não se afirma sobre o `produto_id`**, e a razão é uma limitação real de leiaute:
    a coluna `CÓDIGO` tem 26 mm e `_encurtar` corta com reticências o que não cabe —
    `cafe-moido-tradicional` sai truncado, `requeijao-de-corte` não. O código completo
    está no `cProd` do XML, que é onde uma máquina o lê; no papel o que identifica a
    linha para uma pessoa é o nome, e é sobre ele que este teste afirma.
    """
    danfe = emitida.danfe

    for _, nome, _, preco, subtotal in LINHAS:
        assert nome.encode() in danfe
        assert preco.replace(".", ",").encode() in danfe
        assert subtotal.replace(".", ",").encode() in danfe

    # O total do pedido, no formato do papel. É o número que o operador confere
    # contra a fila antes de aprovar.
    assert f"{TOTAL:.2f}".replace(".", ",").encode() in danfe
