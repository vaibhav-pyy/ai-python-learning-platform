"""
signup_screen.py — Sign-up screen.
Allows new learners to create an account with inline, per-field validation.
"""

import logging
import re
import sqlite3

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QCheckBox, QHBoxLayout, QLineEdit

from database import register_user
from ui.widgets import AuthPage, Banner, button, label, set_invalid, text_input

log = logging.getLogger(__name__)

MIN_USERNAME = 4
MIN_PASSWORD = 6
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


class SignupScreen(AuthPage):
    """Sign-up screen for new learner accounts."""

    # Emitted with the new username
    signup_success = pyqtSignal(str)
    back_to_login = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Create a learner account",
                         "Instructor accounts are created by an administrator.", parent)
        self.setObjectName("signupScreen")
        self._build_form()

    def _build_form(self):
        self.banner = Banner()
        self.form.addWidget(self.banner)
        self.form.addSpacing(10)

        self.fullname_input = text_input("e.g. Ada Lovelace", accessible_name="Full name")
        self.username_input = text_input(f"At least {MIN_USERNAME} characters", accessible_name="Username")
        self.password_input = text_input(f"At least {MIN_PASSWORD} characters", password=True,
                                         accessible_name="Password")
        self.confirm_input = text_input("Re-enter your password", password=True,
                                        accessible_name="Confirm password")

        self._fields = [
            ("Full name", self.fullname_input),
            ("Username", self.username_input),
            ("Password", self.password_input),
            ("Confirm password", self.confirm_input),
        ]
        self._errors = {}
        for caption, widget in self._fields:
            err = label("", "error", wrap=True)
            err.hide()
            self._errors[widget] = err
            self.add_field(caption, widget, err)
            widget.textEdited.connect(lambda _, w=widget: self._clear_field_error(w))
            widget.returnPressed.connect(self._handle_signup)

        self.show_password = QCheckBox("Show passwords")
        self.show_password.toggled.connect(self._toggle_password_visibility)
        self.form.addWidget(self.show_password)
        self.form.addSpacing(18)

        self.signup_btn = button("Create account", "primary", self._handle_signup, size="large")
        self.form.addWidget(self.signup_btn)
        self.form.addSpacing(14)

        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(label("Already have an account?", "muted"))
        row.addWidget(button("Sign in", "link", self.back_to_login.emit))
        row.addStretch()
        self.form.addLayout(row)

    def _toggle_password_visibility(self, visible: bool):
        mode = QLineEdit.Normal if visible else QLineEdit.Password
        self.password_input.setEchoMode(mode)
        self.confirm_input.setEchoMode(mode)

    def _set_field_error(self, widget, message: str):
        err = self._errors[widget]
        err.setText(message)
        err.show()
        set_invalid(widget, True)

    def _clear_field_error(self, widget):
        self._errors[widget].hide()
        set_invalid(widget, False)

    def _clear_errors(self):
        for _, widget in self._fields:
            self._clear_field_error(widget)
        self.banner.clear()

    def _validate(self, full_name, username, password, confirm) -> bool:
        errors = []
        if not full_name:
            errors.append((self.fullname_input, "Please enter your name."))
        if not username:
            errors.append((self.username_input, "Please choose a username."))
        elif len(username) < MIN_USERNAME:
            errors.append((self.username_input, f"Username must be at least {MIN_USERNAME} characters."))
        elif not _USERNAME_RE.match(username):
            errors.append((self.username_input, "Use only letters, numbers, dots, dashes and underscores."))
        if len(password) < MIN_PASSWORD:
            errors.append((self.password_input, f"Password must be at least {MIN_PASSWORD} characters."))
        if not confirm:
            errors.append((self.confirm_input, "Please confirm your password."))
        elif password != confirm:
            errors.append((self.confirm_input, "Passwords do not match."))

        for widget, message in errors:
            self._set_field_error(widget, message)
        if errors:
            errors[0][0].setFocus()
        return not errors

    def _handle_signup(self):
        self._clear_errors()

        full_name = self.fullname_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text()
        confirm = self.confirm_input.text()

        if not self._validate(full_name, username, password, confirm):
            return

        try:
            created = register_user(full_name, username, password)
        except sqlite3.Error:
            log.exception("Registration failed due to a database error")
            self.banner.show_message("error", "Your account could not be created because of a database error. "
                                              "Please try again.")
            return

        if created:
            self.signup_success.emit(username)
        else:
            self._set_field_error(self.username_input, "That username is already taken. Please choose another.")
            self.username_input.setFocus()

    def reset_fields(self):
        """Clear all input fields and errors."""
        for _, widget in self._fields:
            widget.clear()
        self.show_password.setChecked(False)
        self._clear_errors()
        self.fullname_input.setFocus()
