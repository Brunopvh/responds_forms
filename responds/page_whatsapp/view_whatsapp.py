from __future__ import annotations
from tkinter import messagebox

from table_stream import Directory, File

from pyflutter_ui import (
    BuildContext,
    Column,
    Consumer,
    Divider,
    ElevatedButton,
    Expanded,
    FilePickerController,
    FilePickerResult,
    FilePickerType,
    FlutterWidget,
    LinearProgress,
    Provider,
    Row,
    Scaffold,
    StatelessWidget,
    Text,
    TkMaterialApp,
    TableOrProgress,
    PageApp,
)

from responds.navigation import MainScaffold, NavIndex
from responds.page_whatsapp import ControllerWhatsAppPage
from responds.page_whatsapp import (
    CMD_ADD_CACHE,
    CMD_FULL_DAY,
    CMD_FULL_MONTH,
    CMD_RENAME_DAY,
    CMD_RENAME_MONTH,
    CMD_UNZIP,
)
from pyflutter_ui.ui.core import GlobalKey


def _shorten(text: str, limit: int = 80) -> str:
    return text if len(text) <= limit else "..." + text[-(limit - 3) :]


class PageWhatsApp(PageApp):
    """Importa chats do WhatsApp, organiza os arquivos dos chats e renomeia cartas TOI."""

    def __init__(
        self, key: GlobalKey | None = None, *, name: str = "WhatsApp Chats"
    ) -> None:
        super().__init__(key, name=name)

    def build(self, context: BuildContext) -> FlutterWidget:
        return _PageWhatsAppState(self.key)


