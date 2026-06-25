"""
Camada de transformação, limpeza e normalização dos dados brutos da API.

Cada função recebe o DataFrame "cru" devolvido por ``src.extract`` e produz
DataFrames já no formato das tabelas físicas (``sql/schema.sql``), aplicando:

* tratamento de nulos (descarte em chaves, zero em medidas);
* padronização de strings (trim, colapso de espaços, categorias canônicas);
* conversão de tipos (inteiros anuláveis, decimais);
* deduplicação pelas chaves naturais;
* normalização estrutural: colunas "largas" do CSV viram linhas categorizadas
  (3FN), ex.: PF/PJ x Pagador/Recebedor em ``transacao_municipio``.
"""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)

# Mapeia os rótulos de tipo de chave da API para categorias canônicas.
_TIPO_CHAVE_CANONICO = {
    "CPF": "CPF",
    "CNPJ": "CNPJ",
    "Celular": "CELULAR",
    "e-mail": "EMAIL",
    "Aleatória": "ALEATORIA",
}


def _normalizar_texto(serie: pd.Series) -> pd.Series:
    """Trim + colapso de espaços internos múltiplos."""
    return serie.astype("string").str.strip().str.replace(r"\s+", " ", regex=True)


def _descartar_nulos_em_chave(df: pd.DataFrame, colunas: list[str], contexto: str) -> pd.DataFrame:
    """Remove (e loga) linhas com nulo em colunas que compõem chave natural."""
    mascara_nulo = df[colunas].isna().any(axis=1)
    removidas = df[mascara_nulo]
    if not removidas.empty:
        logger.warning(
            "%s: %d linha(s) descartada(s) por nulo em %s — conteúdo:\n%s",
            contexto, len(removidas), colunas, removidas.to_string(),
        )
    return df[~mascara_nulo]


def _deduplicar(df: pd.DataFrame, chave: list[str], contexto: str) -> pd.DataFrame:
    """Mantém a última ocorrência de cada chave natural (e loga o descarte)."""
    antes = len(df)
    df = df.drop_duplicates(subset=chave, keep="last")
    if (removidas := antes - len(df)) > 0:
        logger.warning("%s: %d duplicata(s) removida(s) pela chave %s", contexto, removidas, chave)
    return df


# ---------------------------------------------------------------------------
# 1. Fraudes / MED  →  fraude_med + detalhamentos normalizados
# ---------------------------------------------------------------------------

