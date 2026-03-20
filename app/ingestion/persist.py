from datetime import datetime
from sqlalchemy.exc import IntegrityError
from db.session import SessionLocal
from db.models import Article
from sqlalchemy import select
from api.routes.articles import generate_slug
from db.firebase import db
from firebase_admin import firestore
from ml.claim_extraction import analyze_article1

def save_articles(articles: list[dict]) -> list[int]:
    db = SessionLocal()
    saved_ids: list[int] = []

    try:
        for a in articles:
            if a["image_url"]:
                article = Article(
                    title=a["title"],
                    content=a["content"],
                    url=a["url"],
                    publish_date=datetime.fromisoformat(a["publish_date"])
                    if a.get("publish_date") else None,
                    source=a["name"],
                    country=a["country"],
                    credibility_score=a["credibility_score"],
                    image_url = a["image_url"],
                    slug = generate_slug(a["url"], a["title"])
                )

                db.add(article)
            else:
                continue
            try:
                db.commit()
                db.refresh(article)
                saved_ids.append(article.id)
            except IntegrityError:
                db.rollback()
                # already exists, skip
                                # 🔑 fetch existing article
                # existing = db.execute(
                #     select(Article).where(Article.url == a["url"])
                # ).scalar_one_or_none()

                # if existing:
                #     saved_ids.append(existing.id)


    finally:
        db.close()

    return saved_ids



def save_region_articles(articles: list[dict]) -> list[int]:
    saved_ids: list[int] = []
    collection_ref = db.collection("stablescoin_regional")
    
    
    for a in articles:
        if not a.get("image_url"):
            continue

        slug = generate_slug(a["url"], a["title"])
        if slug.lower().endswith(".html"):
            slug = slug[:-5]
        doc_ref = collection_ref.document(slug)
        doc = doc_ref.get()

        # 🚀 Skip if already exists
        if doc.exists:
            continue
        analyze = analyze_article1(a["title"], a["content"])
        publish_date = (
            datetime.fromisoformat(a["publish_date"])
            if a.get("publish_date")
            else None
        )
        article_data = {
            # "title": a["title"],
            # "content": a["content"],
            "url": a["url"],
            "publish_date": publish_date,
            "source": a["name"],
            "region": a["country"].lower(),
            "image_url": a["image_url"],
            "slug": slug,
            "title": analyze["new_title"],
            "content": analyze["new_content"],
            "created_at": firestore.SERVER_TIMESTAMP,
        }

        # slug as document ID → prevents duplicates
        doc_ref = collection_ref.document(slug)
        doc_ref.set(article_data, merge=True)

        saved_ids.append(slug)

    return saved_ids