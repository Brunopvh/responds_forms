# arquivo cartas/__init__.py

# stdlib/builtins
from __future__ import annotations
from dataclasses import dataclass
import os
import re
from enum import StrEnum
from typing import Any, Iterable, Mapping
from abc import ABC, abstractmethod
from os import replace as replace_file
from datetime import datetime
import threading

# External modules
import pandas as pd
from table_stream import (
    # Array
    HashMapDict,
    HashMap,
    ArrayList,
    Set,
    # Tabelas
    TableData,
    ArrayTables,
    ColumnV,
    RowH,
    HeadersSizeNotIqualError,
    # Arquivos.
    HeaderMetaData,
    hashFile,
    File,
    Directory,
    ContentFiles,
    load_file_hash,
)

# from ocr_stream import HeaderOcr, BuilderConfigOcr, CreateRelatorioOcr

from whatsapp_files import (
    RowWhatsApp,
    TableWhatsApp,
    HeaderWhatsApp,
    BuilderTableWhatsApp,
    ControllerWhatsApp,
    BuilderConfigWhatsApp,  # NOVO: base RFA única (substitui BuilderConfigOcr)
    move_path,
)

__version__ = "0.3.1"


@dataclass
class ConfigTOI:

    file_relatorio_toi: File
    file_cartas_lancadas: File
    file_table_toi: File
    file_master_forms: File  # NOVO
    dir_base_toi: Directory
    dir_log_excel: Directory
    dir_relatorios: Directory
    work_dir: Directory


# Mesmos nomes de arquivo gravados por ocr_stream. Se mudar lá, mude aqui.
_OCR_FILE_IMAGE = "tabela_ocr_imagens.xlsx"
_OCR_FILE_PDF = "tabela_ocr_pdf.xlsx"


class BuilderConfigTOI(object):
    """
    Configuração de cartas SEM depender de ocr_stream.
    Base única: <Documentos>/RFA (BuilderConfigWhatsApp.dir_base_root),
    tabelas em <Documentos>/RFA/Tabelas (mesmos caminhos do ocr_stream).
    """

    _instance = None  # Atributo de classe para armazenar a instância singleton

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(BuilderConfigTOI, cls).__new__(cls)
        return cls._instance

    def __init__(self) -> None:

        # Garante que __init__ não será executado mais de uma vez
        if hasattr(self, "_initialized") and self._initialized:
            return

        super().__init__()
        self._initialized: bool = True
        self._builder_wp = BuilderConfigWhatsApp()
        self._dir_retorno_override: Directory | None = None  # NOVO
        self._config = self._create()

    # ---------------------------------------------------------- base RFA
    @property
    def dir_base_work(self) -> Directory:
        return self._builder_wp.dir_base_root

    @property
    def dir_table(self) -> Directory:
        """<Documentos>/RFA/Tabelas"""
        return self._builder_wp.dir_table

    # ---------------------------------------------------------- tabelas OCR (somente leitura)
    @property
    def file_table_ocr_image(self) -> File:
        return self.dir_table.join_file(_OCR_FILE_IMAGE)

    @property
    def file_table_ocr_pdf(self) -> File:
        return self.dir_table.join_file(_OCR_FILE_PDF)

    # ---------------------------------------------------------- pastas TOI
    @property
    def dir_retorno_de_campo(self) -> Directory:
        if self._dir_retorno_override is not None:  # NOVO
            self._dir_retorno_override.mkdir()
            return self._dir_retorno_override

        return self.dir_base_work.concat("Cartas-TOI", True).concat(
            "Retorno-de-campo", True
        )

    @property
    def dir_log_excel(self) -> Directory:
        return self.dir_base_work.concat("Cartas-TOI", True).concat("Logs", True)

    @property
    def dir_relatorios(self) -> Directory:
        return self.dir_base_work.concat("Cartas-TOI", True).concat(
            "Relatorios-toi", True
        )

    # ---------------------------------------------------------- arquivos TOI
    @property
    def file_relatorio_toi(self) -> File:
        return self.dir_table.join_file("Relatorio-tois.xlsx")

    @property
    def file_relatorio_forms(self) -> File:
        return self.dir_table.join_file("cartas-toi-lancadas.xlsx")

    @property
    def file_master_forms(self) -> File:
        return self.dir_table.join_file("master-forms-toi.xlsx")

    @property
    def file_table_toi(self) -> File:
        return self.dir_table.join_file("tabela-entregas-tois.xlsx")

    def _create(self) -> ConfigTOI:
        return ConfigTOI(
            work_dir=self.dir_base_work,
            dir_base_toi=self.dir_retorno_de_campo,
            file_relatorio_toi=self.file_relatorio_toi,
            file_table_toi=self.file_table_toi,
            file_cartas_lancadas=self.file_relatorio_forms,
            dir_log_excel=self.dir_log_excel,
            dir_relatorios=self.dir_relatorios,
            file_master_forms=self.file_master_forms,
        )

    def default_dir_retorno_de_campo(
        self,
    ) -> Directory:  # NOVO (para "Restaurar padrão")
        return self.dir_base_work.concat("Cartas-TOI", True).concat(
            "Retorno-de-campo", True
        )

    def set_dir_retorno_de_campo(self, d: Directory | None) -> None:  # NOVO
        """None = volta ao padrão."""
        self._dir_retorno_override = d
        self.reset_config()

    def reset_config(self) -> None:
        self._config = None

    def builder(self) -> ConfigTOI:
        if self._config is None:
            self._config = self._create()
        return self._config


def set_dir_base_toi(directory: Directory | None) -> None:
    """Define (ou restaura, com None) o diretório base das cartas TOI."""
    cfg = BuilderConfigTOI()
    cfg.set_dir_retorno_de_campo(directory)
    cfg.builder()  # recria o ConfigTOI já com o novo diretório


# ============================================================#
# Leitura das tabelas OCR direto dos .xlsx (sem ocr_stream)
# ============================================================#


class HeaderOcr(StrEnum):
    """Colunas das tabelas OCR (mesmos nomes gravados pelo ocr_stream)."""

    ID = "ID"
    HASH_FILE = HeaderMetaData.HASH_FILE.value
    NUM_PAG = "PÁGINA"
    NUM_LINHA = "LINHA"
    TEXT = "TEXTO"


_OCR_COLUMNS: list[str] = [h.value for h in HeaderOcr]
_OCR_C_HASH = HeaderOcr.HASH_FILE.value


class ReadTablesOcr(object):
    """
    Leitor SOMENTE-LEITURA de RFA/Tabelas/tabela_ocr_imagens.xlsx e
    tabela_ocr_pdf.xlsx. Equivale ao que cartas usava de CreateRelatorioOcr,
    mas sem importar ocr_stream/tesseract/cv2.

    Cache em memória por arquivo, invalidado quando o .xlsx muda
    (mtime + tamanho). Assim, se outro processo/PC rodar o OCR, a próxima
    consulta já enxerga o dado novo.

    As tabelas devolvidas por load_table_* são o objeto do cache: trate
    como SOMENTE LEITURA (nunca chame merge()/set() nelas).
    """

    KIND_IMAGE = "imagem"
    KIND_PDF = "pdf"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cache: dict[str, tuple[tuple[int, int] | None, TableData[HeaderOcr]]] = {}

    # ---------------------------------------------------------- infra
    @staticmethod
    def _file_of(kind: str) -> File:
        cfg = BuilderConfigTOI()
        if kind == ReadTablesOcr.KIND_IMAGE:
            return cfg.file_table_ocr_image
        return cfg.file_table_ocr_pdf

    @staticmethod
    def _stamp(f: File) -> tuple[int, int] | None:
        try:
            st = os.stat(f.absolute())
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size)

    @staticmethod
    def _void() -> TableData[HeaderOcr]:
        return TableData(pd.DataFrame(columns=_OCR_COLUMNS))

    @staticmethod
    def _read(f: File) -> TableData[HeaderOcr]:
        # dtype=str + fillna(""): célula vazia vira "" (e não o texto "nan").
        df = pd.read_excel(f.absolute(), dtype=str).fillna("")
        for c in _OCR_COLUMNS:
            if c not in df.columns:
                df[c] = ""
        return TableData.create_from_data(
            df[_OCR_COLUMNS].astype(str).reset_index(drop=True)
        )

    def _load(self, kind: str) -> TableData[HeaderOcr]:
        f = self._file_of(kind)
        stamp = self._stamp(f)

        with self._lock:
            cached = self._cache.get(kind)
            if cached is not None and cached[0] == stamp:
                return cached[1]

            if stamp is None:  # arquivo ainda não existe (OCR nunca rodou)
                tb = self._void()
            else:
                try:
                    print(f"Lendo tabela OCR ({kind}) ... {f.absolute()}")
                    tb = self._read(f)
                except Exception as e:
                    print(f"[AVISO] falha ao ler {f.absolute()}: {e}")
                    # mantém o cache anterior (se houver) e tenta de novo depois
                    return cached[1] if cached is not None else self._void()

            self._cache[kind] = (stamp, tb)
            return tb

    # ---------------------------------------------------------- READ
    def load_table_image(self) -> TableData[HeaderOcr]:
        return self._load(self.KIND_IMAGE)

    def load_table_pdf(self) -> TableData[HeaderOcr]:
        return self._load(self.KIND_PDF)

    def create_from_hashs(self, hashes: Iterable[str]) -> TableData[HeaderOcr] | None:
        """
        Linhas OCR (imagem + pdf) das hashs informadas, SEM aplicar OCR.
        None se nada for encontrado. O resultado é uma cópia (pode alterar).
        """
        wanted = {str(h) for h in hashes}
        if not wanted:
            return None

        frames: list[pd.DataFrame] = []
        for kind in (self.KIND_IMAGE, self.KIND_PDF):
            df = self._load(kind).get_data()
            if df.empty:
                continue
            sub = df[df[_OCR_C_HASH].isin(wanted)]
            if not sub.empty:
                frames.append(sub)

        if not frames:
            return None

        final = pd.concat(frames, ignore_index=True)
        return TableData.create_from_data(final[_OCR_COLUMNS].astype(str))


