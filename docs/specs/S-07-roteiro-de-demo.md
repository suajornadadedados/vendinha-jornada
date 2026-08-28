# Roteiro da demonstração — duas abas

> Este é o roteiro que a S-07 existe para tornar possível, e é também a **verificação
> manual** da spec. Ele não é uma apresentação de slides: é o produto rodando, e cada
> passo tem um resultado que se confere na tela.

## Antes de começar

```bash
make up && make db-setup && make seed     # infra + catálogo
make api                                  # terminal 1 — http://127.0.0.1:8000
make web                                  # terminal 2 — http://localhost:5173
```

No `.env`: `ANTHROPIC_API_KEY` (ou `OPENAI_API_KEY`), `OPENAI_API_KEY` para o seed, e
`OPERADOR_API_TOKEN` — sem este último o painel **fecha inteiro**, que é o comportamento
correto e não um problema de setup.

Duas abas, lado a lado:

| Aba | Onde | Quem é |
|---|---|---|
| Esquerda | `http://localhost:5173/` | o comprador corporativo |
| Direita | `http://localhost:5173/admin` | o operador da Vendinha |

---

## 1. O painel vazio é honesto

Conecte com o `OPERADOR_API_TOKEN`. A visão geral abre **sem nenhum número inventado**:
"viraram pedido", "valor médio do pedido" e o tempo de resposta aparecem como **traço**, não
como zero — passe o mouse e o `title` diz por quê ("nenhum atendimento neste período").

> É a primeira coisa a mostrar, e a mais fácil de perder de vista: um painel que exibisse
> `0%` de conversão num dia sem conversa estaria afirmando algo falso sobre um dia que não
> aconteceu.

No canto superior direito, **ao vivo**. É o stream do barramento, não polling — deixe a
aba Network aberta se quiser: em dois minutos parados ela não faz uma requisição.

## 2. O cliente chega

Na aba da esquerda, clique no botão verde do canto inferior direito e escreva:

> *café da manhã para 40 pessoas, até R$35 por pessoa*

**Olhe para a aba da direita.** A conversa aparece na lista em menos de um segundo, e a
pergunta do cliente aparece **antes** de o agente responder.

## 3. A regra de ouro, na tela

No widget, a composição aparece **enquanto é montada**: item, quantidade, preço unitário,
subtotal, total e valor por pessoa. Nada disso é calculado no navegador — é o
`ComposicaoValidada` como o validador o devolveu.

Agora force a recusa. Peça um **happy hour para 30 pessoas com no máximo R$20 por pessoa**.
O código recusa, e a tela mostra **o motivo tipado** — orçamento, item obrigatório,
restrição —, não "não foi possível".

Na aba do operador, em **Visão geral** (`/admin`), o gráfico *"Sugestões barradas na
conferência"* ganhou barras. Cada uma é uma vez em que o modelo propôs e o código não deixou
passar.

Em **Conversas** (`/admin/conversas`), clique na linha — a URL vira
`/admin/conversas/<id>`, e é um link que se manda para alguém. À direita, a conversa inteira
em português: o que o cliente escreveu, o que o agente pediu ao sistema, o que o sistema
respondeu, e o que a conferência decidiu — com o custo de cada resposta. **Nenhum JSON e
nenhum nome de variável na tela**, que é a regra de vocabulário do `sistema-visual.md`.

## 4. Fechar o pedido

Volte ao cliente e feche a composição aprovada: informe os dados da empresa quando o
agente pedir. Quando o pedido é criado, o widget mostra o **cartão de pagamento com o
link**, e o painel muda o status da conversa para *aguardando pagamento*.

Abra o link e confirme o pagamento na página de mock.

## 5. O momento do HITL

**O sino do painel toca.** Aparece um aviso com a razão social e o valor, e o contador da
seção *Aprovações* sobe.

Abra a fila. O detalhe traz o destinatário PJ completo — razão social, CNPJ, inscrição
estadual, contato e endereço de entrega — e a composição **item a item**, exatamente como a
nota vai ler.

Clique em **Aprovar e emitir**. A confirmação **repete o que está em jogo**: razão social,
CNPJ e total. Um "tem certeza?" sem o dado seria um clique a mais, não uma defesa.

Confirme.

## 6. A nota chega sozinha ao cliente

**Não toque na aba da esquerda.** O cartão *"Nota fiscal emitida nº N"* aparece no chat,
com DANFE e XML, sem o cliente ter perguntado nada.

> É o passo que fecha uma dívida nomeada: o RF-3.6 diz que o cliente **recebe** a
> confirmação, e até a S-06 ele precisava perguntar (ressalva R-2 da verificação da S-05).

Abra os dois documentos. A DANFE sai com a tarja **SEM VALOR FISCAL** — é um mock fiel, e a
demo diz isso em vez de fingir o contrário.

## 7. Uma rejeição, para ver o outro lado

Faça um segundo pedido e, na fila, escolha **Rejeitar**. O botão de motivo é obrigatório —
e é obrigatório porque o servidor exige, não porque a tela inventou a regra.

O motivo chega ao cliente no chat. Em **Métricas**, a taxa de aprovação deixa de ser traço.

## 8. Derrube o backend

Com as duas abas abertas, mate o processo da API (`Ctrl+C` no terminal 1).

- O painel troca **ao vivo** por **desconectado — dados de HH:MM** e **esmaece o conteúdo**.
- O widget mostra **sem conexão** no cabeçalho.
- Nenhum número antigo continua sendo apresentado como atual.

Suba a API de novo. As duas telas reconectam sozinhas, sem F5.

> É o passo que a verificação independente da spec exige nominalmente, e o mais fácil de
> reprovar: uma reconexão silenciosa deixaria a tela exibindo o último estado conhecido como
> se fosse o presente.

## 9. Onde o dinheiro aparece

Em **Métricas** (`/admin/metricas`): custo de IA do período, quanto ele representa do que
foi vendido, uso por modelo, e o tempo até a resposta começar a aparecer contra a meta de 3s.
Na tela a meta se chama **meta** — o nome do requisito interno (RNF-4) fica na spec, que é
onde ele significa alguma coisa.

Repare no que **não** aparece: "custo de IA sobre o vendido" fica em traço, porque não há
cotação do dólar configurada em `data/precos-modelos.json` — comparar dólar com real por uma
taxa inventada seria pior do que não comparar. E um modelo sem preço cadastrado nunca custa
R$ 0,00; custa traço, com o motivo no `title`.

## 10. O que não se edita

Em **Configurações** (`/admin/configuracoes`), o modelo é trocável por um dropdown (fora de
`APP_ENV=local` a tela avisa que é somente leitura). As **instruções do agente são exibidas e
não editáveis**, uma de cada vez por um seletor, com sha e caminho do arquivo.

> Não é falta de tempo: prompt editável em runtime contornaria o portão de evals do
> ADR-014, e o campo `editavel` é o literal `false` no contrato — um botão de salvar prompt
> nem chega a compilar (ADR-015).

---

## O que conferir no fim

| | |
|---|---|
| A jornada inteira aconteceu sem recarregar a página? | |
| Alguma requisição de polling na aba Network com o painel parado? | deve ser 0 |
| Algum total, custo ou KPI somado no navegador? | deve ser 0 — confira o diff |
| Algum valor ausente exibido como zero? | deve ser 0 |
| O atraso entre o evento e a tela passou de 1s? | não deve |
