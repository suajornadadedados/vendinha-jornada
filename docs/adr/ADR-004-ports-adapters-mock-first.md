# ADR-004 — Ports & adapters mock-first para pagamento e NF

- Status: aceito · Data: 2026-08-03 · Decisões: D6, D7 · Risco: R8

## Contexto
Integrações reais (gateway, emissor de NF) trazem fricção (contas, certificado, CNPJ) que
não pode ficar no caminho do quickstart de 10 minutos nem derrubar a demo.

## Alternativas consideradas
1. **Integração direta nos serviços** — menos código hoje; acoplamento e quickstart frágil.
2. **Ports `PaymentGateway` e `NFEmitter` + adapters** — Mock (default, fiel ao contrato:
   DANFE/XML "SEM VALOR FISCAL") e reais (Mercado Pago sandbox; homologação SEFAZ opcional).

## Decisão
Opção 2, com mock como cidadão de primeira classe (testado por contrato, não um stub jogado).
Troca de adapter por variável de ambiente. Emissor da homologação: spike → novo ADR.

## Consequências
+ Quickstart sem contas externas; testes de contrato; demo com plano B.
− Duas implementações por porta para manter (aceito; contrato pequeno).
