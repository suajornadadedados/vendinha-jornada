"""A DANFE — a metade do documento que uma pessoa lê.

O `MockNFAdapter` existe para a demo e para o quickstart, e a DANFE é a parte dele
que alguém realmente **olha**: o comprador abre o PDF, o operador confere antes de
aprovar. Por isso ela é desenhada nos quadros do leiaute modelo 55 — canhoto,
identificação do emitente, chave de acesso, destinatário, cálculo do imposto,
tabela de produtos, dados adicionais — e não um parágrafo bonito com os mesmos
números. O ADR-004 chama isso de mock de primeira classe; a diferença prática é que
um erro de destinatário salta aos olhos num quadro rotulado e desaparece num
parágrafo.

**A tarja aparece duas vezes, e as duas são deliberadas.** Uma faixa preta no topo
de cada folha, que sobrevive a uma impressão em preto e branco, e uma marca d'água
diagonal, que sobrevive a alguém recortar a folha. Este arquivo circula para fora da
empresa — o contador do comprador é destinatário real dele (`golden-012`) — e um
documento de demonstração que não se anuncia é um documento falso.

**Desenho de baixo nível, de propósito.** `canvas` em vez de `platypus`: o leiaute é
uma grade de caixas com posições fixas, e um framework de fluxo de texto seria uma
camada a mais entre a norma e o que sai no papel. É também o que torna a paginação
explícita — a DANFE numera "Folha 1/2" e a numeração precisa saber quantas folhas
existem **antes** de desenhar a primeira.

**`reportlab` é dependência de produto** (`backend/pyproject.toml`), puro Python e
sem binário externo: o quickstart continua sendo `docker compose up` (RNF-1).
"""

from collections.abc import Sequence
from decimal import Decimal
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as pdfcanvas

from vendinha.documentos import formatar_cnpj
from vendinha.nota.documento import (
    CFOP_VENDA_INTERNA,
    EMITENTE,
    NCM_GENERICO,
    SERIE,
    TARJA,
    TARJA_LONGA,
    UNIDADE_COMERCIAL,
    Autorizacao,
    NotaFiscal,
    formatar_chave,
    inscricao_do_destinatario,
)
from vendinha.pedidos import Endereco, ItemDoPedido, Pedido

LARGURA, ALTURA = A4
MARGEM = 10 * mm
ESQUERDA = MARGEM
DIREITA = LARGURA - MARGEM
UTIL = DIREITA - ESQUERDA

# O rótulo de um quadro é minúsculo e o conteúdo é o que se lê — é assim na DANFE de
# verdade, e é o que faz a grade não competir com o dado.
CORPO = ("Helvetica", 7.5)
ROTULO = ("Helvetica", 5.0)
DESTAQUE = ("Helvetica-Bold", 8.5)
TITULO = ("Helvetica-Bold", 12.0)

ALTURA_DA_LINHA = 4.6 * mm
# Quantos itens cabem na primeira folha e nas seguintes. A primeira carrega o
# cabeçalho inteiro; as demais só a faixa de continuação, então cabem mais.
ITENS_NA_PRIMEIRA = 18
ITENS_POR_FOLHA = 34

# As colunas da tabela de produtos, na ordem do leiaute: rótulo e largura em mm.
COLUNAS: tuple[tuple[str, float, str], ...] = (
    ("CÓDIGO", 26.0, "esquerda"),
    ("DESCRIÇÃO DO PRODUTO / SERVIÇO", 68.0, "esquerda"),
    ("NCM/SH", 16.0, "esquerda"),
    ("CFOP", 12.0, "esquerda"),
    ("UN", 9.0, "esquerda"),
    ("QTD", 14.0, "direita"),
    ("VL. UNIT.", 18.0, "direita"),
    ("VL. TOTAL", 20.0, "direita"),
)


def _real(valor: Decimal) -> str:
    """`1180.00` → `1.180,00`. O documento é brasileiro; o número também."""
    inteiro, _, centavos = f"{valor:.2f}".partition(".")
    negativo = inteiro.startswith("-")
    digitos = inteiro.lstrip("-")
    grupos: list[str] = []
    while len(digitos) > 3:
        grupos.insert(0, digitos[-3:])
        digitos = digitos[:-3]
    grupos.insert(0, digitos)
    return ("-" if negativo else "") + ".".join(grupos) + "," + centavos


