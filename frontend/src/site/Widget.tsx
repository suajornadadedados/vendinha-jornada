// O atendimento no canto da tela — o simulador do canal do cliente.
//
// **Estados honestos, cada um com cara própria** (REQ-8). O que a tela nunca faz:
// dizer "processando" quando está esperando um humano decidir, prometer prazo que
// ninguém garantiu, ou continuar mostrando o último estado conhecido depois que a
// conexão caiu. A verificação independente da spec derruba o backend no meio de
// propósito.

import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  ChatCircleDots,
  CheckCircle,
  Clock,
  FilePdf,
  FileXls,
  WhatsappLogo,
  WifiSlash,
  X,
  XCircle,
} from "@phosphor-icons/react";

import { Composicao } from "./Composicao";
import { useConversa } from "./useConversa";

export function Widget() {
  const [aberto, setAberto] = useState(false);
  const conversa = useConversa();
  const fimDaLista = useRef<HTMLDivElement>(null);
  const campo = useRef<HTMLInputElement>(null);
  const [rascunho, setRascunho] = useState("");

  useEffect(() => {
    fimDaLista.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [conversa.falas, conversa.veredito, conversa.etapa]);

  useEffect(() => {
    if (aberto) campo.current?.focus();
  }, [aberto]);

  // Esc fecha, como qualquer diálogo. Sem isto, um teclado fica preso na conversa.
  useEffect(() => {
    if (!aberto) return;
    const aoTeclar = (evento: KeyboardEvent) => {
      if (evento.key === "Escape") setAberto(false);
    };
    window.addEventListener("keydown", aoTeclar);
    return () => window.removeEventListener("keydown", aoTeclar);
  }, [aberto]);

  const enviar = (evento: React.FormEvent) => {
    evento.preventDefault();
    const texto = rascunho;
    setRascunho("");
    void conversa.enviar(texto);
  };

  return (
    <>
      {!aberto && (
        <button className="fab" onClick={() => setAberto(true)} aria-label="Abrir o atendimento">
          <WhatsappLogo size={30} weight="fill" aria-hidden="true" />
          <span className="fab__pulso" aria-hidden="true" />
        </button>
      )}

      {aberto && (
        <div className="janela" role="dialog" aria-label="Atendimento da Vendinha" aria-modal="false">
          <header className="janela__topo">
            <div className="janela__quem">
              <span className="janela__avatar" aria-hidden="true">
                V
              </span>
              <div>
                <p className="janela__nome">Vendinha</p>
                <p className="janela__estado">
                  {conversa.conexao === "desconectado" && conversa.sessionId ? (
                    <>
                      <WifiSlash size={12} weight="regular" aria-hidden="true" /> sem conexão
                    </>
                  ) : (
                    "responde na hora"
                  )}
                </p>
              </div>
            </div>
            <button onClick={() => setAberto(false)} aria-label="Fechar o atendimento">
              <X size={20} weight="regular" aria-hidden="true" />
            </button>
          </header>

          <div className="janela__corpo" aria-busy={conversa.esperando}>
            {conversa.falas.length === 0 && (
              <div className="convite">
                <p>Oi! Conte o evento e eu monto a composição.</p>
                <p className="convite__exemplo">
                  Por exemplo: <em>café da manhã para 40 pessoas, até R$35 por pessoa, sem glúten</em>
                </p>
              </div>
            )}

            {conversa.falas.map((fala, indice) => (
              <p
                key={indice}
                className={`balao balao--${fala.de}${fala.escrevendo ? " balao--escrevendo" : ""}`}
              >
                {fala.texto}
              </p>
            ))}

            {conversa.esperando && (
              <p className="balao balao--atendente digitando" aria-label="Escrevendo a resposta">
                <span />
                <span />
                <span />
              </p>
            )}

            {conversa.veredito && <Composicao veredito={conversa.veredito} />}

            {conversa.etapa === "aguardando-pagamento" && conversa.pedido && (
              <section className="cartao-estado cartao-estado--acao">
                <p className="rotulo">Pedido criado</p>
                <p className="cartao-estado__valor num">
                  {Number(conversa.pedido.total).toLocaleString("pt-BR", {
                    style: "currency",
                    currency: "BRL",
                  })}
                </p>
                <p>{conversa.pedido.razaoSocial}</p>
                {conversa.pedido.urlPagamento ? (
                  <a
                    className="botao-pagar"
                    href={conversa.pedido.urlPagamento}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Pagar agora
                    <ArrowRight size={16} weight="regular" aria-hidden="true" />
                  </a>
                ) : (
                  // Sem link ainda: a tela diz o que está acontecendo em vez de
                  // mostrar um botão que não leva a lugar nenhum.
                  <p className="cartao-estado__nota">Gerando o link de pagamento…</p>
                )}
              </section>
            )}

            {conversa.etapa === "aguardando-nf" && (
              <section className="cartao-estado cartao-estado--espera">
                <p className="cartao-estado__titulo">
                  <Clock size={18} weight="regular" aria-hidden="true" />
                  Pagamento confirmado. A nota fiscal está com a nossa equipe.
                </p>
                {/* Sem prazo: ninguém prometeu um, e inventá-lo aqui seria a tela
                    afirmando algo que o sistema não garante. */}
                <p className="cartao-estado__nota">
                  Uma pessoa confere os dados antes de emitir. Você recebe aqui assim que sair —
                  não precisa perguntar.
                </p>
              </section>
            )}

            {conversa.nota?.decisao === "aprovada" && (
              <section className="cartao-estado cartao-estado--ok">
                <p className="cartao-estado__titulo">
                  <CheckCircle size={18} weight="regular" aria-hidden="true" />
                  Nota fiscal emitida
                  {conversa.nota.numero !== null && (
                    <span className="mono"> nº {conversa.nota.numero}</span>
                  )}
                </p>
                <div className="cartao-estado__links">
                  <a href={conversa.nota.danfe} target="_blank" rel="noreferrer">
                    <FilePdf size={16} weight="regular" aria-hidden="true" /> DANFE
                  </a>
                  <a href={conversa.nota.xml} target="_blank" rel="noreferrer">
                    <FileXls size={16} weight="regular" aria-hidden="true" /> XML
                  </a>
                </div>
              </section>
            )}

            {conversa.nota?.decisao === "rejeitada" && (
              <section className="cartao-estado cartao-estado--recusa">
                <p className="cartao-estado__titulo">
                  <XCircle size={18} weight="regular" aria-hidden="true" />
                  A emissão foi recusada
                </p>
                <p className="cartao-estado__nota">{conversa.nota.motivo}</p>
              </section>
            )}

            {conversa.erro && (
              <p className="erro" role="alert">
                {conversa.erro}
              </p>
            )}

            <div ref={fimDaLista} />
          </div>

          <form className="janela__campo" onSubmit={enviar}>
            <label className="visualmente-oculto" htmlFor="mensagem">
              Sua mensagem
            </label>
            <input
              id="mensagem"
              ref={campo}
              value={rascunho}
              onChange={(evento) => setRascunho(evento.target.value)}
              placeholder="Conte o evento…"
              autoComplete="off"
            />
            <button type="submit" disabled={!rascunho.trim()} aria-label="Enviar">
              <ArrowRight size={20} weight="regular" aria-hidden="true" />
            </button>
          </form>
        </div>
      )}

      {!aberto && conversa.falas.length > 0 && (
        <button className="retomar" onClick={() => setAberto(true)}>
          <ChatCircleDots size={16} weight="regular" aria-hidden="true" /> retomar conversa
        </button>
      )}
    </>
  );
}
