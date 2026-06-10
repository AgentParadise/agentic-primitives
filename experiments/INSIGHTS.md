# Insights for Effective Agentic Engineering

Insights are grounded in `EXP-01` through `EXP-06`, `FRICTION-*`, and `EXP-05-review-codex.md`.

## 1) Drive TUIs as command pipelines
- **Claim:** Interactive CLIs can be treated as reliable transport endpoints via tmux key injection and pane capture.
- **Evidence pointer:** `EXP-01` and `EXP-05` implement host-driven `tmux send-keys` + `capture-pane` loops; smoke output includes per-agent success markers.
- **So what:** For Syntropic137, standardize a low-level TUI transport layer and avoid per-agent integrations scattered across orchestration.
- **So what for future labs:** Budget repeated probe loops and stable-readiness waits into every new provider from day one.

## 2) Encode per-agent input semantics, do not standardize by hand
- **Claim:** Claude, Codex, and Gemini require different key sequences and submission behavior.
- **Evidence pointer:** `EXP-05` CLI matrix and `EXP-05` driver code (`submit` routines).
- **So what:** Syntropic137 should expose per-agent adapters to keep command layer stable while preserving behavior.
- **So what for future labs:** Add interface tests that lock in first-message quirks for each CLI.

## 3) Multi-signal readiness is mandatory
- **Claim:** One readiness marker is not enough for interactive tools.
- **Evidence pointer:** `EXP-05` readiness section; Claude uses 3 signals, Codex uses working-marker + stable output.
- **So what:** Syntropic137 should model readiness as a logical predicate with redundancy.
- **So what for future labs:** Require negative and positive signals before declaring a session ready.

## 4) Config and mount surfaces are the most common hard failure class
- **Claim:** Most issues are configuration and authentication mount bugs, not core logic bugs.
- **Evidence pointer:** Friction totals in `FRICTION-claude.md`, `FRICTION-codex.md`, `FRICTION-gemini.md`.
- **So what:** Syntropic137 should ship strict validation at container start for mount and token assumptions.
- **So what for future labs:** Keep a machine-readable mount contract per provider.

5) Node/runtime drift directly impacts agent CLI behavior
- **Claim:** Incorrect base runtime can fail provider compatibility even with correct orchestration.
- **Evidence pointer:** `EXP-03` notes Node 18 failure and switch to Node 22 for Gemini.
- **So what:** Syntropic137 should pin runtime versions and capture them in provider manifests.
- **So what for future labs:** Treat runtime image as part of public API and record with reproducibility checks.

## 6) Structured completion results improve recovery quality
- **Claim:** Bare boolean completion states hide retry vs timeout vs failure distinctions.
- **Evidence pointer:** `EXP-05-review-codex.md` M3 and fix to `AwaitResult`.
- **So what:** Syntropic137 should require typed completion payloads (`ready`, `timed_out`, `reason`, timing).
- **So what for future labs:** Make protocol conformance checks assert schema shape, not just truthiness.

## 7) Startup gate enforcement prevents silent breakage
- **Claim:** A success signal at startup must be explicit and enforced before send phase.
- **Evidence pointer:** `EXP-05-review-codex.md` M1; fixed in `interactive_tmux.py`.
- **So what:** Syntropic137 should stop tasks if startup readiness is unproven.
- **So what for future labs:** Add "must be ready" assertions in all provider entrypoints.

## 8) Fresh-agent validation is a first-class requirement
- **Claim:** A clean-room validation pass catches usage gaps missed by insiders.
- **Evidence pointer:** `EXP-06` report and 4 doc gaps found/fixed.
- **So what:** Syntropic137 should require at least one fresh-agent validation run before release.
- **So what for future labs:** Include "new user onboarding" script/test in acceptance criteria.

## 9) Contradictory assumptions must be falsified via controlled probes
- **Claim:** Cross-experiment contradictions are expected and should be experimentally resolved.
- **Evidence pointer:** `EXP-05a` auth matrix resolves token-location disagreement on Claude auth files.
- **So what:** Syntropic137 should prefer deterministic A/B probes over hand-wave assumptions.
- **So what for future labs:** Keep matrix experiments for each claim involving auth, file mounts, and startup.

## 10) Consolidated multi-agent containers work and save orchestration overhead
- **Claim:** Claude, Codex, and Gemini can run concurrently in one container with bounded memory.
- **Evidence pointer:** `EXP-04` and `EXP-04b` results, `EXP-04` idle RSS section.
- **So what:** Syntropic137 can optimize hardware usage by container-level swarms instead of separate hosts.
- **So what for future labs:** Expand mixed-agent workflow tests before introducing extra host-level complexity.

## 11) Documentation is operational infrastructure
- **Claim:** Missing usage docs materially lower autonomous reproducibility.
- **Evidence pointer:** `EXP-06` G1-G4 doc gaps and fixes.
- **So what:** Syntropic137 should treat README coverage as a required artifact beside code.
- **So what for future labs:** Add explicit doc-gap checks in CI and acceptance.

## 12) Error handling should separate policy from mechanism
- **Claim:** The provider implementation is safer once protocol adapters and startup policies are explicit.
- **Evidence pointer:** `EXP-05-review-codex.md` M1/M2/M3 and post-fix behavior.
- **So what:** Syntropic137 should isolate transport, session lifecycle, and result policy layers.
- **So what for future labs:** Build provider interfaces with explicit errors and protocol adapters at design time.

