# A imagem do frontend: build dos estáticos, e o nginx que os serve e faz proxy
# da API. Contexto de build: a RAIZ do repositório.
#
# **`VITE_API_BASE_URL` é build time, e isso não é detalhe de empacotamento.**
# `frontend/src/api/base.ts` lê `import.meta.env["VITE_API_BASE_URL"]`, que o
# Vite substitui estaticamente: o valor fica literalmente dentro do bundle. Não
# existe configuração de runtime no frontend — nada de `window.__CONFIG__`, nada
# de `env.js`. Passar essa variável no `docker run` não teria efeito nenhum, e o
# sintoma seria o painel chamando `http://localhost:8000` da máquina de QUEM
# ABRIU a página.
#
# O default é `/api` porque tudo é servido pela mesma origem — ver `nginx.conf`
# para por que o prefixo existe.

FROM node:22-slim AS builder

WORKDIR /app/frontend

# `npm ci` e não `npm install`: instala exatamente o `package-lock.json`, e falha
# se ele divergir do `package.json` em vez de "consertar" o lockfile sozinho
# durante um build de deploy.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./

ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

# `npm run build` é `tsc -b && vite build`: um erro de tipo derruba o build da
# imagem, e é para derrubar.
#
# Produz DUAS entradas (`vite.config.ts`): `index.html` (a landing pública) e
# `admin.html` (o painel). Um build que perdesse a segunda entregaria um painel
# que responde 404 só em produção — e a landing continuaria funcionando, que é o
# que faz esse erro passar despercebido.
RUN npm run build && test -f dist/index.html && test -f dist/admin.html

# ─────────────────────────────────────────────────────────────────────────────

# `nginx-unprivileged`, e não o `nginx` oficial: neste o processo master roda
# como root e só os workers descem de usuário. RNF-9 pede container non-root, e
# a imagem unprivileged é a que cumpre isso de verdade — ela escuta em 8080,
# porque uma porta abaixo de 1024 exigiria justamente o privilégio que estamos
# tirando.
FROM nginxinc/nginx-unprivileged:1.29-alpine AS runtime

COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/frontend/dist /usr/share/nginx/html

EXPOSE 8080
