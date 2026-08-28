---
spec: S-07
veredito: APROVADO COM RESSALVAS
commit: 57f80cb8dc8ef8605fe66177c33bf4064731fea1
branch: spec/s-07-frontend
data: 2026-08-28
---

# Relatório de verificação independente — S-07 (Frontend integrado e API de observação)

| | |
|---|---|
| **Spec** | `docs/specs/S-07-frontend-integrado.md` (`status: em-revisao`) |
| **Branch** | `spec/s-07-frontend` @ `57f80cb` (16 commits) |
| **Base** | `origin/main` @ `bfd4f3d` — ancestral de `HEAD`, diff não inflado |
| **PR** | **não existe** no momento da verificação — correto sob o `CLAUDE.md` item 4 |
| **Issue** | [#8](https://github.com/suajornadadedados/vendinha-jornada/issues/8) — OPEN, título bate com a spec |
| **Diff** | 144 arquivos · +92.949 / −41 — dos quais **73 arquivos / +23.736 são a entrega da S-07**; o resto é o commit `57f80cb` (ver NC-1) |
| **Suíte** | **1006 passed**, 0 failed, 0 error, 0 skipped, 131 s (`tests/unit` + `tests/security`) |
| **S-07 isolada** | `tests/unit/test_painel.py` + `tests/security/test_admin_boundary.py` → **44 passed** |
| **Lint** | `ruff check .` → *All checks passed* · `ruff format --check .` → 160 arquivos ok |
| **Typecheck** | `mypy` backend 46 arquivos · `mypy` tests 33 arquivos · `tsc -b --noEmit` no frontend — os três sem erro |
| **Contrato (REQ-1)** | regerei `openapi.json` e `schema.d.ts` do zero: `git diff --exit-code` limpo — **sem drift** |
| **Evals / falsificações** | **NÃO EXECUTADOS** — restrição operacional declarada pelo PO nesta rodada |
| **Verificação em navegador** | **NÃO EXECUTADA** — fora do escopo autorizado desta rodada (ver "Não verificável") |
| **Achados** | 1 Alta (bloqueante) · 2 Média · 2 Baixa |
| **Ambiente** | Windows 11 · `uv run --project backend` · Node 22 / `npm --prefix frontend` |
| **Veredito** | **APROVADO COM RESSALVAS** — 1 condição bloqueante antes do merge |

---

## Enquadramento recebido

O prompt desta rodada pediu explicitamente para **não** rodar gates de eval nem falsificação, e
para restringir a execução a testes e lint. Registro isso porque muda o que este relatório pode
afirmar: tudo que depende de navegador aberto, de backend derrubado no meio da jornada, ou de
julgamento de eval está marcado abaixo como **NÃO VERIFICÁVEL nesta rodada**, e não como conforme.
O enquadramento do autor sobre a qualidade da entrega não foi lido nem usado.

---

## Tabela de conformidade

| REQ | O que a spec pede | Onde verifiquei | Veredito |
|---|---|---|---|
| REQ-1 | Cliente TS gerado do OpenAPI, sem subir servidor; CI reprova drift; zero tipo de fronteira à mão | `backend/vendinha/openapi.py`, `frontend/src/api/schema.d.ts`, job `contrato` no `ci.yml` | **CONFORME** — regerei os dois artefatos localmente e o `git diff` saiu vazio. Todo tipo de fronteira em `dados.ts` e `eventos.ts` é alias de `components["schemas"][...]`; os únicos `interface` escritos à mão (`Painel`, `Fala`, `EstadoDoPedido`, `EstadoDaNota`, `EventoBruto`, `OpcoesDoStream`) são estado de UI, não contrato de rede |
| REQ-2 | Read model de sessões/turnos, mensagens lidas do checkpointer | `backend/vendinha/telemetria.py`, `admin.py:149 ler_conversa` | **CONFORME** — o DDL cria `sessao`, `turno` e `veredito_de_composicao`, e **nenhuma** delas tem coluna de conteúdo de mensagem. O detalhe da conversa lê o checkpointer via `ler_conversa(checkpointer, session_id)` |
| REQ-3 | Barramento in-process, fila limitada, descarte do mais antigo, evento de atraso, nunca bloqueia | `backend/vendinha/eventos.py`; `test_painel.py:179 test_a_fila_cheia_descarta_o_antigo_e_avisa`, `:198 test_sair_do_contexto_descadastra_o_assinante` | **CONFORME** |
| REQ-4 | `/admin/*` read-only e fail-closed no `X-Operador-Token` | `backend/vendinha/admin.py`; `tests/security/test_admin_boundary.py` | **CONFORME** — a suíte cobre as três portas (sem token, token errado, e `OPERADOR_API_TOKEN` ausente do ambiente ⇒ fecha inteiro), parametrizadas por rota, mais `test_o_painel_nao_expoe_nenhuma_rota_de_escrita` |
| REQ-5 | Custo em `Decimal` no backend, tabela versionada, `None` e nunca zero | `backend/vendinha/precos.py`, `data/precos-modelos.json`; `test_painel.py:106,120,126,138` | **CONFORME** — quatro testes distintos afirmam que desconhecido / sem preço / sem cotação viram ausência, não zero |
| REQ-6 | Push por sessão: o cliente recebe a NF sem perguntar | `app.py:665 GET /eventos/sessao/{session_id}`; `test_painel.py:155,164`, `test_admin_boundary.py:168` | **CONFORME no código e na suíte** — o isolamento entre sessões é testado nas duas camadas. O comportamento fim-a-fim no widget é NÃO VERIFICÁVEL nesta rodada |
| REQ-7 | Landing pública, identidade própria, FAB, bundle sem JS do painel | `frontend/src/site/Site.tsx`, `site.css`, `vite.config.ts` (duas entradas) | **CONFORME no diff** — entradas separadas, CSS próprio, zero import de `admin/` em `site/`. Aparência NÃO VERIFICÁVEL nesta rodada |
| REQ-8 | Widget com SSE token a token, estados honestos, sem stack trace, `session_id` em `localStorage` | `site/Widget.tsx`, `site/useConversa.ts`, `api/sse.ts` | **CONFORME no diff** — `localStorage` com `try/catch`, estado `desconectado` exposto na UI, reenvio oferecido |
| REQ-9 | Composição visível enquanto montada, exatamente como o validador devolveu, motivo real | `site/Composicao.tsx`; `Veredito = components["schemas"]["ComposicaoValidada"]` | **CONFORME** — o veredito é renderizado a partir do tipo gerado, sem recomposição em JS |
| REQ-10 | Painel ao vivo ≤1s, por evento, zero polling | `admin/dados.ts:78-79`, `useEventos` | **CONFORME quanto a "zero polling"** — `refetchInterval: false`, `refetchOnWindowFocus: false`, e um único assinante SSE que traduz evento em invalidação seletiva. O `setTimeout` em `sse.ts:159` é backoff de reconexão, não poll. **O alvo de ≤1s é NÃO VERIFICÁVEL nesta rodada** (exige cronômetro em duas abas) |
| REQ-11 | Fila HITL com sino, badge, destinatário PJ completo, motivo obrigatório na rejeição | `admin/Telas.tsx` (`Fila`), `dados.ts` (`aviso`, `pendentes`) | **CONFORME no diff** |
| REQ-12 | Rastreabilidade: proposto × validado, tools, latência e custo por turno; Langfuse só com chaves | `Telas.tsx` (`Rastreabilidade`) | **CONFORME no diff** |
| REQ-13 | Pedidos e métricas; KPIs somados no backend | `Telas.tsx`, `backend/vendinha/metricas.py`; `test_painel.py:209-334` | **CONFORME** — janela vazia devolve ausência e não zero (`test_os_kpis_de_uma_janela_vazia_sao_ausencia_e_nao_zero`), divisão sem denominador idem, e recusa com dois motivos conta nos dois |
| REQ-14 | Config via `PUT /config`; prompts em modo leitura, com caminho e sha | `admin.py:353 prompts`, `Telas.tsx` (`Config`); `test_admin_boundary.py:205` | **CONFORME** — `editavel` é literal `False` no contrato, então o tipo TS é `false` e um botão de salvar não compila. É a implementação mais forte possível do ADR-015 aqui |
| REQ-15 | Sistema visual commitado antes do primeiro componente | `git log --diff-filter=A` | **CONFORME** — `docs/design/sistema-visual.md` entrou em `308f775`; o primeiro componente de `frontend/src/components/ui/` entrou em `163477e`, dois commits depois |

---

## Métricas de sucesso — medidas, não estimadas

| Métrica | Alvo | Medido | |
|---|---|---|---|
| Tipos da fronteira escritos à mão | 0 | **0** — varredura de `interface`/`type` em `frontend/src` fora de `schema.d.ts`: todos os que descrevem a API são alias do schema gerado | ✅ |
| Contas de dinheiro no frontend | 0 | **0** — a única aritmética em `Graficos.tsx` é geometria de barra (`valor / escala * 100` para largura em %); o número exibido é o `valor` do backend, sem transformação | ✅ |
| Requisições de polling no painel | 0 | **0 no código** — `refetchInterval: false`, `refetchOnWindowFocus: false`, nenhum `setInterval`. Não medido em aba Network (fora do escopo desta rodada) | ✅ (estático) |
| Rotas `/admin/*` que respondem sem token | 0 | **0** — `test_admin_boundary.py`, parametrizado, 3 formas de ausência de credencial | ✅ |
| Drift entre `openapi.json` e o cliente TS | 0 | **0** — regeração local + `git diff --exit-code` limpo | ✅ |
| Componentes shadcn antes do sistema visual | 0 | **0** — `308f775` < `163477e` | ✅ |
| Mensagens copiadas para tabela nova | 0 | **0** — DDL de `telemetria.py` sem coluna de conteúdo | ✅ |
| Suíte | verde | **1006 passed / 0 failed** | ✅ |
| Lint + typecheck (ruff, mypy ×2, tsc) | verde | os quatro limpos | ✅ |
| Jornada completa sem recarregar a página | 100% | **não medido** — exige navegador | ⚠️ |
| Atraso evento → tela | ≤ 1s | **não medido** — exige duas abas e cronômetro | ⚠️ |
| Estados distinguíveis só por matiz | 0 | **não medido** — exige revisão de tela | ⚠️ |

---

## Achados

### NC-1 — Alta, **bloqueante** — o commit `57f80cb` contradiz a própria spec, o ADR-009, e deixa um check obrigatório vermelho

O último commit da branch, `docs(s-07): adicionei skill de ux`, vendoriza a skill `ui-ux-pro-max`
(70 arquivos, +69.214 linhas) e adiciona um `skills-lock.json` **na raiz**. Quatro problemas, e
nenhum deles é de estilo:

1. **A DESC-1 desta mesma spec diz, por escrito, que isso ficou "Parado para decisão do PO — não
   commitado nesta branch".** O commit veio depois e fez o contrário. Documento normativo e código
   discordando é exatamente o estado que o `CLAUDE.md` manda resolver a favor da spec.
2. **O ADR-009 nomeia `ui-ux-pro-max` como o caso que *não* se vendoriza** ("vendoriza-se markdown,
   não se vendoriza software"). Reverter essa decisão é legítimo; fazê-lo por um commit `docs(...)`
   dentro de uma branch de spec, sem tocar no ADR, não é.
3. **O check obrigatório `skills-drift` fica vermelho.** Rodei `bash scripts/vendor-skills.sh
   --check`: `DRIFT entre o lockfile e .claude/skills/: Only in .claude/skills: ui-ux-pro-max`.
   Este PR não passa no CI como está.
4. **Segunda fonte de verdade sobre a mesma coisa**: `skills-lock.json` na raiz duplica o
   `.claude/skills.lock.json` que o ADR-009 estabeleceu como fonte única — e com formato diferente,
   sem o campo `porque` obrigatório.

Ainda no mesmo commit, uma alteração não relacionada e provavelmente acidental em
`.claude/commands/fechar-spec.md`: `argument-hint: <id da spec, ex.: S-11>` virou
`<id da spec, ex- S-11>`. É dano cosmético num arquivo do harness, entrando de carona num commit
de skill.

**Condição de fechamento:** reverter `57f80cb` nesta branch, devolvendo a decisão à DESC-1 como ela
está escrita, e confirmar com `bash scripts/vendor-skills.sh --check` limpo. Se o PO quiser mesmo
vendorizar a skill, isso é um ADR e um PR próprios — `.claude/skills.lock.json` com o campo
`porque`, `vendor-skills.sh` rematerializando, e um lockfile só.

### NC-2 — Média — `frontend/tsconfig.tsbuildinfo` está commitado

Artefato de build incremental do `tsc`, com caminhos e hashes da máquina de quem compilou. Vai
gerar conflito em todo PR que toque o frontend e não descreve nada do produto. Pertence ao
`.gitignore`. Não bloqueia o merge, mas quanto mais tarde sair, mais atrito acumula.

### NC-3 — Média — três métricas da própria spec continuam sem número

"Jornada completa sem recarregar", "atraso ≤1s" e "estados distinguíveis só por matiz" são alvos
que a spec declarou e que **ninguém mediu ainda** — o autor registrou explicitamente que deixou os
dois primeiros para a verificação independente, e esta rodada foi restringida a testes e lint pelo
PO. Não é falha da entrega; é uma lacuna de evidência que precisa estar visível no PR em vez de ser
lida como conformidade. O roteiro para fechá-la já existe (`S-07-roteiro-de-demo.md`).

### NC-4 — Baixa — o cenário BDD "a conexão cai e a tela não mente" foi lido, não exercido

O código faz a coisa certa: `Admin.tsx:127-130` troca o rótulo para `desconectado — dados de
<hora>` e `painel__main--velho` esmaece o conteúdo, ou seja, número velho aparece **carimbado**
como velho em vez de posar de atual. Isso é leitura de diff, não observação. O cenário só fecha com
a API derrubada e as duas telas abertas.

### NC-5 — Baixa — o `status` da spec ainda é `em-revisao`

Coerente com o momento — é o que a verificação está fazendo —, mas o `CLAUDE.md` pede atualizar o
frontmatter ao concluir. Fica como lembrete para o fechamento.

---

## Invariantes globais

| Invariante | Resultado |
|---|---|
| Secrets no diff | **nenhum** — varredura por chaves de API, chaves privadas e CNPJ no diff da entrega: vazio |
| Regra de ouro (dinheiro é do código) | **respeitada** — nenhum total, custo ou KPI somado em JavaScript; `Decimal` no backend, string no contrato |
| Escrita no domínio a partir do painel | **nenhuma** — `test_o_painel_nao_expoe_nenhuma_rota_de_escrita` afirma isso, e as únicas escritas expostas (decisão HITL, config) já existiam |
| Fronteira de permissões dos subagents | **intocada** — o diff da S-07 não altera `subagents.py` além de ler os prompts vigentes |
| Pointer-not-payload (RNF-6) | **respeitado** — mensagens vêm do checkpointer |
| Escopo da spec | **violado uma vez**, e só em NC-1 |

---

## Não verificável nesta rodada (e por quê)

Por restrição operacional declarada pelo PO, não executei: evals, falsificações, `docker compose
up`, a jornada em navegador, o teste de backend derrubado, e a medição de latência evento→tela.
Os itens 1, 2 e parte do 6 do roteiro de verificação da própria spec permanecem **abertos**.
Nenhum deles foi marcado como conforme acima.

---

## Veredito

**APROVADO COM RESSALVAS.**

A entrega da S-07 propriamente dita — 73 arquivos, backend de observação, contrato gerado e as duas
telas — está **conforme nos 15 requisitos** no que é verificável por código, teste e diff. Os
portões que mais importam nesta spec são justamente os que a spec disse que importariam, e todos
passam com número medido: zero drift de contrato, zero conta de dinheiro no navegador, zero rota de
painel aberta, zero polling, zero mensagem copiada para tabela nova, e a ordem dos commits provando
que o sistema visual veio antes do primeiro componente. 1006 testes verdes, quatro gates de
lint/tipo limpos.

Não é APROVADO liso por dois motivos de natureza diferente. O primeiro é **bloqueante e mecânico**:
o commit `57f80cb` deixa um check obrigatório vermelho e faz o repositório dizer duas coisas
incompatíveis sobre a mesma decisão — a DESC-1 afirma que a skill não foi commitada, e ela está
commitada. Isso se resolve com um `revert`, não com uma discussão. O segundo é **de evidência**:
três das métricas que a própria spec escolheu ainda não têm número, porque medi-las exige o
navegador que esta rodada não abriu.

### Condições de fechamento

1. **(bloqueante)** Reverter `57f80cb` — vendorização da `ui-ux-pro-max` e `skills-lock.json` da
   raiz —, restaurando `.claude/commands/fechar-spec.md`. Confirmar com
   `bash scripts/vendor-skills.sh --check` limpo.
2. Rodar o `S-07-roteiro-de-demo.md` com as duas abas abertas e anexar ao PR: screenshot da
   jornada, o atraso evento→tela cronometrado, e o comportamento com a API derrubada.
3. `frontend/tsconfig.tsbuildinfo` para o `.gitignore`.
4. Atualizar o `status` do frontmatter da spec no fechamento.

Cumprida a condição 1, esta branch está pronta para PR. As condições 2 a 4 são evidência e higiene,
e cabem no mesmo PR.
