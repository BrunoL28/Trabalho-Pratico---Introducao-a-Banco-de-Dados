"""
Camada de acesso a dados, padrão Data Accessor (DAO).

Toda a interação do projeto com o PostgreSQL acontece exclusivamente por meio
da classe :class:`PixFraudDataAccessor`, que:

* encapsula a string de conexão e o ciclo de vida da Engine/conexões;
* expõe métodos Python, um por pergunta de negócio, devolvendo sempre
  ``pandas.DataFrame`` prontos para análise;
* carrega as queries SQL de arquivos dedicados em ``queries/``, mantendo
  Python e SQL em camadas separadas;
* usa exclusivamente consultas parametrizadas (bind parameters), nunca
  interpolação de strings, eliminando risco de SQL injection.

Uso típico::

    with PixFraudDataAccessor() as dao:
        df = dao.volume_pix_por_uf(ano=2025)
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.config import criar_engine

_QUERIES_DIR = Path(__file__).resolve().parent.parent / "queries"


class PixFraudDataAccessor:
    """DAO único do projeto: consultas analíticas sobre fraudes PIX/MED."""

    def __init__(self, engine: Engine | None = None) -> None:
        """Aceita uma Engine externa (testes) ou cria a partir da configuração."""
        self._engine = engine if engine is not None else criar_engine()

    # ------------------------------------------------------------------ infra
    def __enter__(self) -> "PixFraudDataAccessor":
        return self

    def __exit__(self, *exc) -> None:
        self.fechar()

    def fechar(self) -> None:
        """Devolve todas as conexões do pool ao SGBD."""
        self._engine.dispose()

    @staticmethod
    def _carregar_sql(nome_arquivo: str) -> str:
        """Lê o conteúdo de um arquivo SQL em queries/."""
        return (_QUERIES_DIR / nome_arquivo).read_text(encoding="utf-8")

    def _consultar(self, sql: str, **parametros) -> pd.DataFrame:
        """Executa SQL parametrizado em conexão própria (abre, usa e devolve)."""
        with self._engine.connect() as conexao:
            return pd.read_sql(text(sql), conexao, params=parametros)

    # ------------------------------------------------- 1. WHERE + projeção
    def buscar_instituicoes(self, termo: str) -> pd.DataFrame:
        """Localiza instituições participantes do PIX pelo nome (busca parcial).

        Consulta de projeção simples com filtro ``WHERE ... ILIKE``.
        """
        return self._consultar(
            self._carregar_sql("buscar_instituicoes.sql"),
            padrao=f"%{termo}%",
        )

    # ------------------------------- 2. Agregação + GROUP BY + HAVING
    def volume_pix_por_uf(self, ano: int | None = None, valor_minimo: float = 0.0) -> pd.DataFrame:
        """Volume transacionado via PIX por UF, com corte de relevância.

        Agregações ``SUM``/``COUNT`` agrupadas por UF/região; o ``HAVING``
        descarta UFs abaixo de ``valor_minimo`` (em R$).

        Parameters
        ----------
        ano:
            Ano de referência. ``None`` agrega o período completo disponível.
        """
        return self._consultar(
            self._carregar_sql("volume_pix_por_uf.sql"),
            ano=ano,
            valor_minimo=valor_minimo,
        )

    # --------------------------------------------- 3. JOIN estrutural
    def evolucao_mensal_med(self) -> pd.DataFrame:
        """Série mensal do MED: contestações, valores e devoluções por tipo.

        ``JOIN`` estrutural entre ``periodo``, ``fraude_med`` e
        ``devolucao_med`` (pivotada por tipo com ``FILTER``).
        """
        return self._consultar(self._carregar_sql("evolucao_mensal_med.sql"))

    # ------------------------------ 4. Window functions + subquery
    def ranking_crescimento_chaves(self, top_n: int = 10) -> pd.DataFrame:
        """Instituições com maior crescimento mensal da base de chaves PIX.

        Consulta analítica em três níveis: CTE de consolidação mensal por
        instituição; ``LAG()`` (window function particionada por instituição)
        para obter o mês anterior; ``RANK()`` por crescimento absoluto dentro
        de cada mês, com subconsulta final cortando o top N.

        O crescimento da base de chaves é usado como *proxy* de exposição a
        fraude, já que o dataset MED do BCB não abre fraude por instituição.
        """
        return self._consultar(
            self._carregar_sql("ranking_crescimento_chaves.sql"),
            top_n=top_n,
        )

    # ----------------------------------------- Apoio à EDA (Fase 5)
    def nao_devolucao_por_motivo(self) -> pd.DataFrame:
        """Quanto o MED deixa de recuperar, consolidado por motivo da falha."""
        return self._consultar(self._carregar_sql("nao_devolucao_por_motivo.sql"))

    def contestacoes_vs_volume_nacional(self) -> pd.DataFrame:
        """Taxa de contestação: PIX contestados a cada 100 mil transações.

        Subconsulta agregando o volume nacional (a partir do recorte
        municipal) confrontada com o consolidado mensal do MED.
        """
        return self._consultar(self._carregar_sql("contestacoes_vs_volume_nacional.sql"))
