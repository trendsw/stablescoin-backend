import os
from dotenv import load_dotenv
from db.pricing import get_token_price_on_chain
from db.firebase import get_profile_by_email_or_wallet, get_gas_discount

BASE_FEE_USD = float(os.getenv("BASE_FEE_USD", "0.01"))
DFS_TOKEN_ADDRESS = os.getenv("DFS_ONCHAIN_TOKEN_ADDRESS")

def gas_fee_calculate(from_user: str, to_user: str) -> dict:
    dfs_price = get_token_price_on_chain(DFS_TOKEN_ADDRESS)["priceUsd"]
    dfs_price = dfs_price if dfs_price > 0 else 0.01

    from_profile = get_profile_by_email_or_wallet(from_user)
    to_profile = get_profile_by_email_or_wallet(to_user)

    base_fee_usd = BASE_FEE_USD

    if from_profile and to_profile:
        from_code = from_profile.get("geoLocation", {}).get("calling_code", "")
        to_code = to_profile.get("geoLocation", {}).get("calling_code", "")
        base_fee_usd = get_gas_discount(from_code, to_code)

    gas_fee_dfs = base_fee_usd / dfs_price

    return {
        "gasFeeInUsd": base_fee_usd,
        "gasFeeInDfs": round(gas_fee_dfs, 6)
    }