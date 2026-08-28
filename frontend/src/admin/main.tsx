import { StrictMode, useCallback, useState } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

// A ordem importa: os tokens da marca definem as variáveis que o tema do shadcn
// consome em `tailwind.css`. Invertida, os componentes nasceriam sem cor.
import "../estilo/tokens.css";
import "../estilo/tailwind.css";
import "./admin.css";
import { Admin } from "./Admin";
import { Conectar } from "./Conectar";
import { tokenDoOperador } from "../api/client";

// Sem retry automático: um 401 não melhora na terceira tentativa, e um painel que
// tenta três vezes antes de pedir o token parece quebrado.
const cliente = new QueryClient({
  defaultOptions: { queries: { retry: false } },
});

function Raiz() {
  const [conectado, setConectado] = useState(() => tokenDoOperador() !== null);
  const desconectar = useCallback(() => setConectado(false), []);

  return (
    <QueryClientProvider client={cliente}>
      <TooltipProvider>
        {conectado ? (
          <Admin aoPerderAcesso={desconectar} />
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
