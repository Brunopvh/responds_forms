# progress.py
from __future__ import annotations
from tkinter import ttk
import tkinter as tk

from pyflutter_ui.ui.core import (
    BuildContext,
    Element,
    FlutterWidget,
    GlobalKey,
    StatelessWidget,
)

# ============================================================
# LINEAR PROGRESS
# ============================================================


class LinearProgress(StatelessWidget):

    def __init__(
        self,
        value: float = 0.0,
        indeterminate: bool = False,
        *,
        key: GlobalKey | None = None,
    ) -> None:
        super().__init__(key)

        self.value = value
        self.indeterminate = indeterminate

    def build(self, context: BuildContext) -> FlutterWidget:
        return self

    def create_element(self) -> Element:
        return LinearProgressElement(self)


class LinearProgressElement(Element[LinearProgress, ttk.Progressbar]):

    def __init__(self, widget: LinearProgress) -> None:
        super().__init__(widget)

    def get_widget_flutter(self) -> LinearProgress:
        return self.widget_flutter

    def get_widget_tk(self) -> ttk.Progressbar:
        return super().get_widget_tk()

    def _apply(self, bar: ttk.Progressbar, widget: LinearProgress) -> None:
        """Sincroniza o ttk.Progressbar com o estado do widget."""
        if widget.indeterminate:
            if str(bar.cget("mode")) != "indeterminate":
                bar.configure(mode="indeterminate")
                bar.start(9)
            # se já estava indeterminate, não reinicia a animação
        else:
            if str(bar.cget("mode")) != "determinate":
                bar.stop()
                bar.configure(mode="determinate")
            bar["value"] = max(0.0, min(100.0, widget.value * 100))

    def mount(self, context: BuildContext) -> ttk.Progressbar:
        super().mount(context)
        progress = ttk.Progressbar(context.parent_tk_widget, mode="determinate")
        self._apply(progress, self.get_widget_flutter())
        progress.pack(fill="x", expand=True, padx=1, pady=1)
        self.widget_tk = progress
        return progress

    def update(self, new_widget: FlutterWidget) -> None:
        super().update(new_widget)  # atualiza widget_flutter e context
        bar = self.get_widget_tk()
        if bar is None:
            return
        try:
            if bar.winfo_exists():
                self._apply(bar, self.get_widget_flutter())
        except tk.TclError:
            pass

    def unmount(self) -> None:
        bar = self.get_widget_tk()
        if bar is not None:
            try:
                bar.stop()  # cancela o after() da animação
            except Exception:
                pass
        super().unmount()


# ============================================================
# CIRCULAR PROGRESS
# ============================================================
class CircularProgress(StatelessWidget):

    def __init__(self, key: GlobalKey | None = None) -> None:
        super().__init__(key)

    def build(self, context: BuildContext) -> FlutterWidget:
        return self

    def create_element(self) -> Element:
        return CircularProgressElement(self)


class CircularProgressElement(Element[CircularProgress, ttk.Progressbar]):

    def __init__(self, widget: CircularProgress) -> None:
        super().__init__(widget)

    def update(self, new_widget: FlutterWidget) -> None:
        super().update(new_widget)  # nada visual para atualizar

    def unmount(self) -> None:
        bar: ttk.Progressbar = self.get_widget_tk()
        if bar is not None:
            try:
                bar.stop()
            except Exception:
                pass
        super().unmount()
