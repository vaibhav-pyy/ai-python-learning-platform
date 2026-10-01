"""
keystroke_monitor.py — pynput-based keystroke tracker.

Counts key presses so the platform can compute the typing-activity ratio
r = K / C (keystrokes / submitted characters). A low ratio is a *heuristic*
signal that code may have been pasted rather than typed; it is shown to the
instructor as "review recommended" and is never treated as proof of anything.
"""

import threading

from pynput import keyboard

import config


def compute_ratio(keystroke_count: int, char_count: int) -> float:
    """r = K / C. Returns 0.0 when there are no characters."""
    if char_count == 0:
        return 0.0
    return keystroke_count / char_count


def needs_review(keystroke_count: int, char_count: int,
                 threshold: float = config.INTEGRITY_THRESHOLD) -> bool:
    """True when r < threshold. Empty code is never marked for review."""
    if char_count == 0:
        return False
    return compute_ratio(keystroke_count, char_count) < threshold


class KeystrokeMonitor:
    """
    Monitors keyboard activity using pynput.
    Counts every individual key press as one keystroke.

    pynput listens system-wide, so the owning window should call
    set_window_active() to report whether the application is focused;
    key presses made in other applications are not counted.
    """

    def __init__(self):
        self._keystroke_count = 0
        self._lock = threading.Lock()
        self._listener = None
        self._active = False
        self._window_active = True

    def _on_press(self, key):
        """Callback for every key press event (runs on pynput's thread)."""
        if self._active and self._window_active:
            with self._lock:
                self._keystroke_count += 1

    def start(self):
        """Start monitoring keystrokes. Resets the counter."""
        self.reset()
        self._active = True
        if self._listener is None or not self._listener.running:
            self._listener = keyboard.Listener(on_press=self._on_press)
            self._listener.start()

    def stop(self):
        """Stop monitoring keystrokes."""
        self._active = False
        if self._listener is not None and self._listener.running:
            self._listener.stop()
        self._listener = None

    def reset(self):
        """Reset the keystroke counter to zero without stopping the listener."""
        with self._lock:
            self._keystroke_count = 0

    def set_window_active(self, active: bool):
        """Tell the monitor whether the application window currently has focus."""
        self._window_active = active

    @property
    def keystroke_count(self) -> int:
        """Return the current keystroke count."""
        with self._lock:
            return self._keystroke_count

    def compute_ratio(self, char_count: int) -> float:
        """Ratio of the current keystroke count to `char_count`."""
        return compute_ratio(self.keystroke_count, char_count)

    def is_flagged(self, char_count: int, threshold: float = config.INTEGRITY_THRESHOLD) -> bool:
        """True when the current ratio is below the review threshold."""
        return needs_review(self.keystroke_count, char_count, threshold)
