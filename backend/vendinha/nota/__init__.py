"""A porta do emissor de NF-e e o adapter mock — ADR-004, e a metade da R8 que falta.

Espelha `pagamento.py` de propósito: as duas integrações externas deste projeto têm
a mesma forma, e a semelhança é o que faz "trocar de adapter é configuração, não
código" ser verificável em vez de prometido.

**O que o port promete.** Uma operação — `emitir` — que recebe o pedido, o número da
nota e quem autorizou, e devolve `NotaEmitida`: identidade fiscal, XML e DANFE.
Falha se anuncia como `EmissorIndisponivel`, e código que trata falha de emissão não
precisa saber qual adapter está configurado.

**O número da nota NÃO é do adapter.** Ele chega de fora, alocado por `fiscal.py` a
partir de uma sequência do Postgres. Numeração de nota é fato de negócio e sequência
é a coisa que bancos fazem certo e processos concorrentes fazem errado — deixá-la no
adapter faria dois adapters numerarem de dois jeitos, e o `HomologacaoAdapter` da
S-09 herdaria uma responsabilidade que não é dele (ADR-001).

**Como se troca.** `NF_EMITTER=mock` (default) ou `homologacao`. Aqui existe a
variável explícita que o `gateway_de` do pagamento recusou ter, e a assimetria é
deliberada: o pagamento deriva a escolha da presença do token porque
`mercadopago` sem token é um estado inválido que sobe e quebra depois. Na emissão o
estado equivalente — `homologacao` sem certificado — **também** é inválido, e a
diferença é que aqui ele é recusado na subida, com uma frase que diz o que falta.
A variável já estava no `.env.example` desde a S-02 sem ninguém a ler; agora é lida.

**`HomologacaoAdapter` é da S-09** e está fora do escopo desta spec. `emissor_de`
recusa `homologacao` dizendo isso, em vez de devolver silenciosamente o mock: um
ambiente configurado para emitir contra a SEFAZ e servido pelo mock é a pior falha
possível — ele parece funcionar.
"""

import logging
from typing import Protocol

from vendinha.nota.danfe import montar_danfe
from vendinha.nota.documento import (
    EMITENTE,
    ISENTO,
    MODELO,
    SERIE,
    TARJA,
    TARJA_LONGA,
    Autorizacao,
    Emitente,
    NotaEmitida,
    NotaFiscal,
    agora,
    chave_confere,
    chave_de_acesso,
    formatar_chave,
    inscricao_do_destinatario,
)
from vendinha.nota.xml import montar_xml
from vendinha.pedidos import Pedido

logger = logging.getLogger(__name__)

MOCK = "mock"
HOMOLOGACAO = "homologacao"

EMISSORES = (MOCK, HOMOLOGACAO)


class EmissorIndisponivel(RuntimeError):
    """O emissor não respondeu, ou respondeu o que não dá para usar.

    Uma exceção só para todos os adapters, como `GatewayIndisponivel` no pagamento:
    é parte do contrato que o ADR-004 pede, e é o que permite `fiscal.emitir` tratar
    a falha sem saber qual emissor está configurado (R8).
    """


class NFEmitter(Protocol):
    """A porta. Uma operação, e nada específico de fornecedor no que ela devolve."""

    nome: str

    async def emitir(
        self, pedido: Pedido, numero: int, autorizacao: Autorizacao
    ) -> NotaEmitida: ...


