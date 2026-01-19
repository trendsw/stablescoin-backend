import faiss
import numpy as np
from db.models import TruthCluster

SIM_THRESHOLD = 0.7
EMBED_DIM = 384


def normalize_embedding(embedding) -> np.ndarray:
    """
    Ensures FAISS-compatible embedding
    """
    if isinstance(embedding, list):
        embedding = np.array(embedding, dtype="float32")
    elif isinstance(embedding, np.ndarray):
        embedding = embedding.astype("float32")

    if embedding.ndim == 1:
        embedding = embedding.reshape(1, -1)

    faiss.normalize_L2(embedding)
    return embedding

class TopicClusterIndex:
    def __init__(self):
        self.index = faiss.IndexFlatIP(EMBED_DIM)
        self.cluster_ids: list[int] = []

    def add_cluster(self, embedding, cluster_id: int):
        emb = normalize_embedding(embedding)
        self.index.add(emb)
        self.cluster_ids.append(cluster_id)

    def match(self, embedding):
        if self.index.ntotal == 0:
            return None, 0.0

        emb = normalize_embedding(embedding)
        scores, ids = self.index.search(emb, 1)
        return self.cluster_ids[ids[0][0]], float(scores[0][0])
    
def assign_topic_cluster(article, embedding, index: TopicClusterIndex, db):
    cluster_id, score = index.match(embedding)

    if cluster_id and score >= SIM_THRESHOLD:
        article.topic_cluster_id = cluster_id
        db.commit()
        return cluster_id

    cluster = TruthCluster(topic_summary=article.title)
    db.add(cluster)
    db.flush()  # ensures cluster.id exists

    index.add_cluster(embedding, cluster.id)

    article.topic_cluster_id = cluster.id
    db.commit()

    return cluster.id