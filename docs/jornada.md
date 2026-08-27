# Jornada do cliente — onde a IA entra e por quê

Regra de ouro: **o LLM decide o que dizer; o código decide o que pode ser feito.**

Quem percorre esta jornada é a **compradora corporativa** (`docs/PRD.md` §4): alguém que recebeu uma tarefa com número — tantas pessoas, tanto por pessoa, tal data — e vai prestar contas do resultado.

| Etapa | Natureza | Quem resolve | Por quê |
|---|---|---|---|
| Chegada / boas-vindas | Conversacional | LLM | Tom, acolhimento, contexto |
| Entender o evento ("café da manhã pra 40, R$35 por cabeça, tem um celíaco") | Linguagem natural, necessidade implícita | **LLM — o valor está aqui** | Nenhum filtro de e-commerce resolve isso |
| Escolher os produtos da composição | Semântica + fatos | LLM **ancorado em RAG** | Conversa e gosto são do modelo; atributos e preços são do catálogo |
| **Validar a composição** (total, slots, restrições, rendimento) | Aritmética e regra de negócio | **Código — nunca o modelo** | É aqui que a proposta do modelo é aceita ou recusada, e a recusa vem com motivo |
| Informar preço / calcular total | Fato de negócio | **Código/banco — nunca o modelo** | Erro destrói confiança |
| Coletar dados da empresa (razão social, CNPJ, endereço) | Estruturado + sensível | LLM coleta, **código valida** | Validação nunca é do modelo |
| Gerar link de pagamento | Side effect financeiro | Tool determinística com permissão | Idempotência, auditoria |
| Confirmar pagamento | Evento externo | Webhook + código | Zero IA |
| Emitir NF | Side effect **irreversível** | Tool + **HITL obrigatório** | Custo do erro alto |
| Pós-venda / status | Consulta | LLM lê via tool read-only | Conveniência sem risco |

## A etapa que dá nome ao projeto

**Validar a composição** é a linha onde a regra de ouro deixa de ser prosa e vira comportamento observável. O modelo propõe uma cesta; o código responde *"R$163, o teto é R$150, e faltou item de bebida quente"*; o modelo ajusta. As duas chamadas ficam no mesmo trace, e é possível **assistir** à fronteira funcionando.

Repare que ela não substitui a etapa anterior. Escolher *quais* produtos combinam com um time jovem numa sexta à tarde continua sendo do modelo — é onde ele é insubstituível. O que o código não delega é a **conta** e o **corte**: quanto dá, quantos atende, e o que não pode entrar. Restrição alimentar em particular nunca é julgamento do modelo, porque a resposta errada machuca alguém (R10).

Lição: IA não é uma camada sobre o fluxo — é um componente **posicionado** onde linguagem
natural gera valor, cercado de código determinístico onde o cliente precisa de garantia.
