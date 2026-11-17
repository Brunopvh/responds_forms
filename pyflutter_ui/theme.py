# theme.py
"""
Sistema de temas para pyflutter — inspirado na ThemeData do Flutter.

Funcionalidades:
  - ThemeMode: light | dark | system  (detecta o SO automaticamente)
  - ColorScheme: paleta completa com primary, secondary, surface, error, etc.
  - TextTheme: estilos tipográficos (displayLarge → labelSmall)
  - ButtonThemeData: estilo para ElevatedButton, OutlinedButton, TextButton
  - ThemeData: objeto raiz que agrega tudo e aplica no ttk.Style
  - ThemeProvider(ChangeNotifier): permite trocar o tema em runtime

Uso básico:
    from pyflutter.theme import ThemeData, ThemeMode, ThemeProvider

    provider = ThemeProvider(ThemeData.light())
    app.register_provider(provider)

    # Para mudar o tema em runtime:
    provider.set_mode(ThemeMode.DARK)
"""

from __future__ import annotations
import sys
import tkinter as tk
from dataclasses import dataclass, field
from enum import Enum
from tkinter import ttk
from typing import Optional, TypeVar

from pyflutter_ui.ui.core import ChangeNotifier, BaseMaterialApp, Navigator
from pyflutter_ui.system_theme import SystemThemeDetector

T = TypeVar("T")

# ============================================================
# THEME MODE
# ============================================================


class ThemeMode(Enum):
    """
    Equivalente ao ThemeMode do Flutter.
    SYSTEM detecta a preferência do sistema operacional.
    """

    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


def _detect_system_dark_mode() -> bool:
    """
    Tenta detectar se o SO está em modo escuro.
    Suporta Windows, macOS e Linux (via tk).
    Retorna True se dark mode estiver ativo.
    """
    return SystemThemeDetector.create().is_dark()


# ============================================================
# COLOR SCHEME
# ============================================================


