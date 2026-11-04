"""Mini-écran flottant (HUD) : heure, météo, état du système et rappels, en temps réel.

- Version COMPLÈTE ou RÉDUITE (bouton − / +) : la version réduite n'affiche que l'heure et les infos système.
- REDIMENSIONNABLE : tire sur un bord ou un coin. Les tailles (complète / réduite) sont mémorisées.
Les timers ne tournent que quand la fenêtre est visible.
"""
from collections import deque
from datetime import datetime

from PySide6.QtCore import QPoint, QPointF, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget,
)

import config
from core import info, reminders
from ui import theme
from ui.async_util import run_async

DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
          "septembre", "octobre", "novembre", "décembre"]
MAX_ROWS = 4            # rappels affichés (le reste est résumé par « +N autres »)
EDGE = 10               # épaisseur (px) de la zone de bord qui permet de redimensionner
MIN_W = {"full": 230, "compact": 170}
DEFAULT_W = {"full": 280, "compact": 200}
MAX_W = 700

_BAR = ("QProgressBar { border:1px solid rgba(63,216,255,90); background:rgba(3,6,14,200); color:white;"
        " text-align:center; font-size:10px; } QProgressBar::chunk { background: %s; }")
# niveau -> (style de la barre, couleur du chiffre)
LEVELS = {
    "ok":   (_BAR % "rgba(63,216,255,130)", theme.CYAN),
    "warn": (_BAR % "rgba(255,176,46,170)", theme.AMBER),
    "hot":  (_BAR % "rgba(255,46,151,190)", theme.MAGENTA),
}


def level(value, low_is_bad=False) -> str:
    """ok / warn / hot : CPU, RAM, disque > 60 % puis > 85 % ; batterie < 40 % puis < 20 %."""
    if low_is_bad:
        return "hot" if value < 20 else "warn" if value < 40 else "ok"
    return "hot" if value > 85 else "warn" if value > 60 else "ok"

_L, _R, _T, _B = Qt.Edge.LeftEdge, Qt.Edge.RightEdge, Qt.Edge.TopEdge, Qt.Edge.BottomEdge


class Spark(QWidget):
    """Petite courbe de l'historique du CPU : remplit l'espace entre l'heure et les chiffres."""

    def __init__(self):
        super().__init__()
        self.values = deque(maxlen=45)
        self.color = QColor(theme.CYAN)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setToolTip("Historique CPU")

    def push(self, value: float, color: str):
        self.values.append(max(0.0, min(100.0, float(value))))
        self.color = QColor(color)
        self.update()

    def paintEvent(self, _):
        r = self.rect().adjusted(4, 6, -4, -6)
        if r.width() < 12 or len(self.values) < 2:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        step = r.width() / (self.values.maxlen - 1)
        x0 = r.right() - step * (len(self.values) - 1)          # le plus récent est à droite
        pts = [QPointF(x0 + i * step, r.bottom() - v / 100 * r.height()) for i, v in enumerate(self.values)]
        guide = QColor(111, 138, 166, 60)                       # repères 0 / 50 / 100 %
        p.setPen(QPen(guide, 1, Qt.PenStyle.DotLine))
        for frac in (0.0, 0.5, 1.0):
            y = r.bottom() - frac * r.height()
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
        line = QPainterPath(pts[0])
        for pt in pts[1:]:
            line.lineTo(pt)
        area = QPainterPath(line)
        area.lineTo(QPointF(pts[-1].x(), r.bottom()))
        area.lineTo(QPointF(pts[0].x(), r.bottom()))
        area.closeSubpath()
        fill = QColor(self.color)
        fill.setAlpha(45)
        p.fillPath(area, fill)
        p.setPen(QPen(self.color, 1.6))
        p.drawPath(line)


