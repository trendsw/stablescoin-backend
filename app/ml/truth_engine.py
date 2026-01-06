from collections import defaultdict
from db.models import ClaimSupport, Article, Claim
  
def evaluate_truth(cluster, claims, articles, db):
    """
    Professional truth evaluation based on claim-level evidence.
    """

   # --- 1. Build claim -> credibility map ---
    claim_credibility = dict(
        db.query(Claim.id, Article.credibility_score)
        .join(Article, Claim.article_id == Article.id)
        .filter(Article.topic_cluster_id == cluster.id)
        .all()
    )

    # --- 2. Load ClaimSupport rows ---
    support_rows = db.query(ClaimSupport).filter(
        ClaimSupport.cluster_id == cluster.id
    ).all()

    # claim_id -> support/contradicting weight
    weighted_support = {}
    weighted_contradict = {}

    for row in support_rows:
        weight = claim_credibility.get(row.claim_id, 0.0)
        if row.support_type == "supporting":
            weighted_support[row.claim_id] = weighted_support.get(row.claim_id, 0.0) + weight
        elif row.support_type == "contradicting":
            weighted_contradict[row.claim_id] = weighted_contradict.get(row.claim_id, 0.0) + weight

    # --- 3. Evaluate each claim ---
    supporting_claims = []
    contradicting_claims = []
    supporting_weight = 0.0
    contradicting_weight = 0.0
    total_weight = 0.0

    for claim in claims:
        weight = claim_credibility.get(claim.id, 0.0)
        s = weighted_support.get(claim.id, weight)  # default to full weight if missing
        c = weighted_contradict.get(claim.id, 0.0)

        total_weight += 1.0
        supporting_weight += s
        contradicting_weight += c

        if s > c:
            supporting_claims.append(claim)
        elif c > s:
            contradicting_claims.append(claim)
        # equal s == c -> ignore for counts

    # --- 4. Compute confidence score ---
    confidence_score = round(supporting_weight / max(total_weight, 1e-6), 3)

    # --- 5. Verdict thresholds ---
    if confidence_score >= 0.8:
        verdict = "Highly likely true"
    elif confidence_score >= 0.6:
        verdict = "Likely true"
    elif confidence_score >= 0.4:
        verdict = "Inconclusive"
    else:
        verdict = "Likely false"

    # --- 6. Final truth summary ---
    cluster.final_truth_summary = (
        f"{verdict}. Weighted evidence from {len(articles)} articles: "
        f"{len(supporting_claims)} supporting, "
        f"{len(contradicting_claims)} contradicting."
    )
    cluster.confidence_score = confidence_score

    db.add(cluster)