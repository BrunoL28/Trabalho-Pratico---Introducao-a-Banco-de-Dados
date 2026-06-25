"""
Análise Exploratória de Dados (EDA), fraudes PIX / MED.

Consome exclusivamente a camada de acesso (:class:`PixFraudDataAccessor`),
gera as visualizações em ``notebooks/figuras/`` e imprime no console as
estatísticas que fundamentam os insights de negócio.

Uso:
    python -m src.eda
"""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns

from src.data_accessor import PixFraudDataAccessor

logger = logging.getLogger(__name__)

DIR_FIGURAS = Path(__file__).resolve().parent.parent / "notebooks" / "figuras"

sns.set_theme(style="whitegrid", palette="deep")
plt.rcParams.update({"figure.dpi": 120, "axes.titlesize": 12, "axes.titleweight": "bold"})


def _fmt_milhoes(valor, _pos) -> str:
    return f"R$ {valor / 1e6:,.0f} mi".replace(",", ".")


def _fmt_bilhoes(valor, _pos) -> str:
    return f"R$ {valor / 1e9:,.1f} bi".replace(",", ".")


def _salvar(fig: plt.Figure, nome: str) -> None:
    destino = DIR_FIGURAS / nome
    fig.tight_layout()
    fig.savefig(destino, bbox_inches="tight")
    plt.close(fig)
    logger.info("Figura gerada: %s", destino)


# ---------------------------------------------------------------------------
# Visualizações — uma função por pergunta de negócio
# ---------------------------------------------------------------------------

def grafico_evolucao_contestacoes(dao: PixFraudDataAccessor) -> None:
    """P1: Como evoluem as contestações de fraude e quanto delas é acatado?"""
    df = dao.evolucao_mensal_med()

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)

    ax1.plot(df["data_competencia"], df["qtd_pix_contestados"] / 1e6,
             marker="o", label="PIX contestados")
    ax1.plot(df["data_competencia"], df["qtd_contestacoes_aceitas"] / 1e6,
             marker="s", label="Contestações aceitas")
    ax1.set_title("Evolução mensal das contestações de fraude no PIX (MED)")
    ax1.set_ylabel("Milhões de transações")
    ax1.legend()

    ax2.bar(df["data_competencia"], df["valor_contestados_aceitos"], width=20,
            color=sns.color_palette()[2], label="Valor contestado aceito")
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(_fmt_milhoes))
    ax2.set_ylabel("Valor mensal")
    ax2.set_xlabel("Competência")
    ax2.legend()

    _salvar(fig, "01_evolucao_contestacoes.png")

    taxa_aceite = 100 * df["qtd_contestacoes_aceitas"].sum() / df["qtd_pix_contestados"].sum()
    print(f"[P1] Contestados no biênio: {df['qtd_pix_contestados'].sum():,.0f} | "
          f"taxa média de aceite: {taxa_aceite:.1f}% | "
          f"valor aceito total: R$ {df['valor_contestados_aceitos'].sum() / 1e9:.2f} bi")


def grafico_taxa_contestacao(dao: PixFraudDataAccessor) -> None:
    """P2: A fraude cresce mais rápido que o próprio uso do PIX?"""
    df = dao.contestacoes_vs_volume_nacional()

    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(df["data_competencia"], df["contestados_por_100mil"],
            marker="o", color=sns.color_palette()[3])
    ax.set_title("PIX contestados a cada 100 mil transações enviadas")
    ax.set_ylabel("Contestações / 100 mil transações")
    ax.set_xlabel("Competência")

    _salvar(fig, "02_taxa_contestacao.png")

    print(f"[P2] Taxa de contestação: início {df['contestados_por_100mil'].iloc[0]:.1f} | "
          f"pico {df['contestados_por_100mil'].max():.1f} | "
          f"fim {df['contestados_por_100mil'].iloc[-1]:.1f} por 100 mil")


