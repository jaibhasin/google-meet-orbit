# Decision: Deepgram STT For Orbit

Reviewed on 2026-05-29
Skills used: office-hours, plan-ceo-review, plan-eng-review

## Implementation Note

This document is a historical pre-implementation decision review. The repo now includes a local live STT path using a Manifest V3 Chrome extension, Orbit-owned Deepgram streaming, optional Google Meet caption speaker attribution, and transcript memory storage. See [`../live-stt.md`](../live-stt.md) for the current implementation and local setup.

## Decision

Do not pause the baseline reliability work to build full STT now.

Do run a narrow Deepgram STT spike after the first engineering-baseline tasks are in place. The spike should answer one question:

> Can Orbit capture meeting speech with enough reliability, consent clarity, and provenance to materially improve meeting recall beyond chat-only memory?

## Recommendation

Sequence this as:

1. Add the baseline repo work first: dependency pinning, CI, structured session events, and explicit answer modes.
2. Run a 2-3 day Deepgram spike behind a feature flag.
3. Decide whether STT becomes part of the pilot only after measuring transcription quality, capture reliability, latency, consent burden, and storage/privacy implications.

## Why Deepgram Is Plausible

Deepgram is a credible fit because its API supports live streaming transcription over WebSocket and offers transcription features relevant to meetings, including diarization and formatting options. That makes it better aligned with live meeting capture than a purely batch transcription flow.

Official docs reviewed:

- Deepgram streaming listen API: https://developers.deepgram.com/reference/speech-to-text/listen-streaming
- Deepgram prerecorded transcription API: https://developers.deepgram.com/reference/speech-to-text/transcribe
- Google Meet artifacts API guide: https://developers.google.com/workspace/meet/api/guides/artifacts

## CEO Review

### Product upside

STT directly addresses the biggest weakness found in the CEO review: Meet chat alone is a weak sensor. Many meetings have little useful chat, so transcription could make Orbit's recall value much stronger.

### Product risk

STT moves Orbit into the same market as many meeting assistants. If the product becomes "bot records meetings and summarizes them," it loses the sharper positioning around decision memory with provenance.

### Product stance

Use STT to improve evidence quality, not to reposition Orbit as a generic meeting notetaker.

The product promise should remain:

> Source-backed decision recall.

Not:

> AI meeting summaries.

## Engineering Review

### Recommended architecture

Add a source-agnostic transcript boundary rather than wiring Deepgram directly into `orbit/meet.py`.

Suggested modules:

- `orbit/transcript.py`: transcript dataclasses and provider protocol.
- `orbit/deepgram_transcript.py`: Deepgram implementation.
- `orbit/audio_capture.py`: capture adapter if live audio is used.
- `orbit/memory.py`: extend memory service to record transcript segments.

Suggested data model:

- `TranscriptSegment`
- `session_id`
- `meeting_code`
- `speaker`
- `start_ms`
- `end_ms`
- `text`
- `confidence`
- `source_type`
- `source_id`

### Capture options

Option A: official Google Meet artifacts

Use Google Meet transcript artifacts where available. This is likely the most compliant and stable path, but it may not support live answers during the meeting and may depend on Workspace settings, recording/transcript availability, and organizer permissions.

Option B: live audio capture plus Deepgram streaming

This enables live recall and mention handling, but it adds major complexity:

- audio routing from browser/system output,
- participant consent,
- recording disclosure,
- latency and reconnect handling,
- speaker diarization accuracy,
- storage policy,
- local OS and deployment differences.

Option C: manual upload / post-meeting audio

This is the simplest validation path for transcription quality, but it does not prove live meeting automation.

## Recommended Spike

Build Option C first, then Option B only if the value is obvious.

Spike scope:

- Add `TranscriptSegment` and transcript memory ingestion.
- Add a script that transcribes a local audio file with Deepgram.
- Store transcript segments into the existing memory layer.
- Ask questions over the transcript using the existing RAG path.
- Log answer source labels as transcript timestamps.

Do not initially capture live Google Meet audio. That is a separate risk.

## Acceptance Criteria

The spike is worth expanding only if:

- transcript ingestion works end to end into memory,
- answers cite transcript timestamps or segment labels,
- the system can say "not enough evidence" when transcript context is weak,
- the implementation does not couple memory to Deepgram,
- the transcript path has tests independent of live Google Meet,
- there is an explicit consent/disclosure note in README before any live capture.

## What To Do Before The Spike

Minimum prerequisite work:

- Pin dependencies or add a lockfile.
- Add CI for tests and compile checks.
- Add structured session events.
- Add answer mode separation: `memory_answer`, `memory_insufficient`, `general_answer`.

Reason:

STT will multiply the number of failure modes. Without observability, a failed pilot will be impossible to diagnose.

## Final Call

Deepgram is worth trying, but only as a contained transcript-ingestion spike. Do not build live Google Meet STT as the next full feature. First make the repo measurable and reliable enough that the STT experiment produces trustworthy learning.
