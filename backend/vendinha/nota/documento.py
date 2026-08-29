"""O documento fiscal como dado: quem emite, quem recebe, e a chave que o identifica.

Este módulo não escreve XML nem PDF. Ele guarda o que os dois precisam concordar —
e é essa concordância que faz o mock ser **fiel** em vez de ser dois arquivos
parecidos. Uma DANFE cuja chave de acesso não bate com a do XML é exatamente o
artefato que passa despercebido numa demo e reprova numa conferência.

**A chave de acesso é calculada, não sorteada.** São 44 dígitos com uma composição
definida pela SEFAZ e um dígito verificador de módulo 11 — a mesma aritmética que
`documentos._digito` faz para o CNPJ. Gerar 44 dígitos aleatórios daria um arquivo
com a forma certa e o conteúdo errado, e o dia em que alguém colar essa chave num
validador online seria o dia em que descobriríamos que o "mock fiel" não era.

**O emitente é fabricado, e o CNPJ dele também** (RNF-7). `22.333.444/0001-81` tem
dígitos verificadores válidos e não pertence a ninguém. Nenhum documento real entra
neste repositório, e um emitente é tão real quanto um destinatário.

**A tarja não é decoração.** `SEM VALOR FISCAL` sai no XML (`infCpl`) e na DANFE
(marca d'água), porque o artefato circula: o comprador manda para a contabilidade
dele. Um documento de demonstração que não diz que é demonstração é um documento
falso (ADR-004, RF-3.4).
"""

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from vendinha.pedidos import Endereco, Pedido

Texto = Annotated[str, Field(min_length=1)]

# O que a tarja diz, palavra por palavra, num lugar só. O XML e a DANFE leem daqui,
# e `tests/unit/test_nota_fiscal.py` afirma sobre os dois com a mesma constante —
# uma string repetida em três arquivos é a que fica diferente em um deles.
TARJA = "SEM VALOR FISCAL"
TARJA_LONGA = "SEM VALOR FISCAL - DOCUMENTO DE DEMONSTRACAO"

# Modelo 55 é a NF-e de mercadoria, que é o que uma cesta de evento é. Série 1
# porque só existe um ponto de emissão neste projeto.
MODELO = 55
SERIE = 1

# Minas Gerais. O código da UF entra na chave de acesso e no `cUF` do XML, e é do
# EMITENTE — não do destinatário, que pode estar em qualquer estado.
CODIGO_DA_UF = 31

# Classificação fiscal fixa, e dito em voz alta: NCM, CFOP e unidade comercial são
# atributos fiscais do produto que este projeto **não modela** — o catálogo de
# `data/catalogo/` descreve comida, não tributação. Os valores abaixo são plausíveis
# para alimento em venda interna, e existem para o documento ter a forma certa.
# Inventar um NCM por produto seria fato de negócio saindo de lugar nenhum, que é
# exatamente o que a regra de ouro proíbe (ADR-001).
NCM_GENERICO = "21069090"
CFOP_VENDA_INTERNA = "5102"
UNIDADE_COMERCIAL = "UN"

# Destinatário sem inscrição estadual. `9` é o código do `indIEDest` para "não
# contribuinte", e `ISENTO` é o que a DANFE imprime. Não é atalho: é o caminho
# normal para boa parte das empresas compradoras de um evento corporativo.
ISENTO = "ISENTO"
IND_IE_CONTRIBUINTE = 1
IND_IE_NAO_CONTRIBUINTE = 9


class Emitente(BaseModel):
    """A loja. Fabricada inteira (RNF-7)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    razao_social: Texto
    nome_fantasia: Texto
    cnpj: Texto
    inscricao_estadual: Texto
    endereco: Endereco


EMITENTE = Emitente(
    razao_social="Vendinha Comercio de Alimentos LTDA",
    nome_fantasia="Vendinha - Emporio Mineiro",
    cnpj="22333444000181",
    inscricao_estadual="0623456700109",
    endereco=Endereco(
        logradouro="Rua Sao Paulo",
        numero="1500",
        complemento="loja 4",
        bairro="Centro",
        cidade="Belo Horizonte",
        uf="MG",
        cep="30170-132",
    ),
)


class Autorizacao(BaseModel):
    """Quem liberou a emissão, e quando.

    Vive aqui, e não em `fiscal.py`, para o emissor não precisar importar o módulo
    que o chama — o port ficaria com uma dependência na direção errada. O que o
    emissor precisa saber sobre a aprovação são estes dois campos, e `fiscal.py`
    monta um a partir do registro que persistiu.

    O operador vai impresso na DANFE de propósito: a trilha de auditoria do ADR-003
    fica no documento, não só numa tabela que ninguém abre.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    operador: Texto
    decidido_em: datetime


class NotaFiscal(BaseModel):
    """A identidade fiscal do documento. Nada aqui foi escolhido pelo modelo."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pedido_id: Texto
    numero: int = Field(ge=1)
    serie: int = Field(ge=1)
    chave: Texto = Field(min_length=44, max_length=44)
    emitida_em: datetime
    emissor: Texto
    aprovada_por: Texto
    total: Decimal


class NotaEmitida(BaseModel):
    """A nota e os dois artefatos que o comprador recebe."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    nota: NotaFiscal
    xml: str
    danfe: bytes


