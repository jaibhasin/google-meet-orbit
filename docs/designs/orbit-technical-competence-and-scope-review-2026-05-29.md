# Technical Competence And Scope Review: Orbit

Reviewed on 2026-05-29
Skills used: health, plan-eng-review
Repo: jaibhasin/google-meet-orbit
Branch: main

Historical snapshot note:
This document captures repo state as of 2026-05-29. Some statements below are no longer current (for example CI/workflow presence and command-handler architecture).

## Executive Assessment

Orbit is technically competent for an early prototype. The repo shows real system thinking: a working WhatsApp control plane, isolated Google Meet automation, a clear memory boundary, Postgres + pgvector persistence, and tests around the highest-value service paths.

It is not yet technically competent as a pilot-ready product. The gaps are operational: reproducibility, CI, observability, integration testing, dependency pinning, privacy controls, and resilience around browser automation. The current engineering quality is best described as "credible prototype, not reliable service."

Recommended next repo scope:

> Make Orbit a reliable, instrumented, single-workflow pilot system for meeting/decision recall with provenance.

Do not expand the repo into Slack, email, docs, dashboards, multi-tenancy, or a broad company operating layer until this pilot scope is stable.

## Health Result

Commands run:

```bash
.venv-browser-use/bin/python -m unittest discover -s tests
.venv-browser-use/bin/python -m py_compile orbit/core.py orbit/meet.py orbit/meet_types.py orbit/memory.py orbit/postgres_memory.py orbit/whatsapp_app.py orbit/whatsapp_service.py
.venv-browser-use/bin/python -m pip check
```

Result:

- Unit tests: PASS, 7 tests.
- Compile check: PASS.
- Dependency consistency: PASS, no broken installed requirements.
- Python runtime: 3.12.0.

Health score: 6.5/10.

Why not higher:

- No CI workflow exists.
- No lint/type gate exists.
- Only Playwright is pinned in `requirements.txt`; core runtime dependencies are floating.
- Tests cover service logic but not real database, webhook auth, browser session behavior, or end-to-end meeting flows.
- Observability is print/log based, not structured or metric-driven.

## Strong Engineering Signals

### 1. Good module boundaries

The repo separates the main concerns cleanly:

- `orbit/meet.py`: Google Meet automation and chat capture.
- `orbit/whatsapp_service.py`: WhatsApp command routing and session orchestration.
- `orbit/memory.py`: memory service interface.
- `orbit/postgres_memory.py`: Postgres + pgvector implementation.
- `orbit/whatsapp_app.py`: FastAPI boundary.

The memory interface in `orbit/memory.py` is the strongest architecture decision. It lets the product change memory storage and retrieval without rewriting the Meet or WhatsApp layers.

### 2. Sensible async orchestration

`OrbitWhatsAppService` keeps active meeting state behind an `asyncio.Lock`, deduplicates meetings by meeting code, and enforces a configured concurrency cap. See `orbit/whatsapp_service.py:89`, `orbit/whatsapp_service.py:161`, and `orbit/whatsapp_service.py:165`.

This is enough discipline for a prototype that launches long-running browser tasks from a webhook.

### 3. Product constraints are encoded in prompts and behavior

The Meet automation task explicitly tells the browser agent not to bypass sign-in, host approval, guest restrictions, or Google security controls. See `orbit/meet.py:35`.

The answering prompts also state that Orbit should not claim access to audio or transcript content. See `orbit/whatsapp_service.py:300` and `orbit/whatsapp_service.py:362`.

That matters because the product's trust boundary is central to whether it can be piloted.

### 4. Memory persistence is real, not fake demo state

`PostgresMemoryService` creates session, message, and vector chunk tables, records raw chat messages, and indexes memory chunks at finalization. See `orbit/postgres_memory.py:59`, `orbit/postgres_memory.py:124`, and `orbit/postgres_memory.py:155`.

This is a meaningful foundation for provenance-backed recall.

## Technical Gaps

### 1. Reproducibility is weak

`requirements.txt` pins only `playwright==1.54.0`; `browser-use`, `fastapi`, `uvicorn`, `twilio`, `openai`, and `psycopg` are floating. See `requirements.txt:1`.

Risk:

- A fresh install can behave differently tomorrow.
- Browser automation and OpenAI SDK behavior can shift without a code change.
- Debugging pilot failures becomes harder because the runtime is not reproducible.

Recommendation:

- Pin direct dependencies.
- Add a lockfile strategy, preferably `uv.lock` or fully pinned `requirements.txt`.
- Record the tested Python version and Playwright browser version.

### 2. No CI or quality gate

There is no `.github/workflows` directory. The repo depends on manual README commands.

Risk:

- Basic regressions can land unnoticed.
- New contributors have no executable definition of "healthy."

Recommendation:

- Add a CI workflow that runs unit tests, py_compile, pip check, and a linter.
- Add a minimal type checker once annotations stabilize.

### 3. Browser automation is the least reliable layer and has the least test coverage

Most of `orbit/meet.py` is DOM probing, keyboard fallback, and page-state classification. This is inherently fragile. The repo has a small unit test for Orbit-authored message detection, but no fixture-driven tests for the selectors and state classifiers.

Risk:

- Google Meet UI changes can silently break capture.
- The product can appear to work while missing chat or misclassifying join state.

Recommendation:

