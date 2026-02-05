import os
import requests

DEXTOOLS_API_KEY = os.getenv("DEXTOOLS_API_KEY")
FALLBACK_PRICE = float(os.getenv("FALLBACK_TOKEN_PRICE_USD", "0.001"))

def get_token_price_on_chain(token_address: str) -> dict:
    if not DEXTOOLS_API_KEY:
        return {"priceUsd": FALLBACK_PRICE}

    url = f"https://public-api.dextools.io/trial/v2/token/bsc/{token_address}/price"
    headers = {
        "X-API-KEY": DEXTOOLS_API_KEY,
        "accept": "application/json"
    }

    try:
        r = requests.get(url, headers=headers, timeout=10)
        if not r.ok:
            return {"priceUsd": FALLBACK_PRICE}

        data = r.json().get("data", {})
        return {
            "priceUsd": data.get("price", FALLBACK_PRICE),
            "priceChange": {
                "m5": data.get("variation5m", 0),
                "h1": data.get("variation1h", 0),
                "h6": data.get("variation6h", 0),
                "h24": data.get("variation24h", 0),
            }
        }
    except Exception:
        return {"priceUsd": FALLBACK_PRICE}