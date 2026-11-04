"""Orby : toujours là, toujours au premier plan.

- clic simple              -> signal `clicked` (ouvre la bulle de dialogue)
- glisser                  -> le déplace (animations drag_left, drag_right_up... selon le sens)
- passer la souris en va-et-vient dessus -> le caresser (animation "pet")
- molette                  -> zoom (config.ZOOM_LEVELS)
- clic droit               -> menu (console, taille, masquer, quitter)
"""
import time

from PySide6.QtCore import QPoint, QTimer, Qt, Signal
from PySide6.QtWidgets import QApplication, QMenu, QVBoxLayout, QWidget

import config
from ui import theme
from ui.avatars import make_avatar

DRAG_THRESHOLD = 5      # pixels : en dessous, c'est un clic, pas un glissement
PET_TURNS = 3           # nombre de demi-tours de la souris pour déclencher la caresse
PET_WINDOW = 1.2        # ...dans ce délai (secondes)
PET_END_MS = 700        # la caresse s'arrête si la souris reste immobile aussi longtemps
MARGIN = 2


class Companion(QWidget):
    clicked = Signal()
    dragged = Signal()
    moved_by_user = Signal()
    petted = Signal()
    started = Signal()            # l'animation de démarrage est terminée
    zoom_changed = Signal(float)
    console_requested = Signal()
    hud_requested = Signal()
    hide_requested = Signal()
    quit_requested = Signal()

    def __init__(self, zoom: float = 1.0):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus   # ne vole jamais le focus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)    # nécessaire pour sentir la caresse

        self.avatar = make_avatar()
        # l'avatar laisse passer la souris : c'est cette fenêtre qui gère tout
        self.avatar.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(MARGIN, MARGIN, MARGIN, MARGIN)
        self.lay.addWidget(self.avatar)

        self.zoom = self._nearest_level(zoom)
        self._apply_zoom(anchor=False)

        self._press = None
        self._origin = None
        self._dragging = False
        self._last_move = None        # (temps, x, y globaux) pour calculer la vitesse
        self._vx = self._vy = 0.0
        self._busy = False            # vrai pendant les animations start / stop
        self._after_stop = None
        self._wheel = 0
        # caresse
        self._petting = False
        self._reset_pet_tracking()
        self.pet_timer = QTimer(self)
        self.pet_timer.setSingleShot(True)
        self.pet_timer.timeout.connect(self._end_pet)

        self._split_off = None        # décalage de fenêtre pendant le déplacement tête + corps
        self.avatar.animation_finished.connect(self._on_animation_finished)
        self.avatar.split_closed.connect(self._on_split_closed)

    # ---------------------------------------------------------------- Infos
    @property
    def busy(self) -> bool:
        return self._busy

    def visual_rect(self):
        """Zone réellement occupée par le dessin (sans les marges), en coordonnées écran."""
        m = MARGIN + self.avatar.pad
        return self.frameGeometry().adjusted(m, m, -m, -m)

    # ----------------------------------------------------------- Animations
    def play_start(self):
        """Animation d'apparition (à appeler juste après show())."""
        self._busy = True
        self.avatar.play_start()

    def play_stop(self, then=None):
        """Animation de disparition ; `then` est appelé quand elle est terminée."""
        self._busy = True
        self._after_stop = then
        self.avatar.play_stop()

    def _on_animation_finished(self, name: str):
        if name == "start":
            self._busy = False
            self.started.emit()
        elif name == "stop":
            self._busy = False
            callback, self._after_stop = self._after_stop, None
            if callback:
                callback()

    # ------------------------------------------------------------------ Zoom
    @staticmethod
    def _nearest_level(z: float) -> float:
        return min(config.ZOOM_LEVELS, key=lambda lv: abs(lv - z))

    def zoom_step(self, direction: int):
        levels = config.ZOOM_LEVELS
        i = levels.index(self.zoom) + (1 if direction > 0 else -1)
        self.set_zoom(levels[max(0, min(len(levels) - 1, i))])

    def set_zoom(self, zoom: float):
        zoom = self._nearest_level(zoom)
        if zoom == self.zoom:
            return
        self.zoom = zoom
        self._apply_zoom(anchor=True)
        self.zoom_changed.emit(self.zoom)

    def _refit(self):
        self.lay.activate()
        self.setFixedSize(self.lay.sizeHint())

    def _on_split_closed(self):
        """Le corps est revenu sous la tête : on remet la fenêtre à sa taille normale."""
        off, self._split_off = self._split_off, None
        self._refit()
        if off is not None:
            self.move(self.pos() + off)
        self.moved_by_user.emit()

    def _apply_zoom(self, anchor: bool):
        old = self.visual_rect() if (anchor and self.isVisible()) else None
        self.avatar.set_zoom(self.zoom)
        self.lay.activate()
        self.setFixedSize(self.lay.sizeHint())
        if old:                      # le bas-centre d'Orby reste au même endroit
            new = self.visual_rect()
            self.move(self.x() + old.center().x() - new.center().x(),
                      self.y() + old.bottom() - new.bottom())

    # -------------------------------------------------------------- Position
    def place_default(self):
        """Coin bas-droit de l'écran principal."""
        scr = QApplication.primaryScreen().availableGeometry()
        self.move(scr.right() - self.width() - 30, scr.bottom() - self.height() - 30)

    def restore_position(self, pos) -> bool:
        """Remet Orby là où il était, si l'endroit est toujours sur un écran."""
        try:
            x, y = int(pos[0]), int(pos[1])
        except (TypeError, ValueError, IndexError):
            return False
        centre = QPoint(x + self.width() // 2, y + self.height() // 2)
        if any(s.availableGeometry().contains(centre) for s in QApplication.screens()):
            self.move(x, y)
            return True
        return False

    # ---------------------------------------------------------------- Souris
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._press = e.globalPosition().toPoint()
            self._origin = self.pos()
            self._dragging = False
            self._last_move = None

    def mouseMoveEvent(self, e):
        if self._press is None:
            self._track_pet(e)
            return
        delta = e.globalPosition().toPoint() - self._press
        if not self._dragging and delta.manhattanLength() > DRAG_THRESHOLD:
            self._dragging = True
            self._end_pet()
            self.avatar.set_interaction("drag")      # animation de base dès le début du déplacement
            off = self.avatar.enter_split()          # tête + corps : la fenêtre s'agrandit
            if off is not None:
                if self._split_off is None:
                    self._split_off = QPoint(off)
                self._refit()
                self._origin = self._origin - off    # la tête reste sous la souris
            self._vx = self._vy = 0.0
            self.dragged.emit()

        if self._dragging:
            self.move(self._origin + delta)
            pos, now = e.globalPosition(), time.monotonic()
            if self._last_move:
                dt = max(0.001, now - self._last_move[0])
                # vitesse lissée : évite que le sens saute au moindre tremblement de la souris.
                # Le choix de l'animation (gauche / droite / diagonales / base) est fait par l'avatar.
                self._vx = 0.5 * self._vx + 0.5 * (pos.x() - self._last_move[1]) / dt
                self._vy = 0.5 * self._vy + 0.5 * (pos.y() - self._last_move[2]) / dt
                self.avatar.set_drag_velocity(self._vx, self._vy)
            self._last_move = (now, pos.x(), pos.y())

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._press is not None:
            if self._dragging:
                # Réinitialise l'interaction pour repasser sur l'animation de repos (idle)
                self.avatar.set_interaction(None)
                self.avatar.set_drag_velocity(0, 0)
                if self._split_off is not None:
                    self.avatar.end_split()          # le corps revient, puis _on_split_closed
                else:
                    self.moved_by_user.emit()
            elif not self._busy:
                self.clicked.emit()
            self._press = None
            self._dragging = False

    def leaveEvent(self, e):
        self._reset_pet_tracking()
        super().leaveEvent(e)

    def wheelEvent(self, e):
        self._wheel += e.angleDelta().y()
        while abs(self._wheel) >= 120:
            self.zoom_step(1 if self._wheel > 0 else -1)
            self._wheel -= 120 if self._wheel > 0 else -120
        e.accept()

    def contextMenuEvent(self, e):
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background:#0b1224; color:{theme.TEXT}; border:1px solid {theme.CYAN}; }}"
            f"QMenu::item {{ padding:6px 18px; }}"
            f"QMenu::item:selected {{ background:rgba(63,216,255,70); }}")
        menu.addAction("💬 Ouvrir la console", self.console_requested.emit)
        size = menu.addMenu("🔍 Taille")
        size.addAction("Agrandir  (molette ↑)", lambda: self.zoom_step(+1))
        size.addAction("Réduire  (molette ↓)", lambda: self.zoom_step(-1))
        size.addAction("Taille normale", lambda: self.set_zoom(1.0))
        menu.addAction("📊 Mini-écran (météo, système)", self.hud_requested.emit)
        menu.addAction("Masquer", self.hide_requested.emit)
        menu.addSeparator()
        menu.addAction("⏻ Quitter", self.quit_requested.emit)
        menu.exec(e.globalPos())

    # --------------------------------------------------------------- Caresse
    def _reset_pet_tracking(self):
        self._last_x = None
        self._dir = 0
        self._extreme_x = None
        self._turns = []

    def _track_pet(self, e):
        """Détecte des allers-retours de la souris au-dessus d'Orby."""
        if self._busy:
            return
        x, now = e.position().x(), time.monotonic()
        swing_min = max(12.0, 0.18 * self.avatar.sw)     # amplitude minimale d'un aller
        if self._last_x is None:
            self._last_x = self._extreme_x = x
            return
        dx = x - self._last_x
        if abs(dx) < 2:                                   # on ignore les micro-tremblements
            return
        direction = 1 if dx > 0 else -1
        turned = False
        if direction != self._dir:
            if self._dir != 0 and abs(self._last_x - self._extreme_x) >= swing_min:
                self._turns.append(now)
                turned = True
            self._extreme_x = self._last_x
            self._dir = direction
        self._last_x = x
        self._turns = [t for t in self._turns if now - t <= PET_WINDOW]
        if len(self._turns) >= PET_TURNS:
            if not self._petting:
                self._petting = True
                self.avatar.set_interaction("pet")
                self.petted.emit()
                turned = True
            if turned:                       # on prolonge seulement si on continue vraiment
                self.pet_timer.start(PET_END_MS)

    def _end_pet(self):
        self.pet_timer.stop()
        self._turns = []
        if self._petting:
            self._petting = False
            if not self._dragging:
                self.avatar.set_interaction(None)
