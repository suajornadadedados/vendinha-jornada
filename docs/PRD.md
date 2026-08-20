# PRD — Vendinha: Atendimento de Vendas End-to-End com IA

| Campo | Valor |
|---|---|
| Status | Aprovado para desenvolvimento |
| Versão | 1.0 |
| Autor / PO | Caio Oliveira |
| Última atualização | 2026-08-03 |
| Artefatos relacionados | `docs/requisitos.md` · `docs/jornada.md` · `docs/riscos.md` · `docs/decisoes.md` · `docs/adr/` · `docs/arquitetura.md` · `docs/specs/` |

> **Nota de contexto:** a Vendinha é um produto de demonstração construído para um workshop público sobre decisões de engenharia em projetos com IA. Este PRD é escrito como o de um produto real — porque o método é o produto. O roteiro do workshop vive em `docs/workshop/` e não se mistura com este documento.

---

## 1. Contexto e problema

Pequenos produtores e empórios de produtos artesanais mineiros (queijos, cafés, doces, cachaças) vendem produtos que **exigem conversa**: harmonização, maturação, intensidade, ocasião, presente para terceiros. O e-commerce tradicional resolve isso com filtros e categorias — e falha: o cliente que quer "um presente pra minha sogra que ama vinho tinto" não sabe traduzir isso em filtros, abandona o carrinho ou compra errado.

Ao mesmo tempo, a operação de venda tem etapas onde erro é inaceitável: preço informado, cobrança, emissão de nota fiscal. Colocar um modelo de linguagem nessas etapas sem os devidos cuidados troca um problema de conversão por um problema de confiança (e potencialmente jurídico).

**O problema, em uma frase:** como capturar o valor da conversa em linguagem natural na venda consultiva, sem jamais comprometer as garantias determinísticas que o cliente e a operação exigem nas etapas de dinheiro e documento fiscal.

> **Origem dos requisitos.** O enunciado deste projeto entrega um pedido de cliente em prosa — o que ele quer e o que ele teme — sem stack, arquitetura ou numeração. Os requisitos deste PRD são a **nossa tradução** desse pedido: o recorte, a redação e o rigor de cada linha são decisão deste projeto. A tradução completa, com o que foi recusado em cada ponto, está em `docs/requisitos.md`.

## 2. Objetivos e métricas de sucesso

### Objetivos de produto

| ID | Objetivo | Métrica | Alvo (MVP) |
|---|---|---|---|
| O1 | Atendimento consultivo que entende necessidade implícita | Casos golden aprovados (recomendação aderente à necessidade descrita) | 100% do golden dataset |
| O2 | Zero fato inventado sobre produto | Atributo, preço ou disponibilidade inexistente citado pelo agente | 0 ocorrências (uma reprova a suíte e trava o release) |
| O3 | Checkout completo sem fricção | Conversa → link de pagamento válido em fluxo contínuo | 100% dos cenários golden de checkout |
| O4 | Emissão de NF segura | NFs emitidas sem aprovação humana registrada | 0 (invariante, testada) |
| O5 | Operável em produção | Trace completo por sessão no Langfuse, com custo e scores | 100% das sessões |

### Guardrail metrics (não podem piorar para os objetivos valerem)

- Custo por sessão de atendimento ≤ teto configurado (budget cap); p95 de latência do primeiro token ≤ 3s.
- Nenhum dado pessoal (CPF, e-mail) legível em traces ou logs.
- Suite adversarial (prompt injection): 100% de resistência — nenhuma ação fora da allowlist executada.

## 3. Não-objetivos (fora de escopo deste release)

- Emissão de NF com **validade fiscal real** (apenas mock fiel + ambiente de homologação SEFAZ opcional). *Motivo: risco e fricção de certificado/CNPJ para um produto de demonstração.*
- Pagamento com dinheiro real (apenas sandbox). 
- Autenticação de clientes finais, contas, histórico entre sessões.
- Gestão de estoque, frete, logística, trocas e devoluções.
- Multi-tenancy (múltiplas lojas) e painel administrativo completo.
- Apps mobile e multi-idioma.

Cada item acima está documentado como evolução sugerida no README.

## 4. Personas

**Cliente da Vendinha** — quer resolver uma necessidade (presente, harmonização, ocasião) conversando, como faria no balcão de um empório. Não conhece os produtos pelo nome. Precisa confiar no preço mostrado e receber a nota.

**Operador da loja** — responsável fiscal pela operação. Precisa revisar os dados de cada nota antes da emissão, com fila clara do que está pendente e informação suficiente para aprovar ou rejeitar em segundos.

**Dev da comunidade (persona de distribuição)** — clona o repositório, roda localmente em ≤ 10 minutos com tudo mockado, estuda as decisões de engenharia e adapta o padrão ao próprio domínio.

## 5. Jornada e posicionamento da IA

A jornada completa e a classificação de cada etapa (LLM / LLM ancorado / código puro) estão em `docs/jornada.md` e são **requisito normativo** deste PRD. Resumo da regra que governa o produto:

> O LLM decide o que dizer. O código decide o que pode ser feito.

Consequências diretas: preço e total nunca são gerados pelo modelo (sempre lidos do banco via tool); side effects só existem como tools tipadas com permissão explícita; a emissão de NF exige aprovação humana registrada.

