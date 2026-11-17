from __future__ import annotations
import os
import threading
from datetime import datetime
from enum import StrEnum
from typing import Any

import pandas as pd
from table_stream import RowH, TableData
from cartas import BuilderConfigTOI

from responds.page_forms.common import HeaderForms, clean_number, clean_text


class HeaderMasterForms(StrEnum):
    KEY = "key_uc_toi"
    UC = HeaderForms.UC.value
    TOI = HeaderForms.TOI.value
    DATA_ENTREGA = HeaderForms.DATA_ENTREGA.value
    LOCAL_ENTREGA = HeaderForms.LOCAL_ENTREGA.value
    TIPO = HeaderForms.TIPO.value
    HASH_FILE = HeaderForms.HASH_FILE.value
    FULL_PATH = HeaderForms.FULL_PATH.value
    DATA_LANCAMENTO = "data_lancamento"


def make_key(uc: Any, toi: Any) -> str:
    """Chave de uma carta: UC sozinha não identifica, usa UC+TOI."""
    return f"{clean_number(uc)}_{clean_number(toi)}"


class ControllerMasterForms(object):
    """
    Arquivo master do Forms: tudo que já foi lançado com sucesso.
    Equivalente ao ControllerTOI().load_table_toi(), mas exclusivo do Forms.
    """

    COLUMNS: list[str] = [h.value for h in HeaderMasterForms]

    def __init__(self) -> None:
        self._lock = threading.Lock()

    @property
    def file_master(self):
        return BuilderConfigTOI().builder().file_master_forms

    # ---------------------------------------------------------------- leitura
    def load_dataframe(self) -> pd.DataFrame:
        f = self.file_master
        if not f.exists():
            return pd.DataFrame(columns=self.COLUMNS)

        df = pd.read_excel(f.absolute(), dtype=str).fillna("")
        for c in self.COLUMNS:
            if c not in df.columns:
                df[c] = ""
        return df[self.COLUMNS]

    def load_table_master(self) -> TableData[HeaderMasterForms]:
        return TableData(self.load_dataframe())

    def load_keys(self) -> set[str]:
        df = self.load_dataframe()
        return set(df[HeaderMasterForms.KEY.value].astype(str).tolist())

    def contains(self, uc: Any, toi: Any) -> bool:
        return make_key(uc, toi) in self.load_keys()

    # ---------------------------------------------------------------- escrita
    def register(self, row: RowH[HeaderForms, Any]) -> bool:
        """
        Grava uma carta lançada com sucesso. Retorna False se a chave já existia.
        Escrita atômica (tmp + replace): nunca deixa .xlsx corrompido.
        """
        uc = clean_number(row.get(HeaderForms.UC))
        toi = clean_number(row.get(HeaderForms.TOI))
        key = make_key(uc, toi)

        with self._lock:
            df = self.load_dataframe()
            if key in set(df[HeaderMasterForms.KEY.value].tolist()):
                return False

            record = {
                HeaderMasterForms.KEY.value: key,
                HeaderMasterForms.UC.value: uc,
                HeaderMasterForms.TOI.value: toi,
                HeaderMasterForms.DATA_ENTREGA.value: clean_text(
                    row.get(HeaderForms.DATA_ENTREGA)
                ),
                HeaderMasterForms.LOCAL_ENTREGA.value: clean_text(
                    row.get(HeaderForms.LOCAL_ENTREGA)
                ),
                HeaderMasterForms.TIPO.value: clean_text(row.get(HeaderForms.TIPO)),
                HeaderMasterForms.HASH_FILE.value: clean_text(
                    row.get(HeaderForms.HASH_FILE)
                ),
                HeaderMasterForms.FULL_PATH.value: clean_text(
                    row.get(HeaderForms.FULL_PATH)
                ),
                HeaderMasterForms.DATA_LANCAMENTO.value: datetime.now().strftime(
                    "%d/%m/%Y %H:%M:%S"
                ),
            }
            new = pd.DataFrame([record], columns=self.COLUMNS)
            final = new if df.empty else pd.concat([df, new], ignore_index=True)

            path = self.file_master.absolute()
            tmp = f"{path}-tmp.xlsx"
            final.to_excel(tmp, index=False)
            os.replace(tmp, path)
            return True