class _PageWhatsAppState(StatelessWidget):

    # WINDOW_SIZE: tuple[int, int] = (1100, 700)

    def __init__(self, key=None) -> None:
        super().__init__(key)
        # self._prev_size: tuple[int, int] | None = None

        self.picker_zip = FilePickerController(
            type=FilePickerType.custom,
            allow_multiple=True,
            allowed_extensions=["zip"],
            dialog_title="Escolha os chats do WhatsApp (.zip)",
        )
        self.picker_txt = FilePickerController(
            type=FilePickerType.custom,
            allow_multiple=True,
            allowed_extensions=["txt"],
            dialog_title="Escolha o chat do WhatsApp (.txt)",
        )
        self.picker_cartas_dir = FilePickerController(
            dialog_title="Escolha a pasta com as cartas TOI (PDF/imagem)",
        )

        ctrl = self.controller
        ctrl.fn_show_error = self.show_error
        ctrl.fn_show_info = self.show_info
        ctrl.ensure_summary()  # lê o cache em worker thread, sem travar a UI
        ctrl.fn_confirm = self.confirm

    @property
    def controller(self) -> ControllerWhatsAppPage:
        return Provider.read(ControllerWhatsAppPage)

    def show_error(self, msg: str) -> None:
        messagebox.showerror("Erro", msg)

    def show_info(self, msg: str) -> None:
        messagebox.showinfo("Aviso", msg)

    def confirm(self, msg: str) -> bool:
        return messagebox.askyesno("Remover arquivos duplicados", msg)

    def action_remove_duplicates(self, ctrl: ControllerWhatsAppPage) -> None:
        if ctrl.busy:
            self.show_info("Existe outra operação em andamento.")
            return

        conf = ctrl.get_config()
        if conf.value.initial_dir.exists():
            self.picker_cartas_dir.initial_directory = conf.value.initial_dir.absolute()

        path = self.picker_cartas_dir.pick_directory()
        if not path:
            return

        folder = Directory(path)
        conf.set_initial_dir(folder)
        ctrl.remove_duplicates_folder(folder)

    # ------------------------------------------------------------------ ações

    def _pick(
        self, ctrl: ControllerWhatsAppPage, picker: FilePickerController
    ) -> list[File] | None:
        if ctrl.busy:
            self.show_info("Existe outra operação em andamento.")
            return None

        conf = ctrl.get_config()
        if conf.value.initial_dir.exists():
            picker.initial_directory = conf.value.initial_dir.absolute()

        result: FilePickerResult | None = picker.pick_files()
        if result is None or not result.files:
            return None

        if picker.initial_directory is not None:
            conf.set_initial_dir(Directory(picker.initial_directory))

        return [File(p) for p in result.paths]

    def action_import_zip(self, ctrl: ControllerWhatsAppPage) -> None:
        files = self._pick(ctrl, self.picker_zip)
        if files:
            ctrl.import_files(files)

    def action_import_txt(self, ctrl: ControllerWhatsAppPage) -> None:
        files = self._pick(ctrl, self.picker_txt)
        if files:
            ctrl.import_files(files)

    def action_import_cartas(self, ctrl: ControllerWhatsAppPage) -> None:
        if ctrl.busy:
            self.show_info("Existe outra operação em andamento.")
            return

        conf = ctrl.get_config()
        if conf.value.initial_dir.exists():
            self.picker_cartas_dir.initial_directory = conf.value.initial_dir.absolute()

        path = self.picker_cartas_dir.pick_directory()
        if not path:
            return

        folder = Directory(path)
        conf.set_initial_dir(folder)

        ok = messagebox.askyesno(
            "Importar e renomear cartas TOI",
            f"Todos os PDFs e imagens de:\n{folder.absolute()}\n"
            "(incluindo subpastas) serão identificados pelo nome, cache TOI, "
            "texto do cache OCR e data do chat, e MOVIDOS para a pasta de "
            "cartas TOI.\n\nContinuar?",
        )
        if ok:
            ctrl.import_cartas_folder(folder)

    def action_chat_command(self, ctrl: ControllerWhatsAppPage, kind: str) -> None:
        if ctrl.busy:
            self.show_info("Existe outra operação em andamento.")
            return

        moves = kind in (CMD_RENAME_MONTH, CMD_RENAME_DAY, CMD_FULL_MONTH, CMD_FULL_DAY)
        if moves:
            ok = messagebox.askyesno(
                "Organizar arquivos dos chats",
                "Os arquivos das conversas descompactadas serão MOVIDOS para a "
                "pasta de conversas organizadas.\n\nContinuar?",
            )
            if not ok:
                return
        ctrl.run_chat_command(kind)

    # ------------------------------------------------------------------ widgets
    def build_body(
        self, context: BuildContext, ctrl: ControllerWhatsAppPage
    ) -> FlutterWidget:
        return Column(
            [
                Row(
                    [
                        ElevatedButton(
                            "Importar chat (.zip)",
                            lambda: self.action_import_zip(ctrl),
                        ),
                        ElevatedButton(
                            "Importar .txt", lambda: self.action_import_txt(ctrl)
                        ),
                        ElevatedButton(
                            "Atualizar", lambda: ctrl.refresh_summary(reload=True)
                        ),
                        # ElevatedButton("Abrir pasta", ctrl.open_work_dir),
                    ]
                ),
                Row(
                    [
                        Text("Chats:"),
                        ElevatedButton(
                            "Descompactar zips",
                            lambda: self.action_chat_command(ctrl, CMD_UNZIP),
                        ),
                        ElevatedButton(
                            "Atualizar cache (descompactados)",
                            lambda: self.action_chat_command(ctrl, CMD_ADD_CACHE),
                        ),
                        ElevatedButton(
                            "Renomear (ano-mês)",
                            lambda: self.action_chat_command(ctrl, CMD_RENAME_MONTH),
                        ),
                        ElevatedButton(
                            "Renomear (ano-mês-dia)",
                            lambda: self.action_chat_command(ctrl, CMD_RENAME_DAY),
                        ),
                    ]
                ),
                Row(
                    [
                        Text("Fluxo completo:"),
                        ElevatedButton(
                            "Zips -> cache -> renomear (mês)",
                            lambda: self.action_chat_command(ctrl, CMD_FULL_MONTH),
                        ),
                        ElevatedButton(
                            "Zips -> cache -> renomear (dia)",
                            lambda: self.action_chat_command(ctrl, CMD_FULL_DAY),
                        ),
                        # ElevatedButton("Abrir chats organizados", ctrl.open_chats_dir),
                    ]
                ),
                Row(
                    [
                        Text("Cartas TOI:"),
                        ElevatedButton(
                            "Importar e renomear cartas",
                            lambda: self.action_import_cartas(ctrl),
                        ),
                        ElevatedButton(
                            "Remover Arquivos Duplicados",
                            lambda: self.action_remove_duplicates(ctrl),
                        ),

                    ]
                ),
                Text(f"Cache: {_shorten(ctrl.cache_label)}"),
                Text(ctrl.info_text),
                Text(ctrl.status_text),
                LinearProgress(value=ctrl.progress_fraction),
                Divider(),
                Text("Conversas no cache"),
                Expanded(TableOrProgress(running=ctrl.busy, df=ctrl.view_data())),
                Divider(),
                Text(ctrl.log_title),
                Expanded(TableOrProgress(running=False, df=ctrl.log_data())),
            ]
        )

    def build(self, context: BuildContext) -> FlutterWidget:
        self.context = context
        return MainScaffold(
            Consumer(ControllerWhatsAppPage, self.build_body), NavIndex.WHATSAPP
        )
