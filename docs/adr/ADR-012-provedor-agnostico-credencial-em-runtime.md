# ADR-012 — Provedor de LLM agnóstico, com credencial configurável em runtime

- Status: aceito · Data: 2026-08-26 · Decisão: D15 · Riscos: R5, R6
- Não substitui nenhum ADR. Estende o **ADR-001** (o LLM fala, o código executa) para a
  escolha de *qual* LLM fala, e herda do **ADR-007/010** a exigência de que nada sensível
  saia deste processo em claro.

## Contexto
O `.env.example` nascido na S-00 fixava um fornecedor: `ANTHROPIC_API_KEY` e
`ANTHROPIC_MODEL=claude-opus-5`. Trocar de provedor era editar código e variável de
ambiente, e a escolha do modelo era decisão de quem faz deploy — não de quem opera.

O PO definiu outra coisa na abertura da S-02: **quem usa o sistema coloca a própria chave
e escolhe o modelo pela interface**, e o produto precisa funcionar com Anthropic, OpenAI ou
outro provedor sem reescrita. São duas perguntas que parecem uma:

1. como o código deixa de conhecer o fornecedor?
2. onde mora a credencial, se ela deixa de ser variável de ambiente?

## Alternativas consideradas

1. **Fornecedor fixo no `.env` (status quo).** Zero superfície nova e zero código. Em
   troca, trocar de provedor exige redeploy, e o estudo de caso público fica amarrado a um
   fornecedor — exatamente o contrário do que o ADR-010 elogia na escolha do Langfuse
   ("a decisão de hospedagem é reversível; a de fornecedor não seria").
2. **Agnóstico, mas só por variável de ambiente.** `LLM_MODEL=anthropic:claude-haiku-4-5`
   resolve a pergunta 1 e não mexe em segurança. Falha na pergunta 2: quem opera a
   vendinha não necessariamente tem acesso ao `.env` do servidor, e não há história de UI.
3. **Agnóstico, com credencial cifrada no banco, editável em runtime pela API.** Resolve as
   duas. Cria uma classe nova de segredo dentro do processo — e é isso que precisa ser
   pago com invariante, não com boa intenção.
4. **Credencial vinda do browser a cada requisição, sem persistência.** Nada para vazar em
   repouso. Em compensação o segredo viaja em toda chamada, passa por todo log de acesso e
   por todo handler de erro, e a superfície fica *maior*, não menor.

## Decisão
Opção 3, com quatro invariantes que o código precisa provar.

**A porta já existe: é o `BaseChatModel`.** O modelo é resolvido por
`init_chat_model("<provedor>:<modelo>")` do LangChain. Não escrevemos adapter próprio —
adicionar um terceiro provedor passa a ser uma linha de dependência, não uma refatoração.
Isso também é o que torna o R6 mensurável de forma agnóstica: a contagem de tokens sai do
`usage_metadata`, que o LangChain normaliza entre fornecedores. Sem isso, o budget cap teria
uma conta por provedor — e três contas é o mesmo que nenhuma.

1. **O modelo que o cliente manda é escolha dentro de uma allowlist do servidor, nunca
   string livre.** `GET /models` devolve o que está disponível, derivado de quais
   credenciais existem; `POST /chat` valida contra essa lista. String livre no campo
   `model` é o cliente decidindo para qual fornecedor o servidor autentica e quanto gasta —
   e a régua da S-06 mede o comportamento de um modelo declarado, não de um escolhido pelo
   cliente. É a regra de ouro aplicada à configuração: o LLM decide o que dizer, o código
   decide o que pode ser feito — inclusive *qual* LLM.
2. **A credencial nunca volta pela API.** A leitura da configuração devolve
   `configured: true` e uma dica mascarada (`sk-…4f2a`). Não existe rota que devolva o valor.
3. **A credencial nunca entra em trace nem em log.** É o mesmo caminho de redação que o
   ADR-007 exige para PII, e por isso ela ganha caso dentro de
   `tests/security/test_pii_redaction.py` em vez de arquivo novo: o seam é o mesmo — o que
   sai deste processo — e inventar camada nova onde a existente serve é o que o
   `docs/testes.md` §3 item 6 manda registrar como descoberta, não improvisar.
4. **Cifrada em repouso, e dito com precisão.** Chave simétrica vinda do `.env`. Isso
   protege contra **dump do banco**; não protege contra quem já tem o `.env`. Escrever
   "criptografado" sem essa segunda frase seria vender garantia que não existe.

O `.env` continua valendo como *bootstrap*: chave presente no ambiente aparece na allowlist
sem nenhuma configuração pela UI. O que está no banco vence o que está no ambiente.

Escopo do que se persiste: **uma linha de configuração da instância**, não credencial por
usuário. Não existe modelo de usuário nem autenticação na S-02, e escrever a decisão como
se fosse multi-tenant seria prometer o que nenhuma spec entrega. Multi-tenancy, se vier,
é decisão nova e ADR novo.

## Consequências
+ Trocar de fornecedor deixa de ser reescrita e passa a ser seleção — o mesmo argumento que
  o ADR-010 usou para manter o Langfuse como fornecedor.
+ O budget cap (R6) nasce agnóstico, porque a unidade medida é token e não preço de tabela.
+ Quem clona o projeto não precisa ter conta na Anthropic: qualquer chave de qualquer
  provedor suportado faz o quickstart da RNF-1 funcionar.
− **Uma classe nova de segredo dentro do processo.** Antes só havia PII vindo do cliente;
  agora há credencial de terceiro em memória e em banco. As invariantes 2, 3 e 4 são o preço,
  e nenhuma delas é opcional.
− A tabela de preço por modelo continua não existindo neste repositório, então "budget" é
  teto de tokens e o custo em R$ vive no dashboard do Langfuse. É menos intuitivo que USD, e
  é o que se pode afirmar sem manter uma tabela que desatualiza em silêncio.
− `GET /models`, `GET /config` e `PUT /config` são superfície de API que os REQ-1 a REQ-5 da
  S-02 não previam: a spec ganha o REQ-6 por causa desta decisão.
