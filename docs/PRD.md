# PRD — Vendinha: Atendimento de Vendas End-to-End com IA

| Campo | Valor |
|---|---|
| Status | Aprovado para desenvolvimento |
| Versão | 2.0 — pivô B2B (ADR-013) |
| Autor / PO | Caio Oliveira |
| Última atualização | 2026-08-27 |
| Artefatos relacionados | `docs/requisitos.md` · `docs/jornada.md` · `docs/riscos.md` · `docs/decisoes.md` · `docs/adr/` · `docs/arquitetura.md` · `docs/specs/` |

> **Nota de contexto:** a Vendinha é um produto de demonstração construído para um workshop público sobre decisões de engenharia em projetos com IA. Este PRD é escrito como o de um produto real — porque o método é o produto. O roteiro do workshop vive em `docs/workshop/` e não se mistura com este documento.

---

## 1. Contexto e problema

Empórios de produtos artesanais mineiros (queijos, cafés, doces, cachaças, petiscos) têm no **corporativo** o cliente de maior ticket e maior recorrência: café da manhã de treinamento, happy hour de sexta, cesta de fim de ano para clientes, kit de boas-vindas para quem entra na empresa. E é justamente onde o e-commerce tradicional falha mais feio, porque o pedido não é um produto — é um **problema de composição**: *"preciso de café da manhã para 40 pessoas, R$35 por cabeça, tem uma pessoa celíaca no time, e precisa chegar antes de quinta"*.

Nenhum filtro de categoria responde essa frase. Quem responde é alguém que conhece o catálogo, sabe o que combina, sabe quanto cada item rende e **sabe fazer a conta** — e é essa pessoa que as empresas não têm do outro lado da tela.

Ao mesmo tempo, a operação de venda tem etapas onde erro é inaceitável: preço informado, cobrança, emissão de nota fiscal. No corporativo entram mais duas, e as duas machucam: **estourar o orçamento aprovado** de quem vai prestar contas ao financeiro, e **furar uma restrição alimentar** de alguém que sequer participou da conversa. Colocar um modelo de linguagem nessas etapas sem os devidos cuidados troca um problema de conversão por um problema de confiança (e potencialmente jurídico, ou clínico).

**O problema, em uma frase:** como capturar o valor da conversa em linguagem natural na venda consultiva corporativa, sem jamais comprometer as garantias determinísticas que o cliente e a operação exigem nas etapas de **aritmética**, dinheiro e documento fiscal.

> **Nota de versão.** O case nasceu B2C (pessoa física comprando um presente) e virou B2B na S-10. O motivo, as alternativas recusadas e o custo estão no ADR-013 e em `docs/requisitos.md` §*O case mudou de comprador*. Nenhum ADR de 001 a 012 mudou.

> **Origem dos requisitos.** O enunciado deste projeto entrega um pedido de cliente em prosa — o que ele quer e o que ele teme — sem stack, arquitetura ou numeração. Os requisitos deste PRD são a **nossa tradução** desse pedido: o recorte, a redação e o rigor de cada linha são decisão deste projeto. A tradução completa, com o que foi recusado em cada ponto, está em `docs/requisitos.md`.

## 2. Objetivos e métricas de sucesso

### Objetivos de produto

| ID | Objetivo | Métrica | Alvo (MVP) |
|---|---|---|---|
| O1 | Atendimento consultivo que entende necessidade implícita | Casos golden aprovados (composição aderente ao evento descrito) | 100% do golden dataset |
| O2 | Zero fato inventado sobre produto | Atributo, preço, disponibilidade ou **total** inexistente citado pelo agente | 0 ocorrências (uma reprova a suíte e trava o release) |
| O3 | Checkout completo sem fricção | Conversa → link de pagamento válido em fluxo contínuo | 100% dos cenários golden de checkout |
| O6 | Composição sempre dentro do que foi pedido | Composições apresentadas ao cliente que estouram o orçamento ou violam restrição declarada | 0 (invariante, testada) |
| O4 | Emissão de NF segura | NFs emitidas sem aprovação humana registrada | 0 (invariante, testada) |
| O5 | Operável em produção | Trace completo por sessão no Langfuse, com custo e scores | 100% das sessões |

### Guardrail metrics (não podem piorar para os objetivos valerem)

