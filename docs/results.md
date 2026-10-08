# Results: Nimble vs Jev

[`out/`](../out/) holds the output of the ticket-router exercise run against both backends. Each run routes the same 20 labelled support tickets (5 each of billing, bug, feature and account) with one `choice` question. To produce these runs yourself, follow [Step 5 of the tutorial](tutorial.md#step-5-the-learning-run).

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

## What it shows

- **Both models routed every ticket correctly. Jev was consistently more confident.**
- **Removing option descriptions cost Nimble far more confidence** (0.95 → 0.87, with one ticket falling below 0.5). Jev barely moved (0.99 → 0.98).
- **Both found the same ticket hardest.** t13 ("Can you support SSO with Okta?") was the least confident for both, split between `feature` and `account`.

## What it doesn't show

- **Higher confidence is not the same as better calibration.** With 20 easy tickets and 100% accuracy on both sides, there's nothing here to test whether either model's confidence matches how often it is right. That needs a larger, harder labelled set.
- **The latency numbers aren't a fair speed comparison.** One model ran over the network on hosted hardware; the other ran on a local machine.
- **`confidence` may not be computed the same way.** On Ollama it is `1 − normalized entropy` of the probabilities. One DefAPI result didn't fit that formula. Compare the probabilities as well as `confidence`.
