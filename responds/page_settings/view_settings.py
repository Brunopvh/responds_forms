from __future__ import annotations

from tkinter import messagebox
from typing import Final

from table_stream import Directory, File

from pyflutter_ui import (
    BuildContext,
    Column,
    Consumer,
    Divider,
    DropdownButton,
    ElevatedButton,
    FilePickerController,
    FilePickerResult,
    FilePickerType,
    FlutterWidget,
    PageApp,
    PlatformFile,
    Row,
    StatelessWidget,
    Text,
    ThemeMode,
    Provider,
)
from pyflutter_ui.ui.core import GlobalKey

from responds.navigation import MainScaffold, NavIndex
from responds.page_settings.controller_settings import ControllerSettings


def _shorten(text: str, limit: int = 90) -> str:
    return text if len(text) <= limit else "..." + text[-(limit - 3):]


class PageSettings(PageApp):
    """Configurações: diretório base das cartas, tema e importar/exportar JSON."""

    def __init__(
        self, key: GlobalKey | None = None, *, name: str = "Configurações"
    ) -> None:
        super().__init__(key, name=name)

    def build(self, context: BuildContext) -> FlutterWidget:
        return _PageSettingsState(self.key)


class _PageSettingsState(StatelessWidget):

    _LABEL_BY_MODE: Final[dict[ThemeMode, str]] = {
        ThemeMode.DARK: "Escuro",
        ThemeMode.LIGHT: "Claro",
        ThemeMode.SYSTEM: "Sistema",
    }
    _MODE_BY_LABEL: Final[dict[str, ThemeMode]] = {
        v: k for k, v in _LABEL_BY_MODE.items()
    }

    def __init__(self, key: GlobalKey | None = None) -> None:
        super().__init__(key)

        self.picker_dir = FilePickerController(
            dialog_title="Escolha o diretório base das cartas TOI",
        )
        self.picker_open = FilePickerController(
            type=FilePickerType.custom,
            allowed_extensions=["json"],
            dialog_title="Importar configurações (JSON)",
        )
        self.picker_save = FilePickerController(
            type=FilePickerType.custom,
            allowed_extensions=["json"],
            dialog_title="Exportar configurações (JSON)",
        )

        ctrl = self.controller
        ctrl.fn_show_error = self.show_error
        ctrl.fn_show_info = self.show_info

    @property
    def controller(self) -> ControllerSettings:
        return Provider.read(ControllerSettings)

    def show_error(self, msg: str) -> None:
        messagebox.showerror("Erro", msg)

    def show_info(self, msg: str) -> None:
        messagebox.showinfo("Aviso", msg)

    # ------------------------------------------------------------------ ações
    def action_change_cartas_dir(self, ctrl: ControllerSettings) -> None:
        current = ctrl.effective_cartas_dir
        if current.exists():
            self.picker_dir.initial_directory = current.absolute()

        path = self.picker_dir.pick_directory()
        if path:
            ctrl.change_cartas_dir(Directory(path))

    def action_theme_changed(self, ctrl: ControllerSettings, label: str) -> None:
        mode = self._MODE_BY_LABEL.get(label)
        if mode is not None:  # o combobox é editável: ignora texto digitado
            ctrl.set_theme_mode(mode)

    def action_export(self, ctrl: ControllerSettings) -> None:
        path = self.picker_save.save_file(suggested_name="rfa-config.json")
        if path:
            ctrl.export_config(File(path))

    def action_import(self, ctrl: ControllerSettings) -> None:
        result: FilePickerResult | None = self.picker_open.pick_files()
        pf: PlatformFile | None = result.single() if result is not None else None
        if pf is None:
            return

        ok = messagebox.askyesno(
            "Importar configurações",
            "As configurações atuais serão substituídas pelos campos presentes "
            "no arquivo.\n\nContinuar?",
        )
        if ok:
            ctrl.import_config(File(pf.path))

    # ------------------------------------------------------------------ widgets
    def build_body(self, context: BuildContext, ctrl: ControllerSettings) -> FlutterWidget:
        origem = "padrão" if ctrl.is_default_cartas_dir else "personalizado"
        return Column(
            [
                Text("Configurações"),
                Divider(),
                Text(f"Diretório base das cartas TOI ({origem})"),
                Text(_shorten(ctrl.effective_cartas_dir.absolute())),
                Row(
                    [
                        ElevatedButton(
                            "Alterar diretório...",
                            lambda: self.action_change_cartas_dir(ctrl),
                        ),
                        ElevatedButton("Restaurar padrão", ctrl.reset_cartas_dir),
                    ]
                ),
                Divider(),
                Text("Tema"),
                DropdownButton(
                    list(self._LABEL_BY_MODE.values()),
                    self._LABEL_BY_MODE[ctrl.theme_mode],
                    on_changed=lambda label: self.action_theme_changed(ctrl, label),
                ),
                Divider(),
                Text("Configurações do app (JSON)"),
                Row(
                    [
                        ElevatedButton("Exportar...", lambda: self.action_export(ctrl)),
                        ElevatedButton("Importar...", lambda: self.action_import(ctrl)),
                    ]
                ),
                Divider(),
                Text(ctrl.status_text),
            ]
        )

    def build(self, context: BuildContext) -> FlutterWidget:
        self.context = context
        return MainScaffold(
            Consumer(ControllerSettings, self.build_body), NavIndex.SETTINGS
        )
