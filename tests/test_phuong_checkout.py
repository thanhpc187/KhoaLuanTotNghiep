"""Checks for the imported checkout and optional provider request field."""
from pathlib import Path
import json

import httpx
import pytest

from agent_pentest.control.registry import verify_source
from agent_pentest.execution.live_backend import CompatibleChatModel, ModelConfig


def test_full_upstream_checkout_matches_reviewed_manifest():
    root = Path(__file__).resolve().parents[1]
    assert verify_source(root / "upstream/agents-from-scratch", root) == verify_source(
        root / "third_party/agents_from_scratch", root)


@pytest.mark.parametrize("thinking", [None, "disabled", "enabled"])
def test_optional_thinking_is_sent_only_when_configured(monkeypatch, thinking):
    seen = []

    def handle(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(CompatibleChatModel, "_client", lambda self: httpx.Client(
        transport=httpx.MockTransport(handle), follow_redirects=False))
    config = ModelConfig(base_url="https://provider.example.invalid/v1",
        allowed_base_urls=("https://provider.example.invalid/v1",), model="test-model",
        require_api_key=False, thinking=thinking)
    CompatibleChatModel(config).invoke([("user", "test")])
    if thinking is None:
        assert "thinking" not in seen[0]
    else:
        assert seen[0]["thinking"] == {"type": thinking}
