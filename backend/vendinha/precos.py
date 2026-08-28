"""Quanto custou. Em `Decimal`, no backend, e nunca zero por falta de informação.

Dinheiro é código — é a regra de ouro do projeto, e ela não tem uma versão relaxada
para a tela de custo. O `reduce` que soma preços no navegador parece inofensivo no
diff e é exatamente o furo que o ADR-015 fecha nomeando a métrica: contas de
dinheiro no frontend, zero.

**Três decisões, e as três são sobre não mentir.**

**Modelo sem preço custa `None`, não `0`.** Um zero é uma afirmação — *"esta
conversa foi de graça"* — e uma afirmação falsa numa tela cuja única função é dizer
quanto se gastou. `None` é a ausência, e a tela a escreve como ausência. É a mesma
regra que `telemetria.py` aplica um andar abaixo, ao token que o provedor não
informou.

**O casamento é por prefixo mais longo.** `LLM_MODEL` aponta para um snapshot datado
de propósito (ADR-014: uma régua que anda sozinha não detecta regressão), então
`anthropic:claude-haiku-4-5-20251001` precisa herdar o preço de
`anthropic:claude-haiku-4-5` sem uma linha por data. Prefixo mais longo e não o
primeiro que casar: `claude-opus-4-8` e `claude-opus-4` não podem depender da ordem
do dicionário.

**A cotação do dólar é opcional, e a ausência dela aparece.** Sem `usd_brl`, o custo
sai só em dólar e o percentual sobre o ticket não é calculado — em vez de convertido
por uma taxa inventada. A tabela de preços já é o artefato que desatualiza em
silêncio; acrescentar câmbio chutado seria uma segunda fonte do mesmo erro.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

from vendinha.config import REPO_ROOT
from vendinha.telemetria import UsoDeModelo

TABELA = REPO_ROOT / "data" / "precos-modelos.json"

POR_MILHAO = Decimal(1_000_000)
# Seis casas em dólar porque uma conversa inteira custa centavos: arredondar a duas
# transformaria o custo de metade das sessões em US$ 0,00, que é o zero mentiroso
# entrando por outra porta. Reais fica em duas, que é o que se lê numa tela.
CASAS_USD = Decimal("0.000001")
CASAS_BRL = Decimal("0.01")


class Preco(BaseModel):
    """Dólares por 1 milhão de tokens."""

    entrada: Decimal
    saida: Decimal


class Custo(BaseModel):
    """O que uma fatia de uso custou — e o que não deu para saber.

    `modelos_sem_preco` e `turnos_sem_uso` não são detalhe de diagnóstico: são o que
    permite à tela dizer *"US$ 0,42 — incompleto"* em vez de *"US$ 0,42"*. Um total
    parcial apresentado como total é a mentira que este módulo existe para evitar.
    """

    usd: Decimal | None = Field(
        default=None, description="`None` quando nenhum modelo da fatia tem preço."
    )
    brl: Decimal | None = Field(
        default=None, description="`None` sem cotação configurada — nunca convertido no chute."
    )
    modelos_sem_preco: tuple[str, ...] = ()
    turnos_sem_uso: int = 0

    @property
    def completo(self) -> bool:
        return not self.modelos_sem_preco and not self.turnos_sem_uso


class TabelaDePrecos(BaseModel):
    """O arquivo versionado, tipado na fronteira como todo o resto."""

    atualizado_em: date
    moeda: str
    fonte: str
    usd_brl: Decimal | None = None
    usd_brl_atualizado_em: date | None = None
    modelos: dict[str, Preco] = {}

    def preco_de(self, modelo: str) -> Preco | None:
        """Prefixo mais longo que case. `None` quando nenhum casa."""
        melhor: str | None = None
        for chave in self.modelos:
            if modelo.startswith(chave) and (melhor is None or len(chave) > len(melhor)):
                melhor = chave
        return None if melhor is None else self.modelos[melhor]

    def custo(self, uso: tuple[UsoDeModelo, ...]) -> Custo:
        """Soma o uso de vários modelos numa conta só.

        Ausência não zera o que se sabe: um par de modelos em que um tem preço e o
        outro não devolve o custo do primeiro **mais** o nome do segundo, para a
        tela mostrar o parcial dizendo que é parcial.
        """
        total: Decimal | None = None
        sem_preco: list[str] = []
        sem_uso = 0

        for linha in uso:
            sem_uso += linha.turnos_sem_uso
            # Modelo com preço e **nenhum token conhecido** não custa zero: custa
            # nada de conhecido. Sem esta linha, um turno cujo provedor não informou
            # consumo passava por `0 × preço` e chegava à tela como US$ 0,000000 —
            # o zero mentiroso entrando pela porta que este módulo achava fechada,
            # porque a ausência estava no token e a checagem estava no preço.
            if not linha.tokens_entrada and not linha.tokens_saida:
                continue
            preco = self.preco_de(linha.modelo)
            if preco is None:
                sem_preco.append(linha.modelo)
                continue
            parcial = (
                Decimal(linha.tokens_entrada) * preco.entrada
                + Decimal(linha.tokens_saida) * preco.saida
            ) / POR_MILHAO
            total = parcial if total is None else total + parcial

        usd = None if total is None else total.quantize(CASAS_USD, rounding=ROUND_HALF_UP)
        return Custo(
            usd=usd,
            brl=self.em_reais(usd),
            modelos_sem_preco=tuple(sorted(set(sem_preco))),
            turnos_sem_uso=sem_uso,
        )

    def em_reais(self, usd: Decimal | None) -> Decimal | None:
        if usd is None or self.usd_brl is None:
            return None
        return (usd * self.usd_brl).quantize(CASAS_BRL, rounding=ROUND_HALF_UP)


@lru_cache(maxsize=1)
def tabela(caminho: Path | None = None) -> TabelaDePrecos:
    """Lida uma vez. Trocar o arquivo pede reinício, como toda configuração daqui.

    Um arquivo ausente ou ilegível **não derruba a API**: devolve tabela vazia, e
    tabela vazia significa que todo modelo fica sem preço — que é o estado que a
    tela sabe exibir. O oposto — deixar subir — poria a tela de custo no caminho da
    resposta ao cliente, e o custo é a informação menos urgente do sistema.
    """
    origem = caminho or TABELA
    try:
        return TabelaDePrecos.model_validate_json(origem.read_bytes())
    except (OSError, ValueError):
        return TabelaDePrecos(
            atualizado_em=date(1970, 1, 1),
            moeda="USD",
            fonte=f"tabela ausente ou ilegivel em {origem.name}",
        )


def custo_de(uso: tuple[UsoDeModelo, ...]) -> Custo:
    """Atalho para quem só quer a conta, com a tabela vigente."""
    return tabela().custo(uso)
