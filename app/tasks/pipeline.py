import asyncio
from ingestion.scraper import scrape_all_sources, scrape_videos
from ml.embeddings import embed
from ml.claim_extraction import extract_claims, analyze_article_no_claim, extract_info
from ml.claim_comparison import compare_claims, semantic_group_claims, classify_group, save_supports, update_article_credibility, llm_contradiction_check
from ml.truth_engine import evaluate_truth
from ml.llm import call_llm
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
from db.firebase import db as firebase_db
from tasks.twitter import get_related_tweets, search_user_tweets, parse_tweets
import httpx
from fastapi import HTTPException
import requests
import re
STOPWORDS = {
    "a","an","the","and","or","but","if","while","with","to","from","of",
    "in","on","at","for","by","after","before","latest","new"
}
X_SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"
BEARER_TOKEN = os.getenv("X_API_KEY")

def detect_stance(title: str, content: str, tweet_text: str):
    system_prompt = """
    You are a stance detection engine.

    Compare the tweet with the news article.

    Return strictly valid JSON in this format:

    {
      "stance": "SUPPORT" | "CONTRADICT" | "NEUTRAL",
      "confidence": 0.0-1.0
    }

    No explanations.
    JSON only.
    """

    user_text = f"""
    News Article:
    Title: {title}
    Content: {content}

    Tweet:
    {tweet_text}
    """

    try:
        result = call_llm(system_prompt, user_text)

        stance = result.get("stance", "NEUTRAL")
        confidence = float(result.get("confidence", 0.0))

        # If invalid stance → fallback to NEUTRAL
        if stance not in ["SUPPORT", "CONTRADICT", "NEUTRAL"]:
            return {
                "stance": "NEUTRAL",
                "confidence": 0.0
            }

        return {
            "stance": stance,
            "confidence": round(confidence, 2)
        }

    except Exception:
        # Any parsing / API / JSON error
        return {
            "stance": "NEUTRAL",
            "confidence": 0.0
        }


def build_query(title: str):

    # remove punctuation except letters/numbers
    cleaned = re.sub(r"[^\w\s]", " ", title)

    words = cleaned.split()

    keywords = []

    for w in words:
        if w.lower() not in STOPWORDS:
            keywords.append(w)

    keywords = keywords[:3]

    query = " ".join(keywords)

    # query += " -is:retweet lang:en"

    return query

def chunk_list(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]
        
