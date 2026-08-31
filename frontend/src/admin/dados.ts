// As leituras do painel, e a assinatura que as mantém frescas.
//
// **Zero polling.** É métrica da spec, e o desenho que a sustenta é este: cada tela
// faz um `GET` na montagem e depois só reage a evento. O `useEventos` abaixo é um
// único assinante de `/admin/eventos` no topo da árvore — não um por componente —,
// e ele invalida as consultas que aquele evento tornou velhas.
//
// Um assinante por tela seria N streams SSE abertos para o mesmo barramento, cada um
// com sua fila no servidor. O barramento aguenta; o navegador é que não precisa.

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { BASE_URL } from "../api/base";
import { cabecalhoDoOperador, esquecerToken } from "../api/client";
import { lerEventoDoPainel } from "../api/eventos";
import type { EventoDoPainel } from "../api/eventos";
import type { components } from "../api/schema";
import type { EstadoDaConexao } from "../api/sse";
import { assinar } from "../api/sse";

type S = components["schemas"];
export type Metricas = S["Metricas"];
export type ConversaNaLista = S["ConversaNaLista"];
export type DetalheDaConversa = S["DetalheDaConversa"];
export type PedidoNoPainel = S["PedidoNoPainel"];
export type FilaDoOperador = S["FilaDoOperador"];
export type PedidoNaFila = S["PedidoNaFila"];
export type PromptsDoAgente = S["PromptsDoAgente"];
export type ConfigResponse = S["ConfigResponse"];
export type ModelsResponse = S["ModelsResponse"];
export type CustoApurado = S["CustoApurado"];

export class SemAutorizacao extends Error {
  constructor() {
    super("credencial de operador invalida");
    this.name = "SemAutorizacao";
  }
}

/** Um `GET` autenticado. 401 vira `SemAutorizacao`, que a casca trata pedindo o token. */
async function ler<T>(caminho: string): Promise<T> {
  const resposta = await fetch(`${BASE_URL}${caminho}`, {
    headers: { Accept: "application/json", ...cabecalhoDoOperador() },
  });
  if (resposta.status === 401) {
    esquecerToken();
    throw new SemAutorizacao();
  }
  if (!resposta.ok) throw new Error(`${caminho} respondeu ${resposta.status}`);
  return (await resposta.json()) as T;
}

