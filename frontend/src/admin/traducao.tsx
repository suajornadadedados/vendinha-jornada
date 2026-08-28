// De JSON de ferramenta para português.
//
// A tela de rastreabilidade mostrava o argumento da tool e o retorno dela como
// `<pre>` de JSON cru — nomes de variável, chaves, colchetes. Isso serve a quem
// escreveu o backend e a mais ninguém: quem opera o atendimento precisa saber *o que
// aconteceu*, não como o campo se chama no código.
//
// O que este arquivo faz, e só isto: dá nome de gente para cada ferramenta e para
// cada campo, e escolhe a forma de exibir o valor. **Não calcula nada.** Todo número
// que aparece aqui saiu pronto do backend — a regra de `formato.tsx` vale igual, e
// pelo mesmo motivo: um "helper" que somasse um subtotal seria conta de dinheiro no
// navegador com outro nome.
//
// Campo desconhecido não some: cai no `humanizar()`, que transforma `nome_do_campo`
// em "Nome do campo". Uma tool nova nasce legível sem passar por aqui — pior do que
// um rótulo genérico seria a tela esconder um dado porque ninguém a atualizou.

import type { ReactNode } from "react";

import { inteiro, reais } from "./formato";

/**
 * O que cada ferramenta significa, das duas pontas: o que o agente pediu, e o que o
 * sistema respondeu. As duas frases são diferentes de propósito — é a regra de ouro
 * ficando visível na tela para quem nunca vai abrir um trace.
 */
const FERRAMENTAS: Record<string, { pedido: string; resposta: string }> = {
  buscar_produtos: {
    pedido: "Procurou produtos no catálogo",
    resposta: "O catálogo respondeu",
  },
  detalhar_produto: {
    pedido: "Abriu a ficha de alguns produtos",
    resposta: "A ficha dos produtos",
  },
  consultar_preco: {
    pedido: "Consultou o preço de tabela",
    resposta: "Os preços vieram do banco",
  },
  validar_composicao: {
    pedido: "Mandou a sugestão para conferência",
    resposta: "A conferência respondeu",
  },
  validar_dados_cliente: {
    pedido: "Mandou os dados da empresa para conferência",
    resposta: "A conferência dos dados respondeu",
  },
  criar_pedido: {
    pedido: "Pediu para registrar o pedido",
    resposta: "O pedido foi registrado",
  },
  gerar_link_pagamento: {
    pedido: "Pediu o link de pagamento",
    resposta: "O link de pagamento",
  },
  consultar_pedido: {
    pedido: "Consultou a situação do pedido",
    resposta: "A situação do pedido",
  },
};

export function nomeDaFerramenta(ferramenta: string | null | undefined, proposta: boolean): string {
  if (!ferramenta) return proposta ? "O agente pediu algo ao sistema" : "O sistema respondeu";
  const conhecida = FERRAMENTAS[ferramenta];
  if (conhecida) return proposta ? conhecida.pedido : conhecida.resposta;
  return proposta ? `Pediu: ${humanizar(ferramenta)}` : `Resposta de: ${humanizar(ferramenta)}`;
}

/** `valor_por_pessoa` → "Valor por pessoa". A rede de segurança dos campos sem rótulo. */
function humanizar(chave: string): string {
  const palavras = chave.replace(/_/g, " ").trim();
  return palavras.charAt(0).toUpperCase() + palavras.slice(1);
}

const ROTULOS: Record<string, string> = {
  aprovada: "Passou na conferência",
  atende_pessoas: "Atende",
  bairro: "Bairro",
  cep: "CEP",
  cidade: "Cidade",
  cnpj: "CNPJ",
  complemento: "Complemento",
  composicoes: "Composições",
  contato_email: "E-mail do contato",
  contato_nome: "Nome do contato",
  criado_em: "Criado em",
  encontrados: "Resultado",
  endereco: "Endereço",
  empresa: "Empresa",
  excedente_por_pessoa: "Passou do orçamento em",
  faltando: "Faltou informar",
  inscricao_estadual: "Inscrição estadual",
  itens: "Itens",
  logradouro: "Rua",
  mensagem: "O que houve",
  motivo: "Tipo do problema",
  nao_encontrados: "Não encontrados no catálogo",
  nome: "Produto",
  numero: "Número",
  observacao: "Observação",
  orcamento_por_pessoa: "Orçamento por pessoa",
  pedido_id: "Número do pedido",
  pessoas: "Pessoas",
  preco_unitario: "Preço unitário",
  problemas: "Problemas encontrados",
  problemas_composicao: "Problemas encontrados",
  produto_id: "Código",
  produto_ids: "Produtos escolhidos",
  quantidade: "Quantidade",
  razao_social: "Razão social",
  rendimento: "Rende",
  restricoes: "Restrições alimentares",
  status: "Situação",
  subtotal: "Subtotal",
  termo: "Buscou por",
  tipo: "Tipo",
  tipo_de_evento: "Tipo de evento",
  total: "Total",
  total_composicao: "Total",
  uf: "Estado",
  url_pagamento: "Link de pagamento",
  valor_por_pessoa: "Por pessoa",
};

/** Campos em dinheiro. Vêm prontos do backend; aqui só ganham o `R$`. */
const DINHEIRO = new Set([
  "excedente_por_pessoa",
  "orcamento_por_pessoa",
  "preco",
  "preco_unitario",
  "subtotal",
  "total",
  "total_composicao",
  "valor_por_pessoa",
]);

