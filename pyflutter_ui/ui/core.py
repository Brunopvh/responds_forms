# core.py
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from abc import ABC, abstractmethod, ABCMeta
from typing import Any, Callable, Optional, cast, Union

tkWidgetType = Union[tk.Widget, tk.Tk]


def widget_exists(w: tkWidgetType, *, destroy: bool = False) -> bool:
    e = w.winfo_exists()
    if destroy:
        w.destroy()
    return e


class GlobalKey(object):

    def __init__(self) -> None:
        super().__init__()
        self.element: Element | None = None


class Disposable(ABC):

    def __init__(self):
        super().__init__()

    @abstractmethod
    def dispose(self) -> None:
        pass


# ============================================================
# STATE - CHANGE NOTIFIER
# ============================================================
class ChangeNotifier(object):

    def __init__(self) -> None:
        super().__init__()
        self._listeners: list[Callable[[], None]] = []

    def add_listener(self, listener: Callable[[], None]) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[], None]) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def notify_listeners(self) -> None:
        for listener in self._listeners.copy():
            if listener not in self._listeners:
                continue  # foi removido durante este mesmo ciclo — não chamar

            listener()


class ValueNotifier[T](ChangeNotifier):

    def __init__(self, value: T) -> None:
        super().__init__()
        self._value: T = value

    @property
    def value(self) -> T:
        return self._value

    @value.setter
    def value(self, value: T) -> None:
        self._value = value
        self.notify_listeners()

    def get_value(self) -> T:
        return self._value

    def set_value(self, v: T):
        self._value = v
        self.notify_listeners()


class CommandNotifier[T](ValueNotifier):

    def __init__(
        self,
        command: Callable,
        *,
        on_init: Callable = None,
        on_finish: Callable = None,
        on_error: Callable[[Any | None], None] = None,
        value: T = None,
    ) -> None:
        super().__init__(value)

        self.command: Callable = command
        self.on_init: Callable = on_init
        self.on_finish: Callable = on_finish
        self.on_error: Callable[[Any | None], None] = on_error
        self._value: Any = None
        self.running: bool = False

    def action_error(self, value: Any | None = None) -> None:
        if self.on_error is not None:
            self.on_error(value)

    def action_init(self):
        self.running = True
        self.notify_listeners()
        if self.on_init is not None:
            self.on_init()

    def action_finish(self):
        if self.on_finish is not None:
            self.on_finish()

    def execute(self, *args, **kwargs) -> None:
        try:
            self.action_init()
            self._value = self.command(*args, **kwargs)
        except Exception as e:
            self.action_error(e)
        else:
            self.action_finish()
        finally:
            self.running = False
            self.notify_listeners()


# ============================================================
# CONTEXT
# ============================================================
class BuildContext(object):

    def __init__(
        self,
        app: BaseMaterialApp,
        *,
        parent_widget: tk.Widget,
        parent_context: Optional["BuildContext"] = None,
        element: Optional[Element] = None,
    ) -> None:
        self.app: BaseMaterialApp = app
        self.parent_tk_widget: tk.Widget = parent_widget
        self.parent_context: Optional[BuildContext] = parent_context
        self.element: Optional[Element] = element
        self.name: str = None

    @property
    def navigator(self) -> Navigator:
        return self.app.get_navigator()

    @property
    def theme(self) -> Any:
        return self.app.theme

    def create_child_context(
        self, parent_widget: tk.Widget, element: Optional[Element] = None
    ) -> BuildContext:
        return BuildContext(
            app=self.app,
            parent_widget=parent_widget,
            parent_context=self,
            element=element,
        )

    def read(self, provider_type: type) -> T:
        return self.app.read_state(provider_type)

    def watch(self, provider_type: type[T]) -> T:
        if not isinstance(self.element, StatefulElement):
            raise RuntimeError("watch() só pode ser usado dentro de StatefulWidget")

        provider: T = self.read(provider_type)
        if self.element is not None and isinstance(provider, ChangeNotifier):
            self.element.watch_provider(provider)
        return provider


# ============================================================
# ELEMENT E WIDGET
# ============================================================


