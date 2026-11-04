"""Widgets du chat : messages lisibles, blocs de code encadrés avec bouton COPIER."""
import html
import re

from PySide6.QtCore import QRegularExpression, Qt, QTimer
from PySide6.QtGui import (
    QColor, QFont, QFontDatabase, QGuiApplication, QSyntaxHighlighter, QTextCharFormat, QTextOption,
)
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QTextEdit, QVBoxLayout, QWidget,
)

from ui import theme

MAX_MESSAGES = 200
_FENCE = re.compile(r"```([\w+#.-]*)[ \t]*\n?(.*?)```", re.S)


# ------------------------------------------------------------------ Markdown
def soft_wrap(text: str, n: int = 28) -> str:
    """Autorise le retour à la ligne dans les très longs « mots » (URL, chemins...) pour qu'ils
    ne forcent jamais la largeur du chat. Les liens Markdown [txt](url) sont laissés intacts."""
    def fix(m):
        tok = m.group(0)
        if "](" in tok:
            return tok
        return "\u200b".join(tok[i:i + n] for i in range(0, len(tok), n))
    return re.sub(r"\S{%d,}" % (n + 1), fix, text)


def md_to_html(text: str) -> str:
    """**gras**, *italique*, `code`, [liens](url), listes, titres."""
    t = html.escape(soft_wrap(text.strip("\n")))
    t = re.sub(r"`([^`\n]+)`",
               rf'<span style="color:{theme.AMBER}; font-family:Consolas,monospace">\1</span>', t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\*\w])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\*\w])", r"<i>\1</i>", t)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
               rf'<a style="color:{theme.CYAN}" href="\2">\1</a>', t)
    t = re.sub(r"(?m)^\s*[-*]\s+", "• ", t)
    t = re.sub(r"(?m)^#{1,6}\s*(.+)$", rf'<b style="color:{theme.CYAN}">\1</b>', t)
    return t.replace("\n", "<br>")


def split_blocks(text: str) -> list:
    """[('text', str) | ('code', (langue, code))] dans l'ordre."""
    blocks, pos = [], 0
    for m in _FENCE.finditer(text):
        if m.start() > pos:
            blocks.append(("text", text[pos:m.start()]))
        blocks.append(("code", (m.group(1), m.group(2).rstrip("\n"))))
        pos = m.end()
    if pos < len(text):
        blocks.append(("text", text[pos:]))
    return [b for b in blocks if b[0] == "code" or b[1].strip()]


# ------------------------------------------------------------ Coloration code
_KEYWORDS = (
    "def class return if elif else for while import from as with try except finally raise "
    "lambda yield async await pass break continue in is not and or None True False self "
    "function const let var new this typeof null true false undefined export default "
    "public private static void int float double char string bool struct enum switch case "
    "fn mut impl use pub match package interface extends implements throw catch echo SELECT FROM WHERE"
).split()
_HASH_LANGS = {"python", "py", "bash", "sh", "shell", "zsh", "yaml", "yml", "toml", "ruby", "rb",
               "powershell", "ps1", "dockerfile", "ini", ""}


class CodeHighlighter(QSyntaxHighlighter):
    def __init__(self, doc, lang: str):
        super().__init__(doc)

        def fmt(color, bold=False):
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(QFont.Weight.Bold)
            return f

        comment = r"#[^\n]*" if lang.lower() in _HASH_LANGS else r"//[^\n]*"
        self.rules = [
            (QRegularExpression(r"\b(" + "|".join(_KEYWORDS) + r")\b"), fmt(theme.MAGENTA, True)),
            (QRegularExpression(r"\b\d+(\.\d+)?\b"), fmt(theme.AMBER)),
            (QRegularExpression(r'"[^"\\\n]*(\\.[^"\\\n]*)*"|\'[^\'\\\n]*(\\.[^\'\\\n]*)*\''), fmt("#8be28b")),
            (QRegularExpression(comment), fmt(theme.DIM)),
        ]

    def highlightBlock(self, text):
        for rx, f in self.rules:
            it = rx.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), f)


def _copy_to_clipboard(text: str, button: QPushButton, label="COPIER"):
    QGuiApplication.clipboard().setText(text)
    button.setText("✓ COPIÉ")
    QTimer.singleShot(1500, lambda: button.setText(label))


