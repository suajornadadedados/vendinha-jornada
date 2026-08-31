"""O XML da NF-e modelo 55 — a metade do documento que uma máquina lê.

**Por que XML de verdade e não um arquivo com cara de XML.** O ADR-004 pede mock
como cidadão de primeira classe, e o destinatário deste artefato é o contador da
empresa compradora (`golden-012`). Um arquivo que o sistema dele recusa abrir seria
o equivalente fiscal do link de pagamento que termina em 404 — a falha que a D-6 da
S-04 nomeia. Então a estrutura é a do leiaute 4.00: `nfeProc > NFe > infNFe` com
`ide`, `emit`, `dest`, `det` por item, `total`, `transp`, `pag` e `infAdic`.

**O que ele deliberadamente não é.** Não é assinado — assinatura exige certificado
digital, e certificado real jamais entra neste repositório (RNF-7). Não tem
protocolo de autorização, porque nenhuma SEFAZ o autorizou. Os dois faltam de
propósito, e são exatamente a diferença entre este documento e um com valor fiscal —
diferença que este projeto declara em vez de fingir cobrir (ADR-004).

**`tpAmb=2` (homologação), e uma divergência declarada.** A norma manda que em
homologação a razão social do destinatário seja substituída pela frase de aviso. Aqui
ela **não** é: o REQ-4 existe para mostrar o destinatário PJ real do pedido — razão
social, CNPJ, inscrição estadual e endereço —, e apagá-lo devolveria o furo que o
ADR-013 fechou. O aviso vai em `infCpl`, que é onde ele não custa o requisito.

**Tributação é forma, não fato.** `NCM`, `CFOP` e o CST de ICMS são fixos e estão
comentados em `documento.py`: este projeto modela comida, não tributação. Deduzir
um NCM por produto seria fato de negócio nascendo do nada — o que a regra de ouro
proíbe (ADR-001).
"""

from decimal import Decimal
from xml.etree import ElementTree as ET

from vendinha.documentos import formatar_cnpj
from vendinha.nota.documento import (
    CFOP_VENDA_INTERNA,
    CODIGO_DA_UF,
    EMITENTE,
    MODELO,
    NCM_GENERICO,
    SERIE,
    TARJA_LONGA,
    UNIDADE_COMERCIAL,
    Autorizacao,
    NotaFiscal,
    codigo_numerico,
    indicador_de_ie,
    inscricao_do_destinatario,
)
from vendinha.pedidos import Endereco, ItemDoPedido, Pedido

NS = "http://www.portalfiscal.inf.br/nfe"
VERSAO = "4.00"

# Ambiente de homologação. Ver a nota no docstring do módulo: o mock não é produção
# nem homologação de verdade, e `2` é a única das duas opções que não afirma o que
# seria falso.
AMBIENTE_DE_HOMOLOGACAO = "2"

# Belo Horizonte. O `cMunFG` é o município de ocorrência do fato gerador, que é o do
# emitente — não o da entrega.
CODIGO_DO_MUNICIPIO_DO_EMITENTE = "3106200"

ZERO = Decimal("0.00")


def _dinheiro(valor: Decimal) -> str:
    """Duas casas e ponto decimal, que é como o leiaute pede. `Decimal` até o fim."""
    return f"{valor:.2f}"


def _quantidade(valor: int) -> str:
    return f"{Decimal(valor):.4f}"


def _filho(pai: ET.Element, tag: str, texto: str | None = None) -> ET.Element:
    elemento = ET.SubElement(pai, f"{{{NS}}}{tag}")
    if texto is not None:
        elemento.text = texto
    return elemento


