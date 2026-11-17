# stdlib/builtin
from __future__ import annotations
from enum import StrEnum
import re
from typing import Any
from datetime import datetime
import os
import shutil
from dataclasses import dataclass
import threading

# External libs
from pandas import DataFrame
import pandas as pd

from table_stream import (
    # Arquivos
    PathElement,
    File,
    Directory,
    hashFile,
    HeaderMetaData,
    ContentFiles,
    EnumDocuments,
    UserFileSystem,
    extract_zip_files,
    load_file_hash,
    # HashMap
    ArrayList,
    HashMapDict,
    HashMap,
    Set,
    # Tabelas
    ColumnV,
    RowH,
    TableData,
    Table,
    ColumnNotFoundError,
    # Datas
    DateValues,
    create_date_time,
    BaseObject,
)

# Remover essa dependencia e ocr_stream, mas usar os mesmos caminhos para acesssar
# as tabelas ocr, apartir da mesma base UserFileSystem().get_user_documents().concat("RFA", True)
# from ocr_stream import BuilderConfigOcr

__version__ = "0.2"
DEFAULT_TEXT_CHAT = "Conversa do WhatsApp com"


class InvalidZipFile(ValueError):

    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class InvalidTxtFile(ValueError):

    def __init__(self, *args: object) -> None:
        super().__init__(*args)


@dataclass
class ResultChatImport:
    """Resultado da importação de UM chat."""

    chat: str = ""
    file_txt: str = ""
    messages: int = 0  # mensagens lidas do .txt
    attachments: int = 0  # mensagens com "(arquivo anexado)"
    hashed: int = 0  # anexos encontrados em disco (hash calculado)
    added: int = 0  # linhas NOVAS gravadas no cache


def move_path(src: PathElement, dest: PathElement) -> bool:

    try:
        shutil.move(src.absolute(), dest.absolute())
    except Exception as e:
        print(e)
        return False
    else:
        return True


@dataclass
class ConfigWhatsApp:

    file_relatorio: File
    file_table: File
    dir_unzip_chats: Directory
    dir_zip_chats: Directory
    dir_export_files: Directory
    work_dir: Directory


# Mesmos nomes usados por ocr_stream.BuilderConfigOcr. Se mudar lá, mude aqui.
_DIR_ROOT_NAME = "RFA"
_DIR_TABLES_NAME = "Tabelas"


class BuilderConfigWhatsApp(object):
    """
    Configuração do WhatsApp SEM depender de ocr_stream/tesseract.

    Usa a mesma base que o ocr_stream:
        <Documentos>/RFA/            -> dir_base_root
        <Documentos>/RFA/Tabelas     -> dir_table (onde ficam as tabelas OCR, TOI etc.)
        <Documentos>/RFA/WhatsApp    -> dir_base_work
    """

    _instance = None  # Atributo de classe para armazenar a instância singleton

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(BuilderConfigWhatsApp, cls).__new__(cls)
        return cls._instance

    def __init__(self) -> None:

        # Garante que __init__ não será executado mais de uma vez
        if hasattr(self, "_initialized") and self._initialized:
            return

        super().__init__()
        self._initialized: bool = True
        self._root_dir: Directory | None = None
        self._config = None

    # ---------------------------------------------------------- base RFA
    @property
    def dir_base_root(self) -> Directory:
        """<Documentos>/RFA (mesma base do ocr_stream)."""
        if self._root_dir is None:
            self._root_dir = (
                UserFileSystem().get_user_documents().concat(_DIR_ROOT_NAME, True)
            )
        return self._root_dir

    def set_root_dir(self, d: Directory) -> None:
        """Troca a base (testes / outro PC). Descarta a configuração em cache."""
        d.mkdir()
        self._root_dir = d
        self.reset_config()

    @property
    def dir_base_work(self) -> Directory:
        return self.dir_base_root.concat("WhatsApp", True)

    @property
    def dir_table(self) -> Directory:
        """<Documentos>/RFA/Tabelas (mesma pasta das tabelas OCR)."""
        d = self.dir_base_root.concat(_DIR_TABLES_NAME)
        d.mkdir()
        return d

    @property
    def dir_chats_organizados(self) -> Directory:
        return self.dir_base_work.concat("ConversasOrganizadas", True)

    @property
    def dir_chats_compactados(self) -> Directory:
        return self.dir_base_work.concat("ConversasCompactadas", True)

    @property
    def dir_chats_descompactados(self) -> Directory:
        return self.dir_base_work.concat("ConversasDescompactadas", True)

    def reset_config(self) -> None:
        self._config = None

    def builder(self) -> ConfigWhatsApp:
        if self._config is None:

            self._config = ConfigWhatsApp(
                file_relatorio=self.dir_table.join_file("relatorio-whatsapp.xlsx"),
                file_table=self.dir_table.join_file("tabela-whatsapp.xlsx"),
                dir_unzip_chats=self.dir_chats_descompactados,
                dir_zip_chats=self.dir_chats_compactados,
                dir_export_files=self.dir_chats_organizados,
                work_dir=self.dir_base_work,
            )

        return self._config


