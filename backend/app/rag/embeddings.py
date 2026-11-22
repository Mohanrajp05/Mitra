import os
import threading
from typing import Sequence

import numpy as np

from app.rag.config import RagSettings, rag_settings


class EmbeddingError(RuntimeError):
    pass


class EmbeddingDimensionError(EmbeddingError):
    pass


def _prepare_offline_mode(allow_download: bool) -> None:
    if allow_download:
        return
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


class EmbeddingService:
    def __init__(
        self,
        model_name: str,
        dimension: int,
        batch_size: int = 32,
        allow_download: bool = False,
    ) -> None:
        self.model_name = model_name
        self.dimension = dimension
        self.batch_size = batch_size
        self.allow_download = allow_download
        self._model = None
        self._model_lock = threading.Lock()

    @property
    def model(self):
        if self._model is None:
            # Loading the sentence-transformer costs several seconds on CPU;
            # guard it so a startup warm-up and the first upload cannot load
            # the model twice (or interleave inside sentence-transformers).
            with self._model_lock:
                if self._model is None:
                    _prepare_offline_mode(self.allow_download)
                    try:
                        from sentence_transformers import SentenceTransformer
                    except ImportError as exc:
                        raise EmbeddingError(
                            "sentence-transformers is not installed."
                        ) from exc
                    try:
                        self._model = SentenceTransformer(self.model_name, device="cpu")
                    except Exception as exc:
                        raise EmbeddingError(
                            f"The embedding model '{self.model_name}' could not be loaded."
                        ) from exc
        return self._model

    def warm(self) -> None:
        """Load the model eagerly so the first document upload is not slowed."""
        self.model  # noqa: B018 - triggering the property is the point

    def embed_texts(
        self,
        texts: Sequence[str],
        batch_size: int | None = None,
    ) -> np.ndarray:
        cleaned = [str(item).strip() for item in texts]
        if not cleaned:
            return np.zeros((0, self.dimension), dtype=np.float32)

        if any(not item for item in cleaned):
            raise EmbeddingError("Embedding input must not be empty.")

        try:
            vectors = self.model.encode(
                cleaned,
                batch_size=batch_size or self.batch_size,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        except EmbeddingError:
            raise
        except Exception as exc:
            raise EmbeddingError("Embedding generation failed.") from exc

        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.ndim == 1:
            matrix = matrix.reshape(1, -1)

        if matrix.shape[0] != len(cleaned):
            raise EmbeddingError(
                "The embedding model returned an unexpected number of vectors."
            )

        if matrix.shape[1] != self.dimension:
            raise EmbeddingDimensionError(
                f"The embedding model returned {matrix.shape[1]} dimensions "
                f"but {self.dimension} are configured."
            )

        if not np.all(np.isfinite(matrix)):
            raise EmbeddingError("The embedding model returned invalid values.")

        return matrix

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_texts([text])[0]


_embedding_service: EmbeddingService | None = None


def get_embedding_service(settings: RagSettings | None = None) -> EmbeddingService:
    global _embedding_service

    if _embedding_service is None:
        active = settings or rag_settings
        _embedding_service = EmbeddingService(
            model_name=active.embedding_model,
            dimension=active.embedding_dimension,
            batch_size=active.embedding_batch_size,
            allow_download=active.allow_model_download,
        )

    return _embedding_service


def set_embedding_service(service: EmbeddingService | None) -> None:
    global _embedding_service
    _embedding_service = service


def reset_embedding_service() -> None:
    set_embedding_service(None)
