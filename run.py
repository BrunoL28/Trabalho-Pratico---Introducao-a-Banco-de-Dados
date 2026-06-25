"""
Orquestrador do projeto.

Ponto de entrada. Sequencia:
  1. Inicialização do sistema de logging (arquivo em logs/).
  2. Validação das configurações de ambiente (DATABASE_URL).
  3. Execução do pipeline ETL (src.ingest.executar).

Uso:
    python run.py [--inicio AAAA-MM] [--fim AAAA-MM] [--recriar-schema]

Exemplos:
    python run.py
    python run.py --inicio 2025-01 --fim 2025-06
    python run.py --recriar-schema --inicio 2024-01 --fim 2025-12
"""

from __future__ import annotations

import argparse
import logging
import sys

from src.config import DATABASE_URL
from src.ingest import executar
from src.logger import Logger


def _validar_config() -> None:
    """Aborta com mensagem clara se configurações obrigatórias estiverem ausentes."""
    if not DATABASE_URL:
        logging.critical("DATABASE_URL não configurada. Verifique o arquivo .env.")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline de ingestão PIX/MED — dados abertos do Banco Central.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--inicio", default="2024-01", metavar="AAAA-MM",
        help="Competência inicial (padrão: 2024-01)",
    )
    parser.add_argument(
        "--fim", default="2025-12", metavar="AAAA-MM",
        help="Competência final (padrão: 2025-12)",
    )
    parser.add_argument(
        "--recriar-schema", action="store_true",
        help="Reaplica sql/schema.sql antes da carga (apaga dados existentes!)",
    )
    args = parser.parse_args()

    Logger().configurar()
    _validar_config()

    log = logging.getLogger(__name__)
    log.info(
        "Iniciando pipeline | intervalo: %s → %s | recriar_schema=%s",
        args.inicio, args.fim, args.recriar_schema,
    )

    executar(args.inicio, args.fim, recriar_schema=args.recriar_schema)


if __name__ == "__main__":
    main()
