# Pre-flight checklist

Run BEFORE writing the hypothesis. Each item resolves a confound that has bitten prior experiments. Sourced from `experiments/_template/README.md` and the retrospectives that hardened it.

## 1. Working tree is clean for the files the experiment depends on

`git status --short` and audit. If a relevant source file shows `M`, either commit the change, `git checkout HEAD -- <file>` to reset, or explicitly document it as part of Setup (it's now a confound).

*Source:* retrospective 002 -- working-tree drift cost ~5 min of false-bug investigation.

## 2. Stack is in a known state

If the experiment requires a fresh stack: `pnpm harness destroy` first. If it requires baseline traffic, seed it before measuring. Don't measure against a stack whose state evolved across other experiments.

## 3. Artifacts directory is clean for the iso_key under test

Pre-existing `.harness/artifacts/<iso>/` files from prior runs can confuse subagents that read them expecting fresh state.

*Source:* retrospective 003 -- reviewer noted REPORT.md from a prior run.

## 4. Tool versions documented

If the experiment depends on a specific version of a tool (Playwright, RTK, ffmpeg, Rust, Node), note the version in the Setup section so the experiment is reproducible across time.

## 5. Conventions cited; marketing claims separated

If your hypothesis references a marketing claim from a tool's docs ("saves 60-90% tokens"), treat that as a WORKLOAD average and predict your specific commands separately. Aggregate ≠ per-command.

*Source:* retrospective 005 -- RTK marketing aggregate ≠ per-command.

## 6. Baseline captured before any change

Without a recorded baseline, "after" numbers are anecdotes. The baseline goes into `runs/baseline-*` and is referenced from `results.md` as the comparison anchor. This is the harness-lab analog of the AI-pilot "before/after snapshot" pattern: the baseline is what lets impact be measured, not assumed.
