"""
llm_client.py — Hugging Face Inference API wrapper (Qwen2.5-Coder-7B-Instruct).
Uses the HF_TOKEN environment variable for authentication.

Both public functions return the model's text on success and raise LLMError
on failure. LLMError.user_message is safe to show in the UI; the technical
cause is written to the log for developers.
"""

import logging

import config

log = logging.getLogger(__name__)

# The five hint levels, in order. Shown in the UI and described in the prompt.
HINT_LEVELS = [
    "Concept direction",
    "Spot the gap",
    "Useful Python tools",
    "Direct explanation",
    "Partial skeleton code",
]


class LLMError(Exception):
    """An AI request failed. `user_message` is a friendly explanation."""

    def __init__(self, user_message: str):
        super().__init__(user_message)
        self.user_message = user_message


def is_configured() -> bool:
    """True when an API token is available."""
    return config.hf_token() is not None


def _friendly_error(exc: Exception) -> str:
    """Translate a library/network exception into a message for learners."""
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if status in (401, 403):
        return ("The AI service rejected the access token. "
                "Ask your administrator to check the HF_TOKEN setting.")
    if status == 429:
        return "The AI service is busy right now (rate limit reached). Please wait a minute and try again."
    if status is not None and status >= 500:
        return "The AI service is temporarily unavailable. Please try again in a few moments."

    name = type(exc).__name__.lower()
    if "timeout" in name or isinstance(exc, TimeoutError):
        return "The AI service took too long to respond. Please try again."
    if "connect" in name or "network" in name or isinstance(exc, ConnectionError):
        return "Unable to contact the AI service. Please check your internet connection and try again."
    return "The AI service could not complete the request. Please try again."


def _chat(prompt: str) -> str:
    """Send one user message to the model and return the reply text."""
    token = config.hf_token()
    if not token:
        raise LLMError(
            "AI features are not configured. Set the HF_TOKEN environment variable "
            "(or add it to a .env file) and restart the application."
        )
    try:
        from huggingface_hub import InferenceClient

        client = InferenceClient(api_key=token, timeout=config.LLM_TIMEOUT_SECONDS)
        completion = client.chat.completions.create(
            model=config.HF_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        content = completion.choices[0].message.content
    except Exception as exc:  # network/library errors vary by huggingface_hub version
        log.exception("LLM request failed")
        raise LLMError(_friendly_error(exc)) from exc

    if not content or not content.strip():
        raise LLMError("The AI service returned an empty response. Please try again.")
    return content.strip()


def evaluate_code(problem_statement: str, student_code: str) -> str:
    """Send the student's code to the LLM for evaluation and return the feedback."""
    prompt = f"""You are a Python code evaluator for a coding education platform.
A student has submitted the following Python code as a solution to this problem:

Problem: {problem_statement}

Student's Code:
{student_code}

You cannot run the code. Base your evaluation only on reading it, and do not claim
that it was executed or tested.

Evaluate the code and provide:
1. Whether the solution appears to be correct or not
2. What the student did well
3. What can be improved (logic, efficiency, style)
4. A brief explanation of any bugs if present

Keep the feedback educational, encouraging, and concise."""
    return _chat(prompt)


def get_hint(problem_statement: str, hint_number: int, current_code: str) -> str:
    """
    Request a progressive hint from the LLM.
    hint_number should be 1–5.
    """
    prompt = f"""You are a Python tutor helping a student solve a coding problem.

Problem Statement:
{problem_statement}

The student's current code is:
{current_code if current_code.strip() else "(The student has not written any code yet.)"}

This is hint number {hint_number} out of a maximum of {config.MAX_HINTS}.

Based on what the student has written so far, give a targeted hint:
- Hint 1: Identify what concept or approach the student seems to be attempting. Give only a general direction — no code at all.
- Hint 2: Point out specifically what is missing or wrong in their current code in plain English. No code.
- Hint 3: Suggest which Python built-in functions, methods, or logic structures would help. Still no code.
- Hint 4: Give a more direct explanation of the fix needed, referencing their actual code. No complete solution.
- Hint 5 (FINAL): Provide partial Python code — a skeleton or the corrected first few lines only — that directly addresses the gap in the student's code. Do NOT give the complete solution.

Give only hint number {hint_number}. Do not give all hints at once. Do not number your response. Just give the hint content directly."""
    return _chat(prompt)
