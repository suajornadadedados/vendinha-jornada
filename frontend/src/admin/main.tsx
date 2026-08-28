import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "../estilo/tokens.css";

const raiz = document.getElementById("raiz");
if (!raiz) throw new Error("elemento #raiz nao encontrado");

createRoot(raiz).render(
  <StrictMode>
    <p>O painel chega no commit 15.</p>
  </StrictMode>,
);
