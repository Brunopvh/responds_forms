# widgets.py
from __future__ import annotations
from enum import Enum
import tkinter as tk
from tkinter import ttk
from typing import Optional, Callable, cast, Any, Literal

from pyflutter_ui.ui.core import (
    BuildContext,
    Element,
    FlutterWidget,
    GlobalKey,
    StatelessWidget,
    BaseMaterialApp,
    RenderObject,
    inflate_widget,
    PageApp,
)
from pyflutter_ui.ui.container import Container, SizedBox
from pyflutter_ui.navigator import NavigatorApp, Navigator
from pyflutter_ui.scheduler import MainThreadScheduler


class TkMaterialApp(BaseMaterialApp):

    def __init__(
        self,
        home: PageApp,
        *,
        theme: Any = None,
        height: int = 350,
        width: int = 480,
    ) -> None:
        super().__init__(home, theme)
        self._navigator = NavigatorApp(self)
        self._width: int = width
        self._height: int = height
        self._root: tk.Tk = tk.Tk()

    @property
    def geometry(self) -> str:
        return f"{self._width}x{self._height}"

    def set_height(self, new: int):
        self._height = new
        self.update_geometry()

    def set_width(self, new: int):
        self._width = new
        self.update_geometry()

    def update_geometry(self):
        self.get_root().geometry(self.geometry)

    def get_navigator(self) -> Navigator:
        return self._navigator

    def run(self) -> None:
        if self._root is None:
            self._root = tk.Tk()

        self.update_geometry()
        # self._root.title(self.home.name)

        ##
        MainThreadScheduler.attach(self.get_root())
        ##
        self.get_navigator().push(self.home)

        try:
            self._root.mainloop()
        finally:
            MainThreadScheduler.detach()


# ============================================================
# ALIGNMENTS
# ============================================================
class MainAxisAlignment(Enum):
    START = "start"
    CENTER = "center"
    END = "end"
    SPACE_BETWEEN = "space_between"
    SPACE_AROUND = "space_around"
    SPACE_EVENLY = "space_evenly"


class CrossAxisAlignment(Enum):
    START = "start"
    CENTER = "center"
    END = "end"
    STRETCH = "stretch"


class Alignment(Enum):
    TOP_LEFT = "top_left"
    TOP_CENTER = "top_center"
    TOP_RIGHT = "top_right"

    CENTER_LEFT = "center_left"
    CENTER = "center"
    CENTER_RIGHT = "center_right"

    BOTTOM_LEFT = "bottom_left"
    BOTTOM_CENTER = "bottom_center"
    BOTTOM_RIGHT = "bottom_right"


