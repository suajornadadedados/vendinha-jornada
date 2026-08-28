// As telas do painel. Uma por seção, e todas leitura — exceto a fila, que é a
// única que decide (ADR-015).

import { useState } from "react";
import {
  ArrowSquareOut,
  CaretRight,
  ChatCircleText,
  CheckCircle,
  FilePdf,
  FileXls,
  Lock,
  Robot,
  ShieldCheck,
  User,
  XCircle,
} from "@phosphor-icons/react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import { useJanela } from "./Admin";
import {
  decidir,
  gravarConfig,
  useConfig,
  useConversa,
  useConversas,
  useFila,
  useMetricas,
  useModelos,
  usePedidos,
  usePrompts,
  type DetalheDaConversa,
  type PedidoNaFila,
} from "./dados";
import { BarrasOrdenadas, Bullet } from "./Graficos";
import {
  Ausente,
  Custo,
  Estado,
  NOME_DO_MOTIVO,
  hora,
  inteiro,
  milissegundos,
  porcento,
  quando,
  reais,
} from "./formato";
import {
  ConteudoDaFerramenta,
  MOTIVO_DO_PROBLEMA,
  TIPO_DE_EVENTO,
  nomeDaFerramenta,
} from "./traducao";

/** O operador é uma declaração, não uma identidade provada — e a tela diz isso. */
const OPERADOR = "operador do painel";

/** O subagente é um nome de código; na tela vale o momento do atendimento que ele cobre. */
const NOME_DA_ETAPA: Record<string, string> = {
  recomendacao: "Montar a sugestão do evento",
  checkout: "Fechar o pedido e o pagamento",
};

