"""HuggingFace sentence-transformer embedding provider."""

import asyncio
import threading
from typing import Dict, List, Tuple

import numpy as np


_HF_EMBEDDERS: Dict[Tuple[str, str, int, bool], object] = {}
_HF_EMBEDDERS_LOCK = threading.Lock()


def _get_hf_embedder(
    model_name: str,
    device: str,
    max_tokens: int,
    trust_remote_code: bool,
):
    key = (model_name, device, max_tokens, trust_remote_code)
    with _HF_EMBEDDERS_LOCK:
        if key not in _HF_EMBEDDERS:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise ImportError(
                    "HuggingFace embeddings require sentence-transformers. "
                    "Install with: pip install sentence-transformers transformers "
                    "huggingface_hub accelerate"
                ) from exc

            model = SentenceTransformer(
                model_name,
                device=device,
                trust_remote_code=trust_remote_code,
            )
            model.max_seq_length = max_tokens
            _HF_EMBEDDERS[key] = model
        return _HF_EMBEDDERS[key]


async def huggingface_embedding(
    texts: List[str],
    model: str = "nomic-ai/nomic-embed-text-v1.5",
    device: str = "cpu",
    batch_size: int = 16,
    max_tokens: int = 7500,
    prefix: str = "search_document: ",
    normalize_embeddings: bool = True,
    trust_remote_code: bool = True,
) -> np.ndarray:
    """Generate embeddings with a local HuggingFace sentence-transformer model."""

    def _encode() -> np.ndarray:
        embedder = _get_hf_embedder(model, device, max_tokens, trust_remote_code)
        prepared_texts = [
            text if not prefix or text.startswith(prefix) else f"{prefix}{text}"
            for text in texts
        ]
        vectors = embedder.encode(
            prepared_texts,
            batch_size=batch_size,
            normalize_embeddings=normalize_embeddings,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)

    return await asyncio.to_thread(_encode)
