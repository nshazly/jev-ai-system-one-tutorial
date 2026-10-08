# Concepts: System One decision models

## What a System One model does

You send a **state** (text or JSON) and a set of named, typed **questions**. The model answers every question in one pass with a label or score plus **probabilities**. It never writes free text or explanations. That makes it fast, cheap and predictable, which suits the many small decisions software makes all day. Open-ended reasoning stays with an LLM or a person.

## The three question types

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

Every question needs both `instructions` and `criteria`. Clear instructions and good option descriptions do much of the work: in this repo's runs, removing the option descriptions lowered Nimble's confidence noticeably ([results](results.md)).

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
- **It uses the same request shape.** Moving to Jev later means changing the model, base URL, endpoint and token in `.env`. No code changes are needed (see [backends](backends.md)).
- **Measure; don't assume.** TypeSafe's speed and calibration claims are about hosted Jev. Measure Nimble's accuracy and calibration on your own data, and measure again after switching.

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
