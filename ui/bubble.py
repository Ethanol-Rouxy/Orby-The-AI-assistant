"""La bulle de dialogue d'Orby : style néon, texte qui s'écrit lettre par lettre."""
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPolygonF
from PySide6.QtWidgets import QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

import config
from ui import theme

TAIL = 14        # hauteur de la pointe de la bulle
WIDTH = getattr(config, "BUBBLE_WIDTH", 300)
TYPE_MS = 18     # vitesse de la machine à écrire (ms par lettre) : plus petit = plus rapide


class Bubble(QWidget):
    mode_chosen = Signal(str)     # clé du mode choisi (voir config.MODES)
    quit_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus   # ne vole pas le focus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(WIDTH)
        self.setStyleSheet(theme.STYLE)
        self._tail_down = True
        self._tail_x = WIDTH // 2
        self._full = ""
        self._typed = 0
        self._after_ms = 0

        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(20, TAIL + 14, 20, TAIL + 14)
        self.lay.setSpacing(8)
        self.name = QLabel(f"◈ {config.ASSISTANT_NAME.upper()}")
        self.name.setObjectName("section")
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.lay.addWidget(self.name)
        self.lay.addWidget(self.label)
        # Les boutons sont dans une zone défilante : s'il y en a trop, ça défile au lieu de déborder.
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.host = QWidget()
        self.buttons = QVBoxLayout(self.host)
        self.buttons.setContentsMargins(0, 0, 0, 0)
        self.buttons.setSpacing(6)
        self.scroll.setWidget(self.host)
        self.host.setAutoFillBackground(False)
        self.scroll.hide()
        self.lay.addWidget(self.scroll)

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)
        self.type_timer = QTimer(self)
        self.type_timer.timeout.connect(self._type_tick)

    # ----------------------------------------------------------------- API
    def show_menu(self, text: str, modes: list, anchor: QWidget):
        """Bulle avec un texte et un bouton par mode."""
        self._clear_buttons()
        for m in modes:
            b = QPushButton(m["label"])
            b.clicked.connect(lambda _=False, k=m["key"]: self.mode_chosen.emit(k))
            self.buttons.addWidget(b)
        q = QPushButton("⏻ Quitter")
        q.setObjectName("quit")
        q.clicked.connect(self.quit_requested.emit)
        self.buttons.addWidget(q)
        self.scroll.show()
        self._say(text, anchor, auto_hide_ms=0)

    def show_offer(self, text: str, offers: list, anchor: QWidget, ms: int = 30000):
        """Bulle avec des propositions [(texte du bouton, clé)] ; disparaît seule si on l'ignore."""
        self._clear_buttons()
        for label, key in offers:
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, k=key: self.mode_chosen.emit(k))
            self.buttons.addWidget(b)
        later = QPushButton("Plus tard")
        later.setObjectName("quit")
        later.clicked.connect(lambda: self.mode_chosen.emit("_dismiss"))
        self.buttons.addWidget(later)
        self.scroll.show()
        self._say(text, anchor, auto_hide_ms=ms)

    def show_notice(self, text: str, anchor: QWidget, ms: int = 5000):
        """Bulle d'information sans bouton, qui disparaît toute seule."""
        self._clear_buttons()
        self._say(text, anchor, auto_hide_ms=ms)

    # ------------------------------------------------------------ Interne
    def _say(self, text: str, anchor: QWidget, auto_hide_ms: int):
        self.hide_timer.stop()
        self.type_timer.stop()
        self.label.setText(text)            # texte complet d'abord, pour calculer la taille
        self._place(anchor)
        self._full, self._typed, self._after_ms = text, 0, auto_hide_ms
        self.label.setText("")
        self.type_timer.start(TYPE_MS)

    def _type_tick(self):
        self._typed += 1
        self.label.setText(self._full[: self._typed])
        if self._typed >= len(self._full):
            self.type_timer.stop()
            if self._after_ms:
                self.hide_timer.start(self._after_ms)

    def hideEvent(self, e):
        self.type_timer.stop()
        self.hide_timer.stop()
        super().hideEvent(e)

    def _clear_buttons(self):
        self.scroll.hide()
        while self.buttons.count():
            w = self.buttons.takeAt(0).widget()
            if w:
                w.deleteLater()

    def _place(self, anchor: QWidget):
        geo = anchor.visual_rect() if hasattr(anchor, "visual_rect") else anchor.frameGeometry()
        scr = anchor.screen().availableGeometry()
        max_h = int(scr.height() * 0.85)

        want = 0
        if not self.scroll.isHidden():             # zone des boutons : hauteur plafonnée
            self.buttons.activate()
            want = self.host.sizeHint().height()
            self.scroll.setFixedHeight(want)
        self.lay.activate()
        h = self.lay.totalHeightForWidth(WIDTH)
        if want and h > max_h:                     # trop haut pour l'écran : les boutons défilent
            self.scroll.setFixedHeight(max(80, want - (h - max_h)))
            self.lay.activate()
            h = self.lay.totalHeightForWidth(WIDTH)
        self.setFixedHeight(h if h > 0 else self.sizeHint().height())

        self._tail_down = geo.top() - self.height() >= scr.top()   # place au-dessus ?
        x = geo.center().x() - WIDTH // 2
        x = max(scr.left() + 4, min(x, scr.right() - WIDTH - 4))
        y = geo.top() - self.height() + 4 if self._tail_down else geo.bottom() - 4
        self._tail_x = max(30, min(WIDTH - 30, geo.center().x() - x))
        self.move(x, y)
        self.update()
        self.show()
        self.raise_()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        body = QRectF(6, TAIL, self.width() - 12, self.height() - 2 * TAIL)
        path = theme.chamfer(body, 12, ("tr", "bl"))
        x = self._tail_x
        if self._tail_down:
            y0, tip = body.bottom(), body.bottom() + TAIL - 3
            pts = [QPointF(x - 9, y0 - 1), QPointF(x, tip), QPointF(x + 9, y0 - 1)]
        else:
            y0, tip = body.top(), body.top() - TAIL + 3
            pts = [QPointF(x - 9, y0 + 1), QPointF(x, tip), QPointF(x + 9, y0 + 1)]
        tail = QPainterPath()
        tail.addPolygon(QPolygonF(pts))
        tail.closeSubpath()
        theme.paint_panel(p, path.united(tail))