@dataclass
class ColorScheme:
    """
    Paleta de cores completa, espelhando o ColorScheme do Flutter (Material 3).

    Convenção:
      - `primary`         : cor principal da marca
      - `on_primary`      : texto/ícone sobre primary
      - `primary_container`   : variante de fundo para primary
      - `on_primary_container` : texto sobre primary_container
      - `secondary`       : cor de destaque secundária
      - `on_secondary`    : texto sobre secondary
      - `secondary_container`
      - `on_secondary_container`
      - `tertiary` / `on_tertiary` / `tertiary_container` / `on_tertiary_container`
      - `error` / `on_error` / `error_container` / `on_error_container`
      - `surface`         : fundo dos cards/dialogs
      - `on_surface`      : texto sobre surface
      - `surface_variant` : variante de surface
      - `on_surface_variant`
      - `background`      : cor de fundo da janela
      - `on_background`   : texto sobre background
      - `outline`         : bordas e divisores
      - `shadow`          : cor de sombra
      - `inverse_surface` / `on_inverse_surface` / `inverse_primary`
      - `scrim`           : overlay semi-transparente (Drawer, Modal)
    """

    # ── Primary ──────────────────────────────────────────────
    primary: str = "#6750A4"
    on_primary: str = "#FFFFFF"
    primary_container: str = "#EADDFF"
    on_primary_container: str = "#21005D"

    # ── Secondary ────────────────────────────────────────────
    secondary: str = "#625B71"
    on_secondary: str = "#FFFFFF"
    secondary_container: str = "#E8DEF8"
    on_secondary_container: str = "#1D192B"

    # ── Tertiary ─────────────────────────────────────────────
    tertiary: str = "#7D5260"
    on_tertiary: str = "#FFFFFF"
    tertiary_container: str = "#FFD8E4"
    on_tertiary_container: str = "#31111D"

    # ── Error ────────────────────────────────────────────────
    error: str = "#B3261E"
    on_error: str = "#FFFFFF"
    error_container: str = "#F9DEDC"
    on_error_container: str = "#410E0B"

    # ── Surface / Background ─────────────────────────────────
    surface: str = "#FFFBFE"
    on_surface: str = "#1C1B1F"
    surface_variant: str = "#E7E0EC"
    on_surface_variant: str = "#49454F"

    background: str = "#FFFBFE"
    on_background: str = "#1C1B1F"

    # ── Utilities ────────────────────────────────────────────
    outline: str = "#79747E"
    outline_variant: str = "#CAC4D0"
    shadow: str = "#000000"
    scrim: str = "#000000"

    # ── Inverse ──────────────────────────────────────────────
    inverse_surface: str = "#313033"
    on_inverse_surface: str = "#F4EFF4"
    inverse_primary: str = "#D0BCFF"

    @classmethod
    def light(cls) -> "ColorScheme":
        """Paleta Material 3 Light padrão."""
        return cls()

    @classmethod
    def dark(cls) -> "ColorScheme":
        """Paleta Material 3 Dark padrão."""
        return cls(
            primary="#D0BCFF",
            on_primary="#381E72",
            primary_container="#4F378B",
            on_primary_container="#EADDFF",
            secondary="#CCC2DC",
            on_secondary="#332D41",
            secondary_container="#4A4458",
            on_secondary_container="#E8DEF8",
            tertiary="#EFB8C8",
            on_tertiary="#492532",
            tertiary_container="#633B48",
            on_tertiary_container="#FFD8E4",
            error="#F2B8B5",
            on_error="#601410",
            error_container="#8C1D18",
            on_error_container="#F9DEDC",
            surface="#1C1B1F",
            on_surface="#E6E1E5",
            surface_variant="#49454F",
            on_surface_variant="#CAC4D0",
            background="#1C1B1F",
            on_background="#E6E1E5",
            outline="#938F99",
            outline_variant="#49454F",
            shadow="#000000",
            scrim="#000000",
            inverse_surface="#E6E1E5",
            on_inverse_surface="#313033",
            inverse_primary="#6750A4",
        )


# ============================================================
# TEXT STYLE & TEXT THEME
# ============================================================


@dataclass
class TextStyle:
    """
    Estilo tipográfico individual.
    Mapeia para os parâmetros de fonte do ttk.Label / tk.font.Font.
    """

    font_family: str = "Helvetica"
    font_size: int = 10
    font_weight: str = "normal"  # "normal" | "bold"
    font_slant: str = "roman"  # "roman"  | "italic"
    color: Optional[str] = None  # None = herda do ColorScheme

    def to_tk_font(self) -> tuple:
        """Retorna tupla compatível com o parâmetro `font=` do Tk."""
        style = []
        if self.font_weight == "bold":
            style.append("bold")
        if self.font_slant == "italic":
            style.append("italic")
        return (self.font_family, self.font_size) + (tuple(style) if style else ())