## 6. Requisitos funcionais

### RF-1 Conversação e recomendação
- RF-1.1 O cliente conversa via chat com streaming de resposta (SSE).
- RF-1.2 O agente investiga a necessidade antes de recomendar (perguntas de qualificação quando a necessidade é ambígua).
- RF-1.3 Recomendações citam apenas produtos existentes no catálogo, com atributos e preços lidos por tool (RAG sobre Qdrant + consulta de preço no Postgres).
- RF-1.4 O agente oferece alternativas por faixa de preço quando pertinente.
- RF-1.5 O subagent de recomendação possui exclusivamente tools read-only (invariante arquitetural testada).

### RF-2 Checkout e pagamento
- RF-2.1 A transição para checkout ocorre apenas após confirmação explícita do cliente.
- RF-2.2 O agente coleta nome, CPF e e-mail; a validação é feita por schema no código (nunca pelo modelo).
- RF-2.3 O pedido é persistido com itens, quantidades e preços do banco no momento da criação.
- RF-2.4 A tool `gerar_link_pagamento` cria uma preferência no gateway (Mercado Pago, ambiente sandbox) e retorna link funcional no chat.
- RF-2.5 A confirmação de pagamento chega por webhook idempotente com verificação de origem; eventos duplicados não geram efeito duplicado.
- RF-2.6 Desconto não existe como ação disponível a nenhum agente.

### RF-3 Emissão de nota fiscal com aprovação humana
- RF-3.1 Após pagamento confirmado, o pedido entra na fila do operador com status `aguardando_aprovacao_nf` e o grafo pausa (interrupt persistido em checkpointer).
- RF-3.2 A área do operador lista pedidos pendentes com os dados completos da nota.
- RF-3.3 Aprovação e rejeição são registradas (quem, quando) e retomam o grafo.
- RF-3.4 A emissão ocorre via port `NFEmitter` com dois adapters: `MockAdapter` (default; gera XML e DANFE em PDF fiéis ao layout NF-e modelo 55, com tarja "SEM VALOR FISCAL") e `HomologacaoAdapter` (ambiente de homologação SEFAZ via emissor com API; requer certificado digital e CNPJ; opcional).
- RF-3.5 É impossível, por construção, emitir NF sem aprovação registrada (invariante testada em integração).
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
| RNF-7 | Nenhum dado real no repositório: CPFs/e-mails de teste gerados; certificado/CNPJ jamais versionados |
| RNF-8 | Deploy: Docker; VPS com stacks DEV e PROD isoladas; TLS automático; imagens buildadas em CI e publicadas em registry (zero build na VPS) |
| RNF-9 | Segurança mínima de host documentada: firewall, SSH por chave, containers non-root, backup do Postgres |
| RNF-10 | README em PT-BR; código e comentários em inglês |

## 8. Riscos e mitigação

A matriz completa (R1-R9), com mitigação, spec responsável e verificação automatizada, vive em `docs/riscos.md` e é requisito normativo. Riscos de projeto adicionais:

- **Dependência de sandbox de terceiros na demo** → mocks de primeira classe e checkpoints gravados como plano B.
- **Fricção do adapter de homologação (certificado/CNPJ)** → mantido opcional (S-09), nunca no caminho do quickstart.

## 9. Dependências e premissas

- API Anthropic (Claude) disponível com key do usuário; Mercado Pago sandbox; emissor de NF com ambiente de homologação (a definir em spike, registrado em ADR).
- Premissa: uma única loja, um único operador, catálogo estático semeado (~50 produtos).

## 10. Fases de entrega

| Fase | Conteúdo | Specs |
|---|---|---|
| F0 Fundação | Repo protegido, harness, CI, compose | S-00, S-01 |
| F1 Conversa confiável | Agente observável + recomendação ancorada | S-02, S-03 |
| F2 Dinheiro | Fronteira de permissão + pagamento sandbox | S-04 |
| F3 Documento fiscal | HITL + emissão de NF | S-05 |
| F4 Qualidade contínua | Evals como gate | S-06 |
| F5 Produto usável | Frontend integrado | S-07 |
| F6 Produção | Deploy DEV/PROD | S-08 |
| F7 Extra | Homologação real | S-09 (opcional) |

## 11. Questões abertas

| # | Questão | Dono | Prazo |
|---|---|---|---|
| Q1 | Emissor de NF para o adapter de homologação (Focus NFe / NFE.io / eNotas) | Eng | spike antes da S-05 |
| Q2 | Tamanho final do golden dataset (proposta: 12-16 golden + 6-8 adversariais) | PO | antes da S-06 |
| Q3 | Domínio DNS definitivo para DEV/PROD | PO | antes da S-08 |

## 12. Glossário

**HITL** — human-in-the-loop; ponto do fluxo onde uma pessoa aprova antes de o sistema prosseguir. **Interrupt** — primitivo do LangGraph que pausa o grafo com estado persistido. **Groundedness** — grau em que as afirmações do modelo estão ancoradas em fontes verificáveis (aqui: catálogo/banco). **DANFE** — documento auxiliar da NF-e (representação impressa). **Golden dataset** — conjunto versionado de conversas de referência usado nos evals. **Suite adversarial** — conjunto de casos que tentam induzir o agente a agir fora da allowlist.
