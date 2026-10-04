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