def _encurtar(texto: str, largura: float, fonte: tuple[str, float]) -> str:
    """Corta com reticências o que não cabe na coluna.

    Deixar o texto transbordar escreveria por cima da coluna vizinha, e o resultado
    seria um documento em que dois campos se leem como um só — pior do que um nome
    truncado, porque parece correto.
    """
    nome, tamanho = fonte
    if stringWidth(texto, nome, tamanho) <= largura:
        return texto
    while texto and stringWidth(texto + "…", nome, tamanho) > largura:
        texto = texto[:-1]
    return texto + "…"


def _linhas_do_endereco(endereco: Endereco) -> tuple[str, str]:
    """O endereço em duas linhas, como os quadros da DANFE o quebram."""
    complemento = f" - {endereco.complemento}" if endereco.complemento else ""
    return (
        f"{endereco.logradouro}, {endereco.numero}{complemento} - {endereco.bairro}",
        f"{endereco.cidade}/{endereco.uf}  CEP {endereco.cep}",
    )


class _Folha:
    """O canvas e o cursor vertical. Todo desenho passa por aqui.

    Uma classe pequena em vez de passar `(c, y)` por dez funções: o `y` é estado
    mutável que **toda** função de desenho avança, e enfiá-lo em cada assinatura é a
    forma mais barata de esquecer de devolvê-lo em uma delas.
    """

    def __init__(self, buffer: BytesIO) -> None:
        # `pageCompression=0`: o fluxo de conteúdo sai legível dentro do arquivo. Um
        # documento destes tem poucos kilobytes, então a compressão não paga nada — e
        # sem ela dá para conferir a tarja e o destinatário com `grep`, o que é o que
        # `tests/unit/test_nota_fiscal.py` faz em vez de trazer um parser de PDF só
        # para afirmar que a palavra está lá. Documento de demonstração que ninguém
        # consegue inspecionar sem ferramenta é documento que ninguém inspeciona.
        self.c = pdfcanvas.Canvas(buffer, pagesize=A4, pageCompression=0)
        self.c.setTitle(f"DANFE ({TARJA}) - Vendinha")
        self.y = ALTURA - MARGEM

    # ---------------------------------------------------------------- primitivas

    def caixa(self, altura: float, x: float = ESQUERDA, largura: float = UTIL) -> float:
        """Desenha o retângulo e devolve o topo dele. Não move o cursor."""
        topo = self.y
        self.c.rect(x, topo - altura, largura, altura)
        return topo

    def rotulo(self, texto: str, x: float, topo: float) -> None:
        self.c.setFont(*ROTULO)
        self.c.drawString(x + 1.2 * mm, topo - 2.6 * mm, texto)

    def valor(
        self,
        texto: str,
        x: float,
        topo: float,
        *,
        fonte: tuple[str, float] = CORPO,
        largura: float | None = None,
        deslocamento: float = 6.2 * mm,
    ) -> None:
        self.c.setFont(*fonte)
        if largura is not None:
            texto = _encurtar(texto, largura - 2.4 * mm, fonte)
        self.c.drawString(x + 1.2 * mm, topo - deslocamento, texto)

    def campo(
        self,
        rotulo: str,
        valor: str,
        *,
        x: float,
        largura: float,
        topo: float,
        altura: float,
        fonte: tuple[str, float] = CORPO,
    ) -> None:
        """Um quadro rotulado: a unidade de que a DANFE inteira é feita."""
        self.c.rect(x, topo - altura, largura, altura)
        self.rotulo(rotulo, x, topo)
        self.valor(valor, x, topo, fonte=fonte, largura=largura)

    # ------------------------------------------------------------------ a tarja

    def tarja(self) -> None:
        """A faixa preta e a marca d'água. Desenhadas antes do conteúdo.

        Antes, e não depois, para o texto do documento ficar por cima: uma marca
        d'água sobre os números os deixaria ilegíveis, e um documento ilegível é
        recusado em vez de lido — o que anula tanto a tarja quanto o documento.
        """
        self.c.saveState()
        self.c.setFillGray(0.0)
        self.c.rect(0, ALTURA - 7 * mm, LARGURA, 7 * mm, stroke=0, fill=1)
        self.c.setFillGray(1.0)
        self.c.setFont("Helvetica-Bold", 9)
        self.c.drawCentredString(LARGURA / 2, ALTURA - 5 * mm, TARJA_LONGA)
        self.c.restoreState()

        self.c.saveState()
        self.c.setFillGray(0.88)
        self.c.setFont("Helvetica-Bold", 52)
        self.c.translate(LARGURA / 2, ALTURA / 2)
        self.c.rotate(45)
        self.c.drawCentredString(0, 0, TARJA)
        self.c.restoreState()

    # --------------------------------------------------------------- paginação

    def nova_folha(self, numero: int, de: int, nota: NotaFiscal) -> None:
        self.c.showPage()
        self.y = ALTURA - MARGEM
        self.tarja()
        self.y -= 9 * mm
        topo = self.caixa(9 * mm)
        self.rotulo("CONTINUAÇÃO - CHAVE DE ACESSO", ESQUERDA, topo)
        self.valor(formatar_chave(nota.chave), ESQUERDA, topo, fonte=DESTAQUE)
        self.c.setFont(*CORPO)
        self.c.drawRightString(DIREITA - 1.2 * mm, topo - 6.2 * mm, f"FOLHA {numero}/{de}")
        self.y = topo - 9 * mm - 2 * mm


