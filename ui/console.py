"""Une fenêtre de console (style cyberpunk) = UNE page. Tu peux en ouvrir plusieurs en même temps
(chat, lanceur, infos...) : chacune a sa position et sa taille, mémorisées."""
from PySide6.QtCore import QPoint, QTimer, Qt, Signal
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

import config
from ui import theme
from ui.pages import ChatPage, FilesPage, LauncherPage, NewsPage, SummaryPage

HEADER_HEIGHT = 60
EDGE = 8        # épaisseur (px) de la zone de bord qui permet de redimensionner
CASCADE = 30    # décalage (px) entre deux fenêtres ouvertes en même temps

PAGE_CLASSES = {"chat": ChatPage, "files": FilesPage, "launcher": LauncherPage,
                "summary": SummaryPage, "news": NewsPage}

_L, _R, _T, _B = Qt.Edge.LeftEdge, Qt.Edge.RightEdge, Qt.Edge.TopEdge, Qt.Edge.BottomEdge


class Console(QWidget):
    ask_requested = Signal(object, str)     # (page qui demande, texte à envoyer à l'IA)
    chat_requested = Signal(str, bool)      # (texte, l'envoyer tout de suite ?) : à traiter dans le chat
    menu_requested = Signal()               # bouton "◂" : ouvrir la bulle de menu
    geometry_saved = Signal(str, list)      # (clé du mode, [x, y, largeur, hauteur])

    def __init__(self, mode: dict, size=None):
        super().__init__()
        self.mode = mode
        self.key = mode["key"]
        self._badge = ("", theme.DIM)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(theme.STYLE)
        w, h = getattr(config, "CONSOLE_SIZE", (470, 560))
        mw, mh = getattr(config, "CONSOLE_MIN_SIZE", (320, 380))
        self.setMinimumSize(mw, mh)
        try:
            if size:
                w, h = int(size[0]), int(size[1])
        except (TypeError, ValueError, IndexError):
            pass
        self.resize(max(w, mw), max(h, mh))
        self.setMouseTracking(True)           # pour changer le curseur sur les bords
        self._resizing = None                 # (bords, position souris de départ, géométrie de départ)
        self._ready = False                   # vrai après la 1re ouverture : on ne mémorise qu'ensuite
        self._geo_timer = QTimer(self)
        self._geo_timer.setSingleShot(True)
        self._geo_timer.timeout.connect(self._emit_geometry)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        panel = theme.CyberPanel(grip=True)
        panel.setMouseTracking(True)
        outer.addWidget(panel)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(22, 20, 22, 20)
        lay.setSpacing(10)

        head = QHBoxLayout()
        back = QPushButton("◂")
        back.setObjectName("icon")
        back.setFixedWidth(30)
        back.setToolTip("Menu d'Orby")
        back.clicked.connect(self.menu_requested.emit)
        self.title = QLabel(f"◈ {config.ASSISTANT_NAME.upper()} // {mode['title']}")
        self.title.setObjectName("title")
        self.badge = QLabel()
        hide_btn = QPushButton("_")
        hide_btn.setObjectName("icon")
        hide_btn.setFixedWidth(30)
        hide_btn.setToolTip("Fermer cette fenêtre (Échap)")
        hide_btn.clicked.connect(self.hide)
        for w_ in (back, self.title):
            head.addWidget(w_)
        head.addStretch()
        head.addWidget(self.badge)
        head.addWidget(hide_btn)
        lay.addLayout(head)

        self.page = PAGE_CLASSES[mode["page"]]()
        lay.addWidget(self.page, 1)
        if hasattr(self.page, "submitted"):
            self.page.submitted.connect(lambda text: self.ask_requested.emit(self.page, text))
        if hasattr(self.page, "ask_requested"):          # explorateur / infos : la question va dans le chat
            self.page.ask_requested.connect(self.chat_requested.emit)
        if hasattr(self.page, "configure"):
            self.page.configure(mode)
        self.set_badge("", theme.DIM)

    # ----------------------------------------------------------------- API
    def set_badge(self, name: str, color: str):
        self._badge = (name, color)
        self._refresh_badge()

    def _refresh_badge(self):
        """Badge de l'IA utilisée : nom complet, ou juste le point coloré si la fenêtre est étroite."""
        name, color = self._badge
        compact = self.width() < 380
        self.badge.setText("" if not name else "●" if compact else f"● {name.upper()}")
        self.badge.setToolTip(name)
        self.badge.setStyleSheet(f"color:{color}; font-weight:bold; font-size:11px;")

    def notice(self, text: str):
        if hasattr(self.page, "notice"):
            self.page.notice(text)

    def open_near(self, anchor: QWidget, saved_pos=None, slot: int = 0):
        """Ouvre la fenêtre : à sa dernière position, sinon près d'Orby (décalée de `slot` crans)."""
        if not self.isVisible():
            if not self._move_to_saved(saved_pos):
                geo = anchor.visual_rect() if hasattr(anchor, "visual_rect") else anchor.frameGeometry()
                scr = anchor.screen().availableGeometry()
                x = geo.right() - self.width() - slot * CASCADE
                y = geo.top() - self.height() - 6 - slot * CASCADE
                if y < scr.top():
                    y = geo.bottom() + 6 + slot * CASCADE
                x = max(scr.left() + 4, min(x, scr.right() - self.width() - 4))
                y = max(scr.top() + 4, min(y, scr.bottom() - self.height() - 4))
                self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        if hasattr(self.page, "activate"):
            self.page.activate()
        self._ready = True

    def _move_to_saved(self, pos) -> bool:
        try:
            x, y = int(pos[0]), int(pos[1])
        except (TypeError, ValueError, IndexError):
            return False
        centre = QPoint(x + self.width() // 2, y + 20)
        if any(s.availableGeometry().contains(centre) for s in QApplication.screens()):
            self.move(x, y)
            return True
        return False

    # ---------------------------------------- Mémorisation position / taille
    def _emit_geometry(self):
        self.geometry_saved.emit(self.key, [self.x(), self.y(), self.width(), self.height()])

    def moveEvent(self, e):
        super().moveEvent(e)
        if self._ready:
            self._geo_timer.start(400)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._refresh_badge()
        if self._ready:
            self._geo_timer.start(400)

    # ---------------------------------------------- Redimensionnement à la souris
    def _edges_at(self, pos):
        edges = Qt.Edge(0)
        if pos.x() <= EDGE:
            edges |= _L
        if pos.x() >= self.width() - EDGE:
            edges |= _R
        if pos.y() <= EDGE:
            edges |= _T
        if pos.y() >= self.height() - EDGE:
            edges |= _B
        return edges

    @staticmethod
    def _cursor_for(edges):
        horiz, vert = bool(edges & (_L | _R)), bool(edges & (_T | _B))
        if horiz and vert:
            diag = bool(edges & _L and edges & _T) or bool(edges & _R and edges & _B)
            return Qt.CursorShape.SizeFDiagCursor if diag else Qt.CursorShape.SizeBDiagCursor
        return Qt.CursorShape.SizeHorCursor if horiz else Qt.CursorShape.SizeVerCursor

    def _do_resize(self, gp):
        edges, start, g0 = self._resizing
        dx, dy = gp.x() - start.x(), gp.y() - start.y()
        minw, minh = self.minimumWidth(), self.minimumHeight()
        left, top, right, bottom = g0.left(), g0.top(), g0.right(), g0.bottom()
        if edges & _L:
            left = min(g0.left() + dx, right - minw + 1)
        if edges & _R:
            right = max(g0.right() + dx, left + minw - 1)
        if edges & _T:
            top = min(g0.top() + dy, bottom - minh + 1)
        if edges & _B:
            bottom = max(g0.bottom() + dy, top + minh - 1)
        self.setGeometry(left, top, right - left + 1, bottom - top + 1)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.raise_()
        pos = event.position().toPoint()
        edges = self._edges_at(pos)
        if edges:                                   # bord ou coin : on redimensionne
            self._resizing = (edges, event.globalPosition().toPoint(), self.geometry())
        elif pos.y() < HEADER_HEIGHT:               # en-tête : on déplace la fenêtre
            handle = self.windowHandle()
            if handle:
                handle.startSystemMove()

    def mouseMoveEvent(self, event):
        if self._resizing and event.buttons() & Qt.MouseButton.LeftButton:
            self._do_resize(event.globalPosition().toPoint())
        elif event.buttons() == Qt.MouseButton.NoButton:
            edges = self._edges_at(event.position().toPoint())
            if edges:
                self.setCursor(self._cursor_for(edges))
            else:
                self.unsetCursor()

    def mouseReleaseEvent(self, event):
        self._resizing = None

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)
