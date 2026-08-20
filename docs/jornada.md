# Jornada do cliente — onde a IA entra e por quê

Regra de ouro: **o LLM decide o que dizer; o código decide o que pode ser feito.**

| Etapa | Natureza | Quem resolve | Por quê |
|---|---|---|---|
| Chegada / boas-vindas | Conversacional | LLM | Tom, acolhimento, contexto |
| Entender a necessidade ("presente pra sogra que ama vinho") | Linguagem natural, necessidade implícita | **LLM — o valor está aqui** | Nenhum filtro de e-commerce resolve isso |
| Recomendar produtos | Semântica + fatos | LLM **ancorado em RAG** | Conversa é do modelo; atributos/preços são do catálogo |
| Informar preço / calcular total | Fato de negócio | **Código/banco — nunca o modelo** | Erro destrói confiança |
| Coletar dados (nome, CPF, e-mail) | Estruturado + sensível | LLM coleta, **código valida** | Validação nunca é do modelo |
| Gerar link de pagamento | Side effect financeiro | Tool determinística com permissão | Idempotência, auditoria |
| Confirmar pagamento | Evento externo | Webhook + código | Zero IA |
| Emitir NF | Side effect **irreversível** | Tool + **HITL obrigatório** | Custo do erro alto |
| Pós-venda / status | Consulta | LLM lê via tool read-only | Conveniência sem risco |

Lição: IA não é uma camada sobre o fluxo — é um componente **posicionado** onde linguagem
natural gera valor, cercado de código determinístico onde o cliente precisa de garantia.