class FlutterWidget[E: Element](metaclass=ABCMeta):

    def __init__(self, key: GlobalKey | None = None) -> None:
        self.key: GlobalKey | None = key
        self.context: BuildContext = None

    @abstractmethod
    def create_element(self) -> E:
        pass

    @abstractmethod
    def build(self, context: BuildContext) -> FlutterWidget:
        pass


class Element[F: FlutterWidget, T: tkWidgetType]:

    def __init__(self, widget: F) -> None:

        self.widget_flutter: F = widget
        self.render_object = RenderObject()
        self._watched_providers: list[ChangeNotifier] = []

        self.widget_tk: T = None
        self._parent_context: BuildContext | None = None
        self._child_element: Element | None = None

        if widget.key is not None:
            widget.key.element = self

    @property
    def layout_data(self) -> LayoutData:
        return self.render_object.layout_data

    def get_widget_flutter(self) -> FlutterWidget:
        return self.widget_flutter

    def get_widget_tk(self) -> T:
        return self.widget_tk

    def reattach(self, context: BuildContext) -> None:
        old_parent = (
            self._parent_context.parent_tk_widget
            if self._parent_context is not None
            else None
        )
        new_parent = context.parent_tk_widget

        self._parent_context = context
        self.widget_flutter.context = context

        if old_parent is not None and old_parent != new_parent:
            self.remount(context)

    def remount(self, context: BuildContext) -> None:
        pass

    def get_context(self) -> BuildContext | None:
        return self.get_widget_flutter().context

    def watch_provider(self, provider: ChangeNotifier) -> None:
        pass

    def mount(self, context: BuildContext) -> T:
        self.widget_flutter.context = context

        if not context.parent_tk_widget.winfo_exists():
            print(
                f"{__class__.__name__} [ABORTANDO MONTAGEM] .. parent_widget não existe!!!"
            )
            return None  # pai já destruído, aborta silenciosamente em vez de TclError

        return self.get_widget_tk()

    def update(self, new_widget: F) -> None:
        old_context = self.widget_flutter.context
        new_widget.context = old_context
        self.widget_flutter = new_widget

    def update_widget(self, widget: F) -> None:
        widget.context = self.widget_flutter.context
        self.widget_flutter = widget

    def unmount(self) -> None:
        if self.widget_tk is not None:
            try:
                widget_exists(self.get_widget_tk(), destroy=True)
            except Exception:
                pass
            self.widget_tk = None


def inflate_widget(
    widget: FlutterWidget, context: BuildContext | None = None
) -> Element:

    if widget.key is not None:
        old_element = widget.key.element

        if old_element is not None:
            if context is not None:
                old_element.reattach(context)
                # old_element.update_widget(widget)
                old_element.update(widget)
            return old_element

    return widget.create_element()


# ============================================================
# STATELESS
# ============================================================
class StatelessWidget[E: StatelessElement](FlutterWidget[E]):

    def __init__(self, key: GlobalKey | None = None) -> None:
        super().__init__(key)

    def build(self, context: BuildContext) -> FlutterWidget:
        raise NotImplementedError()

    def create_element(self) -> E:
        return StatelessElement(self)


class StatelessElement[F: StatelessWidget, T: tkWidgetType](Element):

    def __init__(self, widget: StatelessWidget) -> None:
        super().__init__(widget)
        self.child_element: Element | None = None
        self.widget_flutter: StatelessWidget = widget

    def reattach(self, context: BuildContext) -> None:
        super().reattach(context)

        if self.child_element is not None:

            child_context = BuildContext(
                app=context.app,
                parent_widget=context.parent_tk_widget,
                parent_context=context,
                element=self.child_element,
            )

            self.child_element.reattach(child_context)

    def mount(self, context: BuildContext) -> T:
        super().mount(context)
        self._parent_context = context
        child = self.get_widget_flutter().build(context)

        self.child_element = inflate_widget(child, context)
        self.widget_tk = self.child_element.mount(context)
        return self.widget_tk

    def remount(self, context: BuildContext) -> None:
        if self.child_element is not None:
            self.child_element.unmount()

        self.mount(context)

    def update(self, new_widget: StatelessWidget) -> None:
        super().update(new_widget)

        self.widget_flutter = new_widget
        if self.child_element is None:
            return

        _context = self.get_context()
        if _context is None:
            return

        new_child = self.get_widget_flutter().build(_context)

        if type(new_child) is type(self.child_element.widget_flutter):
            self.child_element.update(new_child)
        else:
            self.child_element.unmount()
            self.child_element = inflate_widget(new_child)
            self.widget_tk = self.child_element.mount(_context)

    def update_widget(self, widget: FlutterWidget) -> None:
        super().update_widget(widget)

    def unmount(self) -> None:
        if self.child_element is not None:
            self.child_element.unmount()
            self.child_element = None
        self.widget_tk = None