# ---------------------------------------------------------------- Bloc de code
class CodeBlock(QFrame):
    def __init__(self, code: str, lang: str = ""):
        super().__init__()
        self.setObjectName("code")
        self.code = code
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        head = QFrame()
        head.setObjectName("codehead")
        row = QHBoxLayout(head)
        row.setContentsMargins(8, 3, 6, 3)
        name = QLabel((lang or "code").upper())
        name.setObjectName("dim")
        btn = QPushButton("COPIER")
        btn.setObjectName("copy")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: _copy_to_clipboard(self.code, btn))
        row.addWidget(name)
        row.addStretch()
        row.addWidget(btn)
        lay.addWidget(head)

        self.edit = QTextEdit()
        self.edit.setObjectName("codeedit")
        self.edit.setReadOnly(True)
        self.edit.setFrameShape(QFrame.Shape.NoFrame)
        self.edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)    # les longues lignes passent à la ligne
        self.edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setPointSize(10)
        self.edit.setFont(font)
        opt = QTextOption()
        opt.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.edit.document().setDefaultTextOption(opt)
        self.edit.document().setDocumentMargin(6)
        self.edit.setTabStopDistance(4 * self.edit.fontMetrics().horizontalAdvance(" "))
        self.edit.setPlainText(code)
        CodeHighlighter(self.edit.document(), lang)
        lines = code.count("\n") + 1
        self.edit.setFixedHeight(lines * self.edit.fontMetrics().lineSpacing() + 16)   # estimation initiale
        lay.addWidget(self.edit)

    def _fit(self):
        """Hauteur exacte du code une fois les lignes longues repliées."""
        doc = self.edit.document()
        doc.setTextWidth(max(50, self.edit.viewport().width()))
        h = int(doc.size().height()) + 4
        if h != self.edit.height():
            self.edit.setFixedHeight(h)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()

    def showEvent(self, e):
        super().showEvent(e)
        self._fit()


# --------------------------------------------------------------------- Message
class MessageWidget(QFrame):
    def __init__(self, who: str, color: str, text: str, markdown: bool = True, copyable: bool = False):
        super().__init__()
        self.setObjectName("msg")
        self.setStyleSheet(f"QFrame#msg {{ border-left: 2px solid {color}; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 8, 8)
        lay.setSpacing(6)

        head = QHBoxLayout()
        who_lbl = QLabel(who)
        who_lbl.setStyleSheet(f"color:{color}; font-weight:bold; font-size:12px; border:none;")
        head.addWidget(who_lbl)
        head.addStretch()
        if copyable:
            btn = QPushButton("COPIER TOUT")
            btn.setObjectName("copy")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda: _copy_to_clipboard(text, btn, "COPIER TOUT"))
            head.addWidget(btn)
        lay.addLayout(head)

        blocks = split_blocks(text) if markdown else [("text", text)]
        for kind, content in blocks:
            if kind == "code":
                lay.addWidget(CodeBlock(content[1], content[0]))
            else:
                lbl = QLabel(md_to_html(content) if markdown
                             else html.escape(soft_wrap(content)).replace("\n", "<br>"))
                lbl.setTextFormat(Qt.TextFormat.RichText)
                lbl.setWordWrap(True)
                lbl.setStyleSheet("border:none;")
                lbl.setMinimumWidth(0)
                lbl.setOpenExternalLinks(True)
                lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse
                                            | Qt.TextInteractionFlag.LinksAccessibleByMouse)
                lay.addWidget(lbl)


class TypingIndicator(QLabel):
    def __init__(self):
        super().__init__("● ○ ○")
        self.setObjectName("dim")
        self._n = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(350)

    def _tick(self):
        self._n = (self._n + 1) % 3
        self.setText(" ".join("●" if i == self._n else "○" for i in range(3)) + "  réflexion…")


# ------------------------------------------------------------------ Vue du chat
class ChatView(QScrollArea):
    """Liste défilante de messages (plus de problème d'affichage quand il y en a beaucoup)."""

    def __init__(self):
        super().__init__()
        self.setObjectName("chatview")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        self.lay = QVBoxLayout(body)
        self.lay.setContentsMargins(6, 6, 6, 6)
        self.lay.setSpacing(8)
        self.lay.addStretch()
        self.setWidget(body)
        body.setAutoFillBackground(False)

    def add(self, widget: QWidget):
        self.lay.insertWidget(self.lay.count() - 1, widget)
        while self.lay.count() - 1 > MAX_MESSAGES:        # on garde la mémoire raisonnable
            old = self.lay.takeAt(0).widget()
            if old:
                old.deleteLater()
        QTimer.singleShot(40, self.to_bottom)

    def to_bottom(self):
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())

    def add_notice(self, text: str):
        lbl = QLabel(f"⚠ {text}")
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color:{theme.AMBER}; font-size:11px;")
        self.add(lbl)
