# ADR-010 — Langfuse Cloud em vez de self-hosted

- Status: aceito · Data: 2026-08-20 · Decisão: D13 · Riscos: R5, R6
- Substitui o ADR-007 **no ponto de hospedagem**. O restante do ADR-007 permanece vigente.

## Contexto
O ADR-007 decidiu observabilidade desde o commit 1, com PII mascarada e Langfuse **self-hosted**.
O argumento registrado para o self-hosted — e para recusar o LangSmith — foi *"a PII sairia da
infra"*.

Ao montar a S-00 esse argumento não sobreviveu à própria arquitetura que o ADR-007 definiu. Se o
mascaramento acontece **na origem**, na camada de instrumentação, então CPF, e-mail e nome nunca
entram no trace — não existe PII para sair da infra. O argumento estava protegendo contra um
vazamento que a decisão anterior já havia eliminado, e em troca colocava um Postgres, um worker e
um serviço web a mais no `docker compose up` do quickstart, contra a RNF-1 (clone rodando em
≤ 10 min) e contra a persona "Dev da comunidade" do PRD §4.

Vale registrar a ordem correta do raciocínio, porque ela inverte a intuição: **não é a hospedagem
que garante a privacidade — é o mascaramento.** Self-hosted com trace ingênuo vaza PII para o
próprio log; cloud com mascaramento na origem não tem o que vazar.

## Alternativas consideradas
1. **Manter Langfuse self-hosted no compose** — o dado nunca trafega para terceiro, e a
   demonstração fica independente de conta externa. Em compensação são três contêineres a mais no
   quickstart, migração de schema do Langfuse vira problema nosso, e a promessa de "sobe em um
   comando" fica mais frágil justamente na persona que o PRD elegeu como crítica.
2. **Langfuse Cloud, com o mascaramento na origem inalterado** — quickstart menor, nada de operar
   banco de observabilidade, e o mesmo SDK. Em troca, aceita-se dependência de terceiro no caminho
   da observabilidade e a região do projeto passa a ser decisão de LGPD.

## Decisão
Opção 2. O projeto usa **Langfuse Cloud**; `docker compose` sobe apenas Postgres e Qdrant. O
mascaramento de PII na origem, definido no ADR-007, é **pré-condição** desta decisão, não
complemento: sem ele, esta decisão não pode ser tomada.

A escolha do **fornecedor** continua sendo Langfuse, e agora por um motivo diferente do que estava
escrito. Langfuse é open-source: se a região, o preço ou a disponibilidade deixarem de servir,
sobe-se a mesma stack self-hosted e troca-se a variável de ambiente, sem reescrever instrumentação.
**A decisão de hospedagem é reversível; a de fornecedor não seria.** É por isso que o LangSmith
segue recusado — não porque "a PII sairia da infra" (com mascaramento na origem, isso vale para
qualquer nuvem), mas porque não oferece essa saída.

## Consequências
+ Quickstart menor e mais confiável: três contêineres a menos, nenhuma migração de schema de
  terceiro para operar. RNF-1 fica mais fácil de cumprir, não mais difícil.
+ A decisão de hospedagem passa a ser uma variável de ambiente, não uma reescrita.
+ O argumento de privacidade fica onde ele de fato mora — no mascaramento — em vez de ficar
  apoiado na topologia de rede, onde era frágil.
− Dependência de terceiro no caminho da observabilidade. Indisponibilidade do Langfuse não pode
  derrubar o atendimento: a instrumentação falha em silêncio, nunca propaga exceção.
− A região do projeto (EU/US) vira decisão de LGPD e precisa estar registrada no runbook.
− Uma chave a mais no CI e no `.env.example` (`LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`,
  `LANGFUSE_SECRET_KEY`), com a superfície de vazamento de credencial que isso implica.
− **O teste de redação de PII (R5) deixa de ser conveniência e vira invariante de release.** Antes,
  uma falha de mascaramento vazava para um contêiner na própria máquina; agora vaza para fora da
  infra. O teste não é opcional em nenhuma spec que toque instrumentação.
