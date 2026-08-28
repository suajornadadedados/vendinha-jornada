import { StrictMode, useCallback, useState } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

// A ordem importa: os tokens da marca definem as variáveis que o tema do shadcn
// consome em `tailwind.css`. Invertida, os componentes nasceriam sem cor.
import "../estilo/tokens.css";
import "../estilo/tailwind.css";
import "./admin.css";
import { Admin } from "./Admin";
import { Conectar } from "./Conectar";
import { Config, Conversas, Fila, Metricas, Pedidos, VisaoGeral } from "./Telas";
import { tokenDoOperador } from "../api/client";

// Sem retry automático: um 401 não melhora na terceira tentativa, e um painel que
// tenta três vezes antes de pedir o token parece quebrado.
const cliente = new QueryClient({
  defaultOptions: { queries: { retry: false } },
});

/**
 * `basename="/admin"` porque a entrada do painel é servida sob esse caminho, e o
 * roteador precisa saber o que é prefixo do que é rota. O `vite.config.ts` faz a
 * outra metade: reescreve `/admin/qualquer-coisa` para `admin.html`, sem o que
 * um F5 numa sub-rota daria 404.
 */
function Raiz() {
  const [conectado, setConectado] = useState(() => tokenDoOperador() !== null);
  const desconectar = useCallback(() => setConectado(false), []);

  return (
    <QueryClientProvider client={cliente}>
      <TooltipProvider>
        {conectado ? (
          <BrowserRouter basename="/admin">
            <Routes>
              <Route element={<Admin aoPerderAcesso={desconectar} />}>
                <Route index element={<VisaoGeral />} />
                <Route path="conversas" element={<Conversas />} />
                <Route path="conversas/:sessionId" element={<Conversas />} />
                <Route path="aprovacoes" element={<Fila />} />
                <Route path="pedidos" element={<Pedidos />} />
                <Route path="metricas" element={<Metricas />} />
                <Route path="configuracoes" element={<Config />} />
                {/* Um caminho que não existe volta para a visão geral em vez de
                    pintar a área de conteúdo de branco sem dizer por quê. */}
                <Route path="*" element={<Navigate to="/" replace />} />
              </Route>
            </Routes>
          </BrowserRouter>
        ) : (
          <Conectar aoConectar={() => setConectado(true)} />
        )}
        <Toaster position="top-right" richColors closeButton />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

const raiz = document.getElementById("raiz");
if (!raiz) throw new Error("elemento #raiz nao encontrado");

createRoot(raiz).render(
  <StrictMode>
    <Raiz />
  </StrictMode>,
);
