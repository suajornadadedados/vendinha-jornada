"""O runner de evals — a régua da S-03, e o começo da régua da S-06.

Este subpacote é **ferramenta de desenvolvimento**, não caminho de atendimento.
Nada em `vendinha/` fora daqui o importa, e as dependências que ele acrescenta
(`pyyaml`) vivem no grupo `dev`. Ele mora dentro do pacote porque precisa montar o
agente de verdade — o mesmo grafo, o mesmo prompt, as mesmas tools —, e um runner
que monta *quase* o agente mede quase nada.

A S-06 é quem constrói o runner completo, com o job do CI e a suíte inteira. A
S-03 entrega a fatia que o REQ-5 pede: os seis casos que declaram `spec: S-03`,
rodados localmente por `make evals-groundedness`.

**Os casos são a régua, e a régua não mora aqui.** `evals/*.yaml` é protegido por
CODEOWNERS justamente para que um PR com eval vermelho não fique verde editando o
caso que reprovou (ADR-006). Este código lê aqueles arquivos; nunca os escreve.
"""

__all__: list[str] = []
