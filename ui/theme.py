"""Style cyberpunk d'Orby.

La palette vient d'Orby lui-même : yeux cyan, reflets bleu électrique, corps argenté,
sur un fond bleu nuit. Le magenta est la touche "néon" qui fait ressortir le tout.
Pour changer les couleurs de toute l'interface, modifie les constantes ci-dessous.
"""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

CYAN = "#3fd8ff"
BLUE = "#4060f0"
MAGENTA = "#ff2e97"
AMBER = "#ffb02e"
TEXT = "#cfe9f2"
DIM = "#6f8aa6"
FONT = "'Cascadia Mono','Consolas','DejaVu Sans Mono','Courier New',monospace"

STYLE = f"""
* {{ font-family: {FONT}; }}
QLabel {{ color: {TEXT}; font-size: 12px; }}
QLabel#title {{ color: {CYAN}; font-weight: bold; font-size: 13px; }}
QLabel#section {{ color: {MAGENTA}; font-size: 10px; font-weight: bold; }}
QLabel#dim {{ color: {DIM}; font-size: 11px; }}
QTextBrowser, QListWidget {{ background: rgba(3,6,14,200); color: {TEXT};
    border: 1px solid rgba(63,216,255,70); padding: 6px; font-size: 12px; }}
QListWidget::item {{ padding: 4px; }}
QListWidget::item:selected {{ background: rgba(63,216,255,60); color: white; }}
QLineEdit, QComboBox {{ background: rgba(3,6,14,220); color: white;
    border: 1px solid rgba(63,216,255,110); padding: 6px; font-size: 12px; }}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {CYAN}; }}
QComboBox QAbstractItemView {{ background: #0b1224; color: {TEXT};
    selection-background-color: rgba(63,216,255,80); }}
QPushButton {{ background: rgba(63,216,255,22); color: {CYAN};
    border: 1px solid rgba(63,216,255,140); padding: 7px 12px; font-size: 12px; text-align: left; }}
QPushButton:hover {{ background: rgba(63,216,255,60); color: white; border-color: {CYAN}; }}
QPushButton:pressed {{ background: rgba(255,46,151,70); border-color: {MAGENTA}; }}
QPushButton:disabled {{ color: {DIM}; border-color: rgba(111,138,166,70); background: transparent; }}
QPushButton#icon {{ text-align: center; padding: 4px; }}
QPushButton#quit {{ background: transparent; color: {DIM}; border: none; text-align: center; padding: 4px; }}
QPushButton#quit:hover {{ color: {MAGENTA}; }}
QPushButton#accent {{ color: {MAGENTA}; border-color: rgba(255,46,151,150);
    background: rgba(255,46,151,22); text-align: center; }}
QPushButton#accent:hover {{ background: rgba(255,46,151,70); color: white; border-color: {MAGENTA}; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollArea#chatview {{ background: rgba(3,6,14,200); border: 1px solid rgba(63,216,255,70); }}
QFrame#msg {{ background: rgba(63,216,255,10); }}
QFrame#code {{ background: rgba(0,0,0,170); border: 1px solid rgba(63,216,255,90); }}
QFrame#codehead {{ background: rgba(63,216,255,28); border: none; }}
QTextEdit#codeedit {{ background: transparent; color: {TEXT}; border: none; font-size: 12px; }}
QPushButton#copy {{ padding: 2px 8px; font-size: 10px; text-align: center; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: rgba(63,216,255,110); min-width: 20px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: rgba(63,216,255,110); min-height: 20px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""


def chamfer(r: QRectF, cut: float = 14.0, corners=("tr", "bl")) -> QPainterPath:
    """Rectangle aux coins coupés (typique de l'interface cyberpunk)."""
    l, t, rr, b = r.left(), r.top(), r.right(), r.bottom()
    pts = []
    pts += [QPointF(l, t + cut), QPointF(l + cut, t)] if "tl" in corners else [QPointF(l, t)]
    pts += [QPointF(rr - cut, t), QPointF(rr, t + cut)] if "tr" in corners else [QPointF(rr, t)]
    pts += [QPointF(rr, b - cut), QPointF(rr - cut, b)] if "br" in corners else [QPointF(rr, b)]
    pts += [QPointF(l + cut, b), QPointF(l, b - cut)] if "bl" in corners else [QPointF(l, b)]
    path = QPainterPath()
    path.addPolygon(QPolygonF(pts))
    path.closeSubpath()
    return path


def paint_panel(p: QPainter, path: QPainterPath):
    """Fond sombre + lignes de balayage + bordure néon avec halo."""
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(7, 11, 22, 238))
    p.drawPath(path)

    r = path.boundingRect()
    p.save()
    p.setClipPath(path)
    p.setPen(QPen(QColor(63, 216, 255, 9), 1))
    y = r.top()
    while y < r.bottom():
        p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
        y += 3
    p.restore()

    p.setBrush(Qt.BrushStyle.NoBrush)
    for width, alpha in ((8, 12), (5, 26), (3, 55)):      # halo
        p.setPen(QPen(QColor(63, 216, 255, alpha), width))
        p.drawPath(path)
    p.setPen(QPen(QColor(CYAN), 1.4))
    p.drawPath(path)
    p.setPen(QPen(QColor(MAGENTA), 2.4))                   # petits accents néon
    p.drawLine(QPointF(r.left() + 10, r.top()), QPointF(r.left() + 42, r.top()))
    p.drawLine(QPointF(r.right() - 42, r.bottom()), QPointF(r.right() - 10, r.bottom()))


class CyberPanel(QWidget):
    """Fond de fenêtre cyberpunk (utilisé par la console)."""

    def __init__(self, cut: float = 16.0, grip: bool = False):
        super().__init__()
        self.cut = cut
        self.grip = grip      # petite poignée en bas à droite : "tire ici pour redimensionner"

    def paintEvent(self, _):
        p = QPainter(self)
        r = QRectF(self.rect()).adjusted(6, 6, -6, -6)
        paint_panel(p, chamfer(r, self.cut))
        if self.grip:
            p.setPen(QPen(QColor(CYAN), 1.2))
            for i in (1, 2, 3):
                o = 4 + i * 5
                p.drawLine(QPointF(r.right() - o, r.bottom() - 4), QPointF(r.right() - 4, r.bottom() - o))
