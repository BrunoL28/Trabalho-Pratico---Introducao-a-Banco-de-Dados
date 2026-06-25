"""
Pipeline de ingestão, orquestra extração, transformação e carga (ETL).

O ponto de entrada é ``run.py`` na raiz do projeto.

Estratégia de carga
-------------------
* **Dimensões** (``periodo``, ``instituicao``, ``municipio``): ``INSERT ...
  ON CONFLICT`` em lote (idempotente, reexecuções não duplicam).
* **Fatos**: ``DELETE`` dos períodos sendo ingeridos seguido de ``COPY``
  (protocolo nativo do PostgreSQL via ``copy_expert``), a forma mais
  eficiente de carga em massa, mais rápida que INSERTs
  linha a linha.
* Toda a carga roda em **uma única transação**: ou o mês entra completo,
  ou nada entra (atomicidade).
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

import pandas as pd
from psycopg2.extras import execute_values
from sqlalchemy import text

from src import extract, transform
from src.config import criar_engine

logger = logging.getLogger(__name__)

RAIZ_PROJETO = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Utilitários de carga
# ---------------------------------------------------------------------------

def _copy_dataframe(cursor, df: pd.DataFrame, tabela: str, colunas: list[str]) -> None:
    """Carga em massa via COPY: serializa o DataFrame como CSV em memória."""
    buffer = io.StringIO()
    df[colunas].to_csv(buffer, index=False, header=False)
    buffer.seek(0)
    cursor.copy_expert(
        f"COPY {tabela} ({', '.join(colunas)}) FROM STDIN WITH (FORMAT csv)",
        buffer,
    )
    logger.info("%s: %d linha(s) carregada(s) via COPY", tabela, len(df))


def _garantir_periodos(cursor, meses: list[tuple[int, int]]) -> dict[int, int]:
    """Insere os períodos (se ausentes) e retorna o mapa AAAAMM -> id_periodo."""
    execute_values(
        cursor,
        "INSERT INTO periodo (ano, mes) VALUES %s ON CONFLICT (ano, mes) DO NOTHING",
        meses,
    )
    cursor.execute("SELECT ano, mes, id_periodo FROM periodo")
    return {ano * 100 + mes: id_ for ano, mes, id_ in cursor.fetchall()}


def _upsert_instituicoes(cursor, df: pd.DataFrame) -> None:
    execute_values(
        cursor,
        """
        INSERT INTO instituicao (ispb, nome) VALUES %s
        ON CONFLICT (ispb) DO UPDATE SET nome = EXCLUDED.nome
        """,
        list(df[["ispb", "nome"]].itertuples(index=False, name=None)),
    )
    logger.info("instituicao: %d registro(s) upsertado(s)", len(df))


def _upsert_municipios(cursor, df: pd.DataFrame) -> None:
    execute_values(
        cursor,
        """
        INSERT INTO municipio (codigo_ibge, nome, codigo_ibge_estado) VALUES %s
        ON CONFLICT (codigo_ibge) DO NOTHING
        """,
        list(df[["codigo_ibge", "nome", "codigo_ibge_estado"]].itertuples(index=False, name=None)),
    )
    logger.info("municipio: %d registro(s) processado(s)", len(df))


def _recarregar_fato(cursor, df: pd.DataFrame, tabela: str, colunas: list[str],
                     ids_periodo: list[int]) -> None:
    """Apaga os períodos em recarga e insere os novos dados via COPY."""
    cursor.execute(f"DELETE FROM {tabela} WHERE id_periodo = ANY(%s)", (ids_periodo,))
    _copy_dataframe(cursor, df, tabela, colunas)


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------

def _listar_meses(inicio: str, fim: str) -> list[tuple[int, int]]:
    """Expande o intervalo AAAA-MM .. AAAA-MM em pares (ano, mes)."""
    datas = pd.period_range(start=inicio, end=fim, freq="M")
    if len(datas) == 0:
        raise ValueError(f"Intervalo vazio: --inicio {inicio} > --fim {fim}")
    return [(p.year, p.month) for p in datas]


def executar(inicio: str, fim: str, recriar_schema: bool = False) -> None:
    """Executa o pipeline completo para a janela [inicio, fim]."""
    meses = _listar_meses(inicio, fim)
    engine = criar_engine()

    if recriar_schema:
        logger.info("Aplicando sql/schema.sql ...")
        ddl = (RAIZ_PROJETO / "sql" / "schema.sql").read_text(encoding="utf-8")
        try:
            with engine.connect() as conexao:
                conexao.execute(text(ddl))
                conexao.commit()
        except Exception:
            logger.exception("Falha ao aplicar sql/schema.sql — abortando.")
            raise

    # ------------------------------ EXTRAÇÃO + TRANSFORMAÇÃO ----------------
    ano_mes_janela = {ano * 100 + mes for ano, mes in meses}

    bruto_fraudes = extract.extrair_fraudes()
    bruto_fraudes = bruto_fraudes[bruto_fraudes["AnoMes"].isin(ano_mes_janela)]
    fraudes = transform.transformar_fraudes(bruto_fraudes)

    frames_chaves, frames_inst, frames_trans, frames_mun = [], [], [], []
    for ano, mes in meses:
        logger.info("Processando competência %04d-%02d ...", ano, mes)
        chaves = transform.transformar_chaves(extract.extrair_chaves(ano, mes), ano, mes)
        frames_inst.append(chaves["instituicao"])
        frames_chaves.append(chaves["chave_pix_instituicao"])

        trans = transform.transformar_transacoes(extract.extrair_transacoes_municipio(ano, mes))
        frames_mun.append(trans["municipio"])
        frames_trans.append(trans["transacao_municipio"])

    instituicao = pd.concat(frames_inst).drop_duplicates(subset=["ispb"], keep="last")
    municipio = pd.concat(frames_mun).drop_duplicates(subset=["codigo_ibge"], keep="last")
    chave_pix = pd.concat(frames_chaves, ignore_index=True)
    transacao = pd.concat(frames_trans, ignore_index=True)

    # ------------------------------ CARGA (transação única) -----------------
    conexao_bruta = engine.raw_connection()
    try:
        with conexao_bruta.cursor() as cursor:
            mapa_periodo = _garantir_periodos(cursor, meses)

            _upsert_instituicoes(cursor, instituicao)
            _upsert_municipios(cursor, municipio)

            def _mapear_periodo(df: pd.DataFrame) -> pd.DataFrame:
                df = df.copy()
                df["id_periodo"] = df["ano_mes"].map(mapa_periodo)
                return df

            ids_janela = [mapa_periodo[am] for am in sorted(ano_mes_janela) if am in mapa_periodo]

            # Detalhamentos referenciam fraude_med: apagar filhos antes do pai.
            for tabela in ("devolucao_med", "nao_devolucao_med", "bloqueio_cautelar"):
                cursor.execute(f"DELETE FROM {tabela} WHERE id_periodo = ANY(%s)", (ids_janela,))

            _recarregar_fato(
                cursor, _mapear_periodo(fraudes["fraude_med"]), "fraude_med",
                ["id_periodo", "qtd_pix_contestados", "qtd_contestacoes_aceitas",
                 "qtd_contestacoes_rejeitadas", "taxa_aceitas_por_100mil",
                 "qtd_usuarios_marcados_fraude", "qtd_chaves_marcadas_fraude",
                 "valor_contestados_aceitos", "valor_residual_nao_devolvido",
                 "percentual_devolucao"],
                ids_janela,
            )
            _copy_dataframe(cursor, _mapear_periodo(fraudes["devolucao_med"]),
                            "devolucao_med", ["id_periodo", "tipo_devolucao", "quantidade", "valor"])
            _copy_dataframe(cursor, _mapear_periodo(fraudes["nao_devolucao_med"]),
                            "nao_devolucao_med", ["id_periodo", "motivo", "quantidade", "valor"])
            _copy_dataframe(cursor, _mapear_periodo(fraudes["bloqueio_cautelar"]),
                            "bloqueio_cautelar", ["id_periodo", "desfecho", "quantidade", "valor"])

            _recarregar_fato(
                cursor, _mapear_periodo(chave_pix), "chave_pix_instituicao",
                ["id_periodo", "ispb", "natureza_usuario", "tipo_chave", "qtd_chaves"],
                ids_janela,
            )
            _recarregar_fato(
                cursor, _mapear_periodo(transacao), "transacao_municipio",
                ["id_periodo", "codigo_ibge_municipio", "papel", "natureza",
                 "valor", "qtd_transacoes", "qtd_pessoas"],
                ids_janela,
            )

        conexao_bruta.commit()
        logger.info("Ingestão concluída com sucesso para %d competência(s).", len(meses))
    except Exception:
        conexao_bruta.rollback()
        logger.exception("Falha na carga — transação revertida (rollback).")
        raise
    finally:
        conexao_bruta.close()


