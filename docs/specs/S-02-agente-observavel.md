---
id: S-02
titulo: Agente base observável
status: em-execucao
branch: spec/s-02-agente-observavel
issue: #3
adrs: [ADR-001, ADR-007, ADR-010, ADR-012]
riscos_cobertos: [R5, R6, R9]
---

# S-02 — Agente base observável

## Objetivo
O menor agente possível — porém com observabilidade, privacidade e limites de custo desde o
primeiro trace. Observabilidade no commit 1, não no incidente 1.

## Requisitos
- [ ] REQ-1 FastAPI com `POST /chat` (SSE) e sessões; grafo LangGraph mínimo (um nó de conversa).
- [ ] REQ-2 Checkpointer em Postgres; estado carrega apenas IDs (pointer-not-payload).
- [ ] REQ-3 Langfuse Cloud instrumentado (`LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY`,
      `LANGFUSE_SECRET_KEY`): trace por sessão com tools, custo, latência. Indisponibilidade
      do Langfuse não pode propagar exceção para o atendimento (ADR-010).
      *O texto original dizia `LANGFUSE_HOST`, nome da v3 do SDK. Ver D-1.*
- [ ] REQ-4 Mascaramento de PII (CPF, e-mail, nome) na camada de instrumentação **antes** do envio.
      Com Langfuse Cloud o trace sai da infra, então este REQ é invariante de release: sem o
      teste de redação verde, a spec não fecha (ADR-010, R5).
- [ ] REQ-5 Budget cap por sessão e timeout por tool via config; exceder = resposta honesta de limite.
      A unidade do cap é **token**, não USD — ver D-2.
- [ ] REQ-6 Provedor de LLM agnóstico com credencial configurável em runtime (ADR-012):
      `GET /models` lista os modelos disponíveis a partir das credenciais existentes,
      `GET`/`PUT /config` leem e gravam a configuração da instância, e o campo `model` do
      `POST /chat` é validado contra a allowlist do servidor. A credencial é cifrada em
      repouso, nunca volta pela API e nunca entra em trace ou log. Ver D-3.

## Fora de escopo
- RAG, subagents, tools de negócio.
- **A tela de configuração.** A S-02 entrega o contrato de API (e o OpenAPI de onde os tipos
  TypeScript são gerados, ADR-004); a interface é entregável da S-07.
- **Credencial por usuário.** Não existe usuário nem autenticação nesta spec: o que se
  persiste é uma linha de configuração da instância (ADR-012).

## Tasks (cada uma vira um commit)
1. `adr(s-02): provider-agnostic llm with runtime credentials` — ADR-012, D15 e a emenda da spec
2. `feat(s-02): fastapi chat endpoint with sse and session handling`
3. `feat(s-02): minimal langgraph graph with postgres checkpointer`
4. `feat(s-02): langfuse instrumentation with pii masking`
5. `feat(s-02): session budget cap and per-tool timeout`
6. `feat(s-02): runtime provider config with encrypted credentials`
7. `ci(s-02): extend typecheck to the test suite` — ressalva R-4 da verificação da S-01

## BDD
```gherkin
Cenário: PII nunca aparece em trace
  Dado uma conversa em que o cliente informa um CPF de teste
  Quando inspeciono o trace da sessão no Langfuse
  Então o CPF aparece mascarado e nunca em texto claro

Cenário: retomada de sessão
  Dado uma conversa interrompida após 3 turnos
  Quando o cliente retorna com o mesmo session_id
  Então o grafo retoma do checkpoint sem perda de contexto

Cenário: a credencial não volta pela porta da frente
  Dado que o operador gravou uma API key pela configuração
  Quando qualquer rota da API é consultada, incluindo a de configuração
  Então nenhuma resposta contém a chave — só `configured: true` e uma dica mascarada
```

## Métricas de sucesso
| Métrica | Alvo | Como medir |
|---|---|---|
| Sessões com trace completo | 100% | Langfuse |
| PII em claro em traces/logs | 0 ocorrências | teste automatizado de redação |
| Credencial em claro em traces/logs/respostas | 0 ocorrências | mesmo teste, caso de credencial |
| p95 primeiro token | ≤ 3s | métrica no trace |

