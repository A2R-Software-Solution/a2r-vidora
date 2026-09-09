import asyncio
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING

from app.core.logging import logger

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / MODEL_NAME
_model_lock = Lock()


@lru_cache
def _get_model() -> "SentenceTransformer":
    from sentence_transformers import SentenceTransformer

    logger.info(f"Loading embedding model: {MODEL_NAME}")
    if not (MODEL_PATH / "model.safetensors").is_file():
        raise RuntimeError("Bundled model missing. Run scripts/prepare_model.py before deployment.")
    model = SentenceTransformer(str(MODEL_PATH), device="cpu", local_files_only=True)
    logger.info("Embedding model loaded.")
    return model


def _encode(text: str) -> list[float]:
    with _model_lock:
        model = _get_model()
        vector = model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
    return vector.tolist()


def _encode_batch(texts: list[str]) -> list[list[float]]:
    with _model_lock:
        model = _get_model()
        return model.encode(texts, batch_size=32, convert_to_numpy=True,
                            normalize_embeddings=True).tolist()


async def embed_texts(texts: list[str]) -> list[list[float]]:
    return await asyncio.to_thread(_encode_batch, texts)


async def embed_text(text: str) -> list[float]:
    if not text or not text.strip():
        raise ValueError("Cannot embed empty text.")

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _encode, text)
