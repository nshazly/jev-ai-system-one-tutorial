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
