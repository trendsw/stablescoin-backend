from openai import OpenAI
from core.config import OPENAI_API_KEY
from sentence_transformers import SentenceTransformer
from typing import Optional
import numpy as np
from ml.services.topic_clustering import EMBED_DIM
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

_model: Optional[SentenceTransformer] = None

def load_embedding_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed(text: str) -> np.ndarray:
    if _model is None:
        raise RuntimeError("Embedding model not loaded")

    vec = _model.encode(
        text,
        normalize_embeddings=True,
        show_progress_bar=False
    )

    assert vec.ndim == 1
    assert vec.dtype in (np.float32, np.float64)

    return vec.astype("float32")


def embed_batch(texts: list[str]) -> np.ndarray:
    if _model is None:
        raise RuntimeError("Embedding model not loaded")
    if not texts:
        return np.empty((0, EMBED_DIM), dtype="float32")
    return _model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False
    ).astype("float32")
    
#client = OpenAI(api_key=OPENAI_API_KEY)

# def embed(text: str) -> list[float]:
#     response = client.embeddings.create(
#         model="text-embedding-3-small",
#         input=text
#     )
#     return response.data[0].embedding
