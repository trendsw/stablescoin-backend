from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from db.session import get_db

router = APIRouter()

@router.get("/opinions/{cluster_id}")
def opinions(cluster_id: int, db: Session = Depends(get_db)):
    result = db.execute(
        text("""
            SELECT c.sentiment, COUNT(*) AS count
            FROM claims c
            JOIN articles a ON c.article_id = a.id
            WHERE a.topic_cluster_id = :cluster_id
            GROUP BY c.sentiment
        """),
        {"cluster_id": cluster_id}
    )
    return result.mappings().all()