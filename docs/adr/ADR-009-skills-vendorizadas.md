# ADR-009 — Skills vendorizadas com origem fixada por SHA

- Status: aceito · Data: 2026-08-03 · Decisão: D12 · Riscos: R7 (parcial)

## Contexto
O agente traz uma noção genérica e frequentemente desatualizada das bibliotecas da stack —
`interrupt` do LangGraph, mascaramento no Langfuse, componentes do shadcn. Skills resolvem isso,
mas a forma de instalá-las é uma decisão de arquitetura, não de conveniência.

Duas restrições apertam a escolha. A primeira vem do cliente: *"um sistema que a sua equipe
consiga colocar para rodar"* (docs/requisitos.md) — quem clona precisa receber o projeto inteiro,
não só o código. A segunda vem do ADR-005: autor e revisor são sessões diferentes, e a comparação
entre o que foi implementado e o que a spec pedia só é honesta se ambos rodarem com exatamente as
mesmas instruções.

## Alternativas consideradas
1. **Plugin/marketplace instalado por máquina** — atualização automática, repositório enxuto,
   nada a manter. Em compensação o harness não acompanha o clone (quem baixa recebe o código sem
   as skills) e a versão pode mudar **entre a implementação e a verificação da mesma spec** — se
   autor e revisor divergirem, a divergência pode ser da skill, não do código, e não há como saber.
2. **Vendorizar: copiar as skills para `.claude/skills/`, versionadas, com o SHA de origem fixado
   em `.claude/skills.lock.json`** — o harness viaja junto com o código e a versão é a mesma para
   todo mundo, sempre. Custa tamanho de repositório e transforma atualização em trabalho manual.

## Decisão
Opção 2. `.claude/skills/` é **derivado** de `.claude/skills.lock.json`, materializado por
`scripts/vendor-skills.sh`. Cada entrada do lockfile carrega um campo `porque` obrigatório ligando
a skill a uma spec ou requisito — skill sem justificativa não entra. As candidatas recusadas ficam
registradas em `rejeitadas`, com motivo.

O limite da decisão: **vendoriza-se markdown, não se vendoriza software.** Skill que traz CLI ou
assets binários (`ui-ux-pro-max`, `frontend-slides` — 16 MB) permanece como plugin e é roteada pela
skill própria `vendinha-harness`. Se o plugin não estiver na máquina, o trabalho segue sem ele.

Skill vendorizada nunca é editada à mão: a alteração seria perdida no próximo `vendor-skills.sh` e
o job `skills-drift` do CI reprova o PR. Adaptação ao contexto do projeto vive em
`.claude/skills/vendinha-harness/SKILL.md`, e é para isso que a seção "Conflitos já conhecidos"
existe.

## Consequências
+ Quem clona recebe o harness junto com o código — o setup é reproduzível de fato, não por
  instrução de README.
+ Autor e revisor rodam com as mesmas skills, byte a byte. É o que torna `/verificar-spec` uma
  comparação honesta em vez de uma comparação entre dois ambientes diferentes.
+ A lista de recusadas documenta o critério: skills de issue tracker competem com o SDD do
  ADR-005; `langsmith-*` empurra a concorrente do ADR-007.
− O repositório carrega ~80 arquivos de terceiros. Aceito: são markdown, o diff é legível e o
  ganho de reprodutibilidade paga.
− Atualizar skill vira trabalho manual (`pin-skills.sh` e revisão do diff). Aceito conscientemente:
  atualização silenciosa é exatamente o que esta decisão existe para impedir.
− O job `skills-drift` vai reprovar PR de quem editar uma skill à mão sem saber da regra. A
  mensagem de erro precisa apontar o caminho, não só falhar.
