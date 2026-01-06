from db.session import SessionLocal
from db.models import TruthCluster

def get_all_cluster_ids() -> list[int]:
    db = SessionLocal()
    try:
        return [c.id for c in db.query(TruthCluster.id).all()]
    finally:
        db.close()