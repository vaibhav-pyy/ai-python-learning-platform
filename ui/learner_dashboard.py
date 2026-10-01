"""
learner_dashboard.py — Learner workspace.

Layout:  [Problems list] | [Problem statement + code editor] | [Hints / AI feedback]

Each problem keeps its own session state while the learner is signed in
(draft code, hints received, keystrokes, last feedback), so switching between
problems never loses work, and hint limits cannot be reset by re-selecting a
problem. LLM requests run on background threads; results are routed back to
the problem they belong to, even if the learner has moved on.
"""

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from PyQt5.QtCore import QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QIcon, QKeySequence, QPainter, QPainterPath, QPen, QPixmap
from PyQt5.QtWidgets import (
    QApplication, QHBoxLayout, QListWidget, QListWidgetItem, QMessageBox,
    QShortcut, QSplitter, QStackedWidget, QStyle, QTabWidget, QVBoxLayout, QWidget,
)

import config
import llm_client
from database import (
    get_all_questions, get_submitted_question_ids, save_submission, set_submission_feedback,
)
from keystroke_monitor import KeystrokeMonitor, compute_ratio, needs_review
from ui import theme
from ui.widgets import (
    Badge, Banner, BusyBar, Card, CodeEditor, EmptyState, HeaderBar, MarkdownView,
    button, divider, label, repolish, scrollable, style_tabs,
)
from ui.workers import BackgroundTask

log = logging.getLogger(__name__)

INTEGRITY_EXPLANATION = (
    "The integrity indicator compares how many keys were pressed while this problem "
    "was open (K) with the number of characters in your code (C).\n\n"
    f"If the ratio r = K / C is below {config.INTEGRITY_THRESHOLD}, the submission is marked "
    "\"review recommended\" for your instructor. This usually means a lot of code appeared "
    "with little typing (for example, pasting).\n\n"
    "It is an automated heuristic to help your instructor decide what to look at. "
    "It is not a judgement about you, and it cannot prove where code came from."
)


@dataclass
class _ProblemSession:
    """Per-problem state kept for the duration of the login session."""
    question: dict
    code: str = ""
    banked_keystrokes: int = 0              # keystrokes from earlier visits to this problem
    hints: list = field(default_factory=list)
    hint_pending: bool = False
    hint_error: str = ""
    eval_pending: bool = False
    feedback: Optional[str] = None
    feedback_error: str = ""
    last_submission: Optional[dict] = None
    submitted_code: Optional[str] = None

    @property
    def qid(self) -> int:
        return self.question["id"]


def _status_icon(done: bool) -> QIcon:
    """Small list icon: filled check circle (submitted) or hollow circle."""
    size = 18
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    rect = QRectF(2, 2, size - 4, size - 4)
    if done:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.SUCCESS))
        p.drawEllipse(rect)
        pen = QPen(QColor("#FFFFFF"), 2)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        path = QPainterPath(QPointF(5.5, 9.2))
        path.lineTo(QPointF(8, 11.6))
        path.lineTo(QPointF(12.5, 6.6))
        p.drawPath(path)
    else:
        p.setPen(QPen(QColor(theme.BORDER_STRONG), 1.6))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(rect)
    p.end()
    icon = QIcon()
    icon.addPixmap(pm, QIcon.Normal)
    icon.addPixmap(pm, QIcon.Selected)  # no selection tint
    return icon


