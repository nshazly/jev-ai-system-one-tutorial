# Tutorial: build a System One ticket router

This tutorial rebuilds this repository from an empty folder. You'll write a small Python client for System One decision models, then use it to route 20 labelled support tickets with one `choice` question. Along the way you'll see each ticket's full probability distribution, plus accuracy, latency and confidence-gated coverage.

The same code runs against local **Nimble** through Ollama or hosted **Jev** through DefAPI. You switch between them in a `.env` file, not in code.

**Time:** about 30 minutes for the code (Steps 1–4), plus a few minutes per run in Step 5. Steps 6 and 7 are optional.

**What you'll learn:**
- The request and response shape of a System One decision API
- Why option descriptions matter, and how much
- Why `confidence` is not the top probability, and what that means for thresholds
- How to keep a configurable client testable offline, with no secrets leaking into tests

Every code block below is the exact file contents used in this repo. The tests are written before the code they test (test-driven), so each step has a "run it and watch it fail" moment before the "make it pass" moment.

## Contents

- [Before you start](#before-you-start)
- [How the pieces fit](#how-the-pieces-fit)
- [Step 1: Scaffold the project](#step-1-scaffold-the-project)
- [Step 2: Write the System One client](#step-2-write-the-system-one-client)
- [Step 3: Add the tickets, routing and summary](#step-3-add-the-tickets-routing-and-summary)
- [Step 4: Add the CLI and a live test](#step-4-add-the-cli-and-a-live-test)
- [Step 5: The learning run](#step-5-the-learning-run)
- [Step 6 (optional): Save API examples](#step-6-optional-save-api-examples)
- [Step 7 (optional): Prepare the repo for publishing](#step-7-optional-prepare-the-repo-for-publishing)
- [What the tests protect you from](#what-the-tests-protect-you-from)
- [Where to go next](#where-to-go-next)

## Before you start

You need:

- **Python 3.12 or newer**
- **[uv](https://docs.astral.sh/uv/)** to manage the project and its dependencies
- **[Ollama](https://ollama.com) 0.35 or newer**, which added the `/v1/systemone` decision endpoint
- **About 9 GB of disk** for the `nimble` model
- **Optional:** a [DefAPI](https://defapi.org) account and API key, to run the same code against hosted Jev

Pull the model and make sure Ollama is running:

```bash
ollama pull nimble
ollama list            # nimble should be listed
```

### Try the API by hand first

Before writing any code, send one request with `curl` so you know what the client has to build and parse. This asks a `noul` (true/false) question and a `score` (rubric) question about the same text:

```bash
curl -s localhost:11434/v1/systemone -d '{
  "model": "nimble",
  "state": "I was charged twice",
  "questions": {
    "urgent": {"type": "noul", "instructions": "Is the customer blocked or losing money?",
               "criteria": {"false": "can wait", "true": "blocked or losing money"}},
    "mood":   {"type": "score", "instructions": "How upset is the customer?",
               "criteria": ["calm", "annoyed", "angry"]}
  }
}' | python3 -m json.tool
```

What to notice in the request:

- `state` is the thing being judged. It can be a string or a JSON object.
- `questions` maps a name you choose to a typed question. Every question needs **both** `instructions` (the question itself, a non-empty string) **and** `criteria`. Sending `criteria` alone returns HTTP 400.
- The three question types take different `criteria`:

  | Type | `criteria` |
  |---|---|
  | `choice` | An object mapping each option key to a description, or to `null`. 2–26 options. |
  | `noul` | `{"false": "...", "true": "..."}` |
  | `score` | An ordered list of 2–26 levels |

What to notice in the response (under `answers[<name>]`):

- `choice` returns `choice` (the label), `probabilities` (label → p) and `confidence`.
- `noul` returns `noul`, which is P(true). There is no `confidence`.
- `score` returns `score`, the **expected level index** (Σ i·pᵢ, 0-based, not scaled to 0–1), plus `legend`, `probabilities` and `confidence`.
- **`confidence` is `1 − normalized entropy`, not the top probability.** A choice with a top probability of 0.97 can report a confidence of 0.89. That's why the router below prints both.
- Errors come back as a non-200 status with `{"error": "..."}`. A model that isn't pulled returns 404, and a malformed question returns 400.

## How the pieces fit

You'll build two parts:

1. **A reusable client** in `src/sysone/client.py`. It posts to the decision endpoint and has small builders for the three question types. Later projects (CI failure triage and a calibration harness) reuse it unchanged.
2. **The ticket-router exercise** in `exercises/ticket_router/`. It holds the dataset, the routing and summary logic, and a CLI.

The finished layout:

```
pyproject.toml                          uv project, pytest and ruff config
.gitignore                              includes .env, so the API token is never committed
.env.example                            template for choosing a backend
.env                                    local only, never committed
src/sysone/__init__.py                  re-exports the client API
src/sysone/client.py                    decide(), choice()/noul()/score(), Decision, SystemOneError
exercises/__init__.py
exercises/ticket_router/tickets.jsonl   20 labelled tickets
exercises/ticket_router/router.py       load, route, summarize, plus the CLI
tests/conftest.py                       clears API_TOKEN / DEFAULT_* for every test
tests/test_client.py
tests/test_router.py
tests/test_live.py                      the one test that calls a real model
```

### Configuration

The client works with any server that speaks this request shape. Each setting resolves as **explicit argument > environment variable > built-in default**:

| Setting | Argument | Environment variable | Default |
|---|---|---|---|
| Model | `model=` / `--model` | `DEFAULT_MODEL` | `nimble` |
| Base URL | `base_url=` | `DEFAULT_BASE_URL` | `http://localhost:11434` |
| Endpoint | `endpoint=` | `DEFAULT_ENDPOINT` | `/v1/systemone` |
| Token | `token=` | `API_TOKEN` | none (no `Authorization` header) |

For hosted Jev through DefAPI, the values are base URL `https://api.defapi.org`, endpoint `/api/v1/decisions` and model `typesafe/jev-1.13`. The request body is the same.

Three design rules follow from this, and the tests enforce all of them:

- **Read environment variables inside `decide()`, never at import time.** The CLI imports `sysone` before it loads `.env`, so values read at import would miss `.env`.
- **Load `.env` only in the CLI's `if __name__ == "__main__":` block.** Never in `sysone`, and never under pytest, so your real token can't reach the tests.
- **Send `Authorization: Bearer <token>` only when a token is set.** If the caller passes its own `http=` client, use that client's headers as they are.

## Step 1: Scaffold the project

Create the folder and start a git repository:

```bash
mkdir jev-ai-system-one-tutorial && cd jev-ai-system-one-tutorial
git init
```

Create `pyproject.toml`:

```toml
[project]
name = "jev-ai-system-one"
version = "0.1.0"
description = "Learning a TypeSafe AI style API with open source decision models"
requires-python = ">=3.12"
dependencies = []

[build-system]
requires = ["hatchling>=1.27"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/sysone"]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
markers = ["live: needs a running Ollama with the nimble model pulled."]

[tool.ruff]
line-length = 100
```

`pythonpath = ["."]` lets the tests import `exercises.ticket_router.router` from the repo root. The `live` marker lets you run `pytest -m "not live"` to skip the one test that needs a real model.

Create `.gitignore`:

```gitignore
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
dist/
.DS_Store
.env
.envrc
```

Create `.env.example`. It's a committed template. Your real settings go in `.env`, which is ignored:

```bash
# API_TOKEN=""                              # unused for Ollama
DEFAULT_MODEL="nimble"                      # typesafe/jev-x.xx
DEFAULT_BASE_URL="http://localhost:11434"   # https://api.defapi.org
DEFAULT_ENDPOINT="/v1/systemone"            # /api/v1/decisions
```

Install the dependencies:

```bash
uv add httpx python-dotenv
uv add --dev pytest ruff
```

This creates `uv.lock` and `.venv/`, and adds `httpx` and `python-dotenv` to `dependencies` and `pytest` and `ruff` to a `dev` dependency group. Use the package name `python-dotenv`. The PyPI package called `dotenv` is a different package.

Commit:

```bash
git add pyproject.toml uv.lock .gitignore .env.example
git commit -m "chore: add uv project scaffold, gitignore and env example"
```

## Step 2: Write the System One client

The client exposes:

- `choice(instructions, options)`, `noul(instructions, *, false, true)` and `score(instructions, levels)`, which build question dicts in the wire format
- `decide(state, questions, *, model=None, base_url=None, endpoint=None, http=None, token=None, timeout=60.0) -> Decision`, which sends the request
- `Decision(answers, usage, latency_ms)`, a frozen dataclass
- `SystemOneError`, raised when the server is unreachable or returns an error

### Write the tests first

`tests/conftest.py` clears the four settings before every test. Without it, a token or `DEFAULT_*` value exported in your shell (for example by direnv) would change what the tests see:

```python
import pytest

CONFIG_VARS = ("API_TOKEN", "DEFAULT_MODEL", "DEFAULT_BASE_URL", "DEFAULT_ENDPOINT")


@pytest.fixture(autouse=True)
def isolated_config_env(monkeypatch):
    """Keep shell or direnv settings (e.g. a DefAPI token) out of every test."""
    for name in CONFIG_VARS:
        monkeypatch.delenv(name, raising=False)
```

`tests/test_client.py` uses `httpx.MockTransport`, so no server is needed. The first four tests pass a stub client through `http=`. The last five cover configuration, so they let `decide()` build its own client and only swap in a stub transport. Passing `http=` would skip the token and environment code they're meant to test.

```python
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
```

Run them and watch them fail:

```bash
uv run pytest tests/test_client.py -v
```

Expected: a collection error, `ModuleNotFoundError: No module named 'sysone'`.

### Write the client

`src/sysone/client.py`:

```python
"""Minimal client defaults to Ollama's System One decision endpoint (POST /v1/systemone)."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_ENDPOINT = "/v1/systemone"
DEFAULT_MODEL = "nimble"


class SystemOneError(RuntimeError):
    """The decision server was unreachable or rejected the request."""


def choice(instructions: str, options: dict[str, str | None]) -> dict[str, Any]:
    return {"type": "choice", "instructions": instructions, "criteria": dict(options)}


def noul(instructions: str, *, false: str, true: str) -> dict[str, Any]:
    return {
        "type": "noul",
        "instructions": instructions,
        "criteria": {"false": false, "true": true},
    }


def score(instructions: str, levels: list[str]) -> dict[str, Any]:
    return {"type": "score", "instructions": instructions, "criteria": list(levels)}


@dataclass(frozen=True)
class Decision:
    answers: dict[str, dict[str, Any]]
    usage: dict[str, int]
    latency_ms: float


def decide(
    state: str | dict[str, Any],
    questions: dict[str, dict[str, Any]],
    *,
    model: str | None = None,
    base_url: str | None = None,
    endpoint: str | None = None,
    http: httpx.Client | None = None,
    token: str | None = None,
    timeout: float = 60.0,
) -> Decision:
    model = model or os.getenv("DEFAULT_MODEL", DEFAULT_MODEL)
    base_url = base_url or os.getenv("DEFAULT_BASE_URL", DEFAULT_BASE_URL)
    token = token or os.getenv("API_TOKEN")
    endpoint = endpoint or os.getenv("DEFAULT_ENDPOINT", DEFAULT_ENDPOINT)
    body = {"model": model, "state": state, "questions": questions}
    owns_http = http is None
    if http is None:
        headers = {"Authorization": f"Bearer {token}"} if token else None
        http = httpx.Client(base_url=base_url, timeout=timeout, headers=headers)
    try:
        start = time.perf_counter()
        try:
            resp = http.post(endpoint, json=body)
        except httpx.TransportError as exc:
            raise SystemOneError(f"cannot reach {http.base_url}: {exc}") from exc
        latency_ms = (time.perf_counter() - start) * 1000
    finally:
        if owns_http:
            http.close()

    if resp.status_code != 200:
        try:
            message = resp.json().get("error", resp.text)
        except ValueError:
            message = resp.text
        raise SystemOneError(f"HTTP {resp.status_code}: {message}")

    data = resp.json()
    return Decision(answers=data["answers"], usage=data.get("usage", {}), latency_ms=latency_ms)
```

`src/sysone/__init__.py`:

```python
from sysone.client import (
    DEFAULT_BASE_URL,
    DEFAULT_ENDPOINT,
    DEFAULT_MODEL,
    Decision,
    SystemOneError,
    choice,
    decide,
    noul,
    score,
)

__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_ENDPOINT",
    "DEFAULT_MODEL",
    "Decision",
    "SystemOneError",
    "choice",
    "decide",
    "noul",
    "score",
]
```

A few things worth knowing about this code:

- **The environment lookups are inside `decide()` on purpose.** `test_env_reads_happen_per_call_not_at_import` fails if anyone moves them to module-level constants.
- **`token or os.getenv("API_TOKEN")`** means an explicit `token=` always beats the environment.
- **Connection failures become `SystemOneError`** with the base URL in the message, so the CLI can print one clear line instead of a traceback. `http.base_url` renders with a trailing slash (`http://test/`). The test's `match=` still passes because it only checks the prefix.
- **Every name in `__all__` must also be imported above it.** `__all__` only lists names; it doesn't create them. Ruff doesn't catch a missing import in `__init__.py`, so it would only show up as an `ImportError` at runtime. Ruff's RUF022 rule wants `__all__` sorted.

Run the tests and the linter:

```bash
uv run pytest tests/test_client.py -v && uv run ruff check .
```

Expected: 9 passed, ruff clean.

Commit:

```bash
git add src/sysone tests/conftest.py tests/test_client.py
git commit -m "feat: add System One client with configurable backend"
```

## Step 3: Add the tickets, routing and summary

This step adds the dataset and three functions: `load_tickets()`, `route()` (one ticket → one decision) and `summarize()` (accuracy, confidence-gated accuracy and latency). The CLI comes in Step 4.

### Create the dataset

Create an empty `exercises/__init__.py`. The `ticket_router` folder doesn't need one.

```bash
mkdir -p exercises/ticket_router && touch exercises/__init__.py
```

`exercises/ticket_router/tickets.jsonl` holds 20 tickets, 5 per class. Tickets t13 (SSO) and t16 (password reset email) are deliberately ambiguous, so you can see how the probabilities spread:

```jsonl
{"id": "t01", "text": "I was charged twice for my Pro subscription this month.", "label": "billing"}
{"id": "t02", "text": "Can I get an invoice with our company VAT number on it?", "label": "billing"}
{"id": "t03", "text": "Please cancel my plan and refund the unused months.", "label": "billing"}
{"id": "t04", "text": "Your pricing page says $12 but my card was billed $15.", "label": "billing"}
{"id": "t05", "text": "How do I switch from monthly to annual billing?", "label": "billing"}
{"id": "t06", "text": "The export to CSV button does nothing in Firefox.", "label": "bug"}
{"id": "t07", "text": "App crashes every time I open the settings screen on Android.", "label": "bug"}
{"id": "t08", "text": "Dashboard charts show yesterday's data even after refreshing.", "label": "bug"}
{"id": "t09", "text": "Getting a 500 error when uploading files larger than 10 MB.", "label": "bug"}
{"id": "t10", "text": "Dark mode makes the text in tables invisible.", "label": "bug"}
{"id": "t11", "text": "It would be great if we could schedule reports to be emailed weekly.", "label": "feature"}
{"id": "t12", "text": "Please add a Slack integration for notifications.", "label": "feature"}
{"id": "t13", "text": "Can you support SSO with Okta? We need it for our rollout.", "label": "feature"}
{"id": "t14", "text": "I'd love keyboard shortcuts for switching between projects.", "label": "feature"}
{"id": "t15", "text": "Any plans to offer an API for bulk importing contacts?", "label": "feature"}
{"id": "t16", "text": "I forgot my password and the reset email never arrives.", "label": "account"}
{"id": "t17", "text": "How do I change the email address on my account?", "label": "account"}
{"id": "t18", "text": "I lost my phone and can't get past two-factor authentication.", "label": "account"}
{"id": "t19", "text": "Please delete my account and all my data.", "label": "account"}
{"id": "t20", "text": "My teammate left the company; how do I transfer ownership of the workspace?", "label": "account"}
```

### Write the tests first

`tests/test_router.py`. `route()` takes a `decide_fn` argument, so the test can pass a fake and check exactly what would be sent:

```python
from collections import Counter

from exercises.ticket_router.router import (
    OPTIONS,
    Routed,
    Ticket,
    build_question,
    load_tickets,
    route,
    summarize,
)
from sysone import Decision


def make_routed(label: str, choice: str, confidence: float, latency_ms: float = 50.0) -> Routed:
    return Routed(
        ticket=Ticket(id="t", text="x", label=label),
        choice=choice,
        probabilities={choice: 0.9},
        confidence=confidence,
        latency_ms=latency_ms,
    )


def test_dataset_is_20_tickets_balanced_across_classes():
    tickets = load_tickets()
    assert len(tickets) == 20
    assert Counter(t.label for t in tickets) == {k: 5 for k in OPTIONS}
    assert len({t.id for t in tickets}) == 20


def test_every_ticket_label_is_a_known_option():
    assert {t.label for t in load_tickets()} <= set(OPTIONS)


def test_build_question_with_and_without_descriptions():
    q = build_question()
    assert q["type"] == "choice"
    assert q["criteria"] == OPTIONS
    assert build_question(describe=False)["criteria"] == dict.fromkeys(OPTIONS)


def test_route_sends_ticket_text_and_reads_choice_answer():
    calls = []

    def fake_decide(state, questions, *, model):
        calls.append((state, questions, model))
        return Decision(
            answers={
                "team": {
                    "type": "choice",
                    "choice": "bug",
                    "probabilities": {"billing": 0.1, "bug": 0.9},
                    "confidence": 0.5,
                }
            },
            usage={},
            latency_ms=42.0,
        )

    ticket = Ticket(id="t06", text="Export is broken", label="bug")
    q = build_question()
    result = route(ticket, q, model="nimble", decide_fn=fake_decide)

    assert calls == [("Export is broken", {"team": q}, "nimble")]
    assert result.choice == "bug"
    assert result.probabilities == {"billing": 0.1, "bug": 0.9}
    assert result.confidence == 0.5
    assert result.latency_ms == 42.0
    assert result.correct is True


def test_summarize_accuracy_coverage_and_latency():
    results = [
        make_routed("bug", "bug", 0.9, 40),
        make_routed("bug", "billing", 0.2, 60),
        make_routed("account", "account", 0.7, 50),
        make_routed("feature", "bug", 0.8, 200),
    ]
    s = summarize(results, threshold=0.5)
    assert s.n == 4
    assert s.accuracy == 0.5
    assert s.confident_n == 3
    assert s.confident_accuracy == 2 / 3
    assert s.p50_latency_ms == 55.0
    assert s.max_latency_ms == 200


def test_summarize_threshold_is_inclusive():
    s = summarize([make_routed("bug", "bug", 0.5)], threshold=0.5)
    assert s.confident_n == 1


def test_summarize_with_nothing_confident():
    s = summarize([make_routed("bug", "bug", 0.1)], threshold=0.5)
    assert s.confident_n == 0
    assert s.confident_accuracy is None
```

Run them:

```bash
uv run pytest tests/test_router.py -v
```

Expected: a collection error, `ModuleNotFoundError: No module named 'exercises.ticket_router.router'`.

### Write the router

`exercises/ticket_router/router.py`. Notice how specific the option descriptions are. In Step 5 you'll measure what happens without them.

```python
"""30-minute starter: route support tickets with a single System One `choice` question."""

from __future__ import annotations

import json
import statistics
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sysone import Decision, choice, decide

TICKETS_PATH = Path(__file__).with_name("tickets.jsonl")
QUESTION_NAME = "team"
INSTRUCTIONS = "Which support team should handle this customer ticket?"
OPTIONS = {
    "billing": "Payments, charges, refunds, invoices, pricing, or changing or cancelling a plan.",
    "bug": "Something that already exists in the product is broken, erroring, crashing or wrong.",
    "feature": "A request for new functionality or an integration that does not exist yet.",
    "account": "Login, passwords, two-factor, email address, ownership, or deleting the account.",
}


@dataclass(frozen=True)
class Ticket:
    id: str
    text: str
    label: str


@dataclass(frozen=True)
class Routed:
    ticket: Ticket
    choice: str
    probabilities: dict[str, float]
    confidence: float
    latency_ms: float

    @property
    def correct(self) -> bool:
        return self.choice == self.ticket.label


@dataclass(frozen=True)
class Summary:
    n: int
    accuracy: float
    threshold: float
    confident_n: int
    confident_accuracy: float | None
    p50_latency_ms: float
    max_latency_ms: float


def load_tickets(path: Path = TICKETS_PATH) -> list[Ticket]:
    lines = path.read_text().splitlines()
    return [Ticket(**json.loads(line)) for line in lines if line.strip()]


def build_question(describe: bool = True) -> dict[str, Any]:
    return choice(INSTRUCTIONS, OPTIONS if describe else dict.fromkeys(OPTIONS))


def route(
    ticket: Ticket,
    question: dict[str, Any],
    *,
    model: str | None = None,
    decide_fn: Callable[..., Decision] = decide,
) -> Routed:
    decision = decide_fn(ticket.text, {QUESTION_NAME: question}, model=model)
    answer = decision.answers[QUESTION_NAME]
    return Routed(
        ticket=ticket,
        choice=answer["choice"],
        probabilities=answer["probabilities"],
        confidence=answer["confidence"],
        latency_ms=decision.latency_ms,
    )


def summarize(results: list[Routed], threshold: float) -> Summary:
    confident = [r for r in results if r.confidence >= threshold]
    latencies = [r.latency_ms for r in results]
    return Summary(
        n=len(results),
        accuracy=sum(r.correct for r in results) / len(results),
        threshold=threshold,
        confident_n=len(confident),
        confident_accuracy=(
            sum(r.correct for r in confident) / len(confident) if confident else None
        ),
        p50_latency_ms=statistics.median(latencies),
        max_latency_ms=max(latencies),
    )
```

Two details the tests pin down: the threshold is inclusive (`>=`), and when nothing clears it, `confident_accuracy` is `None` instead of a division by zero.

Run everything:

```bash
uv run pytest -v && uv run ruff check .
```

Expected: 16 passed (9 client + 7 router), ruff clean. Don't commit yet; Step 4 finishes the exercise.

## Step 4: Add the CLI and a live test

This step adds `format_row()`, `format_summary()` and `main()`, plus one test that calls the real model.

### Write the tests first

At the top of `tests/test_router.py`, replace the imports with this block. It adds the new names and the modules the `.env` tests need, in the order ruff's isort rule (I001) expects. Imports must stay at the top of the file, or ruff raises E402.

```python
import runpy
import sys
from collections import Counter

import dotenv
import pytest

import exercises.ticket_router.router as router_module
import sysone
from exercises.ticket_router.router import (
    OPTIONS,
    Routed,
    Summary,
    Ticket,
    build_question,
    format_row,
    format_summary,
    load_tickets,
    main,
    route,
    summarize,
)
from sysone import Decision, SystemOneError
```

Then append these tests to the end of the file:

```python
def test_format_row_shows_all_probabilities_and_mark():
    r = Routed(
        ticket=Ticket(id="t01", text="x", label="billing"),
        choice="bug",
        probabilities={"billing": 0.3, "bug": 0.7},
        confidence=0.12,
        latency_ms=61.4,
    )
    row = format_row(r)
    assert row.startswith("t01")
    assert "billing=0.30" in row and "bug=0.70" in row
    assert "conf=0.12" in row
    assert "61ms" in row
    assert "✗" in row


def test_format_summary_handles_no_confident_results():
    s = Summary(
        n=20,
        accuracy=0.9,
        threshold=0.5,
        confident_n=0,
        confident_accuracy=None,
        p50_latency_ms=60,
        max_latency_ms=90,
    )
    text = format_summary(s)
    assert "accuracy 90% (18/20)" in text
    assert "n/a" in text


def test_main_reports_unreachable_server(capsys):
    def failing_decide(*args, **kwargs):
        raise SystemOneError("cannot reach http://localhost:11434/: refused")

    assert main([], decide_fn=failing_decide) == 1
    assert "cannot reach http://localhost:11434/" in capsys.readouterr().err


def fake_billing_decide(state, questions, *, model=None):
    answer = {
        "type": "choice",
        "choice": "billing",
        "probabilities": {"billing": 1.0},
        "confidence": 1.0,
    }
    return Decision(answers={"team": answer}, usage={}, latency_ms=1.0)


def test_main_does_not_load_dotenv(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("main() must not load .env; only the __main__ block may")

    monkeypatch.setattr(dotenv, "load_dotenv", fail_if_called)
    monkeypatch.setattr(router_module, "load_dotenv", fail_if_called, raising=False)

    assert main([], decide_fn=fake_billing_decide) == 0


@pytest.mark.filterwarnings("ignore:.*found in sys.modules:RuntimeWarning")
def test_cli_entry_point_loads_dotenv_once_before_routing(monkeypatch, capsys):
    events = []
    # Record the call instead of reading the real .env, so no token reaches the test process.
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: events.append("load_dotenv"))

    def recording_decide(*args, **kwargs):
        events.append("decide")
        return fake_billing_decide(*args, **kwargs)

    monkeypatch.setattr(sysone, "decide", recording_decide)
    monkeypatch.setattr(sys, "argv", ["router"])

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("exercises.ticket_router.router", run_name="__main__")

    assert exit_info.value.code == 0
    assert events[0] == "load_dotenv"
    assert events.count("load_dotenv") == 1
    assert events.count("decide") == 21  # warm-up + 20 tickets
    assert "accuracy" in capsys.readouterr().out
```

How the two `.env` tests work:

- **`test_main_does_not_load_dotenv`** replaces `load_dotenv` with a function that fails if called, both in `dotenv` and in the router module. That catches a `load_dotenv` call inside `main()` whether it's imported locally or at module level.
- **`test_cli_entry_point_loads_dotenv_once_before_routing`** runs `router.py` as `__main__` with `runpy`, the same way `python -m` does.
  - `load_dotenv` is replaced with a recorder, so the real `.env` and its token are never read.
  - `sysone.decide` is replaced with a fake, so no network call is made. `runpy` re-executes the module, so `from sysone import decide` picks up the fake.
  - The `filterwarnings` mark silences the `RuntimeWarning` that `runpy` raises when the module has already been imported.

`tests/test_live.py` is the only test that talks to a real model. It skips itself when Ollama isn't running or `nimble` isn't pulled. It always targets local Ollama: it checks `DEFAULT_BASE_URL` (localhost) and passes `model="nimble"`, and pytest never loads `.env`, so DefAPI settings there don't affect it.

```python
import httpx
import pytest

from exercises.ticket_router.router import Ticket, build_question, route
from sysone import DEFAULT_BASE_URL


def nimble_available() -> bool:
    try:
        tags = httpx.get(f"{DEFAULT_BASE_URL}/api/tags", timeout=2).json()
    except (httpx.HTTPError, ValueError):
        return False
    return any(m["name"].startswith("nimble") for m in tags.get("models", []))


pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not nimble_available(), reason="Ollama with nimble not available"),
]


def test_nimble_routes_obvious_billing_ticket():
    ticket = Ticket(id="live", text="I was charged twice for my subscription.", label="billing")
    r = route(ticket, build_question(), model="nimble")
    assert r.choice == "billing"
    assert sum(r.probabilities.values()) == pytest.approx(1.0, abs=1e-3)
    assert 0.0 <= r.confidence <= 1.0
```

Run them:

```bash
uv run pytest -v
```

Expected: `ImportError: cannot import name 'format_row'` in `test_router.py`.

### Write the CLI

In `exercises/ticket_router/router.py`, add `import argparse` and `import sys` to the standard-library imports, and change the `sysone` import to:

```python
from sysone import Decision, SystemOneError, choice, decide
```

Then append:

```python
def format_row(r: Routed) -> str:
    probs = " ".join(f"{k}={v:.2f}" for k, v in r.probabilities.items())
    mark = "✓" if r.correct else f"✗ expected {r.ticket.label}"
    return (
        f"{r.ticket.id:<4} {r.choice:<8} conf={r.confidence:.2f} "
        f"{r.latency_ms:>4.0f}ms  [{probs}]  {mark}"
    )


def format_summary(s: Summary) -> str:
    correct = round(s.accuracy * s.n)
    if s.confident_accuracy is None:
        gated = "n/a"
    else:
        gated = f"{s.confident_accuracy:.0%}"
    return (
        f"accuracy {s.accuracy:.0%} ({correct}/{s.n})\n"
        f"confidence >= {s.threshold:.2f}: {s.confident_n}/{s.n} kept, accuracy {gated}\n"
        f"latency p50 {s.p50_latency_ms:.0f}ms, max {s.max_latency_ms:.0f}ms (warm-up excluded)"
    )


def main(argv: list[str] | None = None, decide_fn: Callable[..., Decision] = decide) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=None)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument(
        "--no-descriptions",
        action="store_true",
        help="send option keys only (null descriptions) to see how much descriptions help",
    )
    args = parser.parse_args(argv)

    question = build_question(describe=not args.no_descriptions)
    tickets = load_tickets()
    try:
        # Warm-up: the first call loads the model and is several times slower.
        decide_fn("warm-up", {QUESTION_NAME: question}, model=args.model)
        results = [route(t, question, model=args.model, decide_fn=decide_fn) for t in tickets]
    except SystemOneError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    for r in results:
        print(format_row(r))
    print()
    print(format_summary(summarize(results, args.threshold)))
    return 0


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    raise SystemExit(main())
```

Why it's written this way:

- **`--model` defaults to `None`, not `"nimble"`.** `None` lets `decide()` pick up `DEFAULT_MODEL` from the environment or `.env`. A non-`None` default here would silently override `.env`.
- **The warm-up call is left out of the stats.** The first call loads the model. On Ollama it's about 6× slower than a warm call, and on DefAPI the first call took about 7 s against about 170 ms for warm ones.
- **`load_dotenv()` is in the `__main__` block, not in `main()`.** Tests call `main()` directly, and loading `.env` there would put your real token into the test process. `load_dotenv()` doesn't override variables already set in your shell, so an exported variable wins over `.env`.

Run the full check:

```bash
uv run pytest -v && uv run ruff check . && uv run ruff format --check .
```

Expected: 22 passed (21 offline + 1 live), ruff clean. If Ollama isn't running, the live test is skipped instead. If the format check fails, run `uv run ruff format .`.

Commit:

```bash
git add exercises tests
git commit -m "feat: add ticket router exercise with CLI and tests"
```

## Step 5: The learning run

This is the point of the exercise: run the router, read the probabilities, and write down what you see.

### Choose a backend

Copy the template and keep exactly one block uncommented:

```bash
cp .env.example .env
```

```bash
# Local Nimble through Ollama. These match the built-in defaults, so this block is optional.
DEFAULT_MODEL="nimble"
DEFAULT_BASE_URL="http://localhost:11434"
DEFAULT_ENDPOINT="/v1/systemone"

# Hosted Jev through DefAPI
# API_TOKEN="<your DefAPI API key>"
# DEFAULT_MODEL="typesafe/jev-1.13"
# DEFAULT_BASE_URL="https://api.defapi.org"
# DEFAULT_ENDPOINT="/api/v1/decisions"
```

The base URL must contain the scheme only once. `https://https://…` fails.

### Run it three ways

```bash
uv run python -m exercises.ticket_router.router                     # with option descriptions
uv run python -m exercises.ticket_router.router --no-descriptions   # option keys only
uv run python -m exercises.ticket_router.router --threshold 0.8     # stricter confidence gate
```

To save all three runs at once, create `run.sh` and make it executable (`chmod +x run.sh`):

```bash
#!/bin/bash

uv run python -m exercises.ticket_router.router > out-1.txt
uv run python -m exercises.ticket_router.router --no-descriptions > out-2.txt
uv run python -m exercises.ticket_router.router --threshold 0.8 > out-3.txt
```

This repo keeps the saved runs under `out/<backend>/`, for example `mkdir -p out/nimble && mv out-*.txt out/nimble/`. To compare backends, switch the `.env` block, run again and save to `out/jev/`. `--model` overrides `DEFAULT_MODEL` for a single run.

Each run prints 20 rows and a summary. Here's the start and end of a Nimble run with descriptions:

```
t01  billing  conf=0.99  370ms  [billing=1.00 bug=0.00 feature=0.00 account=0.00]  ✓
t02  billing  conf=0.98  516ms  [billing=1.00 bug=0.00 feature=0.00 account=0.00]  ✓
...
t13  feature  conf=0.70  361ms  [billing=0.02 bug=0.02 feature=0.90 account=0.07]  ✓
...
t20  account  conf=0.98  369ms  [billing=0.00 bug=0.00 feature=0.00 account=1.00]  ✓

accuracy 100% (20/20)
confidence >= 0.50: 20/20 kept, accuracy 100%
latency p50 370ms, max 516ms (warm-up excluded)
```

### What to look for

- **t13 and t16**, the ambiguous tickets. How spread out are their probabilities?
- **The gap between the top probability and `conf`.** On t13 above, the top probability is 0.90 but `conf` is 0.70. `confidence` measures how peaked the whole distribution is, not how likely the top answer is.
- **Accuracy and confidence without descriptions.** Does accuracy drop, or only confidence?
- **What the 0.8 threshold drops.** Which tickets fall below it, and would they have been wrong?

For reference, a DefAPI run on 2026-10-03 with `typesafe/jev-1.13` got 20/20 correct, with 18 of 20 rows at `conf=1.00`, p50 latency 174 ms, max 230 ms and about $0.00003 per call (DefAPI reports `cost` in `usage`). With almost everything at confidence 1.00, this dataset can't tell thresholds apart on Jev. Testing calibration needs harder examples. The full comparison is in [results.md](results.md).

### Write down what you learned

Create `exercises/ticket_router/NOTES.md` from your real output. Record measured numbers only, as short bullets, and label every number with its backend and model (for example, Ollama `nimble` or DefAPI `typesafe/jev-1.13`):

- `## Results`: accuracy with and without descriptions, confidence-gated accuracy at 0.5 and 0.8, p50 and max latency
- `## Misses`: ticket id, expected label, chosen label, probabilities
- `## Lessons for CI failure triage`: how you'll phrase instructions and option descriptions, and what threshold to start with

Commit the saved runs:

```bash
git add run.sh out exercises/ticket_router/NOTES.md
git commit -m "docs: add saved Nimble and Jev ticket-router runs"
```

## Step 6 (optional): Save API examples

[`api-examples/`](../api-examples/) holds one request sent to both backends, with each response. It's a refund ticket that asks a `choice` (route), a `noul` (urgent) and a `score` (severity) in one call, so you can see all three answer types side by side.

The `.http` files are written for the VS Code [REST Client](https://marketplace.visualstudio.com/items?itemName=humao.rest-client) extension. To recreate them:

1. Write `api-examples/hello-nimble.http` with `POST http://localhost:11434/v1/systemone`, `Content-Type: application/json` and the request body. Copy the body from [hello-nimble.http](../api-examples/hello-nimble.http).
2. Write `api-examples/hello-defapi.http` with the same body, `POST https://api.defapi.org/api/v1/decisions`, model `typesafe/jev-1.13`, and the header `Authorization: Bearer {{$dotenv API_TOKEN}}`. REST Client reads the key from `.env`, so no secret is stored in the file.
3. Send each request and save the response as `response-nimble.json` and `response-defapi.json`.

See [backends.md](backends.md) for what the responses show.

```bash
git add api-examples
git commit -m "docs: add Ollama and DefAPI request/response examples"
```

## Step 7 (optional): Prepare the repo for publishing

These files aren't needed to learn the API. They make the repo safe and tidy to publish on GitHub.

### README, license and security policy

- **`README.md`**: what the repo is, how to run it and what the results show. See this repo's [README](../README.md).
- **`LICENSE`**: this repo uses the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0.txt). Once the file exists, add the license to `pyproject.toml` under `[project]`:

  ```toml
  license = "Apache-2.0"
  license-files = ["LICENSE"]
  ```

- **`SECURITY.md`**: how to report a vulnerability privately, what's in scope, and where secrets belong. See this repo's [SECURITY.md](../SECURITY.md).

### Continuous integration

`.github/workflows/ci.yml` lints once, then runs the offline tests on every supported Python version. The workflow token is read-only, and actions are pinned to full commit SHAs:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

# Least privilege: the workflow only needs to read the code.
permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  # Stage 1: lint once, on a single Python version.
  lint:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      # Actions are pinned to full commit SHAs; Dependabot keeps them current.
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false

      - uses: astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7 # v10.2.0
        with:
          python-version: "3.13"
          enable-cache: true

      # ShellCheck is preinstalled on GitHub's Ubuntu runners, so no extra action is needed.
      - name: Lint shell scripts
        run: shellcheck scripts/*.sh

      - name: Install dependencies
        run: uv sync --locked

      - name: Lint Python
        run: uv run ruff check .

      - name: Check formatting
        run: uv run ruff format --check .

  # Stage 2: run the tests on every supported Python version, only after lint passes.
  test:
    needs: lint
    runs-on: ubuntu-latest
    timeout-minutes: 10
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.12", "3.13", "3.14"]
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false

      - uses: astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7 # v10.2.0
        with:
          python-version: ${{ matrix.python-version }}
          enable-cache: true

      - name: Install dependencies
        run: uv sync --locked

      # Offline tests only: no Ollama in CI and no API secrets are given to the workflow.
      - name: Test
        run: uv run pytest -m "not live"
```

The `shellcheck scripts/*.sh` step needs at least one script in `scripts/`. Leave it out until you add the configuration script below.

`.github/dependabot.yml` keeps the Python dependencies and the pinned actions up to date, waiting a week before proposing a new release:

```yaml
version: 2
updates:
  # Python dependencies from pyproject.toml / uv.lock
  - package-ecosystem: "uv"
    directory: "/"
    schedule:
      interval: "weekly"
    cooldown:
      default-days: 7 # give new releases a week before proposing them
    groups:
      python-dependencies:
        patterns: ["*"]

  # SHA-pinned actions in .github/workflows
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    cooldown:
      default-days: 7
    groups:
      github-actions:
        patterns: ["*"]
```

### GitHub repository settings

[`scripts/configure-github-repo.sh`](../scripts/configure-github-repo.sh) applies this repo's GitHub security and permission settings, including a ruleset on `main`. It needs `gh` (logged in as a repo admin) and `jq`. Run it after the repo exists on GitHub and `main` has been pushed once. It's a dry run by default:

```bash
scripts/configure-github-repo.sh OWNER/REPO           # print what would change
scripts/configure-github-repo.sh OWNER/REPO --apply   # apply it
```

## What the tests protect you from

Each failure mode below has a test that catches it:

| If this happens | What you see instead | Test |
|---|---|---|
| Ollama isn't running, or `DEFAULT_BASE_URL` is wrong | `cannot reach <base_url>: …` and exit code 1, with no traceback | `test_decide_wraps_connection_errors`, `test_main_reports_unreachable_server` |
| The model isn't pulled (404) | The server's own message, e.g. `model "tev1" not found…` | `test_decide_raises_with_server_error_message` |
| A dataset label has a typo, e.g. `"acount"` | A failing test, not a silent miss | `test_every_ticket_label_is_a_known_option` |
| No result clears the confidence threshold | `n/a` instead of a division by zero | `test_summarize_with_nothing_confident` |
| Confidence exactly equals the threshold | It counts as confident (`>=`) | `test_summarize_threshold_is_inclusive` |
| The token or DefAPI settings leak into tests | Only the CLI's `__main__` block loads `.env`, and `conftest.py` clears the four variables | `test_main_does_not_load_dotenv`, `test_cli_entry_point_loads_dotenv_once_before_routing` |
| An explicit `token=` is ignored | An explicit argument always beats the environment | `test_explicit_arguments_override_env` |
| Settings are read at import time and miss `.env` | Settings are read on every call | `test_env_reads_happen_per_call_not_at_import`, `test_decide_reads_settings_and_token_from_env` |
| An `Authorization` header is sent with no token | No header unless a token is set | `test_decide_uses_built_in_defaults_and_no_auth_without_env` |

## Where to go next

- **Read the background.** [concepts.md](concepts.md) covers the three question types and the design patterns (guardrail sandwich, confidence-gated routing and others) that this client makes possible.
- **Compare the backends.** [results.md](results.md) has the full Nimble vs Jev comparison and what it does and doesn't show.
- **Try a harder problem.** The next stage of this project reuses `src/sysone` unchanged for CI failure triage: a log tail goes in, and one call returns the cause (`choice`), whether it's worth a retry (`noul`) and severity (`score`), with low-confidence cases sent to a person. Ticket routing was too easy to test calibration, so that stage adds a calibration harness: reliability curves binned by top probability, and a threshold sweep across models.
