from __future__ import annotations
import os
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

import pandas as pd
from table_stream import HashMapDict, File, TableData, RowH
from cartas import HeaderFilesTOI, TipoCarta, LocalEntregaCarta


class StatusForms(StrEnum):
    PENDING = "pendente"
    RUNNING = "executando"
    SUCCESS = "sucesso"
    FAILED = "falha"
    SKIPPED = "pulado"


class HeaderForms(StrEnum):
    UC = HeaderFilesTOI.UC
    TOI = HeaderFilesTOI.TOI
    DATA_ENTREGA = HeaderFilesTOI.DATE

    TIPO = HeaderFilesTOI.TIPO_DOC
    LOCAL_ENTREGA = HeaderFilesTOI.LOCAL_ENTREGA

    HASH_FILE = HeaderFilesTOI.HASH_FILE
    FULL_PATH = HeaderFilesTOI.FULL_PATH

    STATUS = "status_forms"
    MESSAGE = "mensagem_forms"


@dataclass
class ResultStatus:
    """Status do envio de UMA linha da planilha (uma resposta do formulário)."""

    index: int
    status: StatusForms = StatusForms.PENDING
    message: str = ""


# ---------------------------------------------------------------------- normalização
_EMPTY = {"", "nan", "NaN", "None", "NaT", TableData.NULL_STRING}
_DATE_FORMATS = (
    "%d %m %Y",  # DateValues.DATE_TOI (saída do relatório TOI)
    "%d/%m/%Y",
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M:%S",
    "%d-%m-%Y",
    "%d.%m.%Y",
)


def clean_text(value: Any, default: str = "") -> str:
    s = str(value).strip()
    return default if s in _EMPTY else s


def clean_number(value: Any) -> str:
    """'1305934.0' -> '1305934' (Excel costuma transformar números em float)."""
    s = clean_text(value)
    return s[:-2] if s.endswith(".0") else s


def normalize_date(value: Any) -> str:
    """Qualquer formato usado no projeto -> dd/MM/yyyy (formato do campo no Forms)."""
    s = clean_text(value)
    if not s:
        raise ValueError("data de entrega vazia")

    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue

    raise ValueError(f"data de entrega inválida: {s}")


# ---------------------------------------------------------------------- MapRows
class MapRows(HashMapDict[int, RowH[HeaderForms, Any]]):
    """
    Atribui um índice/id a cada carta TOI. Cada carta é uma RowH (linha da planilha)
    com as colunas de HeaderForms, incluindo STATUS e MESSAGE atualizados durante o lançamento.
    """

    def __init__(
        self, _mapping: dict[int, RowH[HeaderForms, Any]] | None = None
    ) -> None:
        super().__init__(_mapping)

    # ---- status
    def update_status(
        self, idx_row: int, status: StatusForms, message: str = ""
    ) -> None:
        self[idx_row].set(HeaderForms.STATUS, status)
        self[idx_row].set(HeaderForms.MESSAGE, message)

    def get_status(self, idx_row: int) -> StatusForms:
        return self[idx_row].get(HeaderForms.STATUS)

    def count_status(self, status: StatusForms) -> int:
        return sum(1 for r in self.values() if r.get(HeaderForms.STATUS) == status)

    def reset_status(self) -> None:
        for idx in self.header():
            self.update_status(idx, StatusForms.PENDING)

    # ---- conversões
    def to_table(self) -> TableData[HeaderForms]:
        tb = TableData()

        for idx in self.header():
            tb.add_row(self.get_value(idx))
        return tb

    def to_data(self) -> pd.DataFrame | None:
        tb = self.to_table()
        return tb.to_dataframe() if not tb.is_empty() else None

    def to_view_data(self) -> pd.DataFrame:
        """DataFrame enxuto para exibir na tabela da UI."""
        records = []

        for idx in self.header():
            r = self[idx]
            path = clean_text(r.get(HeaderForms.FULL_PATH))

            records.append(
                {
                    "#": idx + 1,
                    "STATUS": str(r.get(HeaderForms.STATUS)),
                    "MENSAGEM": r.get(HeaderForms.MESSAGE),
                    "UC": r.get(HeaderForms.UC),
                    "TOI": r.get(HeaderForms.TOI),
                    "DATA": r.get(HeaderForms.DATA_ENTREGA),
                    "LOCAL": r.get(HeaderForms.LOCAL_ENTREGA),
                    "TIPO": r.get(HeaderForms.TIPO),
                    "ARQUIVO": os.path.basename(path) if path else "-",
                }
            )

        return pd.DataFrame(records)

    def save(self, file: File) -> None:
        df = self.to_data()
        if df is None:
            return

        df.to_excel(file.absolute(), index=False)

    # ---- criação a partir da tabela TOI
    @staticmethod
    def convert_row(row_toi: RowH[HeaderFilesTOI, Any]) -> RowH[HeaderForms, Any]:
        if row_toi.is_empty():
            raise ValueError("MapRows(): Linha TOI vazia")

        def get(h: HeaderFilesTOI, default: str = "") -> str:
            try:
                return clean_text(row_toi.get(h), default)
            except KeyError:
                return default

        r = RowH[HeaderForms, Any](0)
        r.set(HeaderForms.UC, clean_number(get(HeaderFilesTOI.UC)))
        r.set(HeaderForms.TOI, clean_number(get(HeaderFilesTOI.TOI)))
        r.set(HeaderForms.DATA_ENTREGA, get(HeaderFilesTOI.DATE))
        r.set(
            HeaderForms.TIPO,
            get(HeaderFilesTOI.TIPO_DOC, TipoCarta.CARTA_CALCULO.value),
        )

        r.set(
            HeaderForms.LOCAL_ENTREGA,
            get(HeaderFilesTOI.LOCAL_ENTREGA, LocalEntregaCarta.OUTRO.value),
        )
        r.set(HeaderForms.FULL_PATH, get(HeaderFilesTOI.FULL_PATH))
        r.set(HeaderForms.HASH_FILE, get(HeaderFilesTOI.HASH_FILE))
        r.set(HeaderForms.STATUS, StatusForms.PENDING)
        r.set(HeaderForms.MESSAGE, "")
        return r

    @classmethod
    def create_from_table(cls, tb: TableData[HeaderFilesTOI]) -> MapRows:
        mp = cls()
        for n in range(tb.size()):
            mp.set_value(n, cls.convert_row(tb.get_row_at(n)))
        return mp
