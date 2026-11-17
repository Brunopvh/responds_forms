# file_picker.py
# Implementação de FilePicker para PyFlutter no padrão do Flutter real.
#
# No Flutter, FilePicker não é um widget — é um controller/serviço que
# expõe um método pickFiles() e notifica os listeners com o resultado.
# Este arquivo replica essa arquitetura usando os primitivos do PyFlutter.
#
# ─────────────────────────────────────────────────────────────
# USO BÁSICO
# ─────────────────────────────────────────────────────────────
#
#   picker = FilePickerController(
#       type=FilePickerType.image,          # filtro de tipo
#       allow_multiple=True,                # seleção múltipla
#   )
#
#   # Abrir o diálogo e aguardar o resultado:
#   result: FilePickerResult | None = picker.pick_files()
#   if result:
#       for f in result.files:
#           print(f.name, f.path, f.size)
#
#   # Ou de forma reativa (integrado ao build do widget):
#   ValueListenableBuilder(
#       notifier=picker.result_notifier,
#       builder=lambda ctx, result: Text(
#           result.files[0].name if result else "Nenhum arquivo"
#       ),
#   )
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
import os
from dataclasses import dataclass, field
from enum import Enum
from tkinter import filedialog
from typing import Optional
from pyflutter_ui.ui.core import ValueNotifier


# ============================================================
# TIPOS DE ARQUIVO — espelha o FileType do flutter_file_picker
# ============================================================

class FilePickerType(Enum):
    """Filtro de tipo de arquivo para o diálogo."""
    any    = "any"    # sem filtro
    image  = "image"  # png, jpg, jpeg, gif, bmp, webp, svg
    pdf    = "pdf"    # pdf
    spreadsheet = "spreadsheet"  # xlsx, xls, csv, ods
    video  = "video"  # mp4, mov, avi, mkv, webm
    audio  = "audio"  # mp3, wav, ogg, flac, aac
    custom = "custom" # usa allowed_extensions fornecido pelo dev


# Mapeamento interno: tipo → lista de extensões tk-compatíveis
_TYPE_FILTERS: dict[FilePickerType, list[tuple[str, str]]] = {
    FilePickerType.any: [("Todos os arquivos", "*.*")],
    FilePickerType.image: [
        ("Imagens", "*.png *.jpg *.jpeg *.gif *.bmp *.webp *.svg"),
        ("Todos os arquivos", "*.*"),
    ],
    FilePickerType.pdf: [
        ("PDF", "*.pdf"),
        ("Todos os arquivos", "*.*"),
    ],
    FilePickerType.spreadsheet: [
        ("Planilhas", "*.xlsx *.xls *.csv *.ods"),
        ("Todos os arquivos", "*.*"),
    ],
    FilePickerType.video: [
        ("Vídeos", "*.mp4 *.mov *.avi *.mkv *.webm"),
        ("Todos os arquivos", "*.*"),
    ],
    FilePickerType.audio: [
        ("Áudios", "*.mp3 *.wav *.ogg *.flac *.aac"),
        ("Todos os arquivos", "*.*"),
    ],
}


# ============================================================
# MODELO DE RESULTADO — espelha PlatformFile do Flutter
# ============================================================

@dataclass(frozen=True)
class PlatformFile:
    """Representa um arquivo selecionado pelo usuário."""
    path: str                        # caminho absoluto no disco
    name: str = field(init=False)    # nome do arquivo (sem diretório)
    extension: str = field(init=False)  # extensão sem ponto, ex: "pdf"
    size: int = field(init=False)    # tamanho em bytes (0 se inacessível)

    def __post_init__(self) -> None:
        # dataclass frozen=True exige object.__setattr__ para init tardio
        object.__setattr__(self, "name", os.path.basename(self.path))
        ext = os.path.splitext(self.path)[1].lstrip(".")
        object.__setattr__(self, "extension", ext.lower())
        try:
            object.__setattr__(self, "size", os.path.getsize(self.path))
        except OSError:
            object.__setattr__(self, "size", 0)

    @property
    def size_readable(self) -> str:
        """Tamanho formatado (bytes / KB / MB / GB)."""
        n = self.size
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024:
                return f"{n:.1f} {unit}" if unit != "B" else f"{n} {unit}"
            n /= 1024
        return f"{n:.1f} TB"


@dataclass(frozen=True)
class FilePickerResult:
    """Resultado de uma seleção de arquivos. Equivale a FilePickerResult do Flutter."""
    files: list[PlatformFile]

    @property
    def paths(self) -> list[str]:
        """Atalho: lista de caminhos absolutos."""
        return [f.path for f in self.files]

    @property
    def names(self) -> list[str]:
        """Atalho: lista de nomes de arquivo."""
        return [f.name for f in self.files]

    @property
    def is_single(self) -> bool:
        return len(self.files) == 1

    def single(self) -> PlatformFile | None:
        """Retorna o único arquivo ou None se houver 0 ou mais de 1."""
        return self.files[0] if self.is_single else None


