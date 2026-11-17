from __future__ import annotations

from pyflutter_ui.ui.core import (
    Element,
    GlobalKey,
    inflate_widget,
    StatelessWidget,
    BuildContext,
    FlutterWidget,
)
from pyflutter_ui.ui.progress import LinearProgress
from pyflutter_ui.ui.widgets import Column
from tkinter import ttk
import tkinter as tk
from typing import Callable, Generic, cast, TypeVar

T = TypeVar("T")


# ============================================================
# SCROLL VIEW
# ============================================================


class ScrollView(StatelessWidget):

    def __init__(self, child: FlutterWidget, *, key: GlobalKey | None = None) -> None:
        super().__init__(key)
        self.child: FlutterWidget = child

    def build(self, context: BuildContext) -> FlutterWidget:
        return self

    def create_element(self) -> Element:
        return ScrollViewElement(self)


class ScrollViewElement(Element[ScrollView, ttk.Frame]):

    def __init__(self, widget: ScrollView) -> None:
        super().__init__(widget)

    def update(self, new_widget: FlutterWidget) -> None:
        context = self.get_context()  # salva ANTES de trocar o widget
        self.widget_flutter = cast(ScrollView, new_widget)
        self.widget_flutter.context = context
        if context:
            self.unmount()
            self.mount(context)

    def get_widget_flutter(self) -> ScrollView:
        return self.widget_flutter

    def mount(self, context: BuildContext) -> ttk.Frame:
        super().mount(context)
        container = ttk.Frame(context.parent_tk_widget)
        container.pack(fill="both", expand=True)
        canvas = tk.Canvas(container)

        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas)

        content.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self._child_element = self.get_widget_flutter().child.create_element()
        child_context = BuildContext(
            app=context.app, parent_widget=content, parent_context=context
        )
        self._child_element.mount(child_context)

        self.widget_tk = container
        return container

    def unmount(self) -> None:
        if self._child_element is not None:
            self._child_element.unmount()
            self._child_element = None
        super().unmount()


# ============================================================
# SCROLLABLE COLUMN
# ============================================================


class ScrollableColumn(StatelessWidget):

    def __init__(
        self,
        children: list[FlutterWidget],
        *,
        scrollbar: bool = True,
        mousewheel: bool = True,
        padding: int = 0,
        key: GlobalKey | None = None,
    ) -> None:
        super().__init__(key)

        self.children = children
        self.scrollbar = scrollbar
        self.mousewheel = mousewheel
        self.padding = padding

    def build(self, context: BuildContext) -> FlutterWidget:
        return self

    def create_element(self) -> Element:
        return ScrollableColumnElement(self)


class ScrollableColumnElement(Element[ScrollableColumn, ttk.Frame]):

    def __init__(self, widget: ScrollableColumn) -> None:
        super().__init__(widget)

        self._child_elements: list[Element] = []
        self._canvas: tk.Canvas | None = None
        self._content: ttk.Frame | None = None
        self._canvas_window = None

    def get_widget_flutter(self) -> ScrollableColumn:
        return self.widget_flutter

    def mount(self, context: BuildContext) -> ttk.Frame:
        super().mount(context)

        # ====================================================
        # CONTAINER PRINCIPAL
        # ====================================================
        container = ttk.Frame(context.parent_tk_widget)
        container.pack(fill="both", expand=True)

        # ====================================================
        # CANVAS
        # ====================================================
        canvas = tk.Canvas(container, highlightthickness=0, borderwidth=0)
        self._canvas = canvas

        # ====================================================
        # SCROLLBAR
        # ====================================================

        scrollbar = None

        if self.get_widget_flutter().scrollbar:
            scrollbar = ttk.Scrollbar(
                container, orient="vertical", command=canvas.yview
            )
            scrollbar.pack(side="right", fill="y")
            canvas.configure(yscrollcommand=scrollbar.set)

        # ====================================================
        # ÁREA DE CONTEÚDO
        # ====================================================
        self._content = ttk.Frame(canvas)
        self._canvas_window = canvas.create_window(
            (0, 0), window=self._content, anchor="nw"
        )

        # ====================================================
        # ATUALIZA SCROLL REGION
        # ====================================================
        def update_scroll_region(event=None):
            if not canvas.winfo_exists():
                return
            canvas.configure(scrollregion=canvas.bbox("all"))

        self._content.bind("<Configure>", update_scroll_region)

        # ====================================================
        # MANTÉM A LARGURA DO CONTEÚDO IGUAL À DO CANVAS
        # ====================================================
        def update_content_width(event):
            if not canvas.winfo_exists():
                return
            canvas.itemconfigure(self._canvas_window, width=event.width)
            canvas.configure(scrollregion=canvas.bbox("all"))

        canvas.bind("<Configure>", update_content_width)

        # ====================================================
        # CANVAS
        # ====================================================
        canvas.pack(side="left", fill="both", expand=True)

        # ====================================================
        # MOUSE WHEEL
        # ====================================================

        if self.get_widget_flutter().mousewheel:

            def mousewheel(event):

                if event.delta != 0:
                    canvas.yview_scroll(int(-event.delta / 120), "units")

            canvas.bind("<MouseWheel>", mousewheel)
            self._content.bind("<MouseWheel>", mousewheel)

        # Linux
        canvas.bind("<Button-4>", lambda event: canvas.yview_scroll(-1, "units"))

        canvas.bind("<Button-5>", lambda event: canvas.yview_scroll(1, "units"))

        self._content.bind("<Button-4>", lambda event: canvas.yview_scroll(-1, "units"))

        self._content.bind("<Button-5>", lambda event: canvas.yview_scroll(1, "units"))

        # ====================================================
        # CONTEÚDO VERTICAL
        # ====================================================

        content_inner = ttk.Frame(self._content)

        content_inner.pack(
            fill="x",
            expand=False,
            padx=self.get_widget_flutter().padding,
            pady=self.get_widget_flutter().padding,
        )

        # ====================================================
        # MONTA OS WIDGETS
        # ====================================================

        for child in self.get_widget_flutter().children:

            child_element = inflate_widget(child)
            child_context = context.create_child_context(content_inner)
            child_element.mount(child_context)
            self._child_elements.append(child_element)

        # ====================================================
        # FORÇA ATUALIZAÇÃO DO SCROLL REGION
        # ====================================================
        self._content.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))
        self.widget_tk = container
        return container

    def update(self, new_widget: FlutterWidget) -> None:

        context = self._parent_context
        self.widget_flutter = cast(ScrollableColumn, new_widget)

        if context is not None:
            self.unmount()
            self.mount(context)

    def unmount(self) -> None:

        for child_element in self._child_elements:

            try:
                child_element.unmount()
            except Exception:
                pass

        self._child_elements.clear()

        self._canvas = None
        self._content = None
        self._canvas_window = None
        super().unmount()


