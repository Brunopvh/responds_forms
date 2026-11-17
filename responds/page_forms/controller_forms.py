from __future__ import annotations
import os
from datetime import datetime
from typing import Callable
import threading

import pandas as pd
from pyflutter_ui.ui import ChangeNotifier, Provider
from pyflutter_ui.scheduler import MainThreadScheduler

from pyflutter_ui import AppConfigNotifier

from responds.page_forms.common import MapRows, StatusForms, HeaderForms
from responds.page_forms.master_forms import ControllerMasterForms, make_key
from responds.page_forms.model_forms import (
    ModelForms,
    FormsCallbacks,
    ResultGenerateTable,
)
from table_stream import File, Directory, TableData, ArrayList

from cartas import HeaderFilesTOI, BuilderTableFilesTOI
from table_stream import File, Directory, TableData


def _ui(fn: Callable[[], None]) -> None:
    """Executa fn na thread da UI (os callbacks do Model vêm da worker thread)."""
    try:
        MainThreadScheduler.run(fn)
    except RuntimeError:
        fn()


class ControllerForms(ChangeNotifier):

    def __init__(self, model: ModelForms) -> None:
        super().__init__()
        self.model: ModelForms = model
        self.map_rows = MapRows()
        self.table_toi: TableData[HeaderFilesTOI] = TableData()
        self.selected_table_file: File | None = None

        self.status_text: str = "Importe uma tabela TOI para começar."
        self.progress: tuple[int, int] = (0, 0)
        self.send_receipt: bool = True

        self.master = ControllerMasterForms()
        self.generating: bool = False

        self.scanning: bool = False  # NOVO: lendo a pasta

        # Log em Excel gravado durante o lançamento (1 arquivo por execução).
        self.save_every: int = 2  # grava a cada N linhas concluídas (sucesso OU falha)
        self.result_file: File | None = None
        self._since_save: int = 0

        self.fn_show_error: Callable[[str], None] | None = None
        self.fn_show_info: Callable[[str], None] | None = None

    # ------------------------------------------------------------------ infra
    @property
    def running(self) -> bool:
        return self.model.is_running()

    @property
    def progress_fraction(self) -> float:
        done, total = self.progress
        return (done / total) if total > 0 else 0.0

    def get_config(self) -> AppConfigNotifier:
        return Provider.read(AppConfigNotifier)

    def get_initial_dir(self) -> Directory:
        cfg = self.get_config()
        map_initial_dir = cfg.value.initial_dir_map

        if map_initial_dir.header().contains("page_forms"):
            return map_initial_dir.get_value("page_forms")
        return cfg.value.initial_dir

    def set_initial_dir(self, d: Directory):
        k = "page_forms"
        cfg = self.get_config().value

        cfg.initial_dir_map[k] = d
        self.get_config().value = cfg

    def show_info(self, i: str) -> None:
        if self.fn_show_info is not None:
            _ui(lambda: self.fn_show_info(i))

    def show_error(self, e: str) -> None:
        if self.fn_show_error is not None:
            _ui(lambda: self.fn_show_error(e))

        # ------------------------------------------------------------------ master

    def _apply_master(self, mp: MapRows) -> int:
        """Marca como SKIPPED o que já está no master (key UC+TOI) ou repetido na tabela."""
        keys = self.master.load_keys()
        seen: set[str] = set()
        skipped = 0

        for idx in mp.header():
            row = mp[idx]
            if mp.get_status(idx) == StatusForms.SUCCESS:
                seen.add(make_key(row.get(HeaderForms.UC), row.get(HeaderForms.TOI)))
                continue

            key = make_key(row.get(HeaderForms.UC), row.get(HeaderForms.TOI))
            if key in keys:
                mp.update_status(idx, StatusForms.SKIPPED, "Já lançada (master)")
                skipped += 1
            elif key in seen:
                mp.update_status(idx, StatusForms.SKIPPED, "Duplicada na tabela")
                skipped += 1
            seen.add(key)
        return skipped

    # ------------------------------------------------------------------ importação
    def set_map_rows(self, mp: MapRows) -> None:
        if mp.is_empty():
            self.show_error("Nenhuma linha TOI encontrada na tabela.")
            return

        try:
            skipped = self._apply_master(mp)
        except Exception as e:
            self.show_error(f"Falha ao ler o arquivo master:\n{e}")
            return

        self.map_rows = mp
        self.progress = (0, 0)
        pending = mp.size_header() - skipped
        self.status_text = (
            f"{mp.size_header()} cartas importadas | "
            f"{skipped} já lançadas/ignoradas | {pending} a lançar."
        )
        self.notify_listeners()

    # ------------------------------------------------------------------ gerar tabela (cache)
    def generate_table(self, files: ArrayList[File]) -> None:
        if self.running or self.generating or self.scanning:
            self.show_info("Existe outra operação em andamento.")
            return

        if files.empty():
            return

        self.generating = True
        self.progress = (0, 0)
        self.status_text = (
            f"Gerando tabela a partir de {files.size()} arquivos (somente cache)..."
        )
        self.notify_listeners()

        try:
            self.model.start_generate(
                files,
                on_progress=lambda d, t: _ui(lambda: self._on_gen_progress(d, t)),
                on_done=lambda r, e: _ui(lambda: self._on_gen_done(r, e)),
            )
        except Exception as e:
            self.generating = False
            self.show_error(str(e))

    def generate_table_from_folder(self, folder: Directory) -> None:
        """Varre a pasta (recursivo, PDF/imagem) e gera a tabela só com o cache."""
        if self.running or self.generating or self.scanning:
            self.show_info("Existe outra operação em andamento.")
            return
        if not folder.exists():
            self.show_error(f"A pasta não existe:\n{folder.absolute()}")
            return

        self.scanning = True
        self.status_text = f"Lendo {folder.absolute()} (incluindo subpastas) ..."
        self.notify_listeners()

        def work() -> None:
            files: ArrayList[File] | None = None
            err: Exception | None = None
            try:
                files = self.model.list_documents(folder)
            except Exception as e:
                err = e
            _ui(lambda: self._on_folder_scanned(folder, files, err))

        threading.Thread(target=work, daemon=True, name="forms-scan").start()

    def _on_folder_scanned(
        self,
        folder: Directory,
        files: ArrayList[File] | None,
        err: Exception | None,
    ) -> None:
        self.scanning = False

        if err is not None or files is None:
            self.status_text = f"Erro ao ler a pasta: {err}"
            self.notify_listeners()
            self.show_error(f"Não foi possível ler a pasta:\n{err}")
            return

        if files.empty():
            self.status_text = "Nenhum PDF/imagem encontrado na pasta."
            self.notify_listeners()
            self.show_info(f"Nenhum PDF ou imagem encontrado em:\n{folder.absolute()}")
            return

        self.status_text = f"{files.size()} arquivo(s) encontrados. Gerando tabela ..."
        self.notify_listeners()
        self.generate_table(files)  # fluxo existente (hash + cache + Excel)

    def _on_gen_progress(self, done: int, total: int) -> None:
        self.progress = (done, total)
        self.status_text = f"Calculando hashes {done}/{total}"
        if done == total or done % 25 == 0:  # evita piscar a tela
            self.notify_listeners()

    def _on_gen_done(
        self, res: ResultGenerateTable | None, err: Exception | None
    ) -> None:
        self.generating = False
        self.progress = (0, 0)

        if err is not None:
            self.status_text = f"Erro ao gerar tabela: {err}"
            self.notify_listeners()
            self.show_error(str(err))
            return

        if res is None or res.table is None:
            self.status_text = "Nenhum arquivo encontrado no cache."
            self.notify_listeners()
            self.show_info(
                "Nenhum dos arquivos está na tabela TOI em cache.\n"
                "Aplique o OCR/relatório TOI antes de gerar a tabela."
            )
            return

        self.status_text = f"Tabela gerada: {res.found}/{res.total} arquivos."
        self.notify_listeners()

        msg = f"Tabela gerada com {res.found} de {res.total} arquivos.\n\n{res.file.absolute()}"
        if res.not_found:
            sample = "\n".join(res.not_found[:10])
            more = (
                f"\n... e mais {len(res.not_found) - 10}"
                if len(res.not_found) > 10
                else ""
            )
            msg += f"\n\nSem dados no cache ({len(res.not_found)}):\n{sample}{more}"
        if res.invalid:
            msg += f"\n\nIgnorados (não são PDF/imagem): {res.invalid}"
        self.show_info(msg)

    def set_table_toi(self, tb: TableData[HeaderFilesTOI]) -> None:
        if tb.is_empty():
            self.show_error("Tabela TOI vazia")
            return

        missing = [
            h.value
            for h in (
                HeaderFilesTOI.UC,
                HeaderFilesTOI.TOI,
                HeaderFilesTOI.DATE,
                HeaderFilesTOI.FULL_PATH,
            )
            if not tb.header().contains(h)
        ]
        if missing:
            self.show_error(
                "A tabela não tem as colunas necessárias: "
                + ", ".join(missing)
                + "\n\nUse o relatório TOI (com o caminho do arquivo), não a tabela de cache."
            )
            return

        self.table_toi = tb
        self.set_map_rows(MapRows.create_from_table(tb))

    def set_data(self, df: pd.DataFrame) -> None:
        builder = BuilderTableFilesTOI()
        tb = builder.from_data(df)
        self.set_table_toi(tb)

    def set_selected_table_toi(self, f: File) -> None:
        try:
            # dtype=str evita UC virar float e preserva zeros à esquerda
            df = pd.read_excel(f.absolute(), dtype=str)
        except Exception as e:
            self.show_error(f"Não foi possível ler a planilha:\n{e}")
            return
        self.selected_table_file = f
        self.set_data(df)

    def set_send_receipt(self, value: bool) -> None:
        self.send_receipt = value  # sem notify: evita rebuild da página ao marcar

    # ------------------------------------------------------------------ execução
    def start_forms(self) -> None:
        if self.running or self.generating or self.scanning:
            self.show_info("Já existe uma operação em andamento.")
            return

        if self.map_rows.is_empty():
            self.show_error("Importe uma tabela TOI antes de iniciar.")
            return

        try:
            self._apply_master(self.map_rows)  # o master pode ter mudado
        except Exception as e:
            self.show_error(f"Falha ao ler o arquivo master:\n{e}")
            return

        jobs = {}
        for idx in self.map_rows.header():
            if self.map_rows.get_status(idx) in (
                StatusForms.SUCCESS,
                StatusForms.SKIPPED,
            ):
                continue
            try:
                jobs[idx] = self.model.build_submission(self.map_rows[idx])
                self.map_rows.update_status(idx, StatusForms.PENDING)
            except ValueError as e:
                self.map_rows.update_status(idx, StatusForms.FAILED, str(e))

        if not jobs:
            self.status_text = (
                "Nenhuma carta nova para lançar (todas já lançadas ou inválidas)."
            )
            self.notify_listeners()
            return

        # ... resto idêntico ao atual
        config = self.model.create_config(
            self.get_config().value.work_dir, self.send_receipt
        )
        out_dir = (
            self.get_config()
            .value.work_dir.concat("Forms", True)
            .concat("Resultados", True)
        )
        self.result_file = out_dir.join_file(
            f"resultado-forms-{datetime.now():%Y%m%d-%H%M%S}.xlsx"
        )
        self._since_save = 0
        self.save_result(silent=True)  # já grava as linhas inválidas

        self.progress = (0, len(jobs))
        self.status_text = "Iniciando..."
        self.notify_listeners()

        self.model.start(
            jobs,
            config,
            FormsCallbacks(
                on_status=lambda i, s, m: _ui(lambda: self._on_status(i, s, m)),
                on_phase=lambda t: _ui(lambda: self._on_phase(t)),
                on_progress=lambda d, t: _ui(lambda: self._on_progress(d, t)),
                on_done=lambda err, stopped: _ui(lambda: self._on_done(err, stopped)),
            ),
        )

    def stop_forms(self) -> None:
        if not self.running:
            return
        self.model.request_stop()
        self.status_text = "Parando após a linha atual..."
        self.notify_listeners()

    # ------------------------------------------------------------------ callbacks (thread da UI)
    def _on_status(self, idx: int, status: StatusForms, msg: str) -> None:
        self.map_rows.update_status(idx, status, msg)

        if status == StatusForms.SUCCESS:
            try:
                self.master.register(self.map_rows[idx])
            except Exception as e:
                self.show_error(f"Carta lançada, mas falhou ao gravar no master:\n{e}")

        if status in (StatusForms.SUCCESS, StatusForms.FAILED):
            self._since_save += 1
            if self._since_save >= self.save_every:
                self._since_save = 0
                self.save_result(silent=True)
            self.notify_listeners()
        # RUNNING não notifica: on_phase/on_progress já atualizam a tela.

    def _on_phase(self, text: str) -> None:
        self.status_text = text
        self.notify_listeners()

    def _on_progress(self, done: int, total: int) -> None:
        self.progress = (done, total)
        self.notify_listeners()

    def _on_done(self, err: Exception | None, stopped: bool) -> None:
        ok = self.map_rows.count_status(StatusForms.SUCCESS)
        bad = self.map_rows.count_status(StatusForms.FAILED)
        skip = self.map_rows.count_status(StatusForms.SKIPPED)
        summary = f"sucesso: {ok} | falha: {bad} | ignoradas: {skip}"
        # summary = f"sucesso: {ok} | falha: {bad}"

        if err is not None:
            self.status_text = f"Erro: {err}"
            self.show_error(str(err))
        elif stopped:
            self.status_text = f"Interrompido | {summary}"
        else:
            self.status_text = f"Concluído | {summary}"

        self.save_result(silent=True)
        self.notify_listeners()

    def get_dir_datetime(self) -> str:
        t = datetime.now()
        d = f"{t.year}-{t.month}-{t.day}"
        return d

    # ------------------------------------------------------------------ resultado
    def save_result(self, *, silent: bool = False) -> None:

        if self.map_rows.is_empty():
            if not silent:
                self.show_info("Nada para salvar.")
            return

        out = self.result_file

        if out is None:
            out_dir: Directory = (
                self.get_config()
                .value.work_dir.concat("Forms", True)
                .concat("Resultados", True)
            )
            out_dir = out_dir.concat(self.get_dir_datetime(), True)

            out = out_dir.join_file(f"LogForms-{datetime.now():%Y%m%d-%H%M%S}.xlsx")
            self.result_file = out

        try:
            # grava em arquivo temporário e renomeia: nunca deixa um .xlsx corrompido/0 bytes
            tmp = File(f"{out.absolute()}-tmp.xlsx")
            self.map_rows.save(tmp)
            os.replace(tmp.absolute(), out.absolute())
        except Exception as e:
            self.show_error(f"Falha ao salvar o resultado:\n{e}")
            return

        print(f"{__class__.__name__} resultado salvo em ... {out.absolute()}")
        if not silent:
            self.show_info(f"Resultado salvo em:\n{out.absolute()}")
