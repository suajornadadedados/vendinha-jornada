// O cliente HTTP. Tipos gerados, zero tipo de fronteira escrito à mão.
//
// `schema.d.ts` sai de `npm run types`, que lê o `openapi.json` que
// `python -m vendinha.openapi` gera a partir dos modelos Pydantic. O CI regenera e
// compara: se um campo mudar no backend e ninguém rodar `make types`, o build para
// aqui — em vez de a tela quebrar em runtime, na frente do cliente.
//
// `openapi-fetch` e não um SDK gerado: ele é uma casca de ~2kB sobre o `fetch`, com
// os tipos vindo do schema. Um gerador de cliente completo traria mil linhas de
// código que ninguém lê e que precisam ser regeradas junto — e a métrica da spec é
// sobre tipos escritos à mão, não sobre volume de código gerado.

import createClient from "openapi-fetch";

import { BASE_URL } from "./base";
import type { paths } from "./schema";

// `BASE_URL` mudou de casa para `api/base.ts` e NÃO é reexportada daqui de propósito:
// reexportar deixaria a landing importá-la deste módulo de novo, e o chunk público
// voltaria a carregar o token do operador junto (NC-8).

export const api = createClient<paths>({ baseUrl: BASE_URL });

// ---------------------------------------------------------------- o operador
//
// Não há autenticação neste projeto (fora do escopo da S-07, e dito em voz alta no
// ADR-015). O painel guarda o `OPERADOR_API_TOKEN` em `sessionStorage` e o manda no
// header. `sessionStorage` e não `localStorage`: fechar a aba esquece o token, que
// é o mais perto de "logout" que um painel sem login consegue chegar.

const CHAVE_DO_TOKEN = "vendinha:operador";

export function tokenDoOperador(): string | null {
  try {
    return sessionStorage.getItem(CHAVE_DO_TOKEN);
  } catch {
    // Navegador com armazenamento bloqueado. O painel pede o token de novo, que é
    // o comportamento certo — e melhor do que uma tela branca por exceção.
    return null;
  }
}

export function guardarToken(token: string): void {
  try {
    sessionStorage.setItem(CHAVE_DO_TOKEN, token);
  } catch {
    /* sem armazenamento: o token vale só para esta navegação */
  }
}

export function esquecerToken(): void {
  try {
    sessionStorage.removeItem(CHAVE_DO_TOKEN);
  } catch {
    /* nada a esquecer */
  }
}

export function cabecalhoDoOperador(): Record<string, string> {
  const token = tokenDoOperador();
  return token ? { "X-Operador-Token": token } : {};
}

/** 401 significa uma coisa só neste painel: o token não serve. */
export class NaoAutorizado extends Error {
  constructor() {
    super("credencial de operador invalida");
    this.name = "NaoAutorizado";
  }
}