class HeaderWhatsApp(StrEnum):

    date = "data"
    date_hour = "data_hora"
    hour = "hora"

    remetente = "remetente"
    msg = "mensagem"
    name_chat = "nome_chat"
    contains_file = "arquivo_anexado"

    basename = HeaderMetaData.FILE_BASENAME.value
    hash_md5 = HeaderMetaData.HASH_FILE.value


class RowWhatsApp(RowH[HeaderWhatsApp, Any]):

    def __init__(
        self, index: int, data: dict[HeaderWhatsApp, Any] | None = None
    ) -> None:
        super().__init__(index, data)

    def __repr__(self) -> str:
        default = f"{__class__.__name__}():"
        if len(self.data) == 0:
            return f"{default} Size: 0"

        _values = ArrayList()
        for k, v in self.data.items():
            _values.add(f"{k} -> {v}")

        return f"{default}\n{_values}"

    def get_filename(self) -> str:
        return self.get(HeaderWhatsApp.basename)

    def get_date(self) -> HashMapDict[DateValues, str]:
        """
        Retorna data no formato %d %m %Y -> DateValues.DATE_TOI
        """

        dt: datetime = self.get_date_hour()
        # h = dt.time()
        date = dt.date().strftime(DateValues.DATE_TOI)
        return HashMapDict({DateValues.DATE_TOI: date})

    def get_date_hour(self) -> datetime:
        txt = self.get(HeaderWhatsApp.date_hour)
        return create_date_time(txt, DateValues.DATETIME_ENG)

    def hash_file(self) -> hashFile | None:
        h = self.get(HeaderWhatsApp.hash_md5)
        if h == "":
            return None
        return h


class TableWhatsApp(TableData[HeaderWhatsApp]):

    def __init__(self, data: DataFrame | None = None) -> None:
        super().__init__(data)

    def search(self, h: HeaderWhatsApp, value: Any) -> TableWhatsApp:
        return TableWhatsApp.create_from_data(super().search(h, value).to_dataframe())

    def get_chat_names(self) -> ArrayList[str]:
        if self.size() == 0:
            return ArrayList()
        return self.get(HeaderWhatsApp.name_chat).drop_duplicates().get_elements()

    def get_row_at(self, idx: int) -> RowWhatsApp:
        r: RowH = super().get_row_at(idx)
        return RowWhatsApp(idx, r.data)

    def rows(self) -> ArrayList[RowWhatsApp]:  # type: ignore
        final = ArrayList[RowWhatsApp]()

        if self.is_empty():
            return final

        total: int = self.get(self.header().get_first()).size()

        for num in range(total):
            row: RowWhatsApp = self.get_row_at(num)
            final.append(row)
        return final

    @classmethod
    def create_from_data(cls, data: DataFrame) -> TableWhatsApp:
        columns_df = ArrayList(data.columns.tolist())
        columns_wp = [x for x in HeaderWhatsApp]
        tb = cls()

        for col_wp in columns_wp:
            if not columns_df.contains(col_wp):
                continue

            elements = data[col_wp].astype("str").values.tolist()
            col_v = ColumnV(col_wp, ArrayList(elements))
            tb.add(col_v)
        return tb

    @classmethod
    def create_void(cls, columns: list[HeaderWhatsApp]) -> TableWhatsApp:
        tb = cls()
        for c in columns:
            col_v = ColumnV(c)
            tb.add(col_v)
        return tb

    @staticmethod
    def builder() -> BuilderTableWhatsApp:
        return BuilderTableWhatsApp()


class BuilderTableWhatsApp(object):

    def __init__(self) -> None:
        self.default_cols = ArrayList[HeaderWhatsApp].from_list(
            [
                HeaderWhatsApp.date,
                HeaderWhatsApp.date_hour,
                HeaderWhatsApp.hour,
                HeaderWhatsApp.remetente,
                HeaderWhatsApp.msg,
                HeaderWhatsApp.name_chat,
                HeaderWhatsApp.contains_file,
                HeaderWhatsApp.basename,
                HeaderWhatsApp.hash_md5,
            ]
        )

    def create_void(self) -> TableWhatsApp:
        tb = TableWhatsApp()
        self.default_cols.for_each(lambda c: tb.add(ColumnV(c)))
        return tb

    def create_from_data(self, df: pd.DataFrame) -> TableWhatsApp:
        df_cols = ArrayList[str](df.columns.tolist())
        tb = TableWhatsApp()
        c: HeaderWhatsApp

        for c in self.default_cols:

            if not df_cols.contains(c.value):
                raise ColumnNotFoundError(
                    f"{__class__.__name__}: Coluna não encontrada ... {c.value}"
                )

            s = df[c.value].astype(str).values.tolist()
            tb.add(ColumnV(c, ArrayList.from_list(s)))

        return tb


