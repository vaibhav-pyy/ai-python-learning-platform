"""
login_screen.py — Sign-in screen.
Validates credentials and emits login_success so main.py can route by role.
"""

import logging
import sqlite3

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QCheckBox, QHBoxLayout, QLineEdit

import config
from database import authenticate_user
from ui.widgets import AuthPage, Banner, button, label, text_input

log = logging.getLogger(__name__)


class LoginScreen(AuthPage):
    """Login screen with username/password fields and role-based routing."""

    # Emitted on successful login: (username, role, display name)
    login_success = pyqtSignal(str, str, str)
    signup_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Sign in", "Welcome back. Sign in to continue to your workspace.", parent)
        self.setObjectName("loginScreen")
        self._build_form()

    def _build_form(self):
        self.banner = Banner()
        self.form.addWidget(self.banner)
        self.form.addSpacing(10)
        self.banner.hide()

        self.username_input = text_input("Enter your username", accessible_name="Username")
        self.add_field("Username", self.username_input)

        self.password_input = text_input("Enter your password", password=True, accessible_name="Password")
        self.add_field("Password", self.password_input)

        self.show_password = QCheckBox("Show password")
        self.show_password.toggled.connect(
            lambda on: self.password_input.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password)
        )
        self.form.addWidget(self.show_password)
        self.form.addSpacing(18)

        self.login_btn = button("Sign in", "primary", self._handle_login, size="large")
        self.login_btn.setDefault(True)
        self.form.addWidget(self.login_btn)
        self.form.addSpacing(14)

        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(label("New learner?", "muted"))
        signup = button("Create an account", "link", self.signup_requested.emit)
        row.addWidget(signup)
        row.addStretch()
        self.form.addLayout(row)

        if config.SEED_DEMO_ACCOUNTS:
            demo = label("Demo accounts — instructor / admin123 · learner1 / learn123", "caption")
            demo.setAlignment(Qt.AlignCenter)
            demo.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.footer.addWidget(demo)

        self.username_input.returnPressed.connect(self._handle_login)
        self.password_input.returnPressed.connect(self._handle_login)
        self.username_input.textEdited.connect(lambda _: self._clear_error())
        self.password_input.textEdited.connect(lambda _: self._clear_error())

    def _clear_error(self):
        if self.banner.property("tone") == "error":
            self.banner.clear()

    def _handle_login(self):
        """Validate credentials and emit login_success."""
        username = self.username_input.text().strip()
        # Passwords are compared exactly as typed (sign-up does not strip them either).
        password = self.password_input.text()

        if not username or not password:
            self.banner.show_message("error", "Please enter both your username and password.")
            (self.username_input if not username else self.password_input).setFocus()
            return

        try:
            user = authenticate_user(username, password)
        except sqlite3.Error:
            log.exception("Login failed due to a database error")
            self.banner.show_message("error", "Could not reach the local database. Please restart the application.")
            return

        if user:
            self.login_success.emit(user["username"], user["role"], user["full_name"] or user["username"])
        else:
            self.banner.show_message("error", "Incorrect username or password. Please try again.")
            self.password_input.clear()
            self.password_input.setFocus()

    def show_notice(self, message: str, username: str = ""):
        """Show a success notice (e.g. after sign-up) and pre-fill the username."""
        self.reset_fields()
        if username:
            self.username_input.setText(username)
            self.password_input.setFocus()
        self.banner.show_message("success", message)

    def reset_fields(self):
        """Clear all input fields and messages."""
        self.username_input.clear()
        self.password_input.clear()
        self.show_password.setChecked(False)
        self.banner.clear()
        self.username_input.setFocus()