# ============================================================#
# Extração de UC/TOI tolerante a falhas de OCR
# ============================================================#
#
# UC: 1305934 TOI: 193166923 ...
# UC: 1305934 TO! 193166923 ...   (TOI virou TO!, ":" some)
# UC| 1305934 T0I: 193166923 ...  (0 no lugar do O)
#

UC_TOI_PATTERN = re.compile(
    r"U[C0]\s*[:;|!]?\s*(\d{4,10})" r".{0,60}?" r"T[O0][I1L!l]?\s*[:;|!]?\s*(\d{4,10})",
    re.IGNORECASE | re.DOTALL,
)


def extrair_uc_toi(texto: str) -> tuple[str, str] | None:
    """
        Retorna (uc, toi) a partir do texto OCR completo de um arquivo,
    ou None se o padrão não for encontrado.
    """
    m = UC_TOI_PATTERN.search(texto)
    if not m:
        return None
    return m.group(1), m.group(2)


# Nova API: identifica cada campo de forma independente. A função antiga acima
# permanece intacta para não quebrar consumidores existentes.
UC_PATTERN_PARTIAL = re.compile(
    r"(?<![A-Z0-9])U[CGE0]\s*[:;|!,}]?\s*(\d{4,10})(?!\d)",
    re.IGNORECASE,
)

TOI_PATTERN_PARTIAL = re.compile(
    r"(?<![A-Z0-9])T[O0Q][I1L!|}K]?\s*[:;|!,}]?\s*(\d{4,10})(?!\d)",
    re.IGNORECASE,
)


def extrair_identificadores_parciais(
    texto: str | None,
) -> tuple[str | None, str | None]:
    """Retorna (UC, TOI), permitindo que qualquer um dos campos seja None.

    Exemplos tolerados: 'Ue, 78534', 'UG; 1462905', 'TOI: 217678510',
    'Tol: 210768466', 'TO}: 218108980'.
    """
    if not texto:
        return None, None

    uc_match = UC_PATTERN_PARTIAL.search(texto)
    toi_match = TOI_PATTERN_PARTIAL.search(texto)
    uc = uc_match.group(1) if uc_match else None
    toi = toi_match.group(1) if toi_match else None
    return uc, toi


# ========================================================#
# Tabelas TOI.
# ========================================================#


class HeaderEntregaTOI(StrEnum):
    """
    Enumerador que representa a relação entre um documento e os dados
    de entrega:
        UC, TOI, DAY, MON, YEAR, DATE E HASH_FILE.

    a relação/key de uma entrega e a hash do documento.
    """

    UC = "uc"
    TOI = "toi"
    DAY = "day"
    MON = "mon"
    YEAR = "year"
    DATE = "data_entrega"
    HASH_FILE = HeaderMetaData.HASH_FILE.value


class HeaderFilesTOI(StrEnum):
    """
    Dados completos de um arquivo TOI, incluindo os metadados e
    caminho absoluto.
    """

    UC = HeaderEntregaTOI.UC
    TOI = HeaderEntregaTOI.TOI
    DAY = HeaderEntregaTOI.DAY
    MON = HeaderEntregaTOI.MON
    YEAR = HeaderEntregaTOI.YEAR
    DATE = HeaderEntregaTOI.DATE
    HASH_FILE = HeaderEntregaTOI.HASH_FILE

    LOCAL_ENTREGA = "local_entrega"
    TIPO_DOC = "tipo_carta"

    IS_FILE = "arquivo?"
    FULL_PATH = HeaderMetaData.FILE_PATH.value
    SRC = HeaderMetaData.PARENT_DIR.value
    FILE_EXTENSION = HeaderMetaData.FILE_EXTENSION.value
    FILE_BASENAME = "basename"


class TipoCarta(StrEnum):

    CARTA_CALCULO = "CARTA-CALCULO"


class LocalEntregaCarta(StrEnum):

    OUTRO = "OUTRO"
    MAOS = "MÃOS"
    CORREIOS = "CORREIOS"
    PORTAO = "PORTÃO"


# ========================================================#
# Criar Tabelas.
# ========================================================#


class BuilderTOI(ABC):
    """
        Criar dados de uma entrega TOI apartir de um arquivo ou do texto
    de um documento.
    """

    def __init__(self) -> None:
        super().__init__()

    @abstractmethod
    def create_void(self) -> TableData[Any]:
        pass

    @abstractmethod
    def from_data(self, df: pd.DataFrame) -> TableData[Any]:
        pass

    @abstractmethod
    def from_path_name(self, path: File, md5: hashFile = None) -> TableData[Any] | None:
        pass

    @abstractmethod
    def from_hash_files(
        self, data: HashMap[hashFile, File], *, ignore_null: bool = True
    ) -> TableData[Any] | None:
        pass


class BuilderEntregaTOI(BuilderTOI):
    """
        Criar dados de uma entrega TOI apartir de um arquivo ou do texto
    de um documento.
    """

    def __init__(self) -> None:
        super().__init__()
        # self.relatorio_ocr = CreateRelatorioOcr()
        self.relatorio_ocr = ReadTablesOcr()
        self.relatorio_wp = ControllerWhatsApp()

        self.default_cols_toi = ArrayList[HeaderEntregaTOI].from_list(
            [
                HeaderEntregaTOI.UC,
                HeaderEntregaTOI.TOI,
                HeaderEntregaTOI.DATE,
                HeaderEntregaTOI.YEAR,
                HeaderEntregaTOI.MON,
                HeaderEntregaTOI.DAY,
                HeaderEntregaTOI.HASH_FILE,
            ]
        )

    def create_void(self) -> TableData[HeaderEntregaTOI]:
        """
        Cria uma tabela TOI vazia com todos os itens do cabeçalho HeaderTOI
        """
        tb = TableData[HeaderEntregaTOI]()
        self.default_cols_toi.for_each(lambda c: tb.add(ColumnV(c)))
        return tb

    def from_data(self, df: pd.DataFrame) -> TableData[HeaderEntregaTOI]:
        """
        Criar tabela TOI apartir de um DataFrame().
        """
        df = df.astype(str)
        df_cols = ArrayList(df.columns.tolist())
        tb = TableData[HeaderEntregaTOI]()

        c: HeaderEntregaTOI
        for c in self.default_cols_toi:
            if df_cols.contains(c.value):
                tb.add(
                    ColumnV.create_from_list(c, df[c.value].astype(str).values.tolist())
                )

        if tb.header().size() != self.default_cols_toi.size():
            raise HeadersSizeNotIqualError(
                f"DataFrame() de entrega toi com colunas diferente do padrão: \n{tb.header()}"
            )
        return tb

    def from_path_name(
        self, path: File, md5: hashFile = None
    ) -> TableData[HeaderEntregaTOI] | None:
        """
        Criar tabela apartir do nome de uma arquivo que esteja no padrão TOI.
        """

        if not path.exists():
            return None

        mp = self.create_map_from_filename(path.name())
        if mp is None:
            return None
        if md5 is None:
            md5 = load_file_hash(path)

        mp.set_value(HeaderEntregaTOI.HASH_FILE, md5)
        tb = TableData[HeaderEntregaTOI]()
        c: HeaderEntregaTOI

        for c in self.default_cols_toi:
            tb.add(ColumnV.create_from_list(c, [mp.get_value(c)]))
        return tb

    def create_map_from_filename(
        self,
        filename: str,
    ) -> HashMapDict[HeaderEntregaTOI, str] | None:
        """
        Retorna um Map de chave/valor com as seguintes chaves:

        UC, TOI, DAY, MON, YEAR e DATE.
        """

        try:
            values = filename.split(" ")
            if len(values) < 5:
                # Nome incompleto ou inválido.
                return None
        except:
            return None
        else:
            for x in values:
                if not x.isnumeric():
                    return None

            data = HashMapDict()
            data[HeaderEntregaTOI.UC] = values[0]  # UC
            data[HeaderEntregaTOI.TOI] = values[1]  # TOI
            data[HeaderEntregaTOI.DAY] = values[2]  # DIA
            data[HeaderEntregaTOI.MON] = values[3]  # MÊS
            data[HeaderEntregaTOI.YEAR] = values[4]  # ANO
            data[HeaderEntregaTOI.DATE] = f"{values[2]}/{values[3]}/{values[4]}"
            return data

    def from_hash_files(
        self, data: HashMap[hashFile, File], *, ignore_null: bool = True
    ) -> TableData[HeaderEntregaTOI] | None:

        if data.is_empty():
            return None

        header_hashs = data.header().to_set()
        table_ocr: TableData[HeaderOcr] | None = self.relatorio_ocr.create_from_hashs(
            header_hashs
        )

        if table_ocr is None:
            return None
        if table_ocr.is_empty():
            return None

        # builder_wp = BuilderTableWhatsApp()

        table_whatsapp: TableData[HeaderWhatsApp] = self.relatorio_wp.load_cache_table()
        if table_whatsapp.is_empty():
            if ignore_null:
                return None

        key_hash: hashFile
        sequence_tables = ArrayTables[TableData[HeaderEntregaTOI]]()

        for key_hash in header_hashs:
            date_chat_file: str = TableData.NULL_STRING
            day = TableData.NULL_STRING
            mon = TableData.NULL_STRING
            year = TableData.NULL_STRING
            uc = TableData.NULL_STRING
            toi = TableData.NULL_STRING

            # =========================================================#
            # Data de envio do arquivo no chat
            # =========================================================#
            if not table_whatsapp.is_empty():
                tb_chat = table_whatsapp.search(HeaderWhatsApp.hash_md5, key_hash)

                if tb_chat.is_empty() and ignore_null:
                    continue

                if not tb_chat.is_empty():
                    # date_chat_file: datetime = tb_chat.get_row_at(0).get_date_hour()
                    # day = str(date_chat_file.day)
                    # mon = str(date_chat_file.month)
                    # year = str(date_chat_file.year)
                    date_chat_file: str = tb_chat.get_row_at(0).get_date().get_first()
                    day = date_chat_file.split(" ")[0]
                    mon = date_chat_file.split(" ")[1]
                    year = date_chat_file.split(" ")[2]

            # =========================================================#
            # Extrair UC e TOI
            # =========================================================#
            tb_ocr = table_ocr.search(HeaderOcr.HASH_FILE, key_hash)
            if tb_ocr.is_empty() and ignore_null:
                continue

            if not tb_ocr.is_empty():
                txt_ocr: str = tb_ocr.to_string(HeaderOcr.TEXT)
                value_uc_toi: tuple[str, str] | None = extrair_uc_toi(txt_ocr)

                if value_uc_toi is None and ignore_null:
                    continue

                if value_uc_toi is not None:
                    uc = value_uc_toi[0]
                    toi = value_uc_toi[1]

            row_toi = RowH[HeaderEntregaTOI, Any](0)
            row_toi.set(HeaderEntregaTOI.UC, uc)
            row_toi.set(HeaderEntregaTOI.TOI, toi)
            row_toi.set(HeaderEntregaTOI.DAY, day)
            row_toi.set(HeaderEntregaTOI.MON, mon)
            row_toi.set(HeaderEntregaTOI.YEAR, year)
            row_toi.set(HeaderEntregaTOI.HASH_FILE, key_hash)
            row_toi.set(HeaderEntregaTOI.DATE, date_chat_file)

            t = self.create_void()
            t.add_row(row_toi)
            sequence_tables.add(t)

        if sequence_tables.empty():
            return None

        return sequence_tables.concat(TableData).drop_duplicates()


