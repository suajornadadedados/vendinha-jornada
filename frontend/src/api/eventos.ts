// Os eventos do stream, tipados a partir do schema gerado.
//
// Nenhuma forma é escrita aqui: cada tipo é um alias para o que o `openapi.json`
// declarou, e o `openapi.json` sai dos modelos Pydantic. Se alguém acrescentar um
// campo em `AprovacaoPendente` no backend, ele aparece aqui sem ninguém digitar
// nada — e se alguém renomear um, o build para.

import type { components } from "./schema";
import type { EventoBruto } from "./sse";

type S = components["schemas"];

export type SessaoIniciada = S["SessaoIniciada"];
export type MensagemRegistrada = S["MensagemRegistrada"];
export type ComposicaoAvaliada = S["ComposicaoAvaliada"];
export type PedidoAtualizado = S["PedidoAtualizado"];
export type AprovacaoPendente = S["AprovacaoPendente"];
export type NotaDecidida = S["NotaDecidida"];
export type AtrasoNoStream = S["AtrasoNoStream"];

export type EventoDoPainel =
  | SessaoIniciada
  | MensagemRegistrada
  | ComposicaoAvaliada
  | PedidoAtualizado
  | AprovacaoPendente
  | NotaDecidida
  | AtrasoNoStream;

export type SessionEvent = S["SessionEvent"];
export type TokenEvent = S["TokenEvent"];
export type ErrorEvent = S["ErrorEvent"];
export type DoneEvent = S["DoneEvent"];

/**
 * Do quadro cru do SSE para o evento tipado.
 *
 * Devolve `null` em vez de lançar quando o JSON não presta: um evento corrompido
 * não pode derrubar a assinatura inteira e levar junto os que vierem depois. O
 * `tipo` do corpo é conferido contra o nome do `event:` — eles são a mesma coisa
 * no servidor, e discordarem significa que alguém está mandando outra coisa.
 */
export function lerEventoDoPainel(bruto: EventoBruto): EventoDoPainel | null {
  try {
    const corpo = JSON.parse(bruto.dados) as { tipo?: string };
    if (typeof corpo.tipo !== "string" || corpo.tipo !== bruto.evento) return null;
    return corpo as EventoDoPainel;
  } catch {
    return null;
  }
}

/** O mesmo, para os quatro eventos de `/chat`, que não têm campo `tipo`. */
export function lerEventoDoChat(
  bruto: EventoBruto,
): { evento: string; corpo: Record<string, unknown> } | null {
  try {
    return { evento: bruto.evento, corpo: JSON.parse(bruto.dados) as Record<string, unknown> };
  } catch {
    return null;
  }
}
