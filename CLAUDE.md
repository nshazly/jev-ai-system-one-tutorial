# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

A learning repo for Jev-style "System One" decision models served locally by Ollama. The work happens in three stages:

1. **Ticket router** (`exercises/ticket_router/`): a 30-minute warm-up that learns the API with one `choice` question over 20 labelled tickets.
2. **CI failure triage**: the portfolio project. Log tail → `choice` (flaky / infra / dependency / test regression / config), `noul` ("worth a retry") and `score` (severity) in one call, with a human fallback when confidence is low.
3. **Calibration harness**, built into the CI failure triage project: accuracy, latency, reliability curve and threshold sweep across `nimble`, `tev1` and `tev1:0.8b`.

Keep `src/sysone/` as the reusable client shared by every stage. Each exercise or project lives in its own package and depends on it.

## Commands

Python ≥3.12, managed with `uv`. Tests run offline against `httpx.MockTransport`. Anything marked `@pytest.mark.live` needs Ollama running with `nimble` pulled and skips itself otherwise.

```bash
uv sync                                            # install deps
uv run pytest                                      # all tests (live ones auto-skip if Ollama is down)
uv run pytest -m "not live"                        # offline only
uv run pytest tests/test_client.py::test_name -v   # single test
uv run ruff check . && uv run ruff format .        # lint / format
uv run python -m exercises.ticket_router.router    # run the ticket router (--help for flags)
```

## System One API: verified facts (Ollama 0.35.0, `nimble`)

What the live server actually does. Where an older note or example disagrees, trust this list:

- `POST http://localhost:11434/v1/systemone` with body `{"model", "state", "questions": {name: question}}`. `state` can be a string or a JSON object.
- Each question needs **both** `instructions` (a non-empty string: the question itself) **and** `criteria`. Sending `criteria` alone returns a 400 error.
  - `choice`: `criteria` maps each option key to a description, or to `null` for no description. It takes 2–26 options.
  - `noul`: `criteria` is `{"false": "...", "true": "..."}`.
  - `score`: `criteria` is an ordered list of 2–26 levels.
- Answers are returned under `answers[name]`:
  - `choice` → `choice` (the label), `probabilities` (label → p) and `confidence`.
  - `noul` → `noul`, which is P(true). There is no confidence field.
  - `score` → `score`, which is the **expected level index** (0-based, Σ i·pᵢ, not normalized to 0–1), plus `legend` ("0" → level text), `probabilities` ("0" → p) and `confidence`.
- **`confidence` is `1 − normalized entropy`** (entropy / ln n), **not** the top probability. For example, a choice with 0.97 top probability reported confidence 0.89. Keep this in mind when setting thresholds and when drawing reliability curves: bin by top probability for calibration, and treat `confidence` as a separate signal.
- Errors are non-200 responses with `{"error": "..."}`. A model that isn't pulled returns 404 (`model "tev1" not found, try pulling it first`). A bad question returns 400.
- Latency: the first call after a model loads took ~350 ms, and warm calls took ~60 ms. Always make one warm-up call and leave it out of latency statistics.
- Wording matters. `state` = `{"subject":"refund","body":"charged twice"}` with the vague instruction `"Route"` and null descriptions came back as `bug` (p=0.63, confidence 0.05). Clear instructions and good option descriptions carry much of the accuracy.

TypeSafe's calibration claims are about their hosted Jev, not local `nimble`. Measure calibration here instead of assuming it. Only `nimble` is pulled locally so far; pull `tev1` and `tev1:0.8b` before the bake-off.