- Extract DOM-evaluation scripts into named functions with test fixtures.
- Add saved HTML fixtures for pre-join, joined, waiting, denied, blocked, chat-open, and chat-closed states.
- Add a fake page adapter so tests can exercise `get_meeting_status`, `open_chat_panel`, and message collection logic without a real Meet session.

### 4. Observability is too thin for pilots

The code logs useful status strings, but there are no structured events, counters, session summaries, or failure categories beyond in-memory state and console logs. See `orbit/core.py:51` and broad status emission in `orbit/meet.py:105`.

Risk:

- You will not know whether pilots fail because of join approval, UI drift, sparse chat, OpenAI errors, Twilio delivery, memory indexing, or user non-use.

Recommendation:

- Add a `SessionEvent` model and append structured JSONL events in `debug/` for now.
- Track: join outcome, chat panel outcome, messages captured, mentions answered, memory chunks indexed, model failures, Twilio send failures, and final session duration.
- Later, move the same event model into Postgres.

### 5. General Q&A fallback can dilute the product promise

When memory is unavailable or insufficient, normal WhatsApp questions fall back to a general assistant answer. See `orbit/whatsapp_service.py:381` and `orbit/whatsapp_service.py:401`.

Risk:

- Users may confuse generic model answers with company-memory answers.
- Pilot metrics can overstate value because Orbit still replies even when memory failed.

Recommendation:

- Add an explicit response mode: `memory_answer`, `memory_insufficient`, or `general_answer`.
- In pilot mode, prefer saying "I do not have company context for that yet" over answering generically.
- Measure memory answer success separately from generic answer success.

### 6. Database setup is convenient but not migration-safe

`PostgresMemoryService.ensure_ready()` creates tables directly at runtime. See `orbit/postgres_memory.py:59`.

Risk:

- Fine for v1 local development, but not safe for production schema changes.
- Hard to review schema evolution.

Recommendation:

- Keep auto-create for local dev.
- Add explicit SQL migrations under `migrations/`.
- Add a test that validates a clean database can initialize and answer a simple retrieval query.

### 7. Webhook security is minimal

Inbound authorization is based on `From` matching `TWILIO_ALLOWED_FROM`. See `orbit/whatsapp_service.py:104`.

Risk:

- The app is not validating Twilio request signatures at the FastAPI boundary.
- For a public ngrok webhook, sender filtering is useful but incomplete.

Recommendation:

- Validate Twilio signatures in `orbit/whatsapp_app.py`.
- Test rejected signatures and wrong senders.
- Keep `TWILIO_ALLOWED_FROM` as a second authorization layer.

## Recommended Repo Scope

### Scope In

The repo should become excellent at:

- Joining an authorized Google Meet session.
- Capturing visible meeting chat reliably.
- Recording structured session evidence.
- Answering from captured meeting memory with source labels.
- Reporting clearly when it lacks enough context.
- Supporting a concierge pilot for one workflow.

### Scope Out

Keep these out until the pilot scope is proven:

- Slack ingestion.
- Email ingestion.
- Document ingestion.
- Multi-company tenancy.
- Admin dashboards.
- Billing.
- Full auth product.
- General company operating system positioning.

### Scope Rename

The README currently frames Orbit as "an AI layer for company knowledge" and "a queryable company operating system." That is aspirational. The repo should frame its actual current scope more tightly:

> Orbit is a Google Meet and WhatsApp pilot for source-backed meeting recall.

The broader "decision memory" vision can stay in `docs/designs`, not as the top-level product claim.

## Proposed Milestones

### Milestone 1: Engineering Baseline

Goal: make the repo reproducible and reviewable.

- Pin dependencies and add a lockfile.
- Add CI for tests, compile check, and pip check.
- Add linting and formatting configuration.
- Add `.env.example` validation.

### Milestone 2: Pilot Observability

Goal: know why every session succeeds or fails.

- Add structured session events.
- Persist session summaries.
- Add explicit answer modes.
- Add pilot metrics: sessions started, sessions joined, chat opened, messages captured, questions asked, answers with sources, insufficient-context responses.

### Milestone 3: Browser Reliability Harness

Goal: make Meet UI drift detectable.

- Extract DOM classifiers.
- Add HTML fixtures.
- Test join-state classification.
- Test chat-panel detection.
- Test chat message parsing and dedupe.

### Milestone 4: Memory Quality

Goal: prove that recall is useful and trustworthy.

- Add integration tests against local pgvector.
- Add source provenance to answer objects.
- Add retrieval thresholding.
- Add evaluation fixtures for "answerable" vs "not answerable" questions.

### Milestone 5: Pilot Packaging

Goal: run the system for real users without manual babysitting.

- Add deployment docs.
- Add Twilio signature validation.
- Add operational runbook.
- Add privacy/consent notes.
- Add pilot onboarding checklist.

## Technical Competence Verdict

Current repo competence: 6.5/10.

The code is materially better than a throwaway demo. The boundaries are sensible, the async service shape is workable, and the memory layer is pointed in the right direction. The main issue is that the repo has not yet earned operational trust.

Target for pilot readiness: 8/10.

To get there, focus less on new features and more on reproducibility, instrumentation, test realism, and provenance. Those are the engineering moves that directly support the improved product scope from the CEO review: decision recall with evidence, not broad company memory.
