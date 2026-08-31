// A tela de conexão — o mais perto de "login" que um painel sem autenticação chega.
//
// A S-07 não entrega autenticação (fora de escopo, e dito em voz alta no ADR-015).
// O que ela entrega é honestidade sobre isso: o operador cola o `OPERADOR_API_TOKEN`,
// ele fica em `sessionStorage` — fechar a aba esquece —, e qualquer 401 traz esta
// tela de volta em vez de deixar o painel em branco com um erro no console.

import { useState } from "react";
import { Key, Warning } from "@phosphor-icons/react";

import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

import { guardarToken } from "../api/client";

export function Conectar({ aoConectar }: { aoConectar: () => void }) {
  const [token, setToken] = useState("");

  const entrar = (evento: React.FormEvent) => {
    evento.preventDefault();
    if (!token.trim()) return;
    guardarToken(token.trim());
    aoConectar();
  };

  return (
    <div className="conectar">
      <form className="conectar__caixa" onSubmit={entrar}>
        <div className="conectar__marca">
          <span className="conectar__nome">Vendinha</span>
          <span className="mono conectar__cauda">painel do operador</span>
        </div>

        <label htmlFor="token" className="rotulo">
          Token do operador
        </label>
        <div className="conectar__campo">
          <Key size={18} weight="regular" aria-hidden="true" />
          <input
            id="token"
            type="password"
            className="campo"
            value={token}
            onChange={(evento) => setToken(evento.target.value)}
            placeholder="OPERADOR_API_TOKEN"
            autoComplete="off"
            autoFocus
          />
        </div>

        <Button type="submit" disabled={!token.trim()}>
          Conectar
        </Button>

        <Alert>
          <Warning />
          <AlertTitle>Este painel não tem autenticação</AlertTitle>
          <AlertDescription>
            O token é o mesmo <span className="mono">OPERADOR_API_TOKEN</span> do{" "}
            <span className="mono">.env</span>, e vale só para esta aba. É aceitável numa demo
            local e não é aceitável num host público.
          </AlertDescription>
        </Alert>
      </form>
    </div>
  );
}
