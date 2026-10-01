"""
theme.py — Design tokens and the global Qt stylesheet.

Every screen uses the same palette, type scale and component styles defined
here. Widgets opt into variants with dynamic properties instead of styling
themselves, e.g.:

    label.setProperty("role", "title")        # typography
    button.setProperty("variant", "primary")  # button style
    frame.setProperty("card", True)           # white card surface
    banner.setProperty("tone", "warning")     # status colours
"""

from PyQt5.QtGui import QColor, QFont, QPalette

# ── Colour tokens ────────────────────────────────────────────────────────────
BG = "#F3F5F9"
SURFACE = "#FFFFFF"
SURFACE_ALT = "#F8FAFC"
BORDER = "#E2E8F0"
BORDER_STRONG = "#CBD5E1"

TEXT = "#0F172A"
TEXT_SECONDARY = "#334155"
MUTED = "#5B6B82"          # ≥ 4.5:1 on white and on BG

PRIMARY = "#4F46E5"
PRIMARY_HOVER = "#4338CA"
PRIMARY_PRESSED = "#3730A3"
PRIMARY_SOFT = "#EEF2FF"
PRIMARY_SOFT_HOVER = "#E0E7FF"
PRIMARY_ON_SOFT = "#3730A3"
FOCUS_RING = "#A5B4FC"

SUCCESS = "#15803D"
SUCCESS_SOFT = "#DCFCE7"
SUCCESS_ON_SOFT = "#14532D"
WARNING = "#B45309"
WARNING_SOFT = "#FEF3C7"
WARNING_ON_SOFT = "#78350F"
WARNING_BORDER = "#FCD34D"
DANGER = "#B91C1C"
DANGER_HOVER = "#991B1B"
DANGER_SOFT = "#FEE2E2"
DANGER_ON_SOFT = "#7F1D1D"
INFO_SOFT = "#E0F2FE"
INFO_ON_SOFT = "#0C4A6E"

# Code editor (dark)
EDITOR_BG = "#0F172A"
EDITOR_GUTTER = "#111C33"
EDITOR_TEXT = "#E2E8F0"
EDITOR_LINE_NUMBER = "#64748B"
EDITOR_CURRENT_LINE = "#1E293B"
EDITOR_SELECTION = "#334C7A"

# Syntax colours
SYNTAX_KEYWORD = "#C4B5FD"
SYNTAX_BUILTIN = "#7DD3FC"
SYNTAX_STRING = "#86EFAC"
SYNTAX_NUMBER = "#FDBA74"
SYNTAX_COMMENT = "#7C8BA1"
SYNTAX_DEF = "#FDE68A"

# ── Typography ───────────────────────────────────────────────────────────────
UI_FONT_FAMILIES = ["Segoe UI", "Inter", "Helvetica Neue", "Arial"]
MONO_FONT_FAMILIES = ["Cascadia Mono", "Consolas", "Menlo", "DejaVu Sans Mono", "Courier New"]


def ui_font(point_size: float = 10, weight: int = QFont.Normal) -> QFont:
    font = QFont(UI_FONT_FAMILIES[0])
    font.setFamilies(UI_FONT_FAMILIES)
    font.setPointSizeF(point_size)
    font.setWeight(weight)
    return font


def mono_font(point_size: float = 11) -> QFont:
    font = QFont(MONO_FONT_FAMILIES[0])
    font.setFamilies(MONO_FONT_FAMILIES)
    font.setStyleHint(QFont.TypeWriter)
    font.setFixedPitch(True)
    font.setPointSizeF(point_size)
    return font


def build_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(BG))
    palette.setColor(QPalette.WindowText, QColor(TEXT))
    palette.setColor(QPalette.Base, QColor(SURFACE))
    palette.setColor(QPalette.AlternateBase, QColor(SURFACE_ALT))
    palette.setColor(QPalette.Text, QColor(TEXT))
    palette.setColor(QPalette.Button, QColor(SURFACE))
    palette.setColor(QPalette.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.Highlight, QColor(PRIMARY))
    palette.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ToolTipBase, QColor(TEXT))
    palette.setColor(QPalette.ToolTipText, QColor("#FFFFFF"))
    palette.setColor(QPalette.PlaceholderText, QColor("#8A97AB"))
    palette.setColor(QPalette.Link, QColor(PRIMARY))
    return palette


