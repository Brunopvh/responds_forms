# navigator.py
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Callable
from pyflutter_ui.ui.core import (
    BuildContext,
    Element,
    FlutterWidget,
    BaseMaterialApp,
    Navigator,
    PageApp,
)


# ============================================================
# NAVIGATOR
# ============================================================
class Route(ABC):

    def __init__(self) -> None:
        super().__init__()

    @abstractmethod
    def build(self, context: BuildContext) -> PageApp:
        pass


class PageRoute(Route):

    def __init__(self, builder: Callable[[BuildContext], PageApp]) -> None:
        super().__init__()
        self.builder = builder

    def build(self, context: BuildContext) -> PageApp:
        return self.builder(context)


class NavigatorApp(Navigator):

    def __init__(self, app: BaseMaterialApp) -> None:
        super().__init__(app)

    def push(self, page: PageApp) -> None:

        if self.stack:
            current = self.stack[-1]

            if current.widget_tk is not None:
                current.widget_tk.pack_forget()

        self.app.get_root().title(page.name)

        element = page.create_element()
        context = BuildContext(self.app, parent_widget=self.app.get_root())
        element.mount(context)
        self.stack.append(element)
        self.current_element = element

    def pop(self) -> None:

        if len(self.stack) <= 1:
            return

        current = self.stack.pop()
        current.unmount()

        previous = self.stack[-1]

        if previous.widget_tk is not None:
            previous.widget_tk.pack(fill="both", expand=True)
            self.app.get_root().title(previous.get_widget_flutter().name)

        self.current_element = previous

    def replace(self, page: PageApp) -> None:

        if self.stack:
            current = self.stack.pop()

            current.unmount()

        element = page.create_element()

        context = BuildContext(app=self.app, parent_widget=self.app.get_root())

        element.mount(context)

        self.stack.append(element)

        self.current_element = element
        self.app.get_root().title(self.current_element.get_widget_flutter().name)

    def render(self) -> None:
        pass
