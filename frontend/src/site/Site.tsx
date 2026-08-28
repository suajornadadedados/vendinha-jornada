// A landing pública da Vendinha.
//
// **O que ela é: o simulador do canal do cliente.** Não é produto — é a página onde
// alguém abre o atendimento e a demo começa. Por isso ela é honesta sobre o que
// existe: os quatro tipos de evento são os que o validador conhece
// (`composicao.TipoDeEvento`), os produtores e as regiões são os do catálogo real em
// `data/catalogo/`, e não há um único número inventado de "clientes atendidos".
//
// A estrutura é a do pattern *Trust & Authority + Conversion* que a `ui-ux-pro-max`
// devolveu: hero de credibilidade → prova → visão da solução → caminho de ação. O
// que mudou foi a paleta: a skill sugeriu navy e azul de SaaS, e a decisão foi manter
// a paleta terrosa do repositório (`docs/design/sistema-visual.md`).

import { Widget } from "./Widget";

const EVENTOS = [
  {
    nome: "Café da manhã",
    descricao:
      "Café de uma região só, pão de queijo, requeijão de corte e doce. Chega montado e pronto para a copa servir.",
    itens: "café · quitanda · laticínio · doce",
  },
  {
    nome: "Happy hour",
    descricao:
      "Queijo curado, torresmo, biscoito de polvilho e cachaça de alambique. Para confraternização e recepção de cliente.",
    itens: "queijo · petisco · destilado",
  },
  {
    nome: "Cesta de fim de ano",
    descricao:
      "A composição que vai para a casa de cada pessoa do time, com a variação que você precisar — sem álcool, sem glúten, sem lactose.",
    itens: "queijo · doce · café · petisco",
  },
  {
    nome: "Kit de boas-vindas",
    descricao:
      "O que a pessoa nova recebe no primeiro dia. Pequeno, bonito e da mesma qualidade do resto.",
    itens: "café · doce · quitanda",
  },
] as const;

const PRODUTORES = [
  { nome: "Sítio Boa Vista", regiao: "Serra da Canastra", faz: "Queijo Canastra, meia-cura a 120 dias" },
  { nome: "Fazenda Vereda Grande", regiao: "Cerrado Mineiro", faz: "Café de torra média e clara" },
  { nome: "Doceria Vovó Zulmira", regiao: "Zona da Mata", faz: "Doce de leite, goiabada cascão" },
  { nome: "Alambique Boca da Mata", regiao: "Salinas", faz: "Cachaça de amburana e de carvalho" },
  { nome: "Casa de Carnes Serra Verde", regiao: "Sul de Minas", faz: "Torresmo de rolo" },
  { nome: "Quitandas da Serra", regiao: "Belo Horizonte", faz: "Pão de queijo congelado" },
] as const;

const PASSOS = [
  {
    numero: "01",
    titulo: "Você diz o evento",
    texto:
      "Quantas pessoas, que ocasião, quanto por pessoa e o que não pode ter. Em português, pelo WhatsApp.",
  },
  {
    numero: "02",
    titulo: "A gente monta e confere",
    texto:
      "A composição vem com item, quantidade, total e valor por pessoa. Se estourar o orçamento ou faltar um item obrigatório, você fica sabendo antes de fechar — não depois.",
  },
  {
    numero: "03",
    titulo: "Pagamento e nota",
    texto:
      "Link de pagamento e NF-e para o CNPJ da sua empresa, com DANFE e XML. A emissão passa por uma pessoa nossa antes de sair.",
  },
] as const;

