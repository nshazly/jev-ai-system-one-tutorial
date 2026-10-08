# Jev-style decision models: a hands-on tutorial

> **Start here: [the tutorial](docs/tutorial.md)** rebuilds this repo step by step, from an empty folder to a tested client and a ticket router that runs against local Nimble or hosted Jev.

A tutorial for [TypeSafe AI](https://typesafe.ai)'s **Jev**, a "System One" model that makes typed decisions instead of generating text. It runs on **Nimble**, an open-source model from Bespoke Labs served locally through [Ollama](https://ollama.com/library/nimble), whose decision endpoint follows TypeSafe's style. The same code can call hosted Jev through [DefAPI](https://defapi.org/model/typesafe/jev-1.13).

Nimble is **not** Jev. Bespoke Labs state it was [not distilled from Jev](https://github.com/bespokelabsai/nimble), and its probabilities and confidence scores are its own.

> Not affiliated with TypeSafe AI, Bespoke Labs, Ollama or DefAPI. Product names belong to their owners.
>
> This repository was created with the help of AI (Claude Code), including the code, tests, docs and this README. The saved model outputs in `out/` and `api-examples/` are real responses from the two APIs.

## What a System One model does

You send a **state** (text or JSON) and named, typed **questions**. The model answers all of them in one pass with a label or score plus **probabilities**, and never writes free text. Use it for the many small, repeated decisions software makes; leave open-ended reasoning to an LLM or a person.

| Type | You ask | You get back |
|---|---|---|
| **`choice`** | Pick one of 2–26 options | The label, a probability per option, and `confidence` |
| **`noul`** | Is this statement true? | P(true) |
| **`score`** | Rate on an ordered rubric of 2–26 levels | The expected level, a probability per level, and `confidence` |

More in [docs/concepts.md](docs/concepts.md): a full request example, design patterns such as the guardrail sandwich and confidence-gated routing, and how Nimble was built.

## Results in brief

Both backends routed all 20 labelled tickets correctly. Jev was consistently more confident, and removing option descriptions cost Nimble far more confidence than Jev. Twenty easy tickets can't test calibration, though. Full table and caveats: [docs/results.md](docs/results.md).

## Quick start

Requirements: Python ≥ 3.12, [uv](https://docs.astral.sh/uv/) and [Ollama](https://ollama.com) 0.35+.

```bash
ollama pull nimble                                   # ~9 GB
uv sync
uv run python -m exercises.ticket_router.router      # route the 20 tickets
uv run python -m exercises.ticket_router.router --no-descriptions
uv run python -m exercises.ticket_router.router --threshold 0.8
./run.sh                                             # all three runs, saved to out-1..3.txt

uv run pytest                                        # tests; the live test skips if Ollama is down
```

To use hosted Jev instead, copy [`.env.example`](.env.example) to `.env` and set the DefAPI values. See [docs/backends.md](docs/backends.md) for the settings and side-by-side API examples.

## Repository layout

```
src/sysone/                 reusable client: decide(), choice()/noul()/score()
exercises/ticket_router/    the 20-ticket routing exercise and its CLI
tests/                      offline tests (httpx.MockTransport) and one live Nimble test
out/                        saved runs: out/nimble/, out/jev/
api-examples/               the same request sent to Ollama (Nimble) and DefAPI (Jev), with both responses
docs/                       tutorial, concepts, results and backend docs
scripts/                    configure-github-repo.sh: applies this repo's GitHub security settings
```

## Documentation

| Doc | What's in it |
|---|---|
| [Tutorial](docs/tutorial.md) | Rebuild the repo step by step, test-first |
| [Concepts](docs/concepts.md) | Question types, design patterns, building your own model, links |
| [Results](docs/results.md) | Nimble vs Jev on the ticket router: what it shows and doesn't |
| [Backends](docs/backends.md) | Switching between Ollama and DefAPI, with API examples |

## Security and license

To report a vulnerability, see [SECURITY.md](SECURITY.md) and use private reporting, not public issues. CI runs lint and the offline tests with a read-only token, and Dependabot keeps dependencies and pinned actions current.

Copyright 2026 Neill Shazly. Licensed under the [Apache License, Version 2.0](LICENSE). The license covers this repository's code and docs, not the models or services it calls (Nimble, Jev, DefAPI), which have their own terms.