class FlexRenderObject(RenderObject):

    def __init__(
        self,
        direction: Literal["row", "column"],
        *,
        main_axis_alignment: MainAxisAlignment = MainAxisAlignment.CENTER,
        cross_axis_alignment: CrossAxisAlignment = CrossAxisAlignment.CENTER,
    ) -> None:
        super().__init__()
        self.direction = direction
        self.main_axis_alignment: MainAxisAlignment = main_axis_alignment
        self.cross_axis_alignment: CrossAxisAlignment = cross_axis_alignment

    def apply_layout(self) -> None:
        if self.tk_widget is None:
            return

        if self.direction == "row":
            self.tk_widget.grid_rowconfigure(0, weight=1)
        else:
            self.tk_widget.grid_columnconfigure(0, weight=1)

        # Calcula o anchor/sticky base para o cross axis
        if self.direction == "row":
            # ancora o filho à esquerda da célula quando main_axis é START
            main_sticky = {
                MainAxisAlignment.START: "w",
                MainAxisAlignment.END: "e",
                MainAxisAlignment.CENTER: "",
            }.get(self.main_axis_alignment, "w")

            cross_sticky = {
                CrossAxisAlignment.START: "n",
                CrossAxisAlignment.END: "s",
                CrossAxisAlignment.CENTER: "",
                CrossAxisAlignment.STRETCH: "ns",
            }.get(self.cross_axis_alignment, "")
        else:
            main_sticky = {
                MainAxisAlignment.START: "n",
                MainAxisAlignment.END: "s",
                MainAxisAlignment.CENTER: "",
            }.get(self.main_axis_alignment, "n")

            cross_sticky = {
                CrossAxisAlignment.START: "w",
                CrossAxisAlignment.END: "e",
                CrossAxisAlignment.CENTER: "",
                CrossAxisAlignment.STRETCH: "ew",
            }.get(self.cross_axis_alignment, "")

        for index, child in enumerate(self.children):
            widget = child.tk_widget
            if widget is None:
                continue

            flex = child.layout_data.flex
            expand = child.layout_data.expand
            fill_x = child.layout_data.fill_x
            fill_y = child.layout_data.fill_y

            if expand:
                sticky = "nsew"
            else:
                # combina main + cross axis
                sticky = main_sticky + cross_sticky
                if fill_x:
                    sticky += "ew"
                if fill_y:
                    sticky += "ns"

            if self.direction == "row":
                col_weight = flex if flex > 0 else 0
                self.tk_widget.grid_columnconfigure(index, weight=col_weight)
                widget.grid(row=0, column=index, sticky=sticky, padx=(0, 2))
            else:
                row_weight = flex if flex > 0 else 0
                self.tk_widget.grid_rowconfigure(index, weight=row_weight)
                widget.grid(row=index, column=0, sticky=sticky, pady=(0, 2))

    def apply_layout_old(self) -> None:

        if self.tk_widget is None:
            return

        # Row()
        if self.direction == "row":
            self.tk_widget.grid_rowconfigure(0, weight=1)
        else:
            # Column()
            self.tk_widget.grid_columnconfigure(0, weight=1)

        for index, child in enumerate(self.children):

            widget = child.tk_widget
            if widget is None:
                continue

            flex = child.layout_data.flex

            expand = child.layout_data.expand

            fill_x = child.layout_data.fill_x

            fill_y = child.layout_data.fill_y

            sticky = ""

            if expand:
                sticky = "nsew"
            else:

                if fill_x:
                    sticky += "ew"

                if fill_y:
                    sticky += "ns"

            weight = max(1, flex)

            if self.direction == "row":
                self.tk_widget.grid_columnconfigure(index, weight=weight)
                widget.grid(row=0, column=index, sticky=sticky)
            else:
                self.tk_widget.grid_rowconfigure(index, weight=weight)
                widget.grid(row=index, column=0, sticky=sticky)


# ============================================================
# TEXT
# ============================================================


class Text(StatelessWidget):

    def __init__(self, text: str, key: GlobalKey | None = None) -> None:
        super().__init__(key)
        self.text: str = text

    def build(self, context: BuildContext) -> FlutterWidget:
        return self

    def create_element(self) -> Element:
        return TextElement(self)


class TextElement(Element[Text, ttk.Label]):

    def __init__(self, widget: Text) -> None:
        super().__init__(widget)

    def get_widget_flutter(self) -> Text:
        return self.widget_flutter

    def mount(self, context: BuildContext) -> ttk.Label:
        super().mount(context)

        label = ttk.Label(context.parent_tk_widget, text=self.get_widget_flutter().text)
        label.pack()
        self.widget_tk = label
        return label

    def update(self, new_widget: FlutterWidget) -> None:
        self.widget_flutter = cast(Text, new_widget)

        if self.widget_tk is not None:
            self.widget_tk.configure(text=self.widget_flutter.text)


# ============================================================
# PADDING
# ============================================================


class Padding(StatelessWidget):

    def __init__(
        self, key: GlobalKey | None = None, *, padding: int, child: FlutterWidget
    ) -> None:
        super().__init__(key)
        self.padding = padding
        self.child = child

    def build(self, context: BuildContext) -> Padding:
        return self

    def create_element(self) -> PaddingElement:
        return PaddingElement(self)


class PaddingElement(Element[Padding, ttk.Frame]):

    def __init__(self, widget: Padding) -> None:
        super().__init__(widget)

    def update(self, new_widget: FlutterWidget) -> None:
        context = self.get_context()  # salva ANTES de trocar o widget
        self.widget_flutter = cast(Padding, new_widget)
        self.widget_flutter.context = context
        if context:
            self.unmount()
            self.mount(context)

    def get_widget_flutter(self) -> Padding:
        return self.widget_flutter

    def mount(self, context: BuildContext) -> ttk.Frame:
        super().mount(context)
        frame = ttk.Frame(context.parent_tk_widget)
        frame.pack(
            padx=self.get_widget_flutter().padding,
            pady=self.get_widget_flutter().padding,
        )
        child_element = self.get_widget_flutter().child.create_element()

        child_context = BuildContext(
            app=context.app, parent_widget=frame, parent_context=context
        )

        child_element.mount(child_context)
        self.widget_tk = frame
        return frame


