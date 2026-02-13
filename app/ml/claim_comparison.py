import numpy as np
from ml.embeddings import embed, embed_batch
from ml.llm import call_llm
from db.models import Claim, UnionFind, ClaimSupport, Article
from collections import defaultdict
import uuid
import firebase_admin
from firebase_admin import credentials, firestore
from db.cloud_svg import CertificateData, upload_certificate_svg, generate_certificate_svg
from db.firebase import add_uhalisi_post, add_transaction, db, get_profile_by_email_or_wallet
from db.gasFee import gas_fee_calculate
from db.pricing import get_token_price_on_chain
from db.utils import generate_transaction_hash, calculate_required_tokens, calculate_block_number
from db.transfer import transfer_token_by_wallet, get_ip_token_address
from ml.claim_extraction import extract_claims, analyze_article, extract_info, generate_uhalisi_posts
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from api.routes.articles import top_article_per_valid_cluster_subquery
from sqlalchemy.orm import Session, aliased

def cosine_similarity(a, b):
    # a = np.array(a, dtype="float32")
    # b = np.array(b, dtype="float32")

    # if a.shape != b.shape:
    #     raise ValueError(f"Embedding shape mismatch: {a.shape} vs {b.shape}")

    # denom = np.linalg.norm(a) * np.linalg.norm(b)
    # if denom == 0:
    #     return 0.0

    # return float(np.dot(a, b) / denom)
    return float(np.dot(a, b))



def llm_contradiction_check(text1: str, text2: str) -> str:
    prompt = """
    Determine the relationship between two claims.

    Return JSON with:
    - relationship: supporting | contradicting | unrelated
    """

    try:
        result = call_llm(
            prompt,
            f"CLAIM A: {text1}\nCLAIM B: {text2}"
        )
    except TypeError as e:
        print("LLM CALL SIGNATURE ERROR:", e)
        return "unrelated"

    if not isinstance(result, dict):
        print("LLM RAW RESULT:", result)
        return "unrelated"

    return result.get("relationship", "unrelated")

def compare_claims(
    claims: list[Claim],
    semantic_threshold: float = 0.75,
):
    if len(claims) < 2:
        return []

    texts = [c.claim_text for c in claims]
    vectors = embed_batch(texts)

    embeddings = {
        c.id: np.array(vec, dtype="float32")
        for c, vec in zip(claims, vectors)
    }

    results = set()

    for i, c1 in enumerate(claims):
        for j in range(i + 1, len(claims)):
            c2 = claims[j]

            sim = cosine_similarity(
                embeddings[c1.id],
                embeddings[c2.id],
            )

            if sim < semantic_threshold:
                continue

            relationship = llm_contradiction_check(
                c1.claim_text,
                c2.claim_text
            )

            if relationship in ("supporting", "contradicting"):
                results.add((c1.id, relationship))
                results.add((c2.id, relationship))

    return list(results)


def semantic_group_claims(claims, threshold=0.7):
    texts = [c.claim_text for c in claims]
    vectors = embed_batch(texts)

    embeddings = {
        c.id: np.array(vec, dtype="float32")
        for c, vec in zip(claims, vectors)
    }

    uf = UnionFind()
    ids = list(embeddings.keys())

    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            sim = cosine_similarity(
                embeddings[ids[i]],
                embeddings[ids[j]],
            )
            if sim >= threshold:
                uf.union(ids[i], ids[j])

    groups = defaultdict(list)
    for c in claims:
        groups[uf.find(c.id)].append(c)

    return groups

# ---------------------------------------------------------
# Step 2: Support vs Contradiction inside group
# ---------------------------------------------------------
def classify_group(group):
    anchor = group[0]
    supporting = []
    contradicting = []

    for c in group:
        if c.id == anchor.id:
            supporting.append(c)
            continue

        stance = llm_contradiction_check(anchor.claim_text, c.claim_text)

        if stance == "contradicting":
            contradicting.append(c)
        else:
            supporting.append(c)

    return supporting, contradicting


# ---------------------------------------------------------
# Step 3: Persist truth supports
# ---------------------------------------------------------
def save_supports(db, cluster_id, claims, support_type):
    db.bulk_save_objects([
        ClaimSupport(
            cluster_id=cluster_id,
            claim_id=c.id,
            support_type=support_type
        )
        for c in claims
    ])