# ------------------------------------------------------------------ os blocos


def _canhoto(folha: _Folha, nota: NotaFiscal) -> None:
    """O recibo de entrega. Primeiro quadro da DANFE, e o primeiro a ser recortado."""
    altura = 12 * mm
    topo = folha.caixa(altura)
    largura_do_recibo = UTIL - 26 * mm

    folha.c.rect(ESQUERDA, topo - altura, largura_do_recibo, altura)
    folha.rotulo(
        "RECEBEMOS DE "
        f"{EMITENTE.razao_social.upper()} OS PRODUTOS CONSTANTES DA NOTA FISCAL INDICADA AO LADO",
        ESQUERDA,
        topo,
    )
    meio = topo - 5 * mm
    folha.c.line(ESQUERDA, meio, ESQUERDA + largura_do_recibo, meio)
    folha.rotulo("DATA DE RECEBIMENTO", ESQUERDA, meio)
    folha.c.line(ESQUERDA + 45 * mm, meio, ESQUERDA + 45 * mm, topo - altura)
    folha.rotulo("IDENTIFICAÇÃO E ASSINATURA DO RECEBEDOR", ESQUERDA + 45 * mm, meio)

    folha.c.setFont(*DESTAQUE)
    folha.c.drawCentredString(DIREITA - 13 * mm, topo - 5 * mm, f"NF-e Nº {nota.numero:09d}")
    folha.c.setFont(*CORPO)
    folha.c.drawCentredString(DIREITA - 13 * mm, topo - 9 * mm, f"SÉRIE {SERIE:03d}")

    folha.y = topo - altura - 2 * mm