# ============================================================
# CENTER
# ============================================================


class Center(StatelessWidget):

    def __init__(self, child: FlutterWidget, *, key: GlobalKey | None = None) -> None:
        super().__init__(key)

        self.child = child

    def build(self, context: BuildContext) -> Center:
        return self

    def create_element(self) -> CenterElement:
        return CenterElement(self)


class CenterElement(Element[Center, ttk.Frame]):

    def __init__(self, widget: Center) -> None:
        super().__init__(widget)

    def get_widget_flutter(self) -> Center:
        return self.widget_flutter

    def mount(self, context: BuildContext) -> ttk.Frame:
        super().mount(context)
        frame = ttk.Frame(context.parent_tk_widget)
        frame.pack(expand=True)
        child_element = self.get_widget_flutter().child.create_element()

        child_context = BuildContext(
            app=context.app, parent_widget=frame, parent_context=context
        )

        child_element.mount(child_context)
        self.widget_tk = frame
        return frame


# ============================================================
# ALIGN
# ============================================================


class Align(StatelessWidget):

    def __init__(
        self,
        child: FlutterWidget,
        alignment: Alignment = (Alignment.CENTER),
        *,
        key: GlobalKey | None = None,
    ) -> None:
        super().__init__(key)

        self.child = child
        self.alignment = alignment

    def build(self, context: BuildContext) -> FlutterWidget:
        return self

    def create_element(self) -> Element:
        return AlignElement(self)


class AlignElement(Element[Align, ttk.Frame]):

    def __init__(self, widget: Align) -> None:
        super().__init__(widget)

    def get_widget_flutter(self) -> Align:
        return self.widget_flutter

    def get_widget_tk(self) -> ttk.Frame:
        return super().get_widget_tk()

    def mount(self, context: BuildContext) -> ttk.Frame:
        super().mount(context)
        frame = ttk.Frame(context.parent_tk_widget)

        anchor = {
            Alignment.TOP_LEFT: "nw",
            Alignment.TOP_CENTER: "n",
            Alignment.TOP_RIGHT: "ne",
            Alignment.CENTER_LEFT: "w",
            Alignment.CENTER: "center",
            Alignment.CENTER_RIGHT: "e",
            Alignment.BOTTOM_LEFT: "sw",
            Alignment.BOTTOM_CENTER: "s",
            Alignment.BOTTOM_RIGHT: "se",
        }.get(self.get_widget_flutter().alignment, "center")

        frame.pack(fill="both", expand=True)

        child_element = self.get_widget_flutter().child.create_element()
        child_context = context.create_child_context(frame)
        child_element.mount(child_context)

        # ancora o filho dentro do frame
        if child_element.widget_tk is not None:
            child_element.widget_tk.pack_configure(anchor=anchor, expand=False)

        self.widget_tk = frame
        return frame


# ============================================================
# DIVIDER
# ============================================================


class Divider(StatelessWidget):

    def __init__(
        self,
        *,
        orientation: Literal["horizontal", "vertical"] = "horizontal",
        key: GlobalKey | None = None,
    ) -> None:
        super().__init__(key)

        self.orientation: Literal["horizontal", "vertical"] = orientation

    def create_element(self) -> Element:
        return DividerElement(self)

    def build(self, context: BuildContext) -> FlutterWidget:
        return self


class DividerElement(Element[Divider, ttk.Separator]):

    def __init__(self, widget: Divider) -> None:
        super().__init__(widget)

    def get_widget_flutter(self) -> Divider:
        return self.widget_flutter

    def mount(self, context: BuildContext) -> ttk.Separator:
        super().mount(context)
        separator = ttk.Separator(
            context.parent_tk_widget, orient=self.get_widget_flutter().orientation
        )

        if self.get_widget_flutter().orientation == "horizontal":
            separator.pack(fill="x", padx=4)
        elif self.get_widget_flutter().orientation == "vertical":
            separator.pack(fill="y", pady=4)

        self.widget_tk = separator
        return separator


