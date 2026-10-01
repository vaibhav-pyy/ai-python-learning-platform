"""
instructor_dashboard.py — Instructor workspace.
Two tabs: Questions (create / review / delete) and Submissions (review learner work).
"""

import logging
import sqlite3

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QHBoxLayout, QHeaderView,
    QLineEdit, QMessageBox, QPlainTextEdit, QSplitter, QStackedWidget, QTabWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

import config
from database import add_question, delete_question, get_all_questions, get_all_submissions
from keystroke_monitor import compute_ratio
from ui import theme
from ui.widgets import (
    Badge, Banner, Card, CodeEditor, EmptyState, HeaderBar, MarkdownView,
    button, label, set_invalid, style_tabs,
)

log = logging.getLogger(__name__)

DB_ERROR = "The database could not be read. Please try again or restart the application."


def _integrity_text(flagged: bool) -> str:
    return "Review recommended" if flagged else "Not flagged"


def _learner_display(s: dict) -> str:
    name = (s.get("learner_name") or "").strip()
    return f"{name} ({s['learner_username']})" if name else s["learner_username"]


class _SortItem(QTableWidgetItem):
    """Table item that sorts by an explicit key instead of its display text."""

    def __init__(self, text: str, sort_key=None):
        super().__init__(text)
        self._key = text.lower() if sort_key is None else sort_key

    def __lt__(self, other):
        if isinstance(other, _SortItem):
            try:
                return self._key < other._key
            except TypeError:
                return str(self._key) < str(other._key)
        return super().__lt__(other)


def _make_table(headers):
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(40)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setWordWrap(False)
    table.horizontalHeader().setHighlightSections(False)
    table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    # No sorting until the user clicks a header; rows keep the database order.
    table.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)
    return table


def _stat_tile(caption: str):
    card = Card(margins=(16, 12, 16, 12), spacing=2)
    value = label("0", "stat")
    card.body.addWidget(label(caption, "overline"))
    card.body.addWidget(value)
    return card, value


# ══ Submission detail dialog ═════════════════════════════════════════════════

