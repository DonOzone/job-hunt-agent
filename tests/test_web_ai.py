import pytest

pytest.importorskip("cryptography")
pytest.importorskip("fastapi")

from jobhunt.web import ai
from jobhunt.web.api import preview_digest


def test_consent_digest_changes_when_approved_connection_changes():
    settings = {"provider": "openai", "model": "test-model", "key": "encrypted-test-value"}
    digest = preview_digest("Displayed prompt", settings)
    for field in ("provider", "model", "key"):
        assert preview_digest("Displayed prompt", settings | {field: "changed"}) != digest
    assert preview_digest("Different displayed prompt", settings) != digest


def test_provider_redirects_are_rejected_without_forwarding_credentials(monkeypatch):
    calls = []

    class Redirect:
        status_code = 302

    def redirect(*args, **kwargs):
        calls.append((args, kwargs))
        return Redirect()

    monkeypatch.setattr(ai.requests, "post", redirect)
    with pytest.raises(RuntimeError, match="HTTP 302"):
        ai.generate("openai", "test-model", "fake-test-key", "Synthetic prompt")
    assert len(calls) == 1
    assert calls[0][1]["allow_redirects"] is False
    assert calls[0][1]["headers"]["Authorization"] == "Bearer fake-test-key"
