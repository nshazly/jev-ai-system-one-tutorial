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
