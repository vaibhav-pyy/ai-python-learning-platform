"""
Unit tests for the non-GUI logic. Run from the project root with:

    python -m unittest discover tests

The tests use a temporary database and never contact the AI service.
"""

import hashlib
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_TMP = tempfile.mkdtemp()
os.environ["LP_DB_PATH"] = os.path.join(_TMP, "test.db")
os.environ.pop("HF_TOKEN", None)

import config  # noqa: E402
import database  # noqa: E402
import llm_client  # noqa: E402
from keystroke_monitor import KeystrokeMonitor, compute_ratio, needs_review  # noqa: E402


class IntegrityHeuristicTests(unittest.TestCase):
    def test_threshold_is_unchanged(self):
        self.assertEqual(config.INTEGRITY_THRESHOLD, 0.35)

    def test_ratio(self):
        self.assertAlmostEqual(compute_ratio(50, 100), 0.5)
        self.assertEqual(compute_ratio(10, 0), 0.0)

    def test_rule(self):
        self.assertTrue(needs_review(34, 100))      # r = 0.34 < 0.35
        self.assertFalse(needs_review(35, 100))     # r = 0.35 is not flagged
        self.assertFalse(needs_review(0, 0))        # empty code never flagged

    def test_monitor_counts_only_when_window_active(self):
        m = KeystrokeMonitor()
        m._active = True                            # simulate a started listener
        m._on_press("a")
        m.set_window_active(False)
        m._on_press("b")
        m.set_window_active(True)
        m._on_press("c")
        self.assertEqual(m.keystroke_count, 2)
        self.assertTrue(m.is_flagged(char_count=100))
        m.reset()
        self.assertEqual(m.keystroke_count, 0)


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        # A fresh database file per test
        fd, path = tempfile.mkstemp(suffix=".db", dir=_TMP)
        os.close(fd)
        os.remove(path)
        patcher = mock.patch.object(database, "DB_PATH", path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.db_path = path
        database.initialize_database()

    def _sql(self, query, params=()):
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            return conn.execute(query, params).fetchall()

    def test_demo_accounts_seeded_and_login(self):
        user = database.authenticate_user("instructor", "admin123")
        self.assertEqual(user["role"], "instructor")
        self.assertIsNone(database.authenticate_user("instructor", "wrong"))
        self.assertIsNone(database.authenticate_user("nobody", "admin123"))

    def test_passwords_are_salted(self):
        a, b = database.hash_password("same"), database.hash_password("same")
        self.assertNotEqual(a, b)
        self.assertTrue(database.verify_password("same", a))
        self.assertFalse(database.verify_password("other", a))

    def test_legacy_sha256_hash_is_accepted_and_upgraded(self):
        legacy = hashlib.sha256(b"oldpass").hexdigest()
        self._sql("INSERT INTO users (username, password, role) VALUES ('old', ?, 'learner')", (legacy,))
        self.assertIsNotNone(database.authenticate_user("old", "oldpass"))
        stored = self._sql("SELECT password FROM users WHERE username='old'")[0][0]
        self.assertTrue(stored.startswith("pbkdf2_sha256$"))
        self.assertIsNotNone(database.authenticate_user("old", "oldpass"))

    def test_register_rejects_duplicates(self):
        self.assertTrue(database.register_user("Ada", "ada_l", "secret1"))
        self.assertFalse(database.register_user("Ada 2", "ada_l", "secret2"))
        self.assertEqual(database.authenticate_user("ada_l", "secret1")["full_name"], "Ada")

    def test_submission_lifecycle(self):
        qid = database.add_question("Sum", "Add two numbers", "instructor")
        sid = database.save_submission("learner1", qid, "print(1+2)", None, 2, 1, 3, 10)
        sub = database.get_all_submissions()[0]
        self.assertIsNone(sub["feedback"])
        self.assertEqual(sub["learner_name"], "Demo Learner")
        database.set_submission_feedback(sid, "Looks good")
        self.assertEqual(database.get_all_submissions()[0]["feedback"], "Looks good")
        self.assertEqual(database.get_all_questions()[0]["submission_count"], 1)
        self.assertEqual(database.get_submitted_question_ids("learner1"), {qid})

        database.delete_question(qid)
        self.assertEqual(database.get_all_questions(), [])
        self.assertEqual(database.get_all_submissions(), [])


class LLMClientTests(unittest.TestCase):
    def test_missing_token_raises_friendly_error(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("HF_TOKEN", None)
            with self.assertRaises(llm_client.LLMError) as ctx:
                llm_client.get_hint("p", 1, "")
        self.assertIn("HF_TOKEN", ctx.exception.user_message)

    def test_error_messages_hide_technical_details(self):
        class Resp:
            def __init__(self, code):
                self.status_code = code

        class HTTPErr(Exception):
            def __init__(self, code):
                super().__init__("Client error '401 Unauthorized' for url https://...")
                self.response = Resp(code)

        class ConnectError(Exception):
            pass

        self.assertIn("access token", llm_client._friendly_error(HTTPErr(401)))
        self.assertIn("busy", llm_client._friendly_error(HTTPErr(429)))
        self.assertIn("internet connection", llm_client._friendly_error(ConnectError("x")))
        self.assertIn("too long", llm_client._friendly_error(TimeoutError()))
        for msg in (llm_client._friendly_error(HTTPErr(401)), llm_client._friendly_error(ValueError("boom"))):
            self.assertNotIn("http", msg.lower())

    def test_five_hint_levels(self):
        self.assertEqual(len(llm_client.HINT_LEVELS), config.MAX_HINTS)
        self.assertEqual(config.MAX_HINTS, 5)


class ConfigTests(unittest.TestCase):
    def test_dotenv_does_not_override_existing_values(self):
        path = os.path.join(_TMP, ".env")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("# comment\nLP_TEST_A=from_file\nLP_TEST_B='quoted'\n")
        os.environ["LP_TEST_A"] = "from_env"
        config._load_dotenv(path)
        self.assertEqual(os.environ["LP_TEST_A"], "from_env")
        self.assertEqual(os.environ["LP_TEST_B"], "quoted")


if __name__ == "__main__":
    unittest.main()
