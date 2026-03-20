# core/openai_client.py
# import asyncio
# from openai import AsyncOpenAI
# from core.config import OPENAI_API_KEY

# OPENAI_MAX_CONCURRENT = 2  # SAFE default

# openai_semaphore = asyncio.Semaphore(OPENAI_MAX_CONCURRENT)

# client = AsyncOpenAI(
#     api_key=OPENAI_API_KEY,
#     max_retries=0,  # IMPORTANT: disable SDK retries
# )

import asyncio
import time
from openai import AsyncOpenAI
from core.config import OPENAI_API_KEY

# ---------------- CONFIG ----------------
OPENAI_MAX_CONCURRENT = 1       # request concurrency
OPENAI_MAX_TPM = 200000        # MUST be below dashboard limit
OPENAI_MAX_OUTPUT_TOKENS = 1000
# --------------------------------------

# request-level concurrency
openai_semaphore = asyncio.Semaphore(OPENAI_MAX_CONCURRENT)

# token bucket (TPM-based)
_token_lock = asyncio.Lock()
_tokens_used = 0
_window_start = time.monotonic()

client = AsyncOpenAI(
    api_key=OPENAI_API_KEY,
    max_retries=0,  # IMPORTANT: disable SDK retries
)


def estimate_tokens(text: str) -> int:
    """
    Conservative token estimator (~4 chars/token).
    """
    return max(1, len(text) // 4)


async def acquire_token_budget(tokens_needed: int):
    """
    Global TPM gate to prevent 429 errors.
    """
    global _tokens_used, _window_start

    async with _token_lock:
        now = time.monotonic()

        # Reset every 60 seconds
        if now - _window_start >= 60:
            _window_start = now
            _tokens_used = 0

        # Wait until budget is available
        while _tokens_used + tokens_needed > OPENAI_MAX_TPM:
            sleep_for = 60 - (now - _window_start)
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)

            _window_start = time.monotonic()
            _tokens_used = 0
            now = _window_start

        _tokens_used += tokens_needed
        print("token used====>", _tokens_used)