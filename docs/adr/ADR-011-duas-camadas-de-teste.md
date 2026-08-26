# ADR-011 — Duas camadas de teste: unit e security, sem camada de integração

- Status: aceito · Data: 2026-08-26 · Decisão: D14 · Riscos: R2, R3, R5, R8
- Atualiza o ADR-003 **apenas quanto à camada onde a invariante do HITL é provada**. A decisão
  do ADR-003 — interrupt do LangGraph, estado persistido, fila do operador, aprovação registrada
  com quem e quando — permanece vigente e inalterada.

## Contexto
A discovery escreveu, em oito lugares, que a invariante "nenhum caminho emite NF sem aprovação
registrada" é *testada em integração*. A palavra ali significava **"provada por execução, não
prometida em prosa"** — era ênfase, não escolha de tier.

Depois, `docs/testes.md` fechou a arquitetura de testes em duas camadas e declarou o contrário
com todas as letras: *"Não existe camada de integração neste repositório"*, mapeando R3 para
`tests/security/test_hitl_invariant.py`. Nenhum dos dois textos foi reconciliado — os dois
nasceram no mesmo commit inicial e seguiram divergindo.

O REQ-1 da S-01 (D-1) topou com a divergência. Ela não podia ser resolvida como conserto de
redação por dois motivos: o ADR-003 está **aceito**, e o `CLAUDE.md` trata ADR aceito como
imutável; e a precedência do harness coloca `docs/riscos.md` **acima** de `docs/testes.md`, de
modo que "o documento mais novo vence" não decidia sozinho.

## Alternativas consideradas
1. **Criar `tests/integration/`** — honra a letra do ADR-003 e da matriz de riscos. Em troca,
   o job `test` do CI passa a exigir `docker compose` (hoje sobe em segundos, sem contêiner),
   e contradiz a escolha argumentada de `docs/testes.md` §1, que já declarou o preço que paga:
   o que só se prova com infraestrutura real é verificado à mão no `/verificar-spec`, com
   resultado registrado no relatório.
2. **Errata no ADR-003, sem ADR novo** — mais barato e resolve a leitura. Mas deixa uma mudança
   de arquitetura de testes registrada como nota de rodapé, sem alternativa considerada e sem
   consequência declarada. Decisão que não vira ADR reaparece como discussão na próxima spec.
3. **ADR novo fixando duas camadas** — `unit/` responde *"a função faz a conta certa?"*;
   `security/` responde *"existe caminho de código até a ação proibida?"*. A invariante do HITL
   é a segunda pergunta, não a primeira, e é onde `docs/testes.md` já a colocou.

## Decisão
Opção 3. O repositório tem **duas camadas de teste automatizado e apenas duas**, como descrito
em `docs/testes.md` §1. A invariante do ADR-003 é provada em `tests/security/test_hitl_invariant.py`.

Onde os documentos diziam *"testado em integração"*, passam a dizer a camada real. **A exigência
não afrouxa** — muda de endereço, e para um endereço mais forte: um teste de `security/` prova
que o caminho proibido **não existe**, enquanto um teste de integração provaria apenas que o
caminho feliz funciona. A distinção é a própria regra de ouro aplicada a teste.

O que depende de infraestrutura real — retomada após restart de processo, adapter contra o
sandbox do gateway — continua verificado **à mão** no `/verificar-spec`, com resultado no
relatório. Está declarado, não automatizado, e `docs/testes.md` §1 já dizia isso.

## Consequências
+ Um só mapa risco → teste, em `docs/testes.md` §2, sem segunda versão discordando na matriz
  de riscos.
+ O job `test` do CI continua sem contêiner: as duas camadas rodam sem `docker compose`.
+ A invariante do HITL sobe de nível: passa a ser provada como *inalcançabilidade*, não como
  *fluxo que funcionou*.
− O que só a infraestrutura real prova fica dependente de disciplina humana no `/verificar-spec`.
  É o preço que `docs/testes.md` §1 já havia aceito, agora com decisão rastreável por trás.
− A coluna "Verificação" de `docs/riscos.md` deixa de ser texto livre e passa a ter que casar
  com a camada e o arquivo de `docs/testes.md` §2. Divergir volta a ser bug de documento.