# ---------------------------------------------------------
# Step 4: Update article credibility
# ---------------------------------------------------------
def update_article_credibility(db, cluster_id,  truth_claim_ids):

    article_claims = (
        db.query(Claim.article_id, Claim.id)
        .join(Article, Claim.article_id == Article.id)
        .filter(Article.topic_cluster_id == cluster_id)
        .all()
    )

    article_totals = defaultdict(int)
    article_truths = defaultdict(int)

    for article_id, claim_id in article_claims:
        article_totals[article_id] += 1
        if claim_id in truth_claim_ids:
            article_truths[article_id] += 1

    for article_id in article_totals:
        score = article_truths[article_id] / article_totals[article_id]
        db.query(Article).filter(
            Article.id == article_id
        ).update({"credibility_score": score})
        db.commit()
        
        ranked_sq = top_article_per_valid_cluster_subquery(db)
        RankedArticle = aliased(Article, ranked_sq)
        top_articles = (
            db.query(RankedArticle)
            .filter(ranked_sq.c.rn == 1)
            .all()
        )
        
        print("length of trust articles===>", len(top_articles))
        
        article = db.query(Article).filter(Article.id == article_id).first()
        is_trust = any(item.url == article.url for item in top_articles)
        cur_article = db.get(Article, article_id)
        if is_trust: 
            print("trust title==>", article.jp_title)
            print("trust content==>", article.jp_content)
            
            post_id = str(uuid.uuid4())
            tx_hash = generate_transaction_hash()
            data = CertificateData(
                post_id=post_id,
                title=article.jp_title,
                description=article.jp_content,
                poster_wallet="0xe8646b5fa4bcd037b322dfe50a6f2b10bcc9ea24",
                timestamp=datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(),
                tx_hash=tx_hash
            )

            svg = generate_certificate_svg(data)

            cert_url = upload_certificate_svg(
                    svg,
                    public_id=f"certificate_{data.post_id}"
            )

            print(cert_url)
            ip_price = get_token_price_on_chain(os.getenv("IP_ONCHAIN_TOKEN_ADDRESS"))
            gas = gas_fee_calculate(os.getenv("FROM_ADDRESS"), os.getenv("TO_ADDRESS"))

            required_ip = calculate_required_tokens(0.5, ip_price["priceUsd"])
            
            
            ip_token_address = get_ip_token_address()
            
            result = transfer_token_by_wallet(
                from_wallet=os.getenv("FROM_ADDRESS"),
                to_wallet=os.getenv("TO_ADDRESS"),
                token_address=ip_token_address,
                amount=required_ip,
            )
            
            post_id = add_uhalisi_post(
                cert_url=cert_url,
                commission_fee=0.5,
                content=article.jp_content,
                description= article.summary,
                poster="dfs_0xc313b83f5c446db28c9352e67e784b4619735ec3",
                payment_method="credit_card",
                post_type="text",
                title=article.jp_title,
                tx_hash=tx_hash,
                stripe_session_id="cs_test_a1ZBJKlEqExCLQguWzP5wZ2CxXhNFtOHWoI8fZQLo1XRemCy4XtOt4RdLm"
            )
            cur_article.uhalisi_id = post_id
            db.commit()
            firebase_db = firestore.client()
            from_user = get_profile_by_email_or_wallet("dfs_0xe8646b5fa4bcd037b322dfe50a6f2b10bcc9ea24")
            to_user = get_profile_by_email_or_wallet("dfs_0x8aaa0fbdcc8ca4bed440e9f13576732061cd044d")
            fromEmail = from_user.get("email", "")
            toEmail = to_user.get("email", "")
            blockNumber = calculate_block_number()
            token_ref = firebase_db.collection("tokens")
            query = token_ref.where("symbol", "==", "IP").limit(1)
            results = query.get()
            if results:
                token_doc = results[0]
                
            else:
                print("there is no IP token data")
            print("token ID===>", token_doc.id)
            tokenData = token_doc.to_dict()
            token = {
                "id" : token_doc.id,
                "logoUrl" : tokenData.get("logoUrl", ""),
                "name" : tokenData.get("name", ""),
                "symbol" : tokenData.get("symbol", ""),
                "tokenAddress" : tokenData.get("tokenAddress", "")
            }
            transaction_id = add_transaction(float(required_ip), blockNumber, "dfs_0xe8646b5fa4bcd037b322dfe50a6f2b10bcc9ea24", fromEmail, float(gas["gasFeeInDfs"]), float(gas["gasFeeInUsd"]), "dfs_0x8aaa0fbdcc8ca4bed440e9f13576732061cd044d", toEmail, token, tx_hash)
            print("token data===>", token_doc)
            print("fromEmail:", fromEmail)
            print("toEmial:", toEmail)
            print("blockNumber:", blockNumber)
            print("transaction result:", transaction_id)
        else:
            continue