@dataclass
class TextTheme:
    """
    Hierarquia tipográfica completa — espelha o TextTheme do Flutter (Material 3).

    Display  → headings grandes (splash screens, hero)
    Headline → títulos de seção
    Title    → AppBar, dialogs
    Body     → texto corrido
    Label    → botões, captions, chips
    """

    display_large: TextStyle = field(
        default_factory=lambda: TextStyle(font_size=57, font_weight="normal")
    )
    display_medium: TextStyle = field(
        default_factory=lambda: TextStyle(font_size=45, font_weight="normal")
    )
    display_small: TextStyle = field(
        default_factory=lambda: TextStyle(font_size=36, font_weight="normal")
    )

    headline_large: TextStyle = field(
        default_factory=lambda: TextStyle(font_size=32, font_weight="normal")
    )
    headline_medium: TextStyle = field(
        default_factory=lambda: TextStyle(font_size=28, font_weight="normal")
    )
    headline_small: TextStyle = field(
        default_factory=lambda: TextStyle(font_size=24, font_weight="normal")
    )

    title_large: TextStyle = field(
        default_factory=lambda: TextStyle(font_size=22, font_weight="normal")
    )
    title_medium: TextStyle = field(
        default_factory=lambda: TextStyle(font_size=14, font_weight="bold")
    )
    title_small: TextStyle = field(
        default_factory=lambda: TextStyle(font_size=11, font_weight="bold")
    )

    body_large: TextStyle = field(
        default_factory=lambda: TextStyle(font_size=16, font_weight="normal")
    )
    body_medium: TextStyle = field(
        default_factory=lambda: TextStyle(font_size=14, font_weight="normal")
    )
    body_small: TextStyle = field(
        default_factory=lambda: TextStyle(font_size=11, font_weight="normal")
    )

    label_large: TextStyle = field(
        default_factory=lambda: TextStyle(font_size=14, font_weight="bold")
    )
    label_medium: TextStyle = field(
        default_factory=lambda: TextStyle(font_size=12, font_weight="bold")
    )
    label_small: TextStyle = field(
        default_factory=lambda: TextStyle(font_size=10, font_weight="bold")
    )


# ============================================================
# BUTTON THEME DATA
# ============================================================


@dataclass
class ButtonThemeData:
    """
    Configuração visual dos botões.
    Espelha ElevatedButtonThemeData / OutlinedButtonThemeData / TextButtonThemeData.
    """

    # Padding interno (px)
    padding_x: int = 16
    padding_y: int = 8

    # Raio da borda (aproximado via relief no Tk)
    border_radius: int = 12

    # Altura mínima (px)
    min_height: int = 20

    # Estilos para cada variante
    elevated_relief: str = "raised"
    outlined_relief: str = "groove"
    text_relief: str = "flat"


# ============================================================
# INPUT DECORATION THEME
# ============================================================


@dataclass
class InputDecorationTheme:
    """
    Estilo dos campos de texto (TextField).
    """

    border_color: Optional[str] = None  # None = usa outline do ColorScheme
    focused_border_color: Optional[str] = None  # None = usa primary
    label_color: Optional[str] = None
    hint_color: Optional[str] = None
    fill_color: Optional[str] = None  # None = usa surface_variant
    filled: bool = True
    border_width: int = 1
    padding_x: int = 12
    padding_y: int = 8


# ============================================================
# APP BAR THEME
# ============================================================


@dataclass
class AppBarTheme:
    """
    Estilo da AppBar.
    """

    background_color: Optional[str] = None  # None = usa surface do ColorScheme
    foreground_color: Optional[str] = None  # None = usa on_surface
    elevation: int = 0
    center_title: bool = False
    title_text_style: Optional[TextStyle] = None


# ============================================================
# CARD THEME
# ============================================================


@dataclass
class CardTheme:
    """
    Estilo dos Cards.
    """

    color: Optional[str] = None  # None = usa surface
    shadow_color: Optional[str] = None  # None = usa shadow
    elevation: int = 1
    margin: int = 4


# ============================================================
# DIVIDER THEME
# ============================================================


@dataclass
class DividerTheme:
    color: Optional[str] = None  # None = usa outline_variant
    thickness: int = 1
    indent: int = 0
    end_indent: int = 0


# ============================================================
# THEME DATA
# ============================================================


