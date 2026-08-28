// As telas do painel. Uma por seção, e todas leitura — exceto a fila, que é a
// única que decide (ADR-015).

import { useState } from "react";
import {
  ArrowSquareOut,
  ChatCircleText,
  CheckCircle,
  FilePdf,
  FileXls,
  Lock,
  XCircle,
} from "@phosphor-icons/react";
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

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

/** O operador é uma declaração, não uma identidade provada — e a tela diz isso. */
const OPERADOR = "operador do painel";

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

export function VisaoGeral({ janela, irPara }: { janela: string; irPara: (t: string) => void }) {
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
            <button className="sublinhado" onClick={() => irPara("fila")}>
              Abrir a fila
            </button>
          </AlertDescription>
        </Alert>
      )}

      <div className="kpis">
        <Kpi titulo="Conversas" valor={inteiro(m.conversas)} nota={`${inteiro(m.turnos)} turnos`} />
        <Kpi
          titulo="Conversão"
          valor={m.taxa_de_conversao === null ? null : porcento(m.taxa_de_conversao)}
          nota={`${inteiro(m.conversas_com_pedido)} viraram pedido`}
          porque="nenhuma conversa nesta janela"
        />
        <Kpi
          titulo="Ticket médio"
          valor={m.ticket_medio === null ? null : reais(m.ticket_medio)}
          nota={`${inteiro(m.pedidos)} pedidos · ${reais(m.receita)}`}
          porque="nenhum pedido nesta janela"
        />
        <Kpi
          titulo="Custo de LLM"
          valorNo={<Custo custo={m.custo} />}
          nota={
            m.custo_sobre_ticket === null
              ? "sem cotação do dólar configurada"
              : `${porcento(m.custo_sobre_ticket)} da receita`
          }
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Desempenho</CardTitle>
            <CardDescription>A régua do RNF-4 e o tempo de atendimento.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <Bullet
              valor={m.primeiro_token_p95_ms}
              alvo={m.primeiro_token_alvo_ms}
              rotulo="p95 do primeiro token"
            />
            <Separator />
            <dl className="linhas">
              <div>
                <dt>p50 do primeiro token</dt>
                <dd className="num">{milissegundos(m.primeiro_token_p50_ms)}</dd>
              </div>
              <div>
                <dt>Atendimento médio</dt>
                <dd className="num">{milissegundos(m.atendimento_medio_ms)}</dd>
              </div>
              <div>
                <dt>Turnos por conversa</dt>
                <dd className="num">
                  {m.turnos_por_conversa === null ? (
                    <Ausente porque="nenhuma conversa nesta janela" />
                  ) : (
                    Number(m.turnos_por_conversa).toFixed(1).replace(".", ",")
                  )}
                </dd>
              </div>
              <div>
                <dt>Erros de stream</dt>
                <dd className="num">{inteiro(m.erros_de_stream)}</dd>
              </div>
            </dl>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>O que o código recusou</CardTitle>
            <CardDescription>
              Cada barra é uma composição que o modelo propôs e o validador não deixou passar.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <BarrasOrdenadas
              rotulo="Recusas por motivo"
              vazio="nenhuma recusa nesta janela"
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
          <CardTitle>Conversas recentes</CardTitle>
          <CardDescription>Atualiza por evento — sem recarregar a página.</CardDescription>
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
                  <button onClick={() => irPara("conversas")}>
                    <ChatCircleText size={16} weight="regular" aria-hidden="true" />
                    <span className="mono">{conversa.session_id.slice(0, 8)}</span>
                    <span className="conversas-curtas__meta">
                      {inteiro(conversa.turnos)} turnos · {hora(conversa.ultima_atividade)}
                    </span>
                    <Estado status={conversa.status_do_pedido} />
                  </button>
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
  const [aberta, setAberta] = useState<string | null>(null);
  const conversas = useConversas();

  if (conversas.isLoading) return <Carregando linhas={5} />;
  const lista = conversas.data?.conversas ?? [];

  if (lista.length === 0) {
    return (
      <Empty>
        <EmptyHeader>
          <EmptyTitle>Nenhuma conversa</EmptyTitle>
          <EmptyDescription>
            Nada foi atendido ainda. Abra a landing em outra aba para começar uma.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
      <Card>
        <CardHeader>
          <CardTitle>Conversas</CardTitle>
          <CardDescription>{inteiro(lista.length)} no total</CardDescription>
        </CardHeader>
        <CardContent className="tabela-rolante">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Sessão</TableHead>
                <TableHead className="num">Turnos</TableHead>
                <TableHead className="num">Custo</TableHead>
                <TableHead>Pedido</TableHead>
                <TableHead>Atividade</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {lista.map((conversa) => (
                <TableRow
                  key={conversa.session_id}
                  onClick={() => setAberta(conversa.session_id)}
                  data-selecionada={conversa.session_id === aberta ? "" : undefined}
                  className="cursor-pointer"
                >
                  <TableCell className="mono">{conversa.session_id.slice(0, 10)}</TableCell>
                  <TableCell className="num">{inteiro(conversa.turnos)}</TableCell>
                  <TableCell className="num">
                    <Custo custo={conversa.custo} />
                  </TableCell>
                  <TableCell>
                    <Estado status={conversa.status_do_pedido} />
                  </TableCell>
                  <TableCell className="mono">{quando(conversa.ultima_atividade)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Rastreabilidade sessionId={aberta} />
    </div>
  );
}

// ---------------------------------------------------------- rastreabilidade

export function Rastreabilidade({ sessionId }: { sessionId: string | null }) {
  const detalhe = useConversa(sessionId);

  if (!sessionId) {
    return (
      <Card>
        <CardContent className="p-6">
          <Empty>
            <EmptyHeader>
              <EmptyTitle>Escolha uma conversa</EmptyTitle>
              <EmptyDescription>
                Aqui aparece o que o modelo propôs ao lado do que o código validou ou recusou.
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
        <CardTitle className="mono text-base">{d.resumo.session_id}</CardTitle>
        <CardDescription>
          canal {d.resumo.canal} · iniciada {quando(d.resumo.iniciada_em)}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {d.mensagens_indisponiveis && (
          <Alert>
            <AlertTitle>Não consegui ler esta conversa</AlertTitle>
            <AlertDescription>
              O checkpointer não respondeu. Isto não é uma conversa vazia — é uma leitura que
              falhou.
            </AlertDescription>
          </Alert>
        )}

        <section>
          <p className="rotulo mb-2">A conversa</p>
          <ol className="linha-do-tempo">
            {d.mensagens.map((mensagem, indice) => (
              <li key={indice} className={`linha-do-tempo--${mensagem.papel}`}>
                {mensagem.ferramenta ? (
                  <>
                    <span className="linha-do-tempo__tag mono">
                      {mensagem.argumentos ? "propôs" : "código respondeu"} ·{" "}
                      {mensagem.ferramenta}
                    </span>
                    <pre className="linha-do-tempo__json">
                      {mensagem.argumentos ?? mensagem.texto}
                    </pre>
                  </>
                ) : (
                  <>
                    <span className="linha-do-tempo__tag mono">
                      {mensagem.papel === "cliente" ? "cliente" : "atendente"}
                    </span>
                    <p>{mensagem.texto}</p>
                  </>
                )}
              </li>
            ))}
          </ol>
        </section>

        {d.vereditos.length > 0 && (
          <section>
            <p className="rotulo mb-2">O que o código decidiu</p>
            <ul className="vereditos">
              {d.vereditos.map((veredito, indice) => (
                <li key={indice}>
                  <span className={`estado ${veredito.aprovada ? "estado--ok" : "estado--recusa"}`}>
                    {veredito.aprovada ? (
                      <CheckCircle size={14} weight="regular" aria-hidden="true" />
                    ) : (
                      <XCircle size={14} weight="regular" aria-hidden="true" />
                    )}
                    {veredito.aprovada ? "Aprovada" : "Recusada"}
                  </span>
                  <span className="num">{reais(veredito.total)}</span>
                  <span className="num">{reais(veredito.valor_por_pessoa)}/pessoa</span>
                  <span className="vereditos__motivos">
                    {veredito.motivos.map((motivo) => (
                      <Badge key={motivo} variant="outline">
                        {NOME_DO_MOTIVO[motivo] ?? motivo}
                      </Badge>
                    ))}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}

        <section>
          <p className="rotulo mb-2">O que cada turno custou</p>
          <div className="tabela-rolante">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Modelo</TableHead>
                  <TableHead className="num">Entrada</TableHead>
                  <TableHead className="num">Saída</TableHead>
                  <TableHead className="num">1º token</TableHead>
                  <TableHead className="num">Custo</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {d.turnos.map((turno, indice) => (
                  <TableRow key={indice}>
                    <TableCell className="mono">{turno.modelo}</TableCell>
                    <TableCell className="num">
                      {turno.tokens_entrada === null ? (
                        <Ausente porque="o provedor não informou o consumo" />
                      ) : (
                        inteiro(turno.tokens_entrada)
                      )}
                    </TableCell>
                    <TableCell className="num">
                      {turno.tokens_saida === null ? (
                        <Ausente porque="o provedor não informou o consumo" />
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
          <EmptyTitle>Nada esperando</EmptyTitle>
          <EmptyDescription>
            Nenhuma nota fiscal aguarda decisão. Quando uma entrar, o sino toca aqui.
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
                  <dt>Criado</dt>
                  <dd className="mono">{quando(pedido.criado_em)}</dd>
                </div>
              </dl>

              {pedido.composicoes.map((composicao, indice) => (
                <div key={indice} className="tabela-rolante">
                  <p className="rotulo mb-1">
                    {composicao.tipo_de_evento} · {composicao.pessoas} pessoas ·{" "}
                    {reais(composicao.valor_por_pessoa)}/pessoa
                  </p>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Item</TableHead>
                        <TableHead className="num">Qtd</TableHead>
                        <TableHead className="num">Unit.</TableHead>
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
          <EmptyDescription>Nada foi fechado ainda nesta instância.</EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Pedidos</CardTitle>
        <CardDescription>{inteiro(lista.length)} no total</CardDescription>
      </CardHeader>
      <CardContent className="tabela-rolante">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Empresa</TableHead>
              <TableHead>CNPJ</TableHead>
              <TableHead className="num">Total</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Nota</TableHead>
              <TableHead>Criado</TableHead>
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

export function Metricas({ janela }: { janela: string }) {
  const metricas = useMetricas(janela);
  if (metricas.isLoading) return <Carregando linhas={4} />;
  const m = metricas.data;
  if (!m) return null;

  return (
    <div className="flex flex-col gap-4">
      <div className="kpis">
        <Kpi titulo="Conversas" valor={inteiro(m.conversas)} />
        <Kpi
          titulo="Conversão"
          valor={m.taxa_de_conversao === null ? null : porcento(m.taxa_de_conversao)}
          porque="nenhuma conversa nesta janela"
        />
        <Kpi titulo="Receita" valor={reais(m.receita)} nota={`${inteiro(m.pedidos)} pedidos`} />
        <Kpi
          titulo="Ticket médio"
          valor={m.ticket_medio === null ? null : reais(m.ticket_medio)}
          porque="nenhum pedido nesta janela"
        />
        <Kpi titulo="Custo de LLM" valorNo={<Custo custo={m.custo} />} />
        <Kpi
          titulo="Custo / receita"
          valor={m.custo_sobre_ticket === null ? null : porcento(m.custo_sobre_ticket)}
          porque="sem cotação do dólar configurada em data/precos-modelos.json"
        />
        <Kpi titulo="Fila agora" valor={inteiro(m.fila_pendentes)} nota="notas aguardando" />
        <Kpi
          titulo="Taxa de aprovação"
          valor={m.taxa_de_aprovacao === null ? null : porcento(m.taxa_de_aprovacao)}
          nota={`${inteiro(m.aprovadas)} de ${inteiro(m.decisoes)} decisões`}
          porque="nenhuma decisão nesta janela"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Latência</CardTitle>
          </CardHeader>
          <CardContent>
            <Bullet
              valor={m.primeiro_token_p95_ms}
              alvo={m.primeiro_token_alvo_ms}
              rotulo="p95 do primeiro token"
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Consumo por modelo</CardTitle>
          </CardHeader>
          <CardContent className="tabela-rolante">
            {m.uso.length === 0 ? (
              <p className="grafico__vazio">nenhum turno nesta janela</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Modelo</TableHead>
                    <TableHead className="num">Turnos</TableHead>
                    <TableHead className="num">Entrada</TableHead>
                    <TableHead className="num">Saída</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {m.uso.map((uso) => (
                    <TableRow key={uso.modelo}>
                      <TableCell className="mono">{uso.modelo}</TableCell>
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

      <Card>
        <CardHeader>
          <CardTitle>O que o código recusou</CardTitle>
        </CardHeader>
        <CardContent>
          <BarrasOrdenadas
            rotulo="Recusas por motivo"
            vazio="nenhuma recusa nesta janela"
            dados={m.recusas_do_validador.map((r) => ({
              chave: NOME_DO_MOTIVO[r.motivo] ?? r.motivo,
              valor: r.recusas,
            }))}
          />
        </CardContent>
      </Card>
    </div>
  );
}

// ------------------------------------------------------------ configurações

export function Config() {
  const config = useConfig();
  const modelos = useModelos();
  const prompts = usePrompts();
  const [gravando, setGravando] = useState(false);

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
          <CardTitle>Modelo</CardTitle>
          <CardDescription>
            A lista vem do provedor, não daqui — texto livre deixaria o cliente escolher para
            qual fornecedor o servidor autentica.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {config.data && !config.data.editable && (
            <Alert>
              <AlertTitle>Somente leitura neste ambiente</AlertTitle>
              <AlertDescription>
                Gravar configuração só é aceito em <span className="mono">APP_ENV=local</span>{" "}
                enquanto não existir autenticação — esta rota guarda credencial de provedor.
              </AlertDescription>
            </Alert>
          )}
          <ul className="modelos">
            {(modelos.data?.models ?? []).map((modelo) => (
              <li key={modelo}>
                <button
                  className="modelos__item"
                  disabled={!config.data?.editable || gravando}
                  data-atual={modelo === config.data?.selected_model ? "" : undefined}
                  onClick={() => void trocarModelo(modelo)}
                >
                  <span className="mono">{modelo}</span>
                  {modelo === config.data?.selected_model && (
                    <Badge variant="secondary">em uso</Badge>
                  )}
                </button>
              </li>
            ))}
          </ul>
          <div className="provedores">
            {(config.data?.providers ?? []).map((provedor) => (
              <span key={provedor.provider} className="provedores__item">
                <span className="mono">{provedor.provider}</span>
                <Badge variant={provedor.configured ? "secondary" : "outline"}>
                  {provedor.configured ? `via ${provedor.source} …${provedor.hint}` : "sem chave"}
                </Badge>
              </span>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Lock size={18} weight="regular" aria-hidden="true" />
            Prompts do agente
          </CardTitle>
          <CardDescription>
            Somente leitura, em todo ambiente. Prompt muda por PR com evals — editá-lo aqui
            contornaria o portão que existe justamente para pegar regressão de prompt
            (ADR-015).
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {prompts.data?.tabela_de_precos_atualizada_em && (
            <p className="kpi__nota">
              Tabela de preços dos modelos atualizada em{" "}
              <span className="mono">{prompts.data.tabela_de_precos_atualizada_em}</span>.
            </p>
          )}
          {(prompts.data?.prompts ?? []).map((prompt) => (
            <details key={prompt.subagent} className="prompt">
              <summary>
                <span className="prompt__nome">{prompt.subagent}</span>
                <span className="mono prompt__sha">{prompt.sha}</span>
                <span className="mono prompt__arquivo">
                  {prompt.arquivo}
                  <ArrowSquareOut size={12} weight="regular" aria-hidden="true" />
                </span>
              </summary>
              <pre className="prompt__texto">{prompt.texto}</pre>
            </details>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
