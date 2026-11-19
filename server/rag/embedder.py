from functools import lru_cache

from fastembed import TextEmbedding

import config


@lru_cache(maxsize=1)
def _model() -> TextEmbedding:
    # Pin the cache inside the project: the default lives under %TEMP%, which
    # gets wiped and forces a ~90 MB model re-download on the next run.
    config.EMBED_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return TextEmbedding(
        model_name=config.EMBED_MODEL,
        cache_dir=str(config.EMBED_CACHE_DIR),
    )


def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return [list(map(float, vector)) for vector in _model().embed(texts)]
