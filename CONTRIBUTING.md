# Contributing to OpenWellness

Thanks for your interest in contributing. OpenWellness is an open-source
platform for running wellness research studies, developed with support from the
National Institutes of Health (NIH). Contributions from other researchers and
developers are welcome — bug reports, fixes, documentation, and new features.

## Ways to contribute

- **Report a bug or request a feature** — open an issue describing what you
  observed (or want), with steps to reproduce and your environment where
  relevant.
- **Improve documentation** — the per-package READMEs are the source of truth;
  corrections and clarifications are valued contributions.
- **Submit code** — see the workflow below.

## Project layout

OpenWellness is two workspaces. Start with the top-level
[`README.md`](README.md), then the workspace and package READMEs:

| Area | Where | Toolchain |
| --- | --- | --- |
| Backend ([`backend/`](backend/README.md)) | `core`, `api`, `scheduler` | Python 3.12+, [uv](https://docs.astral.sh/uv/) |
| Dashboard ([`frontend/dashboard/`](frontend/dashboard/README.md)) | React SPA | Node, npm, Vite |
| Mobile ([`frontend/mobile/`](frontend/mobile/README.md)) | Compose Multiplatform | Gradle, Xcode |

Each package is self-contained with its own setup, configuration, and tests
documented in its README. Read the relevant one before starting.

## Development setup

Full prerequisites and configuration live in the workspace READMEs
([backend](backend/README.md#setup), [frontend](frontend/README.md)). The short
version:

```bash
# backend — from the workspace root so the shared lockfile/venv are used
cd backend
uv sync --extra dev

# dashboard
cd frontend/dashboard
npm install

# mobile
cd frontend/mobile
./gradlew :androidApp:installDebug   # iOS: open iosApp/iosApp.xcodeproj
```

No test suite needs a live datastore, broker, or backend — they all run against
in-memory fakes (MSW on the dashboard, Ktor `MockEngine` on mobile).

## Before opening a pull request

Run the checks for the area(s) you touched. All commands assume the setup
above.

**Backend** — `pytest` runs *per package*; there is no aggregate target. Type
checking runs from the workspace root:

```bash
cd backend/core       && uv run pytest
cd backend/api        && uv run pytest
cd backend/scheduler  && uv run pytest
cd backend            && uv run pyright   # type-check (workspace root)
```

**Dashboard:**

```bash
cd frontend/dashboard
npm run lint
npm run typecheck
npm run format:check
npm run test
```

**Mobile:**

```bash
cd frontend/mobile
./gradlew testAndroidHostTest
```

Please make sure the relevant suites pass and add or update tests for the
behavior you change.

## Architecture and conventions

Every package follows **Clean Architecture**: source-code dependencies point
only inward, and outer rings reach inner ones through abstract ports. The
shared vocabulary (Entities, Use Cases, Interface Adapters, Frameworks &
Drivers, the Dependency Rule) is defined once in the
[`core` glossary](backend/core/README.md#glossary); the frontend packages
mirror the same intent in their own idioms. New code should respect these
boundaries — keep framework and datastore concerns out of the inner rings.

The dashboard and mobile clients deliberately mirror each other (matching test
names, the shared AIP wire contract, the same auth flow). When you change a
cross-cutting behavior on one side, check whether its counterpart needs the same
change.

## Commit messages

Follow the existing style in the history: `type (scope): subject`, e.g.

```text
fix (core): source App default identifiers from env instead of hardcoding
docs (frontend): add aggregate README mapping the two client packages
```

Common types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`. Keep the
subject in the imperative mood and add a body explaining the *why* when the
change isn't self-evident.

## Pull request process

1. Fork the repository and create a topic branch from `main`.
2. Make your change, with tests and docs updated as needed.
3. Run the checks for the areas you touched (above).
4. Open a pull request against `main` describing the change and its motivation.
   Link any related issue.
5. Address review feedback. A maintainer will merge once it's approved and CI
   is green.

## Licensing of contributions

OpenWellness is licensed under the [Apache License 2.0](LICENSE). Under
Section 5 of that license, any contribution you intentionally submit for
inclusion in the project is provided under the same Apache-2.0 terms, unless you
explicitly state otherwise. In other words, the license you receive the code
under is the license under which you contribute back ("inbound = outbound"). You
are responsible for ensuring you have the right to submit the contribution.

Please do not add code that introduces dependencies under licenses incompatible
with Apache-2.0 (e.g. GPL/AGPL) without discussing it first in an issue.

## Code of conduct

Please be respectful and constructive in all project interactions. Harassment
or abusive behavior is not tolerated.

## Questions

If anything here is unclear, open an issue — improving these instructions is
itself a welcome contribution.
