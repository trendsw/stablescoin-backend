from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text, func, and_, desc
from db.models import Article
from db.session import get_db
from db.schemas import ArticleOut, HomeArticlesResponse, PaginatedArticlesOut
from urllib.parse import urlparse
from typing import List, Optional


router = APIRouter()

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

    return ArticleOut(
        id=article.id,
        title=title,
        excerpt=content,
        url= article.url,
        image=article.image_url or "",
        slug=article.slug,
        summary= article.summary,
        date=article.publish_date.strftime("%d %b %Y %H:%M"),
        source = article.source,
        country= article.country
    )

@router.get("/articles/home", response_model=HomeArticlesResponse)
def get_home_articles(
    locale: str = Query("en", regex="^(en|ja)$"),
    db: Session = Depends(get_db),
):
    # Step 1: newest article per slug
    subquery = (
        db.query(
            Article.slug,
            func.max(Article.publish_date).label("max_publish_date"),
        )
        .filter(Article.credibility_score >= 0.3)
        .group_by(Article.slug)
        .subquery()
    )

    # Step 2: join back & sort globally
    articles = (
        db.query(Article)
        .join(
            subquery,
            (Article.slug == subquery.c.slug)
            & (Article.publish_date == subquery.c.max_publish_date),
        )
        .order_by(
            Article.publish_date.desc(),
            Article.credibility_score.desc(),
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

@router.get("/articles/counts")
def get_article_counts(db: Session = Depends(get_db)):
    # Priority counts: top, major, breaking
    priority_counts = (
        db.query(Article.priority, func.count(Article.id))
        .group_by(Article.priority)
        .all()
    )
    priority_dict = {p: c for p, c in priority_counts}

    # Category counts
    category_counts = (
        db.query(Article.category, func.count(Article.id))
        .filter(Article.credibility_score > 0)
        .group_by(Article.category)
        .all()
    )
    category_dict = {c: n for c, n in category_counts}

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
    Return latest articles with priority 'breaking'.
    """
    articles = (
        db.query(Article)
        .filter(Article.priority == "breaking")
        .order_by(Article.publish_date.desc())
        .limit(limit)
        .all()
    )

    # ALWAYS return a list
    return [map_article(article, locale) for article in articles]


@router.get("/articles", response_model=PaginatedArticlesOut)
def get_articles(
    category: Optional[str] = None,
    priority: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
):
    query = db.query(Article).filter(Article.credibility_score > 0)

    if category:
        query = query.filter(func.lower(Article.category) == category.lower())

    if priority:
        query = query.filter(func.lower(Article.priority) == priority.lower())

    # Order by publish_date descending first, then credibility_score
    query = query.order_by(Article.publish_date.desc(), Article.credibility_score.desc())

    # Fetch more than page_size to handle duplicates
    articles_all = query.all()

    # Deduplicate by slug
    seen = set()
    unique_articles = []
    for a in articles_all:
        if a.slug not in seen:
            seen.add(a.slug)
            unique_articles.append(a)
    if not unique_articles:
        raise HTTPException(status_code=404, detail="No articles found")

    # Pagination
    total = len(unique_articles)
    start = (page - 1) * page_size
    end = start + page_size
    page_articles = unique_articles[start:end]

    return {
        "items": [
            {
                "id": a.id,
                "slug": a.slug,
                "title": a.title,
                "excerpt": a.content,
                "url": a.url,
                "summary": a.summary,
                "image": a.image_url,
                "date": a.publish_date.strftime("%d %b %Y %H:%M") if a.publish_date else None,
                "source": a.source,
                "country": a.country
            }
            for a in page_articles
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size,
    }
    
@router.get('/articles/main', response_model=dict)
def get_main_article(
    db:Session = Depends(get_db),
):
    article = (
        db.query(Article)
        .filter(Article.credibility_score > 0)
        .order_by(
            desc(Article.credibility_score),
            desc(Article.publish_date),
        )
        .first()
    )
    
    if not article:
        return None
    
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
        "credibilityScore": article.credibility_score
    }  


@router.get("/articles/featured", response_model=ArticleOut | None)
def get_featured_article(
    category: Optional[str] = None,
    priority: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = (
        db.query(Article)
        .filter(Article.credibility_score > 0)
    )

    if category:
        query = query.filter(Article.category == category)

    if priority:
        query = query.filter(Article.priority == priority)

    article = (
        query.order_by(Article.publish_date.desc())
        .first()
    )

    if not article:
        return None

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
        "country": article.country
    }

@router.get(
    "/articles/{slug}/cluster-related",
    response_model=list[ArticleOut],
)
def get_cluster_related_articles(
    slug: str,
    db: Session = Depends(get_db),
):
    latest_subq = latest_per_slug_subquery(db)

    # 🔹 Base article (latest by slug)
    base = (
        db.query(Article)
        .join(
            latest_subq,
            and_(
                Article.slug == latest_subq.c.slug,
                Article.publish_date == latest_subq.c.max_date,
            ),
        )
        .filter(Article.slug == slug)
        .filter(Article.credibility_score.isnot(None))
        .first()
    )

    if not base:
        raise HTTPException(status_code=404, detail="Article not found")

    base_score = base.credibility_score
    excluded_slugs = {base.slug}
    results: list[Article] = []

    def fetch(query, needed):
        if needed <= 0:
            return []

        rows = (
            query
            .join(
                latest_subq,
                and_(
                    Article.slug == latest_subq.c.slug,
                    Article.publish_date == latest_subq.c.max_date,
                ),
            )
            .filter(~Article.slug.in_(excluded_slugs))
            .filter(Article.credibility_score.isnot(None))
            .limit(needed)
            .all()
        )

        for r in rows:
            excluded_slugs.add(r.slug)

        return rows
    
    if base.topic_cluster_id:
        results += fetch(
            db.query(Article)
            .filter(Article.topic_cluster_id == base.topic_cluster_id)
            .order_by(func.abs(Article.credibility_score - base_score)),
            2 - len(results),
        )

    # 2️⃣ SAME CATEGORY
    if len(results) < 2 and base.category:
        results += fetch(
            db.query(Article)
            .filter(Article.category == base.category)
            .order_by(func.abs(Article.credibility_score - base_score)),
            2 - len(results),
        )

    # 3️⃣ DIFFERENT COUNTRY
    if len(results) < 2 and base.country:
        results += fetch(
            db.query(Article)
            .filter(Article.country != base.country)
            .order_by(func.abs(Article.credibility_score - base_score)),
            2 - len(results),
        )

    # 4️⃣ GLOBAL FALLBACK
    if len(results) < 2:
        results += fetch(
            db.query(Article)
            .order_by(func.abs(Article.credibility_score - base_score)),
            2 - len(results),
        )

    return [serialize_article(a) for a in results]

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