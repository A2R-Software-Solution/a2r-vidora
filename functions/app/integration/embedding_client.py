import asyncio
from functools import lru_cache
from typing import TYPE_CHECKING

from app.core.logging import logger

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


@lru_cache
def _get_model() -> "SentenceTransformer":
    from sentence_transformers import SentenceTransformer

    logger.info(f"Loading embedding model: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME, device="cpu")
    logger.info("Embedding model loaded.")
    return model


def _encode(text: str) -> list[float]:
    model = _get_model()
    vector = model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
    return vector.tolist()


async def embed_text(text: str) -> list[float]:
    if not text or not text.strip():
        raise ValueError("Cannot embed empty text.")

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _encode, text)