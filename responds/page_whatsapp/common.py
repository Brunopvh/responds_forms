from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum

from whatsapp_files import ResultChatImport
import pandas as pd


class ImportStatus(StrEnum):
    OK = "importado"
    ERROR = "erro"


@dataclass
class ImportItem:
    """Resultado da importação de UM arquivo (.zip ou .txt)."""

    source: str
    status: ImportStatus
    message: str = ""
    result: ResultChatImport | None = None


@dataclass(frozen=True)
class ImportSummary:
    total: int = 0
    ok: int = 0
    errors: int = 0
    added: int = 0
    elapsed_s: float = 0.0


@dataclass
class TaskResult:
    """Resultado de uma tarefa (renomear cartas / comandos de chat)."""

    title: str
    message: str = ""
    df: pd.DataFrame | None = None
