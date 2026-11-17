# buttons.py
from __future__ import annotations
from typing import Any, Callable
from tkinter import ttk
import tkinter as tk

from pyflutter_ui.ui.core import (
    FlutterWidget,
    BuildContext,
    Element,
    GlobalKey,
    StatelessWidget,
    tkWidgetType,
    ChangeNotifier,
)
from pyflutter_ui.ui.container import Container


# ============================================================
# FLEX
# ============================================================
class Expanded[E: ExpandedElement](StatelessWidget):

    def __init__(
        self, child: FlutterWidget, flex: int = 1, *, key: GlobalKey | None = None
    ) -> None:
        super().__init__(key)

        self.child = child
        self.flex = flex

    def create_element(self) -> ExpandedElement:
        return ExpandedElement(self)

    def build(self, context: BuildContext) -> FlutterWidget:
        return self.child


class ExpandedElement[F: Expanded, T: tkWidgetType](Element):

    def __init__(self, widget: Expanded) -> None:
        super().__init__(widget)
        self._child_element: Element | None = None

    def get_widget_flutter(self) -> Expanded:
        return self.widget_flutter

    def mount(self, context: BuildContext) -> T:
        super().mount(context)
        child_element: Element = self.get_widget_flutter().child.create_element()

        child_element.layout_data.flex = self.get_widget_flutter().flex
        child_element.layout_data.expand = True
        widget = child_element.mount(context)

        self._child_element = child_element  # <-- faltava
        self.render_object = child_element.render_object
        self.widget_tk = widget
        return widget

    def unmount(self) -> None:
        if self._child_element is not None:
            self._child_element.unmount()
            self._child_element = None
        super().unmount()


class Flexible(Expanded):

    def __init__(
        self, child: FlutterWidget, flex: int = 1, *, key: GlobalKey | None = None
    ) -> None:
        super().__init__(child, flex, key=key)

    def create_element(self) -> FlexibleElement:
        return FlexibleElement(self)


class FlexibleElement(ExpandedElement):

    EXPAND = False

    def __init__(self, widget: Flexible) -> None:
        super().__init__(widget)

    def get_widget_flutter(self) -> Flexible:
        return self.widget_flutter

    def mount(self, context: BuildContext) -> tk.Widget:
        super().mount(context)
        self._child_element.layout_data.expand = False
        return self.widget_tk


class Spacer(Expanded):

    def __init__(
        self, child: FlutterWidget, flex: int = 1, *, key: GlobalKey | None = None
    ) -> None:
        super().__init__(child, flex, key=key)


# ============================================================
# ELEVATED BUTTON
# ============================================================


class ElevatedButton(StatelessWidget):

    def __init__(
        self, text: str, on_pressed: Callable[[], None], *, key: GlobalKey | None = None
    ) -> None:
        super().__init__(key)

        self.text = text
        self.on_pressed = on_pressed

    def build(self, context: BuildContext) -> FlutterWidget:
        return self

    def create_element(self) -> ElevatedButtonElement:
        return ElevatedButtonElement(self)


class ElevatedButtonElement[F: ElevatedButton, T: ttk.Button](Element):

    def __init__(self, widget: ElevatedButton) -> None:
        super().__init__(widget)

    def get_widget_flutter(self) -> ElevatedButton:
        return super().get_widget_flutter()

    def get_widget_tk(self) -> ttk.Button:
        return super().get_widget_tk()

    def mount(self, context: BuildContext) -> ttk.Button:
        super().mount(context)
        self.widget_tk = ttk.Button(
            context.parent_tk_widget,
            text=self.get_widget_flutter().text,
            command=self.get_widget_flutter().on_pressed,
        )
        # fill="both" garante que o botão preenche o wrapper
        # que o FlexRenderObject controla via grid
        self.widget_tk.pack(fill="both", expand=True)
        return self.widget_tk

    def update(self, new_widget: FlutterWidget) -> None:
        super().update(new_widget)
        if self.widget_tk is not None:
            self.get_widget_tk().configure(
                text=self.get_widget_flutter().text,
                command=self.get_widget_flutter().on_pressed,
            )


# ============================================================
# DROPDOWN BUTTON
# ============================================================


class DropdownButton(StatelessWidget):

    def __init__(
        self,
        items: list[str],
        value: str | None = None,
        *,
        on_changed: Callable[[str], None] | None = None,
        key: GlobalKey | None = None,
    ) -> None:
        super().__init__(key)

        self.items = items

        if value is None:
            if len(self.items) > 0:
                self.value = self.items[0]
            else:
                self.value = ""
        else:
            self.value = value

        self.on_changed = on_changed

    def build(self, context: BuildContext) -> FlutterWidget:
        return self

    def create_element(self) -> Element:
        return DropdownButtonElement(self)


