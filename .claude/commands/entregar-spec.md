# /entregar-spec — Ritual de execução de uma spec

Entrada esperada: id da spec (ex.: S-04). Pré-condição: sessão nova, branch main atualizada.

1. Ler a spec inteira + documentos normativos citados nela. Confirmar entendimento do escopo
   e do que está FORA do escopo antes de escrever código.
2. `git checkout -b spec/s-XX-nome` a partir da main.
3. Executar task a task, na ordem:
   - implementar → lint + typecheck + testes → commit (Conventional Commits, escopo = spec).
   - Se algo fora do escopo aparecer: registrar em "Descobertas" na spec e NÃO implementar.
4. Ao final: rodar a suite completa + evals. Atualizar status da spec para `em-revisao`.
5. **Parar aqui e chamar `/fechar-spec S-XX`.** O encerramento — verificação independente,
   correção, e só então o PR — é dele, e não deste comando.

   > Este passo já mandou abrir o PR antes da verificação. Estava errado: o `CLAUDE.md`,
   > fluxo item 4, põe a verificação **antes** do PR, e o PR nasce com a correção dentro.
   > Não é mais só convenção — `.claude/hooks/gate-pr.py` recusa `gh pr create` numa branch
   > `spec/s-XX-*` sem relatório aprovado. Implementar e encerrar são sessões diferentes de
   > propósito: quem acabou de escrever o código é a pior pessoa para decidir que ele está
   > pronto.
