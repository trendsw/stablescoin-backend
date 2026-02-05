from google.cloud import firestore
from db.firebase import db
def get_user_doc_by_wallet(wallet_address: str):
    query = (
        db.collection("users")
        .where("walletAddress", "==", wallet_address)
        .limit(1)
        .stream()
    )

    for doc in query:
        return doc.reference, doc.to_dict()

    return None, None

def find_token_index_by_address(tokens: list, token_address: str):
    for i, token in enumerate(tokens):
        if token.get("tokenAddress") == token_address:
            return i
    return None

def transfer_token_by_wallet(
    from_wallet: str,
    to_wallet: str,
    token_address: str,
    amount: float,
):
    if amount <= 0:
        raise ValueError("Amount must be greater than zero")

    transaction = db.transaction()

    @firestore.transactional
    def _transfer(tx):
        from_ref, from_data = get_user_doc_by_wallet(from_wallet)
        to_ref, to_data = get_user_doc_by_wallet(to_wallet)

        if not from_ref or not to_ref:
            raise ValueError("Sender or receiver wallet not found")

        from_tokens = from_data.get("tokens", [])
        to_tokens = to_data.get("tokens", [])

        from_idx = find_token_index_by_address(from_tokens, token_address)
        to_idx = find_token_index_by_address(to_tokens, token_address)

        if from_idx is None:
            raise ValueError("Sender does not own this token")

        if to_idx is None:
            raise ValueError("Receiver does not own this token")

        sender_balance = from_tokens[from_idx]["balance"]

        if sender_balance < amount:
            raise ValueError("Insufficient token balance")

        # 🔄 Update balances
        from_tokens[from_idx]["balance"] = sender_balance - amount
        to_tokens[to_idx]["balance"] += amount

        # 💾 Commit updates
        tx.update(from_ref, {"tokens": from_tokens})
        tx.update(to_ref, {"tokens": to_tokens})

        return {
            "tokenAddress": token_address,
            "fromWallet": from_wallet,
            "toWallet": to_wallet,
            "amount": amount,
            "senderRemainingBalance": from_tokens[from_idx]["balance"],
        }

    return _transfer(transaction)

def get_ip_token_address():
    tokens_ref = db.collection("tokens")
    # query for the document where symbol is "IP"
    query = tokens_ref.where("symbol", "==", "IP").limit(1)
    results = query.get()

    if results:
        token_doc = results[0]
        token_data = token_doc.to_dict()
        return token_data.get("tokenAddress")
    else:
        return None