# ============================================================
# CONTROLLER — o equivalente ao FilePicker.platform do Flutter
# ============================================================

class FilePickerController:
    """
    Controller que encapsula a lógica de seleção de arquivos.

    Não é um widget — vive no State do seu widget pai, exatamente
    como FilePickerController no Flutter.

    Parâmetros
    ----------
    type : FilePickerType
        Filtro de tipo de arquivo. Use FilePickerType.custom junto com
        allowed_extensions para filtros personalizados.
    allow_multiple : bool
        Se True, permite selecionar vários arquivos de uma vez.
    allowed_extensions : list[str] | None
        Usado apenas quando type=FilePickerType.custom.
        Ex.: ["json", "toml", "yaml"]
    dialog_title : str
        Título da janela de diálogo do SO.
    initial_directory : str | None
        Diretório inicial do diálogo. Padrão: pasta home do usuário.
    """

    def __init__(
                self,
                type: FilePickerType = FilePickerType.any,
                allow_multiple: bool = False,
                allowed_extensions: Optional[list[str]] = None,
                dialog_title: str = "Selecionar arquivo",
                initial_directory: Optional[str] = None,
            ) -> None:
                
        self.type = type
        self.allow_multiple = allow_multiple
        self.allowed_extensions = allowed_extensions
        self.dialog_title = dialog_title
        self.initial_directory = initial_directory #or os.path.expanduser("~")
        
        if self.initial_directory is None:
            self.initial_directory = os.path.join(f"{os.path.expanduser("~")}", "Downloads")

        # Expõe o resultado de forma reativa — use em ValueListenableBuilder
        self.result_notifier: ValueNotifier[FilePickerResult | None] = ValueNotifier(None)

    # ── API pública ───────────────────────────────────────────

    def pick_files(self) -> FilePickerResult | None:
        """
        Abre o diálogo de seleção de arquivos do SO.

        Retorna FilePickerResult se o usuário confirmou, None se cancelou.
        Também atualiza result_notifier para notificar widgets ouvintes.
        """
        filters = self._resolve_filters()

        if self.allow_multiple:
            paths = filedialog.askopenfilenames(
                title=self.dialog_title,
                filetypes=filters,
                initialdir=self.initial_directory,
            )
            raw = list(paths) if paths else []
        else:
            path = filedialog.askopenfilename(
                title=self.dialog_title,
                filetypes=filters,
                initialdir=self.initial_directory,
            )
            raw = [path] if path else []

        result = FilePickerResult(files=[PlatformFile(p) for p in raw]) if raw else None
        if raw is not None:
            first = raw[0] if len(raw) > 0 else None
            if first is not None:
                self.initial_directory = os.path.dirname(first)
                print(f'{__class__.__name__} [INITIAL_DIR] ... {self.initial_directory}')
        
        self.result_notifier.value = result
        return result

    def pick_directory(self) -> str | None:
        """
        Abre o diálogo para selecionar uma pasta.

        Retorna o caminho absoluto ou None se cancelado.
        """
        path = filedialog.askdirectory(
            title=self.dialog_title,
            initialdir=self.initial_directory,
            mustexist=True,
        )
        return path or None

    def save_file(
        self,
        suggested_name: str = "",
    ) -> str | None:
        """
        Abre o diálogo "Salvar como".

        Retorna o caminho escolhido ou None se cancelado.
        """
        filters = self._resolve_filters()
        default_ext = (
            "." + self.allowed_extensions[0]
            if self.allowed_extensions
            else ""
        )
        path = filedialog.asksaveasfilename(
            title=self.dialog_title,
            filetypes=filters,
            initialdir=self.initial_directory,
            initialfile=suggested_name,
            defaultextension=default_ext,
        )
        return path or None

    def clear_result(self) -> None:
        """Limpa o resultado atual e notifica os ouvintes."""
        self.result_notifier.value = None

    # ── privado ───────────────────────────────────────────────

    def _resolve_filters(self) -> list[tuple[str, str]]:
        if self.type == FilePickerType.custom:
            if not self.allowed_extensions:
                return [("Todos os arquivos", "*.*")]
            pattern = " ".join(f"*.{ext}" for ext in self.allowed_extensions)
            label = ", ".join(self.allowed_extensions).upper()
            return [(label, pattern), ("Todos os arquivos", "*.*")]
        return _TYPE_FILTERS.get(self.type, [("Todos os arquivos", "*.*")])