class ThemeData:
    """
    Objeto raiz do tema — equivalente ao ThemeData do Flutter.

    Agrega ColorScheme, TextTheme, ButtonThemeData e sub-temas,
    e aplica tudo no ttk.Style quando `apply()` é chamado.

    Exemplo:
        theme = ThemeData.light()
        theme.apply(root)
    """

    def __init__(
        self,
        color_scheme: ColorScheme,
        text_theme: Optional[TextTheme] = None,
        button_theme: Optional[ButtonThemeData] = None,
        input_decoration_theme: Optional[InputDecorationTheme] = None,
        app_bar_theme: Optional[AppBarTheme] = None,
        card_theme: Optional[CardTheme] = None,
        divider_theme: Optional[DividerTheme] = None,
        font_family: str = "Helvetica",
    ) -> None:
        self.color_scheme = color_scheme
        self.text_theme = text_theme or TextTheme()
        self.button_theme = button_theme or ButtonThemeData()
        self.input_decoration_theme = input_decoration_theme or InputDecorationTheme()
        self.app_bar_theme = app_bar_theme or AppBarTheme()
        self.card_theme = card_theme or CardTheme()
        self.divider_theme = divider_theme or DividerTheme()
        self.font_family = font_family

        # Propaga font_family padrão para todos os TextStyle sem família definida
        self._propagate_font_family()

    def _propagate_font_family(self) -> None:
        for attr in vars(self.text_theme).values():
            if isinstance(attr, TextStyle) and attr.font_family == "Helvetica":
                attr.font_family = self.font_family

    # ── Factory ──────────────────────────────────────────────

    @classmethod
    def light(
        cls,
        color_scheme: Optional[ColorScheme] = None,
        font_family: str = "Helvetica",
        **kwargs,
    ) -> "ThemeData":
        """Cria um ThemeData com paleta Light."""
        return cls(
            color_scheme=color_scheme or ColorScheme.light(),
            font_family=font_family,
            **kwargs,
        )

    @classmethod
    def dark(
        cls,
        color_scheme: Optional[ColorScheme] = None,
        font_family: str = "Helvetica",
        **kwargs,
    ) -> "ThemeData":
        """Cria um ThemeData com paleta Dark."""
        return cls(
            color_scheme=color_scheme or ColorScheme.dark(),
            font_family=font_family,
            **kwargs,
        )

    # ── Atalhos rápidos para cores ───────────────────────────

    @property
    def primary(self) -> str:
        return self.color_scheme.primary

    @property
    def background(self) -> str:
        return self.color_scheme.background

    @property
    def surface(self) -> str:
        return self.color_scheme.surface

    @property
    def error(self) -> str:
        return self.color_scheme.error

    # ── Aplicação no ttk.Style ───────────────────────────────

    def apply(self, root: tk.Tk) -> None:
        """
        Aplica o tema inteiro no ttk.Style.
        Deve ser chamado APÓS tk.Tk() ser criado — nunca antes,
        pois ttk.Style() sem um root existente cria uma janela tk implícita.

        Args:
            root: instância do tk.Tk. Obrigatório quando ainda não há
                  uma instância Tk ativa no processo.
        """
        # Garante que existe um root antes de instanciar o Style.
        # Se nenhum root foi passado, usa o root padrão do Tk, que
        # só existe se tk.Tk() já foi chamado antes.
        if root is None and not tk._default_root:  # noqa: SLF001
            # Sem root ativo: não há como aplicar estilos ttk com segurança.
            # O chamador deve passar o root explicitamente.
            return

        cs = self.color_scheme
        tt = self.text_theme
        bt = self.button_theme
        idt = self.input_decoration_theme
        abt = self.app_bar_theme
        ct = self.card_theme
        dt = self.divider_theme

        style = ttk.Style(root) if root else ttk.Style()

        # ── Tema base ────────────────────────────────────────
        # Usa "clam" como base: permite sobrescrever mais configurações
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        # ── Janela principal ─────────────────────────────────
        if root:
            root.configure(bg=cs.background)

        # ── TFrame ───────────────────────────────────────────
        style.configure(
            "TFrame",
            background=cs.background,
        )

        style.configure(
            "Surface.TFrame",
            background=cs.surface,
        )

        style.configure(
            "Card.TFrame",
            background=ct.color or cs.surface,
            relief="raised",
            borderwidth=ct.elevation,
        )

        # ── TLabel ───────────────────────────────────────────
        body_font = tt.body_small.to_tk_font()
        title_font = tt.title_small.to_tk_font()
        label_font = tt.label_small.to_tk_font()
        display_font = tt.display_small.to_tk_font()
        headline_font = tt.headline_small.to_tk_font()

        style.configure(
            "TLabel",
            background=cs.background,
            foreground=cs.on_background,
            font=body_font,
            padding=2,
        )

        # Variantes semânticas de label
        _label_variants = {
            "Display.TLabel": (display_font, cs.on_background),
            "Headline.TLabel": (headline_font, cs.on_background),
            "Title.TLabel": (title_font, cs.on_surface),
            "Body.TLabel": (body_font, cs.on_background),
            "Caption.TLabel": (tt.label_small.to_tk_font(), cs.on_surface_variant),
            "Error.TLabel": (label_font, cs.error),
            "Primary.TLabel": (label_font, cs.primary),
            "OnPrimary.TLabel": (label_font, cs.on_primary),
        }
        for name, (font, fg) in _label_variants.items():
            style.configure(
                name,
                background=cs.background,
                foreground=fg,
                font=font,
                padding=2,
            )

        # Label sobre superfície colorida
        style.configure(
            "AppBar.TLabel",
            background=abt.background_color or cs.surface,
            foreground=abt.foreground_color or cs.on_surface,
            font=(abt.title_text_style or tt.title_large).to_tk_font(),
            padding=(8, 8),
        )

        # ── TButton (ElevatedButton) ─────────────────────────
        style.configure(
            "TButton",
            background=cs.primary,
            foreground=cs.on_primary,
            font=tt.label_small.to_tk_font(),
            padding=(bt.padding_x, bt.padding_y),
            relief=bt.elevated_relief,
            borderwidth=0,
        )
        style.map(
            "TButton",
            background=[
                ("active", cs.primary_container),
                ("disabled", cs.surface_variant),
            ],
            foreground=[
                ("active", cs.on_primary_container),
                ("disabled", cs.on_surface_variant),
            ],
        )

        # ElevatedButton explícito
        style.configure(
            "Elevated.TButton",
            background=cs.primary,
            foreground=cs.on_primary,
            font=tt.label_large.to_tk_font(),
            padding=(bt.padding_x, bt.padding_y),
            relief=bt.elevated_relief,
        )
        style.map(
            "Elevated.TButton",
            background=[
                ("active", cs.primary_container),
                ("disabled", cs.surface_variant),
            ],
            foreground=[
                ("active", cs.on_primary_container),
                ("disabled", cs.on_surface_variant),
            ],
        )

        # OutlinedButton
        style.configure(
            "Outlined.TButton",
            background=cs.surface,
            foreground=cs.primary,
            font=tt.label_large.to_tk_font(),
            padding=(bt.padding_x, bt.padding_y),
            relief=bt.outlined_relief,
            borderwidth=bt.border_width if hasattr(bt, "border_width") else 1,
        )
        style.map(
            "Outlined.TButton",
            background=[
                ("active", cs.primary_container),
                ("disabled", cs.surface),
            ],
            foreground=[
                ("active", cs.primary),
                ("disabled", cs.on_surface_variant),
            ],
        )

        # TextButton
        style.configure(
            "Text.TButton",
            background=cs.background,
            foreground=cs.primary,
            font=tt.label_large.to_tk_font(),
            padding=(bt.padding_x, bt.padding_y),
            relief=bt.text_relief,
            borderwidth=0,
        )
        style.map(
            "Text.TButton",
            background=[
                ("active", cs.primary_container),
                ("disabled", cs.background),
            ],
            foreground=[
                ("active", cs.on_primary_container),
                ("disabled", cs.on_surface_variant),
            ],
        )

        # FloatingActionButton
        style.configure(
            "FAB.TButton",
            background=cs.primary_container,
            foreground=cs.on_primary_container,
            font=tt.label_large.to_tk_font(),
            padding=(16, 16),
            relief="raised",
            borderwidth=0,
        )
        style.map(
            "FAB.TButton",
            background=[("active", cs.primary)],
            foreground=[("active", cs.on_primary)],
        )

        # Danger / Error button
        style.configure(
            "Danger.TButton",
            background=cs.error,
            foreground=cs.on_error,
            font=tt.label_large.to_tk_font(),
            padding=(bt.padding_x, bt.padding_y),
            relief=bt.elevated_relief,
        )
        style.map(
            "Danger.TButton",
            background=[("active", cs.error_container)],
            foreground=[("active", cs.on_error_container)],
        )

        # ── TEntry (TextField) ───────────────────────────────
        fill = idt.fill_color or cs.surface_variant
        border = idt.border_color or cs.outline
        focused_border = idt.focused_border_color or cs.primary

        style.configure(
            "TEntry",
            fieldbackground=fill,
            foreground=cs.on_surface,
            selectbackground=cs.primary,
            selectforeground=cs.on_primary,
            insertcolor=cs.primary,
            font=body_font,
            padding=(idt.padding_x, idt.padding_y),
            relief="flat",
            borderwidth=idt.border_width,
            bordercolor=border,
        )
        style.map(
            "TEntry",
            fieldbackground=[("focus", cs.surface)],
            bordercolor=[("focus", focused_border)],
        )

        # ── TCombobox (DropdownButton) ───────────────────────
        style.configure(
            "TCombobox",
            fieldbackground=fill,
            foreground=cs.on_surface,
            background=cs.surface,
            selectbackground=cs.primary,
            selectforeground=cs.on_primary,
            font=body_font,
            padding=(8, 6),
            relief="flat",
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", fill)],
            foreground=[("readonly", cs.on_surface)],
        )

        # ── TCheckbutton ─────────────────────────────────────
        style.configure(
            "TCheckbutton",
            background=cs.background,
            foreground=cs.on_background,
            font=body_font,
            focuscolor=cs.primary,
            indicatorcolor=cs.primary,
        )
        style.map(
            "TCheckbutton",
            background=[("active", cs.background)],
            indicatorcolor=[
                ("selected", cs.primary),
                ("!selected", cs.surface_variant),
            ],
        )

        # ── TRadiobutton ─────────────────────────────────────
        style.configure(
            "TRadiobutton",
            background=cs.background,
            foreground=cs.on_background,
            font=body_font,
            focuscolor=cs.primary,
        )
        style.map(
            "TRadiobutton",
            background=[("active", cs.background)],
            indicatorcolor=[
                ("selected", cs.primary),
                ("!selected", cs.surface_variant),
            ],
        )

        # ── TProgressbar ─────────────────────────────────────
        style.configure(
            "TProgressbar",
            troughcolor=cs.surface_variant,
            background=cs.primary,
            bordercolor=cs.outline,
            lightcolor=cs.primary,
            darkcolor=cs.primary_container,
        )

        # ── Horizontal.TSeparator (Divider) ──────────────────
        style.configure(
            "TSeparator",
            background=dt.color or cs.outline_variant,
        )

        # ── TScrollbar ───────────────────────────────────────
        style.configure(
            "TScrollbar",
            background=cs.surface_variant,
            troughcolor=cs.background,
            arrowcolor=cs.on_surface_variant,
            bordercolor=cs.background,
            lightcolor=cs.surface_variant,
            darkcolor=cs.surface_variant,
        )
        style.map(
            "TScrollbar",
            background=[("active", cs.primary)],
        )

        # ── Treeview (TableView) ─────────────────────────────
        style.configure(
            "Treeview",
            background=cs.surface,
            foreground=cs.on_surface,
            fieldbackground=cs.surface,
            font=body_font,
            rowheight=28,
            borderwidth=0,
        )
        style.configure(
            "Treeview.Heading",
            background=cs.surface_variant,
            foreground=cs.on_surface_variant,
            font=tt.label_medium.to_tk_font(),
            relief="flat",
            padding=(8, 6),
        )
        style.map(
            "Treeview",
            background=[("selected", cs.primary_container)],
            foreground=[("selected", cs.on_primary_container)],
        )

        # ── AppBar Frame ─────────────────────────────────────
        style.configure(
            "AppBar.TFrame",
            background=abt.background_color or cs.surface,
            relief="flat" if abt.elevation == 0 else "raised",
            borderwidth=abt.elevation,
        )

        # ── Notebook (TabBar) ─────────────────────────────────
        style.configure(
            "TNotebook",
            background=cs.background,
            borderwidth=0,
        )
        style.configure(
            "TNotebook.Tab",
            background=cs.surface_variant,
            foreground=cs.on_surface_variant,
            font=tt.label_medium.to_tk_font(),
            padding=(12, 6),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", cs.primary_container)],
            foreground=[("selected", cs.on_primary_container)],
        )

        # ── Scale (Slider) ────────────────────────────────────
        style.configure(
            "TScale",
            background=cs.background,
            troughcolor=cs.surface_variant,
            sliderrelief="flat",
        )