def _endereco(
    pai: ET.Element, tag: str, endereco: Endereco, municipio: str, fone: str = ""
) -> None:
    """O bloco de endereço, idêntico para emitente e destinatário.

    O código do município é o do emitente nos dois lugares, e isso é uma limitação
    declarada: traduzir cidade+UF em código IBGE exige a tabela do IBGE, que seria
    um segundo catálogo para manter. Está aqui em vez de escondido porque um mock
    que mente sobre o que não sabe é pior do que um mock que declara o buraco.
    """
    bloco = _filho(pai, tag)
    _filho(bloco, "xLgr", endereco.logradouro)
    _filho(bloco, "nro", endereco.numero)
    if endereco.complemento:
        _filho(bloco, "xCpl", endereco.complemento)
    _filho(bloco, "xBairro", endereco.bairro)
    _filho(bloco, "cMun", municipio)
    _filho(bloco, "xMun", endereco.cidade)
    _filho(bloco, "UF", endereco.uf)
    _filho(bloco, "CEP", endereco.cep.replace("-", ""))
    _filho(bloco, "cPais", "1058")
    _filho(bloco, "xPais", "BRASIL")
    if fone:
        _filho(bloco, "fone", fone)


def _emitente(pai: ET.Element) -> None:
    emit = _filho(pai, "emit")
    _filho(emit, "CNPJ", EMITENTE.cnpj)
    _filho(emit, "xNome", EMITENTE.razao_social)
    _filho(emit, "xFant", EMITENTE.nome_fantasia)
    _endereco(emit, "enderEmit", EMITENTE.endereco, CODIGO_DO_MUNICIPIO_DO_EMITENTE)
    _filho(emit, "IE", EMITENTE.inscricao_estadual)
    _filho(emit, "CRT", "3")


def _destinatario(pai: ET.Element, pedido: Pedido) -> None:
    """O destinatário PJ, campo a campo, vindo do pedido (REQ-4).

    Cada valor aqui foi coletado pelo agente, validado por `pedidos.Empresa` e
    gravado na criação do pedido. Nenhum é recalculado, completado ou inferido na
    emissão: a nota carrega o que foi combinado, e é por isso que a S-04 recusou
    afrouxar o schema do endereço (P-2 daquela spec).
    """
    dest = _filho(pai, "dest")
    _filho(dest, "CNPJ", pedido.empresa.cnpj)
    _filho(dest, "xNome", pedido.empresa.razao_social)
    _endereco(dest, "enderDest", pedido.empresa.endereco, CODIGO_DO_MUNICIPIO_DO_EMITENTE)
    _filho(dest, "indIEDest", str(indicador_de_ie(pedido)))
    _filho(dest, "IE", inscricao_do_destinatario(pedido))
    _filho(dest, "email", pedido.empresa.contato_email)


def _item(pai: ET.Element, posicao: int, item: ItemDoPedido) -> None:
    det = _filho(pai, "det")
    det.set("nItem", str(posicao))

    prod = _filho(det, "prod")
    _filho(prod, "cProd", item.produto_id)
    _filho(prod, "cEAN", "SEM GTIN")
    _filho(prod, "xProd", item.nome)
    _filho(prod, "NCM", NCM_GENERICO)
    _filho(prod, "CFOP", CFOP_VENDA_INTERNA)
    _filho(prod, "uCom", UNIDADE_COMERCIAL)
    _filho(prod, "qCom", _quantidade(item.quantidade))
    _filho(prod, "vUnCom", _dinheiro(item.preco_unitario))
    _filho(prod, "vProd", _dinheiro(item.subtotal))
    _filho(prod, "cEANTrib", "SEM GTIN")
    _filho(prod, "uTrib", UNIDADE_COMERCIAL)
    _filho(prod, "qTrib", _quantidade(item.quantidade))
    _filho(prod, "vUnTrib", _dinheiro(item.preco_unitario))
    _filho(prod, "indTot", "1")

    imposto = _filho(det, "imposto")
    icms = _filho(imposto, "ICMS")
    # CST 41, não tributada. É forma, não apuração — ver o docstring do módulo.
    isento = _filho(icms, "ICMS40")
    _filho(isento, "orig", "0")
    _filho(isento, "CST", "41")


def _totais(pai: ET.Element, total: Decimal) -> None:
    icms_tot = _filho(_filho(pai, "total"), "ICMSTot")
    for tag in ("vBC", "vICMS", "vICMSDeson", "vFCP", "vBCST", "vST"):
        _filho(icms_tot, tag, _dinheiro(ZERO))
    _filho(icms_tot, "vProd", _dinheiro(total))
    for tag in ("vFrete", "vSeg", "vDesc", "vII", "vIPI", "vPIS", "vCOFINS", "vOutro"):
        _filho(icms_tot, tag, _dinheiro(ZERO))
    _filho(icms_tot, "vNF", _dinheiro(total))