## Verificação independente
- Enviar CPF/e-mail de teste e auditar o trace bruto.
- Forçar estouro de budget e verificar a degradação honesta — e que a resposta **não** revela
  valor de configuração nem nome de limite (`evals/adversarial/adversarial-006`).
- Gravar uma chave falsa pela API e varrer resposta, log e trace atrás dela em claro.
- Reiniciar o processo de verdade e retomar a sessão pelo mesmo `session_id` — é a metade
  manual do R9, declarada em `docs/testes.md` §1 porque não existe camada de integração.

## Descobertas (preenchido durante a execução)

**D-1 — `LANGFUSE_HOST` é o nome da v3; o SDK atual documenta `LANGFUSE_BASE_URL`.**
O REQ-3, o `.env.example`, o comentário do `docker-compose.yml` e a §Consequências do
ADR-010 nomeiam `LANGFUSE_HOST`. A documentação do SDK Python v4 (`langfuse 4.x`, reescrito
sobre OpenTelemetry) usa `LANGFUSE_BASE_URL` em todos os exemplos e não menciona o nome
antigo em `docs/observability/sdk/overview`.

Resolvido dentro do escopo: o código lê `LANGFUSE_BASE_URL` e aceita `LANGFUSE_HOST` como
fallback — quem já tem um `.env` escrito não quebra. O `.env.example` e o REQ-3 passam a
documentar o nome atual. **O ADR-010 não foi tocado:** a decisão que ele registra é *Langfuse
Cloud em vez de self-hosted*, e ela continua inteira; o que mudou foi o nome de uma variável
de terceiro, que é consequência e não decisão. Emendar um ADR aceito por causa disso
gastaria o mecanismo que a S-01 construiu para mudanças que de fato revogam decisão.

**D-2 — o `.env.example` declarava `SESSION_BUDGET_USD`; o cap é por token.**
Medir custo em USD exigiria uma tabela de preço por modelo dentro do repositório — e, agora
que o provedor é configurável (ADR-012), seriam várias, desatualizando em silêncio. O
`usage_metadata` do LangChain dá contagem de token normalizada entre fornecedores, o que
torna `tests/unit/test_budget_guard.py` determinístico e sem rede. O custo em R$ continua
visível no dashboard do Langfuse, que é exatamente onde `docs/riscos.md` R6 já o colocava.
Decidido pelo PO na abertura da spec. `SESSION_BUDGET_USD` vira `SESSION_BUDGET_TOKENS`.

**D-3 — provedor agnóstico e chave pela UI: decisão do PO, registrada em ADR-012.**
O pedido — *"funcionar com Anthropic, OpenAI ou outro provedor; o usuário só coloca a chave
dele, e o modelo é configurável na UI"* — não cabia em nenhum dos cinco requisitos originais
e cria uma classe nova de segredo dentro do processo. Foi tratado como decisão de
arquitetura, não como implementação silenciosa: **ADR-012** (D15), REQ-6 na spec, e três
invariantes que o código prova — allowlist no servidor, credencial que nunca volta pela API,
credencial que nunca entra em trace ou log. A cifra em repouso protege contra dump do banco
e **não** contra quem já tem o `.env`; está escrito assim no ADR de propósito.

**D-4 — a credencial não ganha seam novo.**
O caso "a chave não sai deste processo" entra em `tests/security/test_pii_redaction.py`, e
não em arquivo próprio. O seam é o mesmo que o R5 já ocupa — *o que atravessa a fronteira do
processo* — e `docs/testes.md` §2 mapeia esse seam para aquele arquivo. Criar
`test_credential_leak.py` seria inventar camada no meio da execução, que a §3 item 6 manda
registrar em vez de improvisar. Registrado para o `/verificar-spec` não ler a ausência do
arquivo como lacuna.

## Definition of Done
- [ ] Todos os requisitos CONFORMES no relatório de verificação
- [ ] CI verde (lint, typecheck, testes, evals)
- [ ] PR com evidência (screenshot + trace Langfuse)
- [ ] Relatório /verificar-spec anexado com veredito APROVADO
