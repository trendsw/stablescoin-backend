import numpy as np
from ml.embeddings import embed, embed_batch
from ml.llm import call_llm
from db.models import Claim, UnionFind, ClaimSupport, Article
from collections import defaultdict

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

    # article_claims = (
    #     db.query(Claim.article_id, Claim.id)
    #     .all()
    # )

    # article_totals = defaultdict(int)
    # article_truths = defaultdict(int)

    # for article_id, claim_id in article_claims:
    #     article_totals[article_id] += 1
    #     if claim_id in truth_claim_ids:
    #         article_truths[article_id] += 1

    # for article_id in article_totals:
    #     score = article_truths[article_id] / article_totals[article_id]
    #     db.query(Article).filter(
    #         Article.id == article_id
    #     ).update({"credibility_score": score})
    #     db.commit()
    

# def compare_claims(
#     claims: list[Claim],
#     semantic_threshold: float = 0.75,
# ):
#     if len(claims) < 2:
#         return []

#     embeddings = {}

#     for c in claims:
#         raw = embed(c.claim_text)

#         # Normalize embedding shape
#         if isinstance(raw, list) and isinstance(raw[0], list):
#             raw = raw[0]

#         vec = np.array(raw, dtype="float32")

#         if vec.ndim != 1:
#             raise ValueError(f"Invalid embedding shape: {vec.shape}")

#         embeddings[c.id] = vec
#     results = set()
#     try: 
#         for i, c1 in enumerate(claims):
#             for j, c2 in enumerate(claims):
#                 if i >= j:
#                     continue

#                 sim = cosine_similarity(
#                     embeddings[c1.id],
#                     embeddings[c2.id],
#                 )

#                 if sim < semantic_threshold:
#                     continue

#                 relationship = llm_contradiction_check(
#                     c1.claim_text,
#                     c2.claim_text
#                 )
#                 print("LLM relationship raw:", relationship, type(relationship))
#                 if relationship in ("supporting", "contradicting"):
#                     results.add((c1.id, relationship))
#                     results.add((c2.id, relationship))
#     except Exception as e:
#         print("comparison exception===>", str(e))
        
#     return list(results)


# def semantic_group_claims(claims, threshold=0.75):
#     embeddings = {}
#     uf = UnionFind()

#     for c in claims:
#         vec = embed(c.claim_text)
#         if isinstance(vec[0], list):
#             vec = vec[0]
#         embeddings[c.id] = np.array(vec, dtype="float32")

#     ids = list(embeddings.keys())

#     for i in range(len(ids)):
#         for j in range(i + 1, len(ids)):
#             sim = cosine_similarity(
#                 embeddings[ids[i]],
#                 embeddings[ids[j]],
#             )
#             if sim >= threshold:
#                 uf.union(ids[i], ids[j])

#     groups = defaultdict(list)
#     for c in claims:
#         root = uf.find(c.id)
#         groups[root].append(c)

#     return groups