from __future__ import annotations
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime
from cartas import BuilderConfigTOI
from typing import Any, Callable

from table_stream import (
    ArrayList,
    File,
    Directory,
    HashMapDict,
    RowH,
    TableData,
    ContentFiles,
    EnumDocuments,
    load_file_hash,
)

from cartas import (
    ControllerTOI,
    HeaderFilesTOI,
    BuilderTableFilesTOI,
)

from responds.page_forms.common import (
    HeaderForms,
    StatusForms,
    clean_text,
    normalize_date,
)
from responds.page_forms.config import (
    FormsConfig,
    FormsSubmission,
    LOCAL_LABELS,
    TIPO_LABELS,
    DEFAULT_LOCAL,
    DEFAULT_TIPO,
)
from responds.page_forms.service import PlaywrightFormsService


def _noop(*_a, **_k) -> None:
    pass


@dataclass
class FormsCallbacks:
    """
    Chamados pela WORKER THREAD. Quem consome (Controller) é responsável por
    levar a atualização para a thread da UI.
    """

    on_status: Callable[[int, StatusForms, str], None] = _noop
    on_phase: Callable[[str], None] = _noop
    on_progress: Callable[[int, int], None] = _noop
    on_done: Callable[[Exception | None, bool], None] = _noop  # (erro, interrompido)


@dataclass
class ResultGenerateTable:
    table: TableData[HeaderFilesTOI] | None = None
    file: File | None = None
    total: int = 0
    found: int = 0
    invalid: int = 0
    not_found: list[str] = field(default_factory=list)


