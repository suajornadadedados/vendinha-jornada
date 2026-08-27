---
description: Encerra uma spec — verificação independente, correção, e só então o PR
argument-hint: <id da spec, ex.: S-11>
---

# /fechar-spec — Encerramento de uma spec

Entrada: o id da spec (`$ARGUMENTS`). Pré-condição: implementação terminada nesta branch.

Este comando é o `CLAUDE.md`, fluxo **itens 4 a 6**, em forma executável. O `/entregar-spec`
te trouxe até aqui; daqui em diante o caminho é um só, e ele **não passa pelo PR antes do
veredito**. O hook `.claude/hooks/gate-pr.py` recusa `gh pr create` se você tentar.

---

## 1. Antes de chamar o revisor — arrume a sua casa

Não é para o revisor achar o que você já sabe. Rode e confirme verde:

- suíte, lint, typecheck (`backend/.venv/Scripts/python.exe -m pytest`, `ruff check`, `ruff format --check`);
- evals, se a spec tocou prompt (`make evals` — nesta máquina `make` não existe: rode a linha
  de dentro do alvo);
- `git status --short` limpo, tudo commitado, branch empurrada;
- frontmatter da spec com `status: em-revisao`;
- a seção **Descobertas** da spec preenchida, se apareceu qualquer coisa fora do escopo.

Se algo aqui está vermelho, **pare e conserte**. Mandar trabalho quebrado para a verificação
gasta uma revisão inteira para descobrir o que um `pytest` descobriria.

## 2. Disparar a verificação — com o id, e nada além dele

Chame o subagente **`verificador-de-spec`** com uma mensagem que contenha **exatamente**
`$ARGUMENTS` e mais nada.

> **Nada além do id.** Não diga o que já está verde, o que testou, quais arquivos "valem a
> pena olhar", quanto do trabalho está pronto, nem o que espera que ele ache. As instruções
> do revisor vivem versionadas em `.claude/agents/verificador-de-spec.md` justamente para que
> a sua contribuição encolha a um parâmetro (ADR-005). Um prompt escrito à mão aqui devolve a
> você o enquadramento que aquele arquivo existe para tirar — e aí não há revisor, há o autor
> com outra voz. O revisor registra qualquer enquadramento recebido numa seção do relatório:
> o viés fica visível, não some.

Ele escreve `docs/specs/relatorios/$ARGUMENTS-verificacao.md`, com frontmatter
(`spec`, `veredito`, `commit`, `data`), tabela de conformidade, tabela de falsificações e o
porquê do veredito — inclusive por que **não** o veredito vizinho.

> **Quando usar sessão nova em vez do subagente:** sempre que o veredito vier bom demais.
> APROVADO sem uma única ressalva mede o prompt antes de medir a entrega. O subagente elimina
> o **contexto**; sessão nova elimina a **autoria**, e continua sendo o portão mais forte
> (`/verificar-spec`).

## 3. Ler o relatório inteiro. Sim, inteiro

Comece pela **tabela de falsificações**, não pelo veredito. É lá que se vê se os testes mordem:
uma quebra deliberada que sobreviveu à suíte é achado ALTO sobre o *teste*, e um teste que não
prova o que o nome diz é a coisa mais cara que sai de uma spec, porque ele custa confiança em
tudo que vier depois.

## 4. Corrigir — nesta mesma branch, antes do PR

- **REPROVADO** → corrija e **volte ao passo 2**. O relatório continua dizendo REPROVADO até
  que uma nova verificação o sobrescreva; o portão recusa o PR enquanto disser. É deliberado:
  reprovação se destrava com re-verificação, não com argumento no PR.
- **APROVADO COM RESSALVAS** → percorra as **condições de fechamento** na ordem em que o
  relatório as numerou. Para cada uma, uma de duas saídas, sem terceira: corrigida no código,
  ou registrada por escrito na spec (Descobertas) com a decisão do PO. Ressalva que some sem
  nenhuma das duas volta como dívida na spec seguinte.
- **APROVADO** → siga.

Corrigiu? A correção entrou **depois** do veredito e não foi verificada. O portão vai notar
(ele compara o `commit` do relatório com o HEAD) e vai **perguntar**, listando o que entrou
depois. Duas respostas legítimas:

- a correção mexeu no que foi verificado → **volte ao passo 2** e re-verifique;
- a correção foi pontual e periférica → assuma e siga, sabendo que o PR carrega commits não
  verificados. Quem aprova isso é você, por escrito no PR — não o hook.

## 5. Commitar o relatório

`docs(<escopo>): relatório de verificação da $ARGUMENTS`. O relatório é evidência do PR: se
ficar fora do commit, o PR não o carrega e o portão pergunta o porquê.

## 6. Só então: o PR

Template preenchido, `Closes #N` com o número da issue **lido do frontmatter da spec** (o
número não é derivável do id), o que muda, como testar, evidência (screenshot + link do trace
Langfuse), e o relatório anexado ou linkado.

Se o `gh pr create` for recusado, **leia a recusa em vez de contorná-la**. Ela diz qual das
condições falta. Abrir o PR pela web para escapar do hook é fraudar o próprio método — e fica
no histórico, que é onde este projeto mostra as decisões.

---

## O portão, em uma frase

`.claude/hooks/gate-pr.py` intercepta `gh pr create` numa branch `spec/s-XX-*` e decide:
**recusa** sem relatório ou com veredito REPROVADO; **pergunta** quando o relatório está
defasado, não commitado ou ilegível; **cala** quando está verificado e fresco.

É a regra de ouro do projeto virada para dentro: o modelo decide o que dizer, **o código
decide o que pode ser feito**. Sem ele, o item 4 do `CLAUDE.md` é um pedido — e pedido em
contexto é probabilístico, principalmente no fim de uma sessão longa de implementação, que é
exatamente quando este fluxo roda.
