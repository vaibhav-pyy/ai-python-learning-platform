"""
widgets.py — Reusable UI building blocks shared by every screen.
"""

import keyword
import re

from PyQt5.QtCore import QRect, QSize, Qt, pyqtSignal
from PyQt5.QtGui import (
    QColor, QFont, QPainter, QSyntaxHighlighter, QTextCharFormat, QTextCursor, QTextFormat,
)
from PyQt5.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QTextBrowser, QTextEdit, QVBoxLayout, QWidget,
)

from ui import theme


# ── Small helpers ────────────────────────────────────────────────────────────

def repolish(widget: QWidget):
    """Re-apply the stylesheet after a dynamic property changed."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def label(text: str = "", role: str = "body", wrap: bool = False, selectable: bool = False) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("role", role)
    lbl.setWordWrap(wrap)
    if selectable:
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return lbl


def button(text: str, variant: str = "secondary", on_click=None, tooltip: str = "",
           size: str = "") -> QPushButton:
    btn = QPushButton(text)
    if variant != "secondary":
        btn.setProperty("variant", variant)
    if size:
        btn.setProperty("size", size)
    btn.setCursor(Qt.PointingHandCursor)
    if tooltip:
        btn.setToolTip(tooltip)
    if on_click is not None:
        btn.clicked.connect(on_click)
    return btn


def scrollable(content: QWidget) -> QScrollArea:
    """Wrap `content` in a frameless vertical scroll area."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    area.setWidget(content)
    return area


def style_tabs(tabs):
    """Tab captions use a semibold font set in code (not QSS) so Qt sizes them correctly."""
    tabs.setDocumentMode(True)
    tabs.tabBar().setFont(theme.ui_font(10, QFont.DemiBold))
    tabs.tabBar().setExpanding(False)


def divider() -> QFrame:
    line = QFrame()
    line.setObjectName("divider")
    line.setFrameShape(QFrame.NoFrame)
    return line


class Card(QFrame):
    """White rounded surface with a vertical layout."""

    def __init__(self, parent=None, margins=(18, 16, 18, 16), spacing=10):
        super().__init__(parent)
        self.setProperty("card", True)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(*margins)
        self.body.setSpacing(spacing)


class Badge(QLabel):
    """Small pill label. Tone: neutral, primary, success, warning, error."""

    def __init__(self, text: str = "", tone: str = "neutral", parent=None):
        super().__init__(text, parent)
        self.setProperty("badge", tone)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

    def set_badge(self, text: str, tone: str):
        self.setText(text)
        if self.property("badge") != tone:
            self.setProperty("badge", tone)
            repolish(self)


class Banner(QFrame):
    """Inline status message (info / success / warning / error).

    The tone is conveyed by an icon glyph and the wording, not only by colour.
    """

    _ICONS = {"info": "i", "success": "✓", "warning": "!", "error": "×"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("banner")
        self.setProperty("tone", "info")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 9, 12, 9)
        lay.setSpacing(10)
        self._icon = QLabel()
        self._icon.setObjectName("bannerIcon")
        self._icon.setFixedWidth(14)
        self._icon.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        lay.addWidget(self._icon)
        self._text = QLabel()
        self._text.setWordWrap(True)
        self._text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._text.setTextFormat(Qt.PlainText)
        lay.addWidget(self._text, 1)
        self.setAccessibleName("Status message")
        self.hide()

    def show_message(self, tone: str, text: str):
        self._icon.setText(self._ICONS.get(tone, "i"))
        self._text.setText(text)
        self.setAccessibleDescription(f"{tone}: {text}")
        if self.property("tone") != tone:
            self.setProperty("tone", tone)
            repolish(self)
            for child in (self._icon, self._text):
                repolish(child)
        self.show()

    def clear(self):
        self._text.clear()
        self.hide()

    def resizeEvent(self, event):
        # Reserve enough height for the wrapped text so narrow panels never clip it.
        super().resizeEvent(event)
        needed = self.layout().heightForWidth(self.width())
        if needed > 0 and needed != self.minimumHeight():
            self.setMinimumHeight(needed)


