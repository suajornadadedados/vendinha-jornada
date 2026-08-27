# /verificar-spec — Verificação independente (sessão revisora)

> **Este comando é a via manual, para sessão nova.** O caminho padrão é o subagente
> `verificador-de-spec`, cujas instruções vivem em `.claude/agents/verificador-de-spec.md` e são
> mais completas que as daqui — falsificação obrigatória, tabela de quebras, e a regra de ignorar
> enquadramento vindo no prompt. Os dois precisam dizer a mesma coisa: ao mudar um, releia o outro.

## Papel
Você é o REVISOR desta entrega. Você NÃO é o autor. Padrão autor/revisor: seu valor está em
olhar apenas a evidência, sem o contexto mental de quem implementou.

## O que você PODE ler
- A spec (`docs/specs/S-XX-*.md`) e os documentos normativos que ela cita.
- O diff do PR (`git diff main...spec/s-XX-nome`) e o código do repositório.
- Resultados de testes e evals que você mesmo executar.

## O que você NÃO PODE fazer
- Ler histórico/resumo da sessão autora, mensagens de planejamento ou anotações do autor.
- Corrigir o código. Você reporta; o autor corrige.
- Assumir intenção: se a spec diz X e o código faz Y, é não-conformidade mesmo que Y pareça melhor.

## Roteiro de verificação
1. Rodar do zero: `docker compose up`, suite de testes, evals. Registrar resultados reais.
2. Para cada requisito e cada cenário BDD da spec: verificar implementação e teste correspondente.
   Marcar: CONFORME / NÃO CONFORME / NÃO VERIFICÁVEL (com motivo).
3. Verificar as métricas de sucesso da spec com números medidos (não estimados).
4. Verificar invariantes globais: fronteira de permissões dos subagents, ausência de secrets
   no diff, PII mascarada em traces, escopo respeitado.
5. Gerar `docs/specs/relatorios/S-XX-verificacao.md` com: resumo, tabela de conformidade,
   métricas medidas vs alvo, riscos observados, veredito (APROVADO / APROVADO COM RESSALVAS /
   REPROVADO) e o porquê.
   O arquivo começa por frontmatter — `spec`, `veredito`, `commit` (o sha exato que você
   verificou), `branch`, `data` — porque `.claude/hooks/gate-pr.py` lê o veredito daqui para
   recusar ou liberar o `gh pr create` da branch. Prosa não é interface. O frontmatter não
   substitui o veredito escrito por extenso com o porquê.
6. Entregar o relatório como **arquivo**. Não existe PR neste momento: a verificação vem antes
   dele (`CLAUDE.md`, fluxo item 4). Quem anexa o relatório ao PR é o autor, depois de corrigir
   o que a verificação apontou.
