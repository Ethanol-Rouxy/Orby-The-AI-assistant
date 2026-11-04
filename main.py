import signal
import sys

from PySide6.QtWidgets import QApplication

from ui.app import AssistantApp

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)  # Ctrl+C dans le terminal arrête tout
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # reste actif même sans fenêtre ouverte
    assistant = AssistantApp(app)         # on garde la référence
    sys.exit(app.exec())