class BuilderTableFilesTOI(BuilderTOI):

    def __init__(self) -> None:
        super().__init__()

        self.default_cols_cartas = ArrayList[HeaderFilesTOI].from_list(
            [
                HeaderFilesTOI.UC,
                HeaderFilesTOI.TOI,
                HeaderFilesTOI.DATE,
                HeaderFilesTOI.YEAR,
                HeaderFilesTOI.MON,
                HeaderFilesTOI.DAY,
                HeaderFilesTOI.LOCAL_ENTREGA,
                HeaderFilesTOI.TIPO_DOC,
                HeaderFilesTOI.HASH_FILE,
                HeaderFilesTOI.IS_FILE,
                HeaderFilesTOI.FILE_BASENAME,
                HeaderFilesTOI.FILE_EXTENSION,
                HeaderFilesTOI.FULL_PATH,
                HeaderFilesTOI.SRC,
            ]
        )

        self.factory_toi: BuilderEntregaTOI = BuilderEntregaTOI()

    def get_factory_toi(self) -> BuilderEntregaTOI:
        return self.factory_toi

    def create_void(self) -> TableData[HeaderFilesTOI]:
        """
        Cria uma tabela com os cabeçalhos de HeaderFilesTOI.
        """
        tb = TableData()
        self.default_cols_cartas.for_each(lambda c: tb.add(ColumnV(c)))
        return tb

    def from_data(self, df: pd.DataFrame) -> TableData[HeaderFilesTOI]:
        df = df.astype(str)
        df_cols = ArrayList(df.columns.tolist())
        final_table = TableData()

        c: HeaderFilesTOI
        for c in self.default_cols_cartas:

            if df_cols.contains(c.value):
                final_table.add(
                    ColumnV.create_from_list(c, df[c.value].astype(str).values.tolist())
                )

        if final_table.header().size() != self.default_cols_cartas.size():
            msg = "DataFrame() FORMS toi com colunas diferente do padrão:"
            msg_header = f"Cabeçalho FORMS {final_table.header()}"
            raise HeadersSizeNotIqualError(
                f"{msg} \n\n{msg_header}\nCabeçalho externo {df.columns}"
            )
        return final_table

    def decode_table_toi(
        self, tb: TableData[HeaderEntregaTOI], data: HashMap[hashFile, File]
    ) -> TableData[HeaderFilesTOI] | None:

        if data.is_empty():
            return None
        if tb.is_empty():
            return None

        _df_toi = tb.to_dataframe().drop_duplicates(
            subset=[HeaderEntregaTOI.HASH_FILE.value]
        )

        tb = self.get_factory_toi().from_data(_df_toi)
        final_tb = TableData[HeaderFilesTOI].create_void(self.default_cols_cartas)

        rows = tb.rows()
        r: RowH[HeaderEntregaTOI, Any]
        row_tb: RowH[HeaderFilesTOI, Any]

        for r in rows:
            row_tb = RowH(0)

            row_tb.set(HeaderFilesTOI.UC, r.get(HeaderEntregaTOI.UC))
            row_tb.set(HeaderFilesTOI.TOI, r.get(HeaderEntregaTOI.TOI))
            row_tb.set(HeaderFilesTOI.DATE, r.get(HeaderEntregaTOI.DATE))
            row_tb.set(HeaderFilesTOI.DAY, r.get(HeaderEntregaTOI.DAY))
            row_tb.set(HeaderFilesTOI.MON, r.get(HeaderEntregaTOI.MON))
            row_tb.set(HeaderFilesTOI.YEAR, r.get(HeaderEntregaTOI.YEAR))
            row_tb.set(HeaderFilesTOI.HASH_FILE, r.get(HeaderEntregaTOI.HASH_FILE))

            row_tb.set(HeaderFilesTOI.LOCAL_ENTREGA, LocalEntregaCarta.OUTRO)
            row_tb.set(HeaderFilesTOI.TIPO_DOC, TipoCarta.CARTA_CALCULO)

            # Incluir colunas adicionais.
            _hash_file = r.get(HeaderEntregaTOI.HASH_FILE)
            path = data.get_value(_hash_file)

            row_tb.set(HeaderFilesTOI.FILE_BASENAME, path.basename())
            row_tb.set(
                HeaderFilesTOI.FILE_EXTENSION,
                path.extension() or ".nan",
            )
            row_tb.set(HeaderFilesTOI.FULL_PATH, path.absolute())

            row_tb.set(HeaderFilesTOI.SRC, path.parent().absolute())
            row_tb.set(HeaderFilesTOI.IS_FILE, "S" if path.is_file() else "N")

            final_tb.add_row(row_tb)

        if final_tb.is_empty():
            return None

        _final_df = final_tb.to_dataframe().drop_duplicates(
            subset=[HeaderFilesTOI.HASH_FILE.value]
        )
        return self.from_data(_final_df)

    def from_path_name(
        self, path: File, md5: hashFile = None
    ) -> TableData[HeaderFilesTOI] | None:

        if md5 is None:
            md5 = load_file_hash(path)

        tb_toi = self.get_factory_toi().from_path_name(path, md5)
        if tb_toi is None:
            return None

        return self.decode_table_toi(tb_toi, HashMapDict({md5: path}))

    def from_hash_files(
        self, data: HashMap[hashFile, File], *, ignore_null: bool = True
    ) -> TableData[HeaderFilesTOI] | None:
        tb_toi = self.get_factory_toi().from_hash_files(data, ignore_null=ignore_null)
        if tb_toi is None:
            return None

        return self.decode_table_toi(tb_toi, data)


@dataclass
class IdNames:
    """
    Identificar os índices de cada elemento do nome de uma carta.

    2026 3 03 1488594 193258476 e 1488594 193258476 03 03 2026 são

    a mesma coisa porém nomeado com datas diferentes.
    """

    year: int = 0
    mon: int = 1
    day: int = 2
    uc: int = 3
    toi: int = 4


def create_table_from_ids(
    filename: str, md5: hashFile, *, ids: IdNames = IdNames()
) -> TableData[HeaderEntregaTOI]:

    # Separar os nomes em uma lista
    list_name: list[str] = filename.split(" ")

    # Gerar a data no formato dia mês ano.
    dt = f"{list_name[ids.day]} {list_name[ids.mon]} {list_name[ids.year]}"

    row = RowH[HeaderEntregaTOI, str](0)
    row.set(HeaderEntregaTOI.HASH_FILE, md5)
    row.set(HeaderEntregaTOI.UC, list_name[ids.uc])
    row.set(HeaderEntregaTOI.TOI, list_name[ids.toi])
    row.set(HeaderEntregaTOI.YEAR, list_name[ids.year])
    row.set(HeaderEntregaTOI.MON, list_name[ids.mon])
    row.set(HeaderEntregaTOI.DAY, list_name[ids.day])
    row.set(HeaderEntregaTOI.DATE, dt)
    tb = BuilderEntregaTOI().create_void()
    tb.add_row(row)
    return tb


# ============================================================#
# IDENTIFICAÇÃO v2: UC/TOI parcial, OCR tolerante, nome manual
# ============================================================#
#
# Tudo desta seção é NOVO e independente do fluxo antigo
# (extrair_uc_toi, add_hashs_on_table, ...). A UI pode migrar aos poucos.
#
# Ideia central: cada arquivo (HASH) gera um ResultadoUcToi que pode estar:
#   COMPLETO (uc+toi) | SO_UC | SO_TOI | NAO_IDENTIFICADO
#
# Fontes, em ordem de prioridade:
#   1) NOME do arquivo (identificação manual feita por uma pessoa);
#   2) CACHE (tabela-entregas-tois.xlsx, já processado antes);
#   3) OCR (extração tolerante, também aceita só UC ou só TOI).
# A data de entrega vem do nome, do cache ou da data de envio no WhatsApp.
#
# Regra de ouro do cache: um campo preenchido nunca é apagado por um
# resultado pior (merge_smart). Só o valor "manual" pode substituir outro.
#
# Formatos observados no OCR:
#   UC: 7 dígitos (ex.: 1305934)    TOI: 9 dígitos (ex.: 221673216)
# Aceitamos UC 6-8 e TOI 8-10 dígitos no OCR; números fora disso são lixo
# (ex.: "78534" ou "2936" são UCs truncadas pelo OCR e são descartadas).