# ============================================================#
# Gerar DataFrame() apartir do arquivo de conversas do whatsapp .TXT
# ============================================================#

# Caracteres invisíveis que o WhatsApp costuma inserir (LRM, isoladores direcionais etc.)
INVISIBLE_CHARS = re.compile(r"[\u200e\u200f\u2066\u2067\u2068\u2069]")

# Início de mensagem: 23/01/2026 05:45 - Nome do Remetente: mensagem
# O grupo do remetente é opcional porque mensagens de sistema não têm ":"
# (ex: "Você criou este grupo", "Você adicionou Sr Alguém")

LINE_START = re.compile(r"^(\d{2}/\d{2}/\d{4}) (\d{2}:\d{2}) - (?:([^:\n]+?): )?(.*)$")


def load_whatsapp_txt(
    file_txt: File,
    dayfirst: bool = True,
) -> DataFrame:

    if not file_txt.exists():
        raise FileNotFoundError(file_txt.absolute())

    path = file_txt.absolute()

    with open(path, encoding="utf-8") as f:
        raw_lines: list[str] = f.readlines()

    records: list[dict[HeaderWhatsApp, str]] = []

    for _raw_line in raw_lines:
        line: str = INVISIBLE_CHARS.sub("", _raw_line).rstrip("\n")
        if not line.strip():
            continue

        match = LINE_START.match(line)
        if match:
            date_str, time_str, sender, message = match.groups()

            records.append(
                {
                    HeaderWhatsApp.date: date_str,
                    HeaderWhatsApp.hour: time_str,
                    HeaderWhatsApp.remetente: sender if sender else "[sistema]",
                    HeaderWhatsApp.msg: message,
                }
            )
        else:
            # Continuação de uma mensagem multi-linha: anexa à última mensagem
            if records:
                records[-1][HeaderWhatsApp.msg] += "\n" + line

    df = pd.DataFrame(records)

    if not df.empty:
        df[HeaderWhatsApp.date_hour] = pd.to_datetime(
            df[HeaderWhatsApp.date] + " " + df[HeaderWhatsApp.hour],
            dayfirst=dayfirst,
            format="%d/%m/%Y %H:%M",
        )

        df[HeaderWhatsApp.contains_file] = df[HeaderWhatsApp.msg].str.contains(
            r"\(arquivo anexado\)", regex=True
        )

        df[HeaderWhatsApp.basename] = (
            df[HeaderWhatsApp.msg]
            .where(df[HeaderWhatsApp.contains_file])
            .str.extract(r"^(.*?)\s*\(arquivo anexado\)", expand=False)
        )

    name_chat = file_txt.name().replace(DEFAULT_TEXT_CHAT, "").strip()
    col_name_chat = [name_chat] * len(df)
    df[HeaderWhatsApp.name_chat] = pd.Series(col_name_chat)
    return df


# ----------------------------------------------------------------------
# 1) Localiza, em disco, o arquivo original + variantes "-1", "-2" ...
#    geradas quando dois anexos do chat chegam com o MESMO nome.
# ----------------------------------------------------------------------
def _variantes_fisicas_por_nome(
    dir_media: Directory, nome_arquivo: str
) -> ArrayList[File]:
    """
        Retorna, em `dir_media`, o arquivo cujo nome é exatamente
    `nome_arquivo` e as variantes "-1", "-2", ... que o sistema de
    arquivos costuma gerar quando dois anexos do WhatsApp chegam com o
    MESMO nome original (ex: duas mensagens citando "Boleto.pdf", mas em
    disco existem "Boleto.pdf" e "Boleto-1.pdf").

        Ordenado por data de modificação (mtime), do mais antigo ao mais
    novo -- a mesma convenção já usada em resolver_colisao() e em
    MatchDataWhatsapp (stream_files.py), reaproveitada aqui para casar,
    em ordem, cada MENÇÃO do nome no chat com o arquivo físico certo.
    """
    nome, ext = os.path.splitext(nome_arquivo)
    candidatos = ArrayList[File]()

    original = dir_media.join_file(nome_arquivo)
    if original.exists():
        candidatos.append(original)

    contador = 1
    while True:
        variante = dir_media.join_file(f"{nome}-{contador}{ext}")
        if not variante.exists():
            break
        candidatos.append(variante)
        contador += 1

    candidatos.sort(key=lambda f: os.path.getmtime(f.absolute()))
    return candidatos