def grafico_funil_devolucao(dao: PixFraudDataAccessor) -> None:
    """P3: Por que o dinheiro contestado não volta para a vítima?"""
    df = dao.nao_devolucao_por_motivo()
    ref_med = dao.evolucao_mensal_med()
    inicio = ref_med["data_competencia"].min().strftime("%Y-%m")
    fim    = ref_med["data_competencia"].max().strftime("%Y-%m")

    rotulos = {
        "SALDO_INSUFICIENTE": "Saldo insuficiente\nna conta do fraudador",
        "CONTA_ENCERRADA": "Conta encerrada",
        "OUTROS": "Motivos diversos",
    }

    fig, ax = plt.subplots(figsize=(9, 4.5))
    cores = sns.color_palette("flare", len(df))
    ax.barh([rotulos[m] for m in df["motivo"]], df["valor_total"], color=cores)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(_fmt_bilhoes))
    ax.invert_yaxis()
    ax.set_title(f"Valor NÃO recuperado pelo MED por motivo ({inicio} a {fim})")
    ax.set_xlabel("Valor acumulado")

    _salvar(fig, "03_funil_nao_devolucao.png")

    total = df["valor_total"].sum()
    lider = df.iloc[0]
    print(f"[P3] Não devolvido total: R$ {total / 1e9:.2f} bi | "
          f"{lider['motivo']} responde por {100 * lider['valor_total'] / total:.1f}%")


def grafico_volume_por_uf(dao: PixFraudDataAccessor, ano: int | None = None) -> None:
    """P4: Onde o dinheiro circula? Concentração regional do volume PIX."""
    todos = dao.volume_pix_por_uf(ano=ano)
    df = todos.head(10)

    ref_med = dao.evolucao_mensal_med()
    inicio = ref_med["data_competencia"].min().strftime("%Y-%m")
    fim    = ref_med["data_competencia"].max().strftime("%Y-%m")
    titulo_periodo = str(ano) if ano else f"{inicio} a {fim}"

    fig, ax = plt.subplots(figsize=(9, 5))
    sns.barplot(data=df, x="valor_total", y="sigla_uf", hue="regiao", ax=ax, dodge=False)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, p: f"R$ {v / 1e12:.1f} tri"))
    ax.set_title(f"Top 10 UFs por valor transacionado via PIX ({titulo_periodo})")
    ax.set_xlabel("Valor acumulado no período")
    ax.set_ylabel("UF")
    ax.legend(title="Região")

    _salvar(fig, "04_volume_por_uf.png")

    top3 = 100 * todos["valor_total"].head(3).sum() / todos["valor_total"].sum()
    print(f"[P4] {titulo_periodo}: top 3 UFs concentram {top3:.1f}% do valor transacionado")


def grafico_ranking_instituicoes(dao: PixFraudDataAccessor) -> None:
    """P5: Quais instituições mais expandem base de chaves (proxy de exposição)?"""
    df = dao.ranking_crescimento_chaves(top_n=1)

    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.bar(df["data_competencia"], df["crescimento_absoluto"] / 1e6, width=20,
           color=sns.color_palette()[0])
    for _, linha in df.iterrows():
        ax.annotate(linha["nome"].split()[0].title(),
                    (linha["data_competencia"], linha["crescimento_absoluto"] / 1e6),
                    rotation=90, fontsize=7, ha="center", va="bottom")
    ax.set_title("Líder mensal de crescimento da base de chaves PIX (window functions)")
    ax.set_ylabel("Novas chaves no mês (milhões)")
    ax.set_xlabel("Competência")

    _salvar(fig, "05_ranking_crescimento_chaves.png")

    extremo = df.loc[df["crescimento_pct"].idxmax()]
    print(f"[P5] Maior salto relativo: {extremo['nome']} em "
          f"{extremo['data_competencia']:%Y-%m} (+{extremo['crescimento_pct']:.0f}%)")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    DIR_FIGURAS.mkdir(parents=True, exist_ok=True)

    with PixFraudDataAccessor() as dao:
        grafico_evolucao_contestacoes(dao)
        grafico_taxa_contestacao(dao)
        grafico_funil_devolucao(dao)
        grafico_volume_por_uf(dao)
        grafico_ranking_instituicoes(dao)

    logger.info("EDA concluída — figuras em %s", DIR_FIGURAS)


if __name__ == "__main__":
    main()
