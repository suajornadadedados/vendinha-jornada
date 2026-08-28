# Sistema visual da Vendinha

> Produzido na S-07 pela skill `ui-ux-pro-max` **antes** do primeiro componente, como o
> harness manda (`.claude/skills/vendinha-harness/SKILL.md`): *decidir, então implementar.
> Inverter produz componente bonito sem sistema.*
>
> Este documento é o insumo dos commits 12 a 17 da S-07 e a régua da verificação
> independente: ele existe para que o revisor julgue **consistência**, e não gosto.

## O problema de desenho

Um produto, **dois registros**, e eles não podem ser o mesmo desenho nem duas marcas
diferentes:

| | Landing pública | Painel do operador |
|---|---|---|
| Quem lê | comprador corporativo decidindo se confia | operador decidindo emitir nota fiscal |
| O que precisa | respiro, prova, uma ação clara | densidade, estado atual, nenhuma ambiguidade |
| Tempo na tela | 40 segundos | a manhã inteira |
| Erro caro | não converter | aprovar a nota errada |

A resolução é **uma paleta e uma tipografia, duas escalas de espaço**. A marca é a mesma;
o que muda é a densidade e a temperatura.

## O que a consulta devolveu, e o que fizemos com ele

| Eixo | Recomendação da skill | Decisão |
|---|---|---|
| Pattern | *Trust & Authority + Conversion* — hero de credibilidade, prova, visão da solução, CTA | **Adotado** na estrutura da landing |
| Style | *Accessible & Ethical* — contraste 4.5:1, navegação por teclado, foco visível, reduced-motion, alvo 44×44 | **Adotado como requisito**, não como sugestão |
| Paleta | navy `#0F172A` + azul `#0369A1` ("Professional navy + blue CTA") | **Recusada.** É o SaaS genérico que o PO descartou nominalmente. Mantida a paleta terrosa dos diagramas do repo — mas submetida à régua de contraste do style acima, que reprovou um tom (abaixo) |
| Tipografia | *SaaS Mobile Boutique*: **Calistoga** + **Inter** + **JetBrains Mono** — "warm, editorial, human warmth", B2B SaaS e dashboards | **Adotada integralmente.** É exatamente o problema dos dois registros: a serifa quente serve o empório, a Inter serve a tabela densa, e a mono serve dinheiro e id |
| Ícones | **Phosphor** | **Adotado, e um set só** |
| Gráfico: KPI contra alvo | *Bullet chart* (Performance vs Target, compacto; grid de bullets para 3+ KPIs) | **Adotado** para o p95 do primeiro token contra os 3s do RNF-4 |
| Gráfico: série temporal | *Line chart*; nunca distinguir série só por matiz | **Adotado** para custo ao longo do tempo |
| Gráfico: categórico | a busca devolveu radar/scatter — **não é o caso**. A própria ficha nomeia *grouped bar* como a alternativa quando a comparação precisa ser precisa | **Barra horizontal ordenada** para recusas por motivo. Registrado que aqui a escolha foi nossa, e não um match do banco |
| Estado de conexão perdida | **nenhum match no banco** (duas tentativas) | Regra escrita por nós, abaixo, e marcada como tal |

## Paleta

Uma paleta, e **cada tom com um trabalho declarado**. Contraste medido contra `#FAF8F5`.

| Token | Hex | Contraste | Para quê |
|---|---|---|---|
| `--tinta` | `#1A1714` | 16.84 | texto principal, títulos |
| `--tinta-suave` | `#5F5850` | 6.61 | texto secundário, rótulos |
| `--papel` | `#FAF8F5` | — | fundo da landing |
| `--cartao` | `#FFFFFF` | — | superfície elevada, linhas de tabela |
| `--linha` | `#E3DCD2` | 1.28 | **só borda e divisória.** Nunca texto |
| `--verde` | `#1F6F5C` | 5.68 | aprovado, sucesso, CTA |
| `--ocre` | `#8A5714` | 5.74 | **pendente, atenção — em texto e ícone** |
| `--ocre-fundo` | `#B4711F` | 3.72 | **só preenchimento** — barra de gráfico, tarja |
| `--vermelho` | `#A03A3A` | 6.27 | recusado, rejeitado, erro |

