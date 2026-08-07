"""
Wraps fastembed for turning text into dense vectors. fastembed runs on ONNX
Runtime instead of torch, which keeps the eventual Docker image much
smaller - the tradeoff is a smaller pool of supported models, but the
default model here is a solid, well-benchmarked choice for retrieval.

The model is loaded once and cached at module level since construction
downloads/loads ONNX weights and is too slow to repeat per call.
"""

from fastembed import TextEmbedding

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"

_model: TextEmbedding | None = None


def _get_model() -> TextEmbedding:
    global _model
    if _model is None:
        _model = TextEmbedding(model_name=EMBEDDING_MODEL)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts (e.g. chunks) for indexing."""
    return [vec.tolist() for vec in _get_model().embed(texts)]


def embed_query(query: str) -> list[float]:
    """Embed a single query string for search."""
    return embed_texts([query])[0]