# ============================================================
# THEME PROVIDER (ChangeNotifier)
# ============================================================


class ThemeProvider(ChangeNotifier):
    """
    Provider reativo do tema — permite trocar ThemeData em runtime.

    Padrão de uso:
        provider = ThemeProvider.from_mode(ThemeMode.SYSTEM)
        app.register_provider(provider)

        # Para alternar:
        provider.set_mode(ThemeMode.DARK)
        # Todos os Consumer(ThemeProvider) serão reconstruídos.

    Nota: a re-aplicação do tema via `apply()` muda os ttk.Style globais,
    mas widgets já montados precisam ser desmontados/remontados para refletir
    as novas cores — isso depende do mecanismo de rebuild do pyflutter.
    """

    def __init__(
        self,
        light_theme: Optional[ThemeData] = None,
        dark_theme: Optional[ThemeData] = None,
        mode: ThemeMode = ThemeMode.SYSTEM,
    ) -> None:
        super().__init__()
        self._light = light_theme or ThemeData.light()
        self._dark = dark_theme or ThemeData.dark()
        self._mode = mode
        self._root: Optional[tk.Tk] = None

    @property
    def mode(self) -> ThemeMode:
        return self._mode

    # ── Factory ──────────────────────────────────────────────

    @classmethod
    def from_mode(
        cls,
        mode: ThemeMode = ThemeMode.SYSTEM,
        light_theme: Optional[ThemeData] = None,
        dark_theme: Optional[ThemeData] = None,
    ) -> "ThemeProvider":
        return cls(light_theme=light_theme, dark_theme=dark_theme, mode=mode)

    # ── Estado atual ─────────────────────────────────────────

    @property
    def is_dark(self) -> bool:
        if self._mode == ThemeMode.DARK:
            return True
        if self._mode == ThemeMode.LIGHT:
            return False
        return _detect_system_dark_mode()

    @property
    def theme(self) -> ThemeData:
        """Retorna o ThemeData ativo (light ou dark)."""
        return self._dark if self.is_dark else self._light

    # ── Getters de conveniência (espelha context.theme no Flutter) ──

    @property
    def color_scheme(self) -> ColorScheme:
        return self.theme.color_scheme

    @property
    def text_theme(self) -> TextTheme:
        return self.theme.text_theme

    @property
    def primary(self) -> str:
        return self.theme.primary

    @property
    def background(self) -> str:
        return self.theme.background

    # ── Mutação ──────────────────────────────────────────────

    def set_mode(self, mode: ThemeMode) -> None:
        """Alterna entre Light, Dark e System e notifica os listeners."""
        if mode != self._mode:
            self._mode = mode
            if self._root:
                self.theme.apply(self._root)
            self.notify_listeners()

    def toggle(self) -> None:
        """Alterna entre Dark e Light (ignora System)."""
        self.set_mode(ThemeMode.LIGHT if self.is_dark else ThemeMode.DARK)

    def set_light_theme(self, theme: ThemeData) -> None:
        self._light = theme
        self.notify_listeners()

    def set_dark_theme(self, theme: ThemeData) -> None:
        self._dark = theme
        self.notify_listeners()

    # ── Aplicação ────────────────────────────────────────────

    def attach_root(self, root: tk.Tk) -> None:
        """
        Vincula o provider à janela raiz do Tk.
        Deve ser chamado em TkMaterialApp.run() antes do mainloop.
        """
        self._root = root
        self.apply()

    def apply(self) -> None:
        """Aplica o tema ativo no ttk.Style."""
        self.theme.apply(self._root)


