from __future__ import annotations

from dataclasses import replace
from typing import Callable

from table_stream import Directory, File, HashMapDict
from pyflutter_ui import AppConfigNotifier, ChangeNotifier, Provider, ThemeMode, ThemeProvider
from pyflutter_ui.config_app import MapConfig

from responds.page_settings.gateway_cartas import CartasDirGateway, CartasModuleGateway
from responds.page_settings.model_settings import (
    ConfigValidationError,
    ImportedSettings,
    ImportPlan,
    ModelSettings,
)


def _dir_or(path: object, fallback: Directory) -> Directory:
    return Directory(str(path)) if path is not None else fallback


class ControllerSettings(ChangeNotifier):

    def __init__(
        self, model: ModelSettings, gateway: CartasDirGateway | None = None
    ) -> None:
        super().__init__()
        self.model: ModelSettings = model
        self._gateway: CartasDirGateway = gateway or CartasModuleGateway()
        self._default_cartas_dir: Directory | None = None

        self.status_text: str = "Configurações carregadas."
        self.fn_show_error: Callable[[str], None] | None = None
        self.fn_show_info: Callable[[str], None] | None = None

    # ------------------------------------------------------------------ infra
    def get_config(self) -> AppConfigNotifier:
        return Provider.read(AppConfigNotifier)

    def get_theme(self) -> ThemeProvider:
        return Provider.read(ThemeProvider)

    def show_error(self, msg: str) -> None:
        if self.fn_show_error is not None:
            self.fn_show_error(msg)
        else:
            print(f"[ERRO] {msg}")

    def show_info(self, msg: str) -> None:
        if self.fn_show_info is not None:
            self.fn_show_info(msg)

    # ------------------------------------------------------------------ estado
    def _default_dir(self) -> Directory:
        if self._default_cartas_dir is None:
            self._default_cartas_dir = self._gateway.current()
        return self._default_cartas_dir

    @property
    def effective_cartas_dir(self) -> Directory:
        saved = self.get_config().value.cartas_dir
        return saved if saved is not None else self._default_dir()

    @property
    def is_default_cartas_dir(self) -> bool:
        return self.get_config().value.cartas_dir is None

    @property
    def theme_mode(self) -> ThemeMode:
        return self.get_theme().mode

    # ------------------------------------------------------------------ startup
    def apply_saved_config(self) -> None:
        """Chamar no main, depois de registrar os notifiers e ANTES de run_app()."""
        self._default_dir()  # captura o padrão ANTES de qualquer override
        saved = self.get_config().value.cartas_dir
        if saved is None:
            return
        if not saved.exists():
            self.show_error(f"Diretório das cartas salvo não existe mais:\n{saved.absolute()}")
            return
        try:
            self._gateway.apply(saved)
        except Exception as e:
            self.show_error(f"Falha ao aplicar o diretório das cartas:\n{e}")

    # ------------------------------------------------------------------ diretório das cartas
    def change_cartas_dir(self, directory: Directory) -> None:
        if not directory.exists():
            self.show_error(f"A pasta não existe:\n{directory.absolute()}")
            return
        try:
            self._gateway.apply(directory)
        except Exception as e:
            self.show_error(f"Falha ao aplicar o diretório das cartas:\n{e}")
            return

        self.get_config().set_cartas_dir(directory)
        self.status_text = f"Diretório das cartas alterado: {directory.absolute()}"
        self.notify_listeners()
        self.show_info(
            "Diretório base das cartas alterado.\n"
            "Valerá nas próximas operações; se alguma rotina já estiver carregada, "
            "reinicie o aplicativo."
        )

    def reset_cartas_dir(self) -> None:
        default = self._default_dir()
        try:
            self._gateway.apply(default)
        except Exception as e:
            self.show_error(f"Falha ao restaurar o diretório padrão:\n{e}")
            return
        self.get_config().set_cartas_dir(None)
        self.status_text = "Diretório das cartas restaurado para o padrão."
        self.notify_listeners()

    # ------------------------------------------------------------------ tema
    def set_theme_mode(self, mode: ThemeMode) -> None:
        # Sem notify_listeners: os estilos ttk mudam ao vivo e o combobox já mostra
        # o valor escolhido; evitar o rebuild da página dentro do evento do combobox.
        self.get_theme().set_mode(mode)
        self.get_config().set_theme_mode(mode)
        self.status_text = f"Tema alterado: {mode.value}"

    # ------------------------------------------------------------------ JSON
    def export_config(self, file: File) -> None:
        try:
            self.model.export_config(dict(self.get_config().get_dict_config()), file)
        except OSError as e:
            self.show_error(f"Falha ao exportar:\n{e}")
            return
        self.status_text = f"Configurações exportadas: {file.absolute()}"
        self.notify_listeners()
        self.show_info(f"Configurações exportadas para:\n{file.absolute()}")

    def import_config(self, file: File) -> None:
        try:
            plan = self.model.read_import(file)
        except ConfigValidationError as e:
            body = "\n".join(f"• {p}" for p in e.problems)
            self.show_error(f"Arquivo de configuração inválido:\n{body}")
            return

        try:
            self._apply_plan(plan)
        except Exception as e:
            self.show_error(f"Falha ao aplicar as configurações:\n{e}")
            return

        self.status_text = f"Configurações importadas: {file.absolute()}"
        self.notify_listeners()

        msg = "Configurações importadas com sucesso."
        if plan.skipped:
            msg += "\n\nIgnorados:\n" + "\n".join(f"• {s}" for s in plan.skipped)
        self.show_info(msg)

    def _apply_plan(self, plan: ImportPlan) -> None:
        s: ImportedSettings = plan.settings
        config = self.get_config()
        cfg: MapConfig = config.value

        merged = HashMapDict[str, Directory]()
        for name in cfg.initial_dir_map.header():
            merged.set_value(name, cfg.initial_dir_map.get_value(name))
        for name, path in s.initial_dir_map.items():
            merged.set_value(name, Directory(str(path)))

        new_cartas = _dir_or(s.cartas_dir, cfg.cartas_dir) if s.cartas_dir else cfg.cartas_dir
        new_cfg = replace(
            cfg,
            initial_dir=_dir_or(s.initial_dir, cfg.initial_dir),
            last_dir=_dir_or(s.last_dir, cfg.last_dir),
            work_dir=_dir_or(s.work_dir, cfg.work_dir),
            documents_dir=_dir_or(s.documents_dir, cfg.documents_dir),
            cartas_dir=new_cartas,
            theme_mode=s.theme_mode if s.theme_mode is not None else cfg.theme_mode,
            initial_dir_map=merged,
        )

        # Efeitos colaterais que podem falhar primeiro; o config só é gravado se deram certo.
        if s.cartas_dir is not None and new_cartas is not None:
            self._gateway.apply(new_cartas)
        if s.theme_mode is not None:
            self.get_theme().set_mode(s.theme_mode)

        config.value = new_cfg  # notifica e grava em disco
