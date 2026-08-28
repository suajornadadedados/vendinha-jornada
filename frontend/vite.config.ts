import { resolve } from "node:path";

import tailwind from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, type Connect, type Plugin } from "vite";

/**
 * O painel tem rotas de verdade (`/admin`, `/admin/conversas`, …), e uma rota de
 * verdade tem que sobreviver a um F5.
 *
 * `admin.html` é uma entrada estática servida por caminho fixo: sem isto, abrir
 * `/admin/pedidos` direto na barra de endereços dá 404, porque não existe arquivo
 * com esse nome. O middleware reescreve qualquer caminho sob `/admin` para o HTML
 * da entrada e deixa o roteador do navegador decidir o resto — o mesmo `try_files`
 * que qualquer SPA precisa, escrito onde ele é lido.
 *
 * O que NÃO é reescrito: requisição de arquivo (tem extensão) e o que o Vite
 * atende internamente (`/@vite`, `/@fs`, `/src`, `/node_modules`). Reescrever esses
 * devolveria HTML no lugar de um módulo, e o erro chega como "Failed to fetch
 * dynamically imported module", que não aponta para cá.
 */
function rotasDoPainel(): Plugin {
  const middleware: Connect.NextHandleFunction = (req, _res, next) => {
    const caminho = (req.url ?? "").split("?")[0] ?? "";
    const interno = /^\/(@|src\/|node_modules\/)/.test(caminho);
    const arquivo = /\.[a-z0-9]+$/i.test(caminho);
    if (/^\/admin(\/|$)/.test(caminho) && !interno && !arquivo) {
      req.url = "/admin.html";
    }
    next();
  };
  // `use` direto, e NÃO `return () => use(...)`. A forma com retorno instala o
  // middleware DEPOIS dos internos do Vite, e o fallback de HTML dele já teria
  // decidido: `/admin` acha `admin.html` pelo nome e funciona, `/admin/conversas`
  // cai no `index.html` e serve a LANDING com a URL do painel na barra. Passou pelo
  // primeiro teste — que só olhou o status 200 — e só apareceu no screenshot.
  return {
    name: "vendinha:rotas-do-painel",
    configureServer(servidor) {
      servidor.middlewares.use(middleware);
    },
    configurePreviewServer(servidor) {
      servidor.middlewares.use(middleware);
    },
  };
}

// Duas entradas no mesmo projeto, e não dois projetos.
//
// Elas compartilham `src/api/` — o cliente gerado do OpenAPI e o leitor de SSE —,
// que é o ponto: o widget da landing e o painel falam com a MESMA API pelos MESMOS
// tipos. Dois projetos separados teriam duas cópias do cliente, e a segunda seria a
// que fica velha.
//
// E são duas entradas, e não duas rotas do mesmo bundle, porque a landing é uma
// página pública: ela sai sem uma linha de JavaScript do painel dentro.
export default defineConfig({
  plugins: [react(), tailwind(), rotasDoPainel()],
  resolve: {
    alias: { "@": resolve(__dirname, "src") },
  },
  build: {
    rollupOptions: {
      input: {
        site: resolve(__dirname, "index.html"),
        admin: resolve(__dirname, "admin.html"),
      },
    },
  },
  server: {
    port: 5173,
    // `strictPort` porque a origem está na allowlist de CORS do backend: cair para
    // a 5174 em silêncio produziria um erro de CORS numa API perfeitamente de pé —
    // a falha mais confusa de diagnosticar do conjunto.
    strictPort: true,
  },
});
