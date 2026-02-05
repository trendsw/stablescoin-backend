import hashlib
import os
import time
from datetime import datetime

FIRST_BLOCK_TIME = os.getenv("FIRST_BLOCK_TIME")
BLOCK_GENERATION_TIME = int(os.getenv("BLOCK_GENERATION_TIME", "3000"))

def generate_transaction_hash() -> str:
    payload = f"{time.time_ns()}{os.urandom(16).hex()}"
    digest = hashlib.sha256(payload.encode()).hexdigest()
    return f"dfs_0x{digest[:64]}"


def calculate_block_number() -> int:
    now = int(time.time() * 1000)
    first = int(datetime.fromisoformat(FIRST_BLOCK_TIME.replace("Z", "")).timestamp() * 1000)
    return (now - first) // BLOCK_GENERATION_TIME


def calculate_required_tokens(usd_amount: float, token_price_usd: float) -> float:
    if token_price_usd <= 0:
        raise ValueError("Invalid token price")
    return usd_amount / token_price_usd