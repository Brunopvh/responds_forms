# responds/page_whatsapp/dedup_folder.py
"""
Remoção de arquivos duplicados (mesmo hash MD5) DENTRO de cada pasta.

Regras:
  * Duplicata = mesmo conteúdo na MESMA pasta. Arquivos iguais em pastas
    diferentes não são tocados ("um arquivo por pasta").
  * Em cada grupo mantém-se 1 arquivo, preferindo: nome sem sufixo '-N'
    (ex.: 'X.pdf' ganha de 'X-1.pdf'), depois nome mais curto, depois o mais
    antigo.
  * Duas fases: scan() só PLANEJA (não altera nada); execute() apaga.
    A UI mostra o plano e pede confirmação entre as duas.
  * Antes de apagar, confere se o arquivo mantido existe e se o arquivo a
    apagar não mudou (tamanho/data) desde o scan.
  * Só os.remove (exclusão permanente, sem lixeira). Sem subprocess/pathlib.
  * Links simbólicos são ignorados.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

import pandas as pd

from table_stream import Directory, File, load_file_hash

ProgressFn = Callable[[int, int], None]

STATUS_REMOVED: str = "REMOVIDO"
STATUS_FAILED: str = "FALHA"
STATUS_SKIPPED: str = "IGNORADO"

_COLLISION_SUFFIX: re.Pattern[str] = re.compile(r"-\d{1,3}$")


def _noop(_done: int, _total: int) -> None:
    return None


@dataclass(frozen=True)
class FileStamp:
    path: str
    size: int
    mtime_ns: int

    @property
    def basename(self) -> str:
        return os.path.basename(self.path)


@dataclass
class DuplicateGroup:
    folder: str
    file_hash: str
    keep: FileStamp
    remove: list[FileStamp]


@dataclass
class DuplicatePlan:
    root: str
    scanned: int = 0
    groups: list[DuplicateGroup] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def total_remove(self) -> int:
        return sum(len(g.remove) for g in self.groups)

    @property
    def bytes_to_free(self) -> int:
        return sum(s.size for g in self.groups for s in g.remove)


@dataclass(frozen=True)
class RemovalRecord:
    path: str
    kept: str
    status: str
    message: str


class DuplicateFolderService:
    """Planeja e executa a remoção de duplicatas por pasta."""

    # ---------------------------------------------------------- escolha
    @staticmethod
    def _keep_key(s: FileStamp) -> tuple[bool, int, int, str]:
        stem: str = os.path.splitext(s.basename)[0]
        return (
            _COLLISION_SUFFIX.search(stem) is not None,
            len(s.basename),
            s.mtime_ns,
            s.basename,
        )

    @staticmethod
    def _stamp(path: str) -> FileStamp | None:
        try:
            if os.path.islink(path) or not os.path.isfile(path):
                return None
            st: os.stat_result = os.stat(path)
        except OSError:
            return None
        return FileStamp(path, st.st_size, st.st_mtime_ns)

    # ---------------------------------------------------------- fase 1
    def scan(self, folder: Directory, on_progress: ProgressFn = _noop) -> DuplicatePlan:
        plan = DuplicatePlan(root=folder.absolute())

        listing: list[tuple[str, list[str]]] = [
            (dirpath, filenames)
            for dirpath, _dirs, filenames in os.walk(folder.absolute(), followlinks=False)
        ]
        total: int = sum(len(f) for _, f in listing)
        done: int = 0
        on_progress(0, total)

        for dirpath, filenames in listing:
            by_size: dict[int, list[FileStamp]] = {}
            for name in filenames:
                s: FileStamp | None = self._stamp(os.path.join(dirpath, name))
                if s is not None:
                    by_size.setdefault(s.size, []).append(s)

            for same_size in by_size.values():
                if len(same_size) < 2:
                    continue  # tamanho único: não pode ser duplicata (sem hash)

                by_hash: dict[str, list[FileStamp]] = {}
                for s in same_size:
                    try:
                        h: str = str(load_file_hash(File(s.path)))
                    except OSError as e:
                        plan.errors.append(f"{s.path}: {e}")
                        continue
                    by_hash.setdefault(h, []).append(s)

                for h, members in by_hash.items():
                    if len(members) < 2:
                        continue
                    ordered: list[FileStamp] = sorted(members, key=self._keep_key)
                    plan.groups.append(
                        DuplicateGroup(dirpath, h, ordered[0], ordered[1:])
                    )

            done += len(filenames)
            plan.scanned = done
            on_progress(done, total)

        return plan

    # ---------------------------------------------------------- fase 2
    def execute(
        self, plan: DuplicatePlan, on_progress: ProgressFn = _noop
    ) -> list[RemovalRecord]:
        records: list[RemovalRecord] = []
        total: int = plan.total_remove
        done: int = 0

        for g in plan.groups:
            keep_now: FileStamp | None = self._stamp(g.keep.path)
            keep_ok: bool = keep_now is not None and keep_now.size == g.keep.size

            for s in g.remove:
                done += 1
                on_progress(done, total)

                if not keep_ok:
                    records.append(
                        RemovalRecord(
                            s.path, g.keep.path, STATUS_SKIPPED,
                            "Arquivo mantido sumiu ou mudou desde a análise",
                        )
                    )
                    continue

                cur: FileStamp | None = self._stamp(s.path)
                if cur is None or cur.size != s.size or cur.mtime_ns != s.mtime_ns:
                    records.append(
                        RemovalRecord(
                            s.path, g.keep.path, STATUS_SKIPPED,
                            "Arquivo sumiu ou mudou desde a análise",
                        )
                    )
                    continue
                if os.path.abspath(s.path) == os.path.abspath(g.keep.path):
                    continue

                try:
                    os.remove(s.path)
                except OSError as e:
                    records.append(
                        RemovalRecord(s.path, g.keep.path, STATUS_FAILED, str(e))
                    )
                else:
                    records.append(RemovalRecord(s.path, g.keep.path, STATUS_REMOVED, ""))

        return records

    # ---------------------------------------------------------- log
    @staticmethod
    def write_log(records: list[RemovalRecord], log_dir: Directory) -> File:
        out: File = log_dir.join_file(
            f"duplicados-removidos-{datetime.now():%Y%m%d-%H%M%S}.xlsx"
        )
        df: pd.DataFrame = pd.DataFrame(
            [
                {"arquivo": r.path, "mantido": r.kept, "status": r.status, "mensagem": r.message}
                for r in records
            ],
            columns=["arquivo", "mantido", "status", "mensagem"],
        )
        log_dir.mkdir()
        tmp: str = f"{out.absolute()}-tmp.xlsx"
        df.to_excel(tmp, index=False)
        os.replace(tmp, out.absolute())
        return out