class DropdownButtonElement(Element[DropdownButton, ttk.Combobox]):

    def __init__(self, widget: DropdownButton) -> None:
        super().__init__(widget)
        self.variable: tk.StringVar = tk.StringVar(value=widget.value)

    def get_widget_flutter(self) -> DropdownButton:
        return self.widget_flutter

    def get_widget_tk(self) -> ttk.Combobox:
        return super().get_widget_tk()

    def update(self, new_widget: FlutterWidget) -> None:
        super().update(new_widget)
        self.get_widget_tk().set(self.get_widget_flutter().value)
        self.get_widget_tk()["values"] = self.get_widget_flutter().items

    def mount(self, context: BuildContext) -> ttk.Combobox:
        super().mount(context)

        combo = ttk.Combobox(
            context.parent_tk_widget,
            textvariable=self.variable,
            values=self.get_widget_flutter().items,
        )
        combo.set(self.get_widget_flutter().value)
        combo.pack(fill="x")

        # Força o Tk processar o layout antes de setar o valor
        combo.update_idletasks()

        if self.get_widget_flutter().on_changed:
            combo.bind(
                "<<ComboboxSelected>>",
                lambda e: self.get_widget_flutter().on_changed(self.variable.get()),
            )
        self.widget_tk = combo
        return combo


# ============================================================
# FLOATING ACTION BUTTON
# ============================================================


class FloatingActionButton(ElevatedButton):

    def __init__(
        self, text: str, on_pressed: Callable[[], None], *, key: GlobalKey | None = None
    ) -> None:
        super().__init__(text, on_pressed, key=key)


# ============================================================
# TextEditingController + TextInput (campo de texto controlado)
# ============================================================
class TextEditingController(ChangeNotifier):
    """Equivalente ao TextEditingController do Flutter."""

    def __init__(self, text: str = "") -> None:
        super().__init__()
        self._text: str = text
        self._focus: Callable[[], None] | None = None

    @property
    def text(self) -> str:
        return self._text

    @text.setter
    def text(self, value: str) -> None:
        self._text = value
        self.notify_listeners()

    def set_silent(self, value: str) -> None:
        """Atualiza sem notificar (usado pelo próprio campo ao digitar)."""
        self._text = value

    def clear(self) -> None:
        self.text = ""

    def bind_focus(self, fn: Callable[[], None] | None) -> None:
        self._focus = fn

    def request_focus(self) -> None:
        if self._focus is not None:
            self._focus()


class TextInput(StatelessWidget):

    def __init__(
        self,
        controller: TextEditingController,
        *,
        width: int = 14,
        on_submitted: Callable[[], None] | None = None,
        key: GlobalKey | None = None,
    ) -> None:
        super().__init__(key)

        self.controller: TextEditingController = controller
        self.width: int = width
        self.on_submitted: Callable[[], None] | None = on_submitted

    def build(self, context: BuildContext) -> FlutterWidget:
        return self

    def create_element(self) -> Element:
        return TextInputElement(self)


class TextInputElement(Element[TextInput, ttk.Entry]):

    def __init__(self, widget: TextInput) -> None:
        super().__init__(widget)
        self._var: tk.StringVar | None = None

    def get_widget_flutter(self) -> TextInput:
        return self.widget_flutter  # type: ignore[return-value]

    def mount(self, context: BuildContext) -> ttk.Entry:
        super().mount(context)
        w = self.get_widget_flutter()
        var = tk.StringVar(value=w.controller.text)
        entry = ttk.Entry(context.parent_tk_widget, textvariable=var, width=w.width)
        entry.pack(fill="x")

        self._var = var
        var.trace_add("write", self._on_var)
        w.controller.add_listener(self._on_controller)

        def focus() -> None:
            entry.focus_set()
            entry.selection_range(0, "end")

        w.controller.bind_focus(focus)

        if w.on_submitted is not None:
            callback = w.on_submitted
            entry.bind("<Return>", lambda _e: callback())

        self.widget_tk = entry
        return entry

    def _on_var(self, *_: object) -> None:
        if self._var is not None:
            self.get_widget_flutter().controller.set_silent(self._var.get())

    def _on_controller(self) -> None:
        ctrl = self.get_widget_flutter().controller
        if self._var is not None and self._var.get() != ctrl.text:
            self._var.set(ctrl.text)

    def unmount(self) -> None:
        ctrl = self.get_widget_flutter().controller
        ctrl.remove_listener(self._on_controller)
        ctrl.bind_focus(None)
        self._var = None
        super().unmount()
