// De onde a API responde. Um módulo só para isto, e o motivo é de bundle.
//
// `BASE_URL` morava em `api/client.ts`, ao lado do `createClient` e das funções que
// leem e gravam o token do operador. A landing pública importa `BASE_URL` (o
// `useConversa` monta as URLs do `POST /chat` e do SSE à mão, porque `openapi-fetch`
// não fala streaming), e o bundler trazia o módulo inteiro junto: o chunk público
// saía com `X-Operador-Token` e `vendinha:operador` dentro.
//
// Nada vazava — o token vive no `sessionStorage` do operador, que na aba do cliente
// está vazio —, mas a REQ-7 promete que a landing "sai do bundle sem uma linha de JS
// do painel", com alvo **0**, e a métrica estava literalmente falsa (verificação
// independente da S-07, rodada 2, NC-8). Uma constante num módulo sem dependências é
// o que faz a promessa voltar a ser verdade.

export const BASE_URL =
  (import.meta.env["VITE_API_BASE_URL"] as string | undefined) ?? "http://localhost:8000";
