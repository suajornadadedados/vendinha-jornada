// Formatação — e a regra que a governa: **formatar, nunca calcular.**
//
// Tudo aqui recebe um número já pronto do backend e decide como escrevê-lo. Não há
// uma soma, uma divisão ou uma porcentagem calculada neste arquivo, e é de propósito:
// a métrica da spec é "contas de dinheiro no frontend: 0", e a forma de furá-la é
// exatamente um helper de formatação que "só" divide por cem.
//
// A segunda regra: **ausência é traço, e o traço diz por quê.** Um `null` que virasse
// `0` seria uma afirmação falsa com cara de dado — a mesma que o `precos.py` recusa
// duas camadas abaixo.

import { CheckCircle, Clock, Warning, XCircle } from "@phosphor-icons/react";
import type { ReactNode } from "react";

import type { CustoApurado } from "./dados";

export function Ausente({ porque }: { porque: string }) {
  return (
    <span className="ausente" title={porque}>
      —
    </span>
  );
}

export function reais(valor: number | string | null | undefined): string {
  if (valor === null || valor === undefined || valor === "") return "—";
  return Number(valor).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export function dolares(valor: number | string | null | undefined): string {
  if (valor === null || valor === undefined || valor === "") return "—";
  return Number(valor).toLocaleString("pt-BR", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  });
}

/** O backend manda a razão pronta (0.4286); aqui ela só ganha o símbolo. */
export function porcento(razao: number | string | null | undefined): string {
  if (razao === null || razao === undefined) return "—";
  return `${(Number(razao) * 100).toFixed(1).replace(".", ",")}%`;
}

export function milissegundos(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(2).replace(".", ",")} s`;
}

export function inteiro(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return n.toLocaleString("pt-BR");
}

export function quando(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function hora(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

/**
 * O custo, com a incompletude visível.
 *
 * Quando `completo` é falso o valor sai com um aviso ao lado, e o `title` diz o que
 * falta — modelo sem preço cadastrado, ou turno em que o provedor não informou
 * consumo. Sem isso, um parcial apareceria como total, que é o modo de falha nomeado
 * no ADR-015.
 */
export function Custo({ custo }: { custo: CustoApurado }) {
  if (custo.usd === null || custo.usd === undefined) {
    const porque = custo.modelos_sem_preco.length
      ? `sem preço cadastrado para ${custo.modelos_sem_preco.join(", ")}`
      : "o provedor não informou o consumo destes turnos";
    return <Ausente porque={porque} />;
  }

  const faltas: string[] = [];
  if (custo.modelos_sem_preco.length)
    faltas.push(`sem preço para ${custo.modelos_sem_preco.join(", ")}`);
  if (custo.turnos_sem_uso)
    faltas.push(`${custo.turnos_sem_uso} turno(s) sem consumo informado`);

  return (
    <span className="inline-flex items-center gap-1">
      <span className="num">{dolares(custo.usd)}</span>
      {!custo.completo && (
        <Warning
          size={14}
          weight="regular"
          className="text-[var(--ocre)]"
          aria-label={`parcial: ${faltas.join("; ")}`}
        />
      )}
    </span>
  );
}

const ESTADOS: Record<string, { classe: string; texto: string; icone: ReactNode }> = {
  aguardando_pagamento: {
    classe: "estado--espera",
    texto: "Aguardando pagamento",
    icone: <Clock size={14} weight="regular" aria-hidden="true" />,
  },
  aguardando_aprovacao_nf: {
    classe: "estado--espera",
    texto: "Aguardando aprovação",
    icone: <Clock size={14} weight="regular" aria-hidden="true" />,
  },
  nota_emitida: {
    classe: "estado--ok",
    texto: "Nota emitida",
    icone: <CheckCircle size={14} weight="regular" aria-hidden="true" />,
  },
  nota_rejeitada: {
    classe: "estado--recusa",
    texto: "Nota rejeitada",
    icone: <XCircle size={14} weight="regular" aria-hidden="true" />,
  },
};

/** Cor **e** ícone **e** palavra. Nenhum estado se distingue só por matiz. */
export function Estado({ status }: { status: string | null | undefined }) {
  if (!status) return <Ausente porque="esta conversa ainda não gerou pedido" />;
  const definido = ESTADOS[status];
  if (!definido) return <span className="estado estado--neutro">{status}</span>;
  return (
    <span className={`estado ${definido.classe}`}>
      {definido.icone}
      {definido.texto}
    </span>
  );
}

/**
 * O motivo da devolução, em português de quem opera a loja.
 *
 * Curto porque vira rótulo de eixo, e explícito porque "Orçamento" sozinho não diz
 * se estourou ou se faltou informar. A versão longa, para o corpo de texto, está em
 * `traducao.tsx` (`MOTIVO_DO_PROBLEMA`).
 */
export const NOME_DO_MOTIVO: Record<string, string> = {
  orcamento: "Estourou o orçamento",
  slot: "Faltou item obrigatório",
  restricao: "Restrição alimentar",
  disponibilidade: "Produto indisponível",
  composicao_vazia: "Sem nenhum item",
};
