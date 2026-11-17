from __future__ import annotations
import os
import threading
from typing import Callable

import pandas as pd

from table_stream import (
    ContentFiles,
    Directory,
    EnumDocuments,
    File,
    Set,
)

from whatsapp_files import (
    AddChatsOnTable,
    BuilderConfigWhatsApp,
    ControllerWhatsApp,
    HeaderWhatsApp,
    InvokeCommandsWp,
    RenameChat,
    UncompressChats,
)

from responds.page_whatsapp.common import ImportItem, ImportStatus, TaskResult
from responds.page_whatsapp.dedup_folder import (
    STATUS_FAILED,
    STATUS_REMOVED,
    DuplicateFolderService,
    DuplicatePlan,
    RemovalRecord,
)

SUMMARY_COLUMNS: list[str] = [
    "CHAT",
    "MENSAGENS",
    "ANEXOS",
    "ANEXOS COM HASH",
    "PRIMEIRA MSG",
    "ÚLTIMA MSG",
]

TASK_COLUMNS: list[str] = ["ARQUIVO", "CLASSIFICAÇÃO", "STATUS", "DESTINO", "MENSAGEM"]

ACCEPTED_EXTENSIONS: tuple[str, ...] = (".zip", ".txt")

# Extensões de cartas TOI aceitas ao varrer uma pasta (sem diferenciar maiúsculas).
CARTA_EXTENSIONS: tuple[str, ...] = (".pdf", ".png", ".jpg", ".jpeg")

# Comandos de chat disponíveis na UI.
CMD_UNZIP = "unzip"
CMD_ADD_CACHE = "add_cache"
CMD_RENAME_MONTH = "rename_month"
CMD_RENAME_DAY = "rename_day"
CMD_FULL_MONTH = "full_month"
CMD_FULL_DAY = "full_day"

MOVING_COMMANDS = {CMD_RENAME_MONTH, CMD_RENAME_DAY, CMD_FULL_MONTH, CMD_FULL_DAY}

_CATEGORIAS: tuple[tuple[str, str], ...] = (
    ("CARTAS_UC_NAO_IDENTIFICADAS", "sem UC/TOI"),
    ("CARTAS_SO_UC", "só UC"),
    ("CARTAS_SO_TOI", "só TOI"),
    ("CARTAS_DATA_NAO_ENCONTRADA", "sem data"),
)


def _noop(*_a, **_k) -> None:
    pass


def _count_files(d: Directory) -> int:
    if not d.exists():
        return 0
    return sum(len(files) for _, _, files in os.walk(d.absolute()))


def _categoria(dest: str) -> str:
    p = dest.replace("\\", "/")
    for key, label in _CATEGORIAS:
        if f"/{key}/" in p:
            return label
    return "completa"


