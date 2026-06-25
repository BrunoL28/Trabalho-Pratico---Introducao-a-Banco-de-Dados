"""
Logger Singleton, ponto único de configuração do sistema de logging.

Padrão de projeto: Singleton.
A classe garante uma única instância via ``__new__``, de modo que qualquer
parte do código que instancie ``Logger()`` recebe sempre o mesmo objeto já
configurado e sem risco de handlers duplicados ou arquivos de log conflitantes.

Uso típico::

    from src.logger import Logger

    Logger().configurar()          # chamado uma vez no ponto de entrada
    log = Logger.get(__name__)     # em qualquer módulo, em seguida
    log.info("mensagem")
"""

from __future__ import annotations

import datetime
import logging
from pathlib import Path

_RAIZ = Path(__file__).resolve().parent.parent
_FMT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


class Logger:
    """Singleton que configura e expõe o sistema de logging do projeto."""

    _instancia: "Logger | None" = None
    _configurado: bool = False

    def __new__(cls) -> "Logger":
        if cls._instancia is None:
            cls._instancia = super().__new__(cls)
        return cls._instancia

    def configurar(
        self,
        nivel: int = logging.INFO,
        pasta_logs: Path | None = None,
    ) -> None:
        """Configura handlers de console e arquivo (idempotente após a 1ª chamada).

        Parameters
        ----------
        nivel:
            Nível mínimo de severidade (ex.: ``logging.DEBUG``).
        pasta_logs:
            Diretório onde o arquivo ``.log`` será criado. Padrão: ``logs/``
            na raiz do projeto. O diretório é criado se não existir.
        """
        if self._configurado:
            return

        if pasta_logs is None:
            pasta_logs = _RAIZ / "logs"
        pasta_logs.mkdir(exist_ok=True)

        nome_arquivo = datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".log"
        caminho_log = pasta_logs / nome_arquivo

        fmt = logging.Formatter(_FMT, datefmt=_DATEFMT)

        raiz = logging.getLogger()
        raiz.setLevel(nivel)

        console = logging.StreamHandler()
        console.setFormatter(fmt)
        raiz.addHandler(console)

        arquivo = logging.FileHandler(caminho_log, encoding="utf-8")
        arquivo.setFormatter(fmt)
        raiz.addHandler(arquivo)

        self._configurado = True
        logging.getLogger(__name__).info("Log iniciado → %s", caminho_log)

    @staticmethod
    def get(nome: str) -> logging.Logger:
        """Atalho para ``logging.getLogger``; mantém compatibilidade com o módulo padrão."""
        return logging.getLogger(nome)
