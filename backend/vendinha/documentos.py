"""CNPJ, e-mail e CEP — quem decide se um dado é válido, e por que não é o modelo.

O `golden-008` é o caso inteiro deste módulo, e ele tem duas armadilhas. A primeira
é o dígito errado: um modelo prestativo "conserta" o CNPJ e cria um documento que
ninguém digitou. A segunda parece colaboração e é pior — *"põe qualquer um aí que
depois eu corrijo"* é o pedido para gravar lixo num campo que vai sair impresso numa
nota fiscal, e **não existe "depois eu corrijo" quando o dado atravessa uma emissão**
(RF-2.2, RF-3.4).

A defesa das duas é a mesma: quem diz o que é um CNPJ válido é o algoritmo dos
dígitos verificadores, aqui, em código puro. O modelo não valida, não corrige e não
completa — ele coleta e repassa.

**Nada de `EmailStr`.** Ele exigiria o pacote `email-validator` como dependência do
produto, e o que precisamos verificar é bem menor do que o RFC 5322: que o endereço
para onde a nota vai tem uma parte local, uma arroba e um domínio com ponto. Uma
regex conservadora recusa o que precisa ser recusado sem trazer um pacote para o
caminho do quickstart (RNF-1). O preço está declarado: endereço exótico porém legal
é recusado, e a saída é o cliente informar outro.

**Nenhum documento real neste arquivo, nem nos testes** (RNF-7). Os CNPJs dos casos
de eval são números com dígitos válidos de empresas que não existem.
"""

import re

# 14 dígitos, e o cliente escreve como quiser: com pontuação, sem, com espaço.
# Normalizar antes de validar é o que evita recusar um dado certo por causa de um
# ponto — e recusa errada é o que ensina o cliente a desconfiar do formulário.
SO_DIGITOS = re.compile(r"\D")

TAMANHO_DO_CNPJ = 14

# Os pesos do módulo 11, na ordem em que a Receita os define. Escritos e não
# gerados: uma list comprehension esperta aqui economizaria uma linha e esconderia
# a única coisa que alguém vai querer conferir contra a norma.
PESOS_DO_PRIMEIRO = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
PESOS_DO_SEGUNDO = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)

# Deliberadamente conservadora — ver o docstring do módulo. Sem espaço, uma arroba
# só, domínio com pelo menos um ponto e TLD alfabético.
EMAIL = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)*\.[A-Za-z]{2,}$")

CEP = re.compile(r"^\d{5}-?\d{3}$")

# As 27 unidades federativas. Lista fechada pelo mesmo motivo que `Alergeno` é
# fechado em `catalogo.py`: "MJ" digitado por engano vira um endereço que a
# transportadora não encontra e a nota carrega para sempre.
UFS = frozenset(
    "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()
)


def normalizar_cnpj(valor: str) -> str:
    """Só os dígitos. `11.222.333/0001-81` e `11222333000181` são o mesmo documento."""
    return SO_DIGITOS.sub("", valor)


def cnpj_valido(valor: str) -> bool:
    """Os dígitos verificadores fecham?

    `11111111111111` é recusado explicitamente: os dígitos repetidos passam no
    módulo 11 por acidente aritmético, e é exatamente o número que sai de um
    "põe qualquer um aí". A checagem custa uma linha e fecha a segunda armadilha
    do `golden-008`.
    """
    digitos = normalizar_cnpj(valor)
    if len(digitos) != TAMANHO_DO_CNPJ or len(set(digitos)) == 1:
        return False
    return digitos[12:] == _verificadores(digitos[:12])


def _verificadores(base: str) -> str:
    """Os dois dígitos que fecham uma base de 12."""
    primeiro = _digito(base, PESOS_DO_PRIMEIRO)
    segundo = _digito(base + primeiro, PESOS_DO_SEGUNDO)
    return primeiro + segundo


def _digito(base: str, pesos: tuple[int, ...]) -> str:
    resto = sum(int(d) * p for d, p in zip(base, pesos, strict=True)) % 11
    return "0" if resto < 2 else str(11 - resto)


def formatar_cnpj(valor: str) -> str:
    """`11222333000181` → `11.222.333/0001-81`. Assume já validado."""
    d = normalizar_cnpj(valor)
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def mascarar_cnpj(valor: str) -> str:
    """O bastante para a pessoa reconhecer o documento, inútil para copiá-lo.

    É a mesma ideia do `Vault.hint` para credencial: o retorno de tool que confirma
    o cadastro não pode ser o lugar de onde o modelo copia o número em claro para a
    resposta. `golden-003` e `golden-008` reprovam a execução que repete o CNPJ, e
    ADR-007/R5 pedem que PII não trafegue legível nem em trace — e retorno de tool
    vira trace.
    """
    d = normalizar_cnpj(valor)
    if len(d) != TAMANHO_DO_CNPJ:
        return "[CNPJ]"
    return f"**.***.***/{d[8:12]}-{d[12:]}"


def email_valido(valor: str) -> bool:
    """Tem parte local, arroba e domínio com ponto? Ver a nota no docstring do módulo."""
    return bool(EMAIL.match(valor.strip()))


def cep_valido(valor: str) -> bool:
    return bool(CEP.match(valor.strip()))


def uf_valida(valor: str) -> bool:
    return valor.strip().upper() in UFS


__all__ = [
    "TAMANHO_DO_CNPJ",
    "UFS",
    "cep_valido",
    "cnpj_valido",
    "email_valido",
    "formatar_cnpj",
    "mascarar_cnpj",
    "normalizar_cnpj",
    "uf_valida",
]
