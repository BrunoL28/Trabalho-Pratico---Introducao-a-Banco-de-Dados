"""
Camada de extração, cliente da API Olinda (PIX Dados Abertos / BCB).

Particularidade da API descoberta durante a engenharia: os endpoints são
*function imports* OData que EXIGEM o parâmetro de função na URL (ex.:
``ChavesPix(Data=@Data)?@Data='2024-12-31'``), porém o parâmetro é ignorado
pelo servidor, que devolve a tabela inteira. A filtragem efetiva é feita via
``$filter`` OData, aplicada server-side (validado enquanto testávamos).
"""

from __future__ import annotations

import calendar
import datetime as dt
import logging
from urllib.parse import quote

import pandas as pd
import requests
from requests.adapters import HTTPAdapter, Retry

from src.config import HTTP_TIMEOUT, OLINDA_BASE_URL, PAGINA_ODATA

logger = logging.getLogger(__name__)


def _criar_sessao() -> requests.Session:
    """Sessão HTTP com retry exponencial para tolerar instabilidade da API."""
    sessao = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    sessao.mount("https://", HTTPAdapter(max_retries=retries))
    return sessao


_SESSAO = _criar_sessao()


def _buscar_odata(recurso: str, parametro_funcao: str, filtro: str | None = None) -> pd.DataFrame:
    """Busca um recurso OData completo, paginando com ``$top``/``$skip``.

    Parameters
    ----------
    recurso:
        Nome do function import, ex.: ``"ChavesPix"``.
    parametro_funcao:
        Trecho obrigatório da assinatura, ex.: ``"(Data=@Data)?@Data='2024-12-31'"``.
    filtro:
        Expressão ``$filter`` OData aplicada server-side (opcional).
    """
    paginas: list[pd.DataFrame] = []
    skip = 0
    while True:
        # A query string é montada manualmente: o servidor Olinda rejeita
        # espaços codificados como "+" (padrão do requests) no $filter,
        # apenas "%20" é aceito.
        partes = [f"$format=json", f"$top={PAGINA_ODATA}"]
        # Peculiaridade da API: "$skip=0" provoca HTTP 500, o parâmetro só
        # pode ser enviado a partir da segunda página.
        if skip > 0:
            partes.append(f"$skip={skip}")
        if filtro:
            partes.append(f"$filter={quote(filtro)}")
        url = f"{OLINDA_BASE_URL}/{recurso}{parametro_funcao}&{'&'.join(partes)}"

        resposta = _SESSAO.get(url, timeout=HTTP_TIMEOUT)
        resposta.raise_for_status()
        valores = resposta.json()["value"]
        paginas.append(pd.DataFrame(valores))

        if len(valores) < PAGINA_ODATA:  # última página
            break
        skip += PAGINA_ODATA

    df = pd.concat(paginas, ignore_index=True)
    logger.info("Extraídos %d registros de %s (filtro=%s)", len(df), recurso, filtro)
    return df


# ---------------------------------------------------------------------------
# Extratores públicos, um por dataset de origem
# ---------------------------------------------------------------------------

def extrair_fraudes() -> pd.DataFrame:
    """Estatísticas mensais de fraude/MED (série completa, ~poucas dezenas de linhas)."""
    return _buscar_odata("EstatisticasFraudesPix", "(Database=@Database)?@Database='000000'")


def extrair_chaves(ano: int, mes: int) -> pd.DataFrame:
    """Snapshot da base de chaves PIX por instituição no último dia do mês."""
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    data_ref = dt.date(ano, mes, ultimo_dia)
    return _buscar_odata(
        "ChavesPix",
        f"(Data=@Data)?@Data='{data_ref.isoformat()}'",
        filtro=f"Data eq {data_ref.isoformat()}",
    )


def extrair_transacoes_municipio(ano: int, mes: int) -> pd.DataFrame:
    """Volumetria de transações PIX por município na competência informada."""
    ano_mes = ano * 100 + mes
    return _buscar_odata(
        "TransacoesPixPorMunicipio",
        f"(DataBase=@DataBase)?@DataBase='{ano_mes}'",
        filtro=f"AnoMes eq {ano_mes}",
    )
