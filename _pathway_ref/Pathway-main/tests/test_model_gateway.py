import pytest

from pathwayai_backend.config import Settings
from pathwayai_backend.llm.gateway import ModelGateway, ModelUnavailableError


@pytest.mark.asyncio
async def test_model_gateway_uses_deterministic_fallback_without_credentials() -> None:
    gateway = ModelGateway(Settings(GROQ_API_KEY=None, HUGGINGFACE_API_TOKEN=None))

    result = await gateway.generate(
        system_prompt="system",
        user_prompt="user",
        fallback="safe fallback",
    )

    assert result.content == "safe fallback"
    assert result.provider == "deterministic-fallback"


@pytest.mark.asyncio
async def test_model_gateway_fails_cleanly_without_fallback() -> None:
    gateway = ModelGateway(Settings(GROQ_API_KEY=None, HUGGINGFACE_API_TOKEN=None))

    with pytest.raises(ModelUnavailableError):
        await gateway.generate(system_prompt="system", user_prompt="user")


@pytest.mark.asyncio
async def test_embedding_gateway_disabled_without_token() -> None:
    from pathwayai_backend.llm.embeddings import EmbeddingGateway

    gateway = EmbeddingGateway(Settings(HUGGINGFACE_API_TOKEN=None))

    assert gateway.enabled is False
    assert await gateway.embed("anything") is None


@pytest.mark.asyncio
async def test_embedding_gateway_unwraps_batch_dimension(monkeypatch) -> None:
    import pathwayai_backend.llm.embeddings as embeddings_module
    from pathwayai_backend.llm.embeddings import EmbeddingGateway

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def feature_extraction(self, text):
            return [[0.5] * 384]  # batch-wrapped vector

    monkeypatch.setattr(embeddings_module, "AsyncInferenceClient", FakeClient)
    gateway = EmbeddingGateway(Settings(HUGGINGFACE_API_TOKEN="token"))

    vector = await gateway.embed("Implemented webhook dedup")

    assert vector is not None
    assert len(vector) == 384
    assert vector[0] == 0.5


@pytest.mark.asyncio
async def test_embedding_gateway_rejects_wrong_dimensions(monkeypatch) -> None:
    import pathwayai_backend.llm.embeddings as embeddings_module
    from pathwayai_backend.llm.embeddings import EmbeddingGateway

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def feature_extraction(self, text):
            return [0.5] * 768  # wrong model dimension

    monkeypatch.setattr(embeddings_module, "AsyncInferenceClient", FakeClient)
    gateway = EmbeddingGateway(Settings(HUGGINGFACE_API_TOKEN="token"))

    assert await gateway.embed("text") is None