class MockNFAdapter:
    """O emissor do quickstart — e o default (RNF-1).

    **Não é um stub.** Ele produz um XML que parseia no leiaute 4.00 e uma DANFE que
    um leitor de PDF abre, os dois carregando a mesma chave de acesso de 44 dígitos
    com dígito verificador correto, o destinatário PJ do pedido e a tarja
    `SEM VALOR FISCAL`. Um emissor que devolvesse `b"pdf falso"` passaria em todo
    teste de contrato e entregaria ao contador da empresa compradora um arquivo que
    não abre — que é a diferença entre "mock de primeira classe" e "stub jogado" que
    o ADR-004 nomeia, e a mesma lição que a D-6 da S-04 aprendeu com o link de
    pagamento que terminava em 404.

    **Ele não assina e não protocola**, porque assinar exige certificado digital e
    nenhum certificado real entra neste repositório (RNF-7). É exatamente essa a
    diferença que o `HomologacaoAdapter` da S-09 acrescenta.
    """

    nome = MOCK

    async def emitir(self, pedido: Pedido, numero: int, autorizacao: Autorizacao) -> NotaEmitida:
        emitida_em = agora()
        nota = NotaFiscal(
            pedido_id=pedido.id,
            numero=numero,
            serie=SERIE,
            chave=chave_de_acesso(pedido_id=pedido.id, numero=numero, emitida_em=emitida_em),
            emitida_em=emitida_em,
            emissor=self.nome,
            aprovada_por=autorizacao.operador,
            # Copiado do pedido, e não somado aqui. O total é o que o cliente
            # confirmou e pagou; recalculá-lo na emissão criaria a segunda conta
            # que a regra de ouro existe para não ter (ADR-001, R1).
            total=pedido.total,
        )
        return NotaEmitida(
            nota=nota,
            xml=montar_xml(pedido, nota, autorizacao),
            danfe=montar_danfe(pedido, nota, autorizacao),
        )


def emissor_de(nome: str | None, api_key: str | None, base_url: str | None) -> NFEmitter:
    """O adapter que vale nesta instância, dito em voz alta no log.

    A escolha é explícita — ao contrário da do pagamento — e mesmo assim é anunciada:
    a lição da D-4 da S-04 é que a pergunta *"por que o documento é falso?"* aparece
    três semanas depois, e a resposta precisa estar no log de subida.
    """
    escolhido = (nome or MOCK).strip().lower()

    if escolhido == MOCK:
        logger.info(
            "nota fiscal: adapter MOCK — DANFE e XML fiéis ao leiaute 55, com tarja "
            "%r. Nenhum documento emitido aqui tem valor fiscal.",
            TARJA,
        )
        return MockNFAdapter()

    if escolhido == HOMOLOGACAO:
        # Recusa alta, e não fallback silencioso: uma instância configurada para a
        # SEFAZ e servida pelo mock emitiria documentos de demonstração achando que
        # emitiu notas — e ninguém descobriria até alguém procurar a nota na SEFAZ.
        #
        # A mensagem diz TUDO que falta de uma vez, e não só a primeira coisa. Quem
        # está configurando homologação vai precisar das três, e descobri-las uma
        # por reinício é a forma mais cara possível de ler um erro.
        pendentes = [
            variavel
            for variavel, valor in (
                ("NF_EMITTER_API_KEY", api_key),
                ("NF_EMITTER_BASE_URL", base_url),
            )
            if not valor
        ]
        ainda_falta = (
            f" Além disso, {' e '.join(pendentes)} não está definida." if pendentes else ""
        )
        raise EmissorIndisponivel(
            "NF_EMITTER=homologacao ainda não tem adapter: ele é entregável da S-09 "
            "(docs/specs/S-09-homologacao-real.md), e exige certificado digital e CNPJ "
            f"reais, que não entram neste repositório.{ainda_falta} Use NF_EMITTER=mock."
        )

    raise EmissorIndisponivel(
        f"NF_EMITTER={nome!r} não existe. Os valores aceitos são: {', '.join(EMISSORES)}."
    )


__all__ = [
    "EMISSORES",
    "EMITENTE",
    "HOMOLOGACAO",
    "ISENTO",
    "MOCK",
    "MODELO",
    "SERIE",
    "TARJA",
    "TARJA_LONGA",
    "Autorizacao",
    "EmissorIndisponivel",
    "Emitente",
    "MockNFAdapter",
    "NFEmitter",
    "NotaEmitida",
    "NotaFiscal",
    "agora",
    "chave_confere",
    "chave_de_acesso",
    "formatar_chave",
    "inscricao_do_destinatario",
    "montar_danfe",
    "montar_xml",
]
