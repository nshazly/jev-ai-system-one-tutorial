# Security policy

## Supported versions

This is a tutorial and portfolio project. Only the latest commit on `main` is supported; there are no maintained releases.

## Reporting a vulnerability

Please **don't open a public issue** for a security problem. Report it privately instead:

1. Go to this repository's **Security** tab.
2. Click **Report a vulnerability**. This uses GitHub's private vulnerability reporting.

Include what you found, the steps to reproduce it, and what an attacker could do with it. This is a personal project, so responses are best effort. You can expect an acknowledgement within 7 days, and a fix or a decision soon after. You'll be credited in the advisory unless you'd rather not be.

## Scope

**In scope:**
- The code in this repository: the `sysone` client, the ticket-router CLI, the tests and the CI configuration.
- Any credential or secret accidentally committed to the repository or its history.

**Out of scope.** Please report these to the projects that own them:
- Vulnerabilities in [Ollama](https://github.com/ollama/ollama), [Nimble](https://github.com/bespokelabsai/nimble), [TypeSafe AI's Jev](https://typesafe.ai) or [DefAPI](https://defapi.org).
- Model behaviour, such as a misclassification or a decision changed by prompt injection. These are limitations of the models; the README covers the guardrail patterns that reduce them.

## Handling secrets

API keys belong in a local `.env` file, which is gitignored; see `.env.example`. If you find a real key anywhere in this repository, report it privately using the steps above so it can be revoked.