def _observacoes(pedido: Pedido, autorizacao: Autorizacao) -> str:
    """A tarja, a trilha de auditoria e o que cada composição é.

    A aprovação vai **dentro do documento** e não só numa tabela: o ADR-003 pede
    trilha de auditoria, e a trilha que viaja junto do artefato é a que ainda existe
    quando alguém abre o XML seis meses depois, longe do nosso banco.
    """
    linhas = [
        TARJA_LONGA,
        f"Emissao aprovada por {autorizacao.operador} em "
        f"{autorizacao.decidido_em:%d/%m/%Y %H:%M} UTC.",
    ]
    linhas += [
        f"Composicao {posicao + 1}: {composicao.tipo_de_evento.value.replace('_', ' ')} "
        f"para {composicao.pessoas} pessoas."
        for posicao, composicao in enumerate(pedido.composicoes)
    ]
    return " ".join(linhas)


def montar_xml(pedido: Pedido, nota: NotaFiscal, autorizacao: Autorizacao) -> str:
    """O XML inteiro, como string, pronto para ser gravado e lido.

    Devolve `str` e não `bytes` porque é isso que a coluna do Postgres guarda e o
    que a rota serve — e porque a única codificação que este documento tem é UTF-8,
    declarada no prólogo.
    """
    ET.register_namespace("", NS)

    proc = ET.Element(f"{{{NS}}}nfeProc", {"versao": VERSAO})
    nfe = _filho(proc, "NFe")
    inf = _filho(nfe, "infNFe")
    inf.set("Id", f"NFe{nota.chave}")
    inf.set("versao", VERSAO)

    ide = _filho(inf, "ide")
    _filho(ide, "cUF", f"{CODIGO_DA_UF:02d}")
    _filho(ide, "cNF", codigo_numerico(pedido.id))
    _filho(ide, "natOp", "Venda de mercadoria")
    _filho(ide, "mod", str(MODELO))
    _filho(ide, "serie", str(SERIE))
    _filho(ide, "nNF", str(nota.numero))
    _filho(ide, "dhEmi", nota.emitida_em.isoformat())
    _filho(ide, "tpNF", "1")
    # 1 = operação interna. É o mesmo estado do emitente na esmagadora maioria dos
    # casos deste catálogo, e a alternativa exigiria a tabela de UF do IBGE — a
    # mesma limitação declarada em `_endereco`.
    _filho(ide, "idDest", "1")
    _filho(ide, "cMunFG", CODIGO_DO_MUNICIPIO_DO_EMITENTE)
    _filho(ide, "tpImp", "1")
    _filho(ide, "tpEmis", "1")
    _filho(ide, "cDV", nota.chave[-1])
    _filho(ide, "tpAmb", AMBIENTE_DE_HOMOLOGACAO)
    _filho(ide, "finNFe", "1")
    _filho(ide, "indFinal", "1")
    _filho(ide, "indPres", "2")
    _filho(ide, "procEmi", "0")
    _filho(ide, "verProc", "vendinha-0.1.0")

    _emitente(inf)
    _destinatario(inf, pedido)

    posicao = 0
    for composicao in pedido.composicoes:
        for item in composicao.itens:
            posicao += 1
            _item(inf, posicao, item)

    _totais(inf, pedido.total)

    transp = _filho(inf, "transp")
    _filho(transp, "modFrete", "9")

    pag = _filho(inf, "pag")
    det_pag = _filho(pag, "detPag")
    _filho(det_pag, "tPag", "99")
    _filho(det_pag, "vPag", _dinheiro(pedido.total))

    inf_adic = _filho(inf, "infAdic")
    _filho(inf_adic, "infCpl", _observacoes(pedido, autorizacao))

    corpo = ET.tostring(proc, encoding="unicode")
    return f'<?xml version="1.0" encoding="UTF-8"?>{corpo}'


def cnpj_impresso(digitos: str) -> str:
    """`22333444000181` → `22.333.444/0001-81`. A DANFE imprime pontuado; o XML, não."""
    return formatar_cnpj(digitos)


__all__ = ["NS", "VERSAO", "cnpj_impresso", "montar_xml"]
