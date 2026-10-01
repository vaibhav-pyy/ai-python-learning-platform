"""
main.py — Entry point for the AI Python Learning Platform.
Launches the PyQt5 application and routes between sign-in, sign-up and the
role-specific dashboards.
"""

import logging
import os
import sqlite3
import sys

# Ensure the project root is on the path so imports work correctly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox, QStackedWidget

from database import initialize_database
from ui import theme
from ui.instructor_dashboard import InstructorDashboard
from ui.learner_dashboard import LearnerDashboard
from ui.login_screen import LoginScreen
from ui.signup_screen import SignupScreen

APP_NAME = "AI Python Learning Platform"


class MainWindow(QMainWindow):
    """Main application window managing screen navigation."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1000, 660)
        self.resize(1320, 820)

        self.stack = QStackedWidget()
        self.stack.setObjectName("mainStack")
        self.setCentralWidget(self.stack)

        self.login_screen = LoginScreen()
        self.login_screen.login_success.connect(self._on_login)
        self.login_screen.signup_requested.connect(self._show_signup)
        self.stack.addWidget(self.login_screen)

        self.signup_screen = SignupScreen()
        self.signup_screen.signup_success.connect(self._on_signup_success)
        self.signup_screen.back_to_login.connect(self._show_login)
        self.stack.addWidget(self.signup_screen)

        # The active dashboard (created on login, destroyed on logout)
        self.dashboard = None

    # ── Navigation ───────────────────────────────────────────────────────
    def _on_login(self, username: str, role: str, display_name: str):
        """Route to the appropriate dashboard after login."""
        self._close_dashboard()
        if role == "instructor":
            self.dashboard = InstructorDashboard(username, display_name)
        else:
            self.dashboard = LearnerDashboard(username, display_name)
            self.dashboard.load_questions()
        self.dashboard.logout_requested.connect(self._logout)
        self.stack.addWidget(self.dashboard)
        self.stack.setCurrentWidget(self.dashboard)
        self.setWindowTitle(f"{APP_NAME} — {display_name}")

    def _show_signup(self):
        self.signup_screen.reset_fields()
        self.stack.setCurrentWidget(self.signup_screen)

    def _on_signup_success(self, username: str):
        self.login_screen.show_notice("Account created. Sign in with your new password.", username)
        self.stack.setCurrentWidget(self.login_screen)

    def _show_login(self):
        self.login_screen.reset_fields()
        self.stack.setCurrentWidget(self.login_screen)

    def _close_dashboard(self):
        if self.dashboard is None:
            return
        if isinstance(self.dashboard, LearnerDashboard):
            self.dashboard.cleanup()
        self.stack.removeWidget(self.dashboard)
        self.dashboard.deleteLater()
        self.dashboard = None

    def _logout(self):
        """Return to the login screen."""
        self._close_dashboard()
        self.setWindowTitle(APP_NAME)
        self._show_login()

    def closeEvent(self, event):
        if isinstance(self.dashboard, LearnerDashboard) and not self.dashboard.confirm_leave():
            event.ignore()
            return
        self._close_dashboard()
        event.accept()


def main():
    logging.basicConfig(
        level=os.environ.get("LP_LOG_LEVEL", "WARNING").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setPalette(theme.build_palette())
    app.setFont(theme.ui_font(10))
    app.setStyleSheet(theme.STYLESHEET)

    try:
        initialize_database()
    except sqlite3.Error as exc:
        logging.exception("Database initialisation failed")
        QMessageBox.critical(None, APP_NAME,
                             "The application database could not be opened or created.\n\n"
                             f"Details: {exc}")
        return 1

    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
