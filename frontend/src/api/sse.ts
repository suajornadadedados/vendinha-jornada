// Um leitor de `text/event-stream` sobre `fetch`, porque `EventSource` não serve.
//
// Duas razões, e nenhuma delas é preferência:
//
//   1. `/chat` é POST. `EventSource` só faz GET.
//   2. `/admin/eventos` exige o header `X-Operador-Token`. `EventSource` não manda
//      header nenhum, e a saída fácil — o token na query string — o colocaria no
//      log de acesso de todo proxy do caminho.
//
// São ~90 linhas e nenhuma dependência nova. O que ele NÃO faz também importa: não
// reconecta sozinho. A reconexão mora em `assinar()` abaixo, onde ela pode contar
// ao chamador que está desconectada — um leitor que reconecta em silêncio produz
// exatamente a tela que a spec manda reprovar: números velhos apresentados como
// atuais.

export interface EventoBruto {
  readonly evento: string;
  readonly dados: string;
}

export interface OpcoesDoStream {
  readonly metodo?: "GET" | "POST";
  readonly corpo?: unknown;
  readonly cabecalhos?: Record<string, string>;
  readonly sinal?: AbortSignal;
}

/** Lê um stream SSE até o fim. Lança se a resposta não for 2xx. */
export async function* lerStream(
  url: string,
  opcoes: OpcoesDoStream = {},
): AsyncGenerator<EventoBruto> {
  const { metodo = "GET", corpo, cabecalhos = {}, sinal } = opcoes;

  const resposta = await fetch(url, {
    method: metodo,
    headers: {
      Accept: "text/event-stream",
      ...(corpo === undefined ? {} : { "Content-Type": "application/json" }),
      ...cabecalhos,
    },
    ...(corpo === undefined ? {} : { body: JSON.stringify(corpo) }),
    ...(sinal ? { signal: sinal } : {}),
  });

  if (!resposta.ok) {
    throw new ErroDeStream(resposta.status);
  }
  if (!resposta.body) {
    throw new ErroDeStream(0);
  }

  const leitor = resposta.body.getReader();
  const decodificador = new TextDecoder();
  let pendente = "";

  try {
    for (;;) {
      const { done, value } = await leitor.read();
      if (done) break;

      // `stream: true` é o que impede um caractere multibyte partido entre dois
      // pacotes de virar `` no meio de uma palavra. Um acento por frase é o
      // suficiente para isso acontecer em português.
      pendente += decodificador.decode(value, { stream: true });

      // Um evento SSE termina em linha em branco; `\r?\n` porque nem todo proxy
      // preserva `\n` puro. O último pedaço volta para `pendente` justamente
      // porque ele pode estar cortado no meio — um evento nunca é processado
      // antes de o separador ter chegado.
      const blocos = pendente.split(/\r?\n\r?\n/);
      pendente = blocos.pop() ?? "";
      for (const bloco of blocos) {
        const analisado = analisar(bloco);
        if (analisado) yield analisado;
      }
    }
  } finally {
    // Sempre: sem isto, sair do `for await` por `break` deixaria a conexão aberta,
    // e um painel que troca de tela algumas vezes acumularia streams vivos.
    leitor.cancel().catch(() => undefined);
  }
}

function analisar(bloco: string): EventoBruto | null {
  let evento = "message";
  const dados: string[] = [];

  for (const linha of bloco.split(/\r?\n/)) {
    if (linha.startsWith(":")) continue; // comentário — é o que o heartbeat manda
    const separador = linha.indexOf(":");
    const campo = separador === -1 ? linha : linha.slice(0, separador);
    const valor = separador === -1 ? "" : linha.slice(separador + 1).replace(/^ /, "");
    if (campo === "event") evento = valor;
    else if (campo === "data") dados.push(valor);
  }

  if (dados.length === 0) return null;
  return { evento, dados: dados.join("\n") };
}

export class ErroDeStream extends Error {
  constructor(readonly status: number) {
    super(`stream recusado: ${status}`);
    this.name = "ErroDeStream";
  }
}

export type EstadoDaConexao = "conectando" | "conectado" | "desconectado";

/**
 * Assina um stream e reconecta com backoff — dizendo em voz alta quando não está
 * conectado.
 *
 * O `aoMudarEstado` é o ponto deste wrapper. A verificação independente da S-07
 * manda derrubar o backend no meio e julgar a honestidade da tela; uma reconexão
 * silenciosa deixaria a tela exibindo o último estado conhecido como se fosse o
 * atual, e é isso que ela existe para impedir.
 */
export function assinar(
  url: string,
  opcoes: OpcoesDoStream & {
    aoReceber: (evento: EventoBruto) => void;
    aoMudarEstado?: (estado: EstadoDaConexao) => void;
    aoNaoAutorizar?: () => void;
  },
): () => void {
  const controlador = new AbortController();
  let vivo = true;
  let espera = 500;

  const anunciar = (estado: EstadoDaConexao) => opcoes.aoMudarEstado?.(estado);

  void (async () => {
    while (vivo) {
      anunciar("conectando");
      try {
        for await (const evento of lerStream(url, { ...opcoes, sinal: controlador.signal })) {
          if (!vivo) return;
          anunciar("conectado");
          espera = 500;
          opcoes.aoReceber(evento);
        }
        // O stream terminou sem erro: o servidor fechou. Reconectar é certo.
        anunciar("desconectado");
      } catch (erro) {
        if (!vivo) return;
        if (erro instanceof ErroDeStream && erro.status === 401) {
          // Token errado não melhora com tentativa: insistir só produziria um
          // painel piscando "reconectando" para sempre em vez de pedir o token.
          anunciar("desconectado");
          opcoes.aoNaoAutorizar?.();
          return;
        }
        anunciar("desconectado");
      }

      if (!vivo) return;
      await new Promise((resolva) => setTimeout(resolva, espera));
      // Teto de 15s: a demo é local, e uma espera de minutos faria parecer que a
      // API voltou quebrada quando ela só voltou.
      espera = Math.min(espera * 2, 15_000);
    }
  })();

  return () => {
    vivo = false;
    controlador.abort();
  };
}
