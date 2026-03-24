from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import astrbot.core.provider.sources.openai_embedding_source as embedding_source


class _FakeAsyncOpenAI:
    response = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.embeddings = SimpleNamespace(create=AsyncMock(return_value=self.response))

    async def close(self):
        return None


def _make_provider(monkeypatch, **overrides):
    monkeypatch.setattr(embedding_source, "AsyncOpenAI", _FakeAsyncOpenAI)

    provider_config = {
        "id": "openai-embedding-test",
        "embedding_api_key": "test-key",
        "embedding_api_base": "https://example.com",
        "embedding_model": "text-embedding-3-small",
        "timeout": 20,
    }
    provider_config.update(overrides)
    return embedding_source.OpenAIEmbeddingProvider(
        provider_config=provider_config,
        provider_settings={},
    )


def test_openai_embedding_provider_normalizes_root_api_base(monkeypatch):
    _FakeAsyncOpenAI.response = SimpleNamespace(data=[SimpleNamespace(embedding=[0.1])])

    provider = _make_provider(
        monkeypatch,
        embedding_api_base="https://example.com/",
    )

    assert provider.client.kwargs["base_url"] == "https://example.com/v1"


def test_openai_embedding_provider_preserves_custom_api_path(monkeypatch):
    _FakeAsyncOpenAI.response = SimpleNamespace(data=[SimpleNamespace(embedding=[0.1])])

    provider = _make_provider(
        monkeypatch,
        embedding_api_base="https://example.com/v1beta/openai/",
    )

    assert provider.client.kwargs["base_url"] == "https://example.com/v1beta/openai"


@pytest.mark.asyncio
async def test_openai_embedding_provider_raises_clear_error_for_text_response(
    monkeypatch,
):
    _FakeAsyncOpenAI.response = "<!doctype html><html><body>Not JSON</body></html>"

    provider = _make_provider(monkeypatch)

    with pytest.raises(RuntimeError, match="plain text/HTML"):
        await provider.get_embedding("hello")