def _identificacao(folha: _Folha, nota: NotaFiscal, folhas: int) -> None:
    """Emitente, o bloco DANFE e a chave de acesso — o cabeçalho do documento."""
    altura = 26 * mm
    topo = folha.caixa(altura)
    coluna_emitente = 82 * mm
    coluna_danfe = 34 * mm
    x_danfe = ESQUERDA + coluna_emitente
    x_chave = x_danfe + coluna_danfe

    folha.c.line(x_danfe, topo, x_danfe, topo - altura)
    folha.c.line(x_chave, topo, x_chave, topo - altura)

    folha.c.setFont(*DESTAQUE)
    folha.c.drawString(ESQUERDA + 1.2 * mm, topo - 5 * mm, EMITENTE.nome_fantasia)
    folha.c.setFont(*CORPO)
    linha_um, linha_dois = _linhas_do_endereco(EMITENTE.endereco)
    for deslocamento, texto in enumerate(
        (EMITENTE.razao_social, linha_um, linha_dois, f"CNPJ {formatar_cnpj(EMITENTE.cnpj)}")
    ):
        folha.c.drawString(
            ESQUERDA + 1.2 * mm,
            topo - 9 * mm - deslocamento * 3.6 * mm,
            _encurtar(texto, coluna_emitente - 2.4 * mm, CORPO),
        )

    folha.c.setFont(*TITULO)
    folha.c.drawCentredString(x_danfe + coluna_danfe / 2, topo - 6 * mm, "DANFE")
    folha.c.setFont(*ROTULO)
    for deslocamento, texto in enumerate(
        (
            "DOCUMENTO AUXILIAR DA",
            "NOTA FISCAL ELETRÔNICA",
            "0 - ENTRADA   1 - SAÍDA",
        )
    ):
        folha.c.drawCentredString(
            x_danfe + coluna_danfe / 2, topo - 10 * mm - deslocamento * 3.0 * mm, texto
        )
    folha.c.setFont(*DESTAQUE)
    folha.c.drawCentredString(x_danfe + coluna_danfe / 2, topo - 21 * mm, "1")
    folha.c.setFont(*CORPO)
    folha.c.drawCentredString(
        x_danfe + coluna_danfe / 2,
        topo - 25 * mm,
        f"Nº {nota.numero:09d}  SÉRIE {SERIE:03d}  FL 1/{folhas}",
    )

    largura_da_chave = DIREITA - x_chave
    folha.rotulo("CHAVE DE ACESSO", x_chave, topo)
    folha.c.setFont("Helvetica-Bold", 7.0)
    folha.c.drawCentredString(
        x_chave + largura_da_chave / 2, topo - 7 * mm, formatar_chave(nota.chave)
    )
    folha.c.setFont(*ROTULO)
    folha.c.drawCentredString(
        x_chave + largura_da_chave / 2,
        topo - 12 * mm,
        "Consulta de autenticidade indisponível: documento de demonstração.",
    )
    folha.c.setFont(*CORPO)
    folha.c.drawString(x_chave + 1.2 * mm, topo - 18 * mm, "NATUREZA DA OPERAÇÃO")
    folha.c.setFont(*CORPO)
    folha.c.drawString(x_chave + 1.2 * mm, topo - 22 * mm, "Venda de mercadoria")

    folha.y = topo - altura

    # A faixa de protocolo existe na DANFE de verdade e aqui ela diz a verdade: não
    # há protocolo, porque nenhuma SEFAZ autorizou. Escrever um número plausível
    # seria a única mentira do documento inteiro.
    topo = folha.caixa(8 * mm)
    folha.campo(
        "PROTOCOLO DE AUTORIZAÇÃO DE USO",
        f"NÃO AUTORIZADA - {TARJA_LONGA}",
        x=ESQUERDA,
        largura=UTIL,
        topo=topo,
        altura=8 * mm,
    )
    folha.y = topo - 8 * mm - 2 * mm


def _emitente_fiscal(folha: _Folha) -> None:
    altura = 8 * mm
    topo = folha.caixa(altura)
    largura = UTIL / 3
    for posicao, (rotulo, valor) in enumerate(
        (
            ("INSCRIÇÃO ESTADUAL", EMITENTE.inscricao_estadual),
            ("INSCR. ESTADUAL DO SUBST. TRIBUTÁRIO", ""),
            ("CNPJ", formatar_cnpj(EMITENTE.cnpj)),
        )
    ):
        folha.campo(
            rotulo,
            valor,
            x=ESQUERDA + posicao * largura,
            largura=largura,
            topo=topo,
            altura=altura,
        )
    folha.y = topo - altura - 2 * mm


def _destinatario(folha: _Folha, pedido: Pedido, nota: NotaFiscal) -> None:
    """O quadro do destinatário PJ — o REQ-4 no papel.

    Todo valor sai do pedido, e nenhum é completado aqui. Razão social, CNPJ,
    inscrição estadual e o endereço de entrega que a S-04 passou a exigir por schema
    (P-2 daquela spec) — é este quadro que fecha o furo que o ADR-013 nomeia: o case
    B2C coletava nome, CPF e e-mail para uma nota que precisa de endereço.
    """
    folha.c.setFont(*ROTULO)
    folha.c.drawString(ESQUERDA, folha.y + 0.8 * mm, "DESTINATÁRIO / REMETENTE")

    altura = 8 * mm
    topo = folha.caixa(altura)
    folha.campo(
        "NOME / RAZÃO SOCIAL",
        pedido.empresa.razao_social,
        x=ESQUERDA,
        largura=UTIL - 66 * mm,
        topo=topo,
        altura=altura,
    )
    folha.campo(
        "CNPJ",
        formatar_cnpj(pedido.empresa.cnpj),
        x=DIREITA - 66 * mm,
        largura=36 * mm,
        topo=topo,
        altura=altura,
    )
    folha.campo(
        "DATA DE EMISSÃO",
        f"{nota.emitida_em:%d/%m/%Y}",
        x=DIREITA - 30 * mm,
        largura=30 * mm,
        topo=topo,
        altura=altura,
    )
    folha.y = topo - altura

    linha_um, linha_dois = _linhas_do_endereco(pedido.empresa.endereco)
    topo = folha.caixa(altura)
    folha.campo(
        "ENDEREÇO",
        linha_um,
        x=ESQUERDA,
        largura=UTIL - 60 * mm,
        topo=topo,
        altura=altura,
    )
    folha.campo(
        "MUNICÍPIO / UF / CEP",
        linha_dois,
        x=DIREITA - 60 * mm,
        largura=60 * mm,
        topo=topo,
        altura=altura,
    )
    folha.y = topo - altura

    topo = folha.caixa(altura)
    folha.campo(
        "INSCRIÇÃO ESTADUAL",
        inscricao_do_destinatario(pedido),
        x=ESQUERDA,
        largura=45 * mm,
        topo=topo,
        altura=altura,
    )
    folha.campo(
        "CONTATO",
        pedido.empresa.contato_nome,
        x=ESQUERDA + 45 * mm,
        largura=55 * mm,
        topo=topo,
        altura=altura,
    )
    folha.campo(
        "E-MAIL",
        pedido.empresa.contato_email,
        x=ESQUERDA + 100 * mm,
        largura=UTIL - 100 * mm,
        topo=topo,
        altura=altura,
    )
    folha.y = topo - altura - 2 * mm