export const TIPO_DE_EVENTO: Record<string, string> = {
  cafe_da_manha: "Café da manhã",
  happy_hour: "Happy hour",
  cesta_de_fim_de_ano: "Cesta de fim de ano",
  kit_de_boas_vindas: "Kit de boas-vindas",
};

export const MOTIVO_DO_PROBLEMA: Record<string, string> = {
  orcamento: "Estourou o orçamento",
  slot: "Faltou um item obrigatório",
  restricao: "Bateu numa restrição alimentar",
  disponibilidade: "Produto indisponível",
  composicao_vazia: "Nenhum item na composição",
};

function valorLegivel(chave: string, valor: unknown): ReactNode {
  if (valor === null || valor === undefined || valor === "") return <span className="ausente">—</span>;
  if (typeof valor === "boolean") return valor ? "sim" : "não";
  if (DINHEIRO.has(chave)) return <span className="num">{reais(valor as string)}</span>;
  if (chave === "tipo_de_evento") return TIPO_DE_EVENTO[String(valor)] ?? humanizar(String(valor));
  if (chave === "motivo") return MOTIVO_DO_PROBLEMA[String(valor)] ?? humanizar(String(valor));
  if (typeof valor === "number") return <span className="num">{inteiro(valor)}</span>;
  const texto = String(valor);
  if (/^https?:\/\//.test(texto)) {
    return (
      <a href={texto} target="_blank" rel="noreferrer" className="sublinhado">
        abrir o link
      </a>
    );
  }
  return texto;
}

function ehObjeto(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === "object" && valor !== null && !Array.isArray(valor);
}

/**
 * Uma lista de objetos com as mesmas chaves vira tabela; qualquer outra coisa vira
 * lista de campos. É a diferença entre "os itens da composição" lidos de relance e
 * doze blocos empilhados dizendo a mesma coisa.
 */
function Tabelinha({ linhas }: { linhas: Record<string, unknown>[] }) {
  const colunas = Array.from(new Set(linhas.flatMap((linha) => Object.keys(linha))));
  return (
    <div className="tabela-rolante">
      <table className="tabelinha">
        <thead>
          <tr>
            {colunas.map((coluna) => (
              <th key={coluna} className={DINHEIRO.has(coluna) ? "num" : undefined}>
                {ROTULOS[coluna] ?? humanizar(coluna)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {linhas.map((linha, indice) => (
            <tr key={indice}>
              {colunas.map((coluna) => (
                <td key={coluna} className={DINHEIRO.has(coluna) ? "num" : undefined}>
                  {valorLegivel(coluna, linha[coluna])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Campos({ dados }: { dados: Record<string, unknown> }) {
  const entradas = Object.entries(dados).filter(([, valor]) => {
    if (valor === null || valor === undefined) return false;
    if (Array.isArray(valor) && valor.length === 0) return false;
    return true;
  });

  if (entradas.length === 0) {
    return <p className="passo__vazio">Sem detalhes — a chamada não levou nenhum dado.</p>;
  }

  return (
    <dl className="campos">
      {entradas.map(([chave, valor]) => {
        const rotulo = ROTULOS[chave] ?? humanizar(chave);

        if (Array.isArray(valor)) {
          const objetos = valor.filter(ehObjeto);
          if (objetos.length === valor.length && objetos.length > 0) {
            return (
              <div key={chave} className="campos__bloco">
                <dt>{rotulo}</dt>
                <dd>
                  {objetos.length === 1 && objetos[0] ? (
                    <Campos dados={objetos[0]} />
                  ) : (
                    <Tabelinha linhas={objetos} />
                  )}
                </dd>
              </div>
            );
          }
          return (
            <div key={chave}>
              <dt>{rotulo}</dt>
              <dd className="campos__fichas">
                {valor.map((item, indice) => (
                  <span key={indice} className="ficha">
                    {valorLegivel(chave.replace(/s$/, ""), item)}
                  </span>
                ))}
              </dd>
            </div>
          );
        }

        if (ehObjeto(valor)) {
          return (
            <div key={chave} className="campos__bloco">
              <dt>{rotulo}</dt>
              <dd>
                <Campos dados={valor} />
              </dd>
            </div>
          );
        }

        return (
          <div key={chave}>
            <dt>{rotulo}</dt>
            <dd>{valorLegivel(chave, valor)}</dd>
          </div>
        );
      })}
    </dl>
  );
}

/**
 * O conteúdo de uma chamada de ferramenta, legível.
 *
 * Quando não for JSON — uma tool que devolve frase, ou um erro — sai como texto, e
 * não como "erro ao interpretar". Um retorno que a tela não entende ainda é
 * informação sobre o atendimento; escondê-lo seria mentir por omissão.
 */
export function ConteudoDaFerramenta({ bruto }: { bruto: string }) {
  const texto = (bruto ?? "").trim();
  if (!texto) return <p className="passo__vazio">Sem detalhes.</p>;

  let dados: unknown;
  try {
    dados = JSON.parse(texto);
  } catch {
    return <p className="passo__texto">{texto}</p>;
  }

  if (ehObjeto(dados)) return <Campos dados={dados} />;
  if (Array.isArray(dados)) {
    const objetos = dados.filter(ehObjeto);
    if (objetos.length === dados.length && objetos.length > 0) return <Tabelinha linhas={objetos} />;
  }
  return <p className="passo__texto">{texto}</p>;
}
