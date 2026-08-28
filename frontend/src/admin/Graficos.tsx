// Três gráficos, em SVG inline e sem biblioteca.
//
// **Nenhum tem mais de uma série**, e é por isso que não há paleta categórica aqui:
// o bullet mede um valor contra um alvo, a linha é uma série, e as recusas têm a
// categoria **no eixo**. Pintar cada barra de uma cor codificaria com cor o que o
// rótulo já diz. A paleta de marca, aliás, reprovou no validador da `dataviz` como
// escala categórica — e a resposta certa foi não precisar de uma
// (`docs/design/sistema-visual.md`).
//
// Regras que a skill fixa e que estão implementadas abaixo: marcas finas, pontas
// arredondadas de 4px ancoradas na linha de base, eixos recessivos, rótulo direto em
// vez de número em todo ponto, e **valor ausente é traço, nunca zero desenhado**.

import { Ausente, inteiro, milissegundos } from "./formato";

/**
 * Bullet chart: um valor contra um alvo. O p95 do primeiro token contra os 3s do
 * RNF-4.
 *
 * O alvo é uma **marca no eixo**, não uma faixa colorida de fundo: a pergunta é
 * "passou da linha?", e a linha precisa ser uma linha. A cor da barra muda com o
 * veredito, mas o texto ao lado diz o mesmo — a skill proíbe cor sozinha.
 */
export function Bullet({
  valor,
  alvo,
  rotulo,
}: {
  valor: number | null | undefined;
  alvo: number;
  rotulo: string;
}) {
  if (valor === null || valor === undefined) {
    return (
      <div className="grafico">
        <p className="rotulo">{rotulo}</p>
        <p className="grafico__vazio">
          <Ausente porque="nenhum turno com primeiro token medido nesta janela" /> sem amostra
          nesta janela
        </p>
      </div>
    );
  }

  const dentro = valor <= alvo;
  const escala = Math.max(valor, alvo) * 1.25;
  const largura = (valor / escala) * 100;
  const posicaoDoAlvo = (alvo / escala) * 100;

  return (
    <div className="grafico">
      <div className="grafico__topo">
        <p className="rotulo">{rotulo}</p>
        <p className={`grafico__valor num ${dentro ? "grafico__valor--ok" : "grafico__valor--fora"}`}>
          {milissegundos(valor)}
        </p>
      </div>
      <svg
        viewBox="0 0 100 12"
        preserveAspectRatio="none"
        className="grafico__bullet"
        role="img"
        aria-label={`${rotulo}: ${milissegundos(valor)}, alvo ${milissegundos(alvo)}, ${
          dentro ? "dentro do alvo" : "acima do alvo"
        }`}
      >
        <rect x="0" y="3" width="100" height="6" rx="3" fill="var(--linha)" />
        <rect
          x="0"
          y="3"
          width={Math.min(largura, 100)}
          height="6"
          rx="3"
          fill={dentro ? "var(--verde)" : "var(--vermelho)"}
        />
        {/* A marca do alvo por cima, com um anel da superfície para não colar na
            barra quando os dois quase coincidem. */}
        <rect x={posicaoDoAlvo - 0.5} y="0.5" width="1" height="11" fill="var(--papel)" />
        <rect x={posicaoDoAlvo - 0.25} y="1" width="0.5" height="10" fill="var(--tinta)" />
      </svg>
      <p className="grafico__nota">
        alvo {milissegundos(alvo)} · {dentro ? "dentro" : "acima"} — RNF-4
      </p>
    </div>
  );
}

/**
 * Barras horizontais ordenadas. Recusas do validador por motivo.
 *
 * É a regra de ouro virando gráfico: cada barra é uma vez em que o modelo propôs e o
 * código recusou. Uma cor só — a categoria está no rótulo à esquerda.
 */
export function BarrasOrdenadas({
  dados,
  rotulo,
  vazio,
}: {
  dados: readonly { readonly chave: string; readonly valor: number }[];
  rotulo: string;
  vazio: string;
}) {
  if (dados.length === 0) {
    return (
      <div className="grafico">
        <p className="rotulo">{rotulo}</p>
        <p className="grafico__vazio">{vazio}</p>
      </div>
    );
  }

  const maior = Math.max(...dados.map((d) => d.valor));

  return (
    <div className="grafico">
      <p className="rotulo">{rotulo}</p>
      <ul className="barras">
        {dados.map((linha) => (
          <li key={linha.chave}>
            <span className="barras__nome">{linha.chave}</span>
            <span className="barras__trilho">
              <span
                className="barras__preenchimento"
                style={{ width: `${Math.max((linha.valor / maior) * 100, 2)}%` }}
              />
            </span>
            <span className="barras__valor num">{inteiro(linha.valor)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Linha: uma série ao longo do tempo.
 *
 * Menos de quatro pontos não vira gráfico — vira cartão de número, como a ficha da
 * `ui-ux-pro-max` manda. A tela chama isto só quando tem série.
 */
export function Linha({
  pontos,
  rotulo,
  formatar,
}: {
  pontos: readonly { readonly quando: string; readonly valor: number }[];
  rotulo: string;
  formatar: (valor: number) => string;
}) {
  if (pontos.length < 4) {
    return (
      <div className="grafico">
        <p className="rotulo">{rotulo}</p>
        <p className="grafico__vazio">
          {pontos.length === 0
            ? "sem dados nesta janela"
            : "poucos pontos para uma tendência — veja o número acima"}
        </p>
      </div>
    );
  }

  const maior = Math.max(...pontos.map((p) => p.valor), 0.000001);
  const passo = 100 / (pontos.length - 1);
  const caminho = pontos
    .map((ponto, indice) => {
      const x = indice * passo;
      const y = 30 - (ponto.valor / maior) * 26;
      return `${indice === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  const ultimo = pontos[pontos.length - 1];

  return (
    <div className="grafico">
      <div className="grafico__topo">
        <p className="rotulo">{rotulo}</p>
        {ultimo && <p className="grafico__valor num">{formatar(ultimo.valor)}</p>}
      </div>
      <svg
        viewBox="0 0 100 32"
        preserveAspectRatio="none"
        className="grafico__linha"
        role="img"
        aria-label={`${rotulo}: ${pontos.length} pontos, último ${
          ultimo ? formatar(ultimo.valor) : "—"
        }`}
      >
        <path d={caminho} fill="none" stroke="var(--verde)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
      </svg>
      <p className="grafico__nota">
        {pontos[0]?.quando} — {ultimo?.quando}
      </p>
    </div>
  );
}