function Carregando({ linhas = 3 }: { linhas?: number }) {
  return (
    <div className="flex flex-col gap-2">
      {Array.from({ length: linhas }, (_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  );
}

// ------------------------------------------------------------- visão geral
//
// **Visão geral e Métricas mostravam quase a mesma coisa** — mesma consulta, quatro
// KPIs repetidos, o mesmo bullet de latência e o mesmo gráfico de recusas nas duas.
// Duas telas que dizem o mesmo treinam a pessoa a abrir só uma, e aí a outra some.
//
// O corte, decidido com o PO: **aqui é venda e atendimento; lá é máquina.** Quanto
// se vendeu, quantos atendimentos viraram pedido, quanto dura um atendimento, o que
// a conferência barrou. Token, custo de modelo e latência de primeiro token não
// aparecem nesta tela, e é de propósito: quem abre a visão geral quer saber como foi
// o dia da loja, não quanto o fornecedor de IA cobrou por ele.

export function VisaoGeral() {
  const [janela] = useJanela();
  const metricas = useMetricas(janela);
  const conversas = useConversas();
  const fila = useFila();

  if (metricas.isLoading) return <Carregando linhas={4} />;
  const m = metricas.data;
  if (!m) return null;

  const recentes = (conversas.data?.conversas ?? []).slice(0, 6);
  const pendentes = fila.data?.pendentes ?? [];

  return (
    <div className="flex flex-col gap-4">
      {pendentes.length > 0 && (
        <Alert>
          <AlertTitle>
            {pendentes.length} nota{pendentes.length > 1 ? "s" : ""} esperando decisão
          </AlertTitle>
          <AlertDescription>
            Nenhuma sai sem uma pessoa aprovar.{" "}
            <Link className="sublinhado" to="/aprovacoes">
              Abrir a fila
            </Link>
          </AlertDescription>
        </Alert>
      )}

      <div className="kpis">
        <Kpi
          titulo="Atendimentos"
          valor={inteiro(m.conversas)}
          nota="conversas iniciadas no período"
        />
        <Kpi
          titulo="Viraram pedido"
          valor={m.taxa_de_conversao === null ? null : porcento(m.taxa_de_conversao)}
          nota={`${inteiro(m.conversas_com_pedido)} de ${inteiro(m.conversas)} atendimentos`}
          porque="nenhum atendimento neste período"
        />
        <Kpi titulo="Vendido" valor={reais(m.receita)} nota={`${inteiro(m.pedidos)} pedidos`} />
        <Kpi
          titulo="Valor médio do pedido"
          valor={m.ticket_medio === null ? null : reais(m.ticket_medio)}
          porque="nenhum pedido neste período"
        />
        <Kpi
          titulo="Atendimento completo"
          valor={m.atendimento_medio_ms === null ? null : milissegundos(m.atendimento_medio_ms)}
          nota="em média, do primeiro oi à última mensagem"
          porque="nenhum atendimento com começo e fim neste período"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Como foram os atendimentos</CardTitle>
            <CardDescription>
              O que o agente precisou fazer para chegar no pedido, e o que ainda depende de
              uma pessoa.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="linhas linhas--explicadas">
              <div>
                <dt>
                  Idas e vindas por atendimento
                  <span>quantas vezes o agente respondeu, em média</span>
                </dt>
                <dd className="num">
                  {m.turnos_por_conversa === null ? (
                    <Ausente porque="nenhum atendimento neste período" />
                  ) : (
                    Number(m.turnos_por_conversa).toFixed(1).replace(".", ",")
                  )}
                </dd>
              </div>
              <div>
                <dt>
                  Esperando aprovação agora
                  <span>notas fiscais paradas na fila neste momento</span>
                </dt>
                <dd className="num">{inteiro(m.fila_pendentes)}</dd>
              </div>
              <div>
                <dt>
                  Notas aprovadas
                  <span>
                    {inteiro(m.aprovadas)} de {inteiro(m.decisoes)} decisões do operador
                  </span>
                </dt>
                <dd className="num">
                  {m.taxa_de_aprovacao === null ? (
                    <Ausente porque="ninguém decidiu nada neste período" />
                  ) : (
                    porcento(m.taxa_de_aprovacao)
                  )}
                </dd>
              </div>
            </dl>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Sugestões barradas na conferência</CardTitle>
            <CardDescription>
              O agente monta a sugestão, mas quem soma o total e confere as regras é o sistema —
              e ele devolve a sugestão para refazer quando algo não fecha. Estas foram devolvidas,
              e por quê.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <BarrasOrdenadas
              rotulo="Motivo da devolução"
              vazio="nenhuma sugestão foi barrada neste período"
              dados={m.recusas_do_validador.map((r) => ({
                chave: NOME_DO_MOTIVO[r.motivo] ?? r.motivo,
                valor: r.recusas,
              }))}
            />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Últimos atendimentos</CardTitle>
          <CardDescription>
            Aparecem sozinhos, no instante em que acontecem — ninguém precisa recarregar a
            página.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {recentes.length === 0 ? (
            <Empty>
              <EmptyHeader>
                <EmptyTitle>Nenhuma conversa ainda</EmptyTitle>
                <EmptyDescription>
                  Abra a landing em outra aba e fale com o atendimento — a conversa aparece aqui
                  em menos de um segundo.
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : (
            <ul className="conversas-curtas">
              {recentes.map((conversa) => (
                <li key={conversa.session_id}>
                  <Link to={`/conversas/${conversa.session_id}`}>
                    <ChatCircleText size={16} weight="regular" aria-hidden="true" />
                    <span>Atendimento das {hora(conversa.ultima_atividade)}</span>
                    <span className="conversas-curtas__meta">
                      {inteiro(conversa.turnos)}{" "}
                      {conversa.turnos === 1 ? "resposta" : "respostas"} do agente
                    </span>
                    <Estado status={conversa.status_do_pedido} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Kpi({
  titulo,
  valor,
  valorNo,
  nota,
  porque,
}: {
  titulo: string;
  valor?: string | null;
  valorNo?: React.ReactNode;
  nota?: string;
  porque?: string;
}) {
  return (
    <div className="kpi">
      <p className="rotulo">{titulo}</p>
      <p className="kpi__valor">
        {valorNo ?? (valor === null ? <Ausente porque={porque ?? "sem dados"} /> : valor)}
      </p>
      {nota && <p className="kpi__nota">{nota}</p>}
    </div>
  );
}

// ---------------------------------------------------------------- conversas

export function Conversas() {
  // A conversa aberta é a URL, e não um `useState`: `/admin/conversas/<id>` é um
  // link que se manda para alguém, e o "voltar" do navegador fecha o detalhe.
  const { sessionId = null } = useParams<{ sessionId: string }>();
  const navegar = useNavigate();
  const conversas = useConversas();

  if (conversas.isLoading) return <Carregando linhas={5} />;
  const lista = conversas.data?.conversas ?? [];

  if (lista.length === 0) {
    return (
      <Empty>
        <EmptyHeader>
          <EmptyTitle>Nenhum atendimento ainda</EmptyTitle>
          <EmptyDescription>
            Ninguém foi atendido até agora. Abra a loja em outra aba e converse com o
            atendimento — o que acontecer lá aparece aqui na hora.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.25fr)]">
      <Card>
        <CardHeader>
          <CardTitle>Atendimentos</CardTitle>
          <CardDescription>
            {inteiro(lista.length)} no total — clique para ver tudo o que aconteceu em cada um.
          </CardDescription>
        </CardHeader>
        <CardContent className="tabela-rolante">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Atendimento</TableHead>
                <TableHead className="num">Respostas</TableHead>
                <TableHead className="num">Custo de IA</TableHead>
                <TableHead>Situação</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {lista.map((conversa) => (
                <TableRow
                  key={conversa.session_id}
                  onClick={() => navegar(`/conversas/${conversa.session_id}`)}
                  data-selecionada={conversa.session_id === sessionId ? "" : undefined}
                  className="cursor-pointer"
                >
                  <TableCell>{quando(conversa.ultima_atividade)}</TableCell>
                  <TableCell className="num">{inteiro(conversa.turnos)}</TableCell>
                  <TableCell className="num">
                    <Custo custo={conversa.custo} />
                  </TableCell>
                  <TableCell>
                    <Estado status={conversa.status_do_pedido} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Rastreabilidade sessionId={sessionId} />
    </div>
  );
}

// ---------------------------------------------------------- rastreabilidade

/** Quanto do texto cabe na linha fechada antes de virar reticências. */
const PREVIA = 110;

/**
 * Um acontecimento do atendimento: uma linha fechada, o detalhe atrás de um clique.
 *
 * A versão anterior despejava tudo aberto e a seção virava uma barra de rolagem de
 * 340px onde nada era encontrável. Aqui a leitura padrão é a **sequência** — cliente
 * escreveu, agente consultou o catálogo, a conferência respondeu —, e o detalhe é
 * uma decisão de quem lê, não um imposto sobre quem só quer entender o que houve.
 *
 * `<details>` nativo, e não `useState`: vem com teclado, com `aria-expanded` e com o
 * comportamento que o navegador já sabe fazer. Cinquenta linhas de menos.
 */
function Passo({ mensagem }: { mensagem: DetalheDaConversa["mensagens"][number] }) {
  const proposta = mensagem.argumentos != null;
  const detalhe = mensagem.argumentos ?? mensagem.texto;

  if (mensagem.ferramenta) {
    return (
      <li className="linha-do-tempo--passo">
        <details className="passo">
          <summary>
            <CaretRight className="passo__seta" size={12} weight="bold" aria-hidden="true" />
            {proposta ? (
              <Robot size={14} weight="regular" aria-hidden="true" />
            ) : (
              <ShieldCheck size={14} weight="regular" aria-hidden="true" />
            )}
            <span className="passo__titulo">
              {nomeDaFerramenta(mensagem.ferramenta, proposta)}
            </span>
          </summary>
          <div className="passo__corpo">
            <ConteudoDaFerramenta bruto={detalhe} />
          </div>
        </details>
      </li>
    );
  }

  const cliente = mensagem.papel === "cliente";
  const texto = mensagem.texto.trim();
  // Corta no espaço, não no meio da palavra. A prévia é para ser lida de relance.
  const previa =
    texto.length > PREVIA
      ? `${texto.slice(0, texto.lastIndexOf(" ", PREVIA) || PREVIA)}…`
      : texto;

  return (
    <li className={`linha-do-tempo--${mensagem.papel}`}>
      <details className="passo">
        <summary>
          <CaretRight className="passo__seta" size={12} weight="bold" aria-hidden="true" />
          {cliente ? (
            <User size={14} weight="regular" aria-hidden="true" />
          ) : (
            <Robot size={14} weight="regular" aria-hidden="true" />
          )}
          <span className="passo__titulo">
            {cliente ? "O cliente escreveu" : "O agente respondeu"}
          </span>
          <span className="passo__previa">{previa}</span>
        </summary>
        <div className="passo__corpo">
          <p className="passo__fala">{texto}</p>
        </div>
      </details>
    </li>
  );
}

export function Rastreabilidade({ sessionId }: { sessionId: string | null }) {
  const detalhe = useConversa(sessionId);

  if (!sessionId) {
    return (
      <Card>
        <CardContent className="p-6">
          <Empty>
            <EmptyHeader>
              <EmptyTitle>Escolha um atendimento</EmptyTitle>
              <EmptyDescription>
                Aqui aparece a conversa inteira: o que o cliente pediu, o que o agente sugeriu e
                o que o sistema conferiu antes de deixar passar.
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        </CardContent>
      </Card>
    );
  }

  if (detalhe.isLoading) return <Carregando linhas={6} />;
  const d = detalhe.data;
  if (!d) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Atendimento de {quando(d.resumo.iniciada_em)}</CardTitle>
        <CardDescription>
          Pelo {d.resumo.canal === "web" ? "site" : d.resumo.canal} · leitura da conversa como
          ela aconteceu, na ordem
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        {d.mensagens_indisponiveis && (
          <Alert>
            <AlertTitle>Não consegui recuperar esta conversa</AlertTitle>
            <AlertDescription>
              O histórico não respondeu agora. Isto <strong>não</strong> quer dizer que a
              conversa foi vazia — quer dizer que a leitura falhou. Tente de novo em instantes.
            </AlertDescription>
          </Alert>
        )}

        <section>
          <p className="rotulo rotulo--frase mb-1">Como foi o atendimento</p>
          <p className="secao__nota">
            Uma linha por acontecimento, na ordem. Clique em qualquer uma para ver o detalhe.
          </p>
          <ol className="linha-do-tempo">
            {d.mensagens.map((mensagem, indice) => (
              <Passo key={indice} mensagem={mensagem} />
            ))}
          </ol>
        </section>

        {d.vereditos.length > 0 && (
          <section>
            <p className="rotulo rotulo--frase mb-1">O que a conferência decidiu</p>
            <p className="secao__nota">
              O agente sugere; quem soma o total e aplica as regras é o sistema. Cada linha é uma
              sugestão conferida, com o resultado que valeu.
            </p>
            <ul className="vereditos">
              {d.vereditos.map((veredito, indice) => (
                <li key={indice}>
                  <span className={`estado ${veredito.aprovada ? "estado--ok" : "estado--recusa"}`}>
                    {veredito.aprovada ? (
                      <CheckCircle size={14} weight="regular" aria-hidden="true" />
                    ) : (
                      <XCircle size={14} weight="regular" aria-hidden="true" />
                    )}
                    {veredito.aprovada ? "Liberada" : "Devolvida para refazer"}
                  </span>
                  <span className="num">{reais(veredito.total)} no total</span>
                  <span className="num">{reais(veredito.valor_por_pessoa)} por pessoa</span>
                  <span className="vereditos__motivos">
                    {veredito.motivos.map((motivo) => (
                      <Badge key={motivo} variant="outline">
                        {MOTIVO_DO_PROBLEMA[motivo] ?? NOME_DO_MOTIVO[motivo] ?? motivo}
                      </Badge>
                    ))}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}

        <section>
          <p className="rotulo rotulo--frase mb-1">Quanto a inteligência artificial custou</p>
          <p className="secao__nota">
            Uma linha por resposta do agente. "Leu" e "escreveu" são o tamanho do texto que
            entrou e saiu do modelo — é sobre isso que o fornecedor cobra.
          </p>
          <div className="tabela-rolante">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Modelo usado</TableHead>
                  <TableHead className="num">Leu</TableHead>
                  <TableHead className="num">Escreveu</TableHead>
                  <TableHead className="num">Demorou a começar</TableHead>
                  <TableHead className="num">Custo</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {d.turnos.map((turno, indice) => (
                  <TableRow key={indice}>
                    <TableCell>{turno.modelo}</TableCell>
                    <TableCell className="num">
                      {turno.tokens_entrada === null ? (
                        <Ausente porque="o fornecedor não informou o consumo desta resposta" />
                      ) : (
                        inteiro(turno.tokens_entrada)
                      )}
                    </TableCell>
                    <TableCell className="num">
                      {turno.tokens_saida === null ? (
                        <Ausente porque="o fornecedor não informou o consumo desta resposta" />
                      ) : (
                        inteiro(turno.tokens_saida)
                      )}
                    </TableCell>
                    <TableCell className="num">
                      {milissegundos(turno.primeiro_token_ms)}
                    </TableCell>
                    <TableCell className="num">
                      <Custo custo={turno.custo} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </section>
      </CardContent>
    </Card>
  );
}

// --------------------------------------------------------------- a fila HITL

export function Fila() {
  const fila = useFila();
  const [decidindo, setDecidindo] = useState<{ pedido: PedidoNaFila; qual: "aprovar" | "rejeitar" } | null>(null);

  if (fila.isLoading) return <Carregando linhas={3} />;
  const pendentes = fila.data?.pendentes ?? [];

  if (pendentes.length === 0) {
    return (
      <Empty>
        <EmptyHeader>
          <EmptyTitle>Nada esperando decisão</EmptyTitle>
          <EmptyDescription>
            Nenhuma nota fiscal precisa da sua aprovação agora. Quando um pedido pago chegar
            até aqui, o sino toca e a lista aparece sozinha.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  return (
    <>
      <div className="flex flex-col gap-4">
        {pendentes.map((pedido) => (
          <Card key={pedido.pedido_id}>
            <CardHeader>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <CardTitle>{pedido.destinatario.razao_social}</CardTitle>
                  <CardDescription className="mono">
                    CNPJ {pedido.destinatario.cnpj} · IE {pedido.destinatario.inscricao_estadual}
                  </CardDescription>
                </div>
                <p className="fila__total num">{reais(pedido.total)}</p>
              </div>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <dl className="linhas">
                <div>
                  <dt>Contato</dt>
                  <dd>
                    {pedido.destinatario.contato_nome} · {pedido.destinatario.contato_email}
                  </dd>
                </div>
                <div>
                  <dt>Entrega</dt>
                  <dd>
                    {pedido.destinatario.endereco.logradouro},{" "}
                    {pedido.destinatario.endereco.numero} — {pedido.destinatario.endereco.bairro},{" "}
                    {pedido.destinatario.endereco.cidade}/{pedido.destinatario.endereco.uf}
                  </dd>
                </div>
                <div>
                  <dt>Pedido feito em</dt>
                  <dd className="mono">{quando(pedido.criado_em)}</dd>
                </div>
              </dl>

              {pedido.composicoes.map((composicao, indice) => (
                <div key={indice} className="tabela-rolante">
                  <p className="rotulo rotulo--frase mb-1">
                    {TIPO_DE_EVENTO[composicao.tipo_de_evento] ?? composicao.tipo_de_evento} ·{" "}
                    {composicao.pessoas} pessoas · {reais(composicao.valor_por_pessoa)} por pessoa
                  </p>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Item</TableHead>
                        <TableHead className="num">Quantidade</TableHead>
                        <TableHead className="num">Preço unitário</TableHead>
                        <TableHead className="num">Subtotal</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {composicao.itens.map((item) => (
                        <TableRow key={item.produto_id}>
                          <TableCell>{item.nome}</TableCell>
                          <TableCell className="num">{inteiro(item.quantidade)}</TableCell>
                          <TableCell className="num">{reais(item.preco_unitario)}</TableCell>
                          <TableCell className="num">{reais(item.subtotal)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              ))}

              {/* Os dois botões NÃO são espelhados: peso visual igual em ações de
                  consequência desigual é como se clica errado. */}
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => setDecidindo({ pedido, qual: "aprovar" })}>
                  <CheckCircle data-icon="inline-start" />
                  Aprovar e emitir
                </Button>
                <Button
                  variant="outline"
                  onClick={() => setDecidindo({ pedido, qual: "rejeitar" })}
                >
                  <XCircle data-icon="inline-start" />
                  Rejeitar
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {decidindo && (
        <ConfirmarDecisao
          pedido={decidindo.pedido}
          qual={decidindo.qual}
          aoFechar={() => setDecidindo(null)}
          aoDecidir={() => void fila.refetch()}
        />
      )}
    </>
  );
}

/**
 * A confirmação — e ela **repete o que está em jogo**.
 *
 * Um "tem certeza?" sem o dado é um clique a mais, não uma defesa. Aqui aparecem a
 * razão social, o CNPJ e o total, porque é sobre eles que a pessoa está decidindo, e
 * a emissão não tem volta.
 */
function ConfirmarDecisao({
  pedido,
  qual,
  aoFechar,
  aoDecidir,
}: {
  pedido: PedidoNaFila;
  qual: "aprovar" | "rejeitar";
  aoFechar: () => void;
  aoDecidir: () => void;
}) {
  const [motivo, setMotivo] = useState("");
  const [enviando, setEnviando] = useState(false);
  const rejeitando = qual === "rejeitar";
  // A regra é do servidor (`fiscal.Aprovacao`); a UI só a antecipa, para o operador
  // não descobrir no 422.
  const faltaMotivo = rejeitando && motivo.trim() === "";

  const confirmar = async () => {
    setEnviando(true);
    try {
      const vigente = await decidir(pedido.pedido_id, qual, {
        operador: OPERADOR,
        ...(rejeitando ? { motivo: motivo.trim() } : {}),
      });
      // Nada de sucesso silencioso — e o que volta é a decisão QUE VALEU, que pode
      // não ser a que acabou de ser pedida (a primeira vence).
      toast.success(
        vigente.decisao === "aprovada"
          ? `Nota emitida${vigente.numero_nota ? ` — nº ${vigente.numero_nota}` : ""}`
          : "Rejeição registrada, e o cliente foi avisado",
        { description: vigente.motivo ?? undefined },
      );
      aoDecidir();
      aoFechar();
    } catch (erro) {
      toast.error(erro instanceof Error ? erro.message : "a decisão não foi registrada");
    } finally {
      setEnviando(false);
    }
  };

  return (
    <Dialog open onOpenChange={(aberto) => !aberto && aoFechar()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {rejeitando ? "Rejeitar a emissão?" : "Emitir a nota fiscal?"}
          </DialogTitle>
          <DialogDescription>
            {rejeitando
              ? "O cliente recebe o motivo no chat. A decisão não pode ser desfeita."
              : "A emissão é irreversível. Confira o destinatário antes de confirmar."}
          </DialogDescription>
        </DialogHeader>

        <dl className="confirmacao">
          <div>
            <dt>Razão social</dt>
            <dd>{pedido.destinatario.razao_social}</dd>
          </div>
          <div>
            <dt>CNPJ</dt>
            <dd className="mono">{pedido.destinatario.cnpj}</dd>
          </div>
          <div>
            <dt>Total</dt>
            <dd className="num">{reais(pedido.total)}</dd>
          </div>
        </dl>

        {rejeitando && (
          <div className="flex flex-col gap-1">
            <label htmlFor="motivo" className="rotulo">
              Motivo (obrigatório)
            </label>
            <textarea
              id="motivo"
              className="campo"
              rows={3}
              value={motivo}
              onChange={(evento) => setMotivo(evento.target.value)}
              aria-invalid={faltaMotivo}
              placeholder="O que o cliente precisa saber para corrigir"
            />
            {faltaMotivo && (
              <p className="campo__erro">É o que o cliente recebe no chat — sem ele não dá.</p>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={aoFechar} disabled={enviando}>
            Cancelar
          </Button>
          <Button
            variant={rejeitando ? "destructive" : "default"}
            onClick={() => void confirmar()}
            disabled={enviando || faltaMotivo}
          >
            {rejeitando ? "Rejeitar" : "Aprovar e emitir"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ----------------------------------------------------------------- pedidos

export function Pedidos() {
  const pedidos = usePedidos();
  if (pedidos.isLoading) return <Carregando linhas={5} />;
  const lista = pedidos.data?.pedidos ?? [];

  if (lista.length === 0) {
    return (
      <Empty>
        <EmptyHeader>
          <EmptyTitle>Nenhum pedido</EmptyTitle>
          <EmptyDescription>Nenhuma compra foi fechada até agora.</EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Pedidos</CardTitle>
        <CardDescription>
          {inteiro(lista.length)} no total. Os preços são os que estavam valendo na hora da
          compra — uma mudança de tabela depois disso não mexe num pedido já fechado.
        </CardDescription>
      </CardHeader>
      <CardContent className="tabela-rolante">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Empresa</TableHead>
              <TableHead>CNPJ</TableHead>
              <TableHead className="num">Total</TableHead>
              <TableHead>Situação</TableHead>
              <TableHead>Nota fiscal</TableHead>
              <TableHead>Quando</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {lista.map((pedido) => (
              <TableRow key={pedido.pedido_id}>
                <TableCell>{pedido.razao_social}</TableCell>
                <TableCell className="mono">{pedido.cnpj}</TableCell>
                <TableCell className="num">{reais(pedido.total)}</TableCell>
                <TableCell>
                  <Estado status={pedido.status} />
                </TableCell>
                <TableCell>
                  {pedido.url_danfe ? (
                    <span className="flex gap-2">
                      <a className="link-doc" href={pedido.url_danfe} target="_blank" rel="noreferrer">
                        <FilePdf size={14} weight="regular" aria-hidden="true" /> DANFE
                      </a>
                      <a className="link-doc" href={pedido.url_xml!} target="_blank" rel="noreferrer">
                        <FileXls size={14} weight="regular" aria-hidden="true" /> XML
                      </a>
                    </span>
                  ) : (
                    <Ausente porque="a nota ainda não foi emitida" />
                  )}
                </TableCell>
                <TableCell className="mono">{quando(pedido.criado_em)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------- métricas
//
// A metade técnica do corte descrito na visão geral: **aqui é máquina.** Quanto os
// modelos consumiram, quanto isso custou, quanto texto entrou e saiu de cada um, e
// quanto o cliente espera até a resposta começar a aparecer.
//
// Nenhum KPI de venda aparece aqui — receita, conversão e ticket vivem na visão
// geral, e repeti-los era o que fazia as duas telas dizerem a mesma coisa. A única
// ponte é "custo de IA sobre o vendido", que só existe porque a pergunta dela é
// técnica: o modelo escolhido cabe no preço do produto?

export function Metricas() {
  const [janela] = useJanela();
  const metricas = useMetricas(janela);
  if (metricas.isLoading) return <Carregando linhas={4} />;
  const m = metricas.data;
  if (!m) return null;

  return (
    <div className="flex flex-col gap-4">
      <div className="kpis">
        <Kpi
          titulo="Custo de IA"
          valorNo={<Custo custo={m.custo} />}
          nota="o que os modelos consumiram no período"
        />
        <Kpi
          titulo="Custo de IA sobre o vendido"
          valor={m.custo_sobre_ticket === null ? null : porcento(m.custo_sobre_ticket)}
          nota="quanto de cada real vendido foi para a IA"
          porque="falta a cotação do dólar para converter o custo em reais"
        />
        <Kpi
          titulo="Respostas do agente"
          valor={inteiro(m.turnos)}
          nota={`em ${inteiro(m.conversas)} atendimentos`}
        />
        <Kpi
          titulo="Respostas que travaram"
          valor={inteiro(m.erros_de_stream)}
          nota="a conexão caiu antes de o agente terminar de escrever"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Tempo até a resposta começar</CardTitle>
            <CardDescription>
              Quanto o cliente olha para a tela em branco antes de ver a primeira palavra. Não é
              o atendimento inteiro — esse fica na visão geral.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <Bullet
              valor={m.primeiro_token_p95_ms}
              alvo={m.primeiro_token_alvo_ms}
              rotulo="Nas respostas mais lentas (95 de cada 100)"
              explica="O traço é a meta que o projeto se deu para este número."
              alvoRotulo="meta"
            />
            <Separator />
            <dl className="linhas linhas--explicadas">
              <div>
                <dt>
                  Numa resposta comum
                  <span>metade das respostas começou a aparecer antes disto</span>
                </dt>
                <dd className="num">{milissegundos(m.primeiro_token_p50_ms)}</dd>
              </div>
            </dl>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Uso por modelo de IA</CardTitle>
            <CardDescription>
              Quanto texto cada modelo leu e escreveu no período — é a base do que o fornecedor
              cobra.
            </CardDescription>
          </CardHeader>
          <CardContent className="tabela-rolante">
            {m.uso.length === 0 ? (
              <p className="grafico__vazio">nenhuma resposta do agente neste período</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Modelo</TableHead>
                    <TableHead className="num">Respostas</TableHead>
                    <TableHead className="num">Leu</TableHead>
                    <TableHead className="num">Escreveu</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {m.uso.map((uso) => (
                    <TableRow key={uso.modelo}>
                      <TableCell>{uso.modelo}</TableCell>
                      <TableCell className="num">{inteiro(uso.turnos)}</TableCell>
                      <TableCell className="num">{inteiro(uso.tokens_entrada)}</TableCell>
                      <TableCell className="num">{inteiro(uso.tokens_saida)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

// ------------------------------------------------------------ configurações

export function Config() {
  const config = useConfig();
  const modelos = useModelos();
  const prompts = usePrompts();
  const [gravando, setGravando] = useState(false);
  const [promptAberto, setPromptAberto] = useState<string | null>(null);

  const trocarModelo = async (modelo: string) => {
    setGravando(true);
    try {
      await gravarConfig({ model: modelo });
      toast.success(`Modelo alterado para ${modelo}`);
      void config.refetch();
      void modelos.refetch();
    } catch (erro) {
      toast.error(erro instanceof Error ? erro.message : "não consegui gravar");
    } finally {
      setGravando(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Modelo de IA em uso</CardTitle>
          <CardDescription>
            Qual modelo atende os clientes. A lista vem do próprio fornecedor — digitar o nome à
            mão deixaria escolher um fornecedor para o qual o servidor não tem credencial.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {config.data && !config.data.editable && (
            <Alert>
              <AlertTitle>Somente leitura neste ambiente</AlertTitle>
              <AlertDescription>
                A troca de modelo só é aceita no ambiente local enquanto não existir login — esta
                configuração guarda credencial de fornecedor.
              </AlertDescription>
            </Alert>
          )}

          {/* Dropdown, e não a lista inteira aberta: são doze modelos, e onze deles
              são ruído permanente para quem só quer saber qual está valendo. */}
          <label className="campo-rotulado">
            <span className="rotulo">Modelo</span>
            <Select
              value={config.data?.selected_model ?? undefined}
              disabled={!config.data?.editable || gravando}
              onValueChange={(modelo) => void trocarModelo(modelo)}
            >
              <SelectTrigger className="w-full max-w-md">
                <SelectValue placeholder="escolha o modelo" />
              </SelectTrigger>
              <SelectContent>
                {(modelos.data?.models ?? []).map((modelo) => (
                  <SelectItem key={modelo} value={modelo}>
                    {modelo}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>

          <div>
            <p className="rotulo rotulo--frase mb-1">Fornecedores conectados</p>
            <div className="provedores">
              {(config.data?.providers ?? []).map((provedor) => (
                <span key={provedor.provider} className="provedores__item">
                  {provedor.provider}
                  <Badge variant={provedor.configured ? "secondary" : "outline"}>
                    {/* `hint` já vem com as reticências do `Vault.hint`; repetir aqui
                        produzia "final ......1QAA". */}
                    {provedor.configured ? `chave configurada ${provedor.hint}` : "sem chave"}
                  </Badge>
                </span>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Lock size={18} weight="regular" aria-hidden="true" />
            Instruções do agente
          </CardTitle>
          <CardDescription>
            As instruções que o agente segue no atendimento. Só leitura, em qualquer ambiente:
            mudá-las é mudar como ele fala com o cliente, e isso passa por revisão e pelos testes
            de qualidade antes de entrar no ar — nunca por esta tela.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {prompts.data?.tabela_de_precos_atualizada_em && (
            <p className="kpi__nota">
              Tabela de preços dos modelos atualizada em{" "}
              {prompts.data.tabela_de_precos_atualizada_em}.
            </p>
          )}

          {/* Um seletor no lugar de dois blocos abertos: as instruções são longas, e
              empilhá-las esconde a de baixo mais do que um dropdown esconderia. */}
          <label className="campo-rotulado">
            <span className="rotulo">Ver as instruções de</span>
            <Select value={promptAberto ?? undefined} onValueChange={setPromptAberto}>
              <SelectTrigger className="w-full max-w-md">
                <SelectValue placeholder="escolha uma etapa do atendimento" />
              </SelectTrigger>
              <SelectContent>
                {(prompts.data?.prompts ?? []).map((prompt) => (
                  <SelectItem key={prompt.subagent} value={prompt.subagent}>
                    {NOME_DA_ETAPA[prompt.subagent] ?? prompt.subagent}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>

          {(prompts.data?.prompts ?? [])
            .filter((prompt) => prompt.subagent === promptAberto)
            .map((prompt) => (
              <div key={prompt.subagent} className="prompt">
                <p className="prompt__origem">
                  Vive no arquivo <span className="mono">{prompt.arquivo}</span>, versão{" "}
                  <span className="mono">{prompt.sha}</span>
                  <ArrowSquareOut size={12} weight="regular" aria-hidden="true" />
                </p>
                <pre className="prompt__texto">{prompt.texto}</pre>
              </div>
            ))}
        </CardContent>
      </Card>
    </div>
  );
}
