from __future__ import annotations
from tkinter import ttk
from pyflutter_ui import (
    StatelessWidget,
    BuildContext,
    FlutterWidget,
    Element,
)

from pandas import DataFrame


class TableOrProgress(StatelessWidget):
    """Widget folha que encapsula os três estados da tabela."""

    def __init__(
        self,
        running: bool,
        df: DataFrame,
    ) -> None:
        super().__init__()
        self.running: bool = running
        self.df = df

    def build(self, context: BuildContext) -> TableOrProgress:
        return self  # leaf widget

    def create_element(self) -> Element:
        return _TableOrProgressElement(self)


class _TableOrProgressElement(Element[TableOrProgress, ttk.Frame]):

    MAX_ROWS = 400  # limite de linhas inseridas no Treeview

    def __init__(self, widget: TableOrProgress) -> None:
        super().__init__(widget)
        self._frame: ttk.Frame = None
        self._progress: ttk.Progressbar = None
        self._tree: ttk.Treeview = None
        self._scrollbar_x: ttk.Scrollbar = None
        self._scrollbar_y: ttk.Scrollbar = None

        self._progress_running: bool = False
        self._last_running: bool | None = None
        self._last_df: DataFrame | None = None

    def get_widget_flutter(self) -> TableOrProgress:
        return self.widget_flutter  # type: ignore

    def get_widget_tk(self) -> ttk.Frame:
        return super().get_widget_tk()

    def mount(self, context: BuildContext) -> ttk.Frame:
        super().mount(context)
        self._frame = ttk.Frame(context.parent_tk_widget)
        self._frame.pack(fill="both", expand=True)

        self._progress = ttk.Progressbar(self._frame, mode="indeterminate", length=300)

        self._scrollbar_y = ttk.Scrollbar(self._frame, orient="vertical")
        self._scrollbar_x = ttk.Scrollbar(self._frame, orient="horizontal")
        self._tree = ttk.Treeview(
            self._frame,
            show="headings",
            yscrollcommand=self._scrollbar_y.set,
            xscrollcommand=self._scrollbar_x.set,
        )
        self._scrollbar_y.configure(command=self._tree.yview)
        self._scrollbar_x.configure(command=self._tree.xview)

        self.widget_tk = self._frame
        self._last_running = None
        self._last_df = None
        self.update_table(self.get_widget_flutter())
        return self._frame

    def update(self, new_widget: FlutterWidget) -> None:
        super().update(new_widget)
        self.update_table(self.get_widget_flutter())

    def unmount(self) -> None:
        if self._progress is not None:
            try:
                self._progress.stop()
            except Exception:
                pass
        self._progress_running = False
        super().unmount()

    # ── estado visual ────────────────────────────────────────

    def update_table(self, w: TableOrProgress) -> None:
        if self._frame is None:
            return

        # Nada mudou: não refaz a tabela nem reinicia a animação.
        if w.running == self._last_running and w.df is self._last_df:
            return
        self._last_running = w.running
        self._last_df = w.df

        if w.running:
            self._show_progress()
        else:
            self._show_table(w.df)

    def _show_progress(self) -> None:
        self._clear_tree()
        self._scrollbar_y.pack_forget()
        self._scrollbar_x.pack_forget()
        self._tree.pack_forget()

        if not self._progress_running:
            self._progress.pack(pady=20)
            self._progress.start(9)
            self._progress_running = True

    def _show_table(self, df: DataFrame) -> None:
        if self._progress_running:
            self._progress.stop()
            self._progress.pack_forget()
            self._progress_running = False

        self._clear_tree()
        self._scrollbar_y.pack(side="right", fill="y")
        self._scrollbar_x.pack(side="bottom", fill="x")
        self._tree.pack(side="left", fill="both", expand=True)
        self.refresh_tree(df)

    def _clear_tree(self) -> None:
        if self._tree is None:
            return
        self._tree.delete(*self._tree.get_children())
        self._tree["columns"] = ()

    def refresh_tree(self, df: DataFrame) -> None:
        if self._tree is None or df.empty:
            return

        names = [str(c) for c in df.columns]  # Treeview exige str
        view = df.head(self.MAX_ROWS)
        sample = view.head(200)
        last = len(names) - 1

        self._tree["columns"] = names

        for i, name in enumerate(names):
            # iloc evita problema com nomes de coluna duplicados
            values = sample.iloc[:, i].tolist()
            longest = max([len(name)] + [len(str(v)) for v in values])
            width = min(max(longest * 8 + 20, 80), 900)

            self._tree.heading(name, text=name)
            self._tree.column(
                name, anchor="w", width=width, minwidth=80, stretch=(i == last)
            )

        for row in view.itertuples(index=False, name=None):
            self._tree.insert("", "end", values=[str(v) for v in row])