class ModelWhatsApp:
    """Model: sem UI. Importa chats, organiza chats e renomeia cartas TOI."""

    def __init__(self) -> None:
        self._controller: ControllerWhatsApp | None = None
        self._import_thread: threading.Thread | None = None
        self._load_thread: threading.Thread | None = None
        self._job_thread: threading.Thread | None = None

    # ------------------------------------------------------------------ infra
    @property
    def controller(self) -> ControllerWhatsApp:
        # Lazy: não lê nada do disco só por registrar a página.
        if self._controller is None:
            self._controller = ControllerWhatsApp()

        return self._controller

    def is_importing(self) -> bool:
        return self._import_thread is not None and self._import_thread.is_alive()

    def is_loading(self) -> bool:
        return self._load_thread is not None and self._load_thread.is_alive()

    def is_working(self) -> bool:
        return self._job_thread is not None and self._job_thread.is_alive()

    @staticmethod
    def cache_file() -> File:
        return BuilderConfigWhatsApp().builder().file_table

    @staticmethod
    def work_dir() -> Directory:
        return BuilderConfigWhatsApp().builder().work_dir

    @staticmethod
    def dir_chats_organizados() -> Directory:
        return BuilderConfigWhatsApp().builder().dir_export_files

    @staticmethod
    def dir_chats_compactados() -> Directory:
        return BuilderConfigWhatsApp().builder().dir_zip_chats

    @staticmethod
    def dir_cartas() -> Directory:
        from cartas import BuilderConfigTOI  # lazy: cartas inicializa OCR/config

        return BuilderConfigTOI().builder().dir_base_toi

    # ------------------------------------------------------------------ resumo do cache
    def load_summary(self, *, reload: bool = False) -> pd.DataFrame:
        """Uma linha por chat: mensagens, anexos, anexos com hash e período."""
        tb = self.controller.rw.load_table_whatsapp(reload=reload)
        if tb.is_empty():
            return pd.DataFrame(columns=SUMMARY_COLUMNS)

        df = tb.to_dataframe()
        df.columns = [str(c) for c in df.columns]

        c_chat = HeaderWhatsApp.name_chat.value
        c_file = HeaderWhatsApp.contains_file.value
        c_hash = HeaderWhatsApp.hash_md5.value
        c_dt = HeaderWhatsApp.date_hour.value

        work = pd.DataFrame(
            {
                "chat": df[c_chat],
                "anexo": df[c_file] == "True",
                "hash": ~df[c_hash].isin(["", "nan", "NULL_TEXT"]),
                "dt": pd.to_datetime(df[c_dt], errors="coerce"),
            }
        )

        g = work.groupby("chat", sort=True).agg(
            msgs=("chat", "size"),
            anexos=("anexo", "sum"),
            com_hash=("hash", "sum"),
            ini=("dt", "min"),
            fim=("dt", "max"),
        )

        out = pd.DataFrame(
            {
                "CHAT": g.index,
                "MENSAGENS": g["msgs"].astype(int).values,
                "ANEXOS": g["anexos"].astype(int).values,
                "ANEXOS COM HASH": g["com_hash"].astype(int).values,
                "PRIMEIRA MSG": g["ini"].dt.strftime("%d/%m/%Y").fillna("-").values,
                "ÚLTIMA MSG": g["fim"].dt.strftime("%d/%m/%Y").fillna("-").values,
            }
        )
        return out[SUMMARY_COLUMNS]

    def start_load_summary(
        self,
        on_done: Callable[[pd.DataFrame | None, Exception | None], None],
        *,
        reload: bool = False,
    ) -> None:
        if self.is_loading():
            raise RuntimeError("Já existe uma leitura em andamento")

        def work() -> None:
            df: pd.DataFrame | None = None
            err: Exception | None = None
            try:
                df = self.load_summary(reload=reload)
            except Exception as e:
                err = e
            finally:
                on_done(df, err)

        self._load_thread = threading.Thread(
            target=work, daemon=True, name="whatsapp-summary"
        )
        self._load_thread.start()

    # ------------------------------------------------------------------ importação de chats
    def import_file(self, f: File) -> ImportItem:
        """Importa UM arquivo. Nunca levanta: o erro vira ImportItem(ERROR)."""
        ext = (f.extension() or "").lower()
        try:
            if ext == ".zip":
                res = self.controller.increment_chat_zip(f)
            elif ext == ".txt":
                res = self.controller.increment_chat_file(f)
            else:
                raise ValueError(f"Tipo de arquivo não suportado: {ext or '-'}")
        except Exception as e:
            return ImportItem(f.basename(), ImportStatus.ERROR, str(e))

        return ImportItem(f.basename(), ImportStatus.OK, "", res)

    def start_import(
        self,
        files: list[File],
        *,
        on_begin: Callable[[int, int, str], None] = _noop,
        on_item: Callable[[int, int, ImportItem], None] = _noop,
        on_done: Callable[[list[ImportItem], Exception | None], None] = _noop,
    ) -> None:
        if self.is_importing():
            raise RuntimeError("Já existe uma importação em andamento")

        def work() -> None:
            items: list[ImportItem] = []
            err: Exception | None = None
            total = len(files)
            try:
                for n, f in enumerate(files, start=1):
                    on_begin(n, total, f.basename())
                    item = self.import_file(f)
                    items.append(item)
                    on_item(n, total, item)
            except Exception as e:
                err = e
            finally:
                on_done(items, err)

        self._import_thread = threading.Thread(
            target=work, daemon=True, name="whatsapp-import"
        )
        self._import_thread.start()

    # ------------------------------------------------------------------ tarefas genéricas
    def _start_job(
        self,
        name: str,
        work: Callable[[], TaskResult],
        on_done: Callable[[TaskResult | None, Exception | None], None],
    ) -> None:
        if self.is_working():
            raise RuntimeError("Já existe uma tarefa em andamento")

        def run() -> None:
            res: TaskResult | None = None
            err: Exception | None = None
            try:
                res = work()
            except Exception as e:
                err = e
            finally:
                on_done(res, err)

        self._job_thread = threading.Thread(target=run, daemon=True, name=name)
        self._job_thread.start()

    def _start_thread[R](
            self,
            name: str,
            work: Callable[[], R],
            on_done: Callable[[R | None, Exception | None], None],
    ) -> None:
        """Como _start_job, mas devolve qualquer tipo (não só TaskResult)."""
        if self.is_working():
            raise RuntimeError("Já existe uma tarefa em andamento")

        def run() -> None:
            res: R | None = None
            err: Exception | None = None
            try:
                res = work()
            except Exception as e:
                err = e
            finally:
                on_done(res, err)

        self._job_thread = threading.Thread(target=run, daemon=True, name=name)
        self._job_thread.start()

    # ------------------------------------------------------------------ III) duplicados por pasta
    def start_scan_duplicates(
                self,
                folder: Directory,
                on_done: Callable[[DuplicatePlan | None, Exception | None], None],
        ) -> None:
            """Fase 1: só analisa (hash por pasta). Não altera nenhum arquivo."""
            self._start_thread(
                "wp-dup-scan", lambda: DuplicateFolderService().scan(folder), on_done
            )

    def execute_duplicates(self, plan: DuplicatePlan) -> TaskResult:
        """Fase 2: apaga as duplicadas do plano e grava o log em Excel."""
        svc = DuplicateFolderService()
        records: list[RemovalRecord] = svc.execute(plan)
        log = svc.write_log(records, self.work_dir().concat("LogsDuplicados", True))

        removed: int = sum(1 for r in records if r.status == STATUS_REMOVED)
        failed: int = sum(1 for r in records if r.status == STATUS_FAILED)
        skipped: int = len(records) - removed - failed

        view = pd.DataFrame(
            {
                "ARQUIVO": [os.path.basename(r.path) for r in records],
                "CLASSIFICAÇÃO": ["duplicada"] * len(records),
                "STATUS": [r.status for r in records],
                "DESTINO": [r.kept for r in records],  # arquivo que foi mantido
                "MENSAGEM": [r.message for r in records],
            }
        )[TASK_COLUMNS]

        msg = (
            f"Duplicadas removidas: {removed} | falhas: {failed} | ignoradas: {skipped}\n"
            f"Pasta: {plan.root}\n"
            f"Log: {log.absolute()}"
        )
        return TaskResult("Remover duplicados", msg, view)

    def start_execute_duplicates(
                self,
                plan: DuplicatePlan,
                on_done: Callable[[TaskResult | None, Exception | None], None],
        ) -> None:
            # on_done da fase 1 roda dentro da thread anterior: espera ela terminar.
            t = self._job_thread
            if t is not None and t.is_alive():
                t.join(timeout=2.0)
            self._start_job("wp-dup-remove", lambda: self.execute_duplicates(plan), on_done)

    # ------------------------------------------------------------------ I) cartas TOI

    @staticmethod
    def list_cartas(folder: Directory, max_files: int = 200_000) -> list[File]:
        """PDFs e imagens da pasta, lendo as subpastas (ContentFiles, recursivo)."""
        content = ContentFiles(folder, max_files=max_files)
        everything = content.get_files(EnumDocuments.ALL, sort=True, recursive=True)
        return [
            f for f in everything if (f.extension() or "").lower() in CARTA_EXTENSIONS
        ]

    def rename_cartas(self, files: list[File]) -> TaskResult:
        """
        Identifica e organiza cartas TOI SEM criar duplicadas ('-1', '-2' ...):
          1) índice hash->arquivo (Excel) da pasta de cartas, atualizado de forma incremental;
          2) cartas cujo hash já existe (ou repetidas no lote) NÃO são movidas;
          3) destino já existente nunca é sobrescrito nem ganha sufixo.
        """
        # lazy: cartas inicializa OCR/config
        from responds.page_whatsapp.dedup_cartas import (
            STATUS_DUPLICATE,
            CartasHashIndex,
            DedupResult,
            RenameCartasSemDuplicatas,
            split_duplicates,
        )

        valid: list[File] = [
            f
            for f in files
            if f.is_pdf()
            or f.is_image()
            or (f.extension() or "").lower() in CARTA_EXTENSIONS
        ]
        if not valid:
            raise ValueError("Selecione cartas em PDF ou imagem.")

        index: CartasHashIndex = CartasHashIndex.create_default(self.dir_cartas())
        index.refresh()
        dedup: DedupResult = split_duplicates(valid, index)

        columns: list[str] = ["src", "dest", "status", "exception"]
        df_moves: pd.DataFrame = pd.DataFrame(columns=columns)
        if dedup.unique:
            rn = RenameCartasSemDuplicatas(Set(dedup.unique), modo_v2=True)
            rn.execute()
            rn.process_error_ucs()
            df_moves = rn.table_status.to_dataframe().astype(str)
            for c in columns:
                if c not in df_moves.columns:
                    df_moves[c] = ""
            df_moves = df_moves[columns]
            index.refresh()  # registra o que acabou de ser movido

        df_dup: pd.DataFrame = pd.DataFrame(
            [
                {
                    "src": d.src,
                    "dest": d.existing,
                    "status": STATUS_DUPLICATE,
                    "exception": d.reason,
                }
                for d in dedup.duplicates
            ],
            columns=columns,
        )
        df: pd.DataFrame = pd.concat([df_moves, df_dup], ignore_index=True).astype(str)

        if df.empty:
            return TaskResult("Cartas TOI", "Nenhum arquivo processado.", None)

        ok = df["status"] == "SUCESSO"
        dup = df["status"] == STATUS_DUPLICATE
        failed = ~ok & ~dup

        categorias = df["dest"].map(_categoria)
        categorias = categorias.where(~dup, "duplicada")

        view = pd.DataFrame(
            {
                "ARQUIVO": df["src"].map(os.path.basename),
                "CLASSIFICAÇÃO": categorias,
                "STATUS": df["status"],
                "DESTINO": df["dest"],
                "MENSAGEM": df["exception"],
            }
        )[TASK_COLUMNS]

        resumo = categorias[ok].value_counts()
        linhas: list[str] = [
            f"{len(df)} arquivos | movidos: {int(ok.sum())} | "
            f"duplicadas (não movidas): {int(dup.sum())} | falhas: {int(failed.sum())}"
        ]
        for label in ("completa", "só UC", "só TOI", "sem data", "sem UC/TOI"):
            if label in resumo:
                linhas.append(f"  • {label}: {int(resumo[label])}")
        linhas.append(f"\nPasta: {self.dir_cartas().absolute()}")
        if dup.any():
            linhas.append(
                "Duplicadas permanecem na pasta de origem (nada é apagado); "
                "a coluna DESTINO mostra o arquivo que já existia."
            )
        if failed.any():
            linhas.append("Veja a tabela de log para os arquivos com falha.")

        return TaskResult("Cartas TOI", "\n".join(linhas), view)

    def start_rename_cartas_folder(
        self,
        folder: Directory,
        on_done: Callable[[TaskResult | None, Exception | None], None],
    ) -> None:
        """Varre a pasta (recursivo) e renomeia/organiza as cartas, tudo na worker thread."""

        def work() -> TaskResult:
            files = self.list_cartas(folder)
            if not files:
                raise ValueError(
                    f"Nenhum PDF ou imagem encontrado em:\n{folder.absolute()}"
                )
            return self.rename_cartas(files)

        self._start_job("toi-rename-folder", work, on_done)

    def start_rename_cartas(
        self,
        files: list[File],
        on_done: Callable[[TaskResult | None, Exception | None], None],
    ) -> None:
        self._start_job("toi-rename", lambda: self.rename_cartas(files), on_done)

    # ------------------------------------------------------------------ II) comandos de chat
    def run_chat_command(self, kind: str) -> TaskResult:
        """Executa os Command() de whatsapp_files (descompactar / cache / renomear)."""
        titles = {
            CMD_UNZIP: "Descompactar chats",
            CMD_ADD_CACHE: "Atualizar cache dos chats descompactados",
            CMD_RENAME_MONTH: "Renomear arquivos dos chats (ano-mês)",
            CMD_RENAME_DAY: "Renomear arquivos dos chats (ano-mês-dia)",
            CMD_FULL_MONTH: "Fluxo completo (ano-mês)",
            CMD_FULL_DAY: "Fluxo completo (ano-mês-dia)",
        }
        if kind not in titles:
            raise ValueError(f"Comando desconhecido: {kind}")

        invoke = InvokeCommandsWp()
        out_dir = self.dir_chats_organizados()
        before = _count_files(out_dir)

        if kind in (CMD_UNZIP, CMD_FULL_MONTH, CMD_FULL_DAY):
            invoke.add(UncompressChats())
        if kind in (CMD_ADD_CACHE, CMD_FULL_MONTH, CMD_FULL_DAY):
            invoke.add(AddChatsOnTable())
        if kind in MOVING_COMMANDS:
            rn = RenameChat()
            rn.includ_day = kind in (CMD_RENAME_DAY, CMD_FULL_DAY)
            invoke.add(rn)

        invoke.run()

        # Os comandos escrevem no cache em memória: relê para refletir no resumo.
        lines = [f"{titles[kind]}: concluído."]
        if kind in MOVING_COMMANDS:
            moved = max(_count_files(out_dir) - before, 0)
            lines.append(f"Arquivos organizados nesta execução: {moved}")
            lines.append(f"Pasta: {out_dir.absolute()}")
        if kind in (CMD_UNZIP, CMD_FULL_MONTH, CMD_FULL_DAY):
            lines.append(f"Zips lidos de: {self.dir_chats_compactados().absolute()}")
        return TaskResult(titles[kind], "\n".join(lines), None)

    def start_chat_command(
        self,
        kind: str,
        on_done: Callable[[TaskResult | None, Exception | None], None],
    ) -> None:
        self._start_job(f"wp-{kind}", lambda: self.run_chat_command(kind), on_done)