- Custo por sessão de atendimento ≤ teto configurado (budget cap); p95 de latência do primeiro token ≤ 3s.
- Rodadas de validação até uma composição válida ≤ 3 em conversa típica: o código recusar é o recurso, não o passatempo.
- Nenhum dado pessoal (CPF, e-mail) legível em traces ou logs.
- Suite adversarial (prompt injection): 100% de resistência — nenhuma ação fora da allowlist executada.

## 3. Não-objetivos (fora de escopo deste release)

- Emissão de NF com **validade fiscal real** (apenas mock fiel; não há adapter de homologação SEFAZ, e não haverá). *Motivo: risco e fricção de certificado/CNPJ para um produto de demonstração. A spec opcional que entregaria esse adapter foi descartada em 2026-08-31 — a emenda no ADR-004 registra o que isso custa à R8.*
- Pagamento com dinheiro real (apenas sandbox). 
- Autenticação de clientes finais, contas, histórico entre sessões.
- Gestão de estoque, frete, logística, trocas e devoluções.
- Multi-tenancy (múltiplas lojas). *O painel administrativo completo saiu desta lista em 2026-08-28: o painel de observação do operador é entregável da S-07 (ADR-015). Continua fora o CRUD administrativo — catálogo, pedido e composição não são editáveis pela interface, e prompt é read-only.*
- Preço escalonado por faixa de quantidade. *Motivo: seria legítimo (tabela no banco, não negociação), mas dá a R1 uma segunda forma de estar errado em troca de realismo que a demonstração não precisa (ADR-013).*
- Variante por pessoa dentro de uma mesma composição. *Motivo: "12 cestas, 2 sem álcool" se resolve como duas composições no mesmo pedido, sem entidade nova.*
- Itens não alimentícios no kit de boas-vindas (caneca, camiseta). *Motivo: pedem estoque e personalização, ambos fora de escopo.*
- Boleto, faturamento com prazo e condição de pagamento corporativa. *Motivo: sandbox de gateway, e prazo de pagamento é outro produto.*
- Apps mobile e multi-idioma.

Cada item acima está documentado como evolução sugerida no README.

## 4. Personas

**Compradora corporativa da Vendinha** — gestora de RH, office manager ou assistente de diretoria. Recebeu uma tarefa com número: *tantas pessoas, tanto por pessoa, tal data*. Não conhece os produtos pelo nome e não quer conhecer — quer chegar num pedido defensável diante do financeiro. Presta contas de duas coisas que o agente precisa acertar sozinho: o **orçamento** e as **restrições alimentares** do time. Precisa da nota no CNPJ da empresa.

**Operador da loja** — responsável fiscal pela operação. Precisa revisar os dados de cada nota antes da emissão, com fila clara do que está pendente e informação suficiente para aprovar ou rejeitar em segundos.

**Dev da comunidade (persona de distribuição)** — clona o repositório, roda localmente em ≤ 10 minutos com tudo mockado, estuda as decisões de engenharia e adapta o padrão ao próprio domínio.

## 5. Jornada e posicionamento da IA

A jornada completa e a classificação de cada etapa (LLM / LLM ancorado / código puro) estão em `docs/jornada.md` e são **requisito normativo** deste PRD. Resumo da regra que governa o produto:

> O LLM decide o que dizer. O código decide o que pode ser feito.

Consequências diretas: preço e total nunca são gerados pelo modelo (sempre lidos do banco via tool); side effects só existem como tools tipadas com permissão explícita; a emissão de NF exige aprovação humana registrada.

## 6. Requisitos funcionais

### RF-1 Conversação e recomendação
- RF-1.1 O cliente conversa via chat com streaming de resposta (SSE).
- RF-1.2 O agente investiga a necessidade antes de recomendar: tipo de evento, número de pessoas, orçamento por pessoa, restrições alimentares e prazo. Qualifica o que falta, sem interrogatório.
- RF-1.3 Recomendações citam apenas produtos existentes no catálogo, com atributos e preços lidos por tool (RAG sobre Qdrant + consulta de preço no Postgres).
- RF-1.4 O agente oferece alternativas por faixa de preço quando pertinente.
- RF-1.5 O subagent de recomendação possui exclusivamente tools read-only (invariante arquitetural testada).
- RF-1.6 O agente monta uma **composição** para o evento. O modelo escolhe os produtos; o código calcula o total em `Decimal`, deriva as quantidades a partir do `rendimento` de cada item e exige os slots obrigatórios do tipo de evento (café da manhã sem café é inválido).
- RF-1.7 Composição que estoura o orçamento por pessoa ou inclui item cujo `contem` viola uma restrição declarada **não é apresentada ao cliente como válida**. A validação é de código, nunca julgamento do modelo, e devolve o motivo em termos acionáveis.

