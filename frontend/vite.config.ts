import { resolve } from "node:path";

import tailwind from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

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
  plugins: [react(), tailwind()],
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