> **O ocre foi dividido em dois, e essa é a única mudança na paleta de partida.** O
> `#B4711F` dos diagramas do repositório mede **3.72** sobre papel e **3.95** com branco por
> cima — reprova em texto nos dois sentidos, e "pendente" é justamente o estado que aparece
> como texto num badge, na tela onde alguém decide emitir documento fiscal. `#8A5714` mede
> 5.74 e 6.08, e continua sendo ocre. O tom original fica vivo onde 3:1 basta: preenchimento
> de gráfico e tarja.

**Estado nunca se distingue só por matiz.** Aprovado, pendente e rejeitado carregam sempre
**cor + ícone Phosphor + palavra**. É requisito de acessibilidade e é também requisito de
demo: a tela vai ser projetada.

## Tipografia

```
Calistoga        títulos e números de destaque      display
Inter            corpo, UI, tabelas                 400 / 500 / 600
JetBrains Mono   dinheiro, id, token, latência      400 / 500
```

**Dinheiro e id nunca em fonte proporcional.** `R$ 1.920,00` e `R$ 1.020,00` precisam alinhar
na coluna, e um `session_id` precisa ser conferível caractere a caractere. É a mesma razão
pela qual o backend devolve `Decimal` como string.

### Escala — os dois registros

| Papel | Landing | Painel |
|---|---|---|
| Display | 44–56px / 1.05 | 28px / 1.15 |
| Título de seção | 30px / 1.2 | 18px / 1.3 |
| Corpo | 18px / 1.65 | 14px / 1.5 |
| Rótulo | 13px / 1.4, mono, maiúscula, tracking 0.08em | igual |
| Número de destaque | — | 26px Calistoga |

### Espaço

A skill oferece o dial de densidade; usamos os dois extremos dele.

| | Landing (respiro) | Painel (denso) |
|---|---|---|
| escala | 8 / 16 / 24 / 40 / 64 / 96 | 4 / 8 / 12 / 16 / 24 / 32 |
| altura de linha de tabela | — | 40px |
| raio | 12px | 8px |

## Regras de interação

### Fila de aprovação — a tela onde o erro é irreversível

Match do banco: *Confirmation Dialogs — confirm before delete/irreversible actions*, severidade
**alta**; e *Confirmation Messages — brief success message, don't: silent success*.

1. **Aprovar e rejeitar pedem confirmação**, e a confirmação **repete o que está em jogo**:
   razão social, CNPJ e total. Um "tem certeza?" sem o dado é um clique a mais, não uma
   defesa.
2. **Rejeitar exige motivo**, e o campo é obrigatório na UI porque é obrigatório no servidor
   (`fiscal.Aprovacao`). A UI não inventa a regra; ela a antecipa.
3. **Nada de sucesso silencioso**: a decisão volta com o número da nota emitida ou o motivo
   registrado.
4. Os dois botões **não são espelhados**. Aprovar é sólido verde; rejeitar é contorno
   vermelho. Peso visual igual em ações de consequência desigual é como se clica errado.

### Streaming de texto

Match do banco: *Loading Indicators — o feedback deve corresponder à espera esperada, sem
piscar em trabalho quase instantâneo; preserve foco e `aria-busy`.*

- Enquanto não chega o primeiro token: **três pontos**, com `aria-busy` no contêiner da
  conversa. Não é spinner de página: a página está inteira.
- Chegado o primeiro token, o indicador **some** — ele mede a espera, não a digitação.
- O painel recebe a fala do atendente **inteira**, no fim do turno. Streaming em dez
  conversas ao mesmo tempo é ruído que nenhuma decisão usa.

### Conexão perdida