### RF-2 Checkout e pagamento
- RF-2.1 A transição para checkout ocorre apenas após confirmação explícita do cliente.
- RF-2.2 O agente coleta os dados da **empresa** — razão social, CNPJ, contato responsável e endereço de entrega; a validação é feita por schema no código (nunca pelo modelo).
- RF-2.3 O pedido é persistido com uma ou mais composições, cada uma com seus itens, quantidades e preços do banco no momento da criação. *"12 cestas, 2 sem álcool"* são duas composições no mesmo pedido.
- RF-2.7 `criar_pedido` **revalida a composição no servidor**. A validação que passou pelo modelo nunca é a que autoriza (R10).
- RF-2.4 A tool `gerar_link_pagamento` cria uma preferência no gateway (Mercado Pago, ambiente sandbox) e retorna link funcional no chat.
- RF-2.5 A confirmação de pagamento chega por webhook idempotente com verificação de origem; eventos duplicados não geram efeito duplicado.
- RF-2.6 Desconto não existe como ação disponível a nenhum agente.

### RF-3 Emissão de nota fiscal com aprovação humana
- RF-3.1 Após pagamento confirmado, o pedido entra na fila do operador com status `aguardando_aprovacao_nf` e o grafo pausa (interrupt persistido em checkpointer).
- RF-3.2 A área do operador lista pedidos pendentes com os dados completos da nota, incluindo destinatário PJ e a composição item a item.
- RF-3.3 Aprovação e rejeição são registradas (quem, quando) e retomam o grafo.
- RF-3.4 A emissão ocorre via port `NFEmitter` com dois adapters: `MockAdapter` (default; gera XML e DANFE em PDF fiéis ao layout NF-e modelo 55, com tarja "SEM VALOR FISCAL") e `HomologacaoAdapter` (ambiente de homologação SEFAZ via emissor com API; requer certificado digital e CNPJ; opcional).
- RF-3.5 É impossível, por construção, emitir NF sem aprovação registrada (invariante testada na camada `security`, `tests/security/test_hitl_invariant.py`).
- RF-3.6 O cliente recebe no chat a confirmação com acesso à DANFE/XML.

### RF-4 Área do operador
- RF-4.1 Fila de pedidos por status, com detalhe do pedido e ações aprovar/rejeitar.
- RF-4.2 Rejeição exige motivo, comunicado ao fluxo do cliente.

### RF-5 Observabilidade e qualidade
- RF-5.1 Toda sessão gera trace completo no Langfuse: roteamento entre subagents, tools chamadas, custo, latência.
- RF-5.2 Dados pessoais são mascarados nos traces (LGPD by design).
- RF-5.3 Os casos de eval (`evals/`) são versionados e carregam seu próprio critério de aprovação; o resultado de cada execução é anexado ao trace correspondente.
- RF-5.4 Evals (golden + adversarial) rodam em todo PR e bloqueiam o merge quando qualquer caso reprova; fato inventado e ação fora da allowlist reprovam a suíte inteira.

## 7. Requisitos não-funcionais

| ID | Requisito |
|---|---|
| RNF-1 | Quickstart local ≤ 10 min: `git clone` + `.env` + `docker compose up`, sem GPU, sem contas externas além da API key do modelo (default: tudo mockado) |
| RNF-2 | Custo do quickstart na ordem de centavos (modelo econômico como default local; roteamento documentado) |
| RNF-3 | Budget cap por sessão e timeout por tool, configuráveis por ambiente |
| RNF-4 | p95 do primeiro token ≤ 3s em conversa típica |
| RNF-5 | Contratos Pydantic em todas as fronteiras (rotas, tools, webhooks); cliente TypeScript gerado do OpenAPI |
| RNF-6 | Estado do grafo carrega identificadores, não payloads (pointer-not-payload); checkpointer em Postgres |
| RNF-7 | Nenhum dado real no repositório: CNPJs/e-mails de teste gerados; razão social e endereço fictícios; certificado e CNPJ reais jamais versionados |
| RNF-8 | Deploy: Docker, num **ambiente único e sem denominação**. Um `compose` de deploy sobe api, frontend, nginx, Postgres e Qdrant; o nginx serve os estáticos e faz proxy da API. Sem TLS, sem DNS, sem registry de imagens e sem CD — o entregável é um ambiente empacotado e reprodutível, não uma URL pública (ADR-008) |
| RNF-9 | Segurança mínima de host documentada: firewall, SSH por chave, containers non-root, backup do Postgres |
| RNF-10 | README em PT-BR; código e comentários em inglês |

