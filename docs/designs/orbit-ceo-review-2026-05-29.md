# CEO Review: Orbit

Reviewed on 2026-05-29
Mode: SELECTIVE_EXPANSION
Input: `/Users/jaibhasin/.gstack/projects/orbit-gmeet/jaibhasin-main-design-20260529-000000.md`

## Executive View

The current office-hours doc makes the right near-term call: narrow hard and prove a repeated habit before claiming a company-memory platform. That said, the best version of Orbit is not "another meeting notetaker." The 10-star opportunity is a trusted operating memory layer that turns volatile coordination into searchable institutional truth.

The constraint is timing. The repo does not yet show the demand, distribution, or moat required to support the full platform story today. The correct CEO move is to preserve the narrow wedge while shaping the product so that, if it works, it naturally expands into a larger category.

## What Changed In The Market

As of 2026, AI meeting assistants are already mainstream enough that basic notes and summaries are table stakes. TechTarget cited Metrigy research saying almost 40% of surveyed companies had already deployed AI meeting assistants and 42% planned rollout within the next year. Google also said more than 110 million users had tried Google Meet's "Take Notes for Me" feature by April 23, 2026. Separately, the Meet ecosystem appears to be tightening around bot risk, with multiple 2026 market analyses describing third-party notetaker bots as warned on or denied by default in some environments.

Implication: Orbit cannot win by being "AI that joins meetings and remembers stuff." Incumbents and the platform itself already cover generic summarization. A browser-joined bot is also structurally fragile as a core product primitive.

## Premise Challenge

### Premise 1: Meeting chat is enough
This is the biggest weak point. Many important meetings produce little or no chat. If Orbit only sees chat, it may miss the exact content users care about.

Verdict: weak as a universal premise, possibly strong in specific workflows.

### Premise 2: WhatsApp is a good control plane
This may work for founder-led pilots, ops-heavy teams, and certain geographies. It is not an obvious default interface for mainstream B2B knowledge workflows.

Verdict: useful bootstrap, unlikely durable front door.

### Premise 3: The product should start broad
The current design doc correctly rejects this. Market proof is too early and category competition is too mature.

Verdict: reject.

### Premise 4: A meeting bot is an acceptable primitive
This is getting weaker, not stronger. Trust, compliance, and platform policy are all moving against visible third-party bots.

Verdict: acceptable for prototyping, dangerous as long-term platform dependency.

## The 10-Star Product

The most ambitious credible version of Orbit is:

"The system of record for what your company decided, why it decided it, and what changed next."

That is larger than meeting notes and more valuable than chat recall. It connects:
- meeting evidence,
- follow-up actions,
- linked docs and tickets,
- source-attributed answers,
- continuity across time rather than per-call summaries.

This is not a horizontal "knowledge base." It is operational memory with provenance.

## Where The Current Wedge Is Right

The office-hours doc is directionally correct on four points:
- It narrows to one repeated user behavior: recall.
- It forces real pilot demand before architecture sprawl.
- It acknowledges that Orbit competes with "good enough" workflows, not a blank slate.
- It centers trust and provenance, which is one of the few plausible paths to defensibility.

## Critical Gaps

### 1. The wedge is still slightly too generic
"Ask what happened in our Google Meet workflow" is better than the broad platform vision, but still generic enough to collide with every meeting assistant in the market.

Fix: choose a specific workflow where missing memory is expensive.
Examples:
- hiring debriefs,
- customer call follow-up,
- founder/staff decision tracking,
- cross-functional launch meetings.

### 2. The product thesis depends on a weak sensor
Meet chat alone is not robust enough to support the bigger promise.

Fix: frame current chat capture as an initial signal, not the core moat. The long-term roadmap should bias toward sanctioned or lower-friction capture paths.

### 3. The control plane and value plane are mixed together
WhatsApp is currently both command surface and user experience story. That risks overfitting the product to a bootstrap interface.

Fix: treat WhatsApp as a transport layer for pilots, not a defining part of the product thesis.

### 4. There is no explicit "why now" beyond AI enthusiasm
The design doc explains the problem but not the timing advantage.

Fix: the best "why now" is a combination of three shifts:
- AI query interfaces are finally good enough for natural recall.
- organizations increasingly expect searchable memory after every meeting.
- incumbent note-taking products still leave follow-through and cross-meeting provenance fragmented.

## Selective Expansion Opportunities

These are the expansions worth keeping in view without expanding the current build scope yet.

### Expansion A: Narrow to a high-pain vertical workflow
Best candidate: founder/staff and cross-functional decision meetings, where remembering rationale matters more than perfect transcript coverage.

Why this matters:
- stronger pain,
- smaller surface area,
- clearer ROI,
- easier trust calibration.

### Expansion B: Sell provenance, not summarization
The answer should not just be "what happened?" It should be "what happened, according to which meeting, who said it, and what happened after?"

Why this matters:
- this is where generic meeting assistants are still weaker,
- this is closer to system-of-record behavior,
- it creates a sharper wedge than notes alone.

### Expansion C: Move from meeting memory to decision memory
The true product category may be "decision infrastructure," not "meeting assistant."

Why this matters:
- it’s a more strategic budget line,
- it reduces head-to-head competition with commodity notetakers,
- it aligns with the long-term product vision without demanding full scope now.

### Expansion D: Reduce reliance on visible bots
Orbit should eventually prefer sanctioned APIs, platform-native capture, or user-side capture where possible.

Why this matters:
- better trust posture,
- lower policy risk,
- stronger enterprise viability.

## Recommended Scope For The Next 30 Days

Keep current implementation scope narrow, but revise the company story.

Build and validate:
- one workflow,
- one user type,
- one repeated recall moment,
- one trust pattern with source evidence.

Do not build yet:
- multi-surface company memory,
- broad workflow automation,
- generalized company operating system positioning,
- heavy expansion into docs, email, and Slack before the wedge is proven.

## CEO Recommendation

The right strategic posture is:

"Act like you are building decision memory. Ship like you are testing post-meeting recall."

That gives you ambition without self-deception. If the recall wedge works, Orbit can grow into a real category. If it fails, you will learn quickly without burning months on platform breadth.

## Concrete Next Moves

1. Pick one workflow where missing memory is costly and frequent.
2. Rewrite the product narrative around provenance and decision recall, not generic company knowledge.
3. Instrument pilot usage around repeat questions, answer trust, and whether answers change behavior.
4. Explicitly track how often chat-only context is insufficient.
5. Start a capture-strategy roadmap that assumes browser bot joining is not the end state.

## Decision

Keep the office-hours wedge, but sharpen it further. The broad vision is worth preserving as a north star, not as current scope.

## Sources

- TechTarget, "8 AI meeting assistants to consider in 2026" (published February 6, 2026): https://www.techtarget.com/searchunifiedcommunications/tip/AI-meeting-assistants-to-consider
- Tom's Guide coverage of Google Meet note-taking expansion, citing Google's announcement (published April 23, 2026): https://www.tomsguide.com/ai/google-meets-ai-note-taking-feature-can-now-summarize-your-in-person-meetings-heres-how-it-works
- Notes.so market analysis on Google Meet bot-policy changes (updated April 2026): https://notes.so/ai-note-taker-google-meet/