> **Sem match no banco.** Duas consultas, nenhuma devolveu regra sobre estado de rede ou dado
> velho. As três regras abaixo são nossas, e estão aqui declaradas como tal — porque a
> verificação independente da S-07 manda derrubar o backend com as telas abertas e julgar a
> honestidade delas.

1. **Um indicador de conexão persistente** na topbar do painel e no cabeçalho do widget:
   conectado / reconectando / desconectado.
2. **Desconectado esmaece o conteúdo e carimba a hora da última atualização.** Número velho
   apresentado como atual é a falha que a spec reprova; número velho **rotulado como velho**
   é informação.
3. **O evento `atraso` é visível.** Quando o servidor avisa que este assinante perdeu
   eventos, a tela diz que perdeu e oferece recarregar — em vez de aplicar a próxima
   atualização por cima de um estado furado.

### Tabelas densas

Match do banco: *Table Handling — `overflow-x-auto`, nunca tabela larga estourando o
layout.*

- Toda tabela vive num `overflow-x-auto`; a página nunca rola na horizontal.
- Cabeçalho fixo (`position: sticky`) — numa fila de 30 pedidos, rolar e perder a coluna é o
  que faz aprovar a linha errada.
- Números alinhados à direita, em mono, com casas fixas.
- Linha inteira clicável, **e** um alvo de 44×44 para a ação — o requisito de toque vale no
  desktop porque a demo pode ser num laptop com trackpad.

## Gráficos

| KPI | Forma | Por quê |
|---|---|---|
| p95 do primeiro token vs. 3s (RNF-4) | **Bullet chart** | Match do banco para *Performance vs Target*, versão compacta, recomendada para grid de dashboard. O alvo é uma marca no eixo, não uma cor de fundo |
| Recusas do validador por motivo | **Barra horizontal ordenada** | Comparação categórica precisa. Escolha nossa — ver a tabela acima |
| Custo por dia | **Linha** | Match do banco para *Trend Over Time*. Menos de 4 pontos vira cartão de número, não gráfico |
| Conversão, ticket, custo por conversa | **Cartão de número** | Um valor não é um gráfico |

Regras que valem para os três, do banco: **nunca distinguir por cor apenas**; o número e o
alvo aparecem em texto ao lado da forma; foco de teclado revela o mesmo que o hover.

E uma nossa, que vem do ADR-015: **um valor ausente não é zero.** Custo sem preço cadastrado,
p95 sem amostra e conversão sem conversa são **traço**, com a razão no `title`. Um gráfico que
desenha zero onde não há medida mente com mais autoridade do que uma tabela.

## Ícones

**Phosphor, weight `regular`, 20px na UI e 16px em linha de tabela.** Um set só — misturar
famílias é a coisa mais visível e mais barata de errar.

Ícone decorativo ao lado de texto visível recebe `aria-hidden="true"`; ícone que carrega
significado sozinho recebe alternativa textual; ícone dentro de controle interativo exige
nome acessível no controle.

| Estado | Ícone | Cor |
|---|---|---|
| Aprovado / emitida | `CheckCircle` | `--verde` |
| Pendente / aguardando | `Clock` | `--ocre` |
| Rejeitado / erro | `XCircle` | `--vermelho` |
| Atenção, dado incompleto | `Warning` | `--ocre` |
| Desconectado | `WifiSlash` | `--vermelho` |

## Checklist de entrega (da skill, e vale para as duas entradas)

- [ ] Nenhum emoji como ícone — SVG do Phosphor
- [ ] `cursor: pointer` em tudo que é clicável
- [ ] Transições de 150–300ms; nenhuma mudança de estado em 0ms
- [ ] Contraste de texto ≥ 4.5:1 (a tabela acima é a prova, e o ocre já custou uma correção)
- [ ] Foco visível em navegação por teclado — anel de 3px, nunca removido
- [ ] `prefers-reduced-motion` respeitado
- [ ] Responsivo em 375 / 768 / 1024 / 1440
- [ ] Nenhum estado distinguível só por matiz
