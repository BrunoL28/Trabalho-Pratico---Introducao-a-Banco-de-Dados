"""
Configuração central do projeto.

Toda parametrização sensível ao ambiente (string de conexão, URL da API,
timeouts) vive aqui e pode ser sobrescrita por variáveis de ambiente,
mantendo o restante do código livre de valores hard-coded.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

load_dotenv()

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/pix_med",
)


def criar_engine(echo: bool = False) -> Engine:
    """Cria a Engine SQLAlchemy usada por todo o projeto.

    ``pool_pre_ping`` evita erros com conexões mortas em sessões longas.
    """
    return create_engine(DATABASE_URL, echo=echo, pool_pre_ping=True)


# ---------------------------------------------------------------------------
# API Olinda — PIX Dados Abertos (Banco Central do Brasil)
# ---------------------------------------------------------------------------
OLINDA_BASE_URL: str = (
    "https://olinda.bcb.gov.br/olinda/servico/Pix_DadosAbertos/versao/v1/odata"
)

#: Timeout (conexão, leitura) em segundos para chamadas HTTP à API.
HTTP_TIMEOUT: tuple[int, int] = (10, 120)

#: Tamanho de página usado na paginação OData ($top/$skip).
PAGINA_ODATA: int = 20_000