class InheritedWidget(StatelessWidget):

    def __init__(self, child: FlutterWidget, *, key: GlobalKey | None = None) -> None:
        super().__init__(key)
        self.child = child

    def build(self, context: BuildContext) -> FlutterWidget:
        return self.child


# ============================================================
# STATE
# ============================================================


class State[F: StatefulWidget](metaclass=ABCMeta):

    def __init__(self) -> None:
        self.context: BuildContext = None
        self._element: StatefulElement = None

    @property
    def widget(self) -> F:
        if self._element is None:
            raise ValueError(
                f"{__class__.__name__}(): self._element não foi definido..."
            )

        return self._element.get_widget_flutter()

    def set_element(self, e: StatefulElement):
        self._element = e

    def init_state(self) -> None:
        pass

    def dispose(self) -> None:
        pass

    def did_update(self) -> None:
        pass

    def set_state(self, callback: Callable[[], None]) -> None:
        callback()
        if self._element:
            self._element.rebuild()

    @abstractmethod
    def build(self, context: BuildContext) -> FlutterWidget:
        pass


class ConsumerState[V](State):
    def __init__(self) -> None:
        super().__init__()

    @property
    def widget(self) -> ValueListenableBuilder:
        return cast(ValueListenableBuilder, super().widget)

    @property
    def provider(self) -> V:
        if self.context is None:
            raise RuntimeError(f"{__class__.__name__}(): self.context é nulo.")

        return self.context.read(self.provider_type())

    @abstractmethod
    def provider_type(self) -> type[V]:
        pass


# ============================================================
# STATEFUL
# ============================================================
class StatefulWidget[E: StatefulElement](FlutterWidget, metaclass=ABCMeta):

    def __init__(self, key: GlobalKey | None = None) -> None:
        super().__init__(key)

    @abstractmethod
    def create_state(self) -> State:
        pass

    def create_element(self) -> StatefulElement:
        return StatefulElement(self)


class StatefulElement[F: StatefulWidget, T: tkWidgetType](Element[F, T]):

    def __init__(self, widget: F) -> None:
        super().__init__(widget)
        self.state: State = widget.create_state()
        self.state.set_element(self)

        self.child_element: Element | None = None
        self._initialized = False

    def reattach(self, context: BuildContext) -> None:
        super().reattach(context)

        state_context = BuildContext(
            app=context.app,
            parent_widget=context.parent_tk_widget,
            parent_context=context,
            element=self,
        )

        self.state.context = state_context
        self.widget_flutter.context = state_context

        if self.child_element is not None:
            self.child_element.reattach(state_context)

    def mount(self, context: BuildContext) -> T:

        super().mount(context)

        self._parent_context = context

        self.state.context = BuildContext(
            app=context.app,
            parent_widget=context.parent_tk_widget,
            parent_context=context,
            element=self,
        )

        self.get_widget_flutter().context = self.state.context

        if not self._initialized:
            self.state.init_state()
            self._initialized = True

        child = self.state.build(self.state.context)

        if self.child_element is None:
            self.child_element = inflate_widget(child, self.state.context)
            self.widget_tk = self.child_element.mount(self.state.context)
        return self.widget_tk

    def remount(self, context: BuildContext) -> None:
        old_child = self.child_element
        if old_child is not None:
            old_child.unmount()

        self.child_element = None
        self.widget_tk = None
        self.mount(context)

    def rebuild(self) -> None:
        # _parent_context é o contexto recebido em mount() — seu parent_tk_widget
        # é o frame pai original, que continua vivo entre rebuilds.
        # state.context pode apontar para um frame filho destruído pelo
        # unmount() anterior do ColumnElement, por isso reconstrói o contexto aqui.
        if self._parent_context is None:
            return

        # Garante que parent_tk_widget é sempre o frame pai vivo, não o filho destruído.
        self.state.context = BuildContext(
            app=self._parent_context.app,
            parent_widget=self._parent_context.parent_tk_widget,
            parent_context=self._parent_context,
            element=self,
        )
        self.widget_flutter.context = self.state.context

        context = self.state.context
        new_child = self.state.build(context)

        if self.child_element is not None and type(new_child) is type(
            self.child_element.widget_flutter
        ):
            self.child_element.update(new_child)
            return

        if self.child_element is not None:
            self.child_element.unmount()

        self.child_element = inflate_widget(new_child)
        self.widget_tk = self.child_element.mount(context)

    def unmount(self) -> None:

        if self.child_element is not None:
            self.child_element.unmount()
            self.child_element = None

        try:
            self.state.dispose()
        finally:
            self.state.context = None
            self.state._element = None
        super().unmount()

    def update(self, new_widget: FlutterWidget) -> None:
        super().update(new_widget)

    def update_widget(self, widget: FlutterWidget) -> None:
        super().update_widget(widget)


