# Backends: Ollama (Nimble) and DefAPI (Jev)

The same request body works against both backends. Only the URL, model name and `Authorization` header differ.

| | Local Nimble through Ollama | Hosted Jev through DefAPI |
|---|---|---|
| Base URL | `http://localhost:11434` | `https://api.defapi.org` |
| Endpoint | `/v1/systemone` | `/api/v1/decisions` |
| Model | `nimble` | `typesafe/jev-1.13` |
| Auth | none | `Authorization: Bearer <DefAPI API key>` |

## Switching backends

The client reads its settings from the environment. The CLI also loads a `.env` file from the repo root; start from [`.env.example`](../.env.example). Keep `.env` out of git; it's already in `.gitignore`.

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

An explicit argument (`--model`, or `decide(model=..., token=...)`) overrides the environment. When `API_TOKEN` is set, it is sent as `Authorization: Bearer <token>`. The [tutorial](tutorial.md#configuration) explains how settings are resolved and why.

## API examples

[`api-examples/`](../api-examples/) has the same request sent to both APIs, with the response each one returned. The request is a refund ticket asking a `choice` (route), a `noul` (urgent) and a `score` (severity):

| File | What it is |
|---|---|
| [`hello-nimble.http`](../api-examples/hello-nimble.http) | Ollama call: `POST http://localhost:11434/v1/systemone` with model `nimble`, no auth |
| [`response-nimble.json`](../api-examples/response-nimble.json) | Ollama's response |
| [`hello-defapi.http`](../api-examples/hello-defapi.http) | DefAPI call: `POST https://api.defapi.org/api/v1/decisions` with model `typesafe/jev-1.13` and a bearer token |
| [`response-defapi.json`](../api-examples/response-defapi.json) | DefAPI's response. It reports the pinned model version `typesafe/jev-1.13-20260917`. |

Both APIs return answers in the same shape. The `.http` files are written for the VS Code [REST Client](https://marketplace.visualstudio.com/items?itemName=humao.rest-client) extension, and `{{$dotenv API_TOKEN}}` reads your key from `.env`, so no secret is stored in the file.