# ----------------------------------------------------------------------
# 2) Calcula o hash MD5 de cada anexo referenciado no DataFrame já
#    parseado do .txt, na mesma ordem cronológica das mensagens.
# ----------------------------------------------------------------------
def _calcular_hashes_arquivos_chat(
    df: pd.DataFrame, dir_media: Directory
) -> ArrayList[hashFile]:
    """
        Para cada linha do DataFrame() do chat, calcula o MD5
    (load_file_hash) do arquivo físico correspondente em `dir_media`.

        Retorna "" (string vazia) quando a linha não tem anexo, ou quando
    o anexo não existe mais em disco -- em vez de None, para manter a
    convenção de tabelas 100% string já usada no restante do projeto
    (TableWhatsApp/TableMap tratam tudo como str).
    """
    hashes = ArrayList[hashFile].from_list([""] * len(df))

    if df.empty:
        return hashes

    # Cache: nome_arquivo -> lista de variantes físicas (ordenadas por mtime)
    cache_variantes: dict[str, ArrayList[File]] = {}

    # Quantas vezes cada nome já apareceu no chat, na ordem em que as
    # linhas são percorridas (== ordem cronológica do .txt)
    ocorrencia_atual: dict[str, int] = {}

    for pos, (contem_arquivo, nome) in enumerate(
        zip(df[HeaderWhatsApp.contains_file], df[HeaderWhatsApp.basename])
    ):
        if not contem_arquivo or pd.isna(nome):
            continue

        nome = str(nome).strip()

        if nome not in cache_variantes:
            cache_variantes[nome] = _variantes_fisicas_por_nome(dir_media, nome)
            ocorrencia_atual[nome] = 0

        variantes = cache_variantes[nome]
        indice = ocorrencia_atual[nome]
        ocorrencia_atual[nome] += 1

        if indice >= variantes.size():
            print(f"[AVISO] ... arquivo não encontrado em disco -> {nome}")
            continue

        arquivo_fisico = variantes[indice]
        try:
            hashes[pos] = load_file_hash(arquivo_fisico)
        except Exception as e:
            print(
                f"[AVISO] ... falha ao calcular hash -> {arquivo_fisico.absolute()} ({e})"
            )

    return hashes


def carregar_dataframe_whatsapp(
    file_txt: File,
    dayfirst: bool = True,
    *,
    dir_media: Directory = None,
) -> pd.DataFrame:
    """
        Faz todo o trabalho de load_whatsapp(), mas retorna o DataFrame()
    cru (com dtypes corretos: datetime, bool) em vez de empacotar em
    TableWhatsApp -- que converte tudo para string via .astype('str') e
    por isso não serve para quem precisa de data_hora como datetime real.

        Usado por mapa_hash_para_data() (stream_files.py) para casar
    ColumnsOcr.HASH_FILE com ColumnsWhatsApp.hash_md5 e formatar a data
    com .strftime('%d-%m-%Y') no nome final do arquivo renomeado.
    """
    if not file_txt.exists():
        raise FileNotFoundError(file_txt.absolute())

    path = file_txt.absolute()

    with open(path, encoding="utf-8") as f:
        raw_lines = f.readlines()

    records: list[dict[str, str]] = []

    for raw_line in raw_lines:
        line = INVISIBLE_CHARS.sub("", raw_line).rstrip("\n")
        if not line.strip():
            continue

        match = LINE_START.match(line)
        if match:
            date_str, time_str, sender, message = match.groups()

            records.append(
                {
                    HeaderWhatsApp.date: date_str,
                    HeaderWhatsApp.hour: time_str,
                    HeaderWhatsApp.remetente: sender if sender else "[sistema]",
                    HeaderWhatsApp.msg: message,
                }
            )
        else:
            # Continuação de uma mensagem multi-linha: anexa à última mensagem
            if records:
                records[-1][HeaderWhatsApp.msg] += "\n" + line

    df = pd.DataFrame(records)

    if not df.empty:
        df[HeaderWhatsApp.date_hour] = pd.to_datetime(
            df[HeaderWhatsApp.date] + " " + df[HeaderWhatsApp.hour],
            dayfirst=dayfirst,
            format="%d/%m/%Y %H:%M",
        )

        df[HeaderWhatsApp.contains_file] = df[HeaderWhatsApp.msg].str.contains(
            r"\(arquivo anexado\)",
            regex=True,
            na=False,
        )

        df[HeaderWhatsApp.basename] = (
            df[HeaderWhatsApp.msg]
            .where(df[HeaderWhatsApp.contains_file])
            .str.extract(
                # r"^(.*?)\s*\(arquivo anexado\)", expand=False
                r"(?s)^(.*?)\s*\(arquivo anexado\)",
                expand=False,
            )
            .fillna("")
            .str.strip()
        )

        pasta_media = dir_media or Directory(file_txt.dirname())
        df[HeaderWhatsApp.hash_md5] = _calcular_hashes_arquivos_chat(df, pasta_media)

    name_chat = file_txt.name().replace(DEFAULT_TEXT_CHAT, "").strip()
    col_name_chat = [name_chat] * len(df)
    df[HeaderWhatsApp.name_chat] = pd.Series(col_name_chat)
    return df


def load_whatsapp(
    file_txt: File,
    dayfirst: bool = True,
    *,
    dir_media: Directory = None,
) -> TableWhatsApp:
    df = carregar_dataframe_whatsapp(file_txt, dayfirst, dir_media=dir_media)
    return BuilderTableWhatsApp().create_from_data(df)


