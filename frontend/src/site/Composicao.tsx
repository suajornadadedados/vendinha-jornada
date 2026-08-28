// A composição enquanto ela é montada — REQ-9, e o coração da spec.
//
// **Nada aqui é calculado.** Item, quantidade, subtotal, total e valor por pessoa
// vêm do `ComposicaoValidada` exatamente como o validador o devolveu. Um `reduce`
// somando `subtotal` para conferir o total pareceria zelo e seria a regra de ouro
// furada na camada mais fácil de furar sem ninguém notar no diff — a métrica da spec
// é literalmente "contas de dinheiro no frontend: 0".
//
// E quando reprova, aparece **o motivo que o validador deu** — orçamento, slot,
// restrição ou disponibilidade —, não uma mensagem genérica. É a tela onde a regra de
// ouro fica visível para quem nunca vai abrir um trace.

import { CheckCircle, Warning } from "@phosphor-icons/react";

import type { Veredito } from "./useConversa";

/** Só formata. O número já veio pronto e em `Decimal` do servidor. */
function reais(valor: number | string | null | undefined): string {
  if (valor === null || valor === undefined) return "—";
  return Number(valor).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });
}

const NOME_DO_EVENTO: Record<string, string> = {
  cafe_da_manha: "Café da manhã",
  happy_hour: "Happy hour",
  cesta_de_fim_de_ano: "Cesta de fim de ano",
  kit_boas_vindas: "Kit de boas-vindas",
};

const NOME_DO_MOTIVO: Record<string, string> = {
  orcamento: "Orçamento",
  slot: "Item obrigatório",
  restricao: "Restrição alimentar",
  disponibilidade: "Disponibilidade",
  composicao_vazia: "Composição vazia",
};

export function Composicao({ veredito }: { veredito: Veredito }) {
  const aprovada = veredito.aprovada;

  return (
    <section
      className={`composicao ${aprovada ? "composicao--ok" : "composicao--recusa"}`}
      aria-label="Composição do evento"
    >
      <header className="composicao__topo">
        <div>
          <p className="rotulo">{NOME_DO_EVENTO[veredito.tipo_de_evento] ?? veredito.tipo_de_evento}</p>
          <p className="composicao__pessoas">
            {veredito.pessoas} pessoas
            {veredito.atende_pessoas !== veredito.pessoas && (
              <span className="composicao__atende"> · atende {veredito.atende_pessoas}</span>
            )}
          </p>
        </div>
        <span className={`estado ${aprovada ? "estado--ok" : "estado--recusa"}`}>
          {aprovada ? (
            <CheckCircle size={16} weight="regular" aria-hidden="true" />
          ) : (
            <Warning size={16} weight="regular" aria-hidden="true" />
          )}
          {aprovada ? "Aprovada" : "Recusada"}
        </span>
      </header>

      <table className="composicao__itens">
        <caption className="visualmente-oculto">
          Itens da composição, com quantidade, preço unitário e subtotal
        </caption>
        <thead>
          <tr>
            <th scope="col">Item</th>
            <th scope="col" className="num">
              Qtd
            </th>
            <th scope="col" className="num">
              Unit.
            </th>
            <th scope="col" className="num">
              Subtotal
            </th>
          </tr>
        </thead>
        <tbody>
          {veredito.itens.map((item) => (
            <tr key={item.produto_id}>
              <td>{item.nome}</td>
              <td className="num">{item.quantidade}</td>
              <td className="num">{reais(item.preco_unitario)}</td>
              <td className="num">{reais(item.subtotal)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <dl className="composicao__totais">
        <div>
          <dt>Total</dt>
          <dd className="num">{reais(veredito.total_composicao)}</dd>
        </div>
        <div>
          <dt>Por pessoa</dt>
          <dd className="num">{reais(veredito.valor_por_pessoa)}</dd>
        </div>
        {veredito.orcamento_por_pessoa !== null && (
          <div>
            <dt>Seu teto</dt>
            <dd className="num">{reais(veredito.orcamento_por_pessoa)}</dd>
          </div>
        )}
        {veredito.excedente_por_pessoa !== null && (
          <div className="composicao__excedente">
            <dt>Excedente</dt>
            <dd className="num">{reais(veredito.excedente_por_pessoa)}</dd>
          </div>
        )}
      </dl>

      {veredito.problemas_composicao.length > 0 && (
        <ul className="composicao__problemas">
          {veredito.problemas_composicao.map((problema, indice) => (
            <li key={`${problema.motivo}-${indice}`}>
              <span className="composicao__motivo mono">
                {NOME_DO_MOTIVO[problema.motivo] ?? problema.motivo}
              </span>
              <span>{problema.mensagem}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
