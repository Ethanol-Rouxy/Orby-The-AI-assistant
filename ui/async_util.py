"""Exécute une fonction lente dans un thread, puis rappelle l'interface sans la geler."""
import threading

from PySide6.QtCore import QObject, Signal, Slot

_alive = set()   # garde une référence tant que la tâche tourne


class _Task(QObject):
    done = Signal(object)

    def __init__(self, on_done):
        super().__init__()
        self._on_done = on_done
        self.done.connect(self._finish)

    @Slot(object)
    def _finish(self, value):
        try:
            self._on_done(value)
        finally:
            _alive.discard(self)
            self.deleteLater()


def run_async(fn, on_done):
    """fn() tourne dans un thread ; on_done(résultat) est appelé dans l'interface.
    Si fn lève une exception, on_done reçoit l'exception."""
    task = _Task(on_done)
    _alive.add(task)

    def work():
        try:
            result = fn()
        except Exception as e:  # noqa: BLE001
            result = e
        task.done.emit(result)

    threading.Thread(target=work, daemon=True).start()