## 8. Riscos e mitigação

A matriz completa (R1-R10), com mitigação, spec responsável e verificação automatizada, vive em `docs/riscos.md` e é requisito normativo. Riscos de projeto adicionais:

- **Dependência de sandbox de terceiros na demo** → mocks de primeira classe e checkpoints gravados como plano B.
- **Fricção de certificado/CNPJ para emitir NF de verdade** → não se paga: o `NFEmitter` tem um adapter só, o mock, e a lacuna que isso deixa na R8 está declarada (ADR-004, `docs/testes.md` §2).

## 9. Dependências e premissas

- API Anthropic (Claude) disponível com key do usuário; Mercado Pago sandbox; emissor de NF com ambiente de homologação (a definir em spike, registrado em ADR).
- Premissa: uma única loja, um único operador, catálogo estático semeado (~65 produtos, todos com `rendimento` e `contem` declarados).

## 10. Fases de entrega

As fases seguem a ordem desta tabela, e não a ordem dos ids: **S-10 e S-11 rodam entre a S-03 e a S-04** (a nota na S-10 explica por que renumerar sairia mais caro que um id fora de ordem).

| Fase | Conteúdo | Specs |
|---|---|---|
| F0 Fundação | Repo protegido, harness, CI, compose | S-00, S-01 |
| F1 Conversa confiável | Agente observável + recomendação ancorada | S-02, S-03 |
| F1.5 Pivô B2B | Discovery do comprador corporativo + composição de evento | S-10, S-11 |
| F2 Dinheiro | Fronteira de permissão + pagamento sandbox | S-04 |
| F3 Documento fiscal | HITL + emissão de NF | S-05 |
| F4 Qualidade contínua | Evals como gate | S-06 |
| F5 Produto usável | Frontend integrado | S-07 |
| F6 Deploy | Ambiente empacotado (compose com api, frontend e nginx) | S-08 |

## 11. Questões abertas

| # | Questão | Dono | Prazo |
|---|---|---|---|
| Q2 | Tamanho final do golden dataset (proposta: 12-16 golden + 6-8 adversariais) | PO | antes da S-06 |
| Q4 | Faixas de `rendimento` conferidas contra evento real (quantas pessoas um pacote de café atende de fato) | PO | antes da S-11 |

> **Q1 e Q3 foram encerradas em 2026-08-31, e por perda de objeto — não por resposta.** A Q1
> escolhia o emissor de NF para o adapter de homologação, que deixou de existir (ADR-004). A Q3
> pedia o domínio DNS definitivo para DEV/PROD, e não há mais DEV, PROD nem DNS (ADR-008).

## 12. Glossário

**HITL** — human-in-the-loop; ponto do fluxo onde uma pessoa aprova antes de o sistema prosseguir. **Interrupt** — primitivo do LangGraph que pausa o grafo com estado persistido. **Groundedness** — grau em que as afirmações do modelo estão ancoradas em fontes verificáveis (aqui: catálogo/banco). **DANFE** — documento auxiliar da NF-e (representação impressa). **Golden dataset** — conjunto versionado de conversas de referência usado nos evals. **Suite adversarial** — conjunto de casos que tentam induzir o agente a agir fora da allowlist. **Composição** — conjunto de produtos e quantidades montado para um evento, com total e valor por pessoa calculados em código. **Slot** — item obrigatório de um tipo de evento (café da manhã exige bebida quente). **Rendimento** — quantas pessoas um item atende num evento; é o que converte número de convidados em quantidade. **`contem`** — lista de alérgenos declarada por produto (lactose, glúten, álcool, castanhas), usada como corte, nunca inferida do texto.
