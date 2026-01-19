
from ml.llm import call_llm
from typing import Any, Dict, List

def extract_claims(text: str):
    prompt = """
    Extract factual claims from the text.

    Return a JSON array where each item has:
    - claim_text (string)
    - claim_type (fact | prediction | opinion | speculation)
    - sentiment (positive | negative | neutral)

    Only include explicit claims.
    """

    return call_llm(prompt, text)


def analyze_article(title: str, content: str) -> Dict[str, Any]:
    system_prompt = """
    TASK:
    Analyze the given news article and return structured data.

    1. Determine article priority:
    - breaking: urgent news that has immediate impact; includes market-moving events, hacks, regulations, bans, lawsuits, disasters, or crises.
    - top: high-impact industry news; important for professionals and decision-makers; notable but not urgent.
    - major: important news that affects a wide audience; interesting but not immediate or critical.
    - trend: general trends, insights, commentary, or updates on topics that indicate shifts over time; often long-term, analytical, or observational.

    2. Determine article category as ONE of:
    domestic, international, economy, life, IT, entertainment, sports, science

    Rules:
    - Category must reflect the real-world domain, not the technology itself.
    - Blockchain, AI, or cryptocurrency are NOT categories by themselves.
    - Sports teams, athletes, leagues → sports
    - Research, cryptography, scientific methods → science
    - Economy includes market reports, companies, investments, finance
    - Life includes health, lifestyle, culture
    - IT includes technology products, software, apps, devices
    - Entertainment includes movies, music, celebrities
    - Domestic vs international → based on main geographic focus

    3. Extract ONLY explicit claims from the article.
    Each claim must include:
    - claim_text (string)
    - claim_type (fact | prediction | opinion | speculation)
    - sentiment (positive | negative | neutral)

    4. Translate the article title and content into Japanese.
    - Keep meaning accurate
    - Use natural Japanese news style

    5. Summarize content in 3–4 sentences.

    OUTPUT FORMAT (STRICT JSON):
    {
      "priority": "...",
      "category": "...",
      "claims": [
        {
          "claim_text": "...",
          "claim_type": "...",
          "sentiment": "..."
        }
      ],
      "ja": {
        "title": "...",
        "content": "..."
      },
      "summary": "..."
    }
    """

    user_text = f"""
    TITLE:
    {title}

    CONTENT:
    {content}
    """

    return call_llm(system_prompt, user_text)