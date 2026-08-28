// O estado da conversa do cliente — e o que ele sabe de cada momento.
//
// **Duas fontes, e cada uma responde uma pergunta diferente.**
//
//   `POST /chat` (SSE)              o que o atendente está dizendo, token a token
//   `GET /eventos/sessao/{id}` (SSE) o que o SERVIDOR fez: veredito da composição,
//                                    status do pedido, decisão da nota
//
// A segunda é o que fecha a ressalva R-2 da verificação da S-05: o RF-3.6 diz que o
// cliente **recebe** a confirmação da nota, e até a S-07 ele precisava perguntar. Com
// essa assinatura, aprovar no painel faz o cartão da NF aparecer aqui sozinho.
//
// O evento `mensagem` é ignorado de propósito: ele existe para o painel, e aqui
// duplicaria o que os tokens já trouxeram.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { BASE_URL } from "../api/client";
import type { ComposicaoAvaliada, NotaDecidida, PedidoAtualizado } from "../api/eventos";
import { lerEventoDoChat, lerEventoDoPainel } from "../api/eventos";
import type { EstadoDaConexao } from "../api/sse";
import { assinar, lerStream } from "../api/sse";
import type { components } from "../api/schema";

export type Veredito = components["schemas"]["ComposicaoValidada"];

export interface Fala {
  readonly de: "cliente" | "atendente";
  readonly texto: string;
  /** Verdadeiro enquanto os tokens ainda estão chegando nesta fala. */
  readonly escrevendo?: boolean;
}

export interface EstadoDoPedido {
  readonly pedidoId: string;
  readonly status: string;
  readonly total: string;
  readonly razaoSocial: string;
  /** `null` enquanto o gateway ainda não devolveu o link. */
  readonly urlPagamento: string | null;
}

export interface EstadoDaNota {
  readonly decisao: "aprovada" | "rejeitada";
  readonly numero: number | null;
  readonly motivo: string | null;
  readonly danfe: string;
  readonly xml: string;
}

const CHAVE_DA_SESSAO = "vendinha:conversa";

function sessaoGuardada(): string | null {
  try {
    return localStorage.getItem(CHAVE_DA_SESSAO);
  } catch {
    return null;
  }
}

function guardarSessao(id: string): void {
  try {
    localStorage.setItem(CHAVE_DA_SESSAO, id);
  } catch {
    /* sem armazenamento: a conversa vale só para esta aba */
  }
}

