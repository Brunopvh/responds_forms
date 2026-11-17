from __future__ import annotations
import time
from typing import Callable

import pandas as pd
from table_stream import Directory, File
from pyflutter_ui import ChangeNotifier, Provider, AppConfigNotifier
from pyflutter_ui.scheduler import MainThreadScheduler
from responds.page_whatsapp.common import (
    ImportItem,
    ImportStatus,
    ImportSummary,
    TaskResult,
)

from responds.page_whatsapp.model_whatsapp import (
    ACCEPTED_EXTENSIONS,
    SUMMARY_COLUMNS,
    TASK_COLUMNS,
    ModelWhatsApp,
)

from responds.page_whatsapp.dedup_folder import DuplicatePlan


LOG_COLUMNS: list[str] = [
    "ARQUIVO",
    "CHAT",
    "MENSAGENS",
    "ANEXOS",
    "COM HASH",
    "NOVAS",
    "STATUS",
    "MENSAGEM",
]


def _ui(fn: Callable[[], None]) -> None:
    """Executa fn na thread da UI (os callbacks do Model vêm da worker thread)."""
    try:
        MainThreadScheduler.run(fn)
    except RuntimeError:
        fn()


class ControllerWhatsAppPage(ChangeNotifier):

    def __init__(self, model: ModelWhatsApp) -> None:
        super().__init__()
        self.model: ModelWhatsApp = model

        self.summary_df: pd.DataFrame = pd.DataFrame(columns=SUMMARY_COLUMNS)
        self.summary_loaded: bool = False

        self.items: list[ImportItem] = []
        self.summary: ImportSummary | None = None

        # Tabela de baixo: "import" (última importação) ou "task" (último comando/cartas)
        self.log_mode: str = "import"
        self.log_title: str = "Última importação"
        self.task_df: pd.DataFrame | None = None

        self.loading: bool = False
        self.importing: bool = False
        self.working: bool = False
        self.progress: tuple[int, int] = (0, 0)
        self.status_text: str = "Importe o .zip exportado do WhatsApp para começar."
        self._started: float = 0.0

        self.fn_show_error: Callable[[str], None] | None = None
        self.fn_show_info: Callable[[str], None] | None = None
        self.fn_confirm: Callable[[str], bool] | None = None

    # ------------------------------------------------------------------ infra
    def get_config(self) -> AppConfigNotifier:
        return Provider.read(AppConfigNotifier)

    def show_error(self, msg: str) -> None:
        if self.fn_show_error is not None:
            self.fn_show_error(msg)

    def show_info(self, msg: str) -> None:
        if self.fn_show_info is not None:
            self.fn_show_info(msg)

    @property
    def busy(self) -> bool:
        return self.loading or self.importing or self.working

    @property
    def progress_fraction(self) -> float:
        done, total = self.progress
        return (done / total) if total > 0 else 0.0

    @property
    def cache_label(self) -> str:
        return self.model.cache_file().absolute()

    @property
    def info_text(self) -> str:
        if self.summary_df.empty:
            return "Cache vazio"
        chats = len(self.summary_df)
        msgs = int(self.summary_df["MENSAGENS"].sum())
        return f"{chats} conversas | {msgs} mensagens no cache"

    # ------------------------------------------------------------------ dados para as tabelas
    def view_data(self) -> pd.DataFrame:
        if self.summary_df.empty:
            return pd.DataFrame({"-": ["Sem dados no cache"]})
        return self.summary_df

    def log_data(self) -> pd.DataFrame:
        if self.log_mode == "task":
            if self.task_df is None or self.task_df.empty:
                return pd.DataFrame({"-": ["Sem detalhes para esta tarefa"]})
            return self.task_df

        if not self.items:
            return pd.DataFrame({"-": ["Nenhuma importação nesta sessão"]})

        records = []
        for it in self.items:
            r = it.result
            records.append(
                {
                    "ARQUIVO": it.source,
                    "CHAT": r.chat if r else "-",
                    "MENSAGENS": r.messages if r else "-",
                    "ANEXOS": r.attachments if r else "-",
                    "COM HASH": r.hashed if r else "-",
                    "NOVAS": r.added if r else "-",
                    "STATUS": it.status.value,
                    "MENSAGEM": it.message,
                }
            )
        return pd.DataFrame(records, columns=LOG_COLUMNS)

    # ------------------------------------------------------------------ resumo do cache
    def ensure_summary(self) -> None:
        """Lê o cache uma vez (em worker thread) quando a página abre."""
        if self.summary_loaded or self.busy:
            return
        self.refresh_summary()

    def refresh_summary(self, *, reload: bool = True) -> None:
        if self.busy:
            self.show_info("Existe outra operação em andamento.")
            return

        self.loading = True
        self.status_text = "Lendo o cache do WhatsApp ..."
        self.notify_listeners()

        try:
            self.model.start_load_summary(
                lambda df, err: _ui(lambda: self._on_summary(df, err)),
                reload=reload,
            )
        except Exception as e:
            self.loading = False
            self.show_error(str(e))

    def _on_summary(self, df: pd.DataFrame | None, err: Exception | None) -> None:
        self.loading = False

        if err is not None or df is None:
            self.status_text = f"Erro ao ler o cache: {err}"
            self.notify_listeners()
            self.show_error(f"Não foi possível ler o cache do WhatsApp:\n{err}")
            return

        self.summary_df = df
        self.summary_loaded = True
        if self.summary is None and not self.working:
            self.status_text = (
                "Cache carregado." if not df.empty else "Cache vazio. Importe um chat."
            )
        self.notify_listeners()

    # ------------------------------------------------------------------ importação de chats
    def import_files(self, files: list[File]) -> None:
        if self.busy:
            self.show_info("Existe outra operação em andamento.")
            return

        valid = [
            f for f in files if (f.extension() or "").lower() in ACCEPTED_EXTENSIONS
        ]
        if not valid:
            self.show_error("Selecione arquivos .zip (ou .txt) de chats do WhatsApp.")
            return

        self.importing = True
        self.log_mode = "import"
        self.log_title = "Última importação"
        self.items = []
        self.summary = None
        self.progress = (0, len(valid))
        self.status_text = f"Iniciando a importação de {len(valid)} arquivo(s) ..."
        self._started = time.monotonic()
        self.notify_listeners()

        try:
            self.model.start_import(
                valid,
                on_begin=lambda n, t, name: _ui(lambda: self._on_begin(n, t, name)),
                on_item=lambda n, t, it: _ui(lambda: self._on_item(n, t, it)),
                on_done=lambda items, err: _ui(lambda: self._on_done(items, err)),
            )
        except Exception as e:
            self.importing = False
            self.show_error(str(e))

    def _on_begin(self, n: int, total: int, name: str) -> None:
        self.status_text = (
            f"Importando {n}/{total}: {name} "
            "(extraindo, lendo mensagens e calculando hashes das mídias ...)"
        )
        self.notify_listeners()

    def _on_item(self, n: int, total: int, item: ImportItem) -> None:
        self.items.append(item)
        self.progress = (n, total)
        self.notify_listeners()

    def _on_done(self, items: list[ImportItem], err: Exception | None) -> None:
        self.importing = False

        ok = sum(1 for i in items if i.status == ImportStatus.OK)
        bad = len(items) - ok
        added = sum(i.result.added for i in items if i.result is not None)
        elapsed = time.monotonic() - self._started

        self.summary = ImportSummary(
            total=len(items), ok=ok, errors=bad, added=added, elapsed_s=elapsed
        )
        self.status_text = (
            f"Concluído | importados: {ok} | erros: {bad} | "
            f"mensagens novas: {added} | {elapsed:.1f}s"
        )

        if err is not None:
            self.status_text = f"Erro: {err}"
            self.show_error(str(err))

        # Recarrega o resumo (a worker thread da importação já terminou).
        self.refresh_summary(reload=False)

        if items:
            self.show_info(self._build_report(items))

    @staticmethod
    def _build_report(items: list[ImportItem]) -> str:
        lines: list[str] = []
        for it in items:
            r = it.result
            if it.status == ImportStatus.OK and r is not None:
                lines.append(
                    f"✓ {r.chat or it.source}: {r.messages} mensagens, "
                    f"{r.attachments} anexos ({r.hashed} com hash) | "
                    f"{r.added} novas no cache"
                )
            else:
                lines.append(f"✗ {it.source}: {it.message}")

        no_hash = [
            it
            for it in items
            if it.result is not None and it.result.attachments > it.result.hashed
        ]
        if no_hash:
            lines.append(
                "\nAtenção: alguns anexos citados no chat não estavam no .zip "
                "(exportado 'sem mídia' ou arquivos removidos). "
                "Eles ficam no cache sem hash."
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------ tarefas (cartas / comandos de chat)
    def _begin_task(self, title: str, status: str) -> None:
        self.working = True
        self.log_mode = "task"
        self.log_title = title
        self.task_df = None
        self.summary = None
        self.progress = (0, 0)
        self.status_text = status
        self.notify_listeners()

    def import_cartas(self, files: list[File]) -> None:
        """I) Renomeia/organiza cartas TOI (PDF/imagem) usando nome + cache OCR + chat."""
        if self.busy:
            self.show_info("Existe outra operação em andamento.")
            return
        if not files:
            return

        self._begin_task(
            "Última operação: cartas TOI",
            f"Identificando {len(files)} carta(s) no cache OCR e movendo ...",
        )
        try:
            self.model.start_rename_cartas(
                files, lambda r, e: _ui(lambda: self._on_task_done(r, e))
            )
        except Exception as e:
            self.working = False
            self.show_error(str(e))

    def import_cartas_folder(self, folder: Directory) -> None:
        """
        I) Lê a pasta (recursivo), identifica e organiza as cartas TOI (PDF/imagem).
        """

        if self.busy:
            self.show_info("Existe outra operação em andamento.")
            return

        if not folder.exists():
            self.show_error(f"A pasta não existe:\n{folder.absolute()}")
            return

        self._begin_task(
            "Última operação: cartas TOI",
            f"Lendo {folder.absolute()} (incluindo subpastas) e identificando as cartas ...",
        )
        try:
            self.model.start_rename_cartas_folder(
                folder, lambda r, e: _ui(lambda: self._on_task_done(r, e))
            )
        except Exception as e:
            self.working = False
            self.show_error(str(e))

    def run_chat_command(self, kind: str) -> None:
        """II) Comandos de whatsapp_files (descompactar, cache, RenameChat ...)."""
        if self.busy:
            self.show_info("Existe outra operação em andamento.")
            return

        self._begin_task("Última operação: chats", "Executando comando de chats ...")
        try:
            self.model.start_chat_command(
                kind, lambda r, e: _ui(lambda: self._on_task_done(r, e))
            )
        except Exception as e:
            self.working = False
            self.show_error(str(e))

    def remove_duplicates_folder(self, folder: Directory) -> None:
        """
        III) Duplicados por pasta, em 2 fases:
          1. analisa (hash) e mostra o que SERIA apagado;
          2. só apaga se o usuário confirmar.
        """
        if self.busy:
            self.show_info("Existe outra operação em andamento.")
            return
        if not folder.exists():
            self.show_error(f"A pasta não existe:\n{folder.absolute()}")
            return

        self._begin_task(
            "Última operação: remover duplicados",
            f"Analisando duplicados em {folder.absolute()} (incluindo subpastas) ...",
        )
        try:
            self.model.start_scan_duplicates(
                folder, lambda p, e: _ui(lambda: self._on_scan_duplicates(p, e))
            )
        except Exception as e:
            self.working = False
            self.show_error(str(e))

    def _on_scan_duplicates(self, plan: DuplicatePlan | None, err: Exception | None) -> None:
        self.working = False

        if err is not None or plan is None:
            self.status_text = f"Erro: {err}"
            self.notify_listeners()
            self.show_error(f"Falha ao analisar duplicados:\n{err}")
            return

        if plan.total_remove == 0:
            self.status_text = f"Nenhum duplicado encontrado ({plan.scanned} arquivos analisados)."
            self.notify_listeners()
            msg = self.status_text
            if plan.errors:
                msg += f"\n\n{len(plan.errors)} arquivo(s) não puderam ser lidos."
            self.show_info(msg)
            return

        mb: float = plan.bytes_to_free / (1024 * 1024)
        question = (
            f"Pasta: {plan.root}\n\n"
            f"{plan.scanned} arquivos analisados.\n"
            f"{len(plan.groups)} grupo(s) de duplicados (mesmo conteúdo na MESMA pasta).\n"
            f"{plan.total_remove} arquivo(s) serão APAGADOS ({mb:.1f} MB), "
            "mantendo 1 de cada grupo.\n\n"
            "A exclusão é PERMANENTE (não vai para a lixeira) e será registrada "
            "em um log Excel.\n\nApagar agora?"
        )
        confirmed: bool = self.fn_confirm(question) if self.fn_confirm is not None else False
        if not confirmed:
            self.status_text = "Remoção de duplicados cancelada."
            self.notify_listeners()
            return

        self.working = True
        self.status_text = f"Apagando {plan.total_remove} duplicado(s) ..."
        self.notify_listeners()
        try:
            self.model.start_execute_duplicates(
                plan, lambda r, e: _ui(lambda: self._on_task_done(r, e))
            )
        except Exception as e:
            self.working = False
            self.show_error(str(e))

    def _on_task_done(self, res: TaskResult | None, err: Exception | None) -> None:
        self.working = False

        if err is not None or res is None:
            self.status_text = f"Erro: {err}"
            self.notify_listeners()
            self.show_error(f"Falha na operação:\n{err}")
            return

        self.log_title = f"Última operação: {res.title}"
        self.task_df = res.df
        first_line = res.message.splitlines()[0] if res.message else res.title
        self.status_text = f"Concluído | {first_line}"
        self.notify_listeners()

        # Chats mudaram o cache em memória: atualiza o resumo.
        self.refresh_summary(reload=False)
        self.show_info(res.message)

    # ------------------------------------------------------------------ utilidades
    def _open(self, d: Directory) -> None:
        raise NotImplementedError()

    def open_work_dir(self) -> None:
        raise NotImplementedError()

    def open_chats_dir(self) -> None:
        raise NotImplementedError()

    def open_cartas_dir(self) -> None:
        raise NotImplementedError()