class LearnerDashboard(QWidget):
    """Learner dashboard with problem list, code editor, hints and feedback."""

    logout_requested = pyqtSignal()

    def __init__(self, username: str, display_name: str = "", parent=None):
        super().__init__(parent)
        self.username = username
        self.display_name = display_name or username
        self.setObjectName("learnerDashboard")

        self.keystroke_monitor = KeystrokeMonitor()
        self._monitor_started = False
        self._sessions = {}             # question id -> _ProblemSession
        self._current: Optional[_ProblemSession] = None
        self._submitted_ids = set()
        self._icon_done = _status_icon(True)
        self._icon_todo = _status_icon(False)

        app = QApplication.instance()
        if app is not None:
            app.applicationStateChanged.connect(self._on_app_state_changed)
            self.keystroke_monitor.set_window_active(app.applicationState() == Qt.ApplicationActive)

        # Live integrity indicator refresh
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(1000)
        self.status_timer.timeout.connect(self._update_integrity_indicator)

        self._build_ui()

    # ══ UI construction ═══════════════════════════════════════════════════
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = HeaderBar("Learner workspace", self.display_name, "Learner")
        header.logout_clicked.connect(self._on_logout)
        root.addWidget(header)

        body = QVBoxLayout()
        body.setContentsMargins(20, 16, 20, 20)
        body.setSpacing(12)
        root.addLayout(body, 1)

        self.config_banner = Banner()
        body.addWidget(self.config_banner)
        if not llm_client.is_configured():
            self.config_banner.show_message(
                "warning",
                "AI hints and feedback are not available because HF_TOKEN is not configured. "
                "You can still write and submit code; submissions are saved without AI feedback."
            )

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(12)
        splitter.addWidget(self._build_problem_list())
        splitter.addWidget(self._build_workspace())
        splitter.addWidget(self._build_assistant())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([240, 680, 360])
        body.addWidget(splitter, 1)

        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._submit_code)
        QShortcut(QKeySequence("Ctrl+Shift+H"), self, activated=self._request_hint)

    def _build_problem_list(self):
        card = Card(margins=(12, 14, 12, 12), spacing=8)
        card.setMinimumWidth(190)

        head = QHBoxLayout()
        head.setContentsMargins(6, 0, 0, 0)
        head.addWidget(label("Problems", "h2"))
        self.count_badge = Badge("0", "neutral")
        head.addWidget(self.count_badge)
        head.addStretch()
        refresh = button("", "ghost", self.load_questions,
                         tooltip="Refresh problems assigned by your instructor")
        refresh.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        refresh.setAccessibleName("Refresh problems")
        head.addWidget(refresh)
        card.body.addLayout(head)

        self.question_list = QListWidget()
        self.question_list.setAccessibleName("Problems")
        self.question_list.setWordWrap(True)
        self.question_list.setIconSize(QSize(18, 18))
        self.question_list.currentItemChanged.connect(self._on_question_selected)

        self.list_empty = EmptyState("No problems yet",
                                     "Your instructor hasn't assigned any problems. Use Refresh to check again.")
        self.list_stack = QStackedWidget()
        self.list_stack.addWidget(self.question_list)
        self.list_stack.addWidget(self.list_empty)
        card.body.addWidget(self.list_stack, 1)
        return card

    def _build_workspace(self):
        self.workspace_stack = QStackedWidget()
        self.workspace_stack.setMinimumWidth(420)

        empty_card = Card()
        empty_card.body.addWidget(EmptyState(
            "Select a problem to begin",
            "Choose a problem from the list on the left. Its description appears here, "
            "with a code editor underneath where you write your solution."
        ))
        self.workspace_stack.addWidget(empty_card)

        split = QSplitter(Qt.Vertical)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(12)

        # Problem statement
        problem = Card(spacing=6)
        problem.setMinimumHeight(110)
        problem.body.addWidget(label("PROBLEM", "overline"))
        self.q_title_label = label("", "title", wrap=True, selectable=True)
        problem.body.addWidget(self.q_title_label)
        self.q_stmt_view = MarkdownView()
        self.q_stmt_view.setAccessibleName("Problem statement")
        problem.body.addWidget(self.q_stmt_view, 1)
        split.addWidget(problem)

        # Editor
        editor_card = Card(spacing=10)
        head = QHBoxLayout()
        head.addWidget(label("Your solution", "h3"))
        head.addWidget(label("Python", "caption"))
        head.addStretch()
        self.char_label = label("", "caption")
        head.addWidget(self.char_label)
        editor_card.body.addLayout(head)

        self.code_editor = CodeEditor()
        self.code_editor.setPlaceholderText("# Write your Python solution here")
        self.code_editor.setMinimumHeight(160)
        self.code_editor.textChanged.connect(self._update_char_label)
        editor_card.body.addWidget(self.code_editor, 1)

        integrity = QHBoxLayout()
        integrity.setSpacing(8)
        self.integrity_badge = Badge("Typing activity: —", "neutral")
        self.integrity_badge.setAccessibleName("Integrity indicator")
        integrity.addWidget(self.integrity_badge)
        self.integrity_detail = label("", "caption")
        integrity.addWidget(self.integrity_detail)
        integrity.addStretch()
        about = button("What's this?", "link", self._explain_integrity,
                       tooltip="How the integrity indicator works")
        integrity.addWidget(about)
        editor_card.body.addLayout(integrity)
        editor_card.body.addWidget(divider())

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addStretch()

        self.hint_btn = button("Get hint", "soft", self._request_hint,
                               tooltip="Ask the AI tutor for the next hint (Ctrl+Shift+H)")
        actions.addWidget(self.hint_btn)
        self.submit_btn = button("Submit for AI review", "primary", self._submit_code,
                                 tooltip="Save your solution and request AI feedback (Ctrl+Enter)")
        actions.addWidget(self.submit_btn)
        editor_card.body.addLayout(actions)

        self.editor_banner = Banner()
        editor_card.body.addWidget(self.editor_banner)
        split.addWidget(editor_card)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([210, 460])

        self.workspace_stack.addWidget(split)
        return self.workspace_stack

    def _build_assistant(self):
        card = Card(margins=(14, 10, 14, 14), spacing=8)
        card.setMinimumWidth(280)

        self.assistant_tabs = QTabWidget()
        style_tabs(self.assistant_tabs)
        self.assistant_tabs.addTab(self._build_hints_tab(), "Hints")
        self.assistant_tabs.addTab(self._build_feedback_tab(), "AI feedback")
        card.body.addWidget(self.assistant_tabs, 1)
        return card

    def _build_hints_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(2, 12, 2, 0)
        lay.setSpacing(8)

        head = QHBoxLayout()
        head.addWidget(label("Hint ladder", "h3"))
        head.addStretch()
        self.hint_count_badge = Badge(f"0 of {config.MAX_HINTS} used", "neutral")
        head.addWidget(self.hint_count_badge)
        lay.addLayout(head)
        lay.addWidget(label("Each hint is more specific than the last. Try on your own first — "
                            "the final hint shows partial code, never the full solution.",
                            "caption", wrap=True))

        self.step_labels = []
        for i, name in enumerate(llm_client.HINT_LEVELS, start=1):
            step = label(f"{i}  {name}", "body")
            step.setProperty("step", "locked")
            self.step_labels.append(step)
            lay.addWidget(step)

        self.hint_busy = BusyBar()
        lay.addWidget(self.hint_busy)
        self.hint_status = label("", "caption", wrap=True)
        self.hint_status.hide()
        lay.addWidget(self.hint_status)
        self.hint_banner = Banner()
        lay.addWidget(self.hint_banner)

        self.hint_stack = QStackedWidget()
        self.hint_empty = EmptyState("No hints yet", "Stuck? Press Get hint. Hints appear here, newest first.")
        self.hint_view = MarkdownView(auto_height=True)
        self.hint_view.setAccessibleName("Hints received")
        self.hint_stack.addWidget(self.hint_empty)
        self.hint_stack.addWidget(self.hint_view)
        lay.addWidget(self.hint_stack, 1)
        self.hint_scroll = scrollable(w)
        return self.hint_scroll

    def _build_feedback_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(2, 12, 2, 0)
        lay.setSpacing(8)

        lay.addWidget(label("AI code analysis", "h3"))
        lay.addWidget(label("Feedback is generated by an AI model that reads your code — it does not "
                            "run it — so treat it as guidance, not a final grade.", "caption", wrap=True))

        self.feedback_busy = BusyBar()
        lay.addWidget(self.feedback_busy)
        self.feedback_status = label("", "caption", wrap=True)
        self.feedback_status.hide()
        lay.addWidget(self.feedback_status)

        self.submission_meta = label("", "caption", wrap=True)
        self.submission_meta.hide()
        lay.addWidget(self.submission_meta)
        self.integrity_banner = Banner()
        lay.addWidget(self.integrity_banner)
        self.feedback_banner = Banner()
        lay.addWidget(self.feedback_banner)

        self.feedback_stack = QStackedWidget()
        self.feedback_empty = EmptyState("No feedback yet",
                                         "Submit your solution and the AI review will appear here.")
        self.feedback_view = MarkdownView(auto_height=True)
        self.feedback_view.setAccessibleName("AI feedback")
        self.feedback_stack.addWidget(self.feedback_empty)
        self.feedback_stack.addWidget(self.feedback_view)
        lay.addWidget(self.feedback_stack, 1)
        self.feedback_scroll = scrollable(w)
        return self.feedback_scroll

    # ══ Problems ═════════════════════════════════════════════════════════
    def load_questions(self):
        """Fetch problems from the database and populate the list (keeps the selection)."""
        current_id = self._current.qid if self._current else None
        try:
            questions = get_all_questions()
            self._submitted_ids = get_submitted_question_ids(self.username)
        except sqlite3.Error:
            log.exception("Could not load questions")
            self.list_empty.title.setText("Problems could not be loaded")
            self.list_empty.description.setText("There was a problem reading the database. Try Refresh.")
            self.list_stack.setCurrentWidget(self.list_empty)
            return

        self.question_list.blockSignals(True)
        self.question_list.clear()
        restore_row = -1
        for row, q in enumerate(questions):
            item = QListWidgetItem(q["title"])
            item.setData(Qt.UserRole, q)
            self.question_list.addItem(item)
            self._refresh_item_status(item)
            # Keep sessions pointing at the latest question text
            if q["id"] in self._sessions:
                self._sessions[q["id"]].question = q
            if q["id"] == current_id:
                restore_row = row
        self.question_list.blockSignals(False)

        self.count_badge.set_badge(str(len(questions)), "neutral")
        if not questions:
            self.list_empty.title.setText("No problems yet")
            self.list_empty.description.setText(
                "Your instructor hasn't assigned any problems. Use Refresh to check again.")
        self.list_stack.setCurrentWidget(self.question_list if questions else self.list_empty)

        if restore_row >= 0:
            self.question_list.blockSignals(True)
            self.question_list.setCurrentRow(restore_row)
            self.question_list.blockSignals(False)
        elif current_id is not None:
            # The open problem was removed by the instructor
            self._store_editor_state()
            self._current = None
            self.workspace_stack.setCurrentIndex(0)
            self._render_assistant()

    def _refresh_item_status(self, item: QListWidgetItem):
        q = item.data(Qt.UserRole)
        done = q["id"] in self._submitted_ids
        item.setIcon(self._icon_done if done else self._icon_todo)
        state = "Submitted" if done else "Not submitted yet"
        item.setToolTip(f"{q['title']}\n{state}")
        item.setData(Qt.AccessibleTextRole, f"{q['title']}, {state}")

    def _store_editor_state(self):
        """Save the editor text and bank keystrokes for the problem being left."""
        if self._current is None:
            return
        self._current.code = self.code_editor.toPlainText()
        self._current.banked_keystrokes += self.keystroke_monitor.keystroke_count
        self.keystroke_monitor.reset()

    def _on_question_selected(self, item, _previous=None):
        if item is None:
            return
        q = item.data(Qt.UserRole)
        if self._current is not None and self._current.qid == q["id"]:
            return

        self._store_editor_state()
        session = self._sessions.get(q["id"])
        if session is None:
            session = _ProblemSession(question=q)
            self._sessions[q["id"]] = session
        self._current = session

        if not self._monitor_started:
            self.keystroke_monitor.start()
            self._monitor_started = True
        else:
            self.keystroke_monitor.reset()
        self.status_timer.start()

        self.q_title_label.setText(q["title"])
        self.q_stmt_view.set_plain(q["problem_statement"])
        self.code_editor.blockSignals(True)
        self.code_editor.setPlainText(session.code)
        self.code_editor.blockSignals(False)
        self.editor_banner.clear()
        self.workspace_stack.setCurrentIndex(1)
        self.code_editor.setFocus()

        self._update_char_label()
        self._update_integrity_indicator()
        self._render_assistant()

    # ══ Integrity indicator ══════════════════════════════════════════════
    def _current_keystrokes(self) -> int:
        if self._current is None:
            return 0
        return self._current.banked_keystrokes + self.keystroke_monitor.keystroke_count

    def _update_char_label(self):
        n = len(self.code_editor.toPlainText().strip())
        self.char_label.setText(f"{n} character{'s' if n != 1 else ''}")

    def _update_integrity_indicator(self):
        if self._current is None:
            return
        chars = len(self.code_editor.toPlainText().strip())
        keys = self._current_keystrokes()
        if chars == 0:
            self.integrity_badge.set_badge("Typing activity: —", "neutral")
            self.integrity_detail.setText("start typing")
        else:
            ratio = compute_ratio(keys, chars)
            if needs_review(keys, chars):
                self.integrity_badge.set_badge("Typing activity: low", "warning")
            else:
                self.integrity_badge.set_badge("Typing activity: normal", "success")
            self.integrity_detail.setText(f"r = {ratio:.2f}")
        self.integrity_badge.setToolTip(
            f"Integrity indicator (heuristic)\n"
            f"Keystrokes recorded (K): {keys}\n"
            f"Characters in your code (C): {chars}\n"
            f"Review is recommended to your instructor when K / C < {config.INTEGRITY_THRESHOLD}."
        )

    def _explain_integrity(self):
        QMessageBox.information(self, "About the integrity indicator", INTEGRITY_EXPLANATION)

    def _on_app_state_changed(self, state):
        self.keystroke_monitor.set_window_active(state == Qt.ApplicationActive)

    # ══ Assistant panel rendering ════════════════════════════════════════
    def _render_assistant(self):
        """Refresh hint + feedback panels and buttons from the current session."""
        s = self._current
        has_problem = s is not None

        # ── Hints
        used = len(s.hints) if s else 0
        for i, step in enumerate(self.step_labels):
            state = "done" if i < used else ("next" if i == used and has_problem else "locked")
            if step.property("step") != state:
                step.setProperty("step", state)
                repolish(step)
        tone = "warning" if used >= config.MAX_HINTS else ("primary" if used else "neutral")
        self.hint_count_badge.set_badge(f"{used} of {config.MAX_HINTS} used", tone)

        hint_pending = bool(s and s.hint_pending)
        self.hint_busy.setVisible(hint_pending)
        self.hint_status.setVisible(hint_pending)
        if hint_pending:
            self.hint_status.setText(f"Generating hint {used + 1} of {config.MAX_HINTS}…")

        if s and s.hint_error:
            self.hint_banner.show_message("error", s.hint_error + " This attempt was not counted.")
        elif s and used >= config.MAX_HINTS:
            self.hint_banner.show_message(
                "info", "You've used all hints for this problem. Keep going — you've got the pieces you need.")
        else:
            self.hint_banner.clear()

        if s and s.hints:
            parts = []
            for n in range(len(s.hints), 0, -1):
                parts.append(f"#### Hint {n} · {llm_client.HINT_LEVELS[n - 1]}\n\n{s.hints[n - 1]}")
            self.hint_view.set_markdown("\n\n---\n\n".join(parts))
            self.hint_stack.setCurrentWidget(self.hint_view)
        else:
            self.hint_stack.setCurrentWidget(self.hint_empty)

        if not has_problem:
            self.hint_btn.setEnabled(False)
            self.hint_btn.setText("Get hint")
        elif hint_pending:
            self.hint_btn.setEnabled(False)
            self.hint_btn.setText("Generating hint…")
        elif used >= config.MAX_HINTS:
            self.hint_btn.setEnabled(False)
            self.hint_btn.setText("All hints used")
        else:
            self.hint_btn.setEnabled(True)
            self.hint_btn.setText(f"Get hint {used + 1} of {config.MAX_HINTS}")

        # ── Feedback
        eval_pending = bool(s and s.eval_pending)
        self.feedback_busy.setVisible(eval_pending)
        self.feedback_status.setVisible(eval_pending)
        if eval_pending:
            self.feedback_status.setText("Analyzing your submission… this usually takes a few seconds.")

        sub = s.last_submission if s else None
        if sub:
            self.submission_meta.setText(
                f"Last submission {sub['time']} · {sub['hints']} hint{'s' if sub['hints'] != 1 else ''} used · "
                f"K {sub['keys']} / C {sub['chars']} · r = {sub['ratio']:.2f}"
            )
            self.submission_meta.show()
            if sub["flagged"]:
                self.integrity_banner.show_message(
                    "warning",
                    "Integrity indicator: review recommended. Typing activity appeared low relative to "
                    "the amount of submitted code, so your instructor may take a closer look. "
                    "This is an automated heuristic, not a finding of misconduct."
                )
            else:
                self.integrity_banner.clear()
        else:
            self.submission_meta.hide()
            self.integrity_banner.clear()

        if s and s.feedback_error:
            self.feedback_banner.show_message(
                "error", "Your submission was saved, but AI feedback could not be generated. "
                         f"{s.feedback_error} You can submit again to retry.")
        else:
            self.feedback_banner.clear()

        if s and s.feedback:
            self.feedback_view.set_markdown(s.feedback)
            self.feedback_stack.setCurrentWidget(self.feedback_view)
        else:
            self.feedback_stack.setCurrentWidget(self.feedback_empty)

        if not has_problem:
            self.submit_btn.setEnabled(False)
            self.submit_btn.setText("Submit for AI review")
        elif eval_pending:
            self.submit_btn.setEnabled(False)
            self.submit_btn.setText("Analyzing…")
        else:
            self.submit_btn.setEnabled(True)
            self.submit_btn.setText("Submit for AI review")

    # ══ Hints ════════════════════════════════════════════════════════════
    def _request_hint(self):
        s = self._current
        if s is None or s.hint_pending or len(s.hints) >= config.MAX_HINTS:
            return

        number = len(s.hints) + 1
        s.hint_pending = True
        s.hint_error = ""
        statement = s.question["problem_statement"]
        code = self.code_editor.toPlainText()

        task = BackgroundTask(lambda: llm_client.get_hint(statement, number, code),
                              context=(s.qid, number))
        task.succeeded.connect(self._on_hint_ready)
        task.failed.connect(self._on_hint_failed)
        task.start()

        self.assistant_tabs.setCurrentIndex(0)
        self._render_assistant()

    def _on_hint_ready(self, context, hint_text):
        qid, number = context
        s = self._sessions.get(qid)
        if s is None:
            return
        s.hint_pending = False
        if len(s.hints) == number - 1:   # ignore duplicates defensively
            s.hints.append(hint_text)
        if s is self._current:
            self._render_assistant()
            self.hint_scroll.verticalScrollBar().setValue(0)

    def _on_hint_failed(self, context, message):
        qid, _ = context
        s = self._sessions.get(qid)
        if s is None:
            return
        s.hint_pending = False
        s.hint_error = message
        if s is self._current:
            self._render_assistant()

    # ══ Submission ═══════════════════════════════════════════════════════
    def _submit_code(self):
        s = self._current
        if s is None or s.eval_pending:
            return

        code = self.code_editor.toPlainText().strip()
        if not code:
            self.editor_banner.show_message("warning", "Your editor is empty. Write some code before submitting.")
            self.code_editor.setFocus()
            return

        char_count = len(code)
        ks_count = self._current_keystrokes()
        flagged = needs_review(ks_count, char_count)
        hints_used = len(s.hints)

        try:
            submission_id = save_submission(
                self.username, s.qid, code, None,
                hints_used, 1 if flagged else 0, ks_count, char_count
            )
        except sqlite3.Error:
            log.exception("Could not save submission")
            self.editor_banner.show_message(
                "error", "Your submission could not be saved because of a database error. "
                         "Your code is still in the editor — please try again.")
            return

        now = datetime.now().strftime("%H:%M")
        s.submitted_code = self.code_editor.toPlainText()
        s.last_submission = {
            "time": now, "hints": hints_used, "keys": ks_count, "chars": char_count,
            "ratio": compute_ratio(ks_count, char_count), "flagged": flagged,
        }
        s.eval_pending = True
        s.feedback = None
        s.feedback_error = ""

        self._submitted_ids.add(s.qid)
        item = self.question_list.currentItem()
        if item is not None:
            self._refresh_item_status(item)

        statement = s.question["problem_statement"]
        task = BackgroundTask(lambda: _evaluate_and_store(submission_id, statement, code),
                              context=s.qid)
        task.succeeded.connect(self._on_feedback_ready)
        task.failed.connect(self._on_feedback_failed)
        task.start()

        self.editor_banner.show_message(
            "success", f"Submission saved at {now}. The AI review is in progress in the AI feedback panel.")
        self.assistant_tabs.setCurrentIndex(1)
        self._render_assistant()

    def _on_feedback_ready(self, qid, feedback):
        s = self._sessions.get(qid)
        if s is None:
            return
        s.eval_pending = False
        s.feedback = feedback
        if s is self._current:
            self.editor_banner.show_message("success", "AI feedback is ready in the AI feedback panel.")
            self._render_assistant()
            self.feedback_scroll.verticalScrollBar().setValue(0)

    def _on_feedback_failed(self, qid, message):
        s = self._sessions.get(qid)
        if s is None:
            return
        s.eval_pending = False
        s.feedback_error = message
        if s is self._current:
            self.editor_banner.clear()
            self._render_assistant()

    # ══ Logout / cleanup ═════════════════════════════════════════════════
    def unsubmitted_problem_count(self) -> int:
        """Number of problems whose editor text differs from what was last submitted."""
        if self._current is not None:
            self._current.code = self.code_editor.toPlainText()
        return sum(1 for s in self._sessions.values()
                   if s.code.strip() and s.code != (s.submitted_code or ""))

    def confirm_leave(self) -> bool:
        """Ask before discarding unsubmitted drafts. Returns True to proceed."""
        n = self.unsubmitted_problem_count()
        if n == 0:
            return True
        reply = QMessageBox.question(
            self, "Unsubmitted work",
            f"You have unsubmitted code in {n} problem{'s' if n != 1 else ''}. "
            "Drafts are not saved after you sign out.\n\nSign out anyway?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        return reply == QMessageBox.Yes

    def _on_logout(self):
        if not self.confirm_leave():
            return
        self.cleanup()
        self.logout_requested.emit()

    def cleanup(self):
        """Stop monitoring when navigating away."""
        self.keystroke_monitor.stop()
        self._monitor_started = False
        self.status_timer.stop()


def _evaluate_and_store(submission_id: int, statement: str, code: str) -> str:
    """Runs on a worker thread: get AI feedback and attach it to the submission.

    Storing here (not in the UI callback) means feedback is still recorded if
    the learner signs out before the review finishes.
    """
    feedback = llm_client.evaluate_code(statement, code)
    try:
        set_submission_feedback(submission_id, feedback)
    except sqlite3.Error:
        log.exception("Could not store feedback for submission %s", submission_id)
    return feedback