def _impostos(folha: _Folha, pedido: Pedido) -> None:
    """O quadro de cálculo do imposto. Zeros de verdade, e o total que o cliente pagou."""
    folha.c.setFont(*ROTULO)
    folha.c.drawString(ESQUERDA, folha.y + 0.8 * mm, "CÁLCULO DO IMPOSTO")

    altura = 8 * mm
    zero = _real(Decimal("0.00"))
    for linha in (
        (
            ("BASE DE CÁLC. DO ICMS", zero),
            ("VALOR DO ICMS", zero),
            ("BASE DE CÁLC. ICMS ST", zero),
            ("VALOR DO ICMS ST", zero),
            ("VALOR TOTAL DOS PRODUTOS", _real(pedido.total)),
        ),
        (
            ("VALOR DO FRETE", zero),
            ("VALOR DO SEGURO", zero),
            ("DESCONTO", zero),
            ("OUTRAS DESPESAS", zero),
            ("VALOR TOTAL DA NOTA", _real(pedido.total)),
        ),
    ):
        topo = folha.caixa(altura)
        largura = UTIL / len(linha)
        for posicao, (rotulo, valor) in enumerate(linha):
            folha.c.rect(ESQUERDA + posicao * largura, topo - altura, largura, altura)
            folha.rotulo(rotulo, ESQUERDA + posicao * largura, topo)
            folha.c.setFont(*(DESTAQUE if rotulo.startswith("VALOR TOTAL") else CORPO))
            folha.c.drawRightString(
                ESQUERDA + (posicao + 1) * largura - 1.2 * mm, topo - 6.2 * mm, valor
            )
        folha.y = topo - altura
    folha.y -= 2 * mm


def _cabecalho_da_tabela(folha: _Folha) -> None:
    folha.c.setFont(*ROTULO)
    folha.c.drawString(ESQUERDA, folha.y + 0.8 * mm, "DADOS DOS PRODUTOS / SERVIÇOS")

    altura = 5 * mm
    topo = folha.caixa(altura)
    x = ESQUERDA
    for rotulo, largura_mm, alinhamento in COLUNAS:
        largura = largura_mm * mm
        folha.c.rect(x, topo - altura, largura, altura)
        folha.c.setFont(*ROTULO)
        if alinhamento == "direita":
            folha.c.drawRightString(x + largura - 1.2 * mm, topo - 3.4 * mm, rotulo)
        else:
            folha.c.drawString(x + 1.2 * mm, topo - 3.4 * mm, rotulo)
        x += largura
    folha.y = topo - altura


