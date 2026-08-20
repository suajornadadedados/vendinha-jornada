# /entregar-spec — Ritual de execução de uma spec

Entrada esperada: id da spec (ex.: S-04). Pré-condição: sessão nova, branch main atualizada.

1. Ler a spec inteira + documentos normativos citados nela. Confirmar entendimento do escopo
   e do que está FORA do escopo antes de escrever código.
2. `git checkout -b spec/s-XX-nome` a partir da main.
3. Executar task a task, na ordem:
   - implementar → lint + typecheck + testes → commit (Conventional Commits, escopo = spec).
   - Se algo fora do escopo aparecer: registrar em "Descobertas" na spec e NÃO implementar.
4. Ao final: rodar a suite completa + evals. Atualizar status da spec para `em-revisao`.
5. Abrir PR para main com o template preenchido: spec relacionada, o que muda, como testar,
   evidência (screenshot da feature + link do trace Langfuse), checklist.
6. Solicitar ao PO que dispare `/verificar-spec` em uma sessão NOVA. Não fazer merge sem o
   relatório da verificação anexado ao PR.