class Hud(QWidget):
    moved_by_user = Signal()
    layout_changed = Signal()     # taille ou mode (complet / réduit) modifié : à mémoriser
    closed = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)   # n'arrache pas le focus
        self.setStyleSheet(theme.STYLE)
        self.setMouseTracking(True)           # curseur de redimensionnement sur les bords

        self.compact = False
        self.sizes = {"full": [DEFAULT_W["full"], 0], "compact": [DEFAULT_W["compact"], 0]}  # [largeur, hauteur voulue]
        self._resizing = None
        self._fitting = False
        self._rem_sig = None
        self._hint_on = False
        self._clock_px = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        panel = theme.CyberPanel(12)
        panel.setMouseTracking(True)
        outer.addWidget(panel)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(5)

        head = QHBoxLayout()
        self.title = QLabel(f"◈ {config.ASSISTANT_NAME.upper()} // HUD")
        self.title.setObjectName("title")
        self.toggle = QPushButton("−")
        self.toggle.setObjectName("icon")
        self.toggle.setFixedWidth(26)
        self.toggle.clicked.connect(lambda: self.set_compact(not self.compact))
        close = QPushButton("×")
        close.setObjectName("icon")
        close.setFixedWidth(26)
        close.setToolTip("Fermer (Échap)")
        close.clicked.connect(self._close)
        head.addWidget(self.title)
        head.addStretch()
        head.addWidget(self.toggle)
        head.addWidget(close)
        lay.addLayout(head)

        self.clock = QLabel()
        self.clock.setTextFormat(Qt.TextFormat.PlainText)
        self.clock.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.date = QLabel()
        self.date.setObjectName("dim")
        top = QHBoxLayout()                        # heure à gauche ; en version réduite, chiffres à droite
        clock_col = QVBoxLayout()
        clock_col.setSpacing(0)
        clock_col.addWidget(self.clock)
        clock_col.addWidget(self.date)
        top.addLayout(clock_col)
        self.spark = Spark()                       # version réduite : courbe CPU entre l'heure et les chiffres
        self.spark.hide()
        top.addWidget(self.spark, 1)
        top.addStretch(0)                          # (si la courbe est masquée, ce ressort prend la place)
        self.stats_box = QWidget()
        grid = QGridLayout(self.stats_box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(1)
        self.stat_rows = {}                        # clé -> (nom, valeur)
        for i, (key, name) in enumerate((("cpu", "CPU"), ("ram", "RAM"), ("disk", "DSK"), ("bat", "BAT"))):
            nm, val = QLabel(name), QLabel()
            nm.setObjectName("dim")
            val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(nm, i, 0)
            grid.addWidget(val, i, 1)
            self.stat_rows[key] = (nm, val)
        top.addWidget(self.stats_box)
        lay.addLayout(top)

        self.sec_weather = self._section("// MÉTÉO")
        self.weather = QLabel("⟳ chargement…")
        self.weather.setWordWrap(True)
        lay.addWidget(self.sec_weather)
        lay.addWidget(self.weather)

        self.sec_sys = self._section("// SYSTÈME")
        lay.addWidget(self.sec_sys)
        self.bars = {}
        for key in ("cpu", "ram", "disk", "bat"):
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setFixedHeight(16)
            bar.setStyleSheet(LEVELS["ok"][0])
            bar.hide()
            self.bars[key] = bar
            lay.addWidget(bar)
        self.sys_note = QLabel()
        self.sys_note.setObjectName("dim")
        self.sys_note.setWordWrap(True)
        lay.addWidget(self.sys_note)

        self.sec_rem = self._section("// RAPPELS")
        lay.addWidget(self.sec_rem)
        self.rem_box = QWidget()
        self.rem_host = QVBoxLayout(self.rem_box)
        self.rem_host.setContentsMargins(0, 0, 0, 0)
        self.rem_host.setSpacing(3)
        lay.addWidget(self.rem_box)
        self.rem_input = QLineEdit()
        self.rem_input.setPlaceholderText("18:30 appeler Paul · dans 10 min …")
        self.rem_input.returnPressed.connect(self._add_reminder)
        lay.addWidget(self.rem_input)
        self.hint = QLabel()
        self.hint.setObjectName("dim")
        self.hint.setWordWrap(True)
        self.hint.hide()
        lay.addWidget(self.hint)
        lay.addStretch()                      # l'espace en trop (fenêtre agrandie) va en bas

        self._full_only = (self.date, self.sec_weather, self.weather, self.sec_rem,
                           self.rem_box, self.rem_input)

        self.fast = QTimer(self)              # horloge + système
        self.fast.timeout.connect(self._tick)
        self.slow = QTimer(self)              # météo
        self.slow.timeout.connect(self._load_weather)
        self._move_timer = QTimer(self)
        self._move_timer.setSingleShot(True)
        self._move_timer.timeout.connect(self.moved_by_user.emit)
        self._size_timer = QTimer(self)
        self._size_timer.setSingleShot(True)
        self._size_timer.timeout.connect(self.layout_changed.emit)
        self._apply_mode()

    @staticmethod
    def _section(text):
        lbl = QLabel(text)
        lbl.setObjectName("section")
        return lbl

    # ------------------------------------------------------- Mode complet / réduit
    @property
    def mode(self) -> str:
        return "compact" if self.compact else "full"

    def set_compact(self, compact: bool):
        if compact == self.compact:
            return
        self.compact = compact
        self._apply_mode()
        self._size_timer.start(300)

    def _apply_mode(self):
        full = not self.compact
        for w in self._full_only:
            w.setVisible(full)
        self.hint.setVisible(full and self._hint_on)
        self.sec_sys.setVisible(full)
        self.stats_box.setVisible(not full)
        self.toggle.setText("−" if full else "+")
        self.toggle.setToolTip("Version réduite (heure + système)" if full else "Version complète")
        self.setMinimumWidth(MIN_W[self.mode])
        self.setMaximumWidth(MAX_W)
        self.resize(max(MIN_W[self.mode], self.sizes[self.mode][0]), self.height())
        self._tick()
        self._refit()

    def restore_state(self, sizes, compact):
        """Remet les tailles et le mode mémorisés."""
        try:
            for key in ("full", "compact"):
                w, h = sizes[key]
                self.sizes[key] = [max(MIN_W[key], min(MAX_W, int(w))), max(0, int(h))]
        except (TypeError, KeyError, ValueError):
            pass
        self.compact = bool(compact)
        self._apply_mode()

    def _refit(self):
        """Hauteur minimale = contenu ; la fenêtre est au moins aussi haute (ou comme l'a voulue l'utilisateur)."""
        if self._fitting:
            return
        self._fitting = True
        try:
            lay = self.layout()
            lay.activate()
            need = lay.totalHeightForWidth(self.width())
            if need <= 0:
                need = lay.sizeHint().height()
            if self.minimumHeight() != need:
                self.setMinimumHeight(need)
            if not self._resizing:
                target = max(need, self.sizes[self.mode][1])
                if self.height() != target:
                    self.resize(self.width(), target)
        finally:
            self._fitting = False

    def resizeEvent(self, e):
        super().resizeEvent(e)
        px = max(18, min(44 if self.compact else 64, int(self.width() * (0.17 if self.compact else 0.1))))   # l'heure grandit avec la fenêtre
        if px != self._clock_px:
            self._clock_px = px
            self.clock.setStyleSheet(f"color:{theme.CYAN}; font-size:{px}px; font-weight:bold;")
        self._refit()

    # ------------------------------------------------------------ Affichage
    def showEvent(self, e):
        super().showEvent(e)
        self._tick()
        self._load_weather()
        self._refresh_reminders(force=True)
        self.fast.start(2000)
        self.slow.start(15 * 60 * 1000)

    def hideEvent(self, e):
        self.fast.stop()
        self.slow.stop()
        super().hideEvent(e)

    def _close(self):
        self.hide()
        self.closed.emit()

    # ---------------------------------------------------------------- Temps réel
    def _tick(self):
        now = datetime.now()
        self.clock.setText(now.strftime("%H\n%M") if self.compact else now.strftime("%H:%M"))   # réduit : heures / minutes
        self.date.setText(f"{DAYS[now.weekday()]} {now.day} {MONTHS[now.month - 1]}")
        s = info.system_stats()
        note = ""
        shown = {}                                  # clé -> (valeur, texte barre, texte court, niveau)
        if s is not None:
            if s["cpu"] is not None:
                shown["cpu"] = (s["cpu"], f"CPU {s['cpu']:.0f}%", f"{s['cpu']:.0f}%", level(s["cpu"]))
            if s["ram"] is not None:
                shown["ram"] = (s["ram"], f"RAM {s['ram']:.0f}%  ({s['ram_used']:.1f}/{s['ram_total']:.1f} Go)",
                                f"{s['ram']:.0f}%", level(s["ram"]))
            if s["disk"] is not None:
                shown["disk"] = (s["disk"], f"DISQUE {s['disk']:.0f}%", f"{s['disk']:.0f}%", level(s["disk"]))
            bat = s["battery"]
            if bat:
                plug = " ⚡" if bat["plugged"] else ""
                lvl = "ok" if bat["plugged"] else level(bat["percent"], low_is_bad=True)
                shown["bat"] = (bat["percent"], f"BATTERIE {bat['percent']}%{plug}", f"{bat['percent']}%{plug}", lvl)
            if s["source"] != "psutil":
                note = "psutil absent : mode simplifié (survole pour la commande d'installation)"
                self.sys_note.setToolTip(f"Installe-le dans le Python utilisé par Orby :\n{info.PSUTIL_HINT}")
        show_names = getattr(config, "HUD_COMPACT_LABELS", True)
        for key in ("cpu", "ram", "disk", "bat"):
            data = shown.get(key)
            bar = self.bars[key]
            nm, val = self.stat_rows[key]
            if data is None:                        # non détecté : rien ne s'affiche
                bar.hide()
                nm.hide()
                val.hide()
                continue
            value, bar_text, short, lvl = data
            bar_style, color = LEVELS[lvl]
            if key == "cpu":
                self.spark.push(value, color)
            bar.setVisible(not self.compact)        # version complète : barres colorées
            bar.setValue(int(value))
            bar.setFormat(bar_text)
            if bar.styleSheet() != bar_style:
                bar.setStyleSheet(bar_style)
            nm.setVisible(self.compact and show_names)   # version réduite : chiffres colorés
            val.setVisible(self.compact)
            val.setText(short)
            val.setStyleSheet(f"color:{color}; font-weight:bold; font-size:13px;")
        self.spark.setVisible(self.compact and "cpu" in shown)
        self.sys_note.setText(note)
        self.sys_note.setVisible(bool(note) and not self.compact)
        self._refresh_reminders()
        self._refit()

    def _load_weather(self):
        if not self.compact:                      # inutile en version réduite
            run_async(info.fetch_weather, self._show_weather)

    def _show_weather(self, res):
        if isinstance(res, Exception):
            self.weather.setText("⚠ Météo indisponible")
        else:
            rain = f" · pluie {res['rain']}%" if res["rain"] is not None else ""
            self.weather.setText(
                f"{res['icon']} {res['desc']} — {res['place']}\n"
                f"{res['temp']}°C (ressenti {res['feels']}°) · vent {res['wind']} km/h\n"
                f"min {res['tmin']}° / max {res['tmax']}°{rain}")
        self._refit()

    # ------------------------------------------------------------------ Rappels
    def _refresh_reminders(self, force=False):
        items = reminders.load()
        sig = tuple((r["id"], r["at"], r["text"]) for r in items)
        if sig == self._rem_sig and not force:
            return
        self._rem_sig = sig
        while self.rem_host.count():
            w = self.rem_host.takeAt(0)
            if w.layout():
                while w.layout().count():
                    x = w.layout().takeAt(0).widget()
                    if x:
                        x.deleteLater()
            if w.widget():
                w.widget().deleteLater()
        if not items:
            none = QLabel("Aucun rappel.")
            none.setObjectName("dim")
            self.rem_host.addWidget(none)
        for r in items[:MAX_ROWS]:
            row = QHBoxLayout()
            lbl = QLabel(f"⏰ {reminders.label(r)}  {r['text']}")
            lbl.setWordWrap(True)
            rm = QPushButton("✕")
            rm.setObjectName("quit")
            rm.setFixedWidth(22)
            rm.clicked.connect(lambda _=False, rid=r["id"]: self._remove(rid))
            row.addWidget(lbl, 1)
            row.addWidget(rm)
            self.rem_host.addLayout(row)
        if len(items) > MAX_ROWS:
            more = QLabel(f"+ {len(items) - MAX_ROWS} autre(s)")
            more.setObjectName("dim")
            self.rem_host.addWidget(more)
        QTimer.singleShot(0, self._refit)

    def _remove(self, rid):
        reminders.remove(rid)
        self._refresh_reminders(force=True)

    def _add_reminder(self):
        line = self.rem_input.text().strip()
        if not line:
            return
        try:
            at, text = reminders.parse_reminder(line)
        except ValueError as e:
            self.hint.setText(f"⚠ {e}")
            self._hint_on = True
            self.hint.show()
            self._refit()
            return
        reminders.add(text, at)
        self.rem_input.clear()
        self._hint_on = False
        self.hint.hide()
        self._refresh_reminders(force=True)

    # ----------------------------------------------------- Position / déplacement
    def place_default(self):
        scr = QApplication.primaryScreen().availableGeometry()
        self.move(scr.right() - self.width() - 20, scr.top() + 20)

    def restore_position(self, pos) -> bool:
        try:
            x, y = int(pos[0]), int(pos[1])
        except (TypeError, ValueError, IndexError):
            return False
        if any(s.availableGeometry().contains(QPoint(x + self.width() // 2, y + 20)) for s in QApplication.screens()):
            self.move(x, y)
            return True
        return False

    def moveEvent(self, e):
        super().moveEvent(e)
        self._move_timer.start(400)       # on mémorise la position une fois le déplacement fini

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

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        edges = self._edges_at(e.position().toPoint())
        if edges:                                   # bord ou coin : on redimensionne
            self._resizing = (edges, e.globalPosition().toPoint(), self.geometry())
        else:                                       # ailleurs : on déplace
            handle = self.windowHandle()
            if handle:
                handle.startSystemMove()

    def mouseMoveEvent(self, e):
        if self._resizing and e.buttons() & Qt.MouseButton.LeftButton:
            self._do_resize(e.globalPosition().toPoint())
        elif e.buttons() == Qt.MouseButton.NoButton:
            edges = self._edges_at(e.position().toPoint())
            if edges:
                self.setCursor(self._cursor_for(edges))
            else:
                self.unsetCursor()

    def mouseReleaseEvent(self, e):
        if self._resizing:
            self._resizing = None
            need = self.minimumHeight()
            # hauteur « voulue » : 0 = suit le contenu ; sinon la taille choisie
            self.sizes[self.mode] = [self.width(), self.height() if self.height() > need + 2 else 0]
            self._refit()
            self._size_timer.start(300)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self._close()
        else:
            super().keyPressEvent(e)
