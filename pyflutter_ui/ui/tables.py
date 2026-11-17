# tables.py
from __future__ import annotations

from tkinter import ttk
from typing import Callable, cast, Any

from pyflutter_ui.ui.core import (
    BuildContext,
    Element,
    FlutterWidget,
    GlobalKey,
    StatelessWidget,
)

# ============================================================
# TABLEVIEW
# ============================================================


class TableView(StatelessWidget):

    def __init__(
        self,
        columns: list[str],
        rows: list[list[object]],
        headings: dict[str, str] | None = None,
        on_select: Callable[[list[Any]], None] | None = None,
        height: int = 10,
        key: GlobalKey | None = None,
    ) -> None:
        super().__init__(key)

        self.columns = columns
        self.rows = rows
        self.headings = headings or {}
        self.on_select = on_select or self._on_select_item
        self.height = height

    def _on_select_item(self, values: list[Any]):
        print(values)

    def build(self, context: BuildContext) -> TableView:
        return self

    def create_element(self) -> Element:
        return TreeViewElement(self)


class TreeViewElement(Element[TableView, ttk.Treeview]):

    def __init__(self, widget: TableView) -> None:
        super().__init__(widget)

    def get_widget_flutter(self) -> TableView:
        return self.widget_flutter

    def update(self, new_widget: FlutterWidget) -> None:

        self.widget_flutter = cast(TableView, new_widget)
        if self.widget_tk is None:
            return

        tree = cast(ttk.Treeview, self.widget_tk)

        for item in tree.get_children():
            tree.delete(item)

        for row in self.widget_flutter.rows:
            tree.insert("", "end", values=[str(v) for v in row])

    def mount(self, context: BuildContext) -> ttk.Treeview:
        super().mount(context)

        frame = ttk.Frame(context.parent_tk_widget)
        frame.pack(fill="both", expand=True)

        # Scrollbar horizontal — precisa ser criada ANTES do tree.pack
        scrollbar_x = ttk.Scrollbar(frame, orient="horizontal")
        scrollbar_y = ttk.Scrollbar(frame, orient="vertical")

        tree = ttk.Treeview(
            frame,
            columns=self.get_widget_flutter().columns,
            show="headings",
            height=self.get_widget_flutter().height,
            xscrollcommand=scrollbar_x.set,
            yscrollcommand=scrollbar_y.set,
        )

        scrollbar_x.configure(command=tree.xview)
        scrollbar_y.configure(command=tree.yview)

        for column in self.get_widget_flutter().columns:
            label = self.get_widget_flutter().headings.get(column, column)
            tree.heading(column, text=label)
            # minwidth garante que haja conteúdo para rolar na horizontal
            tree.column(column, anchor="w", width=120, minwidth=80, stretch=False)

        for row in self.get_widget_flutter().rows:
            tree.insert("", "end", values=[str(v) for v in row])

        # Ordem de pack importa: scrollbars nas bordas, tree no centro
        scrollbar_y.pack(side="right", fill="y")
        scrollbar_x.pack(side="bottom", fill="x")
        tree.pack(side="left", fill="both", expand=True)

        if self.get_widget_flutter().on_select:

            def _on_select(event):
                selection = tree.selection()
                if not selection:
                    return
                values = list(tree.item(selection[0], "values"))
                self.get_widget_flutter().on_select(values)

            tree.bind("<<TreeviewSelect>>", _on_select)

        self.widget_tk = tree
        return tree
