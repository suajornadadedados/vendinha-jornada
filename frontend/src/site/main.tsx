import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "../estilo/tokens.css";
import "./site.css";
import { Site } from "./Site";

const raiz = document.getElementById("raiz");
if (!raiz) throw new Error("elemento #raiz nao encontrado");

createRoot(raiz).render(
  <StrictMode>
    <Site />
  </StrictMode>,
);
