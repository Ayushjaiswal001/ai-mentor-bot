import structlog
from huggingface_hub import AsyncInferenceClient
from tenacity import retry, stop_after_attempt, wait_exponential

from pathwayai_backend.config import Settings

logger = structlog.get_logger(__name__)

# all-MiniLM-L6-v2 truncates around 256 word pieces anyway; cap the input so
# long logs don't waste request size.
MAX_EMBED_CHARS = 2000


class EmbeddingGateway:
    """Sentence embeddings via the Hugging Face Inference API.

    Embeddings are best-effort: any failure returns None so writes and
    searches degrade to keyword behaviour instead of breaking.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return self.settings.huggingface_api_token is not None

    async def embed(self, text: str) -> list[float] | None:
        text = text.strip()
        if not self.enabled or not text:
            return None
        try:
            vector = await self._feature_extraction(text[:MAX_EMBED_CHARS])
        except Exception:
            logger.warning("embedding_failed", exc_info=True)
            return None
        if len(vector) != self.settings.embedding_dimensions:
            logger.warning(
                "embedding_dimension_mismatch",
                expected=self.settings.embedding_dimensions,
                got=len(vector),
            )
            return None
        return vector

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=4))
    async def _feature_extraction(self, text: str) -> list[float]:
        assert self.settings.huggingface_api_token is not None
        client = AsyncInferenceClient(
            model=self.settings.embedding_model,
            token=self.settings.huggingface_api_token.get_secret_value(),
            timeout=self.settings.model_timeout_seconds,
        )
        result = await client.feature_extraction(text)
        # The API returns a vector for a single input, but some providers wrap
        # it in a batch dimension; unwrap until we hit the float level.
        values = result.tolist() if hasattr(result, "tolist") else list(result)
        while values and isinstance(values[0], (list, tuple)):
            values = values[0]
        return [float(value) for value in values]