def _linha_do_item(folha: _Folha, item: ItemDoPedido) -> None:
    topo = folha.caixa(ALTURA_DA_LINHA)
    celulas = (
        item.produto_id,
        item.nome,
        NCM_GENERICO,
        CFOP_VENDA_INTERNA,
        UNIDADE_COMERCIAL,
        str(item.quantidade),
        _real(item.preco_unitario),
        _real(item.subtotal),
    )
    x = ESQUERDA
    folha.c.setFont(*CORPO)
    for (_, largura_mm, alinhamento), texto in zip(COLUNAS, celulas, strict=True):
        largura = largura_mm * mm
        folha.c.rect(x, topo - ALTURA_DA_LINHA, largura, ALTURA_DA_LINHA)
        escrito = _encurtar(texto, largura - 2.4 * mm, CORPO)
        if alinhamento == "direita":
            folha.c.drawRightString(x + largura - 1.2 * mm, topo - 3.2 * mm, escrito)
        else:
            folha.c.drawString(x + 1.2 * mm, topo - 3.2 * mm, escrito)
        x += largura
    folha.y = topo - ALTURA_DA_LINHA


def _dados_adicionais(folha: _Folha, pedido: Pedido, autorizacao: Autorizacao) -> None:
    """As observações — e a trilha de auditoria impressa no documento (ADR-003)."""
    folha.y -= 2 * mm
    linhas = [
        TARJA_LONGA,
        f"Pedido {pedido.id}.",
        f"Emissão aprovada por {autorizacao.operador} em "
        f"{autorizacao.decidido_em:%d/%m/%Y %H:%M} UTC.",
        *(
            f"Composição {posicao + 1}: "
            f"{composicao.tipo_de_evento.value.replace('_', ' ')} para "
            f"{composicao.pessoas} pessoas - total {_real(composicao.total)}, "
            f"{_real(composicao.valor_por_pessoa)} por pessoa."
            for posicao, composicao in enumerate(pedido.composicoes)
        ),
    ]
    altura = 6 * mm + len(linhas) * 3.4 * mm
    topo = folha.caixa(altura)
    folha.rotulo("DADOS ADICIONAIS / INFORMAÇÕES COMPLEMENTARES", ESQUERDA, topo)
    folha.c.setFont(*CORPO)
    for posicao, linha in enumerate(linhas):
        folha.c.drawString(
            ESQUERDA + 1.2 * mm,
            topo - 5.4 * mm - posicao * 3.4 * mm,
            _encurtar(linha, UTIL - 2.4 * mm, CORPO),
        )
    folha.y = topo - altura


def _todos_os_itens(pedido: Pedido) -> tuple[ItemDoPedido, ...]:
    """As linhas de todas as composições, achatadas, na ordem em que foram gravadas.

    Uma nota tem uma lista de itens; um pedido pode ter várias composições
    (RF-2.3). O agrupamento por composição não se perde — ele vai nos dados
    adicionais, que é onde a DANFE guarda o que não cabe num quadro.
    """
    return tuple(item for composicao in pedido.composicoes for item in composicao.itens)


def _quantas_folhas(itens: Sequence[ItemDoPedido]) -> int:
    if len(itens) <= ITENS_NA_PRIMEIRA:
        return 1
    restantes = len(itens) - ITENS_NA_PRIMEIRA
    return 1 + (restantes + ITENS_POR_FOLHA - 1) // ITENS_POR_FOLHA


def montar_danfe(pedido: Pedido, nota: NotaFiscal, autorizacao: Autorizacao) -> bytes:
    """O PDF inteiro, em memória.

    Devolve `bytes` porque é o que a coluna `bytea` guarda e o que a rota serve. Não
    toca disco: um arquivo temporário aqui seria um caminho a limpar, e um caminho
    que alguém esquece de limpar num contêiner que reinicia.
    """
    itens = _todos_os_itens(pedido)
    folhas = _quantas_folhas(itens)

    buffer = BytesIO()
    folha = _Folha(buffer)
    folha.tarja()
    folha.y -= 9 * mm

    _canhoto(folha, nota)
    _identificacao(folha, nota, folhas)
    _emitente_fiscal(folha)
    _destinatario(folha, pedido, nota)
    _impostos(folha, pedido)
    _cabecalho_da_tabela(folha)

    nesta_folha = 0
    numero_da_folha = 1
    limite = ITENS_NA_PRIMEIRA
    for item in itens:
        if nesta_folha == limite:
            numero_da_folha += 1
            folha.nova_folha(numero_da_folha, folhas, nota)
            _cabecalho_da_tabela(folha)
            nesta_folha, limite = 0, ITENS_POR_FOLHA
        _linha_do_item(folha, item)
        nesta_folha += 1

    _dados_adicionais(folha, pedido, autorizacao)

    folha.c.showPage()
    folha.c.save()
    return buffer.getvalue()


__all__ = ["montar_danfe"]
