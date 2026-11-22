import numpy as np
import pytest

from app.rag.embeddings import (
    EmbeddingDimensionError,
    EmbeddingError,
    EmbeddingService,
    get_embedding_service,
    reset_embedding_service,
    set_embedding_service,
)
from tests.rag_helpers import FakeEmbeddingService, make_settings


class StubModel:
    def __init__(self, dimension):
        self.dimension = dimension

    def encode(self, texts, **kwargs):
        return np.ones((len(texts), self.dimension), dtype=np.float32)


def test_empty_input_returns_empty_matrix_without_loading_model():
    service = EmbeddingService("all-MiniLM-L6-v2", 384)

    matrix = service.embed_texts([])

    assert matrix.shape == (0, 384)
    assert service._model is None


def test_blank_text_is_rejected():
    service = EmbeddingService("all-MiniLM-L6-v2", 384)

    with pytest.raises(EmbeddingError):
        service.embed_texts(["   "])


def test_dimension_mismatch_is_rejected():
    service = EmbeddingService("stub", 8)
    service._model = StubModel(3)

    with pytest.raises(EmbeddingDimensionError):
        service.embed_texts(["python developer"])


def test_model_failure_is_wrapped():
    class BrokenModel:
        def encode(self, texts, **kwargs):
            raise RuntimeError("boom")

    service = EmbeddingService("broken", 8)
    service._model = BrokenModel()

    with pytest.raises(EmbeddingError):
        service.embed_texts(["python developer"])


def test_embedding_service_singleton_is_reused(rag_dir):
    reset_embedding_service()
    settings = make_settings(rag_dir)

    first = get_embedding_service(settings)
    second = get_embedding_service(settings)

    assert first is second
    assert first.dimension == 8

    set_embedding_service(FakeEmbeddingService(8))
    assert get_embedding_service(settings).model_name == FakeEmbeddingService.model_name

    reset_embedding_service()


def test_real_model_returns_configured_dimension():
    service = EmbeddingService("all-MiniLM-L6-v2", 384)

    try:
        matrix = service.embed_texts(["python developer", "recruitment agent"])
    except EmbeddingError:
        pytest.skip("The local embedding model is not available.")

    assert matrix.shape == (2, 384)
    assert np.allclose(np.linalg.norm(matrix, axis=1), 1.0, atol=1e-4)
