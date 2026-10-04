"""30-minute starter: route support tickets with a single System One `choice` question."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sysone import Decision, SystemOneError, choice, decide

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