_K_UC = HeaderEntregaTOI.UC.value
_K_TOI = HeaderEntregaTOI.TOI.value
_K_DAY = HeaderEntregaTOI.DAY.value
_K_MON = HeaderEntregaTOI.MON.value
_K_YEAR = HeaderEntregaTOI.YEAR.value
_K_DATE = HeaderEntregaTOI.DATE.value
_K_HASH = HeaderEntregaTOI.HASH_FILE.value

# Mesma ordem de BuilderEntregaTOI.default_cols_toi (sem instanciar o builder).
_COLS_ENTREGA: tuple[HeaderEntregaTOI, ...] = (
    HeaderEntregaTOI.UC,
    HeaderEntregaTOI.TOI,
    HeaderEntregaTOI.DATE,
    HeaderEntregaTOI.YEAR,
    HeaderEntregaTOI.MON,
    HeaderEntregaTOI.DAY,
    HeaderEntregaTOI.HASH_FILE,
)

# Grupos atualizados "em bloco" no merge.
_GRUPOS_MERGE: tuple[tuple[str, ...], ...] = (
    (_K_UC,),
    (_K_TOI,),
    (_K_DAY, _K_MON, _K_YEAR, _K_DATE),
)

_NULOS = {"", "nan", "none", "nat", "null", TableData.NULL_STRING.lower()}


def valor_nulo(v: Any) -> bool:
    """True para None, NaN, '', 'nan', 'NULL_TEXT' etc."""
    if v is None:
        return True
    try:
        if pd.isna(v):
            return True
    except (TypeError, ValueError):
        pass
    return str(v).strip().lower() in _NULOS


def limpar_numero(v: Any) -> str:
    """'1305934.0' -> '1305934'; nulo -> ''."""
    if valor_nulo(v):
        return ""
    s = str(v).strip()
    return s[:-2] if s.endswith(".0") else s


def uc_valida(v: str | None) -> bool:
    return bool(v) and re.fullmatch(r"[0-9]{6,8}", v) is not None


def toi_valido(v: str | None) -> bool:
    return bool(v) and re.fullmatch(r"[0-9]{8,10}", v) is not None


class StatusUcToi(StrEnum):
    COMPLETO = "COMPLETO"
    SO_UC = "SO_UC"
    SO_TOI = "SO_TOI"
    NAO_IDENTIFICADO = "NAO_IDENTIFICADO"


class OrigemUcToi(StrEnum):
    NOME_ARQUIVO = "nome_arquivo"
    CACHE = "cache"
    OCR = "ocr"
    MANUAL = "manual"
    NENHUMA = "nenhuma"


@dataclass
class ResultadoUcToi:
    """
    Resultado da identificação de UMA carta. Campo ausente = None
    (nunca 'NULL_TEXT'; essa conversão acontece só ao gravar a tabela).

    A data é guardada como day/mon/year (strings com zero à esquerda,
    ex.: '03', '03', '2026'), igual ao padrão do fluxo antigo.
    """

    uc: str | None = None
    toi: str | None = None
    day: str | None = None
    mon: str | None = None
    year: str | None = None
    origem: OrigemUcToi = OrigemUcToi.NENHUMA

    @property
    def data(self) -> str | None:
        """Data no formato DateValues.DATE_TOI ('%d %m %Y') ou None."""
        if self.day and self.mon and self.year:
            return f"{self.day} {self.mon} {self.year}"
        return None

    @property
    def completo(self) -> bool:
        return bool(self.uc and self.toi)

    @property
    def tem_dados(self) -> bool:
        return bool(self.uc or self.toi)

    @property
    def status(self) -> StatusUcToi:
        if self.uc and self.toi:
            return StatusUcToi.COMPLETO
        if self.uc:
            return StatusUcToi.SO_UC
        if self.toi:
            return StatusUcToi.SO_TOI
        return StatusUcToi.NAO_IDENTIFICADO

    def completar_com(self, outro: ResultadoUcToi | None) -> ResultadoUcToi:
        """Preenche SOMENTE o que está faltando aqui, usando 'outro'."""
        if outro is None:
            return self

        contribuiu = False
        if not self.uc and outro.uc:
            self.uc = outro.uc
            contribuiu = True
        if not self.toi and outro.toi:
            self.toi = outro.toi
            contribuiu = True
        if self.data is None and outro.data is not None:
            self.day, self.mon, self.year = outro.day, outro.mon, outro.year
            contribuiu = True

        if contribuiu and self.origem == OrigemUcToi.NENHUMA:
            self.origem = outro.origem
        return self

    def como_registro(self, hash_file: str) -> dict[str, str]:
        """Linha no formato da tabela TOI (HeaderEntregaTOI), nulos = NULL_TEXT."""
        nulo = TableData.NULL_STRING
        return {
            _K_UC: self.uc or nulo,
            _K_TOI: self.toi or nulo,
            _K_DATE: self.data or nulo,
            _K_YEAR: self.year or nulo,
            _K_MON: self.mon or nulo,
            _K_DAY: self.day or nulo,
            _K_HASH: str(hash_file),
        }

    @classmethod
    def from_record(
        cls, rec: Mapping[Any, Any], origem: OrigemUcToi = OrigemUcToi.CACHE
    ) -> ResultadoUcToi:
        def g(k: str) -> str | None:
            v = limpar_numero(rec.get(k))
            return v or None

        return cls(
            uc=g(_K_UC),
            toi=g(_K_TOI),
            day=g(_K_DAY),
            mon=g(_K_MON),
            year=g(_K_YEAR),
            origem=origem,
        )


# ------------------------------------------------------------#
# Extração tolerante no texto OCR (aceita só UC ou só TOI)
# ------------------------------------------------------------#
# UC : "UC", "Uc", "UG", "U0" + separador opcional + 6 a 8 dígitos
# TOI: "TOI", "TO!", "T0I", "TOK", "Tol", "To}" ... + separador + 8 a 10 dígitos
# O prefixo não pode estar colado em outra letra/número (evita "...AUC123").

_UC_OCR_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])U[CG0O]\s*[:;|!.,]?\s*(?<![0-9])([0-9]{6,8})(?![0-9])",
    re.IGNORECASE,
)

_TOI_OCR_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])T[O0][IK1Ll!|}\]]?\s*[:;|!.,]?\s*(?<![0-9])([0-9]{8,10})(?![0-9])",
    re.IGNORECASE,
)


def extrair_uc(texto: str) -> str | None:
    """Só a UC (tolerante a OCR). None se não encontrar uma UC plausível."""
    if not texto:
        return None
    m = _UC_OCR_PATTERN.search(texto)
    return m.group(1) if m else None


def extrair_toi(texto: str) -> str | None:
    """Só o TOI (tolerante a OCR). None se não encontrar um TOI plausível."""
    if not texto:
        return None
    m = _TOI_OCR_PATTERN.search(texto)
    return m.group(1) if m else None


def extrair_uc_toi_tolerante(texto: str) -> ResultadoUcToi:
    """
    Versão tolerante de extrair_uc_toi(): devolve o que for possível.

        'UC: 1462905 TOI: 210768466'  -> completo
        'pr 2936 TOI: 217678510'      -> só TOI (a UC truncada é descartada)
        'Uc: 2489141 To}: 21.'        -> só UC

    Primeiro usa extrair_uc_toi() (que já funciona bem) e valida o
    tamanho dos números; o que faltar é procurado de forma independente.
    """
    res = ResultadoUcToi(origem=OrigemUcToi.OCR)
    if not texto:
        return res

    antigo = extrair_uc_toi(texto)
    if antigo is not None:
        if uc_valida(antigo[0]):
            res.uc = antigo[0]
        if toi_valido(antigo[1]):
            res.toi = antigo[1]

    if res.uc is None:
        res.uc = extrair_uc(texto)
    if res.toi is None:
        res.toi = extrair_toi(texto)
    return res


# ------------------------------------------------------------#
# Identificação MANUAL pelo nome do arquivo
# ------------------------------------------------------------#
# Formatos aceitos (qualquer extensão pdf/imagem):
#   '2026 3 03 1488594 193258476'   ano mês dia uc toi
#   '1488594 193258476 03 03 2026'  uc toi dia mês ano
#   'UC 2489141'                    só UC
#   'TOI 217678510'                 só TOI
#   'UC 2489141 TOI 217678510'      os dois (sem data; a data vem do chat)
# Sufixos de colisão '-1', '-2' são ignorados.

_SEP_NOME = re.compile(r"[\s_]+")
_EXT_NOME = re.compile(r"\.(pdf|png|jpe?g|svg)$", re.IGNORECASE)
_COLISAO_NOME = re.compile(r"-\d{1,2}$")

_UC_NOME_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])UC[\s:._-]*([0-9]{4,10})(?![0-9])", re.IGNORECASE
)
_TOI_NOME_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])TOI[\s:._-]*([0-9]{4,12})(?![0-9])", re.IGNORECASE
)

# (year, mon, day, uc, toi) -> índices nos 5 números do nome
_LAYOUTS_NOME: tuple[tuple[int, int, int, int, int], ...] = (
    (0, 1, 2, 3, 4),  # ano mês dia uc toi
    (4, 3, 2, 0, 1),  # uc toi dia mês ano
)


def normalizar_data(year: Any, mon: Any, day: Any) -> tuple[str, str, str] | None:
    """Valida e devolve (day, mon, year) com zero à esquerda, ou None."""
    try:
        y, m, d = int(str(year).strip()), int(str(mon).strip()), int(str(day).strip())
        datetime(y, m, d)
    except (ValueError, TypeError, OverflowError):
        return None
    if not (2000 <= y <= 2100):
        return None
    return f"{d:02d}", f"{m:02d}", str(y)


