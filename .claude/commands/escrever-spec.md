# /escrever-spec — Redigir uma nova spec

Entrada esperada: número e tema da spec (ex.: "S-04 checkout e pagamento").

1. Ler `docs/PRD.md`, `docs/riscos.md`, `docs/decisoes.md` e o template `docs/templates/SPEC-TEMPLATE.md`.
2. Redigir a spec preenchendo TODAS as seções do template, com atenção a:
   - Rastreabilidade: listar ADRs e riscos (R#) que esta spec cobre.
   - Tasks: fatiadas para virarem commits individuais que contam uma história.
   - BDD: 2-3 cenários Gherkin no máximo — os que capturam o comportamento essencial.
   - Métricas de sucesso: definidas pelo PO, com número. Sem número é opinião.
   - Verificação independente: instruções objetivas para a sessão revisora.
3. Salvar em `docs/specs/S-XX-nome.md` e apresentar para aprovação do PO antes de abrir issue.
