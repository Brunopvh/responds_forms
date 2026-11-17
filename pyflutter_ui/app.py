# app.py
from __future__ import annotations
from enum import Enum, auto
from tkinter import Tk
import tkinter as tk
from typing import Callable, Optional

from pyflutter_ui.ui import BuildContext, TkMaterialApp
from pyflutter_ui.theme import ThemeData, ThemeMode, ThemeProvider, ColorScheme
from pyflutter_ui.config_app import AppConfigNotifier

# ============================================================
# SNACKBAR
# ============================================================


class SnackBarType(Enum):
    INFO = auto()
    SUCCESS = auto()
    WARNING = auto()
    ERROR = auto()


class SnackBar:
    """
    Exibe uma mensagem temporária na parte inferior da janela,
    similar ao SnackBar do Flutter.

    Uso via contexto (recomendado):
        SnackBar.of(context).show("Arquivo salvo!", type=SnackBarType.SUCCESS)

    Uso direto com root Tk:
        SnackBar.show_on(root, "Erro ao carregar", type=SnackBarType.ERROR)
    """

    # cores por tipo — funcionam tanto em tema claro quanto escuro
    _COLORS = {
        SnackBarType.INFO: {"bg": "#323232", "fg": "#FFFFFF", "accent": "#90CAF9"},
        SnackBarType.SUCCESS: {"bg": "#1B5E20", "fg": "#FFFFFF", "accent": "#A5D6A7"},
        SnackBarType.WARNING: {"bg": "#E65100", "fg": "#FFFFFF", "accent": "#FFE082"},
        SnackBarType.ERROR: {"bg": "#B71C1C", "fg": "#FFFFFF", "accent": "#EF9A9A"},
    }

    _ICONS = {
        SnackBarType.INFO: "ℹ",
        SnackBarType.SUCCESS: "✓",
        SnackBarType.WARNING: "⚠",
        SnackBarType.ERROR: "✕",
    }

    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._current: Optional[tk.Toplevel] = None
        self._after_id: Optional[str] = None

    @classmethod
    def of(cls, context: BuildContext) -> SnackBar:
        """Obtém o SnackBar a partir de um BuildContext."""
        root = context.app.get_root()
        # reutiliza instância já anexada ao root
        if not hasattr(root, "_snackbar"):
            root._snackbar = cls(root)
        return root._snackbar

    @classmethod
    def show_on(
        cls,
        root: tk.Tk,
        message: str,
        *,
        type: SnackBarType = SnackBarType.INFO,
        duration: int = 3000,
        action_label: Optional[str] = None,
        on_action: Optional[Callable[[], None]] = None,
    ) -> None:
        """Atalho estático: não precisa instanciar."""
        if not hasattr(root, "_snackbar"):
            root._snackbar = cls(root)
        root._snackbar.show(
            message,
            type=type,
            duration=duration,
            action_label=action_label,
            on_action=on_action,
        )

    def show(
        self,
        message: str,
        *,
        type: SnackBarType = SnackBarType.INFO,
        duration: int = 3000,
        action_label: Optional[str] = None,
        on_action: Optional[Callable[[], None]] = None,
    ) -> None:
        """Exibe o SnackBar. Descarta o anterior se ainda estiver visível."""
        self._dismiss()

        colors = self._COLORS[type]
        icon = self._ICONS[type]

        # ── janela sem borda flutuando sobre o root ──────────
        popup = tk.Toplevel(self._root)
        popup.title("Aviso")
        popup.geometry("400x50")
        popup.overrideredirect(True)  # sem barra de título
        popup.attributes("-topmost", True)
        popup.configure(bg=colors["bg"])

        self._current = popup

        # ── frame interno com padding ─────────────────────────
        frame = tk.Frame(popup, bg=colors["bg"], padx=12, pady=10)
        frame.pack(fill="both", expand=True)

        # ícone
        tk.Label(
            frame,
            text=icon,
            bg=colors["bg"],
            fg=colors["accent"],
            font=("Helvetica", 14, "bold"),
        ).pack(side="left", padx=(0, 8))

        # mensagem
        tk.Label(
            frame,
            text=message,
            bg=colors["bg"],
            fg=colors["fg"],
            font=("Helvetica", 10),
            wraplength=360,
            justify="left",
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        # botão de ação opcional (ex.: "DESFAZER")
        if action_label and on_action:

            def _action():
                on_action()
                self._dismiss()

            tk.Button(
                frame,
                text=action_label.upper(),
                bg=colors["bg"],
                fg=colors["accent"],
                font=("Helvetica", 9, "bold"),
                relief="flat",
                cursor="hand2",
                bd=0,
                highlightthickness=0,
                command=_action,
            ).pack(side="right", padx=(12, 0))

        # botão X para fechar manualmente
        tk.Button(
            frame,
            text="✕",
            bg=colors["bg"],
            fg=colors["fg"],
            font=("Helvetica", 8),
            relief="flat",
            cursor="hand2",
            bd=0,
            highlightthickness=0,
            command=self._dismiss,
        ).pack(side="right", padx=(8, 0))

        # ── posicionamento: canto inferior esquerdo do root ──
        popup.update_idletasks()
        self._reposition(popup)

        # reposiciona se o root for movido ou redimensionado
        self._root.bind("<Configure>", lambda e: self._reposition(popup), add="+")

        # ── animação de entrada (slide up) ───────────────────
        self._animate_in(popup)

        # ── auto-dismiss ──────────────────────────────────────
        if duration > 0:
            self._after_id = self._root.after(duration, self._dismiss)

    def _reposition(self, popup: tk.Toplevel) -> None:
        if popup is None or not popup.winfo_exists():
            return

        root = self._root
        rx = root.winfo_x()
        ry = root.winfo_y()
        rw = root.winfo_width()
        rh = root.winfo_height()

        pw = popup.winfo_width()
        ph = popup.winfo_height()

        margin = 16
        x = rx + margin
        y = ry + rh - ph - margin

        popup.geometry(f"+{x}+{y}")

    def _animate_in(self, popup: tk.Toplevel, steps: int = 8) -> None:
        """Desliza o popup de baixo para cima em `steps` passos."""
        if not popup.winfo_exists():
            return

        root = self._root
        rh = root.winfo_height()
        ry = root.winfo_y()
        ph = popup.winfo_reqheight()
        margin = 16

        target_y = ry + rh - ph - margin
        start_y = ry + rh  # começa fora da janela

        def _step(current_y: int, step: int) -> None:
            if not popup.winfo_exists():
                return
            if step >= steps:
                popup.geometry(f"+{popup.winfo_x()}+{target_y}")
                return
            new_y = current_y + (target_y - current_y) // 2
            popup.geometry(f"+{popup.winfo_x()}+{new_y}")
            popup.after(16, lambda: _step(new_y, step + 1))

        popup.geometry(f"+{popup.winfo_x()}+{start_y}")
        _step(start_y, 0)

    def _dismiss(self) -> None:
        if self._after_id:
            self._root.after_cancel(self._after_id)
            self._after_id = None

        if self._current and self._current.winfo_exists():
            self._animate_out(self._current)
        self._current = None

    def _animate_out(self, popup: tk.Toplevel, steps: int = 6) -> None:
        """Desliza o popup para baixo antes de destruir."""
        if not popup.winfo_exists():
            return

        root = self._root
        rh = root.winfo_height()
        ry = root.winfo_y()
        target = ry + rh + 10  # fora da janela

        def _step(current_y: int, step: int) -> None:
            if not popup.winfo_exists():
                return
            if step >= steps:
                popup.destroy()
                return
            new_y = current_y + (target - current_y) // 2 + 2
            popup.geometry(f"+{popup.winfo_x()}+{new_y}")
            popup.after(16, lambda: _step(new_y, step + 1))

        _step(popup.winfo_y(), 0)


def create_theme_provider(mode: ThemeMode = ThemeMode.DARK) -> ThemeProvider:

    return ThemeProvider(
        light_theme=ThemeData.light(color_scheme=ColorScheme.light()),
        dark_theme=ThemeData.dark(color_scheme=ColorScheme.dark()),
        mode=mode,
    )


def include_theme_app(app: TkMaterialApp) -> TkMaterialApp:

    if app._root is None:
        app._root = Tk()

    try:
        notifier: ThemeProvider = app.read_state(ThemeProvider)
        notifier.attach_root(app.get_root())
    except KeyError as e:
        print(f"ThemeProvider não registrado: {e}")

    # NÃO fazer push(app.home) aqui: TkMaterialApp.run() já faz.
    return app


def run_app(app: TkMaterialApp) -> None:
    mode = ThemeMode.DARK
    try:
        mode = app.read_state(AppConfigNotifier).value.theme_mode
    except KeyError:
        pass  # config não registrado: usa o padrão

    app.register_notifier(create_theme_provider(mode))
    include_theme_app(app).run()