# ============================================================
# CARD
# ============================================================


class Card(Container):

    def __init__(
        self,
        child: FlutterWidget | None = None,
        width: int | None = None,
        height: int | None = None,
        padding: int = 0,
        *,
        key: GlobalKey | None = None,
    ) -> None:
        super().__init__(child, width, height, padding, key=key)


# ============================================================
# LIST ORIENTATION WIDGETS (super classe de Row e Column)
# ============================================================


class ListOrientationWidgets(StatelessWidget):
    """
    Base comum para widgets de lista com orientação fixa (Row/Column).
    Centraliza toda a lógica de montagem, layout via FlexRenderObject e
    atualização (update) em um único lugar — bugs corrigidos aqui valem
    automaticamente para Row e Column.
    """

    def __init__(
        self,
        children: list[FlutterWidget],
        direction: Literal["row", "column"],
        main_axis_alignment: MainAxisAlignment = MainAxisAlignment.START,
        cross_axis_alignment: CrossAxisAlignment = CrossAxisAlignment.CENTER,
        *,
        key: GlobalKey | None = None,
    ) -> None:
        super().__init__(key)

        self.children: list[FlutterWidget] = children
        self.direction: Literal["row", "column"] = direction
        self.main_axis_alignment = main_axis_alignment
        self.cross_axis_alignment = cross_axis_alignment

    def build(self, context: BuildContext) -> "ListOrientationWidgets":
        return self

    def create_element(self) -> ListOrientationWidgetsElement:
        return ListOrientationWidgetsElement(self)


class ListOrientationWidgetsElement(Element[ListOrientationWidgets, ttk.Frame]):

    def __init__(self, widget: ListOrientationWidgets) -> None:
        super().__init__(widget)
        self._child_elements: list[Element] = []

        self.render_object = FlexRenderObject(
            direction=widget.direction,
            main_axis_alignment=widget.main_axis_alignment,
            cross_axis_alignment=widget.cross_axis_alignment,
        )

    def get_widget_flutter(self) -> ListOrientationWidgets:
        return self.widget_flutter

    def get_widget_tk(self) -> ttk.Frame:
        return super().get_widget_tk()

    def _pack_frame(self, frame: ttk.Frame) -> None:
        """
        Empacotamento do frame principal. Comportamento padrão = Column
        (ocupa todo o espaço disponível). Subclasses (ex: RowElement)
        sobrescrevem quando precisam de outro comportamento de packing.
        """
        frame.pack(fill="both", expand=True)

    def update(self, new_widget: FlutterWidget) -> None:
        # IMPORTANTE: usa get_context() (== widget_flutter.context), nunca
        # um atributo tipo "_parent_context" guardado manualmente.
        # Element.mount() sempre seta widget_flutter.context em TODA
        # subclasse (é feito na base), então esta fonte nunca fica
        # desatualizada — foi exatamente a falta disso que causava o bug
        # de "monta certo na primeira vez, mas nunca atualiza depois".

        context: BuildContext | None = self.get_context()

        if context:
            new_widget.context = context
            self.widget_flutter = new_widget

            self.render_object = FlexRenderObject(
                direction=self.get_widget_flutter().direction,
                main_axis_alignment=self.get_widget_flutter().main_axis_alignment,
                cross_axis_alignment=self.get_widget_flutter().cross_axis_alignment,
            )
            self.unmount()
            self.mount(context)

    def mount(self, context: BuildContext) -> ttk.Frame:
        super().mount(context)

        if not context.parent_tk_widget.winfo_exists():
            return None  # pai já destruído, aborta silenciosamente em vez de TclError

        frame = ttk.Frame(context.parent_tk_widget)
        self._pack_frame(frame)
        self.render_object.attach_widget(frame)

        self._child_elements: list[Element] = []

        for child in self.get_widget_flutter().children:
            # wrapper entra no frame via grid (apply_layout faz isso)
            # NÃO chamar pack/grid aqui no wrapper
            wrapper = ttk.Frame(frame)

            child_element: Element = inflate_widget(child)
            child_context: BuildContext = context.create_child_context(wrapper)
            child_element.mount(child_context)
            self._child_elements.append(child_element)

            render_object = child_element.render_object
            render_object.attach_widget(wrapper)
            self.render_object.add_child(render_object)

        self.render_object.apply_layout()
        self.widget_tk = frame
        return frame

    def unmount(self) -> None:
        for child_element in self._child_elements:
            child_element.unmount()
        self._child_elements = []
        super().unmount()