def fmt_date_table_whastapp(
    tb: TableWhatsApp,
    fmt_date: DateValues = DateValues.Y_M_D,  # "%Y-%m-%d",
) -> pd.DataFrame:
    """
    Formata a coluna data de uma tabela whatsapp.
    """
    df = tb.to_dataframe()
    col_date = HeaderWhatsApp.date
    fmt = fmt_date.value

    df = df.copy()
    df[col_date] = pd.to_datetime(
        df[col_date], dayfirst=True, format="%d/%m/%Y"
    ).dt.strftime(fmt)
    return df


def remove_void(values: set[str] | list[str]) -> Set[str]:

    final = Set[str]()

    for item in values:
        if item is None:
            continue
        if item == "":
            continue
        final.add(item)
    return final


def get_file_chat_from_dir(d: Directory) -> File | None:
    """
    Busca o arquivo .txt de um chat whatsapp. O parâmetro Directory
    é o caminho absoluto de um diretório de chat.
    """
    if not d.exists():
        raise FileNotFoundError(f"O diretório não existe ... {d.absolute()}")

    files: ArrayList[File] = ContentFiles(d).get_files(EnumDocuments.TXT)
    if files.empty():
        return None

    txts = ArrayList[File]()
    f: File

    for f in files:
        if DEFAULT_TEXT_CHAT in f.name():
            txts.add(f)

    if txts.empty():
        return None
    return txts.get_first()


_NO_HASH = {"", "nan", "NULL_TEXT"}

# Uma mensagem é identificada por estes campos + a ocorrência dentro do minuto.
_KEYS_MSG = [
    HeaderWhatsApp.date.value,
    HeaderWhatsApp.hour.value,
    HeaderWhatsApp.remetente.value,
    HeaderWhatsApp.msg.value,
    HeaderWhatsApp.name_chat.value,
]