export function useConversa() {
  const [sessionId, setSessionId] = useState<string | null>(() => sessaoGuardada());
  const [falas, setFalas] = useState<Fala[]>([]);
  const [esperando, setEsperando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [veredito, setVeredito] = useState<Veredito | null>(null);
  const [pedido, setPedido] = useState<EstadoDoPedido | null>(null);
  const [nota, setNota] = useState<EstadoDaNota | null>(null);
  const [conexao, setConexao] = useState<EstadoDaConexao>("desconectado");

  // Guardado em ref porque o `enviar` precisa do id da sessão que o servidor acabou
  // de anunciar no MESMO stream — antes de qualquer re-render acontecer.
  const sessaoAtual = useRef<string | null>(sessionId);
  sessaoAtual.current = sessionId;

  // A assinatura dos eventos do servidor. Só existe depois que há sessão: antes
  // disso não há o que ouvir, e assinar `/eventos/sessao/null` seria um stream
  // permanentemente vazio piscando "reconectando".
  useEffect(() => {
    if (!sessionId) return;
    return assinar(`${BASE_URL}/eventos/sessao/${encodeURIComponent(sessionId)}`, {
      aoMudarEstado: setConexao,
      aoReceber: (bruto) => {
        const evento = lerEventoDoPainel(bruto);
        if (!evento) return;

        if (evento.tipo === "composicao_avaliada") {
          setVeredito((evento as ComposicaoAvaliada).veredito);
          return;
        }
        if (evento.tipo === "pedido_atualizado") {
          const atualizado = evento as PedidoAtualizado;
          setPedido({
            pedidoId: atualizado.pedido_id,
            status: atualizado.status,
            total: String(atualizado.total),
            razaoSocial: atualizado.razao_social,
            urlPagamento: atualizado.url_pagamento ?? null,
          });
          return;
        }
        if (evento.tipo === "nota_decidida") {
          const decidida = evento as NotaDecidida;
          setNota({
            decisao: decidida.decisao,
            numero: decidida.numero_nota ?? null,
            motivo: decidida.motivo ?? null,
            danfe: `${BASE_URL}/pedidos/${decidida.pedido_id}/nota.pdf`,
            xml: `${BASE_URL}/pedidos/${decidida.pedido_id}/nota.xml`,
          });
        }
        // `mensagem`, `sessao_iniciada` e `atraso` não mudam nada aqui: a conversa
        // desta aba vem dos tokens, e o resto é assunto do painel.
      },
    });
  }, [sessionId]);

  const enviar = useCallback(async (texto: string) => {
    const limpo = texto.trim();
    if (!limpo) return;

    setErro(null);
    setEsperando(true);
    setFalas((atuais) => [...atuais, { de: "cliente", texto: limpo }]);

    let respostaAberta = false;
    try {
      const corpo: Record<string, unknown> = { message: limpo };
      if (sessaoAtual.current) corpo["session_id"] = sessaoAtual.current;

      for await (const bruto of lerStream(`${BASE_URL}/chat`, {
        metodo: "POST",
        corpo,
      })) {
        const evento = lerEventoDoChat(bruto);
        if (!evento) continue;

        if (evento.evento === "session") {
          const id = String(evento.corpo["session_id"] ?? "");
          if (id && id !== sessaoAtual.current) {
            sessaoAtual.current = id;
            guardarSessao(id);
            setSessionId(id);
          }
          continue;
        }

        if (evento.evento === "token") {
          const pedaco = String(evento.corpo["text"] ?? "");
          if (!pedaco) continue;
          setEsperando(false);
          setFalas((atuais) => {
            if (!respostaAberta) {
              respostaAberta = true;
              return [...atuais, { de: "atendente", texto: pedaco, escrevendo: true }];
            }
            const anteriores = atuais.slice(0, -1);
            const ultima = atuais[atuais.length - 1];
            if (!ultima) return atuais;
            return [...anteriores, { ...ultima, texto: ultima.texto + pedaco }];
          });
          continue;
        }

        if (evento.evento === "error") {
          // O servidor manda uma frase deliberadamente vaga; ela é a que o cliente
          // deve ler. Inventar uma nossa aqui seria contradizer o backend sobre o
          // que aconteceu.
          setErro(String(evento.corpo["detail"] ?? "não consegui responder agora."));
        }
      }
    } catch {
      // Falha ANTES do primeiro byte: a API está fora do ar, e a frase precisa
      // dizer isso — e não repetir o "tente de novo" de um erro do modelo.
      setErro("não consegui falar com a loja agora. verifique a conexão e tente de novo.");
    } finally {
      setEsperando(false);
      // Fecha a última fala do atendente: sem isto o cursor de digitação ficaria
      // piscando para sempre no fim de uma resposta que já terminou.
      setFalas((atuais) => {
        const ultima = atuais[atuais.length - 1];
        if (!ultima || ultima.de !== "atendente" || !ultima.escrevendo) return atuais;
        return [...atuais.slice(0, -1), { ...ultima, escrevendo: false }];
      });
    }
  }, []);

  /** O estado honesto do atendimento, para a tela não ter que deduzi-lo. */
  const etapa = useMemo(() => {
    if (nota?.decisao === "aprovada") return "nota-emitida" as const;
    if (nota?.decisao === "rejeitada") return "nota-rejeitada" as const;
    if (pedido?.status === "aguardando_aprovacao_nf") return "aguardando-nf" as const;
    if (pedido?.status === "aguardando_pagamento") return "aguardando-pagamento" as const;
    return "conversando" as const;
  }, [nota, pedido]);

  return {
    sessionId,
    falas,
    esperando,
    erro,
    veredito,
    pedido,
    nota,
    conexao,
    etapa,
    enviar,
  };
}
