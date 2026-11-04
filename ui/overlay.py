"""Fenêtre overlay : toujours au premier plan, sans bordure, déplaçable."""
import html
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu,
    QPushButton, QSystemTrayIcon, QTextBrowser, QVBoxLayout, QWidget,
)

import config
from core.agent import Agent
from ui.avatars import AVATARS

HEADER_HEIGHT = 52

STYLE = """
#panel { background: #1e1f26; border: 1px solid #3a3c48; border-radius: 14px; }
QLabel { color: #e6e6e6; }
QTextBrowser { background: #16171c; color: #e6e6e6; border: none; border-radius: 8px; padding: 6px; }
QLineEdit { background: #16171c; color: #ffffff; border: 1px solid #3a3c48; border-radius: 8px; padding: 6px; }
QPushButton { background: #2d3040; color: #ffffff; border: none; border-radius: 8px; padding: 6px 12px; }
QPushButton:hover { background: #3a3e54; }
"""


class Bridge(QObject):
    """Relie le thread de l'IA à l'interface (les signaux sont thread-safe)."""
    state = Signal(str)
    switched = Signal(str, str, str)   # ancien, nouveau, raison
    answer = Signal(str)
    toggle = Signal()


class Overlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(380, 520)

        self.bridge = Bridge()
        self.agent = Agent(on_state=self.bridge.state.emit,
                           on_switch=self.bridge.switched.emit)

        self._build_ui()
        self._connect_signals()
        self._setup_tray()
        self._setup_hotkey()
        self._welcome()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        self.setStyleSheet(STYLE)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        panel = QFrame()
        panel.setObjectName("panel")
        outer.addWidget(panel)
        lay = QVBoxLayout(panel)

        head = QHBoxLayout()
        self.avatar = AVATARS[config.AVATAR]()
        self.badge = QLabel()
        hide_btn = QPushButton("–")
        hide_btn.setFixedWidth(32)
        hide_btn.clicked.connect(self.hide)
        head.addWidget(self.avatar)
        head.addWidget(QLabel("<b>Assistant</b>"))
        head.addStretch()
        head.addWidget(self.badge)
        head.addWidget(hide_btn)
        lay.addLayout(head)

        self.chat = QTextBrowser()
        lay.addWidget(self.chat, 1)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Pose ta question…")
        self.send_btn = QPushButton("Envoyer")
        row.addWidget(self.input, 1)
        row.addWidget(self.send_btn)
        lay.addLayout(row)

        first = self.agent.pool.first_name
        if first:
            self._set_badge(first)
        else:
            self.badge.setText("● aucune clé")

    def _connect_signals(self):
        self.send_btn.clicked.connect(self._send)
        self.input.returnPressed.connect(self._send)
        self.bridge.state.connect(self.avatar.set_state)
        self.bridge.switched.connect(self._on_switched)
        self.bridge.answer.connect(self._on_answer)
        self.bridge.toggle.connect(self.toggle)

    def _welcome(self):
        if not self.agent.pool.providers:
            self._notice("Aucune clé API trouvée : remplis le fichier .env puis relance.")
        else:
            names = ", ".join(p.name for p in self.agent.pool.providers)
            self._notice(f"Prêt. IA disponibles (par priorité) : {names}")

    # ------------------------------------------------------------- Chat
    def _append(self, who: str, text: str, color: str):
        safe = html.escape(text).replace("\n", "<br>")
        self.chat.append(f'<p><b style="color:{color}">{who}</b><br>{safe}</p>')

    def _notice(self, text: str):
        self.chat.append(
            f'<p style="color:#f5a623"><i>{html.escape(text)}</i></p>')

    def _set_badge(self, name: str):
        color = self.agent.pool.color_of(name)
        self.badge.setText(f"● {name}")
        self.badge.setStyleSheet(f"color:{color}; font-weight:bold;")
        self.avatar.set_accent(color)

    def _send(self):
        text = self.input.text().strip()
        if not text or not self.input.isEnabled():
            return
        self.input.clear()
        self.input.setEnabled(False)
        self._append("Toi", text, "#9ecbff")
        threading.Thread(target=self._work, args=(text,), daemon=True).start()

    def _work(self, text: str):  # tourne dans un thread, pas de Qt ici
        self.bridge.answer.emit(self.agent.ask(text))

    def _on_answer(self, text: str):
        self._append("Assistant", text, "#b9f6ca")
        self.input.setEnabled(True)
        self.input.setFocus()

    def _on_switched(self, old: str, new: str, reason: str):
        self._set_badge(new)
        if reason:
            msg = f"⚠ {reason} → bascule sur {new}"
        elif old:
            msg = f"✓ Retour à la normale, utilisation de {new}"
        else:
            return  # tout premier appel, tout va bien : silence
        self._notice(msg)
        if not self.isVisible():
            self.tray.showMessage("Assistant", msg)

    # ----------------------------------------------- Fenêtre / tray / clavier
    def toggle(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()
            self.input.setFocus()

    def _setup_tray(self):
        pm = QPixmap(32, 32)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor("#4285F4"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(4, 4, 24, 24)
        p.end()
        self.tray = QSystemTrayIcon(QIcon(pm), self)
        self.menu = QMenu()
        self.menu.addAction("Afficher / masquer", self.toggle)
        self.menu.addAction("Quitter", QApplication.quit)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(
            lambda r: self.toggle()
            if r == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()

    def _setup_hotkey(self):
        try:
            from pynput import keyboard
            self._hotkey = keyboard.GlobalHotKeys(
                {config.HOTKEY: self.bridge.toggle.emit})
            self._hotkey.start()
        except Exception as e:  # ex. Wayland : on garde l'icône de la zone de notif
            print("Raccourci global indisponible :", e)

    def mousePressEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton
                and event.position().y() < HEADER_HEIGHT):
            handle = self.windowHandle()
            if handle:
                handle.startSystemMove()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)