async def process_twitter(article_id, title):
    db = SessionLocal()
    try:
        article = db.get(Article, article_id)

        if not article:
            raise ValueError(f"Article {article_id} not found")
        
        BEARER_TOKEN = os.getenv("X_API_KEY") # Paste your bearer token here
    
        ARTICLE_URL = article.url
        ARTICLE_TITLE = title
        ARTICLE_CONTENT = article.content  # NEW: Pull full content from DB for semantic similarity
        
        # Optional: Add claims if you extract them programmatically from content
        CLAIMS = None  # e.g., extract_key_claims(ARTICLE_CONTENT) if you have such a func
        
        # usernames = [           
        #     "VitalikButerin",
        #     "saylor",
        #     "justinsuntron",
        #     "APompliano",
        #     "MMCrypto",
        #     "Ashcryptoreal",
        #     "balajis",
        #     "elonmusk",
        #     "cz_binance",
        #     "nayibbukele",
        #     "aantonop",
        #     "CamiRusso",
        #     "CathieDWood",
        #     "ArthurHayes",
        #     "RaoulGMI",
        #     "Missteencrypto",
        #     "Girlgone_Crypto",
        #     "pierre_rochard",
        #     "NickSzabo4",
        #     "TySmithHQ",
                       
        # ]
        
        tweets = []
        headers = {
            "Authorization": f"Bearer {BEARER_TOKEN}"
        }
        # username_batches = list(chunk_list(usernames, 6))
        
        # for batch in username_batches:

        #     user_query = " OR ".join([f"from:{u}" for u in batch])

        keyword_query = build_query(ARTICLE_TITLE)

        # query = f"({keyword_query}) ({user_query}) -is:retweet lang:en"
        query = f"({keyword_query}) -is:retweet lang:en"

        params = {
                "query": query,
                "max_results": 10,
                "tweet.fields": "created_at,public_metrics",
                "expansions": "author_id",
                "user.fields": "username,name,profile_image_url"
            }


        response = requests.get(X_SEARCH_URL, headers=headers, params=params)

        if response.status_code != 200:
                raise Exception(response.text)

        data = response.json()

        users_map = {}
        for u in data.get("includes", {}).get("users", []):
                users_map[u["id"]] = {
                    "username": u.get("username"),
                    "name": u.get("name"),
                    "avatar" : u.get("profile_image_url"),
                    "profile_url" : f"https://twitter.com/{u.get('username')}"
                }
                
        for tweet in data.get("data", []):
                author = users_map.get(tweet.get("author_id"), {})
                tweet_data = {
                    "id": tweet.get("id"),
                    "text": tweet.get("text"),
                    "created_at": tweet.get("created_at"),
                    "metrics": tweet.get("public_metrics"),
                    "username": author.get("username", "unknown"),
                    "name": author.get("name", "unknown"),
                    "avatar": author.get("avatar"),
                    "profile_url": author.get("profile_url"),
                    "tweet_url": f"https://x.com/{author.get('username')}/status/{tweet.get('id')}"  # ✅ tweet link
                }
                tweets.append(tweet_data)
            # if "data" in data:
            #     tweets.extend(data["data"])
        
        print(f"article id {article_id}")
        # return tweets
        users_ref = firebase_db.collection("twitter_users")
        
               
        for i, t in enumerate(tweets):
            # print(f"{i:2d}. @{t['username']}")
            print(f"{t['avatar']}")
            print(f"{t['profile_url']}")
            print(f"{t['username']}")
            print(f"   {t['text']}")
            print(f"tweet_url")
            post_url = f"https://x.com/{t['username']}/status/{t['id']}"
            print(f"   {t['created_at']}")
            print("-" * 80)
            query = users_ref.where("xuser_name", "==", t['username']).limit(1).stream()
            user_doc = None
            for doc in query:
                user_doc = doc
                break
            if user_doc is None:
                new_user_ref = users_ref.add({
                    "username": t['username'],
                    "name": t['name'],
                    "avatar" : t['avatar'],
                    "profile_url" : t['profile_url'],
                })
                user_id = new_user_ref[1].id
                print("if new user ref===>", new_user_ref)
            else:
                user_id = user_doc.id
                print("else user doc", user_doc)
                
            
            posts_ref = firebase_db.collection("twitter_posts")
            supporting = llm_contradiction_check(ARTICLE_TITLE, t['text'])
            print("supporting=====>", supporting)
            if supporting in ("supporting", "contradicting"):
                post_ref = posts_ref.add({
                    "name": t['name'],
                    "username": t['username'],
                    "content": t['text'],
                    "post_url": post_url,
                    "avatar" : t['avatar'],
                    "profile_url" : t['profile_url'],
                    "article_id": article_id,
                    "supporting_type": supporting
                })          
            
            
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
async def process_article(article_id: int):
    db = SessionLocal()
    try:
        article = db.get(Article, article_id)

        if not article:
            raise ValueError(f"Article {article_id} not found")
        title = article.title
        await process_twitter(article_id, title)
        analysis = analyze_article_no_claim(article.title, article.content)
        
        # ---- Assign article fields ----
        article.priority = analysis["priority"]
        article.category = analysis["category"]
        article.jp_title = analysis["ja"]["title"]
        article.jp_content = analysis["ja"]["content"]
        article.summary = analysis["summary"]
        article.title = analysis["new_title"]
        article.publish_date = datetime.now(ZoneInfo("Asia/Tokyo"))
        db.commit()
        
        
        
        # embedding = embed(article.content)
        # index = get_cluster_index()

        # cluster_id = assign_topic_cluster(article, embedding, index, db)

        # # claims_data = extract_claims(article.content)
        # claims_data = analysis.get("claims", [])
        # for c in claims_data:
        #     db.add(Claim(
        #         article_id=article.id,
        #         claim_text=c["claim_text"],
        #         claim_type=c["claim_type"],
        #         sentiment=c["sentiment"],
        #     ))
        
        # return cluster_id
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

    for article_id in article_ids:
        try:
            log.info("processing_article_started", article_id=article_id)
            await process_article(article_id)
            
        except Exception as e:
            log.error(
                "article_processing_failed",
                article_id=article_id,
                error=str(e)
            )           
    # touched_clusters: set[int] = set()
    
    # for article_id in article_ids:
    #     try:
    #         log.info("processing_article_started", article_id=article_id)
    #         cluster_id = process_article(article_id)
    #         touched_clusters.add(cluster_id)
    #     except Exception as e:
    #         log.error(
    #             "article_processing_failed",
    #             article_id=article_id,
    #             error=str(e)
    #         )
            
    #cluster_ids = get_all_cluster_ids()
    
    # log.info("evaluating_all_clusters", count=len(touched_clusters))
    
    # for cluster_id in touched_clusters:
    #     try:
    #         log.info("evaluating_cluster_started", cluster_id=cluster_id)
    #         evaluate_cluster(cluster_id)
    #     except Exception as e:
    #         log.exception(
    #         "cluster_evaluation_failed",
    #         cluster_id=cluster_id
    #         )

    # log.info(
    #     "pipeline_completed",
    #     cluster_count=len(touched_clusters)
    # )   
    

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