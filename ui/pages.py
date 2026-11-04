"""Les 4 pages de la console. Chaque choix de la bulle ouvre une page différente.

Interface commune des pages qui parlent à l'IA :
  begin(texte)   appelé quand une question part      deliver(texte)  appelé à la réponse
"""
import html
import re
from pathlib import Path
from urllib.parse import quote

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QScrollArea, QSizePolicy, QStyle,
    QStyleOptionButton, QStylePainter, QTextBrowser, QVBoxLayout, QWidget,
)

import config
from core import info, tools
from ui import theme
from ui.async_util import run_async
from ui.chat_widgets import ChatView, MessageWidget, TypingIndicator

NAME = config.ASSISTANT_NAME.upper()


def _fmt(text: str) -> str:
    """Met en forme la réponse de l'IA : **gras**, `code`, listes et titres."""
    t = html.escape(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"`([^`\n]+)`", rf'<span style="color:{theme.AMBER}">\1</span>', t)
    t = re.sub(r"(?m)^\s*[-*]\s+", "• ", t)
    t = re.sub(r"(?m)^#{1,6}\s*(.+)$", r"<b>\1</b>", t)
    return t.replace("\n", "<br>")


def _label(text="", name=None, wrap=False):
    lbl = QLabel(text)
    if name:
        lbl.setObjectName(name)
    lbl.setWordWrap(wrap)
    return lbl


class ElideButton(QPushButton):
    """Bouton qui ne force jamais la largeur : un texte trop long est raccourci avec « … »
    (le texte complet reste dans l'infobulle). Plus de défilement horizontal."""

    def __init__(self, text: str):
        super().__init__(text)
        self._full = text
        self.setToolTip(text)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

    def minimumSizeHint(self):
        return QSize(40, super().minimumSizeHint().height())

    def paintEvent(self, _):
        p = QStylePainter(self)
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        opt.text = self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideRight,
                                                 max(10, self.width() - 26))
        p.drawControl(QStyle.ControlElement.CE_PushButton, opt)


class ScrollPage(QWidget):
    """Page dont le contenu défile s'il y a trop d'éléments. `self.lay` = le contenu,
    `self.footer` = une zone fixe en bas (hors défilement)."""

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        self.lay = QVBoxLayout(body)
        self.lay.setContentsMargins(0, 0, 6, 0)
        self.scroll.setWidget(body)
        body.setAutoFillBackground(False)
        outer.addWidget(self.scroll, 1)
        self.footer = QVBoxLayout()
        outer.addLayout(self.footer)


# =========================================================================== CHAT
class ChatPage(QWidget):
    submitted = Signal(str)

    def __init__(self):
        super().__init__()
        self._placeholder = "Écris ton message…"
        self._greeted = False
        self._typing = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.view = ChatView()
        lay.addWidget(self.view, 1)
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.send_btn = QPushButton("ENVOYER ▸")
        self.send_btn.setObjectName("accent")
        row.addWidget(self.input, 1)
        row.addWidget(self.send_btn)
        lay.addLayout(row)
        self.send_btn.clicked.connect(self._send)
        self.input.returnPressed.connect(self._send)
        self.set_busy(False)

    def configure(self, mode: dict):
        self._placeholder = mode.get("placeholder") or self._placeholder
        if self.input.isEnabled():
            self.input.setPlaceholderText(self._placeholder)
        if not self._greeted and mode.get("greeting"):
            self._greeted = True
            self.add_answer(mode["greeting"])

    def activate(self):
        self.input.setFocus()

    def set_busy(self, busy: bool):
        self.input.setEnabled(not busy)
        self.send_btn.setEnabled(not busy)
        self.input.setPlaceholderText("… réflexion en cours …" if busy else self._placeholder)
        if busy and self._typing is None:
            self._typing = TypingIndicator()
            self.view.add(self._typing)
        elif not busy:
            if self._typing is not None:
                self._typing.deleteLater()
                self._typing = None
            self.input.setFocus()

    def begin(self, text: str):
        self.add_user(text)
        self.set_busy(True)

    def deliver(self, text: str):
        self.set_busy(False)
        self.add_answer(text)

    def add_user(self, text: str):
        self.view.add(MessageWidget("TOI ▸", theme.MAGENTA, text, markdown=False))

    def add_answer(self, text: str):
        self.view.add(MessageWidget(f"{NAME} ▸", theme.CYAN, text, copyable=True))

    def notice(self, text: str):
        self.view.add_notice(text)

    def _send(self):
        text = self.input.text().strip()
        if text and self.input.isEnabled():
            self.input.clear()
            self.submitted.emit(text)