def parse_data_entrega(valor: Any) -> tuple[str, str, str] | None:
    """Converte 'dd mm yyyy', 'dd/mm/yyyy', 'yyyy-mm-dd'... em (day, mon, year)."""
    if valor_nulo(valor):
        return None
    s = str(valor).strip()
    for fmt in ("%d %m %Y", "%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y"):
        try:
            dt = datetime.strptime(s, fmt)
        except ValueError:
            continue
        return normalizar_data(dt.year, dt.month, dt.day)
    return None


def identificar_por_nome(filename: str) -> ResultadoUcToi | None:
    """
    Identifica UC/TOI/data pelo NOME do arquivo (trabalho manual de uma
    pessoa). Retorna None se o nome não segue nenhum formato conhecido.
    """
    if not filename:
        return None

    nome = os.path.basename(str(filename)).strip()
    nome = _EXT_NOME.sub("", nome)
    nome = _COLISAO_NOME.sub("", nome).strip()

    # 1) Cinco números: data + UC + TOI (nos dois formatos).
    tokens = [t for t in _SEP_NOME.split(nome) if t]
    if len(tokens) == 5 and all(t.isascii() and t.isdigit() for t in tokens):
        for iy, im, idy, iuc, itoi in _LAYOUTS_NOME:
            data = normalizar_data(tokens[iy], tokens[im], tokens[idy])
            if data is None:
                continue
            uc, toi = tokens[iuc], tokens[itoi]
            if not (4 <= len(uc) <= 10 and 4 <= len(toi) <= 12):
                continue
            return ResultadoUcToi(
                uc=uc,
                toi=toi,
                day=data[0],
                mon=data[1],
                year=data[2],
                origem=OrigemUcToi.NOME_ARQUIVO,
            )

    # 2) Rótulos explícitos: 'UC 123...' e/ou 'TOI 123...'.
    m_uc = _UC_NOME_PATTERN.search(nome)
    m_toi = _TOI_NOME_PATTERN.search(nome)
    if m_uc or m_toi:
        return ResultadoUcToi(
            uc=m_uc.group(1) if m_uc else None,
            toi=m_toi.group(1) if m_toi else None,
            origem=OrigemUcToi.NOME_ARQUIVO,
        )
    return None


# ------------------------------------------------------------#
# Resultados <-> tabelas
# ------------------------------------------------------------#


def _df_para_tabela_entrega(df: pd.DataFrame) -> TableData[HeaderEntregaTOI]:
    """DataFrame (colunas str ou enum) -> TableData com cabeçalho padrão."""
    df = df[[c.value for c in _COLS_ENTREGA]].astype(str).reset_index(drop=True)
    df.columns = pd.Index(list(_COLS_ENTREGA), dtype=object)
    return TableData[HeaderEntregaTOI](df)


def tabela_entrega_de_resultados(
    resultados: Mapping[str, ResultadoUcToi], *, somente_com_dados: bool = True
) -> TableData[HeaderEntregaTOI] | None:
    """
    Converte {hash: ResultadoUcToi} em TableData[HeaderEntregaTOI].
    Com somente_com_dados=True ignora quem não tem UC nem TOI.
    """
    registros = [
        r.como_registro(h)
        for h, r in resultados.items()
        if (r.tem_dados or not somente_com_dados)
    ]
    if not registros:
        return None
    return _df_para_tabela_entrega(pd.DataFrame(registros))


def create_table_from_name(
    filename: str, md5: hashFile
) -> TableData[HeaderEntregaTOI] | None:
    """
    Versão segura de create_table_from_ids(): usa identificar_por_nome(),
    aceita os dois formatos de nome, UC/TOI parciais e nunca levanta
    IndexError. Retorna None se o nome não identifica nada.
    """
    r = identificar_por_nome(filename)
    if r is None or not r.tem_dados:
        return None
    return tabela_entrega_de_resultados({md5: r})


# ========================================================#
# Relatórios TOI.
# ========================================================#


class ReadWriteTableTOI(object):
    """
    Leitura e escrita de dados na TOI em cache. A tabela em cache contém
    o cabeçalho HeaderEntregaTOI:
        UC, TOI, DAY, MON, YEAR, DATE E HASH_FILE.

    Campos ausentes são gravados como TableData.NULL_STRING.
    """

    _instance = None  # Atributo de classe para armazenar a instância singleton

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ReadWriteTableTOI, cls).__new__(cls)
        return cls._instance

    def __init__(self) -> None:

        # Garante que __init__ não será executado mais de uma vez
        if hasattr(self, "_initialized") and self._initialized:
            return
        super().__init__()

        self._initialized: bool = True
        self.builder: BuilderConfigTOI = BuilderConfigTOI()
        self._tb_toi: TableData[HeaderEntregaTOI] = None

    @property
    def file_table_toi(self) -> File:
        return BuilderConfigTOI().builder().file_table_toi

    def set_table_toi(self, tb: TableData[HeaderEntregaTOI]):
        self._tb_toi = tb

    def get_table_toi(self) -> TableData[HeaderEntregaTOI]:
        if self._tb_toi is not None:
            return self._tb_toi

        f = self.file_table_toi
        if not f.exists():
            self._tb_toi = BuilderTableFilesTOI().get_factory_toi().create_void()
            return self._tb_toi

        print(f"Lendo tabela TOI em cache ... {f.absolute()}")
        # dtype=str preserva UC/TOI como texto (sem virar float/int).
        data = pd.read_excel(f.absolute(), dtype=str).fillna(TableData.NULL_STRING)
        data = data.drop_duplicates(subset=[HeaderFilesTOI.HASH_FILE.value])

        # self._tb_toi = TableTOI.create_from_data(data)
        self._tb_toi = BuilderEntregaTOI().from_data(data)
        return self._tb_toi

    # ---------------------------------------------------------- consulta
    def get_resultados(self, hashes: Iterable[str]) -> dict[str, ResultadoUcToi]:
        """{hash: ResultadoUcToi} das hashs que já estão no cache TOI."""
        wanted = {str(h) for h in hashes}
        if not wanted:
            return {}

        df = self.get_table_toi().to_dataframe()
        if df.empty:
            return {}

        sub = df[df[_K_HASH].astype(str).isin(wanted)]
        out: dict[str, ResultadoUcToi] = {}
        for rec in sub.to_dict("records"):
            h = str(rec.get(_K_HASH))
            if h not in out:  # em duplicatas vale a primeira
                out[h] = ResultadoUcToi.from_record(rec, OrigemUcToi.CACHE)
        return out

    # ---------------------------------------------------------- escrita
    def merge_smart(
        self, tb: TableData[HeaderEntregaTOI], *, override: bool = False
    ) -> int:
        """
        Incorpora tb ao cache SEM piorar o que já existe, por HASH:

          * hash nova                       -> entra;
          * campo vazio no cache            -> é preenchido (UC, TOI e data,
                                               a data é tratada em bloco);
          * campo já preenchido no cache    -> só muda se override=True
                                               (use para valores manuais);
          * valor nulo em tb               -> nunca apaga o cache.

        Só grava o arquivo se algo mudou. Retorna quantas linhas mudaram.
        """
        if tb is None or tb.is_empty():
            return 0

        cols = [c.value for c in _COLS_ENTREGA]
        nulo = TableData.NULL_STRING

        def normalizar(rec: Mapping[Any, Any]) -> dict[str, str]:
            return {
                c: (nulo if valor_nulo(rec.get(c)) else limpar_numero(rec.get(c)))
                for c in cols
            }

        mapa: dict[str, dict[str, str]] = {}
        ordem: list[str] = []

        atual = self.get_table_toi().to_dataframe()
        for rec in atual.to_dict("records"):
            r = normalizar(rec)
            h = r[_K_HASH]
            if h == nulo or h in mapa:
                continue
            mapa[h] = r
            ordem.append(h)

        alterados = 0
        for rec in tb.to_dataframe().to_dict("records"):
            n = normalizar(rec)
            h = n[_K_HASH]
            if h == nulo:
                continue

            r = mapa.get(h)
            if r is None:
                mapa[h] = n
                ordem.append(h)
                alterados += 1
                continue

            mudou = False
            for grupo in _GRUPOS_MERGE:
                if any(n[c] == nulo for c in grupo):
                    continue  # novo valor incompleto: ignora
                atual_ok = all(r[c] != nulo for c in grupo)
                diferente = any(r[c] != n[c] for c in grupo)
                if (not atual_ok) or (override and diferente):
                    for c in grupo:
                        r[c] = n[c]
                    mudou = True
            if mudou:
                alterados += 1

        if alterados == 0:
            return 0

        df = pd.DataFrame([mapa[h] for h in ordem], columns=cols)
        self._tb_toi = _df_para_tabela_entrega(df)
        self.save()
        return alterados

    def merge(self, tb: TableData[HeaderEntregaTOI], *, override: bool = False) -> None:
        """
        Compatível com a API antiga, mas agora usa merge_smart(): um
        resultado novo NUNCA apaga/piora dados já existentes no cache
        (ex.: valores corrigidos manualmente). Use override=True para
        forçar a substituição dos campos preenchidos.
        """
        if tb.is_empty():
            return None

        print(f"Mergeando tabela TOI ... {self.file_table_toi.absolute()}")
        self.merge_smart(tb, override=override)

    def save(self) -> None:
        data = self.get_table_toi().to_dataframe()
        path = self.file_table_toi.absolute()
        tmp_file = f"{path}-tmp.xlsx"

        print(f"Salvando tabela TOI ... {path}")
        self.file_table_toi.parent().mkdir()
        data.to_excel(tmp_file, index=False)
        replace_file(tmp_file, path)  # atômico e portável (rename falha no Windows)


