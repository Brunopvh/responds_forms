# navigation.py
"""
Navegação principal do app: BottomNavigationBar sempre visível + Navigator.replace().

Cada página envolve o seu corpo em MainScaffold(body, NavIndex.X); assim a barra
inferior aparece em todas e a home_page deixa de existir.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Callable

from pyflutter_ui import (
    BottomNavigationBar,
    BuildContext,
    FlutterWidget,
    PageApp,
    Scaffold,
    StatelessWidget,
)
from pyflutter_ui.ui.core import GlobalKey


class NavIndex(IntEnum):
    FORMS = 0
    WHATSAPP = 1
    SETTINGS = 2


@dataclass(frozen=True)
class Destination:
    index: NavIndex
    label: str
    page_factory: Callable[[], PageApp]


class AppDestinations:
    """Registro das abas. Imports locais evitam ciclo (as páginas importam MainScaffold)."""

    @staticmethod
    def all() -> tuple[Destination, ...]:
        from responds.page_forms.view_forms import PageRespondsForms
        from responds.page_settings.view_settings import PageSettings
        from responds.page_whatsapp.view_whatsapp import PageWhatsApp

        return (
            Destination(NavIndex.FORMS, "Forms Cartas", PageRespondsForms),
            Destination(NavIndex.WHATSAPP, "WhatsApp", PageWhatsApp),
            Destination(NavIndex.SETTINGS, "Configurações", PageSettings),
        )


class MainScaffold(StatelessWidget):
    """Scaffold com a barra de navegação inferior padrão do app."""

    def __init__(
        self,
        body: FlutterWidget,
        current: NavIndex,
        *,
        key: GlobalKey | None = None,
    ) -> None:
        super().__init__(key)
        self.body: FlutterWidget = body
        self.current: NavIndex = current

    def build(self, context: BuildContext) -> FlutterWidget:
        destinations = AppDestinations.all()
        return Scaffold(
            self.body,
            bottom_navigation_bar=BottomNavigationBar(
                [d.label for d in destinations],
                lambda i: self._navigate(context, destinations[i]),
                current_index=int(self.current),
            ),
        )

    def _navigate(self, context: BuildContext, destination: Destination) -> None:
        if destination.index == self.current:
            return
        # after_idle: a troca desmonta a página que contém o botão clicado;
        # fazer isso fora do callback do próprio botão evita TclError.
        root = context.app.get_root()
        root.after_idle(lambda: context.navigator.replace(destination.page_factory()))
