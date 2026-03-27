from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session, aliased
from sqlalchemy import text, func, and_, desc, or_, distinct, asc
from db.models import Article
from db.session import get_db
from db.schemas import ArticleOut, HomeArticlesResponse, PaginatedArticlesOut
from urllib.parse import urlparse
from typing import List, Optional, Dict
from db.firebase import db as firebase_db

router = APIRouter()
posts_ref = firebase_db.collection("twitter_posts")


def fetch_related_posts(article_id: int, limit: int = 3):
    posts_ref = firebase_db.collection("twitter_posts")

    posts_query = (
        posts_ref
        .where("article_id", "==", article_id)
        .where("supporting_type", "in", ["supporting", "contradicting"])
    )

    posts_snapshot = posts_query.stream()

    posts = [post.to_dict() for post in posts_snapshot]

    if not posts:
        return []

    grouped_posts = {"supporting": {}, "contradicting": {}}

    for post in posts:
        supporting_type = post.get("supporting_type")
        username = post.get("username")

        if supporting_type in grouped_posts:
            grouped_posts[supporting_type].setdefault(username, []).append(post)

    # limit per user
    result = []
    for supporting_type, users_posts in grouped_posts.items():
        users_data = []
        for user, posts in users_posts.items():
            users_data.append({
                "username": user,
                "posts": posts[:limit]
            })

        result.append({
            "supporting_type": supporting_type,
            "users": users_data
        })

    return result

def top_article_per_valid_cluster_subquery(db: Session):
    
     # 1️⃣ Query Firebase for posts with 'supporting' or 'contradicting' types
    posts_ref = firebase_db.collection("twitter_posts")
    posts_query = posts_ref.where("supporting_type", "in", ["supporting", "contradicting"])

    # Get the posts from Firebase and extract the article_ids
    posts_snapshot = posts_query.stream()
    article_ids_with_supporting_posts = {post.to_dict().get('article_id') for post in posts_snapshot}

    # 2️⃣ Query PostgreSQL to get articles with matching article_ids
    latest_article = (
        db.query(Article)
        .filter(Article.id.in_(article_ids_with_supporting_posts))  # Only include articles with supporting/contradicting posts
        .filter(Article.image_url.isnot(None))  # Ensure the article has an image
        .order_by(desc(Article.publish_date))  # Order by the latest publish date
        .subquery()  # Return as a subquery for further use
    )
    
    return latest_article

def latest_per_slug_subquery(db: Session):
    return (
        db.query(
            Article.slug,
            func.max(Article.publish_date).label("max_date"),
        )
        .group_by(Article.slug)
        .subquery()
    )
    
def serialize_article(a: Article):
    related_posts = fetch_related_posts(a.id)
    return {
        "id": a.id,
        "title": a.title,
        "excerpt": a.summary or a.content[:200],
        "slug": a.slug,
        "image": a.image_url,
        "url": a.url,
        "country": a.country,
        "date": a.publish_date.strftime("%d %b %Y %H:%M") if a.publish_date else None,
        "source": a.source,
        "summary": a.summary or "",
        "uhalisi_id" : a.uhalisi_id or "",
        "related_posts" : related_posts,
    }

def serialize_article_ja(a: Article):
    related_posts = fetch_related_posts(a.id)
    return {
        "id": a.id,
        "title": a.jp_title,
        "excerpt": a.jp_content,
        "slug": a.slug,
        "image": a.image_url,
        "url": a.url,
        "country": a.country,
        "date": a.publish_date.strftime("%d %b %Y %H:%M") if a.publish_date else None,
        "source": a.source,
        "summary": a.summary or "",
        "credibilityScore": a.credibility_score,
        "uhalisi_id" : a.uhalisi_id or "",
        "related_posts" : related_posts,
    }
    
def generate_slug(url: str, title: str) -> str:
    """
    Generate a URL-friendly slug for an article.
    - Prefer last path segment from URL if available.
    - Fallback to title-based slug if URL path is empty.
    """
    if url:
        path = urlparse(url).path  # /news/grant-cardone-bitcoin-real-estate-trump-housing/
        last_segment = path.rstrip("/").split("/")[-1]  # grant-cardone-bitcoin-real-estate-trump-housing
        if last_segment:
            return last_segment.lower()
    # Fallback to title
    slug = (
        title.lower()
        .replace("&", "and")
        .replace("?", "")
        .replace("'", "")
    )
    slug = "-".join(slug.split())  # replace spaces with hyphens
    return slug