STYLESHEET = f"""
/* ── Base ─────────────────────────────────────────────────────────────── */
QMainWindow, QStackedWidget#mainStack > QWidget {{
    background-color: {BG};
}}
QToolTip {{
    background-color: {TEXT};
    color: #FFFFFF;
    border: none;
    padding: 6px 8px;
}}

/* ── Typography roles ─────────────────────────────────────────────────── */
QLabel {{ color: {TEXT}; background: transparent; }}
QLabel[role="display"]  {{ font-size: 19pt; font-weight: 700; }}
QLabel[role="title"]    {{ font-size: 15pt; font-weight: 700; }}
QLabel[role="h2"]       {{ font-size: 12pt; font-weight: 600; }}
QLabel[role="h3"]       {{ font-size: 10.5pt; font-weight: 600; }}
QLabel[role="body"]     {{ font-size: 10pt; color: {TEXT_SECONDARY}; }}
QLabel[role="muted"]    {{ font-size: 9.5pt; color: {MUTED}; }}
QLabel[role="caption"]  {{ font-size: 9pt; color: {MUTED}; }}
QLabel[role="overline"] {{ font-size: 8.5pt; font-weight: 700; color: {MUTED}; letter-spacing: 1px; }}
QLabel[role="field"]    {{ font-size: 9.5pt; font-weight: 600; color: {TEXT_SECONDARY}; }}
QLabel[role="stat"]     {{ font-size: 18pt; font-weight: 700; }}
QLabel[role="error"]    {{ font-size: 9pt; color: {DANGER}; }}

/* ── Surfaces ─────────────────────────────────────────────────────────── */
QFrame[card="true"] {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QFrame[card="true"] QLabel {{ border: none; }}
QFrame#headerBar {{
    background-color: {SURFACE};
    border-bottom: 1px solid {BORDER};
}}
QLabel#appMark {{
    background-color: {PRIMARY};
    color: #FFFFFF;
    border-radius: 8px;
    font-size: 11pt;
    font-weight: 800;
}}
QFrame#divider {{
    background-color: {BORDER};
    border: none;
    max-height: 1px;
    min-height: 1px;
}}

/* ── Buttons ──────────────────────────────────────────────────────────── */
QPushButton {{
    background-color: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER_STRONG};
    border-radius: 7px;
    padding: 7px 14px;
    font-size: 10pt;
    font-weight: 600;
    min-height: 20px;
}}
QPushButton:hover {{ background-color: {SURFACE_ALT}; border-color: #94A3B8; }}
QPushButton:pressed {{ background-color: {BORDER}; }}
QPushButton:focus {{ border: 2px solid {FOCUS_RING}; padding: 6px 13px; }}
QPushButton:disabled {{ color: #94A3B8; background-color: {SURFACE_ALT}; border-color: {BORDER}; }}

QPushButton[variant="primary"] {{
    background-color: {PRIMARY}; color: #FFFFFF; border: 1px solid {PRIMARY};
}}
QPushButton[variant="primary"]:hover {{ background-color: {PRIMARY_HOVER}; border-color: {PRIMARY_HOVER}; }}
QPushButton[variant="primary"]:pressed {{ background-color: {PRIMARY_PRESSED}; }}
QPushButton[variant="primary"]:focus {{ border: 2px solid {FOCUS_RING}; }}
QPushButton[variant="primary"]:disabled {{ background-color: #C7CBE8; border-color: #C7CBE8; color: #F8FAFC; }}

QPushButton[variant="soft"] {{
    background-color: {PRIMARY_SOFT}; color: {PRIMARY_ON_SOFT}; border: 1px solid {PRIMARY_SOFT_HOVER};
}}
QPushButton[variant="soft"]:hover {{ background-color: {PRIMARY_SOFT_HOVER}; }}
QPushButton[variant="soft"]:focus {{ border: 2px solid {FOCUS_RING}; }}
QPushButton[variant="soft"]:disabled {{ background-color: {SURFACE_ALT}; color: #94A3B8; border-color: {BORDER}; }}

QPushButton[variant="danger"] {{
    background-color: {SURFACE}; color: {DANGER}; border: 1px solid #FCA5A5;
}}
QPushButton[variant="danger"]:hover {{ background-color: {DANGER_SOFT}; }}
QPushButton[variant="danger"]:focus {{ border: 2px solid #FCA5A5; }}
QPushButton[variant="danger"]:disabled {{ color: #94A3B8; background-color: {SURFACE_ALT}; border-color: {BORDER}; }}

QPushButton[variant="ghost"] {{
    background-color: transparent; color: {TEXT_SECONDARY}; border: 1px solid transparent;
}}
QPushButton[variant="ghost"]:hover {{ background-color: {SURFACE_ALT}; border-color: {BORDER}; }}
QPushButton[variant="ghost"]:focus {{ border: 2px solid {FOCUS_RING}; }}

QPushButton[variant="link"] {{
    background-color: transparent; color: {PRIMARY}; border: none;
    padding: 4px 6px; font-weight: 600; min-height: 0;
}}
QPushButton[variant="link"]:hover {{ color: {PRIMARY_PRESSED}; text-decoration: underline; }}
QPushButton[variant="link"]:focus {{ border: 2px solid {FOCUS_RING}; padding: 2px 4px; }}

QPushButton[size="large"] {{ padding: 10px 18px; font-size: 10.5pt; }}
QPushButton[size="large"]:focus {{ padding: 9px 17px; }}

/* ── Inputs ───────────────────────────────────────────────────────────── */
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {{
    background-color: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER_STRONG};
    border-radius: 7px;
    padding: 8px 11px;
    font-size: 10.5pt;
    selection-background-color: {PRIMARY_SOFT_HOVER};
    selection-color: {TEXT};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{
    border: 2px solid {PRIMARY};
    padding: 7px 10px;
}}
QLineEdit[invalid="true"], QPlainTextEdit[invalid="true"] {{ border: 2px solid {DANGER}; padding: 7px 10px; }}
QComboBox {{ padding: 6px 11px; }}
QComboBox:focus {{ padding: 5px 10px; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE}; border: 1px solid {BORDER_STRONG};
    selection-background-color: {PRIMARY_SOFT}; selection-color: {TEXT}; outline: none;
}}
QCheckBox {{ color: {TEXT_SECONDARY}; spacing: 8px; font-size: 9.5pt; background: transparent; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid #94A3B8; background: {SURFACE};
}}
QCheckBox::indicator:hover {{ border-color: {PRIMARY}; }}
QCheckBox::indicator:focus {{ border: 2px solid {FOCUS_RING}; }}
QCheckBox::indicator:checked {{ background: {SURFACE}; border: 2px solid {PRIMARY}; image: url(:/qt-project.org/styles/commonstyle/images/standardbutton-apply-16.png); }}

/* Read-only rich text (problem statements, AI feedback, hints) */
QTextBrowser {{
    background-color: transparent;
    border: none;
    padding: 0;
    font-size: 10.5pt;
    color: {TEXT};
}}
QTextBrowser:focus {{ border: none; padding: 0; }}

/* Code editor */
QPlainTextEdit#codeEditor {{
    background-color: {EDITOR_BG};
    color: {EDITOR_TEXT};
    border: 1px solid {EDITOR_BG};
    border-radius: 8px;
    padding: 6px 4px;
    selection-background-color: {EDITOR_SELECTION};
    selection-color: #FFFFFF;
}}
QPlainTextEdit#codeEditor:focus {{ border: 2px solid {PRIMARY}; padding: 5px 3px; }}

/* ── Lists & tables ───────────────────────────────────────────────────── */
QListWidget {{
    background-color: transparent;
    border: none;
    outline: none;
    font-size: 10pt;
}}
QListWidget::item {{
    color: {TEXT_SECONDARY};
    padding: 9px 10px;
    margin: 1px 0;
    border-radius: 7px;
    border-left: 3px solid transparent;
}}
QListWidget::item:hover:!selected {{ background-color: {SURFACE_ALT}; }}
QListWidget::item:selected {{
    background-color: {PRIMARY_SOFT};
    color: {PRIMARY_ON_SOFT};
    border-left: 3px solid {PRIMARY};
}}

QTableWidget {{
    background-color: {SURFACE};
    alternate-background-color: {SURFACE_ALT};
    border: none;
    gridline-color: transparent;
    font-size: 10pt;
    outline: none;
    selection-background-color: {PRIMARY_SOFT};
    selection-color: {TEXT};
}}
QTableWidget::item {{ padding: 6px 10px; border-bottom: 1px solid {BORDER}; }}
QTableWidget::item:selected {{ background-color: {PRIMARY_SOFT}; color: {TEXT}; }}
QHeaderView {{ background-color: {SURFACE}; }}
QHeaderView::section {{
    background-color: {SURFACE};
    color: {MUTED};
    font-size: 9pt;
    font-weight: 700;
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid {BORDER_STRONG};
}}
QTableCornerButton::section {{ background: {SURFACE}; border: none; }}

/* ── Tabs ─────────────────────────────────────────────────────────────── */
QTabWidget::pane {{ border: none; }}
QTabBar {{ qproperty-drawBase: 0; }}
QTabBar::tab {{
    background: transparent;
    color: {MUTED};
    padding: 9px 16px;
    margin-right: 4px;
    border: none;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:hover:!selected {{ color: {TEXT}; border-bottom: 2px solid {BORDER_STRONG}; }}
QTabBar::tab:selected {{ color: {PRIMARY}; border-bottom: 2px solid {PRIMARY}; }}
QTabBar::tab:focus {{ color: {PRIMARY_PRESSED}; }}

/* ── Status banners & badges ──────────────────────────────────────────── */
QFrame#banner {{ border-radius: 8px; border: 1px solid transparent; }}
QFrame#banner[tone="info"]    {{ background: {INFO_SOFT};    border-color: #BAE6FD; }}
QFrame#banner[tone="success"] {{ background: {SUCCESS_SOFT}; border-color: #86EFAC; }}
QFrame#banner[tone="warning"] {{ background: {WARNING_SOFT}; border-color: {WARNING_BORDER}; }}
QFrame#banner[tone="error"]   {{ background: {DANGER_SOFT};  border-color: #FCA5A5; }}
QFrame#banner QLabel {{ font-size: 9.5pt; }}
QFrame#banner[tone="info"] QLabel    {{ color: {INFO_ON_SOFT}; }}
QFrame#banner[tone="success"] QLabel {{ color: {SUCCESS_ON_SOFT}; }}
QFrame#banner[tone="warning"] QLabel {{ color: {WARNING_ON_SOFT}; }}
QFrame#banner[tone="error"] QLabel   {{ color: {DANGER_ON_SOFT}; }}
QLabel#bannerIcon {{ font-weight: 800; font-size: 10pt; }}

QLabel[badge] {{
    border-radius: 9px;
    padding: 2px 9px;
    font-size: 8.5pt;
    font-weight: 700;
}}
QLabel[badge="neutral"] {{ background: #EEF2F6; color: {TEXT_SECONDARY}; }}
QLabel[badge="primary"] {{ background: {PRIMARY_SOFT}; color: {PRIMARY_ON_SOFT}; }}
QLabel[badge="success"] {{ background: {SUCCESS_SOFT}; color: {SUCCESS_ON_SOFT}; }}
QLabel[badge="warning"] {{ background: {WARNING_SOFT}; color: {WARNING_ON_SOFT}; }}
QLabel[badge="error"]   {{ background: {DANGER_SOFT};  color: {DANGER_ON_SOFT}; }}

/* Hint ladder steps */
QLabel[step] {{
    border-radius: 6px;
    padding: 5px 8px;
    font-size: 9pt;
}}
QLabel[step="done"]    {{ background: {SUCCESS_SOFT}; color: {SUCCESS_ON_SOFT}; }}
QLabel[step="next"]    {{ background: {PRIMARY_SOFT}; color: {PRIMARY_ON_SOFT}; font-weight: 700; }}
QLabel[step="locked"]  {{ background: {SURFACE_ALT}; color: {MUTED}; }}

/* ── Progress (indeterminate "working" bar) ───────────────────────────── */
QProgressBar {{
    background-color: {PRIMARY_SOFT};
    border: none;
    border-radius: 2px;
    max-height: 4px;
    min-height: 4px;
}}
QProgressBar::chunk {{ background-color: {PRIMARY}; border-radius: 2px; }}

/* ── Splitters & scrollbars ───────────────────────────────────────────── */
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:hover {{ background: {BORDER}; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER_STRONG}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #94A3B8; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {BORDER_STRONG}; border-radius: 3px; min-width: 30px; }}
QScrollBar::handle:horizontal:hover {{ background: #94A3B8; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ── Dialogs ──────────────────────────────────────────────────────────── */
QDialog, QMessageBox {{ background-color: {BG}; }}
QMessageBox QLabel {{ font-size: 10pt; }}
QMessageBox QPushButton {{ min-width: 80px; }}
"""