class ControllerTOI(object):
    """
        Cria uma tabela de Cartas TOI apartir dos chats do WhatsApp.
    Conectando os arquivos das conversas aos textos extraídos via OCR.

    TableWhatsApp() é usado para obter DATA e HORA do envio de um arquivo
    no chat, pois a data de envio no chat e a data de entrega de uma carta em campo.

    Fluxo antigo : add_hashs_on_table() / find_on_cache() / load_from_map()
    Fluxo novo   : resolver_hashes() / identificar_arquivos() / load_from_map_v2()
                   (aceita UC/TOI parcial, nome de arquivo e usa o cache antes
                   de qualquer reprocessamento).
    """

    def __init__(self) -> None:
        self.builder_toi_files: BuilderTableFilesTOI = BuilderTableFilesTOI()
        self.builder_config: BuilderConfigTOI = BuilderConfigTOI()
        self.rw: ReadWriteTableTOI = ReadWriteTableTOI()

    @property
    def relatorio_whatsapp(self) -> ControllerWhatsApp:
        return self.get_factory_toi().relatorio_wp

    @property
    def relatorio_ocr(self) -> ReadTablesOcr:
        return self.get_factory_toi().relatorio_ocr

    def get_factory_toi(self) -> BuilderEntregaTOI:
        return self.builder_toi_files.get_factory_toi()

    # --------------------------------------------------#
    # Consultar dados - READ
    # --------------------------------------------------#
    def load_table_whatsapp(self) -> TableWhatsApp:
        return self.relatorio_whatsapp.load_cache_table()

    def load_table_toi(self) -> TableData[HeaderEntregaTOI]:
        return self.rw.get_table_toi()

    def find_on_cache(
        self, data: HashMap[hashFile, File], *, apenas_completos: bool = False
    ) -> TableData[HeaderFilesTOI]:
        """
        Procura os textos de cada arquivo na tabela OCR apartir da hash e retorna
        os dados no formato TableData()

        apenas_completos=True devolve só linhas com UC, TOI e data.
        """

        if data.is_empty():
            return self.builder_toi_files.create_void()

        tb_cache: TableData[HeaderEntregaTOI] = self.load_table_toi()
        if tb_cache.is_empty():
            return self.builder_toi_files.create_void()

        content_cache: TableData | None = tb_cache.search_all(
            HeaderEntregaTOI.HASH_FILE, data.header()
        )

        if content_cache is None:
            return self.builder_toi_files.create_void()

        df_cache = content_cache.to_dataframe()

        if apenas_completos and not df_cache.empty:
            ok = ~(
                df_cache[_K_UC].map(valor_nulo)
                | df_cache[_K_TOI].map(valor_nulo)
                | df_cache[_K_DATE].map(valor_nulo)
            )
            df_cache = df_cache[ok]
            if df_cache.empty:
                return self.builder_toi_files.create_void()

        builder = BuilderEntregaTOI()

        final = self.builder_toi_files.decode_table_toi(
            builder.from_data(df_cache), data
        )

        if final is None:
            return self.builder_toi_files.create_void()
        return final

    def load_from_map(
        self, data_map: HashMapDict[hashFile, File], *, ignore_null: bool = True
    ) -> TableData[HeaderFilesTOI] | None:
        """
        I) Usa a HASH MD5 dos arquivos para buscar a data de envio do arquivo na
        tabela whatsapp;

        II) Gera um relatório OCR com os metadados básicos
        de cada arquivo;

        III) Obtem a UC e TOI de cada arquivo.

        IV) Retorna uma tabela apartir dos dados gerados.

        Observação:
            Se o parametro ignore_null for True as linhas que contém UC e TOI inválidos
        serão ignorados.
        """

        if data_map.is_empty():
            return None

        final_table: TableData[HeaderFilesTOI] | None = (
            self.builder_toi_files.from_hash_files(data_map, ignore_null=ignore_null)
        )
        if final_table is None:
            return None

        df = final_table.to_dataframe().drop_duplicates(
            subset=[HeaderFilesTOI.HASH_FILE.value]
        )

        if ignore_null:
            df = df[df[HeaderFilesTOI.UC] != TableData.NULL_STRING]

        return self.builder_toi_files.from_data(df)

    # --------------------------------------------------#
    # Criar dados - CREATE
    # --------------------------------------------------#
    def add_hashs_on_table(
        self, hash_files: Set[hashFile], *, ignore_null: bool = True
    ) -> None:
        """
        I) Analisa arquivos TOI apartir da HASH MD5, pesquisa o texto de cada
        hash na tabela OCR e extrai UC e TOI;

        II) Na sequência, usa a hash para encontrar a data de envio do arquivo no chat
        do whatsapp;

        III) Inclui os dados TOI de cada arquivo na tabela TOI em cache.
        """
        if hash_files.empty():
            print("Lista de arquivos vazia, nada a fazer!")
            return None

        # Filtrar
        # Filtrar: imagem + pdf, só as hashs pedidas (cópia, sem mexer no cache)
        cache_ocr: TableData[HeaderOcr] | None = self.relatorio_ocr.create_from_hashs(
            hash_files
        )

        if cache_ocr is None:
            return None

        # cache_ocr = cache_ocr.drop_duplicates()
        table_whatsapp: TableWhatsApp = self.load_table_whatsapp()

        # Cada arquivo gera/extrai a sua própria tabela, ao final essa
        # lista de tabelas serão concatenadas em uma tabela única.
        list_tables_toi = ArrayTables[TableData[HeaderEntregaTOI]]()
        total = hash_files.size()
        k: hashFile

        print(f"[Pesquisando texto OCR] em {total} arquivos")
        for n, k in enumerate(hash_files):

            current_table_ocr: TableData[HeaderOcr] = cache_ocr.search(
                HeaderOcr.HASH_FILE, k
            )

            text_ocr: str = None

            if not current_table_ocr.is_empty():
                text_ocr = current_table_ocr.to_string(HeaderOcr.TEXT)

            txt_uc_toi: tuple | None = (
                extrair_uc_toi(text_ocr) if text_ocr is not None else None
            )

            if txt_uc_toi is None:
                if ignore_null:
                    continue

            uc = TableData.NULL_STRING
            toi = TableData.NULL_STRING
            year = TableData.NULL_STRING
            mon = TableData.NULL_STRING
            day = TableData.NULL_STRING
            dt: str = TableData.NULL_STRING

            if txt_uc_toi is not None:
                uc = txt_uc_toi[0]
                toi = txt_uc_toi[1]

            # Obter os dados no arquivo no chat whatsapp apartir da hash md5
            current_table_whatsapp = table_whatsapp.search(HeaderWhatsApp.hash_md5, k)

            if not current_table_whatsapp.is_empty():
                # Arquivo encontrado no chat. Extrair dados da data de envio.
                dt = current_table_whatsapp.get_row_at(0).get_date().get_first()
                day = dt.split(" ")[0]
                mon = dt.split(" ")[1]
                year = dt.split(" ")[2]

            if ignore_null:
                if dt == TableData.NULL_STRING:
                    continue

            tb_toi: TableData[HeaderEntregaTOI] = self.get_factory_toi().create_void()
            row_forms = RowH[HeaderEntregaTOI, Any](0)

            row_forms.set(HeaderEntregaTOI.UC, uc)
            row_forms.set(HeaderEntregaTOI.TOI, toi)
            row_forms.set(HeaderEntregaTOI.YEAR, year)
            row_forms.set(HeaderEntregaTOI.MON, mon)
            row_forms.set(HeaderEntregaTOI.DAY, day)
            row_forms.set(HeaderEntregaTOI.DATE, dt)
            row_forms.set(HeaderEntregaTOI.HASH_FILE, k)

            tb_toi.add_row(row_forms)
            list_tables_toi.add(tb_toi)

        if list_tables_toi.empty():
            return None

        final = list_tables_toi.concat(TableData).drop_duplicates()
        self.rw.merge(final)

    @staticmethod
    def filter_uc_toi(
        hf: hashFile, table_ocr_file: TableData[HeaderOcr]
    ) -> tuple[str, str] | None:
        """
        Filtra UC e TOI de uma carta apartir do texto OCR extraído.
        """
        tb_current_hash = table_ocr_file.search(HeaderOcr.HASH_FILE, hf)
        if tb_current_hash.is_empty():
            return None

        values = tb_current_hash.get(HeaderOcr.TEXT)._elements

        for v in values:
            txt = extrair_uc_toi(v)
            if txt is not None:
                return txt
        return None

    # ==================================================#
    # FLUXO NOVO (v2)
    # ==================================================#
    def _textos_ocr(self, hashes: Iterable[str]) -> dict[str, str]:
        """{hash: texto OCR completo} somente do cache (nunca aplica OCR)."""
        alvo = Set(str(h) for h in hashes)
        if alvo.empty():
            return {}

        tb = self.relatorio_ocr.create_from_hashs(alvo)
        if tb is None or tb.is_empty():
            return {}

        c_hash = HeaderOcr.HASH_FILE.value
        c_pag = HeaderOcr.NUM_PAG.value
        c_lin = HeaderOcr.NUM_LINHA.value
        c_txt = HeaderOcr.TEXT.value

        df = tb.to_dataframe().astype(str)
        df = df[df[c_txt] != TableData.NULL_STRING].copy()
        if df.empty:
            return {}

        df["_p"] = pd.to_numeric(df[c_pag], errors="coerce").fillna(0)
        df["_l"] = pd.to_numeric(df[c_lin], errors="coerce").fillna(0)
        df = df.sort_values(["_p", "_l"], kind="stable")

        return {
            str(h): " ".join(g[c_txt].tolist())
            for h, g in df.groupby(c_hash, sort=False)
        }

    def _datas_whatsapp(self, hashes: Iterable[str]) -> dict[str, tuple[str, str, str]]:
        """{hash: (day, mon, year)} da data de envio no chat (primeira ocorrência)."""
        alvo = {str(h) for h in hashes}
        if not alvo:
            return {}

        tb = self.load_table_whatsapp()
        if tb.is_empty():
            return {}

        df = tb.to_dataframe()
        df = df[df[HeaderWhatsApp.hash_md5.value].isin(alvo)]
        if df.empty:
            return {}

        df = df.drop_duplicates(subset=[HeaderWhatsApp.hash_md5.value], keep="first")
        datas = pd.to_datetime(df[HeaderWhatsApp.date_hour.value], errors="coerce")

        out: dict[str, tuple[str, str, str]] = {}
        for h, dt in zip(df[HeaderWhatsApp.hash_md5.value], datas):
            if pd.isna(dt):
                continue
            out[str(h)] = (f"{dt.day:02d}", f"{dt.month:02d}", str(dt.year))
        return out

    def resolver_hashes(
        self,
        data_map: HashMap[hashFile, File],
        *,
        usar_nome: bool = True,
        usar_ocr: bool = True,
        usar_whatsapp: bool = True,
        gravar_cache: bool = True,
    ) -> HashMapDict[hashFile, ResultadoUcToi]:
        """
        Identifica UC/TOI/data de cada arquivo de data_map ({hash: File}).

        Ordem de prioridade (cada fonte só preenche o que ainda falta):
          1) nome do arquivo (identificação manual);
          2) cache TOI (já processado, nada é refeito);
          3) texto OCR em cache (UC/TOI, aceita só um dos dois);
          4) data de envio no chat do WhatsApp.

        Se gravar_cache=True, tudo que tem UC ou TOI é gravado na tabela TOI
        com merge_smart(): nunca piora o que já existia, e o nome manual
        corrige valores antigos. Arquivos sem nenhum número NÃO são gravados
        (o texto OCR já está em cache, reextrair é barato e melhora sozinho
        quando o extrator evolui).

        Retorna {hash: ResultadoUcToi} para TODOS os hashes de data_map.
        """
        if data_map.is_empty():
            return HashMapDict()

        hashes: ArrayList[hashFile] = data_map.header()
        cache = self.rw.get_resultados(hashes)
        res: dict[str, ResultadoUcToi] = {}

        for h in hashes:
            r = ResultadoUcToi()
            if usar_nome:
                r.completar_com(identificar_por_nome(data_map.get_value(h).name()))
            r.completar_com(cache.get(h))
            res[h] = r

        # --- OCR: só para quem ainda não tem UC e TOI
        if usar_ocr:
            faltam = [h for h in hashes if not res[h].completo]
            if faltam:
                for h, txt in self._textos_ocr(faltam).items():
                    if h in res:
                        res[h].completar_com(extrair_uc_toi_tolerante(txt))

        # --- Data de envio no chat: só para quem ainda não tem data
        if usar_whatsapp:
            sem_data = [h for h in hashes if res[h].data is None]
            if sem_data:
                for h, (d, m, y) in self._datas_whatsapp(sem_data).items():
                    if h in res:
                        res[h].day, res[h].mon, res[h].year = d, m, y

        if gravar_cache:
            tb = tabela_entrega_de_resultados(res)
            if tb is not None:
                # 'res' já respeita a prioridade nome > cache > ocr.
                self.rw.merge_smart(tb, override=True)

        return HashMapDict(res)

    def identificar_arquivos(
        self, files: Iterable[File], **opcoes: Any
    ) -> HashMapDict[hashFile, ResultadoUcToi]:
        """Atalho: calcula as hashs dos arquivos e chama resolver_hashes()."""
        data_map = HashMapDict[hashFile, File]()
        for f in files:
            data_map.set_value(load_file_hash(f), f)
        return self.resolver_hashes(data_map, **opcoes)

    def load_from_map_v2(
        self,
        data_map: HashMapDict[hashFile, File],
        *,
        permitir_parcial: bool = False,
        **opcoes: Any,
    ) -> TableData[HeaderFilesTOI] | None:
        """
        Equivalente novo de load_from_map() (mesmo tipo de retorno).

        permitir_parcial=False: só linhas com UC, TOI e data (úteis p/ Forms).
        permitir_parcial=True : também linhas com só UC ou só TOI (organização).
        """
        if data_map.is_empty():
            return None

        res = self.resolver_hashes(data_map, **opcoes).map
        if permitir_parcial:
            validos = {h: r for h, r in res.items() if r.tem_dados}
        else:
            validos = {h: r for h, r in res.items() if r.completo and r.data}

        tb = tabela_entrega_de_resultados(validos)
        if tb is None:
            return None
        return self.builder_toi_files.decode_table_toi(tb, data_map)

    def registrar_manual(
        self,
        hash_file: hashFile,
        *,
        uc: str | None = None,
        toi: str | None = None,
        data: str | None = None,
    ) -> bool:
        """
        Grava no cache dados digitados por uma pessoa (têm prioridade sobre
        qualquer valor existente). 'data' aceita 'dd/mm/yyyy', 'dd mm yyyy'
        ou 'yyyy-mm-dd'. Retorna True se algo mudou no cache.
        """
        r = ResultadoUcToi(
            uc=limpar_numero(uc) or None,
            toi=limpar_numero(toi) or None,
            origem=OrigemUcToi.MANUAL,
        )
        d = parse_data_entrega(data)
        if d is not None:
            r.day, r.mon, r.year = d

        tb = tabela_entrega_de_resultados({str(hash_file): r})
        if tb is None:
            return False
        return self.rw.merge_smart(tb, override=True) > 0

    def buscar_numero(self, numero: str, *, incluir_ocr: bool = True) -> pd.DataFrame:
        """
        Procura um número (UC ou TOI, inclusive parcial/incompleto) e responde
        "essa carta já foi entregue?":

          * no cache TOI (colunas uc/toi);
          * no texto OCR (hashs que ainda não estão no cache TOI).

        Colunas: HASH_FILE, uc, toi, data_entrega, origem ('cache' | 'ocr').
        """
        cols = [_K_HASH, _K_UC, _K_TOI, _K_DATE, "origem"]
        alvo = limpar_numero(numero)
        if not alvo:
            return pd.DataFrame(columns=cols)

        frames: list[pd.DataFrame] = []
        hashes_cache: set[str] = set()

        df = self.rw.get_table_toi().to_dataframe()
        if not df.empty:
            df = df.astype(str)
            achados = df[(df[_K_UC] == alvo) | (df[_K_TOI] == alvo)].copy()
            if not achados.empty:
                achados["origem"] = "cache"
                hashes_cache = set(achados[_K_HASH].tolist())
                frames.append(achados[cols])

        if incluir_ocr:
            nulo = TableData.NULL_STRING
            c_hash, c_txt = HeaderOcr.HASH_FILE.value, HeaderOcr.TEXT.value
            for tb in (
                self.relatorio_ocr.load_table_image(),
                self.relatorio_ocr.load_table_pdf(),
            ):
                dfo = tb.get_data()
                if dfo.empty:
                    continue
                m = dfo[
                    dfo[c_txt].astype(str).str.contains(alvo, regex=False, na=False)
                ]
                hs = {
                    h for h in m[c_hash].astype(str).tolist() if h not in hashes_cache
                }
                if hs:
                    frames.append(
                        pd.DataFrame(
                            {
                                _K_HASH: sorted(hs),
                                _K_UC: nulo,
                                _K_TOI: nulo,
                                _K_DATE: nulo,
                                "origem": "ocr",
                            }
                        )[cols]
                    )
                    hashes_cache |= hs

        if not frames:
            return pd.DataFrame(columns=cols)
        return pd.concat(frames, ignore_index=True)