export function Site() {
  return (
    <>
      <a className="pular" href="#conteudo">
        Pular para o conteúdo
      </a>

      <header className="topo">
        <div className="faixa topo__faixa">
          <a className="marca" href="/" aria-label="Vendinha, página inicial">
            <span className="marca__nome">Vendinha</span>
            <span className="marca__cauda">empório mineiro</span>
          </a>
          <nav aria-label="Principal">
            <a href="#eventos">Eventos</a>
            <a href="#produtores">Produtores</a>
            <a href="#como-funciona">Como funciona</a>
          </nav>
        </div>
      </header>

      <main id="conteudo">
        <section className="heroi">
          <div className="faixa heroi__faixa">
            <p className="rotulo">Para empresas · Minas Gerais</p>
            <h1>
              O café da manhã da sua equipe vem da <em>Serra da Canastra</em>.
            </h1>
            <p className="heroi__linha">
              Montamos composições para eventos corporativos com queijo, café, doce, petisco e
              cachaça de produtores mineiros. Você diz o orçamento por pessoa; a gente respeita.
            </p>
            <p className="heroi__nota">
              Nota fiscal para PJ, entrega em todo o Brasil, e a composição conferida item a item
              antes de você aprovar.
            </p>
          </div>
        </section>

        <section className="prova" aria-label="O que sustenta a proposta">
          <div className="faixa prova__grade">
            <div>
              <p className="prova__valor">65</p>
              <p className="prova__texto">produtos no catálogo, de 6 produtores</p>
            </div>
            <div>
              <p className="prova__valor">4</p>
              <p className="prova__texto">tipos de evento montados</p>
            </div>
            <div>
              <p className="prova__valor">NF-e</p>
              <p className="prova__texto">para CNPJ, com DANFE e XML</p>
            </div>
            <div>
              <p className="prova__valor">0</p>
              <p className="prova__texto">composições fora do orçamento apresentadas</p>
            </div>
          </div>
        </section>

        <section id="eventos" className="secao">
          <div className="faixa">
            <p className="rotulo">O que montamos</p>
            <h2>Quatro formatos, e o seu orçamento manda em todos.</h2>
            <div className="cartoes">
              {EVENTOS.map((evento) => (
                <article key={evento.nome} className="cartao">
                  <h3>{evento.nome}</h3>
                  <p>{evento.descricao}</p>
                  <p className="cartao__itens mono">{evento.itens}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section id="produtores" className="secao secao--papel">
          <div className="faixa">
            <p className="rotulo">De quem vem</p>
            <h2>Seis produtores, e cada item diz de onde veio.</h2>
            <p className="secao__linha">
              Nada aqui é marca própria de indústria. O queijo tem a fazenda, o café tem a região e
              a cachaça tem o alambique — porque é isso que faz uma cesta corporativa valer o que
              custa.
            </p>
            <ul className="produtores">
              {PRODUTORES.map((produtor) => (
                <li key={produtor.nome}>
                  <p className="produtores__nome">{produtor.nome}</p>
                  <p className="produtores__regiao mono">{produtor.regiao}</p>
                  <p className="produtores__faz">{produtor.faz}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section id="como-funciona" className="secao">
          <div className="faixa">
            <p className="rotulo">Como funciona</p>
            <h2>Três passos, e o segundo é o que importa.</h2>
            <ol className="passos">
              {PASSOS.map((passo) => (
                <li key={passo.numero}>
                  <span className="passos__numero mono">{passo.numero}</span>
                  <div>
                    <h3>{passo.titulo}</h3>
                    <p>{passo.texto}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="chamada">
          <div className="faixa chamada__faixa">
            <h2>Conte o evento e receba a composição.</h2>
            <p>
              O atendimento fica no canto da tela. Responde na hora, e você não precisa criar conta
              para conversar.
            </p>
          </div>
        </section>
      </main>

      <footer className="rodape">
        <div className="faixa rodape__faixa">
          <p>
            <strong>Vendinha</strong> — empório mineiro digital. Vendas para empresas.
          </p>
          <p className="rodape__nota">
            Ambiente de demonstração: pagamentos em sandbox e notas fiscais sem valor fiscal.
          </p>
        </div>
      </footer>

      <Widget />
    </>
  );
}
