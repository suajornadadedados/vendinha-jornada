# ADR-004 — Ports & adapters mock-first para pagamento e NF

- Status: aceito · Data: 2026-08-03 · Decisões: D6, D7 · Risco: R8

## Contexto
Integrações reais (gateway, emissor de NF) trazem fricção (contas, certificado, CNPJ) que
não pode ficar no caminho do quickstart de 10 minutos nem derrubar a demo.

## Alternativas consideradas
1. **Integração direta nos serviços** — menos código hoje; acoplamento e quickstart frágil.
2. **Ports `PaymentGateway` e `NFEmitter` + adapters** — Mock (default, fiel ao contrato:
   DANFE/XML "SEM VALOR FISCAL") e reais (Mercado Pago sandbox).

## Decisão
Opção 2, com mock como cidadão de primeira classe (testado por contrato, não um stub jogado).
Troca de adapter por variável de ambiente.

**Emenda de 2026-08-31 — o `NFEmitter` fica com um adapter só.** O adapter de homologação
SEFAZ era entregável de uma spec opcional que o PO descartou: certificado digital e CNPJ
reais são fricção que este repositório não paga, e sem eles a spec não tem como existir. A
consequência é que a metade *"dois adapters satisfazem a mesma interface"* da R8 não fecha
para essa porta — está declarada como lacuna em `docs/riscos.md`, `docs/testes.md` §2 e no
topo de `tests/unit/test_ports.py`, em vez de coberta por uma fixture de um elemento só. O
que continua provado é que a escolha do emissor é **configuração**, e que uma configuração
sem adapter é recusada alto em vez de cair no mock em silêncio.

## Consequências
+ Quickstart sem contas externas; testes de contrato; demo com plano B.
− Duas implementações por porta para manter (aceito; contrato pequeno). Vale para o
  `PaymentGateway`; o `NFEmitter` tem uma, pela emenda acima.
