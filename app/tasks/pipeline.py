import asyncio
from ingestion.scraper import scrape_all_sources, scrape_videos
from ml.embeddings import embed
from ml.claim_extraction import extract_claims, analyze_article
from ml.claim_comparison import compare_claims, semantic_group_claims, classify_group, save_supports, update_article_credibility
from ml.truth_engine import evaluate_truth
from core.logging import log
from ml.services.cluster_registry import get_cluster_index
from ml.services.topic_clustering import SIM_THRESHOLD, assign_topic_cluster
from db.models import TruthCluster, Article, Claim, ClaimSupport
from db.session import SessionLocal
from ingestion.persist import save_articles
from tenacity import retry, stop_after_attempt, wait_exponential
from db.helpers import get_all_cluster_ids
from ingestion.sources import SOURCE_CREDIBILITY_MAP
from datetime import datetime
from zoneinfo import ZoneInfo
from db.cloud_svg import CertificateData, upload_certificate_svg, generate_certificate_svg
from db.firebase import add_uhalisi_post, add_transaction, db, get_profile_by_email_or_wallet
from db.gasFee import gas_fee_calculate
from db.pricing import get_token_price_on_chain
from db.utils import generate_transaction_hash, calculate_required_tokens, calculate_block_number
from db.transfer import transfer_token_by_wallet, get_ip_token_address
import os
import firebase_admin
from firebase_admin import credentials, firestore
import uuid

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=1, max=10),
    reraise=True,
)
def process_article(article_id: int):
    db = SessionLocal()
    try:
        article = db.get(Article, article_id)

        if not article:
            raise ValueError(f"Article {article_id} not found")

        analysis = analyze_article(article.title, article.content)
        # ---- Assign article fields ----
        article.priority = analysis["priority"]
        article.category = analysis["category"]
        article.jp_title = analysis["ja"]["title"]
        article.jp_content = analysis["ja"]["content"]
        article.summary = analysis["summary"]
        article.title = analysis["new_title"]
        article.publish_date = datetime.now(ZoneInfo("Asia/Tokyo"))
        post_id = str(uuid.uuid4())
        tx_hash = generate_transaction_hash()
        data = CertificateData(
            post_id=post_id,
            title=analysis["new_title"],
            description=analysis["summary"],
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
            content=analysis["ja"]["content"],
            description= analysis["ja_content"],
            poster="dfs_0xc313b83f5c446db28c9352e67e784b4619735ec3",
            payment_method="credit_card",
            post_type="text",
            title=analysis["new_title"],
            tx_hash=tx_hash,
            stripe_session_id="cs_test_a1ZBJKlEqExCLQguWzP5wZ2CxXhNFtOHWoI8fZQLo1XRemCy4XtOt4RdLm"
        )
        article.uhalisi_id = post_id

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
        embedding = embed(article.content)
        index = get_cluster_index()

        cluster_id = assign_topic_cluster(article, embedding, index, db)

        # claims_data = extract_claims(article.content)
        claims_data = analysis.get("claims", [])
        for c in claims_data:
            db.add(Claim(
                article_id=article.id,
                claim_text=c["claim_text"],
                claim_type=c["claim_type"],
                sentiment=c["sentiment"],
            ))
        db.commit()
        return cluster_id
    except Exception as e:
        db.rollback()
        print("PROCESSING ARTICLE ERROR:", repr(e))
        raise
    finally:
        db.close()

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=1, max=10),
    reraise=True,
)
def evaluate_cluster(cluster_id: int):
    db = SessionLocal()
    try:
        cluster = db.get(TruthCluster, cluster_id)

        claims = (
            db.query(Claim, Article)
            .join(Article, Claim.article_id == Article.id)
            .filter(Article.topic_cluster_id == cluster_id)
            .all()
        )
        print("claims ===>", len(claims))
        if len(claims) < 2:
            db.query(ClaimSupport).filter(
                ClaimSupport.cluster_id == cluster_id
            ).delete(synchronize_session=False)
            db.commit()
            return
        
        db.query(ClaimSupport).filter(
            ClaimSupport.cluster_id == cluster_id
        ).delete(synchronize_session=False)
        db.commit()
        
        claim_objs = [c for c, _ in claims]
        article_map = {c.id: a for c, a in claims}
        
        groups = semantic_group_claims(claim_objs)

        truth_claim_ids = set()

        for group in groups.values():
            if len(group) < 2:
                continue

            supporting, contradicting = classify_group(group)

            support_score = sum(
                SOURCE_CREDIBILITY_MAP.get(
                article_map[c.id].source,
                0
                )
                for c in supporting
            )

            contradict_score = sum(
                SOURCE_CREDIBILITY_MAP.get(
                article_map[c.id].source,
                0
                )
                for c in contradicting
            )
            print("support_score", support_score)
            print("contradicting_score", contradict_score)
            if support_score >= contradict_score:
                truth_claim_ids.update(c.id for c in supporting)
                save_supports(db, cluster_id, supporting, "supporting")
            else:
                truth_claim_ids.update(c.id for c in contradicting)
                save_supports(db, cluster_id, contradicting, "contradicting")
        print(f"truth_claims {cluster_id}", truth_claim_ids)
        update_article_credibility(db, cluster_id, truth_claim_ids)
        
        db.commit()

    except Exception as e:
        db.rollback()
        print("CLUSTER EVALUATION ERROR:", repr(e))
        raise
    finally:
        db.close()
        
async def run_pipeline_async():
 
    articles = await scrape_all_sources()
    if not articles:
        log.info("pipeline_no_articles")
        return

    article_ids = save_articles(articles)
    print("article ids===>", article_ids)
    log.info("articles_saved", count=len(article_ids))

    touched_clusters: set[int] = set()
    
    for article_id in article_ids:
        try:
            log.info("processing_article_started", article_id=article_id)
            cluster_id = process_article(article_id)
            touched_clusters.add(cluster_id)
        except Exception as e:
            log.error(
                "article_processing_failed",
                article_id=article_id,
                error=str(e)
            )
            
    #cluster_ids = get_all_cluster_ids()
    
    log.info("evaluating_all_clusters", count=len(touched_clusters))
    
    for cluster_id in touched_clusters:
        try:
            log.info("evaluating_cluster_started", cluster_id=cluster_id)
            evaluate_cluster(cluster_id)
        except Exception as e:
            log.exception(
            "cluster_evaluation_failed",
            cluster_id=cluster_id
            )

    log.info(
        "pipeline_completed",
        cluster_count=len(touched_clusters)
    )   
    

def run_pipeline():
    """
    Synchronous entry point for schedulers / workers.
    Safely executes async pipeline.
    """
    try:
        asyncio.run(run_pipeline_async())
    except RuntimeError as e:
        # Handles case where an event loop already exists (rare but possible)
        log.warning("event_loop_exists_fallback", error=str(e))
        loop = asyncio.get_event_loop()
        loop.run_until_complete(run_pipeline_async())
    


# def run_pipeline():
#     try:
#         loop = asyncio.get_running_loop()
#     except RuntimeError:
#         asyncio.run(run_pipeline_async())
#     else:
        # asyncio.create_task(run_pipeline_async())