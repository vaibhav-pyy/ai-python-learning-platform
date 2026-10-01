"""
workers.py — Run slow work (LLM requests) off the GUI thread.

The function runs on a daemon thread, so closing the window never waits for a
slow network call. Results come back through Qt signals; because the task
object lives in the GUI thread, connected slots run on the GUI thread
(queued connection) and may safely touch widgets.

Connect the signals to *bound methods of QObjects* (e.g. a dashboard's
methods): PyQt drops those connections automatically if the receiver is
destroyed before the work finishes.
"""

import logging
import threading

from PyQt5.QtCore import QObject, pyqtSignal

from llm_client import LLMError

log = logging.getLogger(__name__)

_running = set()  # keep tasks alive until they finish


class BackgroundTask(QObject):
    """Runs `fn()` on a worker thread and reports back with a context object."""

    succeeded = pyqtSignal(object, object)  # (context, result)
    failed = pyqtSignal(object, str)        # (context, user-facing message)
    _done = pyqtSignal()

    def __init__(self, fn, context=None):
        super().__init__()
        self._fn = fn
        self.context = context
        # Delivered on the GUI thread after succeeded/failed, so the object is
        # released (and destroyed) on the thread that owns it.
        self._done.connect(self._release)

    def start(self):
        _running.add(self)
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            result = self._fn()
        except LLMError as exc:
            self.failed.emit(self.context, exc.user_message)
        except Exception:
            log.exception("Background task failed")
            self.failed.emit(self.context, "Something went wrong while processing your request. Please try again.")
        else:
            self.succeeded.emit(self.context, result)
        finally:
            self._done.emit()

    def _release(self):
        _running.discard(self)
