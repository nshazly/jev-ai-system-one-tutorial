import json

import httpx
import pytest

from sysone import Decision, SystemOneError, choice, decide, noul, score

OK_BODY = {
    "model": "nimble",
    "answers": {
        "team": {
            "type": "choice",
            "choice": "billing",
            "probabilities": {"billing": 0.97, "bug": 0.03},
            "confidence": 0.8,
        }
    },
    "usage": {"input_tokens": 100, "output_tokens": 1},
}


def stub_client(handler) -> httpx.Client:
    return httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler))


def test_question_builders_match_wire_format():
    assert choice("Which team?", {"billing": "money", "bug": None}) == {
        "type": "choice",
        "instructions": "Which team?",
        "criteria": {"billing": "money", "bug": None},
    }
    assert noul("Retry?", false="no", true="yes") == {
        "type": "noul",
        "instructions": "Retry?",
        "criteria": {"false": "no", "true": "yes"},
    }
    assert score("How bad?", ["low", "high"]) == {
        "type": "score",
        "instructions": "How bad?",
        "criteria": ["low", "high"],
    }


def test_decide_posts_request_and_parses_answers():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=OK_BODY)

    q = {"team": choice("Which team?", {"billing": None, "bug": None})}
    result = decide("charged twice", q, model="nimble", http=stub_client(handler))

    assert seen["path"] == "/v1/systemone"
    assert seen["body"] == {"model": "nimble", "state": "charged twice", "questions": q}
    assert isinstance(result, Decision)
    assert result.answers["team"]["choice"] == "billing"
    assert result.usage == {"input_tokens": 100, "output_tokens": 1}
    assert result.latency_ms >= 0


def test_decide_raises_with_server_error_message():
    def handler(request):
        return httpx.Response(404, json={"error": 'model "tev1" not found, try pulling it first'})

    with pytest.raises(SystemOneError, match=r'HTTP 404: model "tev1" not found'):
        decide("x", {}, model="tev1", http=stub_client(handler))


def test_decide_wraps_connection_errors():
    def handler(request):
        raise httpx.ConnectError("connection refused")

    with pytest.raises(SystemOneError, match="cannot reach http://test"):
        decide("x", {}, http=stub_client(handler))


def capture_own_client(monkeypatch, seen: dict) -> None:
    """Let decide() build its own client (where token and env apply), routed to a stub."""
    real_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        seen["model"] = json.loads(request.content)["model"]
        return httpx.Response(200, json=OK_BODY)

    def client_with_stub_transport(**kwargs) -> httpx.Client:
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "Client", client_with_stub_transport)


def set_defapi_env(monkeypatch) -> None:
    monkeypatch.setenv("API_TOKEN", "env-token")
    monkeypatch.setenv("DEFAULT_MODEL", "typesafe/jev-1.13")
    monkeypatch.setenv("DEFAULT_BASE_URL", "https://api.example.test")
    monkeypatch.setenv("DEFAULT_ENDPOINT", "/api/v1/decisions")


def test_decide_uses_built_in_defaults_and_no_auth_without_env(monkeypatch):
    seen = {}
    capture_own_client(monkeypatch, seen)

    decide("x", {})

    assert seen == {"url": "http://localhost:11434/v1/systemone", "auth": None, "model": "nimble"}


def test_decide_reads_settings_and_token_from_env(monkeypatch):
    set_defapi_env(monkeypatch)
    seen = {}
    capture_own_client(monkeypatch, seen)

    decide("x", {})

    assert seen == {
        "url": "https://api.example.test/api/v1/decisions",
        "auth": "Bearer env-token",
        "model": "typesafe/jev-1.13",
    }


def test_explicit_arguments_override_env(monkeypatch):
    set_defapi_env(monkeypatch)
    seen = {}
    capture_own_client(monkeypatch, seen)

    decide(
        "x",
        {},
        model="nimble",
        base_url="http://other.test",
        endpoint="/v1/systemone",
        token="explicit-token",
    )

    assert seen == {
        "url": "http://other.test/v1/systemone",
        "auth": "Bearer explicit-token",
        "model": "nimble",
    }


def test_env_reads_happen_per_call_not_at_import(monkeypatch):
    seen = {}
    capture_own_client(monkeypatch, seen)
    monkeypatch.setenv("API_TOKEN", "set-after-import")

    decide("x", {})

    assert seen["auth"] == "Bearer set-after-import"


def test_caller_supplied_client_keeps_its_own_headers(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "env-token")
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json=OK_BODY)

    decide("x", {}, http=stub_client(handler), token="explicit-token")

    assert seen["auth"] is None