# ============================================================
# ATALHO GLOBAL (equivalente ao Theme.of(context))
# ============================================================


class Theme:
    """
    Classe utilitária com factory methods — mantém compatibilidade
    com o código existente que usava Theme.PRIMARY, Theme.apply(), etc.

    Para novos projetos, prefira ThemeProvider + ThemeData.
    """

    # Constantes legadas (compatibilidade)
    PRIMARY: str = ColorScheme.light().primary
    BACKGROUND: str = ColorScheme.light().background

    @staticmethod
    def light(font_family: str = "Helvetica") -> ThemeData:
        return ThemeData.light(font_family=font_family)

    @staticmethod
    def dark(font_family: str = "Helvetica") -> ThemeData:
        return ThemeData.dark(font_family=font_family)

    @staticmethod
    def apply(root: Optional[tk.Tk] = None) -> None:
        """
        Compatibilidade legada: aplica um tema light padrão.
        Requer que tk.Tk() já tenha sido criado, ou que `root` seja passado.
        """
        ThemeData.light().apply(root)

    @staticmethod
    def of(context) -> ThemeData:
        """
        Equivalente ao Theme.of(context) do Flutter.
        Recupera o ThemeData ativo a partir do BuildContext.

        Uso:
            theme = Theme.of(context)
            color = theme.primary
        """
        try:
            provider: ThemeProvider = context.read(ThemeProvider)
            return provider.theme
        except (KeyError, AttributeError):
            return ThemeData.light()


