from __future__ import annotations
from typing import Protocol
from table_stream import Directory
from cartas import BuilderConfigTOI, set_dir_base_toi


class CartasDirGateway(Protocol):
    """Porta (Ports & Adapters) para o diretório base das cartas TOI."""

    def current(self) -> Directory:
        """Diretório efetivamente em uso pelo módulo cartas."""
        ...

    def apply(self, directory: Directory) -> None:
        """Faz o módulo cartas passar a usar `directory`."""
        ...


class CartasModuleGateway:
    """Adapter para o módulo `cartas` (imports locais: cartas inicializa OCR/config)."""

    def current(self) -> Directory:
        return BuilderConfigTOI().builder().dir_base_toi

    def apply(self, directory: Directory) -> None:
        # PONTO ÚNICO DE INTEGRAÇÃO: precisa existir (de forma aditiva) em cartas.
        # Ver PATCHES.md, seção "cartas".

        set_dir_base_toi(directory)
