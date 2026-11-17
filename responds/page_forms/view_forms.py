from __future__ import annotations
from tkinter import messagebox

from pyflutter_ui import (
    BuildContext,
    FlutterWidget,
    StatelessWidget,
    Consumer,
    Column,
    Row,
    ElevatedButton,
    Expanded,
    Divider,
    Text,
    Provider,
    FilePickerController,
    FilePickerType,
    FilePickerResult,
    PlatformFile,
    LinearProgress,
    Checkbox,
    TableOrProgress,
    PageApp,
)

import pandas as pd
from responds.page_forms.controller_forms import ControllerForms
from responds.navigation import MainScaffold, NavIndex

from table_stream import File, Directory
from pyflutter_ui.ui import GlobalKey


class PageRespondsForms(PageApp):

    def __init__(
        self, key: GlobalKey | None = None, *, name: str = "Responds Forms Automation"
    ) -> None:
        super().__init__(key, name=name)

    def build(self, context: BuildContext) -> FlutterWidget:
        return _PageRespondsFormsState(self.key)


class _PageRespondsFormsState(StatelessWidget):

    def __init__(self, key=None):
        super().__init__(key)

        self.picker_cartas_dir = FilePickerController(
            dialog_title="Escolha a pasta com as cartas (PDF/imagem)",
        )

        self.file_picker = FilePickerController(
            type=FilePickerType.spreadsheet,
            dialog_title="Escolha a planilha TOI",
        )

        ctrl = self.get_controller()
        ctrl.fn_show_error = self.show_error
        ctrl.fn_show_info = self.show_info

    def get_controller(self) -> ControllerForms:
        return Provider.read(ControllerForms)

    def show_error(self, e: str) -> None:
        messagebox.showerror("Erro", e)

    def show_info(self, i: str) -> None:
        messagebox.showinfo("Aviso", i)

    # ------------------------------------------------------------------ ações
    def action_generate_table(self, controller: ControllerForms) -> None:
        if controller.running or controller.generating or controller.scanning:
            self.show_info("Existe outra operação em andamento.")
            return

        conf = controller.get_config()
        if conf.value.initial_dir.exists():
            self.picker_cartas_dir.initial_directory = conf.value.initial_dir.absolute()

        path = self.picker_cartas_dir.pick_directory()
        if not path:
            return

        folder = Directory(path)
        conf.set_initial_dir(folder)
        controller.generate_table_from_folder(folder)

    def action_pick_table(self, controller: ControllerForms) -> None:
        if controller.running:
            self.show_info("Existe um lançamento em andamento.")
            return

        # conf = controller.get_config()
        conf_initial_dir = controller.get_initial_dir()

        self.file_picker.initial_directory = conf_initial_dir.absolute()

        result: FilePickerResult | None = self.file_picker.pick_files()
        if result is None or not result.files:
            return

        if self.file_picker.initial_directory is not None:
            # conf.set_initial_dir(Directory(self.file_picker.initial_directory))
            controller.set_initial_dir(Directory(self.file_picker.initial_directory))

        pf: PlatformFile = result.files[0]
        controller.set_selected_table_toi(File(pf.path))

    # ------------------------------------------------------------------ widgets
    def build_body(
        self, context: BuildContext, controller: ControllerForms
    ) -> FlutterWidget:
        total = controller.map_rows.size_header()
        info = f"Cartas na tabela: {total}" if total > 0 else "Nenhuma tabela importada"

        df = (
            controller.map_rows.to_view_data()
            if total > 0
            else pd.DataFrame({"-": ["Sem dados"]})
        )

        return Column(
            [
                Row(
                    [
                        ElevatedButton(
                            "Gerar tabela (pasta)",
                            lambda: self.action_generate_table(controller),
                        ),
                        ElevatedButton(
                            "Importar tabela TOI",
                            lambda: self.action_pick_table(controller),
                        ),
                        Text(info),
                    ]
                ),
                Row(
                    [
                        ElevatedButton("Iniciar lançamento", controller.start_forms),
                        ElevatedButton("Parar", controller.stop_forms),
                        ElevatedButton(
                            "Salvar resultado", lambda: controller.save_result()
                        ),
                        Checkbox(
                            value=controller.send_receipt,
                            text="E-mail de confirmação",
                            on_changed=controller.set_send_receipt,
                        ),
                    ]
                ),
                Text(controller.status_text),
                LinearProgress(value=controller.progress_fraction),
                Divider(),
                Expanded(TableOrProgress(running=False, df=df)),
                Divider(),
            ]
        )

    def build(self, context: BuildContext) -> FlutterWidget:
        self.context = context
        return MainScaffold(Consumer(ControllerForms, self.build_body), NavIndex.FORMS)