class ModelForms(object):

    def __init__(self) -> None:
        self._relatorio_toi: ControllerTOI | None = None
        self.builder_carta = BuilderTableFilesTOI()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # ------------------------------------------------------------------ estado
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def request_stop(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------------ relatório TOI (opcional)
    @property
    def relatorio_toi(self) -> ControllerTOI:
        # Lazy: instanciar CreateRelatorioTOI inicializa OCR/Tesseract,
        # o que não deve acontecer só por abrir a página do Forms.
        if self._relatorio_toi is None:
            self._relatorio_toi = ControllerTOI()
        return self._relatorio_toi

    def create_relatorio_toi(self, files: ArrayList[File]) -> TableData[HeaderFilesTOI]:
        if files.empty():
            return self.builder_carta.create_void()

        mp = HashMapDict()
        files.for_each(lambda f: mp.set_value(load_file_hash(f), f))

        tb: TableData[HeaderFilesTOI] | None = self.relatorio_toi.load_from_map(mp)
        if tb is None:
            return self.builder_carta.create_void()

        df = tb.to_dataframe().astype(str)

        df = df[df[HeaderFilesTOI.UC] != TableData.NULL_STRING]
        df = df[df[HeaderFilesTOI.TOI] != TableData.NULL_STRING]
        df = df[df[HeaderFilesTOI.DATE] != TableData.NULL_STRING]
        return self.builder_carta.from_data(df)

    # ------------------------------------------------------------------ validação/conversão
    @staticmethod
    def create_config(work_dir: Directory, send_receipt: bool = True) -> FormsConfig:
        base = work_dir.concat("Forms", True)
        return FormsConfig(
            user_data_dir=base.concat("browser-profile", True).absolute(),
            screenshot_dir=base.concat("screenshots", True).absolute(),
            send_receipt=send_receipt,
        )

    @staticmethod
    def build_submission(row: RowH[HeaderForms, Any]) -> FormsSubmission:
        """Valida uma linha e devolve a resposta pronta. Levanta ValueError se inválida."""
        uc = clean_text(row.get(HeaderForms.UC))
        toi = clean_text(row.get(HeaderForms.TOI))
        if not uc.isdigit():
            raise ValueError(f"UC inválida (o Forms exige número): '{uc}'")
        if not toi:
            raise ValueError("TOI vazio")

        date = normalize_date(row.get(HeaderForms.DATA_ENTREGA))

        local_raw = clean_text(
            row.get(HeaderForms.LOCAL_ENTREGA), DEFAULT_LOCAL
        ).upper()
        if local_raw in LOCAL_LABELS:
            local = LOCAL_LABELS[local_raw]
        elif local_raw in LOCAL_LABELS.values():
            local = local_raw
        else:
            raise ValueError(f"Local de entrega desconhecido: '{local_raw}'")

        tipo_raw = clean_text(row.get(HeaderForms.TIPO), DEFAULT_TIPO).upper()
        if tipo_raw in TIPO_LABELS:
            tipo = TIPO_LABELS[tipo_raw]
        elif tipo_raw in TIPO_LABELS.values():
            tipo = tipo_raw
        elif "CARTA" in tipo_raw:
            tipo = TIPO_LABELS[DEFAULT_TIPO]
        else:
            raise ValueError(f"Tipo de documento desconhecido: '{tipo_raw}'")

        raw_path = clean_text(row.get(HeaderForms.FULL_PATH))
        files = [p.strip() for p in raw_path.split(";") if p.strip()]
        if not files:
            raise ValueError("Linha sem arquivo (coluna FILE_PATH vazia)")
        for p in files:
            if not os.path.isfile(p):
                raise ValueError(f"Arquivo não encontrado: {p}")

        return FormsSubmission(
            uc=uc,
            toi=toi,
            local_label=local,
            tipo_label=tipo,
            date=date,
            files=files,
        )

    # ------------------------------------------------------------------ execução
    def start(
        self,
        jobs: dict[int, FormsSubmission],
        config: FormsConfig,
        cb: FormsCallbacks,
    ) -> None:

        if self.is_running():
            raise RuntimeError("Já existe um lançamento em andamento")

        self._stop.clear()

        self._thread = threading.Thread(
            target=self._worker,
            args=(jobs, config, cb),
            daemon=True,
            name="forms-worker",
        )
        self._thread.start()

    def _worker(
        self, jobs: dict[int, FormsSubmission], config: FormsConfig, cb: FormsCallbacks
    ) -> None:
        # Logs de cada passo vão só para o console: mandar para a UI causava
        # dezenas de rebuilds por linha (a tela piscando).
        service = PlaywrightFormsService(config, log=print)
        error: Exception | None = None
        total = len(jobs)

        try:
            cb.on_phase("Abrindo o navegador...")
            service.start()
            service.open_form()
            cb.on_phase(
                "Faça login no navegador, se solicitado. Aguardando o formulário..."
            )

            if not service.wait_until_ready(config.login_timeout_s, self._stop.is_set):
                if not self._stop.is_set():
                    raise TimeoutError(
                        "O formulário não carregou a tempo (login não concluído?)"
                    )
                return

            for n, (idx, sub) in enumerate(jobs.items()):
                if self._stop.is_set():
                    break

                cb.on_status(idx, StatusForms.RUNNING, "")
                cb.on_phase(f"Lançando {n + 1}/{total} | UC {sub.uc} | TOI {sub.toi}")

                try:
                    service.submit(sub)
                except Exception as e:  # uma linha ruim não derruba o lote
                    cb.on_status(idx, StatusForms.FAILED, str(e))
                    if config.screenshot_dir:
                        service.screenshot(
                            os.path.join(
                                config.screenshot_dir, f"{idx + 1}-{sub.uc}.png"
                            )
                        )
                else:
                    cb.on_status(idx, StatusForms.SUCCESS, "")
                cb.on_progress(n + 1, total)
                self._stop.wait(config.pause_between_rows_s)

        except Exception as e:
            error = e
        finally:
            service.stop()
            cb.on_done(error, self._stop.is_set())

    # ------------------------------------------------------------------
    # gerar tabela (SOMENTE cache, sem OCR)
    # ------------------------------------------------------------------
    def is_generating(self) -> bool:
        t = getattr(self, "_gen_thread", None)
        return t is not None and t.is_alive()

    @staticmethod
    def list_documents(folder: Directory, max_files: int = 200_000) -> ArrayList[File]:
        """PDFs e imagens da pasta, lendo as subpastas (extensão sem diferenciar maiúsculas)."""
        content = ContentFiles(folder, max_files=max_files)
        everything = content.get_files(EnumDocuments.ALL, sort=True, recursive=True)

        valid = ArrayList[File]()
        for f in everything:
            ext = (f.extension() or "").lower()
            if ext == ".pdf" or ext in (".png", ".jpg", ".jpeg"):
                valid.add(f)
        return valid

    def generate_table(
        self,
        files: ArrayList[File],
        on_progress: Callable[[int, int], None] = _noop,
    ) -> ResultGenerateTable:
        """Calcula o hash, consulta ControllerTOI.find_on_cache() e NÃO aplica OCR."""
        res = ResultGenerateTable()
        valid = ArrayList[File]()

        for f in files:
            if f.is_image() or f.is_pdf():
                valid.add(f)
            else:
                res.invalid += 1

        mp = HashMapDict()
        total = valid.size()
        for n, f in enumerate(valid):
            mp.set_value(load_file_hash(f), f)
            on_progress(n + 1, total)

        res.total = mp.size_header()
        if mp.is_empty():
            return res

        tb: TableData[HeaderFilesTOI] = self.relatorio_toi.find_on_cache(mp)
        found_hashes: set[str] = set()

        if not tb.is_empty():
            df = tb.to_dataframe().astype(str)
            for h in (HeaderFilesTOI.UC, HeaderFilesTOI.TOI, HeaderFilesTOI.DATE):
                df = df[df[h] != TableData.NULL_STRING]

            if not df.empty:
                found_hashes = set(df[HeaderFilesTOI.HASH_FILE].tolist())
                res.table = self.builder_carta.from_data(df)

        res.found = len(found_hashes)
        res.not_found = [
            mp.get_value(h).basename() for h in mp.header() if h not in found_hashes
        ]
        return res

    def save_generated_table(self, tb: TableData[HeaderFilesTOI]) -> File:
        """Grava em ConfigTOI.dir_relatorios (padrão do projeto)."""
        cfg = BuilderConfigTOI().builder()
        out = cfg.dir_relatorios.join_file(
            f"tabela-toi-{datetime.now():%Y%m%d-%H%M%S}.xlsx"
        )
        tmp = f"{out.absolute()}-tmp.xlsx"
        tb.to_dataframe().to_excel(tmp, index=False)
        os.replace(tmp, out.absolute())
        return out

    def start_generate(
        self,
        files: ArrayList[File],
        on_progress: Callable[[int, int], None],
        on_done: Callable[[ResultGenerateTable | None, Exception | None], None],
    ) -> None:
        if self.is_generating():
            raise RuntimeError("Já existe uma geração de tabela em andamento")

        def work() -> None:
            res: ResultGenerateTable | None = None
            err: Exception | None = None
            try:
                res = self.generate_table(files, on_progress)
                if res.table is not None:
                    res.file = self.save_generated_table(res.table)
            except Exception as e:
                err = e
            finally:
                on_done(res, err)

        self._gen_thread = threading.Thread(target=work, daemon=True, name="gen-table")
        self._gen_thread.start()