def load_files_toi(files: Set[File]) -> TableData[HeaderFilesTOI] | None:
    """
    I) Analisa arquivos TOI apartir da HASH MD5;
    II) Compara o texto na tabela OCR e inclui, UC e TOI na tabela TOI principal;
    III) Retorna os dados no formato de tabela TOI.
    """

    if files.empty():
        print(f"[DEBUG]: load_files_toi() lista de arquivos vazia!")
        return None

    f: File
    for f in files:
        if (not f.is_image()) and (not f.is_pdf()):
            raise ValueError(
                f"Tipo de documento TOI inválido, use PDF ou Imagem não: {f.extension()}"
            )

    data_map = HashMapDict[hashFile, File]()
    files.for_each(lambda f: data_map.set_value(load_file_hash(f), f))

    controller = ControllerTOI()
    heder_hash = data_map.header()
    controller.add_hashs_on_table(heder_hash.to_set())
    return controller.find_on_cache(data_map)


def load_files_toi_v2(
    files: Set[File], *, permitir_parcial: bool = False, **opcoes: Any
) -> TableData[HeaderFilesTOI] | None:
    """
    Equivalente novo de load_files_toi(): usa nome do arquivo + cache + OCR
    tolerante + data do chat, e grava o que descobriu no cache TOI.
    """
    if files.empty():
        print("[DEBUG]: load_files_toi_v2() lista de arquivos vazia!")
        return None

    f: File
    for f in files:
        if (not f.is_image()) and (not f.is_pdf()):
            raise ValueError(
                f"Tipo de documento TOI inválido, use PDF ou Imagem não: {f.extension()}"
            )

    data_map = HashMapDict[hashFile, File]()
    files.for_each(lambda f: data_map.set_value(load_file_hash(f), f))

    return ControllerTOI().load_from_map_v2(
        data_map, permitir_parcial=permitir_parcial, **opcoes
    )


def get_file_log(base_dir: Directory) -> File:
    _dt = datetime.now()
    y = str(_dt.year)
    m = str(_dt.month)
    day = str(_dt.day)
    current_date = f"{y}-{m}-{day}"
    dir_log: Directory = base_dir.concat(y, True).concat(f"{y}-{m}", True)
    return dir_log.join_file(f"{current_date}.xlsx")