# ========================================================================= FICHIERS
class FilesPage(QWidget):
    ask_requested = Signal(str, bool)   # (texte, l'envoyer tout de suite ?)

    def __init__(self):
        super().__init__()
        self.cwd = None
        self._loaded = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self.path_label = _label("", "dim")
        self.search = QLineEdit()
        self.search.setPlaceholderText("Chercher un fichier par son nom…  (Entrée)")
        self.list = QListWidget()
        self.status = _label("", "dim")

        row1, row2 = QHBoxLayout(), QHBoxLayout()
        self.up_btn = QPushButton("◂ RETOUR")
        self.open_btn = QPushButton("OUVRIR")
        self.sum_btn = QPushButton("RÉSUMER")
        self.ask_btn = QPushButton("QUESTION…")
        for b in (self.up_btn, self.open_btn):
            row1.addWidget(b)
        for b in (self.sum_btn, self.ask_btn):
            b.setObjectName("accent")
            row2.addWidget(b)
        for w in (self.path_label, self.search):
            lay.addWidget(w)
        lay.addWidget(self.list, 1)
        lay.addLayout(row1)
        lay.addLayout(row2)
        lay.addWidget(self.status)

        self.search.returnPressed.connect(self._search)
        self.list.itemDoubleClicked.connect(lambda _i: self._open_selected())
        self.list.itemSelectionChanged.connect(self._update_buttons)
        self.up_btn.clicked.connect(self._go_up)
        self.open_btn.clicked.connect(self._open_selected)
        self.sum_btn.clicked.connect(lambda: self._ask(True))
        self.ask_btn.clicked.connect(lambda: self._ask(False))
        self._update_buttons()

    def activate(self):
        if not self._loaded:
            self._loaded = True
            self.browse(None)
        self.search.setFocus()

    # -- navigation
    def browse(self, path):
        self.cwd = path
        if path is None:
            entries = [(r.name or str(r), True, str(r)) for r in tools.allowed_roots()]
            self.path_label.setText("// DOSSIERS AUTORISÉS")
        else:
            try:
                entries = tools.list_entries(path)
            except Exception as e:  # noqa: BLE001
                self.status.setText(f"⚠ {e}")
                return
            self.path_label.setText(f"// {path}")
        self._fill(entries, "(dossier vide)")

    def _fill(self, entries, empty):
        self.list.clear()
        for name, is_dir, p in entries:
            item = QListWidgetItem(("📁 " if is_dir else "📄 ") + name)
            item.setData(Qt.ItemDataRole.UserRole, (p, is_dir))
            self.list.addItem(item)
        self.status.setText(f"{len(entries)} élément(s)" if entries else empty)
        self._update_buttons()

    def _selected(self):
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _update_buttons(self):
        sel = self._selected()
        self.open_btn.setEnabled(bool(sel))
        self.sum_btn.setEnabled(bool(sel) and not sel[1])
        self.ask_btn.setEnabled(bool(sel) and not sel[1])
        self.up_btn.setEnabled(self.cwd is not None)

    def _go_up(self):
        if self.cwd is None:
            return
        here = Path(self.cwd).resolve()
        roots = [r.resolve() for r in tools.allowed_roots()]
        self.browse(None if here in roots else str(here.parent))

    def _open_selected(self):
        sel = self._selected()
        if not sel:
            return
        path, is_dir = sel
        if is_dir:
            self.browse(path)
            return
        try:
            self.status.setText("✓ " + tools.open_path(path))
        except Exception as e:  # noqa: BLE001
            self.status.setText(f"⚠ {e}")

    def _ask(self, send_now: bool):
        sel = self._selected()
        if not sel or sel[1]:
            return
        if send_now:
            self.ask_requested.emit(f"Lis le fichier « {sel[0]} » et résume-le en quelques points.", True)
        else:
            self.ask_requested.emit(f"À propos du fichier « {sel[0]} » : ", False)

    def _search(self):
        q = self.search.text().strip()
        if not q:
            self.browse(self.cwd)
            return
        self.status.setText("⟳ SCAN EN COURS…")
        run_async(lambda: tools.find_files(q, self.cwd), lambda res: self._show_found(q, res))

    def _show_found(self, q, res):
        if isinstance(res, Exception):
            self.status.setText(f"⚠ {res}")
            return
        self.path_label.setText(f"// RÉSULTATS POUR « {q} »")
        self._fill(res, "Aucun résultat.")