# ============================================================
# INTEGRAÇÃO COM TkMaterialApp
# ============================================================


def make_themed_app(base_app_class: type[BaseMaterialApp]):
    """
    Mixin/decorator que estende qualquer subclasse de BaseMaterialApp
    para aplicar o ThemeProvider automaticamente dentro de run(),
    após tk.Tk() ser criado — sem risco de janela dupla.

    Uso:
        from pyflutter.widgets import TkMaterialApp
        from pyflutter.theme import make_themed_app

        ThemedApp = make_themed_app(TkMaterialApp)
        app = ThemedApp(home=MyPage(), title="App")
        app.register_provider(ThemeProvider(...))
        app.run()  # aplica o tema no momento certo
    """

    class ThemedApp(base_app_class):

        def run(self) -> None:

            self.root = tk.Tk()
            self.root.title(self.title)

            # Aplica o tema AGORA — root já existe, sem janela dupla.
            try:
                provider: ThemeProvider = self.providers.get(ThemeProvider)
                if provider is not None:
                    provider.attach_root(self.root)
            except Exception:
                pass

            self.get_navigator().push(self.home)
            self.root.mainloop()

        def get_navigator(self) -> Navigator:
            return super().get_navigator()

        def register_notifier(self, provider: T) -> None:
            return super().register_notifier(provider)

    ThemedApp.__name__ = f"Themed{base_app_class.__name__}"
    ThemedApp.__qualname__ = ThemedApp.__name__
    return ThemedApp
