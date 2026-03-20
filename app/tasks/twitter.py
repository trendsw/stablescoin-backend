import requests
import json
from datetime import datetime, timedelta
from urllib.parse import urlparse
from sentence_transformers import SentenceTransformer, util  # pip install sentence-transformers
import torch
import os
from typing import List, Optional
import time
BEARER_TOKEN = os.getenv("X_API_KEY")

def chunk_list(lst, chunk_size):
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]

def get_related_tweets(
    article_url: str,
    article_title: str,
    article_content: str,
    bearer_token: str,
    usernames: Optional[List[str]] = None,
    max_results: int = 30,
    days_back: int = 7,
    min_likes: int = 5,
    only_verified: bool = False,
    extra_claims: list = None,
    include_fact_checks: bool = True,
    min_similarity: float = 0.7
):

    if days_back > 7:
        print("WARNING: Capping days_back to 7 (API limit).")
        days_back = 7

    if not article_content or not article_content.strip():
        raise ValueError("Article content is required for semantic similarity ranking.")

    if not usernames:
        raise ValueError("Usernames list required for per-user search.")

    headers = {
    "Authorization": f"Bearer {bearer_token}",
    "User-Agent": "MyAppBot/1.0"
    }

    model = SentenceTransformer('all-MiniLM-L6-v2')
    article_embedding = model.encode(article_content, convert_to_tensor=True)

    eval_terms = '(factcheck OR "fact check" OR debunked OR false OR hoax OR misinformation OR verify OR accurate OR true)'

    # -------------------------
    # Build base article queries
    # -------------------------
    bases = []

    if article_url and article_url.strip():
        domain = urlparse(article_url).netloc
        bases.append(f'url:"{article_url}" OR "{article_url}" OR url:{domain}')

    if article_title and article_title.strip():
        bases.append(f'"{article_title.strip()}"')

    if extra_claims:
        for claim in extra_claims:
            if claim and claim.strip():
                bases.append(f'"{claim.strip()}"')

    if not bases:
        raise ValueError("Need at least URL, title, or claims.")

    # -------------------------
    # 🔥 LOOP PER USER
    # -------------------------
    results = []

    for raw_username in usernames:

        username = raw_username.replace("@", "").strip()
        best_tweet_for_user = None
        best_score = 0

        for base in bases:

            queries = []
            queries.append(f'from:{username} ({base})')

            if include_fact_checks:
                queries.append(f'from:{username} ({base}) {eval_terms}')

            for query in queries:

                next_token = None
                page = 0

                while page < 3:  # limit pages per user
                    params = {
                        "query": query,
                        "max_results": 100,
                        "tweet.fields": "created_at,author_id,public_metrics,conversation_id,lang",
                        "user.fields": "username,name,verified,public_metrics",
                        "expansions": "author_id",
                        "start_time": (datetime.utcnow() - timedelta(days=days_back)).isoformat() + "Z",
                    }

                    if next_token:
                        params["next_token"] = next_token
                    time.sleep(60)
                    response = requests.get(
                        "https://api.twitter.com/2/tweets/search/recent",
                        headers=headers,
                        params=params
                    )

                    if response.status_code != 200:
                        print(f"API Error {response.status_code}: {response.text}")
                        break

                    data = response.json()
                    users_data = {u["id"]: u for u in data.get("includes", {}).get("users", [])}

                    for tweet in data.get("data", []):

                        metrics = tweet.get("public_metrics", {})

                        if metrics.get("like_count", 0) < min_likes:
                            continue

                        author = users_data.get(tweet["author_id"], {})
                        if only_verified and not author.get("verified"):
                            continue

                        content = tweet["text"]

                        tweet_embedding = model.encode(content, convert_to_tensor=True)
                        similarity = util.cos_sim(article_embedding, tweet_embedding)[0][0].item()

                        if similarity < min_similarity:
                            continue

                        if similarity > best_score:
                            best_score = similarity
                            best_tweet_for_user = {
                                "username": username,
                                "name": author.get("name", username),
                                "verified": author.get("verified", False),
                                "content": content,
                                "post_url": f"https://x.com/{username}/status/{tweet['id']}",
                                "created_at": tweet["created_at"],
                                "likes": metrics.get("like_count", 0),
                                "retweets": metrics.get("retweet_count", 0),
                                "replies": metrics.get("reply_count", 0),
                                "similarity_score": similarity,
                            }

                    meta = data.get("meta", {})
                    next_token = meta.get("next_token")
                    page += 1

                    if not next_token:
                        break

        # Save best tweet per user
        if best_tweet_for_user:
            results.append(best_tweet_for_user)

    # Final ranking across users
    results.sort(
        key=lambda x: (x["similarity_score"], x["likes"] + x["retweets"] * 2),
        reverse=True
    )

    return results[:max_results]
        
