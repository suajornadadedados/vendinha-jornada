// A casca do painel: navegação, sino do HITL e o indicador de conexão.
//
// **A navegação é por rota.** A versão anterior guardava a seção em `useState` e
// argumentava que um roteador só serviria para URLs compartilháveis que ninguém
// tinha pedido. O PO pediu: cada seção do painel tem endereço próprio
// (`/admin`, `/admin/conversas`, `/admin/pedidos`, …), uma conversa aberta é um
// link que se manda para alguém, e o botão "voltar" do navegador faz o que a
// pessoa espera. O custo é a reescrita de `/admin/*` para `admin.html`, que está
// no `vite.config.ts` — em produção é a mesma linha no servidor de estáticos.
//
// **O indicador de conexão é o requisito difícil.** A verificação independente derruba
// o backend com a tela aberta: enquanto desconectado, o conteúdo esmaece e a barra
// diz desde quando o dado é velho, em vez de continuar apresentando o último estado
// conhecido como se fosse o atual.

import { useCallback, useEffect } from "react";
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
import { NavLink, Outlet, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

import { useEventos } from "./dados";
import { hora, reais } from "./formato";

const SECOES = [
  { rota: "/", nome: "Visão geral", icone: SquaresFour, fim: true },
  { rota: "/conversas", nome: "Conversas", icone: ChatsCircle, fim: false },
  { rota: "/aprovacoes", nome: "Aprovações", icone: SealCheck, fim: false },
  { rota: "/pedidos", nome: "Pedidos", icone: Receipt, fim: false },
  { rota: "/metricas", nome: "Métricas", icone: ChartLineUp, fim: false },
  { rota: "/configuracoes", nome: "Configurações", icone: Gear, fim: false },
] as const;

const JANELAS = [
  { id: "24h", nome: "24 h" },
  { id: "7d", nome: "7 dias" },
  { id: "30d", nome: "30 dias" },
] as const;

/** A janela vive na URL: `/admin/metricas?janela=7d` é um link que abre no mesmo lugar. */
export const JANELA_PADRAO = "24h";

export function useJanela(): [string, (valor: string) => void] {
  const [busca, setBusca] = useSearchParams();
  const atual = busca.get("janela") ?? JANELA_PADRAO;
  const trocar = (valor: string) => {
    const proxima = new URLSearchParams(busca);
    if (valor === JANELA_PADRAO) proxima.delete("janela");
    else proxima.set("janela", valor);
    setBusca(proxima, { replace: true });
  };
  return [atual, trocar];
}

export function Admin({ aoPerderAcesso }: { aoPerderAcesso: () => void }) {
  const navegar = useNavigate();
  const local = useLocation();
  const [janela, trocarJanela] = useJanela();

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
      action: { label: "Abrir a fila", onClick: () => navegar("/aprovacoes") },
    });
    painel.limparAviso();
  }, [painel, navegar]);

  const desconectado = painel.conexao === "desconectado";
  const secao = SECOES.find((s) =>
    s.fim ? local.pathname === "/" : local.pathname.startsWith(s.rota),
  );
  const comJanela = local.pathname === "/" || local.pathname.startsWith("/metricas");

  return (
    <div className="painel">
      <aside className="painel__lado">
        <div className="painel__marca">
          <span className="painel__marca-nome">Vendinha</span>
          <span className="painel__marca-cauda mono">painel</span>
        </div>
        <nav aria-label="Seções do painel">
          {SECOES.map(({ rota, nome, icone: Icone, fim }) => (
            <NavLink
              key={rota}
              to={rota}
              end={fim}
              className={({ isActive }) => (isActive ? "ativa" : undefined)}
            >
              <Icone size={18} weight="regular" aria-hidden="true" />
              {nome}
              {rota === "/aprovacoes" && painel.pendentes > 0 && (
                <Badge className="ml-auto">{painel.pendentes}</Badge>
              )}
            </NavLink>
          ))}
        </nav>
        <p className="painel__nota">
          Sem autenticação: o token vale só para esta aba. Não publique este painel.
        </p>
      </aside>

      <div className="painel__conteudo">
        <header className="painel__topo">
          <h1>{secao?.nome ?? "Painel"}</h1>

          <div className="painel__ferramentas">
            {comJanela && (
              <div className="janelas" role="group" aria-label="Período">
                {JANELAS.map((opcao) => (
                  <button
                    key={opcao.id}
                    onClick={() => trocarJanela(opcao.id)}
                    data-ativa={opcao.id === janela ? "" : undefined}
                  >
                    {opcao.nome}
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
              <button
                className="sino"
                onClick={() => navegar("/aprovacoes")}
                aria-label="Ir para as aprovações"
              >
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
          <Outlet />
        </main>
      </div>
    </div>
  );
}