# ============================================================
# ROW
# ============================================================
class Row(ListOrientationWidgets):

    def __init__(
        self,
        children: list[FlutterWidget],
        main_axis_alignment: MainAxisAlignment = MainAxisAlignment.START,
        cross_axis_alignment: CrossAxisAlignment = CrossAxisAlignment.CENTER,
        *,
        key: GlobalKey | None = None,
    ) -> None:
        super().__init__(
            children, "row", main_axis_alignment, cross_axis_alignment, key=key
        )

    def create_element(self) -> RowElement:
        return RowElement(self)


class RowElement(ListOrientationWidgetsElement):

    def __init__(self, widget: ListOrientationWidgets) -> None:
        super().__init__(widget)

    def _pack_frame(self, frame: ttk.Frame) -> None:
        frame.pack(fill="x", expand=False, padx=1, pady=1)


# ============================================================
# COLUMN
# ============================================================
class Column(ListOrientationWidgets):

    def __init__(
        self,
        children: list[FlutterWidget],
        main_axis_alignment: MainAxisAlignment = MainAxisAlignment.START,
        cross_axis_alignment: CrossAxisAlignment = CrossAxisAlignment.CENTER,
        *,
        key: GlobalKey | None = None,
    ) -> None:
        super().__init__(
            children, "column", main_axis_alignment, cross_axis_alignment, key=key
        )

    def create_element(self) -> "ColumnElement":
        return ColumnElement(self)


class ColumnElement(ListOrientationWidgetsElement):

    def __init__(self, widget: ListOrientationWidgets) -> None:
        super().__init__(widget)


# ============================================================
# TEXT FIELD
# ============================================================


class TextField(StatelessWidget):

    def __init__(
        self,
        text: str = "",
        hint: str = "",
        on_changed: Callable[[str], None] | None = None,
        width: int = 30,
        *,
        key: GlobalKey | None = None,
    ) -> None:
        super().__init__(key)

        self.text = text
        self.hint = hint
        self.on_changed = on_changed
        self.width = width

    def build(self, context: BuildContext) -> FlutterWidget:
        return self

    def create_element(self) -> Element:
        return TextFieldElement(self)


class TextFieldElement(Element[TextField, ttk.Entry]):

    def __init__(self, widget: TextField) -> None:
        super().__init__(widget)

    def get_widget_flutter(self) -> TextField:
        return self.widget_flutter

    def mount(self, context: BuildContext) -> ttk.Entry:

        super().mount(context)
        var = tk.StringVar(value=self.get_widget_flutter().text)
        entry = ttk.Entry(
            context.parent_tk_widget, textvariable=var, width=self.widget_flutter.width
        )

        if self.get_widget_flutter().on_changed:
            var.trace_add(
                "write", lambda *_: self.get_widget_flutter().on_changed(var.get())
            )

        entry.pack(fill="x")
        self.widget_tk = entry
        return entry


# ============================================================
# ICON BUTTON
# ============================================================


class IconButton(StatelessWidget):

    def __init__(
        self, text: str, on_pressed: Callable[[], None], *, key: GlobalKey | None = None
    ) -> None:
        super().__init__(key)

        self.text = text
        self.on_pressed = on_pressed

    def build(self, context: BuildContext) -> FlutterWidget:
        return self

    def create_element(self) -> Element:
        return IconButtonElement(self)


class IconButtonElement(Element[IconButton, ttk.Button]):

    def __init__(self, widget: IconButton) -> None:
        super().__init__(widget)

    def get_widget_flutter(self) -> IconButton:
        return self.widget_flutter

    def mount(self, context: BuildContext) -> ttk.Button:

        super().mount(context)
        button = ttk.Button(
            context.parent_tk_widget,
            text=self.widget_flutter.text,
            command=self.widget_flutter.on_pressed,
            width=3,
        )

        button.pack()
        self.widget_tk = button
        return button