def get_related_tweets1(
    article_url: str,
    article_title: str,
    article_content: str,
    bearer_token: str,
    usernames: Optional[List[str]] = None,   # ✅ NEW
    max_results: int = 30,
    days_back: int = 7,
    min_likes: int = 5,
    only_verified: bool = False,
    extra_claims: list = None,
    include_fact_checks: bool = True,
    min_similarity: float = 0.7
):
    """
    Enhanced version:
    - Optionally restricts results to specific usernames
    - Maintains semantic similarity ranking
    """

    if days_back > 7:
        print("WARNING: Capping days_back to 7 (API limit).")
        days_back = 7

    if not article_content or not article_content.strip():
        raise ValueError("Article content is required for semantic similarity ranking.")

    headers = {"Authorization": f"Bearer {bearer_token}"}

    model = SentenceTransformer('all-MiniLM-L6-v2')
    article_embedding = model.encode(article_content, convert_to_tensor=True)

    eval_terms = '(factcheck OR "fact check" OR debunked OR false OR hoax OR misinformation OR verify OR accurate OR true)'

    queries = []
    bases = []

    # -------------------------
    # Build base article queries
    # -------------------------

    if article_url and article_url.strip():
        domain = urlparse(article_url).netloc
        url_query = f'url:"{article_url}" OR "{article_url}" OR url:{domain}'
        bases.append(url_query)

    if article_title and article_title.strip():
        bases.append(f'"{article_title.strip()}"')

    if extra_claims:
        for claim in extra_claims:
            if claim and claim.strip():
                bases.append(f'"{claim.strip()}"')

    if not bases:
        raise ValueError("Need at least URL, title, or claims.")

    # -------------------------
    # ✅ Add username filter
    # -------------------------
    MAX_USERS_PER_QUERY = 6
    all_tweets = {}
    
    user_filter = ""
    if usernames:
        for user_batch in chunk_list(usernames, MAX_USERS_PER_QUERY):
        
            cleaned = [u.replace("@", "").strip() for u in user_batch]
            user_query = " OR ".join([f"from:{u}" for u in cleaned])
            user_filter = f"({user_query})"

            for base in bases:
                queries = []
                queries.append(f"{user_filter} ({base})")

                if include_fact_checks:
                    queries.append(f"{user_filter} ({base}) {eval_terms}")              
                
    

    for query in set(queries):
        next_token = None
        page = 0

        while page < 5:
            params = {
                "query": query,
                "max_results": 100,
                "tweet.fields": "created_at,author_id,public_metrics,conversation_id,lang",
                "user.fields": "username,name,verified,public_metrics",
                "expansions": "author_id",
                "start_time": (datetime.utcnow() - timedelta(days=days_back)).isoformat() + "Z",
            }

            if next_token:
                params["next_token"] = next_token

            response = requests.get(
                "https://api.twitter.com/2/tweets/search/recent",
                headers=headers,
                params=params
            )

            if response.status_code != 200:
                print(f"API Error {response.status_code}: {response.text}")
                break

            data = response.json()
            users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}

            for tweet in data.get("data", []):
                tweet_id = tweet["id"]
                if tweet_id in all_tweets:
                    continue

                author = users.get(tweet["author_id"], {})
                username = author.get("username")
                if not username:
                    continue

                metrics = tweet.get("public_metrics", {})

                if metrics.get("like_count", 0) < min_likes:
                    continue
                if only_verified and not author.get("verified"):
                    continue

                content = tweet["text"]

                tweet_embedding = model.encode(content, convert_to_tensor=True)
                similarity = util.cos_sim(article_embedding, tweet_embedding)[0][0].item()

                if similarity < min_similarity:
                    continue

                all_tweets[tweet_id] = {
                    "username": username,
                    "name": author.get("name", username),
                    "verified": author.get("verified", False),
                    "content": content,
                    "post_url": f"https://x.com/{username}/status/{tweet_id}",
                    "created_at": tweet["created_at"],
                    "likes": metrics.get("like_count", 0),
                    "retweets": metrics.get("retweet_count", 0),
                    "replies": metrics.get("reply_count", 0),
                    "similarity_score": similarity,
                    "matched_query": query[:120],
                }

            meta = data.get("meta", {})
            next_token = meta.get("next_token")
            page += 1

            if not next_token:
                break

    tweet_list = list(all_tweets.values())

    tweet_list.sort(
        key=lambda x: (x["similarity_score"], x["likes"] + x["retweets"] * 2),
        reverse=True
    )

    return tweet_list[:max_results]



def search_user_tweets(usernames: List[str], keywords: str):
    url = "https://api.twitter.com/2/tweets/search/recent"

    user_query = " OR ".join([f"from:{u}" for u in usernames])

    query = f"({user_query}) {keywords} -is:retweet lang:en"

    headers = {
        "Authorization": f"Bearer {BEARER_TOKEN}"
    }

    params = {
        "query": query,
        "max_results": 100,
        "tweet.fields": "created_at,author_id,public_metrics,conversation_id,lang,referenced_tweets",
        "user.fields": "username,name,verified,public_metrics",
        "expansions": "author_id",
        "user.fields": "username,name",
        "start_time": (datetime.utcnow() - timedelta(days=10)).isoformat() + "Z",
    }

    response = requests.get(url, headers=headers, params=params)

    return response.json()

def parse_tweets(data):
    tweets = data.get("data", [])
    users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}

    results = []

    for tweet in tweets:
        user = users.get(tweet["author_id"], {})

        tweet_id = tweet["id"]
        username = user.get("username")
        name = user.get("name")

        tweet_link = f"https://x.com/{username}/status/{tweet_id}"

        results.append({
            "poster_id": tweet["author_id"],
            "poster_name": name,
            "username": username,
            "post_link": tweet_link,
            "text": tweet["text"],
            "created_at": tweet["created_at"],
            "metrics": tweet.get("public_metrics", {})
        })

    return results