def get_date_from_row(r: RowH[HeaderFilesTOI, Any]) -> tuple[str, str, str] | None:
    """
    Retorna uma tupla de data no formato (ANO, MÊS, DIA)
    """

    y = r.get(HeaderFilesTOI.YEAR)
    m = r.get(HeaderFilesTOI.MON)
    d = r.get(HeaderFilesTOI.DAY)

    if len(m) > 1:
        if m[0] == "0":
            m = m[1]

    values = (y, m, d)
    i: str
    for i in values:
        if not i.isnumeric():
            return None
    return values


def _resolver_colisao_arquivo(dest: File) -> File:
    """Se dest existe, devolve 'nome-1.ext', 'nome-2.ext'... (primeiro livre)."""
    if not dest.exists():
        return dest
    base, ext = os.path.splitext(dest.absolute())
    n = 1
    novo = File(f"{base}-{n}{ext}")
    while novo.exists():
        n += 1
        novo = File(f"{base}-{n}{ext}")
    return novo


class RenameFilesTOI:
    """
    Organiza cartas TOI e registra o resultado de cada movimentação.

    Destinos:
        UC + TOI + data  -> <base>/ano/ano-mês/ano-mês-dia/'ano mês dia uc toi'
        UC + TOI s/ data -> CARTAS_DATA_NAO_ENCONTRADA/'uc toi'
        só UC            -> CARTAS_SO_UC/'UC <uc> [data] <hash8>'
        só TOI           -> CARTAS_SO_TOI/'TOI <toi> [data] <hash8>'
        nada             -> CARTAS_UC_NAO_IDENTIFICADAS/<hash>

    modo_v2=True usa resolver_hashes() (nome do arquivo + cache + OCR
    tolerante + chat) e nunca sobrescreve um arquivo diferente com o mesmo
    nome de destino (acrescenta -1, -2...). modo_v2=False mantém o fluxo antigo.
    """

    def __init__(self, files: Set[File], *, modo_v2: bool = True) -> None:
        self.config: ConfigTOI = BuilderConfigTOI().builder()
        self.files = files
        self.modo_v2: bool = modo_v2
        self.file_log: File = get_file_log(self.config.dir_log_excel)

        self.base_cartas: Directory = self.config.dir_base_toi
        self.error_uc_dir: Directory = self.base_cartas.concat(
            "UCS_NAO_IDENTIFICADAS", True
        )
        self.error_date_dir: Directory = self.base_cartas.concat(
            "DATA_NAO_ENCONTRADA", True
        )

        self.map_files: HashMapDict[hashFile, File] = HashMapDict()
        self.table_status = TableData.create_void(
            [HeaderFilesTOI.HASH_FILE.value, "src", "dest", "status", "exception"]
        )

    def process_error_ucs(self):
        tb_wp = ControllerWhatsApp().load_cache_table()
        content = ContentFiles(self.error_uc_dir)
        files = content.get_files()

        content_map = HashMapDict[hashFile, File]()
        files.for_each(lambda f: content_map.set_value(load_file_hash(f), f))

        content_chat = tb_wp.search_all(HeaderWhatsApp.hash_md5, content_map.header())

        if content_chat is None:
            return
        if content_chat.is_empty():
            return

        rows = (
            BuilderTableWhatsApp().create_from_data(content_chat.to_dataframe()).rows()
        )

        r: RowWhatsApp
        for r in rows:
            h = r.get(HeaderWhatsApp.hash_md5)
            file_path: File = content_map.get_value(h)

            dt: datetime = r.get_date_hour()
            y = str(dt.year)
            m = f"{dt.month:02d}"

            # ano/ano-mes/arquivo
            current_dir = self.error_uc_dir.concat(y).concat(f"{y}-{m}", True)
            final_path: File = _resolver_colisao_arquivo(
                current_dir.join_file(file_path.basename())
            )

            try:
                move_path(file_path, final_path)
            except Exception as e:
                print(f"{__class__.__name__}(): {e}")

        """
        r: RowWhatsApp
        for r in rows:
            h = r.get(HeaderWhatsApp.hash_md5)
            file_path: File = content_map.get_value(h)

            dt: datetime = r.get_date_hour()
            y = str(dt.year)
            m = str(dt.month)
            d = str(dt.day)
            _date = f"{y}-{m}-{d}"

            current_dir = self.error_uc_dir.concat(y).concat(m).concat(_date, True)
            final_path: File = current_dir.join_file(file_path.basename())

            try:
                move_path(file_path, final_path)
            except Exception as e:
                print(f"{__class__.__name__}(): {e}")
        """

    def _index_files(self) -> None:
        """Indexa os arquivos originais por hash."""
        for file in self.files:
            self.map_files.set_value(load_file_hash(file), file)

    def _create_status_row(self, file_hash: hashFile, src: File, dest: File) -> RowH:
        row = RowH(0)
        row.set(HeaderFilesTOI.HASH_FILE.value, file_hash)
        row.set("src", src.absolute())
        row.set("dest", dest.absolute())
        return row

    def _move(self, file_hash: hashFile, src: File, dest: File) -> bool:
        """Move o arquivo e registra o resultado real da operação."""
        row = self._create_status_row(file_hash, src, dest)

        try:
            if not move_path(src, dest):
                raise OSError(
                    f"move_path retornou False: {src.absolute()} -> {dest.absolute()}"
                )
        except Exception as exc:
            row.set("status", "FALHA")
            row.set("exception", str(exc))
            success = False
        else:
            row.set("status", "SUCESSO")
            row.set("exception", "")
            success = True

        self.table_status.add_row(row)
        return success

    @staticmethod
    def _is_missing(value: Any) -> bool:
        return (
            value is None
            or pd.isna(value)
            or value == TableData.NULL_STRING
            or str(value).strip() == ""
        )

    def _get_destination(self, row: RowH) -> tuple[Directory, str]:
        """Define o destino com prioridade para a ausência de UC."""
        uc = row.get(HeaderFilesTOI.UC)
        toi = row.get(HeaderFilesTOI.TOI)
        date = get_date_from_row(row)
        file_hash = str(row.get(HeaderFilesTOI.HASH_FILE))

        has_uc = not self._is_missing(uc)
        has_toi = not self._is_missing(toi)

        if not has_uc and not has_toi:
            return self.error_uc_dir, file_hash

        # Identificação parcial: o número fica no nome para poder ser pesquisado.
        if not (has_uc and has_toi):
            if has_uc:
                folder, label, number = "CARTAS_SO_UC", "UC", uc
            else:
                folder, label, number = "CARTAS_SO_TOI", "TOI", toi

            sufixo = f" {date[0]} {date[1]} {date[2]}" if date is not None else ""
            name = f"{label} {number}{sufixo} {file_hash[:8]}"
            return self.base_cartas.concat(folder, True), name

        if date is None:
            return self.error_date_dir, f"{uc} {toi}"

        year, month, day = date
        # dest_dir = (
        #    self.base_cartas.concat(year)
        #    .concat(f"{year}-{month}")
        #    .concat(f"{year}-{month}-{day}", True)
        # )

        dest_dir = self.base_cartas.concat(year).concat(f"{year}-{month}", True)
        return dest_dir, f"{year} {month} {day} {uc} {toi}"

    def _destino_livre(self, dest: File, src: File) -> File:
        """Evita sobrescrever outro arquivo com o mesmo nome de destino."""
        if dest.absolute() == src.absolute():
            return dest
        return _resolver_colisao_arquivo(dest)

    def _process_identified_files(self) -> Set[hashFile]:
        """Processa os arquivos que possuem registro na tabela TOI."""
        controller = ControllerTOI()

        if self.modo_v2:
            table_files = controller.load_from_map_v2(
                self.map_files, permitir_parcial=True
            )
            if table_files is None:
                return Set[hashFile]()
        else:
            controller.add_hashs_on_table(self.map_files.header().to_set())
            table_files = controller.find_on_cache(self.map_files)

        processed = Set[hashFile]()

        for row in table_files.rows():
            file_hash: hashFile = row.get(HeaderFilesTOI.HASH_FILE)
            src: File = self.map_files.get_value(file_hash)

            if src is None:
                continue

            processed.add(file_hash)
            dest_dir, output_name = self._get_destination(row)
            dest = dest_dir.join_file(f"{output_name}{src.extension()}")

            if self.modo_v2:
                dest = self._destino_livre(dest, src)

            self._move(file_hash, src, dest)

        return processed

    def _process_unidentified_files(self, processed: Set[hashFile]) -> None:
        """Encaminha para a pasta de UC os arquivos sem registro TOI."""
        for file_hash in self.map_files.header():
            if processed.contains(file_hash):
                continue

            src: File = self.map_files.get_value(file_hash)
            extension = src.extension() or ".nan"
            dest = self.error_uc_dir.join_file(f"{file_hash}{extension}")

            if self.modo_v2:
                dest = self._destino_livre(dest, src)

            self._move(file_hash, src, dest)

    def _save_log(self) -> pd.DataFrame:
        """Acumula os resultados no relatório existente."""
        sequence = ArrayTables[TableData]()
        sequence.add(self.table_status)

        if self.file_log.exists():
            df_previous = pd.read_excel(self.file_log.absolute())
            sequence.add(TableData(df_previous))

        df_final = sequence.concat(TableData).to_dataframe()
        df_final.drop_duplicates(inplace=True)

        print(f"Salvando: {self.file_log}")
        df_final.to_excel(self.file_log.absolute(), index=False)
        return df_final

    def execute(self) -> pd.DataFrame:
        if self.files.empty():
            return self.table_status.to_dataframe()

        self._index_files()
        processed = self._process_identified_files()
        self._process_unidentified_files(processed)
        return self._save_log()


def rename_files_toi(files: Set[File], *, modo_v2: bool = False) -> RenameFilesTOI:
    """Renomear arquivos TOI (modo_v2=True usa o fluxo novo de identificação)."""

    rn = RenameFilesTOI(files, modo_v2=modo_v2)
    rn.execute()
    rn.process_error_ucs()
    return rn