async function escrever<T>(caminho: string, corpo: unknown): Promise<T> {
  const resposta = await fetch(`${BASE_URL}${caminho}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...cabecalhoDoOperador(),
    },
    body: JSON.stringify(corpo),
  });
  if (resposta.status === 401) {
    esquecerToken();
    throw new SemAutorizacao();
  }
  if (!resposta.ok) {
    const detalhe = (await resposta.json().catch(() => null)) as { detail?: string } | null;
    // A mensagem do servidor, não uma nossa: quando ele recusa uma rejeição sem
    // motivo, a frase dele é a que explica o porquê.
    throw new Error(detalhe?.detail ?? `a ação falhou (${resposta.status})`);
  }
  return (await resposta.json()) as T;
}

// As consultas nunca revalidam sozinhas: quem as atualiza é o evento.
const SEM_POLLING = {
  refetchInterval: false as const,
  refetchOnWindowFocus: false,
  staleTime: Infinity,
};

export function useMetricas(janela: string) {
  return useQuery({
    queryKey: ["metricas", janela],
    queryFn: () => ler<Metricas>(`/admin/metricas?janela=${encodeURIComponent(janela)}`),
    ...SEM_POLLING,
  });
}

export function useConversas() {
  return useQuery({
    queryKey: ["conversas"],
    queryFn: () => ler<{ conversas: ConversaNaLista[] }>("/admin/conversas"),
    ...SEM_POLLING,
  });
}

export function useConversa(sessionId: string | null) {
  return useQuery({
    queryKey: ["conversa", sessionId],
    queryFn: () => ler<DetalheDaConversa>(`/admin/conversas/${encodeURIComponent(sessionId!)}`),
    enabled: sessionId !== null,
    ...SEM_POLLING,
  });
}

export function usePedidos() {
  return useQuery({
    queryKey: ["pedidos"],
    queryFn: () => ler<{ pedidos: PedidoNoPainel[] }>("/admin/pedidos"),
    ...SEM_POLLING,
  });
}

export function useFila() {
  return useQuery({
    queryKey: ["fila"],
    queryFn: () => ler<FilaDoOperador>("/operador/fila"),
    ...SEM_POLLING,
  });
}

export function usePrompts() {
  return useQuery({
    queryKey: ["prompts"],
    queryFn: () => ler<PromptsDoAgente>("/admin/prompts"),
    ...SEM_POLLING,
  });
}

export function useConfig() {
  return useQuery({
    queryKey: ["config"],
    queryFn: () => ler<ConfigResponse>("/config"),
    ...SEM_POLLING,
  });
}

export function useModelos() {
  return useQuery({
    queryKey: ["modelos"],
    queryFn: () => ler<ModelsResponse>("/models"),
    ...SEM_POLLING,
  });
}

export function decidir(
  pedidoId: string,
  decisao: "aprovar" | "rejeitar",
  corpo: { operador: string; motivo?: string },
) {
  return escrever<S["DecisaoRegistrada"]>(`/operador/pedidos/${pedidoId}/${decisao}`, corpo);
}

export async function gravarConfig(corpo: Record<string, unknown>): Promise<ConfigResponse> {
  const resposta = await fetch(`${BASE_URL}/config`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...cabecalhoDoOperador() },
    body: JSON.stringify(corpo),
  });
  if (!resposta.ok) {
    const detalhe = (await resposta.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(detalhe?.detail ?? `a gravação falhou (${resposta.status})`);
  }
  return (await resposta.json()) as ConfigResponse;
}

// ---------------------------------------------------------------- o stream

export interface Painel {
  readonly conexao: EstadoDaConexao;
  readonly perdidos: number;
  readonly ultimoEvento: Date | null;
  readonly pendentes: number;
  /** O `aprovacao_pendente` mais recente, para o toast do sino. */
  readonly aviso: { pedidoId: string; razaoSocial: string; total: string } | null;
  readonly limparAviso: () => void;
}

/**
 * O único assinante do barramento. Traduz evento em invalidação de consulta.
 *
 * O mapa abaixo é o coração do "zero polling": cada evento diz que consultas
 * envelheceram. Invalidar tudo a cada evento seria mais simples e recarregaria a
 * tela inteira a cada token — que é polling com outro nome, e mais caro.
 */
export function useEventos(aoNaoAutorizar: () => void): Painel {
  const cliente = useQueryClient();
  const [conexao, setConexao] = useState<EstadoDaConexao>("conectando");
  const [perdidos, setPerdidos] = useState(0);
  const [ultimoEvento, setUltimoEvento] = useState<Date | null>(null);
  const [pendentes, setPendentes] = useState(0);
  const [aviso, setAviso] = useState<Painel["aviso"]>(null);

  useEffect(() => {
    return assinar(`${BASE_URL}/admin/eventos`, {
      cabecalhos: cabecalhoDoOperador(),
      aoMudarEstado: setConexao,
      aoNaoAutorizar: () => {
        esquecerToken();
        aoNaoAutorizar();
      },
      aoReceber: (bruto) => {
        const evento = lerEventoDoPainel(bruto);
        if (!evento) return;
        setUltimoEvento(new Date());
        aplicar(evento, cliente, { setPerdidos, setPendentes, setAviso });
      },
    });
  }, [cliente, aoNaoAutorizar]);

  return {
    conexao,
    perdidos,
    ultimoEvento,
    pendentes,
    aviso,
    limparAviso: () => setAviso(null),
  };
}

function aplicar(
  evento: EventoDoPainel,
  cliente: ReturnType<typeof useQueryClient>,
  set: {
    setPerdidos: (fn: (n: number) => number) => void;
    setPendentes: (fn: (n: number) => number) => void;
    setAviso: (aviso: Painel["aviso"]) => void;
  },
): void {
  const invalidar = (chave: string) => void cliente.invalidateQueries({ queryKey: [chave] });

  switch (evento.tipo) {
    case "sessao_iniciada":
      invalidar("conversas");
      invalidar("metricas");
      return;

    case "mensagem":
    case "composicao_avaliada":
      invalidar("conversas");
      void cliente.invalidateQueries({ queryKey: ["conversa", evento.session_id] });
      if (evento.tipo === "composicao_avaliada") invalidar("metricas");
      return;

    case "pedido_atualizado":
      invalidar("pedidos");
      invalidar("conversas");
      invalidar("metricas");
      invalidar("fila");
      return;

    case "aprovacao_pendente":
      invalidar("fila");
      invalidar("metricas");
      set.setPendentes((n) => n + 1);
      set.setAviso({
        pedidoId: evento.pedido_id,
        razaoSocial: evento.razao_social,
        total: String(evento.total),
      });
      return;

    case "nota_decidida":
      invalidar("fila");
      invalidar("pedidos");
      invalidar("metricas");
      set.setPendentes((n) => Math.max(0, n - 1));
      return;

    case "atraso":
      // Não invalida nada: recarregar por conta própria esconderia o buraco. A tela
      // diz que perdeu e oferece recarregar, que é a decisão de quem está olhando.
      set.setPerdidos((n) => n + evento.perdidos);
  }
}