def map_article(article: Article, locale: str) -> ArticleOut:
    title = (
        article.jp_title if locale == "ja" and article.jp_title
        else article.title
    )

    content = (
        article.jp_content if locale == "ja" and article.jp_content
        else article.content or ""
    )

    # slug = generate_slug(article.url, title)
    related_posts = fetch_related_posts(article.id)
    return ArticleOut(
        id=article.id,
        title=article.title,
        excerpt=content,
        url= article.url,
        image=article.image_url or "",
        slug=article.slug,
        summary= article.summary,
        date=article.publish_date.strftime("%d %b %Y %H:%M"),
        source = article.source,
        country= article.country,
        uhalisi_id = article.uhalisi_id or "",
        related_posts=related_posts,
    )


@router.get(
    "/articles/search",
    response_model=list[ArticleOut],
)
def search_articles(
    search: str,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    if not search.strip():
        raise HTTPException(status_code=400, detail="Search query is empty")
    ranked_sq = top_article_per_valid_cluster_subquery(db)
    RankedArticle = aliased(Article, ranked_sq)
    
    articles = (
        db.query(RankedArticle)
        # .filter(ranked_sq.c.rn == 1)
        # .filter(RankedArticle.uhalisi_id.isnot(None))  # Check for non-NULL
        # .filter(RankedArticle.uhalisi_id != '')
        .filter(
            or_(
                RankedArticle.jp_title.ilike(f"%{search}%"),
                RankedArticle.title.ilike(f"%{search}%"),
            )
        )
        .order_by(
            RankedArticle.credibility_score.desc(),
            RankedArticle.publish_date.desc(),
        )
        .limit(limit)
        .all()
    )

    return [serialize_article(a) for a in articles]

@router.get("/articles/home", response_model=HomeArticlesResponse)
def get_home_articles(
    locale: str = Query("en", regex="^(en|ja)$"),
    db: Session = Depends(get_db),
):
    
    ranked_sq = top_article_per_valid_cluster_subquery(db)
    RankedArticle = aliased(Article, ranked_sq)

    articles = (
        db.query(RankedArticle)
        # .filter(RankedArticle.uhalisi_id.isnot(None))  # Check for non-NULL
        # .filter(RankedArticle.uhalisi_id != '')
        .order_by(
            RankedArticle.publish_date.desc(),
            RankedArticle.credibility_score.desc(),
        )
        .limit(15)
        .all()
    )
    
    if not articles:
        raise HTTPException(status_code=404, detail="No articles found")

    mapped = [map_article(a, locale) for a in articles]

    return HomeArticlesResponse(
        featuredArticle=mapped[0],
        sideArticles=mapped[1:6],
        storyCards=mapped[6:8],
        articleListItems=mapped[8:15],
    )

@router.get("/posts/{article_id}/related", response_model=List[Dict])
def get_related_posts_by_article(
    article_id: int,
    limit: int = 10,  # Optional: Limit the number of posts returned
    db: Session = Depends(get_db),  # Database session dependency
):
    # 1️⃣ Query Firebase to get posts related to the article_id
    posts_ref = firebase_db.collection("twitter_posts")
    posts_query = posts_ref.where("article_id", "==", article_id).where("supporting_type", "in", ["supporting", "contradicting"])

    posts_snapshot = posts_query.stream()

    # Debugging: Check the data we are retrieving
    print(f"Fetching posts for article_id: {article_id}")
    
    posts = []
    for post in posts_snapshot:
        post_data = post.to_dict()
        print(f"Post data: {post_data}")  # Debugging: Print the post data
        posts.append(post_data)
    
    # 2️⃣ If no posts were found
    if not posts:
        raise HTTPException(status_code=404, detail="No posts found for this article")
    
    # Grouping posts by supporting_type and username
    grouped_posts = {"supporting": {}, "contradicting": {}}
    
    for post in posts:
        supporting_type = post.get("supporting_type")
        username = post.get("username")
        
        if supporting_type in grouped_posts:
            if username not in grouped_posts[supporting_type]:
                grouped_posts[supporting_type][username] = []
            grouped_posts[supporting_type][username].append(post)
    
    # Limiting the posts per user
    limited_grouped_posts = {}
    for supporting_type, users_posts in grouped_posts.items():
        limited_grouped_posts[supporting_type] = {}
        for user, posts in users_posts.items():
            limited_grouped_posts[supporting_type][user] = posts[:limit]  # Limit to `limit` posts per user

    return [
        {"supporting_type": supporting_type, "users": [
            {"username": user, "posts": posts}
            for user, posts in users_posts.items()
        ]}
        for supporting_type, users_posts in limited_grouped_posts.items()
    ]

@router.get("/articles/counts")
def get_article_counts(db: Session = Depends(get_db)):
    # Priority counts: top, major, breaking
    
    ranked_sq = top_article_per_valid_cluster_subquery(db)
    RankedArticle = aliased(Article, ranked_sq)
    priority_counts = (
        db.query(RankedArticle.priority, func.count(RankedArticle.id))
        # .filter(ranked_sq.c.rn == 1)
        # .filter(RankedArticle.uhalisi_id.isnot(None))  # Check for non-NULL
        # .filter(RankedArticle.uhalisi_id != '')
        .group_by(RankedArticle.priority)
        .all()
    )
    priority_dict = {p: c for p, c in priority_counts if p}

    # Category counts
    category_counts = (
        db.query(RankedArticle.category, func.count(RankedArticle.id))
        # .filter(ranked_sq.c.rn == 1)
        .group_by(RankedArticle.category)
        .all()
    )
    category_dict = {c: n for c, n in category_counts if c}

    return {
        "priority": priority_dict,
        "category": category_dict
    }
    
@router.get("/articles/breaking", response_model=List[ArticleOut])
def get_breaking_articles(
    locale: str = Query("en", regex="^(en|ja)$"),
    limit: int = 10,
    db: Session = Depends(get_db),
):
    """
    Return latest BREAKING articles (one per cluster).
    """
    ranked_sq = top_article_per_valid_cluster_subquery(db)
    RankedArticle = aliased(Article, ranked_sq)

    articles = (
        db.query(RankedArticle)
        # .filter(ranked_sq.c.rn == 1)
        .filter(RankedArticle.priority == "breaking")
        # .filter(RankedArticle.uhalisi_id.isnot(None))  # Check for non-NULL
        # .filter(RankedArticle.uhalisi_id != '')
        .order_by(
            RankedArticle.publish_date.desc(),
            RankedArticle.credibility_score.desc(),
        )
        .limit(limit)
        .all()
    )

    return [map_article(article, locale) for article in articles]

@router.get("/articles", response_model=PaginatedArticlesOut)
def get_articles(
    category: Optional[str] = None,
    priority: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
):
    ranked_sq = top_article_per_valid_cluster_subquery(db)
    RankedArticle = aliased(Article, ranked_sq)

    base_query = (
        db.query(RankedArticle)
        # .filter(ranked_sq.c.rn == 1)
        # .filter(RankedArticle.uhalisi_id.isnot(None))  # Check for non-NULL
        # .filter(RankedArticle.uhalisi_id != '')
    )

    # Optional filters
    if category:
        base_query = base_query.filter(
            func.lower(RankedArticle.category) == category.lower()
        )

    if priority:
        base_query = base_query.filter(
            func.lower(RankedArticle.priority) == priority.lower()
        )

    # Ordering
    base_query = base_query.order_by(
        RankedArticle.publish_date.desc(),
        RankedArticle.credibility_score.desc(),
    )

    # Total count (correct + fast)
    total = base_query.count()

    # Pagination (DB-level, not Python)
    articles = (
        base_query
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "items": [
            {
                "id": a.id,
                "slug": a.slug,
                "title": a.title,
                "excerpt": a.summary or (a.content[:200] if a.content else ""),
                "url": a.url,
                "summary": a.summary,
                "image": a.image_url,
                "date": a.publish_date.strftime("%d %b %Y %H:%M") if a.publish_date else None,
                "source": a.source,
                "country": a.country,
                "uhalisi_id": a.uhalisi_id or "",
                "related_posts": fetch_related_posts(a.id),
            }
            for a in articles
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size,
    }
    
@router.get("/articles/featured", response_model=ArticleOut | None)
def get_featured_article(
    category: Optional[str] = None,
    priority: Optional[str] = None,
    db: Session = Depends(get_db),
):
    ranked_sq = top_article_per_valid_cluster_subquery(db)
    RankedArticle = aliased(Article, ranked_sq)

    query = (
        db.query(RankedArticle)
        # .filter(ranked_sq.c.rn == 1)
        # .filter(RankedArticle.uhalisi_id.isnot(None))  # Check for non-NULL
        # .filter(RankedArticle.uhalisi_id != '')
    )

    if category:
        query = query.filter(
            func.lower(RankedArticle.category) == category.lower()
        )

    if priority:
        query = query.filter(
            func.lower(RankedArticle.priority) == priority.lower()
        )

    article = (
        query.order_by(
            RankedArticle.publish_date.desc(),
            RankedArticle.credibility_score.desc(),
        )
        .first()
    )

    if not article:
        return None
    related_posts = fetch_related_posts(article.id)
    return {
        "id": article.id,
        "slug": article.slug,
        "url": article.url,
        "title": article.title,
        "excerpt": article.content,
        "summary": article.summary,
        "image": article.image_url,
        "date": article.publish_date.strftime("%d %b %Y %H:%M"),
        "source": article.source,
        "country": article.country,
        "uhalisi_id": article.uhalisi_id or "",
        "related_posts" : related_posts,
    }

@router.get(
    "/articles/{slug}/cluster-related",
    response_model=list[dict],
)
def get_cluster_related_articles(
    slug: str,
    db: Session = Depends(get_db),
):
    # --- Ranked articles subquery ---
    ranked_sq = top_article_per_valid_cluster_subquery(db)
    RankedArticle = aliased(Article, ranked_sq)

    # --- 1️⃣ Base article (must be RankedArticle) ---
    base_article = (
        db.query(RankedArticle)
        # .filter(ranked_sq.c.rn == 1)
        .filter(RankedArticle.slug == slug)
        .first()
    )

    if not base_article:
        raise HTTPException(status_code=404, detail="Article not found")

    # Always include the base article
    results = [base_article]

    # If no cluster, nothing else to return
    if not base_article.topic_cluster_id:
        return [serialize_article(a) for a in results]

    # --- 2️⃣ Lowest credibility article from same cluster, different country ---
    secondary_article = (
        db.query(Article)
        .filter(Article.topic_cluster_id == base_article.topic_cluster_id)
        .filter(Article.country != base_article.country)
        .filter(Article.credibility_score.isnot(None))
        .order_by(
            asc(Article.credibility_score),
            desc(Article.publish_date),
        )
        .first()
    )

    if secondary_article:
        results.append(secondary_article)

    return [serialize_article_ja(a) for a in results]

@router.get("/article/latest")
def latest(db: Session = Depends(get_db)):
    result = db.execute(
        text("""
            SELECT *
            FROM articles
            WHERE credibility_score != 0
            ORDER BY publish_date DESC NULLS LAST
            LIMIT 10
        """)
    )
    return result.mappings().all()


@router.get("/article/by-category")
def articles_by_category(db: Session = Depends(get_db)):
    result = db.execute(
        text("""
            SELECT
                category,
                json_agg(a ORDER BY publish_date DESC) AS articles
            FROM articles a
            WHERE credibility_score != 0
            GROUP BY category
        """)
    )
    return result.mappings().all()

@router.get("/article/by-priority")
def articles_by_priority(db: Session = Depends(get_db)):
    result = db.execute(
        text("""
            SELECT
                priority,
                json_agg(a ORDER BY publish_date DESC) AS articles
            FROM articles a
            WHERE credibility_score != 0
            GROUP BY priority
        """)
    )
    return result.mappings().all()

@router.get("/article/latest/category/{category}")
def latest_by_category(category: str, db: Session = Depends(get_db)):
    result = db.execute(
        text("""
            SELECT *
            FROM articles
            WHERE category = :category
              AND credibility_score != 0
            ORDER BY publish_date DESC NULLS LAST
            LIMIT 10
        """),
        {"category": category}
    )
    return result.mappings().all()



@router.get("/article/{id}")
def article(id: int, db: Session = Depends(get_db)):
    result = db.execute(text("SELECT * FROM articles WHERE id = :id"), {"id" : id})
    return result.mappings().first()