# ========================================================================== LANCEUR
class LauncherPage(ScrollPage):
    def __init__(self):
        super().__init__()
        lay = self.lay
        self._sections = []          # (grille, boutons) : réorganisés quand la largeur change
        self._cols = -1
        self.status = _label("PRÊT.", "dim", wrap=True)

        self._section(lay, "// APPLICATIONS",
                      [(n.capitalize(), lambda n=n: tools.launch_app(n)) for n in config.APPS])
        self._section(lay, "// SITES FAVORIS",
                      [(n, lambda u=u: tools.open_url(u)) for n, u in config.FAVORITE_SITES.items()])
        self._section(lay, "// DOSSIERS",
                      [(r.name or str(r), lambda r=r: tools.open_path(str(r))) for r in tools.allowed_roots()])
        lay.addStretch()

        self.line = QLineEdit()
        self.line.setPlaceholderText("Un site ou une recherche web…  (Entrée)")
        self.line.returnPressed.connect(self._web)
        self.footer.addWidget(self.line)       # zone fixe : toujours visible, même avec beaucoup de boutons
        self.footer.addWidget(self.status)

    def activate(self):
        self.line.setFocus()

    def _section(self, lay, title, items, cols=2):
        if not items:
            return
        lay.addWidget(_label(title, "section"))
        grid = QGridLayout()
        buttons = []
        for i, (text, fn) in enumerate(items):
            b = ElideButton("▸ " + text)
            b.clicked.connect(lambda _=False, fn=fn: self._run(fn))
            grid.addWidget(b, i // cols, i % cols)
            buttons.append(b)
        lay.addLayout(grid)
        self._sections.append((grid, buttons))

    def _reflow(self):
        """Autant de colonnes que la largeur le permet (boutons d'au moins ~120 px), de 1 à 4.
        Les colonnes inutilisées ne gardent aucune largeur : plus de marge vide à droite."""
        width = self.scroll.viewport().width() - 6
        cols = max(1, min(4, (width + 6) // 126))
        if cols == self._cols:
            return
        self._cols = cols
        for grid, buttons in self._sections:
            for b in buttons:
                grid.removeWidget(b)
            for i, b in enumerate(buttons):
                grid.addWidget(b, i // cols, i % cols)
            for c in range(4):
                grid.setColumnStretch(c, 1 if c < cols else 0)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._reflow()

    def showEvent(self, e):
        super().showEvent(e)
        self._reflow()

    def _run(self, fn):
        try:
            self.status.setText("✓ " + str(fn()))
        except Exception as e:  # noqa: BLE001
            self.status.setText(f"⚠ {e}")

    def _web(self):
        text = self.line.text().strip()
        if not text:
            return
        self.line.clear()
        if re.match(r"^https?://", text):
            url = text
        elif re.match(r"^[\w-]+(\.[\w-]+)+(/\S*)?$", text):
            url = "https://" + text
        else:
            url = "https://duckduckgo.com/?q=" + quote(text)
        self._run(lambda: tools.open_url(url))


# ========================================================================== INFOS
class NewsPage(QWidget):
    ask_requested = Signal(str, bool)

    def __init__(self):
        super().__init__()
        self._loaded_at = 0.0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(_label("// ACTUALITÉS DU JOUR  (double-clic : ouvrir)", "section"))
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.list.setSpacing(2)
        lay.addWidget(self.list, 1)
        self.status = _label("", "dim")
        lay.addWidget(self.status)
        row = QHBoxLayout()
        self.refresh_btn = QPushButton("⟳ ACTUALISER")
        self.open_btn = QPushButton("OUVRIR")
        self.open_btn.setEnabled(False)
        row.addWidget(self.refresh_btn)
        row.addWidget(self.open_btn)
        lay.addLayout(row)
        self.sum_btn = QPushButton("🧠 RÉSUMER LES INFOS")
        self.sum_btn.setObjectName("accent")
        lay.addWidget(self.sum_btn)

        self.refresh_btn.clicked.connect(self.refresh)
        self.open_btn.clicked.connect(self._open)
        self.list.itemDoubleClicked.connect(lambda _i: self._open())
        self.list.itemSelectionChanged.connect(
            lambda: self.open_btn.setEnabled(self.list.currentItem() is not None))
        self.sum_btn.clicked.connect(lambda: self.ask_requested.emit(
            "Fais-moi un résumé des principales actualités du jour (utilise get_news), "
            "en quelques points clairs.", True))

    def activate(self):
        import time
        if time.time() - self._loaded_at > 600:
            self.refresh()

    def refresh(self):
        self.status.setText("⟳ CHARGEMENT…")
        self.refresh_btn.setEnabled(False)
        run_async(lambda: info.fetch_news(force=True), self._show)

    def _show(self, res):
        import time
        self.refresh_btn.setEnabled(True)
        if isinstance(res, Exception) or not res:
            self.status.setText("⚠ Impossible de récupérer les actualités (connexion ?)")
            return
        self._loaded_at = time.time()
        self.list.clear()
        for it in res:
            hour = it["date"].strftime("%H:%M") + " · " if it.get("date") else ""
            item = QListWidgetItem(f"{it['title']}\n   ↳ {it['source']} · {hour}".rstrip(" ·"))
            item.setData(Qt.ItemDataRole.UserRole, it["link"])
            self.list.addItem(item)
        self.status.setText(f"{len(res)} titres")

    def _open(self):
        item = self.list.currentItem()
        if item:
            try:
                tools.open_url(item.data(Qt.ItemDataRole.UserRole))
            except Exception as e:  # noqa: BLE001
                self.status.setText(f"⚠ {e}")


# ========================================================================== RÉSUMÉ
SUMMARY_STYLES = {
    "Court (3 phrases)": "un résumé en 3 phrases maximum",
    "Points clés": "une liste de 5 à 8 points clés",
    "Détaillé": "un résumé détaillé et structuré, avec des titres",
}


class SummaryPage(ScrollPage):
    submitted = Signal(str)

    def __init__(self):
        super().__init__()
        self.path = None
        self.setAcceptDrops(True)
        lay = self.lay

        lay.addWidget(_label("// DOCUMENT", "section"))
        self.file_label = _label("Aucun document. Glisse un fichier ici ou utilise le bouton.",
                                 "dim", wrap=True)
        self.pick_btn = QPushButton("📂 CHOISIR UN DOCUMENT…")
        lay.addWidget(self.file_label)
        lay.addWidget(self.pick_btn)

        lay.addWidget(_label("// STYLE DU RÉSUMÉ", "section"))
        self.style_box = QComboBox()
        self.style_box.addItems(list(SUMMARY_STYLES))
        lay.addWidget(self.style_box)

        self.go_btn = QPushButton("▶ RÉSUMER")
        self.go_btn.setObjectName("accent")
        self.go_btn.setEnabled(False)
        lay.addWidget(self.go_btn)

        self.result = QTextBrowser()
        self.result.setMinimumHeight(180)
        lay.addWidget(self.result, 1)
        self.copy_btn = QPushButton("COPIER LE RÉSUMÉ")
        lay.addWidget(self.copy_btn)

        self.pick_btn.clicked.connect(self._pick)
        self.go_btn.clicked.connect(self._go)
        self.copy_btn.clicked.connect(self._copy)

    def set_file(self, path: str):
        if not tools.is_allowed(path):
            self.path = None
            self.go_btn.setEnabled(False)
            self.file_label.setText(
                f"⚠ Ce fichier est hors des dossiers autorisés (voir ALLOWED_DIRS dans config.py) : {path}")
            return
        self.path = path
        self.file_label.setText(f"◈ {Path(path).name}")
        self.go_btn.setEnabled(True)

    def _pick(self):
        roots = tools.allowed_roots()
        start = str(roots[0]) if roots else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir un document", start,
            "Documents (*.pdf *.docx *.txt *.md *.csv);;Tous les fichiers (*)")
        if path:
            self.set_file(path)

    def _go(self):
        if self.path:
            style = SUMMARY_STYLES[self.style_box.currentText()]
            self.submitted.emit(f"Lis le fichier « {self.path} » avec read_file, puis donne-moi {style}.")

    def _copy(self):
        QGuiApplication.clipboard().setText(self.result.toPlainText())

    def begin(self, _text: str):
        self.result.setPlainText("▮ ANALYSE EN COURS…")
        self.go_btn.setEnabled(False)
        self.pick_btn.setEnabled(False)

    def deliver(self, text: str):
        self.result.setMarkdown(text)
        self.go_btn.setEnabled(self.path is not None)
        self.pick_btn.setEnabled(True)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if urls:
            self.set_file(urls[0])
