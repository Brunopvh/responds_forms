# system_theme.py
"""
Detecção do tema do SO SEM subprocess/shell (somente stdlib e leitura de arquivos).

Substitui o corpo de `_detect_system_dark_mode()` do theme.py, que usava
`subprocess` (macOS) e criava uma segunda janela tk.Tk() (Linux).
"""
from __future__ import annotations

import configparser
import os
import plistlib
import sys
from abc import ABC, abstractmethod
from pathlib import Path


class SystemThemeDetector(ABC):
    """Strategy: uma implementação por sistema operacional."""

    @abstractmethod
    def is_dark(self) -> bool:
        """True se o SO estiver em modo escuro. Na dúvida, False (claro)."""

    @staticmethod
    def create() -> SystemThemeDetector:
        if sys.platform == "win32":
            return WindowsThemeDetector()
        if sys.platform == "darwin":
            return MacThemeDetector()
        return LinuxThemeDetector()


class WindowsThemeDetector(SystemThemeDetector):
    _KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"

    def is_dark(self) -> bool:
        try:
            import winreg  # stdlib, só existe no Windows

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._KEY) as key:
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return int(value) == 0
        except (ImportError, OSError, ValueError):
            return False


class MacThemeDetector(SystemThemeDetector):
    def is_dark(self) -> bool:
        path = Path.home() / "Library" / "Preferences" / ".GlobalPreferences.plist"
        try:
            with path.open("rb") as fh:
                data: dict[str, object] = plistlib.load(fh)
        except (OSError, ValueError):
            return False
        return str(data.get("AppleInterfaceStyle", "")).lower() == "dark"


class LinuxThemeDetector(SystemThemeDetector):
    """
    Lê GTK_THEME e ~/.config/gtk-3.0/settings.ini.
    Limitação: a chave moderna do GNOME (color-scheme) só é legível via
    gsettings/dbus, que não usamos de propósito. Nesse caso o app assume
    claro; basta escolher Escuro/Claro manualmente nas Configurações.
    """

    def is_dark(self) -> bool:
        if "dark" in os.environ.get("GTK_THEME", "").lower():
            return True

        base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read(base / "gtk-3.0" / "settings.ini", encoding="utf-8")
        except (OSError, configparser.Error, UnicodeDecodeError):
            return False

        if parser.getboolean("Settings", "gtk-application-prefer-dark-theme", fallback=False):
            return True
        return "dark" in parser.get("Settings", "gtk-theme-name", fallback="").lower()
