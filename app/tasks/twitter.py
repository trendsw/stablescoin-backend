import requests
import json
from datetime import datetime, timedelta
from urllib.parse import urlparse

def get_related_tweets(
    article_url: str,
    article_title: str,
    bearer_token: str,
    max_results: int = 30,
    days_back: int = 30,
    min_likes: int = 0,          # filter low-engagement noise
    only_verified: bool = False, # set True to see only verified accounts
    extra_claims: list = None     # optional: ["exact claim 1", "exact claim 2"]
):
    """
    Returns a list of dicts with exactly what you asked for:
        - username
        - content (full tweet text)
        - post_url
    Plus useful extras for evaluating correctness (verified, engagement, date).
    """
    headers = {"Authorization": f"Bearer {bearer_token}"}
    
    # Build smart queries
    queries = []
    
    # 1. Best: anyone who actually linked the article
    if article_url:
        domain = urlparse(article_url).netloc
        queries.append(f'url:"{article_url}" OR "{article_url}" OR url:{domain}')
    
    # 2. Exact title (very strong signal)
    if article_title.strip():
        queries.append(f'"{article_title.strip()}"')
    
    # 3. Optional key claims from your scraped content
    if extra_claims:
        for claim in extra_claims:
            if claim.strip():
                queries.append(f'"{claim.strip()}"')
    
    all_tweets = {}  # deduplicate by tweet ID
    
    for query in queries:
        next_token = None
        page = 0
        
        while page < 5:  # safety limit (max ~500 tweets total)
            params = {
                "query": query,
                "max_results": 100,  # API max per call
                "tweet.fields": "created_at,author_id,public_metrics,conversation_id,lang,referenced_tweets",
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
            
            # Build user lookup
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
                
                # Optional filters
                if metrics.get("like_count", 0) < min_likes:
                    continue
                if only_verified and not author.get("verified"):
                    continue
                
                post_url = f"https://twitter.com/{username}/status/{tweet_id}"
                
                all_tweets[tweet_id] = {
                    "username": username,
                    "name": author.get("name", username),
                    "verified": author.get("verified", False),
                    "content": tweet["text"],
                    "post_url": post_url,
                    "created_at": tweet["created_at"],
                    "likes": metrics.get("like_count", 0),
                    "retweets": metrics.get("retweet_count", 0),
                    "replies": metrics.get("reply_count", 0),
                    "matched_query": query[:120]  # for debugging which query caught it
                }
            
            meta = data.get("meta", {})
            next_token = meta.get("next_token")
            page += 1
            
            if not next_token:
                break
    
    # Sort by total engagement (best for seeing real impact)
    tweet_list = list(all_tweets.values())
    tweet_list.sort(
        key=lambda x: x["likes"] + x["retweets"] * 2,
        reverse=True
    )
    
    return tweet_list[:max_results]