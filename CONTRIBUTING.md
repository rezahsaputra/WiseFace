# Contributing

Thanks for your interest in improving the Self-Hosted Face Compare API.
This document covers how to set up a dev environment, run the tests, and submit
changes.

## Ground rules

- **Be respectful.** Assume good faith in issues and reviews.
- **Keep the scope tight.** One logical change per pull request.
- **Never commit secrets.** `.env`, real API credentials, and TLS keys are
  git-ignored — keep them out of commits, screenshots, and issue text. See
  [Security](#security).
- **Preserve the contract.** This service mirrors the Face++ Compare
  request/response shape. Don't change the public API contract without a clear
  reason and a note in the PR.

## Development setup

```bash
git clone https://github.com/rezahsaputra/WiseFace.git
cd WiseFace
cp .env.example .env   # fill in values; never commit this file
```

Full deployment steps are in [INSTALLATION.md](INSTALLATION.md). For most code
changes you only need the test suite below — the recognition engine is mocked,
so you don't need TensorFlow or the model weights to develop and test.

## Running the tests

The suite mocks the DeepFace/Facenet512 engine, so it runs **without**
TensorFlow.

```bash
# With a local Python 3.11
pip install -r app/requirements-dev.txt
pytest
```

Or inside a throwaway container if you don't have Python locally:

```bash
docker run --rm -v "$PWD:/src" -w /src python:3.11-slim \
  bash -c "pip install -q -r app/requirements-dev.txt && pytest"
```

What the suite covers: image precedence resolution, base64/file/url decoding,
similarity & confidence math, the full API contract (auth, error shapes,
precedence, metrics), and the guarantee that no employee/identity parameter is
ever required.

### Tests are required for behavior changes

If you change behavior, add or update a test. Bug fixes should come with a test
that fails before the fix and passes after. Run `pytest` and make sure it's
green before opening a PR.

## Code style

- **Python 3.11**, type-hinted. Match the style of the surrounding code.
- Keep functions small and the hot path (per-request auth, compare) free of
  avoidable I/O.
- Comments explain **why**, not **what**. Don't narrate obvious code.
- Frontend (admin panel) is a single self-contained `admin/static/index.html`
  using Tailwind via CDN — keep it dependency-light.

## Project layout

See the [Project layout](README.md#project-layout) section of the README for a
map of `app/`, `admin/`, `nginx/`, `prometheus/`, and `grafana/`.

## Commit messages

- Use a concise, imperative subject line (e.g. `Fix admin API-key column field`).
- Add a body when the change isn't self-evident — explain the reasoning.
- Group related changes; avoid mixing unrelated edits in one commit.

## Pull requests

1. Fork and branch from `master` (e.g. `git checkout -b fix/auth-cache-ttl`).
2. Make your change with tests; run `pytest` locally.
3. Push your branch and open a PR against `master`.
4. In the description, explain **what** changed and **why**, and note any
   contract/behavior impact.

Maintainers may ask for adjustments — that's normal. Small, focused PRs get
reviewed fastest.

## Reporting bugs and requesting features

Open a GitHub issue with:

- **Bugs:** steps to reproduce, expected vs. actual behavior, relevant logs
  (`docker compose logs api`) with **credentials and personal data redacted**.
- **Features:** the problem you're trying to solve, not just the proposed
  solution.

## Security

Do **not** open a public issue for security vulnerabilities. Instead, report
them privately to the maintainer (e.g. via a GitHub Security Advisory on the
repository). Please give a reasonable window to address the issue before any
public disclosure.

When sharing logs or configs anywhere, scrub API keys/secrets, admin
passwords, and any image URLs that could identify a person.