class BusyBar(QProgressBar):
    """Thin indeterminate progress bar shown while background work runs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(0, 0)
        self.setTextVisible(False)
        self.setAccessibleName("Working")
        self.hide()


class EmptyState(QWidget):
    """Centered title + explanation for screens/lists with no content."""

    def __init__(self, title: str, description: str = "", parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(6)
        lay.addStretch()
        self.title = label(title, "h2")
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setWordWrap(True)
        lay.addWidget(self.title)
        self.description = label(description, "muted", wrap=True)
        self.description.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.description)
        lay.addStretch()


class HeaderBar(QFrame):
    """Top application bar: product mark, workspace name, user and sign-out."""

    logout_clicked = pyqtSignal()

    def __init__(self, workspace: str, display_name: str, role: str, parent=None):
        super().__init__(parent)
        self.setObjectName("headerBar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(24, 12, 24, 12)
        lay.setSpacing(12)

        mark = QLabel("Py")
        mark.setObjectName("appMark")
        mark.setFixedSize(36, 36)
        mark.setAlignment(Qt.AlignCenter)
        mark.setAccessibleName("AI Python Learning Platform")
        lay.addWidget(mark)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(label("AI Python Learning Platform", "h3"))
        titles.addWidget(label(workspace, "caption"))
        lay.addLayout(titles)
        lay.addStretch()

        lay.addWidget(label(display_name, "body"))
        lay.addWidget(Badge(role, "primary"))
        lay.addSpacing(4)
        logout = button("Sign out", "ghost", self.logout_clicked.emit,
                        tooltip="Sign out and return to the login screen")
        lay.addWidget(logout)


class AuthPage(QWidget):
    """Shared layout for the sign-in and sign-up screens.

    A brand header above a centered card; the whole page scrolls on short
    windows. Subclasses add their form to `self.form`.
    """

    def __init__(self, heading: str, subheading: str, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)

        page = QWidget()
        scroll.setWidget(page)
        col = QVBoxLayout(page)
        col.setContentsMargins(16, 32, 16, 32)
        col.setSpacing(0)
        col.addStretch(1)

        brand = QHBoxLayout()
        brand.addStretch()
        mark = QLabel("Py")
        mark.setObjectName("appMark")
        mark.setFixedSize(40, 40)
        mark.setAlignment(Qt.AlignCenter)
        brand.addWidget(mark)
        brand.addSpacing(10)
        brand.addWidget(label("AI Python Learning Platform", "h2"))
        brand.addStretch()
        col.addLayout(brand)
        col.addSpacing(6)
        tagline = label("Practise Python with guided hints and AI code feedback.", "muted")
        tagline.setAlignment(Qt.AlignCenter)
        col.addWidget(tagline)
        col.addSpacing(22)

        card = Card(margins=(32, 28, 32, 28), spacing=0)
        card.setFixedWidth(420)
        card.body.addWidget(label(heading, "title"))
        card.body.addSpacing(4)
        card.body.addWidget(label(subheading, "muted", wrap=True))
        card.body.addSpacing(18)
        self.form = card.body

        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(card)
        row.addStretch()
        col.addLayout(row)

        self.footer = QVBoxLayout()
        self.footer.setContentsMargins(0, 16, 0, 0)
        col.addLayout(self.footer)
        col.addStretch(2)

    def add_field(self, caption: str, widget: QWidget, error: QLabel = None):
        """Add a labelled input (and optional inline error) to the form."""
        lbl = label(caption, "field")
        lbl.setBuddy(widget)
        self.form.addWidget(lbl)
        self.form.addSpacing(5)
        self.form.addWidget(widget)
        if error is not None:
            self.form.addSpacing(3)
            self.form.addWidget(error)
        self.form.addSpacing(12)


def text_input(placeholder: str = "", password: bool = False, accessible_name: str = ""):
    inp = QLineEdit()
    inp.setPlaceholderText(placeholder)
    inp.setMinimumHeight(40)
    if password:
        inp.setEchoMode(QLineEdit.Password)
    if accessible_name:
        inp.setAccessibleName(accessible_name)
    return inp


def set_invalid(widget: QWidget, invalid: bool):
    if bool(widget.property("invalid")) != invalid:
        widget.setProperty("invalid", invalid)
        repolish(widget)


# ── Rich text view ───────────────────────────────────────────────────────────



class MarkdownView(QTextBrowser):
    """Read-only view that renders LLM Markdown (headings, lists, code)."""

    def __init__(self, parent=None, auto_height: bool = False):
        super().__init__(parent)
        self.setOpenExternalLinks(True)
        self.document().setDocumentMargin(2)
        self.setFont(theme.ui_font(10.5))
        if auto_height:
            # Grow to fit the content and let an enclosing scroll area scroll.
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            self.document().documentLayout().documentSizeChanged.connect(
                lambda size: self.setMinimumHeight(int(size.height()) + 6))

    def set_markdown(self, text: str):
        self.setMarkdown(text or "")
        self._style_code()

    def _style_code(self):
        """Give inline code and code blocks a monospace font and tinted background.

        Qt's Markdown importer marks code as fixed-pitch but uses the system
        fixed font and no background; CSS does not apply to Markdown input.
        """
        doc = self.document()
        mono = theme.mono_font(10)
        code_blocks, ranges = [], []          # collect first; editing invalidates iterators
        block = doc.begin()
        while block.isValid():
            fmt = block.blockFormat()
            is_code_block = (fmt.hasProperty(QTextFormat.BlockCodeFence)
                             or fmt.hasProperty(QTextFormat.BlockCodeLanguage))
            if is_code_block:
                code_blocks.append(block.position())
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                cf = frag.charFormat()
                if frag.isValid() and (is_code_block or cf.fontFixedPitch()
                                       or cf.hasProperty(QTextFormat.FontFixedPitch)):
                    ranges.append((frag.position(), frag.position() + frag.length(), is_code_block))
                it += 1
            block = block.next()

        for pos in code_blocks:
            cursor = QTextCursor(doc.findBlock(pos))
            bf = cursor.blockFormat()
            bf.setBackground(QColor("#F1F5F9"))
            cursor.setBlockFormat(bf)
        for start, end, in_block in ranges:
            cursor = QTextCursor(doc)
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)
            fmt = QTextCharFormat()
            fmt.setFontFamily(mono.family())
            fmt.setFontFamilies(theme.MONO_FONT_FAMILIES)
            fmt.setFontPointSize(mono.pointSizeF())
            if not in_block:
                fmt.setBackground(QColor("#EEF2F6"))
            cursor.mergeCharFormat(fmt)

    def set_plain(self, text: str):
        self.setPlainText(text or "")


# ── Code editor ──────────────────────────────────────────────────────────────

class PythonHighlighter(QSyntaxHighlighter):
    """Lightweight Python syntax highlighting for the dark editor."""

    def __init__(self, document):
        super().__init__(document)

        def fmt(color, bold=False, italic=False):
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(700)
            f.setFontItalic(italic)
            return f

        builtins = ("print", "input", "len", "range", "int", "str", "float", "list", "dict",
                    "set", "tuple", "sum", "min", "max", "abs", "sorted", "enumerate", "zip",
                    "map", "filter", "open", "bool", "round", "type", "isinstance", "reversed")
        # (pattern, format, regex group to colour)
        self._rules = [
            (re.compile(r"\b(" + "|".join(keyword.kwlist) + r")\b"), fmt(theme.SYNTAX_KEYWORD, bold=True), 0),
            (re.compile(r"\b(" + "|".join(builtins) + r")\b"), fmt(theme.SYNTAX_BUILTIN), 0),
            (re.compile(r"\b(?:def|class)\s+(\w+)"), fmt(theme.SYNTAX_DEF), 1),
            (re.compile(r"\b\d+(\.\d+)?\b"), fmt(theme.SYNTAX_NUMBER), 0),
        ]
        self._string = (re.compile(r"(\"[^\"\\]*(\\.[^\"\\]*)*\"|'[^'\\]*(\\.[^'\\]*)*')"),
                        fmt(theme.SYNTAX_STRING))
        self._comment = (re.compile(r"#[^\n]*"), fmt(theme.SYNTAX_COMMENT, italic=True))

    def highlightBlock(self, text):
        for pattern, f, group in self._rules:
            for m in pattern.finditer(text):
                start, end = m.span(group)
                self.setFormat(start, end - start, f)
        # Strings, then comments (a '#' inside a string is not a comment)
        string_spans = []
        pattern, f = self._string
        for m in pattern.finditer(text):
            string_spans.append(m.span())
            self.setFormat(m.start(), m.end() - m.start(), f)
        pattern, f = self._comment
        for m in pattern.finditer(text):
            if any(s <= m.start() < e for s, e in string_spans):
                continue
            self.setFormat(m.start(), len(text) - m.start(), f)
            break


class _LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self):
        return QSize(self._editor.line_number_width(), 0)

    def paintEvent(self, event):
        self._editor.paint_line_numbers(event)


class CodeEditor(QPlainTextEdit):
    """Plain-text Python editor with line numbers and syntax highlighting.

    Plain text only: pasted content never carries rich formatting.
    The Tab key inserts a tab character (displayed 4 spaces wide); no
    auto-indent is performed, so every character in the editor corresponds to
    what the learner typed or pasted — this keeps the keystroke ratio meaningful.
    """

    def __init__(self, parent=None, read_only: bool = False):
        super().__init__(parent)
        self.setObjectName("codeEditor")
        self.setFont(theme.mono_font(11))
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        self.setReadOnly(read_only)
        self.setAccessibleName("Code editor" if not read_only else "Submitted code")

        self._gutter = _LineNumberArea(self)
        self._highlighter = PythonHighlighter(self.document())
        self.blockCountChanged.connect(self._update_margins)
        self.updateRequest.connect(self._update_gutter)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._update_margins()
        self._highlight_current_line()

    def line_number_width(self) -> int:
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 16 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_margins(self, *_):
        self.setViewportMargins(self.line_number_width(), 0, 0, 0)

    def _update_gutter(self, rect, dy):
        if dy:
            self._gutter.scroll(0, dy)
        else:
            self._gutter.update(0, rect.y(), self._gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_margins()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._gutter.setGeometry(QRect(cr.left(), cr.top(), self.line_number_width(), cr.height()))

    def _highlight_current_line(self):
        if self.isReadOnly():
            self.setExtraSelections([])
            return
        sel = QTextEdit.ExtraSelection()
        sel.format.setBackground(QColor(theme.EDITOR_CURRENT_LINE))
        sel.format.setProperty(QTextFormat.FullWidthSelection, True)
        sel.cursor = self.textCursor()
        sel.cursor.clearSelection()
        self.setExtraSelections([sel])

    def paint_line_numbers(self, event):
        painter = QPainter(self._gutter)
        painter.fillRect(event.rect(), QColor(theme.EDITOR_GUTTER))
        painter.setFont(self.font())
        block = self.firstVisibleBlock()
        number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        current = self.textCursor().blockNumber()
        height = self.fontMetrics().height()
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.setPen(QColor(theme.EDITOR_TEXT if number == current else theme.EDITOR_LINE_NUMBER))
                painter.drawText(0, top, self._gutter.width() - 8, height,
                                 Qt.AlignRight, str(number + 1))
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            number += 1
