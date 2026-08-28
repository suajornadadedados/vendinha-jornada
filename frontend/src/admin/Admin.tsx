// A casca do painel: navegação, sino do HITL e o indicador de conexão.
//
// **Não há roteador.** A navegação é estado, e é deliberado: `admin.html` é uma
// entrada estática servida por caminho fixo, e um `BrowserRouter` exigiria reescrita
// no servidor para sobreviver a um F5 numa sub-rota. A métrica da spec é "jornada
// completa sem recarregar a página" — que este desenho satisfaz sem trazer a máquina
// que só serviria para URLs compartilháveis que ninguém pediu.
//
// **O indicador de conexão é o requisito difícil.** A verificação independente derruba
// o backend com a tela aberta: enquanto desconectado, o conteúdo esmaece e a barra
// diz desde quando o dado é velho, em vez de continuar apresentando o último estado
// conhecido como se fosse o atual.

import { useCallback, useEffect, useState } from "react";
import {
  Bell,
  ChartLineUp,
  ChatsCircle,
  Gear,
  Receipt,
  SealCheck,
  SquaresFour,
  WifiHigh,
  WifiSlash,
} from "@phosphor-icons/react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

import { useEventos } from "./dados";
import { Config, Conversas, Fila, Metricas, Pedidos, VisaoGeral } from "./Telas";
import { hora, reais } from "./formato";

const SECOES = [
  { id: "visao", nome: "Visão geral", icone: SquaresFour },
  { id: "conversas", nome: "Conversas", icone: ChatsCircle },
  { id: "fila", nome: "Aprovações", icone: SealCheck },
  { id: "pedidos", nome: "Pedidos", icone: Receipt },
  { id: "metricas", nome: "Métricas", icone: ChartLineUp },
  { id: "config", nome: "Configurações", icone: Gear },
] as const;

const JANELAS = ["24h", "7d", "30d"] as const;

export function Admin({ aoPerderAcesso }: { aoPerderAcesso: () => void }) {
  const [secao, setSecao] = useState<string>("visao");
  const [janela, setJanela] = useState<string>("24h");

  const perdeuAcesso = useCallback(() => {
    toast.error("O token do operador não foi aceito.");
    aoPerderAcesso();
  }, [aoPerderAcesso]);

  const painel = useEventos(perdeuAcesso);

  // O sino. Toast + badge, e não só badge: numa demo projetada, o número mudando no
  // canto passa despercebido, e o momento em que a nota entra na fila é o ponto
  // inteiro do fluxo de HITL.
  useEffect(() => {
    if (!painel.aviso) return;
    toast(`Nota aguardando decisão — ${painel.aviso.razaoSocial}`, {
      description: `${reais(painel.aviso.total)} · nenhuma nota sai sem uma pessoa aprovar`,
      action: { label: "Abrir a fila", onClick: () => setSecao("fila") },
    });
    painel.limparAviso();
  }, [painel]);

  const desconectado = painel.conexao === "desconectado";

  return (
    <div className="painel">
      <aside className="painel__lado">
        <div className="painel__marca">
          <span className="painel__marca-nome">Vendinha</span>
          <span className="painel__marca-cauda mono">painel</span>
        </div>
        <nav aria-label="Seções do painel">
          {SECOES.map(({ id, nome, icone: Icone }) => (
            <button
              key={id}
              onClick={() => setSecao(id)}
              data-ativa={id === secao ? "" : undefined}
              aria-current={id === secao ? "page" : undefined}
            >
              <Icone size={18} weight="regular" aria-hidden="true" />
              {nome}
              {id === "fila" && painel.pendentes > 0 && (
                <Badge className="ml-auto">{painel.pendentes}</Badge>
              )}
            </button>
          ))}
        </nav>
        <p className="painel__nota">
          Sem autenticação: o token vale só para esta aba. Não publique este painel.
        </p>
      </aside>

      <div className="painel__conteudo">
        <header className="painel__topo">
          <h1>{SECOES.find((s) => s.id === secao)?.nome}</h1>

          <div className="painel__ferramentas">
            {(secao === "visao" || secao === "metricas") && (
              <div className="janelas" role="group" aria-label="Janela temporal">
                {JANELAS.map((opcao) => (
                  <button
                    key={opcao}
                    onClick={() => setJanela(opcao)}
                    data-ativa={opcao === janela ? "" : undefined}
                  >
                    {opcao}
                  </button>
                ))}
              </div>
            )}

            <span
              className={`conexao ${desconectado ? "conexao--fora" : "conexao--dentro"}`}
              role="status"
            >
              {desconectado ? (
                <WifiSlash size={14} weight="regular" aria-hidden="true" />
              ) : (
                <WifiHigh size={14} weight="regular" aria-hidden="true" />
              )}
              {desconectado
                ? painel.ultimoEvento
                  ? `desconectado — dados de ${hora(painel.ultimoEvento.toISOString())}`
                  : "desconectado"
                : painel.conexao === "conectando"
                  ? "conectando"
                  : "ao vivo"}
            </span>

            {painel.pendentes > 0 && (
              <button className="sino" onClick={() => setSecao("fila")} aria-label="Ir para a fila">
                <Bell size={18} weight="fill" aria-hidden="true" />
                <span className="sino__badge">{painel.pendentes}</span>
              </button>
            )}
          </div>
        </header>

        {painel.perdidos > 0 && (
          <div className="atraso" role="alert">
            Perdi {painel.perdidos} atualizaç{painel.perdidos > 1 ? "ões" : "ão"} enquanto esta
            aba estava ocupada — o que está na tela pode estar furado.
            <Button size="sm" variant="outline" onClick={() => window.location.reload()}>
              Recarregar
            </Button>
          </div>
        )}

        {/* Esmaecer é a diferença entre "número velho apresentado como atual" e
            "número velho rotulado como velho". A barra acima diz desde quando. */}
        <main className={`painel__main ${desconectado ? "painel__main--velho" : ""}`}>
          {secao === "visao" && <VisaoGeral janela={janela} irPara={setSecao} />}
          {secao === "conversas" && <Conversas />}
          {secao === "fila" && <Fila />}
          {secao === "pedidos" && <Pedidos />}
          {secao === "metricas" && <Metricas janela={janela} />}
          {secao === "config" && <Config />}
        </main>
      </div>
    </div>
  );
}