class ValueListenableBuilder[V](StatefulWidget):

    def __init__(
        self,
        notifier: ValueNotifier[V],
        builder: Callable[[BuildContext, V], FlutterWidget[StatefulElement]],
        *,
        key: GlobalKey | None = None,
    ) -> None:
        super().__init__(key)

        self.notifier: ValueNotifier[V] = notifier
        self.builder: Callable[[BuildContext, V], FlutterWidget[StatefulElement]] = (
            builder
        )

    def build(self, context: BuildContext) -> FlutterWidget:
        return super().build(context)

    def create_state(self) -> State:
        return _ValueListenableBuilderState()


class _ValueListenableBuilderState(State[ValueListenableBuilder]):

    def __init__(self) -> None:
        super().__init__()

    def init_state(self) -> None:
        widget: ValueListenableBuilder = self._element.get_widget_flutter()
        widget.notifier.add_listener(self._listener)

    def dispose(self) -> None:
        widget: ValueListenableBuilder = cast(
            ValueListenableBuilder, self._element.widget_flutter
        )
        widget.notifier.remove_listener(self._listener)

    def _listener(self) -> None:
        self.set_state(lambda: None)

    def build(self, context: BuildContext) -> FlutterWidget:
        widget: ValueListenableBuilder = self._element.get_widget_flutter()
        return widget.builder(context, widget.notifier.value)


# ============================================================
# PROVIDER
# ============================================================
class MapState[K, T]:

    _instance: "MapState | None" = None

    def __new__(cls, *args, **kwargs) -> "MapState":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not hasattr(self, "values"):
            self.values: dict = dict()

    def __setitem__(self, key, value):
        self.values[key] = value

    def __getitem__(self, key):
        return self.values[key]

    def contains_key(self, key) -> bool:
        for k in self.values.keys():
            if k == key:
                return True
        return False

    def add(self, value: T):
        _type_value = type(value)
        if not self.contains_key(_type_value):
            self.values[_type_value] = value

    def read[T](self, key: type[T]) -> T:
        return self.values[key]


class Provider(object):

    _states: MapState = MapState()
    _instance: "Provider | None" = None

    def __new__(cls) -> "Provider":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        pass

    @classmethod
    def add_state(cls, notifier: T) -> None:
        # print(f"DEBUG: Estado adicionado ... {notifier}")
        cls._states.add(notifier)

    @classmethod
    def read[T](cls, type_notifier: type[T]) -> T:
        return cls._states.read(type_notifier)


class Consumer[V](StatefulWidget):

    def __init__(
        self,
        provider_type: type[V],
        builder: Callable[[BuildContext, Any], FlutterWidget],
        *,
        key: GlobalKey | None = None,
    ) -> None:
        super().__init__(key)

        self.provider_type: type[V] = provider_type
        self.builder: Callable[[BuildContext, Any], FlutterWidget] = builder

    def build(self, context: BuildContext) -> FlutterWidget:
        provider = context.read(self.provider_type)
        return self.builder(context, provider)

    def create_state(self) -> State:
        return _ConsumerState()

    def create_element(self) -> ConsumerElement:
        return ConsumerElement(self)