def numero_da_nota(emitida: NotaEmitida | None) -> int | None:
    """O número da nota, ou `None` quando ela não existe.

    Existe como função porque a travessia estava escrita à mão em dois lugares do
    painel, e nos dois **errada**: `NotaEmitida` embrulha a nota, então o número é
    `.nota.numero` e `.numero` nela é `AttributeError`.

    Ninguém viu porque o caminho só é percorrido quando existe nota emitida de
    verdade — nenhum teste do painel tinha uma. Em produção, `GET /admin/pedidos`
    respondia **500** no primeiro pedido com nota, e a tela de pedidos ficava vazia:
    parecia que o pedido tinha sumido, e o que tinha acontecido é que a rota inteira
    quebrava por causa dele.
    """
    return None if emitida is None else emitida.nota.numero


def codigo_numerico(pedido_id: str) -> str:
    """O `cNF` — oito dígitos que distinguem duas notas do mesmo número.

    Derivado do id do pedido em vez de sorteado, pela mesma razão que o link do
    `MockPaymentAdapter` é derivado: rodar o mesmo cenário duas vezes tem que dar o
    mesmo documento. Sorteio dentro de um mock transforma qualquer conferência numa
    comparação que nunca fecha.
    """
    digest = hashlib.sha256(pedido_id.encode("utf-8")).hexdigest()
    return f"{int(digest[:8], 16) % 100_000_000:08d}"


def digito_da_chave(quarenta_e_tres: str) -> str:
    """O `cDV` — módulo 11 com pesos 2..9 da direita para a esquerda.

    Mesma aritmética de `documentos._digito`, e escrita aqui em vez de importada
    porque os pesos são outros: o CNPJ usa duas tabelas fixas, a chave usa um ciclo.
    Compartilhar uma função genérica esconderia justamente a parte que alguém vai
    querer conferir contra a norma.
    """
    soma = 0
    peso = 2
    for digito in reversed(quarenta_e_tres):
        soma += int(digito) * peso
        peso = 2 if peso == 9 else peso + 1
    resto = soma % 11
    return "0" if resto in (0, 1) else str(11 - resto)


def chave_de_acesso(*, pedido_id: str, numero: int, emitida_em: datetime) -> str:
    """Os 44 dígitos, na ordem em que a SEFAZ os define.

    `cUF(2) AAMM(4) CNPJ(14) mod(2) serie(3) nNF(9) tpEmis(1) cNF(8) cDV(1)`

    `tpEmis=1` é emissão normal. A data entra como ano/mês da emissão, então duas
    notas do mesmo pedido em meses diferentes teriam chaves diferentes — o que não
    acontece, porque uma nota por pedido é constraint de banco (`fiscal.py`).
    """
    sem_digito = (
        f"{CODIGO_DA_UF:02d}"
        f"{emitida_em:%y%m}"
        f"{EMITENTE.cnpj:>014}"
        f"{MODELO:02d}"
        f"{SERIE:03d}"
        f"{numero:09d}"
        f"1"
        f"{codigo_numerico(pedido_id)}"
    )
    return sem_digito + digito_da_chave(sem_digito)


def chave_confere(chave: str) -> bool:
    """A chave tem 44 dígitos e o verificador fecha? Usado pelos testes e por quem lê."""
    return len(chave) == 44 and chave.isdigit() and chave[-1] == digito_da_chave(chave[:43])


def formatar_chave(chave: str) -> str:
    """`4444 4444 ...` — como a DANFE imprime, em onze grupos de quatro."""
    return " ".join(chave[i : i + 4] for i in range(0, len(chave), 4))


def inscricao_do_destinatario(pedido: Pedido) -> str:
    """A IE da compradora, ou `ISENTO`.

    Optional por decisão da S-05: exigir inscrição estadual recusaria compradoras
    legítimas — não contribuinte de ICMS é a situação normal de boa parte das
    empresas que compram um café da manhã — e transformaria a coleta num
    interrogatório. Ausente vira `ISENTO`, que é o que a norma manda imprimir.
    """
    return pedido.empresa.inscricao_estadual or ISENTO


def indicador_de_ie(pedido: Pedido) -> int:
    return IND_IE_CONTRIBUINTE if pedido.empresa.inscricao_estadual else IND_IE_NAO_CONTRIBUINTE


def agora() -> datetime:
    """O relógio, num lugar só, para os testes terem onde ficar de pé."""
    return datetime.now(UTC)


__all__ = [
    "CFOP_VENDA_INTERNA",
    "CODIGO_DA_UF",
    "EMITENTE",
    "IND_IE_CONTRIBUINTE",
    "IND_IE_NAO_CONTRIBUINTE",
    "ISENTO",
    "MODELO",
    "NCM_GENERICO",
    "SERIE",
    "TARJA",
    "TARJA_LONGA",
    "UNIDADE_COMERCIAL",
    "Autorizacao",
    "Emitente",
    "NotaEmitida",
    "NotaFiscal",
    "agora",
    "chave_confere",
    "chave_de_acesso",
    "codigo_numerico",
    "digito_da_chave",
    "formatar_chave",
    "indicador_de_ie",
    "inscricao_do_destinatario",
]
