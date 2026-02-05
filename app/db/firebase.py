import firebase_admin
from firebase_admin import credentials, firestore

# Initialize Firebase only once
if not firebase_admin._apps:
    cred = credentials.Certificate("./key.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

def get_profile_by_email_or_wallet(email_or_wallet: str):
    users_ref = db.collection("users")

    query = users_ref.where("email", "==", email_or_wallet).limit(1).stream()
    docs = list(query)

    if not docs:
        query = users_ref.where("walletAddress", "==", email_or_wallet).limit(1).stream()
        docs = list(query)

    if not docs:
        return None

    return docs[0].to_dict()


def get_gas_discount(from_calling_code: str, to_calling_code: str) -> float:
    discounts = (
        db.collection("gas_discount")
        .where("callingCode", "==", from_calling_code)
        .limit(1)
        .stream()
    )

    docs = list(discounts)
    base_fee = 0.01
    discount_fee = 0.01

    if docs:
        data = docs[0].to_dict()
        base_fee = float(data.get("baseFee", base_fee))
        discount_fee = float(data.get("discountFee", base_fee))

    return discount_fee if from_calling_code == to_calling_code else base_fee


def add_uhalisi_post(
    cert_url: str,
    commission_fee: float,
    content: str,
    description: str,
    poster: str,
    payment_method: str,
    post_type: str,
    title: str,
    tx_hash: str,
    reference_url: str = None,
    stripe_session_id: str = None,
    owner: str = None
):
    doc_ref = db.collection("uhalisi_posts").document()  # auto-generated ID
    data = {
        "cert": cert_url,
        "commissionFee": commission_fee,
        "content": content,
        "createdAt": firestore.SERVER_TIMESTAMP,
        "description": description,
        "owner": owner,
        "paymentMethod": payment_method,
        "post_type": post_type,
        "poster": poster,
        "referenceUrl": reference_url,
        "stripeSessionId": stripe_session_id,
        "title": title,
        "txHash": tx_hash,
        "updatedAt": firestore.SERVER_TIMESTAMP
    }
    doc_ref.set(data)
    print(f"Added post with ID: {doc_ref.id}")
    return doc_ref.id