# ============================================================
# CHECKBOX
# ============================================================


class Checkbox(StatelessWidget):

    def __init__(
        self,
        value: bool = False,
        text: str = "",
        on_changed: Callable[[bool], None] | None = None,
        *,
        key: GlobalKey | None = None,
    ) -> None:
        super().__init__(key)

        self.value = value
        self.text = text
        self.on_changed = on_changed

    def build(self, context: BuildContext) -> FlutterWidget:
        return self

    def create_element(self) -> Element:
        return CheckboxElement(self)


class CheckboxElement(Element[Checkbox, ttk.Checkbutton]):

    def __init__(self, widget: Checkbox) -> None:
        super().__init__(widget)

    def get_widget_flutter(self) -> Checkbox:
        return self.widget_flutter

    def mount(self, context: BuildContext) -> ttk.Checkbutton:
        super().mount(context)
        var = tk.BooleanVar(value=self.get_widget_flutter().value)
        checkbox = ttk.Checkbutton(
            context.parent_tk_widget, text=self.get_widget_flutter().text, variable=var
        )

        if self.get_widget_flutter().on_changed:
            checkbox.configure(
                command=lambda: self.get_widget_flutter().on_changed(var.get())
            )

        checkbox.pack(anchor="w")
        self.widget_tk = checkbox
        return checkbox


# ============================================================
# SWITCH
# ============================================================


class Switch(Checkbox):

    def __init__(
        self,
        value: bool = False,
        text: str = "",
        on_changed: Callable[[bool], None] | None = None,
        *,
        key: GlobalKey | None = None,
    ) -> None:
        super().__init__(value, text, on_changed, key=key)


# ============================================================
# IMAGE
# ============================================================


class Image(StatelessWidget):

    def __init__(self, path: str, key: GlobalKey | None = None) -> None:
        super().__init__(key)

        self.path = path

    def build(self, context: BuildContext) -> FlutterWidget:
        return self

    def create_element(self) -> Element:
        return ImageElement(self)


class ImageElement(Element[Image, ttk.Label]):

    def __init__(self, widget: Image) -> None:
        super().__init__(widget)

    def get_widget_flutter(self) -> Image:
        return self.widget_flutter

    def mount(self, context: BuildContext) -> ttk.Label:
        super().mount(context)
        image = tk.PhotoImage(file=self.get_widget_flutter().path)
        label = ttk.Label(context.parent_tk_widget, image=image)
        # label.image = image
        label.pack()
        self.widget_tk = label
        return label


# ============================================================
# ICON
# ============================================================
class Icon(Text):

    def __init__(self, text: str, key: GlobalKey | None = None) -> None:
        super().__init__(text, key)


# ============================================================
# APP BAR
# ============================================================
class AppBar(StatelessWidget):

    def __init__(
        self,
        title: str,
        actions: list[FlutterWidget] | None = None,
        height: int = 48,
        key: GlobalKey | None = None,
    ) -> None:
        super().__init__(key)

        self.title = title
        self.actions = actions or []
        self.height = height

    def build(self, context: BuildContext) -> FlutterWidget:
        return self

    def create_element(self) -> Element:
        return AppBarElement(self)


class AppBarElement(Element[AppBar, ttk.Frame]):

    def __init__(self, widget: AppBar) -> None:
        super().__init__(widget)
        self._action_elements: list[Element] = []

    def get_widget_flutter(self) -> AppBar:
        return self.widget_flutter

    def mount(self, context: BuildContext) -> ttk.Frame:
        super().mount(context)
        frame = ttk.Frame(context.parent_tk_widget)
        frame.pack(fill="x")
        title = ttk.Label(frame, text=self.get_widget_flutter().title)
        title.pack(side="left", padx=8, pady=8)

        self._action_elements = []
        for action in self.get_widget_flutter().actions:
            wrapper = ttk.Frame(frame)
            wrapper.pack(side="right")
            child = action.create_element()
            child.mount(context.create_child_context(wrapper))
            self._action_elements.append(child)

        self.widget_tk = frame
        return frame

    def unmount(self) -> None:
        for child in self._action_elements:
            child.unmount()
        self._action_elements = []
        super().unmount()


