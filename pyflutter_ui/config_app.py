from __future__ import annotations
from typing import Any
from dataclasses import dataclass
from table_stream import (
    File,
    Directory,
    UserFileSystem,
    JsonConvert,
    HashMapDict,
    HashMap,
    ArrayList,
)
from pyflutter_ui.theme import ThemeMode
from pyflutter_ui.ui.core import ValueNotifier


@dataclass
class MapConfig:
    initial_dir: Directory
    last_dir: Directory
    work_dir: Directory
    documents_dir: Directory
    theme_mode: ThemeMode
    initial_dir_map: HashMap[str, Directory]
    cartas_dir: Directory | None = None  # None = padrão do módulo cartas
    # ^^ apagar isso futuramente, pois cartas_dir é algo especifico de responds_forms
    # enquanto pyflutter_ui deve ser bem generico para ser usado em qualquer app.


class FactoryMapConfig(object):

    def __init__(self) -> None:
        self._conf: MapConfig = self._create()

    def _create(self) -> MapConfig:

        self._conf: MapConfig = MapConfig(
            initial_dir=UserFileSystem().get_user_downloads(),
            last_dir=UserFileSystem().get_user_downloads(),
            work_dir=UserFileSystem().get_user_downloads().concat("RFA", True),
            documents_dir=UserFileSystem().get_user_downloads().concat("RFA", True),
            theme_mode=ThemeMode.DARK,
            initial_dir_map=HashMapDict(),
        )
        return self._conf

    def set_name_initial_dir(self, name: str, d: Directory):
        self._conf.initial_dir_map.set_value(name, d)

    def create_default(self) -> MapConfig:
        return self._conf

    def create_from_dict(self, h: HashMapDict[str, Any]) -> MapConfig:
        if h.header().contains("work_dir"):
            self._conf.work_dir = Directory(h["work_dir"])

        if h.header().contains("documents_dir"):
            self._conf.documents_dir = Directory(h["documents_dir"])

        if h.header().contains("cartas_dir"):
            self._conf.cartas_dir = Directory(h["cartas_dir"])

        if h.header().contains("initial_dir"):
            self._conf.initial_dir = Directory(h["initial_dir"])

        if h.header().contains("last_dir"):
            self._conf.last_dir = Directory(h["last_dir"])

        if h.header().contains("theme_mode"):
            if h["theme_mode"] == "dark":
                self._conf.theme_mode = ThemeMode.DARK
            elif h["theme_mode"] == "light":
                self._conf.theme_mode = ThemeMode.LIGHT
            else:
                self._conf.theme_mode = ThemeMode.SYSTEM

        if h.header().contains("initial_dir_map"):
            _map_initial_dict: dict[str, str] = h.get_value("initial_dir_map")
            final_map = HashMapDict[str, Directory]()
            keys_initial_dir = ArrayList.from_list(list(_map_initial_dict.keys()))

            keys_initial_dir.for_each(
                lambda k: final_map.set_value(k, Directory(_map_initial_dict[k]))
            )
            self._conf.initial_dir_map = final_map

        return self._conf

    def create_from_file(self, file_json: File) -> MapConfig:
        converter = JsonConvert.from_file(file_json)
        map_data = converter.data.to_dict()
        return self.create_from_dict(HashMapDict(map_data))


class AppConfigNotifier(ValueNotifier[MapConfig]):

    file_config: File = UserFileSystem().cache_dir().join_file("RFA-config.json")

    def __init__(self, value: MapConfig = FactoryMapConfig().create_default()) -> None:
        super().__init__(value)
        # self._file_config: File = self.value.work_dir.concat("config", True).join_file("app_config.json")

    def set_work_dir(self, d: Directory):
        self._value.work_dir = d
        self.notify_listeners()

    def set_initial_dir(self, d: Directory):
        self._value.initial_dir = d
        self.notify_listeners()

    def set_documents_dir(self, d: Directory):
        self._value.documents_dir = d
        self.notify_listeners()

    def set_initial_dir_named(self, name: str, d: Directory):
        cfg = self._value
        cfg.initial_dir_map[name] = d
        self._value = cfg
        self.notify_listeners()

    def get_file_config(self) -> File:
        return AppConfigNotifier.file_config

    def set_theme_mode(self, mode: ThemeMode) -> None:
        self._value.theme_mode = mode
        self.notify_listeners()

    def set_cartas_dir(self, d: Directory | None) -> None:
        self._value.cartas_dir = d
        self.notify_listeners()

    def get_dict_config(self) -> dict[str, object]:
        return self.config_to_map()

    def config_to_map(self) -> dict[str, object]:
        final = dict[str, object]()
        cfg = self.value
        final = dict[str, Any]()
        cfg = self.value

        # Converter initial_dir_map para dict/json
        json_initial_dir_map = dict[str, str]()
        header_initial_dir = cfg.initial_dir_map.header()
        header_initial_dir.for_each(
            lambda h_name: json_initial_dir_map.setdefault(
                h_name, cfg.initial_dir_map.get_value(h_name).absolute()
            )
        )

        final["initial_dir_map"] = json_initial_dir_map
        final["initial_dir"] = cfg.initial_dir.absolute()
        final["last_dir"] = cfg.last_dir.absolute()
        final["work_dir"] = cfg.work_dir.absolute()
        final["documents_dir"] = cfg.documents_dir.absolute()
        final["theme_mode"] = cfg.theme_mode.value

        if cfg.cartas_dir is not None:
            final["cartas_dir"] = cfg.cartas_dir.absolute()

        return final

    def save_config(self):
        converter = JsonConvert.from_dict(self.get_dict_config())
        converter.data.to_file(self.get_file_config())
        print(f"Configurações salvas em ... {self.get_file_config().absolute()}")

    def notify_listeners(self) -> None:
        """
        Salvar a nova configuração em arquivo local e notificar os observadores.
        """
        self.save_config()
        return super().notify_listeners()

    @classmethod
    def create(cls) -> AppConfigNotifier:
        src = Directory(cls.file_config.dirname())
        src.mkdir()

        config: MapConfig
        if cls.file_config.exists():
            print(f"Lendo configração em ... {cls.file_config.absolute()}")
            config = FactoryMapConfig().create_from_file(cls.file_config)
        else:
            config = FactoryMapConfig().create_default()
        return cls(config)