class ScrollableColumnOrProgress(StatelessWidget):
    """
    Exibe uma lista vertical e rolável de FlutterWidgets.

    Enquanto `running` for True:
        exibe o LinearProgress.

    Enquanto `running` for False:
        exibe os widgets dentro de um ScrollView.

    Os widgets podem ser qualquer FlutterWidget:
        Text
        Button
        Row
        Column
        Card
        Container
        etc.
    """

    def __init__(
        self,
        running: bool,
        children: list[FlutterWidget],
        *,
        padding: int = 0,
        key: GlobalKey | None = None,
    ) -> None:
        super().__init__(key)

        self.running = running
        self.children = children
        self.padding = padding

    def build(self, context: BuildContext) -> FlutterWidget:

        if self.running:
            return LinearProgress(indeterminate=True)

        return ScrollView(Column(self.children))


# ============================================================
# LIST BUILDER
# ============================================================


class ListBuilder(StatelessWidget, Generic[T]):

    def __init__(
        self,
        items: list[T],
        item_builder: Callable[[BuildContext, int, T], FlutterWidget],
        *,
        key: GlobalKey | None = None,
    ) -> None:
        super().__init__(key)

        self.items: list[T] = items
        self.item_builder: Callable[[BuildContext, int, T], FlutterWidget] = (
            item_builder
        )

    def build(self, context: BuildContext) -> ListBuilder[T]:
        return self

    def create_element(self) -> ListBuilderElement:
        return ListBuilderElement(self)


class ListBuilderElement[F: ListBuilder, T: ttk.Frame](Element[F, T]):

    def __init__(self, widget: F) -> None:
        super().__init__(widget)
        self._child_elements: list[Element] = []
        self._parent_context: BuildContext | None = None

    def get_widget_flutter(self) -> ListBuilder:
        return super().get_widget_flutter()

    def mount(self, context: BuildContext) -> T:

        super().mount(context)
        self._parent_context = context

        if not context.parent_tk_widget.winfo_exists():
            return None

        frame = ttk.Frame(context.parent_tk_widget)
        frame.pack(fill="both", expand=True)

        self._child_elements = []
        _widget_items = self.get_widget_flutter().items

        for index, item in enumerate(_widget_items):
            widget = self.get_widget_flutter().item_builder(context, index, item)
            child_element = widget.create_element()
            child_context = BuildContext(
                app=context.app, parent_widget=frame, parent_context=context
            )
            child_element.mount(child_context)
            self._child_elements.append(child_element)

        self.tk_widget = frame
        return frame

    def update(self, new_widget: FlutterWidget) -> None:
        context = self._parent_context
        self.widget = new_widget
        if context is not None and context.parent_tk_widget.winfo_exists():
            self.unmount()
            self.mount(context)

    def unmount(self) -> None:
        for child_element in self._child_elements:
            child_element.unmount()
        self._child_elements = []
        super().unmount()
