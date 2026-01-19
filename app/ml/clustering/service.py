import numpy as np
from ml.clustering.index import ClusterIndex
from ml.services.topic_clustering import EMBED_DIM
# Global singleton index (production pattern)
INDEX = ClusterIndex(dim=EMBED_DIM)  # OpenAI embedding size

def assign_cluster(embedding: np.ndarray, threshold=0.8):
    vec = np.asarray(embedding, dtype="float32")

    # Ensure shape is (1, dim)
    if vec.ndim == 1:
        vec = vec.reshape(1, -1)

    assert vec.shape[1] == INDEX.dim, (
        f"Embedding dim {vec.shape[1]} != index dim {INDEX.dim}"
    )

    score, idx = INDEX.search(vec)

    if score is not None and score >= threshold:
        return INDEX.get_cluster_id(idx)

    return INDEX.add(vec)