# ============================================================
# SCAFFOLD
# ============================================================


class Scaffold(StatelessWidget):

    def __init__(
        self,
        body: FlutterWidget,
        *,
        app_bar: AppBar | None = None,
        floating_action_button: FlutterWidget | None = None,
        drawer: FlutterWidget | None = None,
        bottom_navigation_bar: BottomNavigationBar | None = None,
        key: GlobalKey | None = None,
    ) -> None:
        super().__init__(key)

        self.body = body
        self.app_bar = app_bar
        self.drawer = drawer
        self.bottom_navigation_bar: BottomNavigationBar | None = bottom_navigation_bar
        self.floating_action_button = floating_action_button

    def build(self, context: BuildContext) -> FlutterWidget:
        return self

    def create_element(self) -> Element:
        return ScaffoldElement(self)


class ScaffoldElement(Element[Scaffold, ttk.Frame]):

    def __init__(self, widget: Scaffold) -> None:
        super().__init__(widget)
        self._app_bar_element = None
        self._body_element = None
        self._bottom_nav_element = None

    def update_widget(self, widget: FlutterWidget) -> None:
        super().update_widget(widget)

    def update(self, new_widget: FlutterWidget) -> None:
        super().update(new_widget)

        # old_widget = self.get_widget()
        self.widget_flutter = cast(Scaffold, new_widget)

        # Se você quiser simplificar para testar se funciona,
        # pode desmontar e remontar tudo, ou implementar a atualização dos filhos:
        if self.widget_tk is not None:
            # Força a reconstrução do conteúdo destruindo o frame antigo e criando um novo
            context = self.get_context()

            if context:
                self.unmount()
                self.mount(context)

    def get_widget_flutter(self) -> Scaffold:
        return self.widget_flutter

    def mount(self, context: BuildContext) -> ttk.Frame:
        super().mount(context)
        root_frame = ttk.Frame(context.parent_tk_widget)
        root_frame.pack(fill="both", expand=True)

        self._app_bar_element = None
        if self.get_widget_flutter().app_bar:
            self._app_bar_element = self.get_widget_flutter().app_bar.create_element()
            self._app_bar_element.mount(context.create_child_context(root_frame))

        # barra inferior primeiro (side="bottom"), senão o corpo (expand) a empurra para fora
        self._bottom_nav_element = None
        if self.get_widget_flutter().bottom_navigation_bar:
            self._bottom_nav_element = (
                self.get_widget_flutter().bottom_navigation_bar.create_element()
            )
            self._bottom_nav_element.mount(context.create_child_context(root_frame))

        body_container = ttk.Frame(root_frame)
        body_container.pack(fill="both", expand=True)

        self._body_element: Element = self.get_widget_flutter().body.create_element()
        self._body_element.mount(context.create_child_context(body_container))

        self.widget_tk = root_frame
        return root_frame

    def unmount(self) -> None:
        for element in (
            self._app_bar_element,
            self._body_element,
            self._bottom_nav_element,
        ):
            if element is not None:
                element.unmount()
        self._app_bar_element = self._body_element = self._bottom_nav_element = None
        super().unmount()


# ============================================================
# SAFE AREA
# ============================================================


class SafeArea(Padding):

    def __init__(
        self, key: GlobalKey | None = None, *, padding: int, child: FlutterWidget
    ) -> None:
        super().__init__(key, padding=padding, child=child)


# ============================================================
# DRAWER
# ============================================================


class Drawer(Container):

    def __init__(
        self,
        child: FlutterWidget | None = None,
        width: int | None = None,
        height: int | None = None,
        padding: int = 0,
        *,
        key: GlobalKey | None = None,
    ) -> None:
        super().__init__(child, width, height, padding, key=key)


# ============================================================
# BOTTOM NAVIGATION BAR
# ============================================================


