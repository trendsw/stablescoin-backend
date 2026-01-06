
from ml.llm import call_llm

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