class _ConsumerState(State):

    def __init__(self) -> None:
        super().__init__()

    def build(self, context: BuildContext) -> FlutterWidget:
        widget: Consumer = cast(Consumer, self.widget)
        provider = context.watch(widget.provider_type)
        return widget.builder(context, provider)


class ConsumerElement(StatefulElement):

    def __init__(self, widget: Consumer) -> None:
        super().__init__(widget)
        self._providers: list[ChangeNotifier] = []

    def watch_provider(self, provider: ChangeNotifier) -> None:

        if provider in self._providers:
            return

        provider.add_listener(self._listener)
        self._providers.append(provider)

    def _listener_fixed(self) -> None:
        try:
            self.rebuild()
        except Exception:
            import traceback

            traceback.print_exc()

    def _listener(self) -> None:
        self.rebuild()
        # self._listener_fixed()

    def unmount(self) -> None:
        for provider in self._providers:
            provider.remove_listener(self._listener)
        self._providers.clear()
        super().unmount()


# ============================================================
# APP
# ============================================================


class PageApp[E: PageElement](StatelessWidget):

    def __init__(
        self, key: GlobalKey | None = None, *, name: str | None = None
    ) -> None:
        super().__init__(key)
        self.name: str = name or "My Page"

    def create_element(self) -> PageElement:
        return PageElement(self)

    def build(self, context: BuildContext) -> FlutterWidget:
        raise NotImplementedError()


class PageElement[F: PageApp, T: ttk.Frame](StatelessElement[F, T]):

    def __init__(self, widget: PageApp) -> None:
        super().__init__(widget)

    def get_widget_flutter(self) -> PageApp:
        return self.widget_flutter

    def get_widget_tk(self) -> ttk.Frame:
        return super().get_widget_tk()


class BaseMaterialApp(ABC):

    def __init__(self, home: PageApp, theme: Any = None) -> None:
        super().__init__()
        self.home: PageApp = home
        self.theme: Any = theme
        self._root: tk.Tk = None
        self.provider: Provider = Provider()

    @property
    def root(self) -> tk.Tk | None:
        return self._root

    @root.setter
    def root(self, r: tk.Tk):
        self.set_root(r)

    def get_root(self) -> tk.Tk:
        if self._root is None:
            raise ValueError(f"Root (tk.Tk) is None")
        return self._root

    def set_root(self, rt: tk.Tk) -> None:
        self._root = rt
        self._root.title(self.home.name)

    @abstractmethod
    def get_navigator(self) -> Navigator:
        pass

    def register_notifier[T](self, notifier: T) -> None:
        self.provider.add_state(notifier)

    def read_state[T](self, type_notifier: type[T]) -> T:
        return self.provider.read(type_notifier)

    def run(self) -> None:
        pass


class Navigator(object):

    def __init__(self, app: BaseMaterialApp) -> None:
        super().__init__()
        self.stack: list[PageElement] = list[PageElement]()
        self.app: BaseMaterialApp = app
        self.current_element = None

    def push(self, page: PageApp) -> None:
        pass

    def pop(self) -> None:
        pass

    def replace(self, page: PageApp) -> None:
        pass

    def render(self) -> None:
        pass


# ============================================================
# LAYOUT DATA
# ============================================================
class LayoutData(object):

    def __init__(
        self,
        flex: int = 0,
        expand: bool = False,
        fill_x: bool = False,
        fill_y: bool = False,
    ) -> None:
        super().__init__()
        self.flex: int = flex
        self.expand: bool = expand
        self.fill_x: bool = fill_x
        self.fill_y: bool = fill_y


# ============================================================
# RENDER OBJECT
# ============================================================


class RenderObject(object):

    def __init__(self) -> None:
        super().__init__()
        self.layout_data: LayoutData = LayoutData()
        self.parent: RenderObject | None = None
        self.children: list[RenderObject] = list()
        self.tk_widget: tk.Widget | None = None

    def add_child(self, child: "RenderObject") -> None:
        child.parent = self
        self.children.append(child)

    def remove_child(self, child: RenderObject) -> None:
        if child in self.children:
            self.children.remove(child)
            child.parent = None

    def attach_widget(self, widget: tk.Widget) -> None:
        self.tk_widget = widget

    def apply_layout(self) -> None:
        pass
