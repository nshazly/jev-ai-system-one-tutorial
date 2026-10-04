# Jev-style decision models: a hands-on tutorial

A tutorial for [TypeSafe AI](https://typesafe.ai)'s **Jev**, a "System One" model that makes typed decisions instead of generating text. The tutorial runs on **Nimble**, an open-source model from Bespoke Labs, served locally through [Ollama](https://ollama.com/library/nimble). Ollama's decision endpoint follows TypeSafe's style, so you can learn the ideas without Jev access.

Nimble is **not** Jev. Bespoke Labs built it to follow the System One approach and state that it was [not distilled from Jev](https://github.com/bespokelabsai/nimble). It is a different model, served by different software at a different endpoint. Its probabilities and confidence scores are its own, so don't expect them to match Jev's.

The same code can also call hosted Jev through [DefAPI](https://defapi.org/model/typesafe/jev-1.13), which made a side-by-side comparison possible ([results below](#results-nimble-vs-jev)).

> Not affiliated with TypeSafe AI, Bespoke Labs, Ollama or DefAPI. Product names belong to their owners.
>
> This repository was created with the help of AI (Claude Code). That includes the code, tests, implementation plan and this README. The saved model outputs in `out/` and `api-examples/` are real responses from the two APIs.

## What a System One model does

You send a **state** (text or JSON) and a set of named, typed **questions**. The model answers every question in one pass with a label or score plus **probabilities**. It never writes free text or explanations. That makes it fast, cheap and predictable, which suits the many small decisions software makes all day. Open-ended reasoning stays with an LLM or a person.

### The three question types

| Type | You ask | You get back |
|---|---|---|
| **`choice`** | "Pick one of these options." 2–26 options, each with an optional description. | The chosen label, a probability for every option, and `confidence` |
| **`noul`** | "Is this statement true?" You describe what `false` and `true` mean. | The probability that the statement is true |
| **`score`** | "Rate the state on this rubric." An ordered list of 2–26 levels. | The expected level (a probability-weighted index), a probability for every level, and `confidence` |

One request can mix all three:

```bash
curl -s localhost:11434/v1/systemone -d '{
  "model": "nimble",
  "state": "I was charged twice and I need this fixed today",
  "questions": {
    "team":   {"type": "choice", "instructions": "Which team should handle this?",
               "criteria": {"billing": "Payments and refunds", "bug": "Something is broken"}},
    "urgent": {"type": "noul", "instructions": "Is the customer blocked or losing money?",
               "criteria": {"false": "can wait", "true": "blocked or losing money"}},
    "mood":   {"type": "score", "instructions": "How upset is the customer?",
               "criteria": ["calm", "annoyed", "angry"]}
  }
}'
```

Every question needs both `instructions` and `criteria`. Clear instructions and good option descriptions do much of the work: in the runs below, removing the option descriptions lowered Nimble's confidence noticeably.

### API examples: Ollama and DefAPI

[`api-examples/`](api-examples/) has the same request sent to both APIs, with the response each one returned. The request is a refund ticket asking a `choice` (route), a `noul` (urgent) and a `score` (severity):

| File | What it is |
|---|---|
| [`hello-nimble.http`](api-examples/hello-nimble.http) | Ollama call: `POST http://localhost:11434/v1/systemone` with model `nimble`, no auth |
| [`response-nimble.json`](api-examples/response-nimble.json) | Ollama's response |
| [`hello-defapi.http`](api-examples/hello-defapi.http) | DefAPI call: `POST https://api.defapi.org/api/v1/decisions` with model `typesafe/jev-1.13` and a bearer token |
| [`response-defapi.json`](api-examples/response-defapi.json) | DefAPI's response. It reports the pinned model version `typesafe/jev-1.13-20260917`. |

Both APIs take the same request body and return answers in the same shape. Only the URL, model name and `Authorization` header differ. The `.http` files are written for the VS Code [REST Client](https://marketplace.visualstudio.com/items?itemName=humao.rest-client) extension, and `{{$dotenv API_TOKEN}}` reads your key from `.env`, so no secret is stored in the file.

## Design patterns

The model only returns probabilities, so your code stays in control. That makes a few patterns natural:

- **Guardrail sandwich (Jev → LLM → Jev).**
  1. Jev screens the inbound message, e.g. "is this a prompt injection?" (`noul`).
  2. The LLM writes the reply.
  3. Jev checks the draft reply, and any tool arguments the agent wants to use, before anything is sent or run.

  Each check returns typed verdicts (allow / review / block) in milliseconds. That's cheap enough to run on every turn. ([Arize write-up](https://arize.com/blog/llm-guardrails-jev/), [demo repo](https://github.com/jimbobbennett/typesafe-guardrails))
  ```
  user message ──► [Jev: safe input?] ──► LLM drafts reply ──► [Jev: safe output / tool call?] ──► send
                        │ block / review                              │ block / review
                        ▼                                             ▼
                     refuse or escalate                          regenerate or escalate
  ```
- **Confidence-gated routing.** The answer says what to do, and the confidence says whether to do it automatically. Above your threshold the code acts. Below it, a person reviews. ([TypeSafe docs](https://docs.typesafe.ai/patterns))
- **Intent routing.** A `choice` question classifies a request and sends it to the right handler. This repo's ticket router does exactly that.
- **Speculative fan-out.** Ask many questions in one call, including some you may not need, and let your code use the relevant answers. It's one pass either way.
- **Composite scoring.** Combine several `score` and `noul` answers into one risk or priority number.

The general rule: **LLMs for open-ended generation, decision models for the repeated yes/no, which-one and how-much calls**, combined in ordinary code.

## Use Nimble while you wait for Jev

Jev is in early access ([typesafe.ai](https://typesafe.ai)). Nimble lets you build and test the same kind of system now:

- **It's free and local.** It runs on your machine through Ollama 0.35+, under the Apache 2.0 license.
- **It uses the same request shape.** Moving to Jev later means changing the model, base URL, endpoint and token in `.env`. No code changes are needed (see [Switching backends](#switching-backends)).
- **Measure; don't assume.** TypeSafe's speed and calibration claims are about hosted Jev. Measure Nimble's accuracy and calibration on your own data, and measure again after switching.

## Results: Nimble vs Jev

[`out/`](out/) holds the output of the ticket-router exercise run against both backends. Each run routes the same 20 labelled support tickets (5 each of billing, bug, feature and account) with one `choice` question.

| File | Run |
|---|---|
| `out/<model>/out-1.txt` | Default: options have descriptions, threshold 0.5 |
| `out/<model>/out-2.txt` | `--no-descriptions`: option keys only |
| `out/<model>/out-3.txt` | `--threshold 0.8` |

Nimble ran locally through Ollama. Jev (`typesafe/jev-1.13`) ran through DefAPI. Both runs were on 2026-10-03.

| Run | Model | Accuracy | Mean confidence | Rows at confidence ≥ 0.99 | Lowest confidence | p50 latency |
|---|---|---|---|---|---|---|
| With descriptions | Nimble | 20/20 | 0.95 | 5/20 | 0.70 (t13) | 370 ms |
| With descriptions | Jev | 20/20 | **0.99** | **19/20** | 0.81 (t13) | 175 ms |
| No descriptions | Nimble | 20/20 | 0.87 | 0/20 | 0.43 (t13) | 302 ms |
| No descriptions | Jev | 20/20 | **0.98** | **18/20** | 0.74 (t13) | 190 ms |

At the 0.8 threshold (`out-3`), Jev kept 20/20 tickets and Nimble kept 19/20, dropping t13.

**What it shows:**
- **Both models routed every ticket correctly. Jev was consistently more confident.**
- **Removing option descriptions cost Nimble far more confidence** (0.95 → 0.87, with one ticket falling below 0.5). Jev barely moved (0.99 → 0.98).
- **Both found the same ticket hardest.** t13 ("Can you support SSO with Okta?") was the least confident for both, split between `feature` and `account`.

**What it doesn't show:**
- **Higher confidence is not the same as better calibration.** With 20 easy tickets and 100% accuracy on both sides, there's nothing here to test whether either model's confidence matches how often it is right. That needs a larger, harder labelled set.
- **The latency numbers aren't a fair speed comparison.** One model ran over the network on hosted hardware; the other ran on a local machine.
- **`confidence` may not be computed the same way.** On Ollama it is `1 − normalized entropy` of the probabilities. One DefAPI result didn't fit that formula. Compare the probabilities as well as `confidence`.

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

### Switching backends

The client reads its settings from the environment. The CLI also loads a `.env` file from the repo root. Keep `.env` out of git; it's already in `.gitignore`.

```bash
# Local Nimble through Ollama (these are the defaults)
DEFAULT_MODEL="nimble"
DEFAULT_BASE_URL="http://localhost:11434"
DEFAULT_ENDPOINT="/v1/systemone"

# Hosted Jev through DefAPI
# API_TOKEN="<your DefAPI API key>"
# DEFAULT_MODEL="typesafe/jev-1.13"
# DEFAULT_BASE_URL="https://api.defapi.org"
# DEFAULT_ENDPOINT="/api/v1/decisions"
```

An explicit argument (`--model`, or `decide(model=..., token=...)`) overrides the environment. When `API_TOKEN` is set, it is sent as `Authorization: Bearer <token>`.

## Repository layout

```
src/sysone/                 reusable client: decide(), choice()/noul()/score()
exercises/ticket_router/    the 20-ticket routing exercise and its CLI
tests/                      offline tests (httpx.MockTransport) and one live Nimble test
out/                        saved runs: out/nimble/, out/jev/
api-examples/               the same request sent to Ollama (Nimble) and DefAPI (Jev), with both responses
scripts/                    configure-github-repo.sh: applies this repo's GitHub security settings (dry run by default)
```

## Build your own Jev-style model

Nimble shows how a model like this is made. It's a LoRA fine-tune of Qwen3.5-9B. It reads the model's scores for the allowed answer tokens instead of generating text, then turns them into probabilities with a softmax. It was trained on contrastive example pairs: pairs that differ in one key fact. Bespoke Labs published the training recipe, data-curation pipeline, evaluation set and inference code:

- **GitHub:** [bespokelabsai/nimble](https://github.com/bespokelabsai/nimble) (training, data curation, evaluation and inference code)
- **Hugging Face:** [bespokelabs/Bespoke-Nimble-9B](https://huggingface.co/bespokelabs/Bespoke-Nimble-9B) (model weights and model card)

## Links

- **Jev:**
  - [TypeSafe AI](https://typesafe.ai), the makers of Jev
  - [TypeSafe docs](https://docs.typesafe.ai) and its [patterns](https://docs.typesafe.ai/patterns)
- **DefAPI:** [DefAPI](https://defapi.org), a hosted API reseller, and its [Jev 1.13 page](https://defapi.org/model/typesafe/jev-1.13)
- **Nimble:**
  - [GitHub](https://github.com/bespokelabsai/nimble)
  - [Hugging Face](https://huggingface.co/bespokelabs/Bespoke-Nimble-9B)
  - [Ollama library](https://ollama.com/library/nimble)
- **Ollama:**
  - [Decision API docs](https://docs.ollama.com/capabilities/decision)
  - [launch blog post](https://ollama.com/blog/ollama-now-supports-jev-style-decision-models)
- **Guardrails:**
  - [Real-time LLM guardrails with Jev](https://arize.com/blog/llm-guardrails-jev/) (Arize)
  - [typesafe-guardrails demo repo](https://github.com/jimbobbennett/typesafe-guardrails)

## Security

To report a vulnerability, see [SECURITY.md](SECURITY.md). Please use private reporting, not public issues. CI runs lint and the offline tests with a read-only token, and Dependabot keeps the Python dependencies and pinned actions up to date.

## License

Copyright 2026 Neill Shazly. Licensed under the [Apache License, Version 2.0](LICENSE). You may use, modify and distribute this code under its terms, which include a patent grant and a requirement to keep the copyright and license notices.

The license covers this repository's code and docs. It doesn't cover the models or services it calls (Nimble, Jev, DefAPI), which have their own licenses and terms. The saved model outputs in `out/` and `api-examples/` are included as examples.