class BottomNavigationBar(StatelessWidget):

    def __init__(
        self,
        items: list[str],
        on_selected: Callable[[int], None],
        *,
        current_index: int = 0,
        key: GlobalKey | None = None,
    ) -> None:
        super().__init__(key)
        self.items = items
        self.on_selected = on_selected
        self.current_index = current_index

    def build(self, context: BuildContext) -> FlutterWidget:
        return self

    def create_element(self) -> Element:
        return BottomNavigationBarElement(self)


class BottomNavigationBarElement(Element[BottomNavigationBar, ttk.Frame]):

    def __init__(self, widget: BottomNavigationBar) -> None:
        super().__init__(widget)

    def get_widget_flutter(self) -> BottomNavigationBar:
        return self.widget_flutter

    def mount(self, context: BuildContext) -> ttk.Frame:
        super().mount(context)
        w = self.get_widget_flutter()
        frame = ttk.Frame(context.parent_tk_widget)
        frame.pack(side="bottom", fill="x")  # side="bottom": nunca é cortada pelo corpo

        for index, item in enumerate(w.items):
            style = "Elevated.TButton" if index == w.current_index else "Text.TButton"
            button = ttk.Button(
                frame,
                text=item,
                style=style,
                command=lambda i=index: w.on_selected(i),
            )
            button.pack(side="left", expand=True, fill="x")

        self.widget_tk = frame
        return frame


# ============================================================
# WRAP
# ============================================================


class Wrap(Column):

    def __init__(
        self,
        children: list[FlutterWidget],
        main_axis_alignment: MainAxisAlignment = MainAxisAlignment.START,
        cross_axis_alignment: CrossAxisAlignment = CrossAxisAlignment.CENTER,
        *,
        key: GlobalKey | None = None,
    ) -> None:
        super().__init__(children, main_axis_alignment, cross_axis_alignment, key=key)


# ============================================================
# STACK
# ============================================================


class Stack(StatelessWidget):

    def __init__(
        self, children: list[FlutterWidget], *, key: GlobalKey | None = None
    ) -> None:
        super().__init__(key)

        self.children = children

    def build(self, context: BuildContext) -> FlutterWidget:
        return self

    def create_element(self) -> Element:
        return StackElement(self)


class StackElement(Element[Stack, ttk.Frame]):

    def __init__(self, widget: Stack) -> None:
        super().__init__(widget)

    def get_widget_flutter(self) -> Stack:
        return self.widget_flutter

    def mount(self, context: BuildContext) -> ttk.Frame:
        super().mount(context)
        frame = ttk.Frame(context.parent_tk_widget)
        frame.pack(fill="both", expand=True)

        for child in self.get_widget_flutter().children:
            wrapper = ttk.Frame(frame)
            wrapper.place(relx=0, rely=0, relwidth=1, relheight=1)

            inflate_widget(child, context).mount(context.create_child_context(wrapper))

        self.widget_tk = frame
        return frame


# ============================================================
# POSITIONED
# ============================================================
class Positioned(StatelessWidget):

    def __init__(
        self,
        child: FlutterWidget,
        x: int = 0,
        y: int = 0,
        *,
        key: GlobalKey | None = None,
    ) -> None:
        super().__init__(key)

        self.child = child
        self.x = x
        self.y = y

    def build(self, context: BuildContext) -> FlutterWidget:
        return self.child

    def create_element(self) -> Element:
        return inflate_widget(self.child, self.context)


# ============================================================
# VISIBILITY
# ============================================================
class Visibility(StatelessWidget):

    def __init__(self, visible: bool, child: FlutterWidget) -> None:
        super().__init__()
        self.visible = visible
        self.child = child

    def build(self, context: BuildContext) -> FlutterWidget:
        if self.visible:
            return self.child
        return SizedBox()

    def create_element(self) -> Element:
        return self.build(None).create_element()


# ============================================================
# FUTURE BUILDER
# ============================================================


class FutureBuilder(StatelessWidget):

    def __init__(
        self,
        future: Callable[[], object],
        builder: Callable[[BuildContext, object], FlutterWidget],
        *,
        key: GlobalKey | None = None,
    ) -> None:
        super().__init__(key)

        self.future = future
        self.builder = builder

    def build(self, context: BuildContext) -> FlutterWidget:
        result = self.future()
        return self.builder(context, result)

    def create_element(self) -> Element:
        return self.build(None).create_element()
