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
  readonly tipo: "fala";
  readonly de: "cliente" | "atendente";
  readonly texto: string;
  /** Verdadeiro enquanto os tokens ainda estão chegando nesta fala. */
  readonly escrevendo?: boolean;
  /**
   * Qual fala do atendente esta é, dentro do turno — vem do backend.
   *
   * Um turno com tool no meio produz mais de uma: "vou consultar os preços" →
   * tool → "aqui está". São dois balões, e sem este índice o segundo emendava no
   * primeiro, saindo "consultar os preços:Perfeito! Aqui".
   *
   * **Não é único na conversa**: o backend zera o contador a cada turno. Quem
   * procura uma fala por este número procura de trás para frente, e acha a do
   * turno corrente.
   */
  readonly indice?: number;
}

export interface CartaoDaComposicao {
  readonly tipo: "composicao";
  readonly veredito: Veredito;
}

/**
 * A conversa é UMA lista ordenada por chegada — fala do cliente, fala do
 * atendente, composição avaliada.
 *
 * Antes o veredito era um estado à parte (`Veredito | null`) renderizado num slot
 * fixo no fim do corpo da janela. Isso produzia dois defeitos de uma vez, e os
 * dois apareceram na primeira conversa longa de verdade: a tabela ficava presa no
 * rodapé enquanto as falas novas nasciam **acima** dela, e cada veredito
 * sobrescrevia o anterior — um atendimento com três variações (sem restrição, sem
 * glúten, sem lactose) mostrava só a última.
 *
 * Ordem de chegada é a única ordem que existe aqui, e é a mesma do `messages` do
 * backend.
 */
export type ItemDaConversa = Fala | CartaoDaComposicao;

function ehFala(item: ItemDaConversa): item is Fala {
  return item.tipo === "fala";
}

/**
 * Onde continuar escrevendo — de trás para frente, e por isso acha a fala do
 * turno corrente mesmo com `indice` repetindo entre turnos.
 *
 * Procura a fala **aberta** com este índice em vez de olhar só o último item
 * porque um cartão de composição pode ter caído no meio: o veredito chega por
 * outro stream, e nada garante que ele não chegue entre dois pedaços da mesma
 * fala. Sem isto, aquele cartão partia a fala em dois balões.
 */
function falaAberta(itens: readonly ItemDaConversa[], indice: number): number {
  for (let i = itens.length - 1; i >= 0; i -= 1) {
    const item = itens[i];
    if (
      item &&
      ehFala(item) &&
      item.de === "atendente" &&
      item.escrevendo &&
      (item.indice ?? 0) === indice
    ) {
      return i;
    }
  }
  return -1;
}

/** A última fala do atendente com este índice, aberta ou não. */
function ultimaFala(itens: readonly ItemDaConversa[], indice: number): number {
  for (let i = itens.length - 1; i >= 0; i -= 1) {
    const item = itens[i];
    if (item && ehFala(item) && item.de === "atendente" && (item.indice ?? 0) === indice) return i;
  }
  return -1;
}

/** Apaga o cursor de digitação de toda fala ainda aberta. */
function fechar(itens: readonly ItemDaConversa[]): ItemDaConversa[] {
  return itens.map((item) =>
    ehFala(item) && item.escrevendo ? { ...item, escrevendo: false } : item,
  );
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
  const [itens, setItens] = useState<ItemDaConversa[]>([]);
  const [esperando, setEsperando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
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
          // Um cartão por veredito, na posição em que ele aconteceu. O barramento
          // não repete evento — `assinar` é pub/sub ao vivo, sem histórico —, então
          // acrescentar não duplica cartão numa reconexão.
          const avaliada = (evento as ComposicaoAvaliada).veredito;
          setItens((atuais) => [...atuais, { tipo: "composicao", veredito: avaliada }]);
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
    setItens((atuais) => [...atuais, { tipo: "fala", de: "cliente", texto: limpo }]);

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
          // A decisão "abrir fala nova × continuar a de cima" sai do PRÓPRIO estado,
          // e não de uma variável de fora.
          //
          // A versão anterior guardava um `respostaAberta` no escopo do `enviar` e o
          // escrevia de dentro deste updater. Updater do React tem que ser função
          // pura: no StrictMode ele roda DUAS vezes para cada chamada. A primeira
          // abria a fala do atendente e marcava a flag; a segunda via a flag já
          // marcada, caía no ramo de "continuar", e emendava a resposta do agente na
          // última fala de `atuais` — que era a do CLIENTE. Daí "Olá, tudo bem?Opa,
          // tudo certo!" num balão verde só.
          const indice = Number(evento.corpo["fala"] ?? 0);
          setItens((atuais) => {
            const aberta = falaAberta(atuais, indice);
            if (aberta >= 0) {
              const fala = atuais[aberta] as Fala;
              const copia = [...atuais];
              copia[aberta] = { ...fala, texto: fala.texto + pedaco };
              return copia;
            }
            // Fala nova: a anterior para de piscar o cursor no mesmo instante.
            return [
              ...fechar(atuais),
              { tipo: "fala", de: "atendente", texto: pedaco, escrevendo: true, indice },
            ];
          });
          continue;
        }

        if (evento.evento === "preambulo") {
          // O backend acabou de descobrir que esta fala era preâmbulo — texto e
          // chamada de tool na mesma `AIMessage` ("Agora vou consultar os
          // preços…"). O balão sai e vira o indicador de digitando: o cliente
          // continua vendo que algo acontece, sem ler a narração do trabalho.
          //
          // Chega DEPOIS do texto, e não antes, porque no streaming a chamada de
          // tool só se revela no fim da mensagem. É o preço de não segurar o
          // primeiro token — e a alternativa era a tela ficar muda enquanto o
          // agente escreve.
          const indice = Number(evento.corpo["fala"] ?? 0);
          setItens((atuais) => {
            const alvo = ultimaFala(atuais, indice);
            return alvo < 0 ? atuais : [...atuais.slice(0, alvo), ...atuais.slice(alvo + 1)];
          });
          setEsperando(true);
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
      // Fecha toda fala ainda aberta: sem isto o cursor de digitação ficaria
      // piscando para sempre no fim de uma resposta que já terminou. Toda, e não
      // só a última, porque um turno com tool no meio abre mais de uma.
      setItens((atuais) => (atuais.some((i) => ehFala(i) && i.escrevendo) ? fechar(atuais) : atuais));
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
    itens,
    esperando,
    erro,
    pedido,
    nota,
    conexao,
    etapa,
    enviar,
  };
}
