import faiss
import numpy as np
import uuid

class ClusterIndex:
    def __init__(self, dim: int):
        self.dim = dim
        self.index = faiss.IndexFlatIP(dim)
        self.cluster_ids = []

    def search(self, vec):
        if self.index.ntotal == 0:
            return None, None

        scores, ids = self.index.search(vec, 1)
        return scores[0][0], ids[0][0]

    def add(self, vec):
        cluster_id = str(uuid.uuid4())
        self.index.add(vec)
        self.cluster_ids.append(cluster_id)
        return cluster_id

    def get_cluster_id(self, idx):
        return self.cluster_ids[idx]