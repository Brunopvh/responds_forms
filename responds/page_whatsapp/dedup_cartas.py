# responds/page_whatsapp/dedup_cartas.py
"""
Anti-duplicatas das cartas TOI, restrito ao MVC page_whatsapp.

NÃO altera cartas / whatsapp_files / table_stream: apenas herda de
RenameFilesTOI e sobrescreve os pontos onde o sufixo "-1", "-2" ... era gerado.

Regra: o mesmo conteúdo (hash MD5) nunca é movido duas vezes para a base de
cartas, e nenhum arquivo ganha sufixo "-N". Se o destino já existe, o arquivo
de origem fica onde está e é reportado como DUPLICADA.

Somente stdlib + pandas + table_stream/whatsapp_files/cartas (sem subprocess,
sem pathlib).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import pandas as pd

from table_stream import (
    ContentFiles,
    Directory,
    EnumDocuments,
    File,
    HashMapDict,
    hashFile,
    load_file_hash,
)
from whatsapp_files import (
    BuilderTableWhatsApp,
    ControllerWhatsApp,
    HeaderWhatsApp,
    RowWhatsApp,
    move_path,
)
from cartas import BuilderConfigTOI, RenameFilesTOI

STATUS_DUPLICATE: str = "DUPLICADA"

_CARTA_EXTENSIONS: tuple[str, ...] = (".pdf", ".png", ".jpg", ".jpeg")
_INDEX_FILENAME: str = "indice-cartas-hash.xlsx"
_C_HASH: str = "hash"
_C_PATH: str = "path"
_C_SIZE: str = "size"
_C_MTIME: str = "mtime_ns"
_INDEX_COLUMNS: list[str] = [_C_HASH, _C_PATH, _C_SIZE, _C_MTIME]


# ============================================================#
# Índice persistente hash -> arquivo (Excel)
# ============================================================#
class CartasHashIndex:
    """
    Índice {hash MD5 -> caminho} de tudo que já está na pasta de cartas,
    gravado em Excel (RFA/Tabelas/indice-cartas-hash.xlsx).

    refresh() é incremental: um arquivo só é relido/hasheado se o caminho
    for novo ou se o tamanho/mtime mudou. Nas execuções seguintes o custo é
    só percorrer a pasta (rápido), sem recalcular MD5 dos arquivos antigos.
    """

    def __init__(self, root: Directory, file_index: File) -> None:
        self._root: Directory = root
        self._file: File = file_index
        # path -> (hash, size, mtime_ns)
        self._by_path: dict[str, tuple[str, int, int]] = {}
        # hash -> path (primeiro encontrado)
        self._by_hash: dict[str, str] = {}
        self._load()

    @classmethod
    def create_default(cls, root: Directory) -> CartasHashIndex:
        return cls(root, BuilderConfigTOI().dir_table.join_file(_INDEX_FILENAME))

    # ---------------------------------------------------------- persistência
    def _load(self) -> None:
        if not self._file.exists():
            return
        try:
            df: pd.DataFrame = pd.read_excel(
                self._file.absolute(), dtype=str, keep_default_na=False
            )
        except Exception as e:
            print(f"[AVISO] índice de cartas ilegível, será refeito: {e}")
            return

        if any(c not in df.columns for c in _INDEX_COLUMNS):
            return

        for rec in df[_INDEX_COLUMNS].to_dict("records"):
            try:
                self._by_path[str(rec[_C_PATH])] = (
                    str(rec[_C_HASH]),
                    int(rec[_C_SIZE]),
                    int(rec[_C_MTIME]),
                )
            except ValueError:
                continue

    def save(self) -> None:
        rows: list[dict[str, str]] = [
            {_C_HASH: h, _C_PATH: p, _C_SIZE: str(s), _C_MTIME: str(m)}
            for p, (h, s, m) in self._by_path.items()
        ]
        df: pd.DataFrame = pd.DataFrame(rows, columns=_INDEX_COLUMNS)

        self._file.parent().mkdir()
        path: str = self._file.absolute()
        tmp: str = f"{path}-tmp.xlsx"
        df.to_excel(tmp, index=False)
        os.replace(tmp, path)  # atômico: nunca deixa .xlsx corrompido

    # ---------------------------------------------------------- atualização
    def refresh(self) -> int:
        """
        Sincroniza o índice com o disco. Retorna quantos arquivos tiveram o
        hash calculado nesta chamada.
        """
        new_by_path: dict[str, tuple[str, int, int]] = {}
        hashed: int = 0

        if self._root.exists():
            files = ContentFiles(self._root, max_files=500_000).get_files(
                EnumDocuments.ALL, sort=False, recursive=True
            )
            for f in files:
                if (f.extension() or "").lower() not in _CARTA_EXTENSIONS:
                    continue
                p: str = f.absolute()
                try:
                    st: os.stat_result = os.stat(p)
                except OSError:
                    continue

                known: tuple[str, int, int] | None = self._by_path.get(p)
                if known is not None and known[1] == st.st_size and known[2] == st.st_mtime_ns:
                    new_by_path[p] = known
                    continue

                try:
                    h: str = str(load_file_hash(f))
                except OSError as e:
                    print(f"[AVISO] falha ao calcular hash de {p}: {e}")
                    continue
                new_by_path[p] = (h, st.st_size, st.st_mtime_ns)
                hashed += 1

        changed: bool = hashed > 0 or set(new_by_path) != set(self._by_path)
        self._by_path = new_by_path
        self._rebuild_hash_map()
        if changed:
            self.save()
        return hashed

    def _rebuild_hash_map(self) -> None:
        self._by_hash = {}
        for p in sorted(self._by_path):
            self._by_hash.setdefault(self._by_path[p][0], p)

    # ---------------------------------------------------------- consulta
    def find(self, file_hash: str) -> str | None:
        """Caminho de um arquivo já existente com este hash (ou None)."""
        p: str | None = self._by_hash.get(str(file_hash))
        if p is not None and os.path.isfile(p):
            return p
        return None


# ============================================================#
# Separar duplicadas ANTES de mover
# ============================================================#
@dataclass(frozen=True)
class DuplicateItem:
    src: str
    existing: str
    file_hash: str
    reason: str


@dataclass
class DedupResult:
    unique: list[File] = field(default_factory=list)
    duplicates: list[DuplicateItem] = field(default_factory=list)


def split_duplicates(files: list[File], index: CartasHashIndex) -> DedupResult:
    """
    Separa as cartas novas das duplicadas (por hash MD5):
      * já existe na pasta de cartas (em outro caminho);
      * repetida dentro do próprio lote (fica só a primeira).
    Um arquivo que já é o próprio registro do índice (mesmo caminho) NÃO é
    duplicata dele mesmo.
    """
    result = DedupResult()
    seen: dict[str, str] = {}

    for f in files:
        try:
            h: str = str(load_file_hash(f))
        except OSError as e:
            print(f"[AVISO] falha ao calcular hash de {f.absolute()}: {e}")
            result.unique.append(f)  # deixa o fluxo normal reportar o erro
            continue

        existing: str | None = index.find(h)
        if existing is not None and os.path.abspath(existing) != f.absolute():
            result.duplicates.append(
                DuplicateItem(f.absolute(), existing, h, "Já existe na pasta de cartas")
            )
            continue

        if h in seen:
            result.duplicates.append(
                DuplicateItem(f.absolute(), seen[h], h, "Repetida no lote selecionado")
            )
            continue

        seen[h] = f.absolute()
        result.unique.append(f)

    return result


# ============================================================#
# RenameFilesTOI sem sufixo -1, -2 ...
# ============================================================#
class RenameCartasSemDuplicatas(RenameFilesTOI):
    """
    Mesmo fluxo de RenameFilesTOI, mas:
      * nunca gera "nome-1.ext": se o destino existe, o arquivo não é movido
        e fica registrado como DUPLICADA no log;
      * process_error_ucs() também não cria sufixos (e não "re-move" um
        arquivo que já está no lugar certo, que era uma fonte de -1, -2...).
    """

    def _destino_livre(self, dest: File, src: File) -> File:
        return dest  # sem resolução de colisão

    def _move(self, file_hash: hashFile, src: File, dest: File) -> bool:
        if dest.exists() and dest.absolute() != src.absolute():
            row = self._create_status_row(file_hash, src, dest)
            row.set("status", STATUS_DUPLICATE)
            row.set(
                "exception",
                "Destino já existe; arquivo não movido (sem sufixo -N)",
            )
            self.table_status.add_row(row)
            return False
        return super()._move(file_hash, src, dest)

    def process_error_ucs(self) -> None:
        tb_wp = ControllerWhatsApp().load_cache_table()
        files = ContentFiles(self.error_uc_dir).get_files()

        content_map = HashMapDict[hashFile, File]()
        files.for_each(lambda f: content_map.set_value(load_file_hash(f), f))

        content_chat = tb_wp.search_all(HeaderWhatsApp.hash_md5, content_map.header())
        if content_chat is None or content_chat.is_empty():
            return

        rows = (
            BuilderTableWhatsApp().create_from_data(content_chat.to_dataframe()).rows()
        )

        r: RowWhatsApp
        for r in rows:
            h: hashFile = r.get(HeaderWhatsApp.hash_md5)
            file_path: File = content_map.get_value(h)

            dt = r.get_date_hour()
            y: str = str(dt.year)
            m: str = f"{dt.month:02d}"

            current_dir: Directory = self.error_uc_dir.concat(y).concat(
                f"{y}-{m}", True
            )
            final_path: File = current_dir.join_file(file_path.basename())

            if final_path.absolute() == file_path.absolute():
                continue  # já está no lugar certo
            if final_path.exists():
                print(
                    f"{__class__.__name__}(): duplicada, não movida -> "
                    f"{file_path.absolute()}"
                )
                continue

            try:
                move_path(file_path, final_path)
            except Exception as e:
                print(f"{__class__.__name__}(): {e}")
