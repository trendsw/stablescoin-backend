from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from db.session import get_db

router = APIRouter()


@router.get("/latest")
def latest(db: Session = Depends(get_db)):
    result = db.execute(
        text("SELECT * FROM truth_clusters ORDER BY id DESC LIMIT 10")
    )
    return result.mappings().all()


@router.get("/{cluster_id}")
def truth(cluster_id: int, db: Session = Depends(get_db)):
    result = db.execute(
        text("SELECT * FROM truth_clusters WHERE id = :id"),
        {"id": cluster_id}
    )
    return result.mappings().first()