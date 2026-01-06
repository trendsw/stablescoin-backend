import json
from typing import Any

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from core.config import OPENAI_API_KEY

client = OpenAI(api_key=OPENAI_API_KEY)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
)
def call_llm(system_prompt: str, user_text: str) -> Any:
    """
    Generic LLM call that enforces JSON output.
    Used for claim extraction, comparison, truth evaluation, etc.
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.1,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an information extraction engine. "
                    "Always respond with valid JSON only. "
                    "Do not include explanations or markdown."
                ),
            },
            {
                "role": "user",
                "content": f"{system_prompt}\n\nTEXT:\n{user_text}",
            },
        ],
    )

    content = response.choices[0].message.content.strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON from LLM: {content}") from e