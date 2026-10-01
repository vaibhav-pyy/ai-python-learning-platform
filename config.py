"""
config.py — Central configuration for the AI Python Learning Platform.

Values come from environment variables. For convenience, a `.env` file in the
project root is also read (without overriding variables that are already set),
so no extra dependency such as python-dotenv is required.
"""

import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def _load_dotenv(path: str) -> None:
    """Minimal .env reader: KEY=VALUE lines, '#' comments, optional quotes."""
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


_load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

# ── Storage ──────────────────────────────────────────────────────────────────
DB_PATH = os.environ.get("LP_DB_PATH") or os.path.join(PROJECT_ROOT, "learning_platform.db")

# Seed the demo accounts (instructor/admin123, learner1/learn123) on first run.
SEED_DEMO_ACCOUNTS = _env_bool("LP_SEED_DEMO_ACCOUNTS", True)

# ── LLM (Hugging Face Inference Providers) ──────────────────────────────────
HF_MODEL = os.environ.get("HF_MODEL", "Qwen/Qwen2.5-Coder-7B-Instruct:nscale")
LLM_TIMEOUT_SECONDS = float(os.environ.get("LP_LLM_TIMEOUT", "60"))


def hf_token():
    """Read the token at call time so a changed environment is picked up."""
    return os.environ.get("HF_TOKEN") or None


# ── Learning rules ───────────────────────────────────────────────────────────
MAX_HINTS = 5

# Keystroke integrity heuristic: r = K / C. A submission is marked
# "review recommended" when r < INTEGRITY_THRESHOLD.
INTEGRITY_THRESHOLD = 0.35
