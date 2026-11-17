# container.py
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Optional

from pyflutter_ui.ui.core import (
    FlutterWidget,
    BuildContext,
    Element,
    GlobalKey,
    StatelessWidget,
)


# ============================================================
# SIZED BOX
# ============================================================
class SizedBox(StatelessWidget):

    def __init__(
        self,
        width: int | None = None,
        height: int | None = None,
        *,
        key: GlobalKey | None = None,
    ) -> None:
        super().__init__(key)

        self.width = width
        self.height = height

    def build(self, context: BuildContext) -> FlutterWidget:
        return self

    def create_element(self) -> Element:
        return SizedBoxElement(self)


class SizedBoxElement(Element):

    def __init__(self, widget: SizedBox) -> None:
        super().__init__(widget)

    def get_widget_flutter(self) -> SizedBox:
        return self.widget_flutter

    def mount(self, context: BuildContext) -> tk.Widget:

        frame = ttk.Frame(context.parent_tk_widget)

        if self.get_widget_flutter().width:
            frame.configure(width=self.get_widget_flutter().width)

        if self.get_widget_flutter().height:
            frame.configure(height=self.get_widget_flutter().height)

        frame.pack_propagate(False)
        frame.pack()
        self.widget_tk = frame
        return frame


# ============================================================
# CONTAINER
# ============================================================


class Container(StatelessWidget):

    def __init__(
        self,
        child: Optional[FlutterWidget] = None,
        width: int | None = None,
        height: int | None = None,
        padding: int = 0,
        *,
        key: GlobalKey | None = None,
    ) -> None:
        super().__init__(key)

        self.child = child
        self.width = width
        self.height = height
        self.padding = padding

    def build(self, context: BuildContext) -> FlutterWidget:
        return self

    def create_element(self) -> Element:
        return ContainerElement(self)


class ContainerElement(Element[Container, ttk.Frame]):

    def __init__(self, widget: Container) -> None:
        super().__init__(widget)

    def get_widget_flutter(self) -> Container:
        return self.widget_flutter

    def mount(self, context: BuildContext) -> ttk.Frame:
        super().mount(context)

        frame = ttk.Frame(context.parent_tk_widget)

        if self.get_widget_flutter().width:
            frame.configure(width=float(self.get_widget_flutter().width))

        if self.get_widget_flutter().height:
            frame.configure(height=float(self.widget_flutter.height))

        frame.pack()

        if self.get_widget_flutter().child:
            child_element = self.get_widget_flutter().child.create_element()

            child_context = BuildContext(
                app=context.app, parent_widget=frame, parent_context=context
            )

            child_element.mount(child_context)

        self.widget_tk = frame
        return frame
