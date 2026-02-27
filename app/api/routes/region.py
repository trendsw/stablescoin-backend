from fastapi import APIRouter, Query
from typing import List
from db.firebase import db
from firebase_admin import firestore

router = APIRouter()

@router.get("/regional-articles")
def get_regional_articles(region: str = Query(...)):
    collection_ref = db.collection("stablescoin_regional")

    region = region.lower()

    docs = (
        collection_ref
        .where("region", "==", region)
        .order_by("publish_date", direction=firestore.Query.DESCENDING)
        .stream()
    )

    articles = []

    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        articles.append(data)

    return {"articles": articles}