def _normalize_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Colunas como str (valor do enum), ordem padrão, tudo texto."""
    cols = [h.value for h in HeaderWhatsApp]
    out = df.copy()
    out.columns = [str(c) for c in out.columns]
    return out[cols].astype(str).reset_index(drop=True)


def merge_chat_frames(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """
    Une o cache (old) com um chat recém-lido (new) sem duplicar mensagens.

    * mensagem repetida  -> fica uma só (a que tiver hash de mídia);
    * "ok" enviado 2x no mesmo minuto -> continuam 2 (contador _occ);
    * mensagem nova      -> entra.
    """
    c_hash = HeaderWhatsApp.hash_md5.value
    c_dt = HeaderWhatsApp.date_hour.value
    c_chat = HeaderWhatsApp.name_chat.value
    cols = [h.value for h in HeaderWhatsApp]

    old_p = _normalize_frame(old)
    new_p = _normalize_frame(new)

    frames = []
    offset = 0
    for df in (old_p, new_p):
        df["_occ"] = df.groupby(_KEYS_MSG).cumcount()
        df["_ord"] = range(offset, offset + len(df))
        offset += len(df)
        if not df.empty:
            frames.append(df)

    if not frames:
        return old_p[cols]

    both = pd.concat(frames, ignore_index=True)
    sub = _KEYS_MSG + ["_occ"]

    both["_has"] = ~both[c_hash].isin(_NO_HASH)
    both["_ord"] = both.groupby(sub)["_ord"].transform("min")  # mantém a posição antiga
    both = both.sort_values("_has", ascending=False, kind="stable")
    both = both.drop_duplicates(subset=sub, keep="first")
    both = both.sort_values([c_chat, c_dt, "_ord"], kind="stable")
    return both[cols].reset_index(drop=True)


class ReadWriteWhatsApp(BaseObject):

    _instance = None  # Atributo de classe para armazenar a instância singleton

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ReadWriteWhatsApp, cls).__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        # Garante que __init__ não será executado mais de uma vez
        if hasattr(self, "_initialized") and self._initialized:
            return

        super().__init__()
        self._initialized: bool = True
        self.builder_conf = BuilderConfigWhatsApp()
        self._tb_whatsapp: TableWhatsApp | None = None
        self._lock = threading.RLock()

    def get_file_table_whatsapp(self) -> File:
        return self.builder_conf.builder().file_table

    def load_table_whatsapp(self, *, reload: bool = False) -> TableWhatsApp:
        """
        Retorna a tabela em cache (memória). reload=True relê o .xlsx do disco.
        """
        with self._lock:
            if self._tb_whatsapp is not None and not reload:
                return self._tb_whatsapp

            f = self.get_file_table_whatsapp()
            if not f.exists():
                self._tb_whatsapp = BuilderTableWhatsApp().create_void()
                return self._tb_whatsapp

            print(f"Lendo tabela whatsapp ... {f.absolute()}")
            # dtype=str + keep_default_na=False: hash vazio continua "" (não vira "nan")
            df = pd.read_excel(f.absolute(), dtype=str, keep_default_na=False)
            self._tb_whatsapp = BuilderTableWhatsApp().create_from_data(df)
            return self._tb_whatsapp

    def merge(self, new: TableWhatsApp) -> int:
        """
        Incorpora um chat ao cache e salva. Retorna quantas linhas NOVAS entraram.
        Só grava o arquivo se algo mudou (linha nova ou hash preenchido).
        """
        if new.is_empty():
            print(f"{__class__.__name__}(): Tabela vazia, nada a fazer!")
            return 0

        with self._lock:
            current = self.load_table_whatsapp()
            old_df = _normalize_frame(current.to_dataframe())
            merged = merge_chat_frames(old_df, new.to_dataframe())

            if merged.equals(old_df):
                return 0

            self._tb_whatsapp = BuilderTableWhatsApp().create_from_data(merged)
            self.save()
            return max(len(merged) - len(old_df), 0)

    def save(self) -> None:
        with self._lock:
            f = self.get_file_table_whatsapp()
            print(f"Salvando tabela whatsapp ... {f.absolute()}")

            f.parent().mkdir()
            tmp_file: str = f"{f.absolute()}-tmp.xlsx"
            path = f.absolute()

            df = self.load_table_whatsapp().to_dataframe()
            df.to_excel(tmp_file, index=False)
            os.replace(tmp_file, path)  # atômico e portável


# ==============================================================#
# Commandos
# ==============================================================#
class CommandWp(object):

    def __init__(self) -> None:
        self.build_conf: BuilderConfigWhatsApp = BuilderConfigWhatsApp()
        self.rw: ReadWriteWhatsApp = ReadWriteWhatsApp()

    def get_conf(self) -> ConfigWhatsApp:
        return self.build_conf.builder()

    def load_hashs(self, files: Set[File]) -> HashMap[hashFile, File]:
        data = HashMapDict[hashFile, File]()
        files.for_each(lambda f: data.set_value(load_file_hash(f), f))
        return data

    def execute(self) -> None:
        raise NotImplementedError()


class AddChatsOnTable(CommandWp):
    """
    Adiciona todos os chats de diretórios descompactados a tabela principal.
    """

    def __init__(self, chats_dir: Set[Directory] | None = None) -> None:
        super().__init__()
        self.chats_dir: Set[Directory] | None = chats_dir

    def get_dirs(self) -> Set[Directory]:
        if self.chats_dir is None:
            self.chats_dir = (
                self.get_conf().dir_unzip_chats.content_dirs(False).to_set()
            )
        return self.chats_dir

    def execute(self) -> None:
        chats = self.get_dirs()

        for d in chats:
            f_chat = get_file_chat_from_dir(d)

            if f_chat is None:
                continue

            df = carregar_dataframe_whatsapp(f_chat)
            self.rw.merge(TableWhatsApp.create_from_data(df))


class UncompressChats(CommandWp):

    def __init__(self, files_zip: Set[File] | None = None) -> None:
        super().__init__()
        self.files_zip: Set[File] | None = files_zip

    def get_zips(self) -> Set[File]:
        if self.files_zip is None:
            content = ContentFiles(self.get_conf().dir_zip_chats)
            self.files_zip = content.get_files(EnumDocuments.ZIP).to_set()

        return self.files_zip

    def execute(self) -> None:
        files = self.get_zips()
        if files.empty():
            return None

        extract_zip_files(
            files.tolist(),
            self.get_conf().dir_unzip_chats,
        )


class RenameChat(CommandWp):

    def __init__(self, chat_dirs: Set[Directory] | None = None) -> None:
        super().__init__()
        if chat_dirs is None:
            chat_dirs = (
                self.get_conf().dir_unzip_chats.content_dirs(recursive=False).to_set()
            )
        self.chat_dirs = chat_dirs

        self.includ_day: bool = False
        self.debug: bool = True
        self.output_dir: Directory = self.get_conf().dir_export_files

    def print(self, txt: str) -> None:
        if not self.debug:
            return
        print(f"{__class__.__name__} {txt}")

    def rename_dir_chat(self, d: Directory) -> None:
        tb = self.rw.load_table_whatsapp()
        content = ContentFiles(d)
        files = content.get_files().to_set()

        data: HashMap[hashFile, File] = self.load_hashs(files)
        header = data.header()
        h: hashFile

        for h in header:
            final_dir: Directory = self.get_conf().dir_export_files
            path = data.get_value(h)

            if not path.exists():
                continue

            idx = tb.find(HeaderWhatsApp.hash_md5, h)
            if idx is None:
                continue

            row = tb.get_row_at(idx)
            current_date: datetime = row.get_date_hour()
            y = str(current_date.year)
            m = str(current_date.month)
            _day = str(current_date.day)
            chat_name: str = row.get(HeaderWhatsApp.name_chat)

            final_dir = final_dir.concat(f"{y}-{chat_name}").concat(f"{y}-{m}", True)

            if self.includ_day:
                final_dir = final_dir.concat(f"{y}-{m}-{_day}", True)

            e: str = path.extension() or ".nan"
            new_filename = f"{y}-{m}-{_day}-{h}{e}"

            output_path: File = final_dir.join_file(new_filename)
            self.print(f"Movendo: {output_path}")
            move_path(path, output_path)

    def execute(self) -> None:
        processed = Set()

        for d in self.chat_dirs:
            self.rename_dir_chat(d)
            processed.add(d)

        processed.for_each(print)
        self.print(f"\nDiretórios processados: {processed.size()}")


class InvokeCommandsWp(object):

    def __init__(self, cmds: ArrayList[CommandWp] | None = None) -> None:
        self.cmds: ArrayList[CommandWp] = cmds or ArrayList()

    def add(self, c: CommandWp):
        self.cmds.add(c)

    def run(self):

        command: CommandWp
        for command in self.cmds:
            command.execute()


def rename_files_whatsapp(
    chat: TableWhatsApp | None = None,
    dir_chat: Directory | None = None,
    output: Directory | None = None,
    *,
    debug: bool = True,
    remetente: bool = False,
) -> None:
    """
        Organiza arquivos de uma conversa/pasta do whatsapp por data
    apartir de uma tabela whatsapp.
    """
    if chat is None:
        chat = ReadWriteWhatsApp().load_table_whatsapp()
    if chat.is_empty():
        return None
    if output is None:
        output = BuilderConfigWhatsApp().builder().dir_export_files

    commands = InvokeCommandsWp()
    add_chats_on_tb = AddChatsOnTable()
    rn = RenameChat()
    rn.output_dir = output

    if dir_chat is None:
        _src_chats = BuilderConfigWhatsApp().builder().dir_unzip_chats
        _dirs_chats = _src_chats.content_dirs(recursive=False).to_set()

        add_chats_on_tb.chats_dir = _dirs_chats
        rn.chat_dirs = _dirs_chats
        commands.add(UncompressChats())
    else:
        add_chats_on_tb.chats_dir = Set([dir_chat])
        rn.chat_dirs = Set([dir_chat])

    _df = chat.remove_null(HeaderWhatsApp.hash_md5).to_dataframe()
    chat = BuilderTableWhatsApp().create_from_data(_df)

    commands.add(add_chats_on_tb)
    commands.add(rn)
    commands.run()


def order_by_time(
    table_chat: TableData[HeaderWhatsApp],
) -> HashMap[hashFile, ArrayList[datetime]]:
    """
    Retorna um Map onde cada chave (string) representa o hash de um arquivo,
    cada valor representa uma lista das datas em que o arquivo foi enviado no chat.

    Um arquivo pode ser enviado várias vezes no chat com o mesmo nome de arquivo
    porém em datas diferentes.
    """
    data_map = HashMapDict[hashFile, ArrayList[datetime]]()

    if table_chat.is_empty():
        return data_map

    elements_hash = table_chat.get(HeaderWhatsApp.hash_md5).get_elements()
    col_hashs: Set[str] = remove_void(elements_hash)
    h: hashFile

    if col_hashs.empty():
        return data_map

    for h in col_hashs:

        current_tb: TableData[HeaderWhatsApp] | None = table_chat.search(
            HeaderWhatsApp.hash_md5, h
        )

        if current_tb is None:
            continue
        if current_tb.is_empty():
            continue

        inner_hours: ArrayList[str] = current_tb.get(
            HeaderWhatsApp.date_hour
        ).get_elements()

        # Converter cada string/data em datetime()
        new_order: ArrayList[datetime] = inner_hours.apply_command(
            lambda dt_str: datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        )

        # Ordenar as datas do mais antigo para o mais recente.
        new_order.sort()
        data_map[h] = new_order

    return data_map


# ============================================================#
# Casamento HASH_FILE <-> data exata
# ============================================================#


def mapa_hash_para_data(chat: TableData[HeaderWhatsApp]) -> HashMap[hashFile, datetime]:
    """
        Constrói um mapa HASH_MD5 -> data_hora de envio considerando o arquivo mais
    recente do chat (caso exista mais de uma arquivo com mesmo hash no chat).
    """
    mapa = HashMapDict[hashFile, datetime]()
    order_map = order_by_time(chat)
    header = order_map.header()

    for h in header:
        values_time: ArrayList[datetime] = order_map[h]
        values_time.sort()
        mapa[h] = values_time.get_last()
    return mapa


def resolver_colisao(destino: File) -> File:
    """
        Se `destino` já existir, acrescenta "-1", "-2", ... até achar um
    nome livre -- em vez de simplesmente pular o arquivo.
    """
    if not destino.exists():
        return destino

    base = destino.name_absolute()
    ext = destino.extension() or ""
    contador = 1
    novo = File(f"{base}-{contador}{ext}")
    while novo.exists():
        contador += 1
        novo = File(f"{base}-{contador}{ext}")
    return novo


class ControllerWhatsApp(BaseObject):
    """
        Classe para gerar um DataFrame() combinando dados de um arquivo (data e hora)
    enviado no chat do whatsapp se este fizer parte dos arquivos do chat.

    Essa combinação de dados não depende do local do arquivo no disco, pois é verificado
    o HASH MD5 do arquivo é não o caminho no disco.

    """

    NULL_TEXT: str = Table.NULL_STRING
    DEFAULT_TEXT_CHAT: str = DEFAULT_TEXT_CHAT

    def __init__(self) -> None:
        super().__init__()
        self.rw: ReadWriteWhatsApp = ReadWriteWhatsApp()
        self.builder_table = BuilderTableWhatsApp()

    def config(self) -> ConfigWhatsApp:
        return BuilderConfigWhatsApp().builder()

    def file_relatorio(self) -> File:
        return self.config().file_relatorio

    def load_cache_table(self) -> TableWhatsApp:
        return self.rw.load_table_whatsapp()

    def merge_table_cache(self, tb: TableWhatsApp) -> None:
        self.rw.merge(tb)

    def increment_chat_file(self, file_txt: File) -> ResultChatImport:
        """
        Adicionar dados de um CHAT (.txt) na tabela principal.

        I) Carrega o DataFrame() do arquivo de chat (inclui o hash das mídias
           que estiverem na mesma pasta do .txt);
        II) Mergeia no cache e salva.
        """
        if (file_txt.extension() or "").lower() != ".txt":
            raise InvalidTxtFile(f"Arquivo de chat inválido: {file_txt.absolute()}")

        df = carregar_dataframe_whatsapp(file_txt)
        if df.empty:
            raise InvalidTxtFile(
                f"Nenhuma mensagem reconhecida em {file_txt.basename()} "
                "(formato de data/hora inesperado?)"
            )

        content = self.builder_table.create_from_data(df)
        added = self.rw.merge(content)

        return ResultChatImport(
            chat=str(df[HeaderWhatsApp.name_chat].iloc[0]),
            file_txt=file_txt.absolute(),
            messages=len(df),
            attachments=int(df[HeaderWhatsApp.contains_file].sum()),
            hashed=int((df[HeaderWhatsApp.hash_md5] != "").sum()),
            added=added,
        )

    def increment_chat_zip(self, file_chat_zip: File) -> ResultChatImport:
        """
        Adicionar dados de um CHAT a partir do .zip exportado pelo WhatsApp.

        I) Extrai o ZIP em dir_unzip_chats/<nome do zip>;
        II) Localiza o .txt do chat;
        III) Importa o .txt (increment_chat_file).
        """
        if (file_chat_zip.extension() or "").lower() != ".zip":
            raise InvalidZipFile(
                f"{__class__.__name__}() arquivo zip inválido: {file_chat_zip.absolute()}"
            )
        if not file_chat_zip.exists():
            raise FileNotFoundError(file_chat_zip.absolute())

        dir_cache_unzip = self.config().dir_unzip_chats
        status = extract_zip_files([file_chat_zip], dir_cache_unzip)
        if not status.get(file_chat_zip.absolute(), False):
            raise InvalidZipFile(f"Falha ao extrair {file_chat_zip.basename()}")

        dir_unzip_chat: Directory = dir_cache_unzip.concat(file_chat_zip.name())
        final_file = get_file_chat_from_dir(dir_unzip_chat)
        if final_file is None:
            raise InvalidTxtFile(
                f"Arquivo de chat (.txt) não encontrado em: {dir_unzip_chat.absolute()}"
            )

        return self.increment_chat_file(final_file)

    def increment_chat_dirs(self, dirs: ArrayList[Directory]) -> None:
        """
            Ler uma lista de diretórios de chat do whatsapp e incrementa os dados
        na tabela em cache.
        """

        if dirs.empty():
            print(f"{__class__.__name__}(): Lista vazia, nada a fazer!")
            return

        d: Directory

        for d in dirs:
            file_chat = self._get_file_chat_from_dir(d)

            if file_chat is None:
                print(
                    f"{__class__.__name__}() [PULANDO]: {d.basename()} ... arquivo TXT não encontrado."
                )
                continue

            self.increment_chat_file(file_chat)

    def _get_file_chat_from_dir(self, d: Directory) -> File | None:
        """
        Procura e retorna o arquivo txt de um chat, se o arquivo não existir
        no diretório informado retorna None.
        """
        return get_file_chat_from_dir(d)

    def filter_table_from_hashs(
        self, hashs: ArrayList[hashFile]
    ) -> TableWhatsApp | None:
        """
            Retorna uma tabela whatsapp filtrando cada item do parâmetro
        hashs na tabela geral do whatsapp.
        """
        if hashs.empty():
            return None

        hashs = hashs.drop_duplicates()
        table_whatsapp_cache = self.load_cache_table()
        final = table_whatsapp_cache.search_all(HeaderWhatsApp.hash_md5, hashs)

        if final is None:
            return None
        return self.builder_table.create_from_data(final.to_dataframe())


def main():
    pass


if __name__ == "__main__":
    main()
