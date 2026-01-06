from datetime import datetime
from sqlalchemy.exc import IntegrityError
from db.session import SessionLocal
from db.models import Article

def save_articles(articles: list[dict]) -> list[int]:
    db = SessionLocal()
    saved_ids: list[int] = []

    try:
        for a in articles:
            article = Article(
                title=a["title"],
                content=a["content"],
                url=a["url"],
                publish_date=datetime.fromisoformat(a["publish_date"])
                if a.get("publish_date") else None,
                source=a["name"],
                country=a["country"],
                credibility_score=a["credibility_score"],
            )

            db.add(article)
            try:
                db.commit()
                db.refresh(article)
                saved_ids.append(article.id)
            except IntegrityError:
                db.rollback()  # already exists, skip

    finally:
        db.close()

    return saved_ids