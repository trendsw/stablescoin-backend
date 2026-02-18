import json
from typing import Any
import os
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from core.config import OPENAI_API_KEY
from anthropic import Anthropic


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=2, max=10),
)
def call_llm(system_prompt: str, user_text: str) -> Any:
    """
    Generic LLM call that enforces JSON output.
    Used for claim extraction, comparison, truth evaluation, etc.
    """
    provider= os.getenv("AI_MODEL", "openai")
    system_message = (
        "You are an information extraction engine. "
        "Always respond with valid JSON only. "
        "Do not include explanations or markdown."
    )
    print("ai model provider===>", provider)
    if provider== "openai":
        client = OpenAI(api_key=OPENAI_API_KEY)
        MODEL = "gpt-4o-mini"
        response = client.chat.completions.create(
        model=MODEL,
        temperature=0.1,
        messages=[
            {
                "role": "system",
                "content": system_message,
            },
            {
                "role": "user",
                "content": f"{system_prompt}\n\nTEXT:\n{user_text}",
            },
        ],
        )
        content = response.choices[0].message.content.strip()
    elif provider=="deepseek":
        client = OpenAI(
            api_key=os.getenv("DEEPSEEK_KEY"),
            base_url="https://api.deepseek.com"
        )
        MODEL = "deepseek-chat"
        response = client.chat.completions.create(
        model=MODEL,
        temperature=0.1,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": system_message,
            },
            {
                "role": "user",
                "content": f"{system_prompt}\n\nTEXT:\n{user_text}",
            },
        ],
    )


        content = response.choices[0].message.content.strip()
    else:
        client = Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))

        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=4000,
            temperature=0.1,
            system=(
                system_message +
                "\n\nYou MUST return strictly valid JSON. "
                "Do not wrap in markdown. "
                "Do not explain. "
                "Return JSON only."
            ),
            messages=[
                {
                    "role": "user",
                    "content": f"{system_prompt}\n\nTEXT:\n{user_text}",
                }
            ],
        )

        # Claude returns list of content blocks
        content = "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()

        # Remove accidental markdown wrapping
        if content.startswith("```"):
            content = content.strip("`")
            content = content.replace("json", "").strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON from LLM: {content}") from e