class SubmissionDetailDialog(QDialog):
    """Full view of one submission: code, AI feedback and integrity stats."""

    def __init__(self, s: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Submission — {s['learner_username']} — {s['question_title']}")
        self.setMinimumSize(680, 520)
        self.resize(980, 680)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        header = label(_learner_display(s), "title", wrap=True, selectable=True)
        layout.addWidget(header)
        layout.addWidget(label(f"{s['question_title']}  ·  submitted {s['submitted_at']}", "muted",
                               wrap=True, selectable=True))

        # Stats row
        ratio = compute_ratio(s["keystroke_count"], s["char_count"])
        ratio_text = f"{ratio:.2f}" if s["char_count"] else "n/a"
        stats = QHBoxLayout()
        stats.setSpacing(10)
        for caption, value in (
            ("HINTS USED", f"{s['hint_count']} / {config.MAX_HINTS}"),
            ("KEYSTROKES (K)", str(s["keystroke_count"])),
            ("CHARACTERS (C)", str(s["char_count"])),
            ("RATIO r = K / C", ratio_text),
        ):
            tile, val = _stat_tile(caption)
            val.setText(value)
            stats.addWidget(tile)
        integrity_tile = Card(margins=(16, 12, 16, 12), spacing=6)
        integrity_tile.body.addWidget(label("INTEGRITY", "overline"))
        integrity_tile.body.addWidget(Badge(_integrity_text(bool(s["flagged_ai"])),
                                            "warning" if s["flagged_ai"] else "success"))
        integrity_tile.body.addStretch()
        stats.addWidget(integrity_tile)
        layout.addLayout(stats)

        if s["flagged_ai"]:
            note = Banner()
            note.show_message(
                "warning",
                f"Typing activity was low relative to the submitted code (r = {ratio_text}, threshold "
                f"{config.INTEGRITY_THRESHOLD}). This can happen when code is pasted. It is a heuristic "
                "signal to guide your review — not evidence of misconduct."
            )
            layout.addWidget(note)

        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(12)

        code_card = Card(spacing=8)
        code_card.body.addWidget(label("Submitted code", "h3"))
        code_box = CodeEditor(read_only=True)
        code_box.setPlainText(s["code"])
        code_card.body.addWidget(code_box, 1)
        split.addWidget(code_card)

        fb_card = Card(spacing=6)
        fb_card.body.addWidget(label("AI feedback", "h3"))
        fb_card.body.addWidget(label("Generated by the AI model from reading the code; the code was not executed.",
                                     "caption", wrap=True))
        fb_view = MarkdownView()
        if s["feedback"]:
            fb_view.set_markdown(s["feedback"])
        else:
            fb_view.set_plain("AI feedback is not available for this submission (the AI service may have "
                              "been unavailable or the review was still in progress).")
        fb_card.body.addWidget(fb_view, 1)
        split.addWidget(fb_card)
        split.setSizes([520, 440])
        layout.addWidget(split, 1)

        row = QHBoxLayout()
        row.addStretch()
        self._close_btn = button("Close", on_click=self.accept)
        self._close_btn.setDefault(True)
        row.addWidget(self._close_btn)
        layout.addLayout(row)

    def showEvent(self, event):
        super().showEvent(event)
        self._close_btn.setFocus()


# ══ Dashboard ════════════════════════════════════════════════════════════════

class InstructorDashboard(QWidget):
    """Instructor dashboard with question management and submission review."""

    logout_requested = pyqtSignal()

    def __init__(self, username: str, display_name: str = "", parent=None):
        super().__init__(parent)
        self.username = username
        self.display_name = display_name or username
        self.setObjectName("instructorDashboard")
        self._questions = []
        self._submissions = {}   # id -> submission dict
        self._build_ui()
        self.refresh_data()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = HeaderBar("Instructor workspace", self.display_name, "Instructor")
        header.logout_clicked.connect(self.logout_requested.emit)
        root.addWidget(header)

        body = QVBoxLayout()
        body.setContentsMargins(20, 8, 20, 20)
        root.addLayout(body, 1)

        self.tabs = QTabWidget()
        style_tabs(self.tabs)
        self.tabs.addTab(self._build_questions_tab(), "Questions")
        self.tabs.addTab(self._build_submissions_tab(), "Submissions")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        body.addWidget(self.tabs, 1)

    # ── Questions tab ────────────────────────────────────────────────────
    def _build_questions_tab(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 14, 0, 0)

        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(14)
        lay.addWidget(split)

        # Create form
        form = Card(margins=(20, 18, 20, 18), spacing=6)
        form.setMinimumWidth(320)
        form.body.addWidget(label("New question", "h2"))
        form.body.addWidget(label("Learners see new questions after they press Refresh in their workspace.",
                                  "caption", wrap=True))
        form.body.addSpacing(10)

        title_lbl = label("Title", "field")
        form.body.addWidget(title_lbl)
        self.q_title = QLineEdit()
        self.q_title.setPlaceholderText("e.g. Reverse a string")
        self.q_title.setAccessibleName("Question title")
        self.q_title.setMaxLength(120)
        self.q_title.textEdited.connect(lambda _: set_invalid(self.q_title, False))
        title_lbl.setBuddy(self.q_title)
        form.body.addWidget(self.q_title)
        form.body.addSpacing(8)

        form.body.addWidget(label("Problem statement", "field"))
        self.q_stmt = QPlainTextEdit()
        self.q_stmt.setPlaceholderText(
            "Describe the task, the expected input and output, and give an example.\n\n"
            "Example:\nWrite a function reverse(s) that returns the string s reversed.\n"
            "reverse(\"abc\") → \"cba\"")
        self.q_stmt.setAccessibleName("Problem statement")
        self.q_stmt.setTabChangesFocus(True)
        self.q_stmt.textChanged.connect(lambda: set_invalid(self.q_stmt, False))
        form.body.addWidget(self.q_stmt, 1)
        form.body.addWidget(label("The AI tutor uses this text when giving hints and reviewing code, "
                                  "so be specific.", "caption", wrap=True))
        form.body.addSpacing(6)

        self.form_banner = Banner()
        form.body.addWidget(self.form_banner)
        create = button("Create question", "primary", self._assign, size="large")
        form.body.addWidget(create)
        split.addWidget(form)

        # Question bank
        bank = Card(margins=(20, 18, 20, 18), spacing=10)
        head = QHBoxLayout()
        head.addWidget(label("Question bank", "h2"))
        self.q_count_badge = Badge("0", "neutral")
        head.addWidget(self.q_count_badge)
        head.addStretch()
        head.addWidget(button("Refresh", "ghost", self._load_questions))
        bank.body.addLayout(head)

        self.questions_table = _make_table(["Title", "Submissions", "Created by"])
        hh = self.questions_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.questions_table.setAccessibleName("Question bank")
        self.questions_table.itemSelectionChanged.connect(self._on_question_selection)

        self.q_empty = EmptyState("No questions yet", "Create your first question with the form on the left.")
        self.q_stack = QStackedWidget()
        self.q_stack.addWidget(self.questions_table)
        self.q_stack.addWidget(self.q_empty)
        bank.body.addWidget(self.q_stack, 3)

        bank.body.addWidget(label("PREVIEW", "overline"))
        self.q_preview = MarkdownView()
        self.q_preview.setAccessibleName("Selected question statement")
        self.q_preview.setMinimumHeight(90)
        bank.body.addWidget(self.q_preview, 2)

        actions = QHBoxLayout()
        self.q_banner = Banner()
        actions.addWidget(self.q_banner, 1)
        actions.addStretch()
        self.delete_btn = button("Delete question…", "danger", self._delete_selected,
                                 tooltip="Delete the selected question and all of its submissions")
        self.delete_btn.setEnabled(False)
        actions.addWidget(self.delete_btn)
        bank.body.addLayout(actions)
        split.addWidget(bank)
        split.setSizes([380, 640])
        return w

    def _assign(self):
        t = self.q_title.text().strip()
        s = self.q_stmt.toPlainText().strip()
        self.form_banner.clear()
        if not t or not s:
            if not s:
                set_invalid(self.q_stmt, True)
                self.q_stmt.setFocus()
            if not t:
                set_invalid(self.q_title, True)
                self.q_title.setFocus()
            missing = " and ".join(x for x, ok in (("a title", t), ("a problem statement", s)) if not ok)
            self.form_banner.show_message("error", f"Please add {missing}.")
            return
        try:
            add_question(t, s, self.username)
        except sqlite3.Error:
            log.exception("Could not create question")
            self.form_banner.show_message("error", "The question could not be saved. Please try again.")
            return
        self.q_title.clear()
        self.q_stmt.clear()
        self.form_banner.show_message("success", f"“{t}” was added to the question bank.")
        self._load_questions()

    def _load_questions(self):
        """Load all questions into the question bank table."""
        try:
            questions = get_all_questions()
        except sqlite3.Error:
            log.exception("Could not load questions")
            self.q_banner.show_message("error", DB_ERROR)
            return
        self.q_banner.clear()
        self._questions = questions

        table = self.questions_table
        table.setSortingEnabled(False)
        table.setRowCount(len(questions))
        for i, q in enumerate(questions):
            title = _SortItem(q["title"])
            title.setData(Qt.UserRole, q["id"])
            title.setToolTip(q["title"])
            table.setItem(i, 0, title)
            count = _SortItem(str(q["submission_count"]), q["submission_count"])
            count.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            table.setItem(i, 1, count)
            table.setItem(i, 2, _SortItem(q["created_by"]))
        table.setSortingEnabled(True)

        self.q_count_badge.set_badge(str(len(questions)), "neutral")
        self.q_stack.setCurrentWidget(table if questions else self.q_empty)
        self._on_question_selection()

    def _selected_question(self):
        rows = self.questions_table.selectionModel().selectedRows()
        if not rows:
            return None
        qid = self.questions_table.item(rows[0].row(), 0).data(Qt.UserRole)
        return next((q for q in self._questions if q["id"] == qid), None)

    def _on_question_selection(self):
        q = self._selected_question()
        self.delete_btn.setEnabled(q is not None)
        if q is None:
            self.q_preview.set_plain("Select a question to preview its problem statement.")
        else:
            self.q_preview.set_plain(f"{q['title']}\n\n{q['problem_statement']}")

    def _delete_selected(self):
        q = self._selected_question()
        if q is None:
            return
        n = q["submission_count"]
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Delete question")
        box.setText(f"Delete “{q['title']}”?")
        box.setInformativeText(
            f"This permanently deletes the question and {n} submission{'s' if n != 1 else ''} for it. "
            "This cannot be undone.")
        delete = box.addButton("Delete", QMessageBox.DestructiveRole)
        cancel = box.addButton("Cancel", QMessageBox.RejectRole)
        box.setDefaultButton(cancel)
        box.exec_()
        if box.clickedButton() is not delete:
            return
        try:
            delete_question(q["id"])
        except sqlite3.Error:
            log.exception("Could not delete question")
            self.q_banner.show_message("error", "The question could not be deleted. Please try again.")
            return
        self._load_questions()
        self.q_banner.show_message("success", f"Deleted “{q['title']}”.")

    # ── Submissions tab ──────────────────────────────────────────────────
    def _build_submissions_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 14, 0, 0)
        lay.setSpacing(12)

        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        tile, self.stat_total = _stat_tile("SUBMISSIONS")
        tiles.addWidget(tile)
        tile, self.stat_learners = _stat_tile("LEARNERS")
        tiles.addWidget(tile)
        tile, self.stat_review = _stat_tile("REVIEW RECOMMENDED")
        tiles.addWidget(tile)
        tile, self.stat_hints = _stat_tile("AVG. HINTS USED")
        tiles.addWidget(tile)
        lay.addLayout(tiles)

        card = Card(margins=(16, 14, 16, 14), spacing=10)
        filters = QHBoxLayout()
        filters.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search learner or question…")
        self.search.setAccessibleName("Search submissions")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filters)
        filters.addWidget(self.search, 2)
        self.question_filter = QComboBox()
        self.question_filter.setAccessibleName("Filter by question")
        self.question_filter.setMinimumWidth(180)
        self.question_filter.currentIndexChanged.connect(self._apply_filters)
        filters.addWidget(self.question_filter, 1)
        self.review_only = QCheckBox("Review recommended only")
        self.review_only.toggled.connect(self._apply_filters)
        filters.addWidget(self.review_only)
        filters.addStretch()
        filters.addWidget(button("Refresh", "ghost", self._load_submissions))
        self.open_btn = button("Open submission", "primary", self._open_selected)
        self.open_btn.setEnabled(False)
        filters.addWidget(self.open_btn)
        card.body.addLayout(filters)

        self.sub_table = _make_table(["Submitted", "Learner", "Question", "Hints", "Ratio (r)",
                                      "Integrity", "AI feedback"])
        hh = self.sub_table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        self.sub_table.setAccessibleName("Submissions")
        self.sub_table.itemSelectionChanged.connect(
            lambda: self.open_btn.setEnabled(bool(self.sub_table.selectionModel().selectedRows())))
        self.sub_table.activated.connect(lambda _: self._open_selected())

        self.sub_empty = EmptyState("No submissions yet", "Learner submissions will appear here.")
        self.sub_stack = QStackedWidget()
        self.sub_stack.addWidget(self.sub_table)
        self.sub_stack.addWidget(self.sub_empty)
        card.body.addWidget(self.sub_stack, 1)

        self.sub_banner = Banner()
        card.body.addWidget(self.sub_banner)
        card.body.addWidget(label(
            f"Integrity uses a keystroke heuristic: r = keystrokes ÷ characters. Submissions with "
            f"r < {config.INTEGRITY_THRESHOLD} are marked “Review recommended”. It highlights work worth "
            "a closer look and does not prove misconduct. Double-click a row to open it.",
            "caption", wrap=True))
        lay.addWidget(card, 1)
        return w

    def _load_submissions(self):
        try:
            subs = get_all_submissions()
        except sqlite3.Error:
            log.exception("Could not load submissions")
            self.sub_banner.show_message("error", DB_ERROR)
            return
        self.sub_banner.clear()
        self._submissions = {s["id"]: s for s in subs}

        # Summary tiles
        self.stat_total.setText(str(len(subs)))
        self.stat_learners.setText(str(len({s["learner_username"] for s in subs})))
        self.stat_review.setText(str(sum(1 for s in subs if s["flagged_ai"])))
        avg = sum(s["hint_count"] for s in subs) / len(subs) if subs else 0
        self.stat_hints.setText(f"{avg:.1f}")

        # Question filter options (keep current choice when possible)
        current = self.question_filter.currentData()
        self.question_filter.blockSignals(True)
        self.question_filter.clear()
        self.question_filter.addItem("All questions", None)
        for title in sorted({s["question_title"] for s in subs}, key=str.lower):
            self.question_filter.addItem(title, title)
        idx = self.question_filter.findData(current)
        self.question_filter.setCurrentIndex(max(0, idx))
        self.question_filter.blockSignals(False)

        table = self.sub_table
        table.setSortingEnabled(False)
        table.setRowCount(len(subs))
        for i, s in enumerate(subs):
            ratio = compute_ratio(s["keystroke_count"], s["char_count"])
            flagged = bool(s["flagged_ai"])

            when = _SortItem(s["submitted_at"], s["submitted_at"])
            when.setData(Qt.UserRole, s["id"])
            table.setItem(i, 0, when)
            table.setItem(i, 1, _SortItem(_learner_display(s)))
            q_item = _SortItem(s["question_title"])
            q_item.setToolTip(s["question_title"])
            table.setItem(i, 2, q_item)
            hints = _SortItem(f"{s['hint_count']} / {config.MAX_HINTS}", s["hint_count"])
            table.setItem(i, 3, hints)
            r_item = _SortItem(f"{ratio:.2f}" if s["char_count"] else "n/a", ratio)
            r_item.setToolTip(f"K = {s['keystroke_count']} keystrokes, C = {s['char_count']} characters")
            table.setItem(i, 4, r_item)
            integrity = _SortItem(("▲ " if flagged else "✓ ") + _integrity_text(flagged), int(flagged))
            integrity.setForeground(QColor(theme.WARNING if flagged else theme.SUCCESS))
            table.setItem(i, 5, integrity)
            table.setItem(i, 6, _SortItem("Ready" if s["feedback"] else "Unavailable"))
        table.setSortingEnabled(True)
        self._apply_filters()

    def _apply_filters(self):
        needle = self.search.text().strip().lower()
        question = self.question_filter.currentData()
        review_only = self.review_only.isChecked()
        table = self.sub_table
        visible = 0
        for row in range(table.rowCount()):
            s = self._submissions.get(table.item(row, 0).data(Qt.UserRole))
            show = s is not None
            if show and needle:
                haystack = f"{s['learner_username']} {s.get('learner_name', '')} {s['question_title']}".lower()
                show = needle in haystack
            if show and question:
                show = s["question_title"] == question
            if show and review_only:
                show = bool(s["flagged_ai"])
            table.setRowHidden(row, not show)
            visible += show

        if not self._submissions:
            self.sub_empty.title.setText("No submissions yet")
            self.sub_empty.description.setText("Learner submissions will appear here.")
        elif visible == 0:
            self.sub_empty.title.setText("No matching submissions")
            self.sub_empty.description.setText("Try clearing the search or filters.")
        self.sub_stack.setCurrentWidget(table if visible else self.sub_empty)

    def _open_selected(self):
        rows = self.sub_table.selectionModel().selectedRows()
        if not rows:
            return
        sid = self.sub_table.item(rows[0].row(), 0).data(Qt.UserRole)
        if sid in self._submissions:
            SubmissionDetailDialog(self._submissions[sid], self).exec_()

    # ── Shared ───────────────────────────────────────────────────────────
    def _on_tab_changed(self, idx):
        if idx == 0:
            self._load_questions()
        elif idx == 1:
            self._load_submissions()

    def refresh_data(self):
        self._load_questions()
        self._load_submissions()