def transformar_fraudes(bruto: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Decompõe o registro mensal da API em 4 tabelas normalizadas.

    Retorna um dicionário com chaves ``fraude_med``, ``devolucao_med``,
    ``nao_devolucao_med`` e ``bloqueio_cautelar``; todas carregam a coluna
    auxiliar ``ano_mes`` (AAAAMM) que a carga converte em ``id_periodo``.
    """
    df = _descartar_nulos_em_chave(bruto.copy(), ["AnoMes"], "fraudes")
    df = _deduplicar(df, ["AnoMes"], "fraudes")

    medidas = [c for c in df.columns if c != "AnoMes"]
    if (nulos := int(df[medidas].isna().sum().sum())) > 0:
        logger.warning("fraudes: %d medida(s) nula(s) preenchida(s) com 0", nulos)
    df[medidas] = df[medidas].fillna(0)
    df["AnoMes"] = df["AnoMes"].astype(int)

    fraude_med = pd.DataFrame({
        "ano_mes": df["AnoMes"],
        "qtd_pix_contestados": df["QtdePixcontestados"].astype("int64"),
        "qtd_contestacoes_aceitas": df["Qtdecontestacoesaceitas"].astype("int64"),
        "qtd_contestacoes_rejeitadas": df["Qtdecontestacoesrejeitadas"].astype("int64"),
        "taxa_aceitas_por_100mil": df["Qtdecontestacoesaceitasacada100mil"].astype(float),
        "qtd_usuarios_marcados_fraude": df["QtdeUsuarioscommarcacoesdefraude"].astype("int64"),
        "qtd_chaves_marcadas_fraude": df["QtdeChavesPixcommarcacoesdefraude"].astype("int64"),
        "valor_contestados_aceitos": df["ValorPixcontestadosaceitos"].astype(float).round(2),
        "valor_residual_nao_devolvido": df["ValorPixresidualnaodevolvido"].astype(float).round(2),
        "percentual_devolucao": df["PercentualdeDevolucao"].astype(float),
    })

    # Validação de coerência: a soma aceitas+rejeitadas pode divergir levemente
    # do total contestado por arredondamento nos dados publicados pelo BCB.
    inconsistentes = fraude_med[
        fraude_med["qtd_contestacoes_aceitas"] + fraude_med["qtd_contestacoes_rejeitadas"]
        > fraude_med["qtd_pix_contestados"]
    ]
    if not inconsistentes.empty:
        for _, row in inconsistentes.iterrows():
            soma = row["qtd_contestacoes_aceitas"] + row["qtd_contestacoes_rejeitadas"]
            delta = soma - row["qtd_pix_contestados"]
            logger.warning(
                "fraudes: inconsistência BCB em %d — aceitas+rejeitadas=%d > contestados=%d (delta=%d)",
                int(row["ano_mes"]), soma, row["qtd_pix_contestados"], delta,
            )

    def _empilhar(categorias: dict[str, tuple[str, str]], nome_categoria: str) -> pd.DataFrame:
        """Converte pares de colunas (qtde, valor) em linhas categorizadas."""
        blocos = [
            pd.DataFrame({
                "ano_mes": df["AnoMes"],
                nome_categoria: rotulo,
                "quantidade": df[col_qtd].astype("int64"),
                "valor": df[col_valor].astype(float).round(2),
            })
            for rotulo, (col_qtd, col_valor) in categorias.items()
        ]
        return pd.concat(blocos, ignore_index=True)

    devolucao_med = _empilhar(
        {
            "INTEGRAL": ("QuantidadedevolvidaintegralmentepormeiodoMED", "ValorPixdevolvidosintegralmente"),
            "PARCIAL": ("QuantidadedevolvidaparcialmentepormeiodoMED", "ValorPixdevolvidosparcialmente"),
        },
        "tipo_devolucao",
    )
    nao_devolucao_med = _empilhar(
        {
            "SALDO_INSUFICIENTE": ("Quantidadedenaodevolvidossaldoinsuficiente", "ValorPixnaodevolvidossaldoinsuficiente"),
            "CONTA_ENCERRADA": ("Quantidadedenaodevolvidoscontaencerrada", "Valornaodevolvidoscontaencerrada"),
            "OUTROS": ("Quantidadedenaodevolvidosmotivosdiversos", "ValorPixnaodevolvidosmotivosdiversos"),
        },
        "motivo",
    )
    bloqueio_cautelar = _empilhar(
        {
            "LIBERADO": ("QtdePixbloqueadoscautelarmenteeliberados", "ValorPixbloqueadoscautelarmenteeliberados"),
            "DEVOLVIDO": ("QtdePixbloqueadoscautelarmenteedevolvidos", "ValorPixbloqueadoscautelarmenteedevolvidos"),
        },
        "desfecho",
    )

    return {
        "fraude_med": fraude_med,
        "devolucao_med": devolucao_med,
        "nao_devolucao_med": nao_devolucao_med,
        "bloqueio_cautelar": bloqueio_cautelar,
    }


# ---------------------------------------------------------------------------
# 2. Chaves PIX  →  instituicao + chave_pix_instituicao
# ---------------------------------------------------------------------------

def transformar_chaves(bruto: pd.DataFrame, ano: int, mes: int) -> dict[str, pd.DataFrame]:
    """Produz a dimensão ``instituicao`` e o fato ``chave_pix_instituicao``."""
    df = bruto.copy()
    df = _descartar_nulos_em_chave(df, ["ISPB", "NaturezaUsuario", "TipoChave"], "chaves")

    # ISPB é identificador com zeros à esquerda, nunca tratar como número.
    df["ISPB"] = _normalizar_texto(df["ISPB"]).str.zfill(8)
    df["Nome"] = _normalizar_texto(df["Nome"])
    df["NaturezaUsuario"] = _normalizar_texto(df["NaturezaUsuario"]).str.upper()
    df["TipoChave"] = _normalizar_texto(df["TipoChave"]).map(_TIPO_CHAVE_CANONICO)

    if (invalidos := int(df["TipoChave"].isna().sum())) > 0:
        logger.warning("chaves: %d linha(s) com tipo de chave desconhecido descartada(s)", invalidos)
        df = df.dropna(subset=["TipoChave"])

    df["qtdChaves"] = pd.to_numeric(df["qtdChaves"], errors="coerce").fillna(0).astype("int64")
    df = _deduplicar(df, ["ISPB", "NaturezaUsuario", "TipoChave"], "chaves")

    instituicao = (
        df[["ISPB", "Nome"]]
        .drop_duplicates(subset=["ISPB"], keep="last")
        .rename(columns={"ISPB": "ispb", "Nome": "nome"})
    )
    instituicao["nome"] = instituicao["nome"].str.slice(0, 120)

    chaves = pd.DataFrame({
        "ano_mes": ano * 100 + mes,
        "ispb": df["ISPB"],
        "natureza_usuario": df["NaturezaUsuario"],
        "tipo_chave": df["TipoChave"],
        "qtd_chaves": df["qtdChaves"],
    })
    return {"instituicao": instituicao, "chave_pix_instituicao": chaves}


# ---------------------------------------------------------------------------
# 3. Transações por município  →  municipio + transacao_municipio
# ---------------------------------------------------------------------------

def transformar_transacoes(bruto: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Produz a dimensão ``municipio`` e o fato ``transacao_municipio``.

    As 12 colunas de medida do CSV (VL/QT/QT_PES x Pagador/Recebedor x PF/PJ)
    são normalizadas em uma linha por combinação (papel, natureza) => 3FN.
    """
    df = bruto.copy()
    df = _descartar_nulos_em_chave(df, ["AnoMes", "Municipio_Ibge", "Estado_Ibge"], "transacoes")
    df = _deduplicar(df, ["AnoMes", "Municipio_Ibge"], "transacoes")

    df["AnoMes"] = df["AnoMes"].astype(int)
    df["Municipio_Ibge"] = df["Municipio_Ibge"].astype(int)
    df["Estado_Ibge"] = df["Estado_Ibge"].astype(int)
    df["Municipio"] = _normalizar_texto(df["Municipio"]).str.slice(0, 60)

    municipio = (
        df[["Municipio_Ibge", "Municipio", "Estado_Ibge"]]
        .drop_duplicates(subset=["Municipio_Ibge"], keep="last")
        .rename(columns={
            "Municipio_Ibge": "codigo_ibge",
            "Municipio": "nome",
            "Estado_Ibge": "codigo_ibge_estado",
        })
    )

    blocos = []
    for papel, sufixo_papel in (("PAGADOR", "Pagador"), ("RECEBEDOR", "Recebedor")):
        for natureza in ("PF", "PJ"):
            sufixo = f"{sufixo_papel}{natureza}"
            medidas = df[[f"VL_{sufixo}", f"QT_{sufixo}", f"QT_PES_{sufixo}"]]
            if (nulos := int(medidas.isna().sum().sum())) > 0:
                logger.warning("transacoes (%s): %d medida(s) nula(s) viram 0", sufixo, nulos)
            blocos.append(pd.DataFrame({
                "ano_mes": df["AnoMes"],
                "codigo_ibge_municipio": df["Municipio_Ibge"],
                "papel": papel,
                "natureza": natureza,
                "valor": df[f"VL_{sufixo}"].fillna(0).astype(float).round(2),
                "qtd_transacoes": df[f"QT_{sufixo}"].fillna(0).astype("int64"),
                "qtd_pessoas": df[f"QT_PES_{sufixo}"].fillna(0).astype("int64"),
            }))

    transacao = pd.concat(blocos, ignore_index=True)
    return {"municipio": municipio, "transacao_municipio": transacao}
