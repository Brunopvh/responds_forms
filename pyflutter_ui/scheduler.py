# pyflutter_ui/scheduler.py
from __future__ import annotations

import queue
import threading
import tkinter as tk
from typing import Callable, Optional


class MainThreadScheduler:

    _root: Optional[tk.Tk] = None
    _ui_thread_id: Optional[int] = None

    _queue: queue.Queue[Callable[[], None]] = queue.Queue()

    _polling: bool = False
    _poll_interval_ms: int = 15

    # ============================================================
    # CICLO DE VIDA
    # ============================================================

    @classmethod
    def attach(cls, root: tk.Tk) -> None:
        """
        Registra a janela Tk e a thread responsável pela UI.

        Deve ser chamado na mesma thread que criou o tk.Tk().
        """

        cls._root = root
        cls._ui_thread_id = threading.get_ident()

        if not cls._polling:
            cls._polling = True
            cls._poll()

    @classmethod
    def detach(cls) -> None:
        """
        Remove o scheduler e descarta callbacks pendentes.
        """

        cls._polling = False
        cls._root = None
        cls._ui_thread_id = None

        while True:
            try:
                cls._queue.get_nowait()
            except queue.Empty:
                break

    @classmethod
    def is_attached(cls) -> bool:
        return (
            cls._root is not None
            and cls._ui_thread_id is not None
        )

    @classmethod
    def is_ui_thread(cls) -> bool:
        return (
            cls._ui_thread_id is not None
            and threading.get_ident() == cls._ui_thread_id
        )

    # ============================================================
    # EXECUÇÃO
    # ============================================================

    @classmethod
    def run(cls, callback: Callable[[], None]) -> None:
        """
        Executa callback na thread da interface.

        Se já estiver na thread do Tk:
            executa imediatamente.

        Se estiver em uma worker thread:
            coloca na fila para execução pelo Tk.
        """

        if not cls.is_attached():
            raise RuntimeError(
                f"{cls.__name__}: scheduler não está anexado. "
                f"Crie o Tk() e chame attach(root) antes de usar run()."
            )

        if cls.is_ui_thread():
            callback()
            return

        cls._queue.put(callback)

        root = cls._root

        if root is None:
            return

        try:
            root.after(0, cls._drain)
        except (tk.TclError, RuntimeError):
            pass

    # ============================================================
    # FILA
    # ============================================================

    @classmethod
    def _drain(cls) -> None:
        """
        Executa os callbacks pendentes na thread do Tk.
        """

        if not cls.is_ui_thread():
            return

        while True:

            try:
                callback = cls._queue.get_nowait()
            except queue.Empty:
                break

            try:
                callback()
            except Exception as e:
                print(
                    f"{cls.__name__} "
                    f"erro ao executar callback: {e}"
                )

    @classmethod
    def _poll(cls) -> None:
        """
        Mantém o processamento da fila ativo.
        """

        root = cls._root

        if root is None or not cls._polling:
            return

        cls._drain()

        try:
            root.after(
                cls._poll_interval_ms,
                cls._poll
            )
        except (tk.TclError, RuntimeError):
            cls._polling = False