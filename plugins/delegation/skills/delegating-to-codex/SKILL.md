---
name: delegating-to-codex
description: Use when authoring a non-interactive `codex exec` invocation or deciding whether to hand a task from Claude Code to OpenAI Codex CLI. Provides the validated autonomous invocation, the sandbox/approval ladder, the JSON event schema for triage, a when-to-delegate framework, failure modes, and one empirical trial. Trigger phrases include "delegate to codex", "codex exec", "hand this to codex", "run codex", "codex --full-auto", "ask codex", "second opinion from codex", "have codex use a skill", "run a skill in codex", "codex pr-review". Do NOT use for interactive pair-programming in the Codex TUI, or for trivial CRUD/UI/first-attempt tasks where a model handoff adds no value. For autonomous Claude (not Codex), use `delegating-to-claude-p` instead.
placement: "Domain skill. Lives at `plugins/delegation/skills/delegating-to-codex/` in agentic-primitives. NOT in `.claude/skills/`; that scope is for meta skills."
---

# Delegating to `codex exec`

## Purpose

Invoke this skill when you are about to dispatch a task from Claude Code to the
OpenAI Codex CLI in non-interactive mode, or when deciding whether a task is
worth a cross-model handoff at all. It is the Codex peer of
[`delegating-to-claude-p`](../delegating-to-claude-p/SKILL.md): both dispatch
work to an autonomous agent one-shot; the steering surface and the footguns
differ, and this skill documents Codex's.

The single most important difference from `claude -p`: **Codex has no built-in
cost cap.** `claude -p` enforces `--max-budget-usd`; `codex exec` has no
equivalent. The only hard bound is an external one (see the budget section).

## The validated invocation

```sh
codex exec -s workspace-write \
  --json \
  -o ./codex-last.txt \
  -C /path/to/project \
  "$TASK_PROMPT" \
  < /dev/null
```

**`< /dev/null` is not optional.** `codex exec` reads stdin *in addition to* the
prompt argument. Launched from any context whose stdin never reaches EOF (a
background shell, a CI step, an agent harness), it prints
`Reading additional input from stdin...` and **hangs forever** - no events, no
error, no tokens consumed, just a wedged process until something kills it.
Omitting it is the single most common way these invocations fail.

> **Flag drift.** Older releases spelled the autonomy mode `--full-auto`. That
> flag was **removed** by `codex-cli 0.147.0` — passing it now aborts the run
> with `error: unexpected argument '--full-auto'`. Use `-s workspace-write`
> instead, as above. `codex exec --help | grep full-auto` returning nothing is
> the quick check. Everything else in this recipe (`--json`, `-o`, `-C`,
> `--ephemeral`, `--add-dir`, `--output-schema`, `--skip-git-repo-check`) is
> unchanged and verified present on 0.147.0.

### Per-flag rationale

- **`-s workspace-write` / `--sandbox workspace-write`** — the realistic
  autonomy mode: Codex may write files and run commands inside the workspace
  sandbox, and `codex exec` does not prompt. This is the Codex analog of
  `claude -p --permission-mode bypassPermissions`, but narrower — it does *not*
  grant network access or writes outside the workspace. (`--ask-for-approval`
  is no longer an `exec` flag; `--approve-for-me` routes approval requests
  through automatic review using the same sandbox.)
- **`--json`** — emit the run as a JSONL event stream on stdout. Without it the
  transcript is prose and unscoreable, exactly as `claude -p` text mode is. See
  the event-schema section for what it carries.
- **`-o <file>` / `--output-last-message <file>`** — capture the agent's final
  message to a file, so a wrapper can read the conclusion without parsing the
  whole stream.
- **`-C <dir>` / `--cd <dir>`** — set the working root explicitly. Safer than
  relying on the caller's CWD when invoked from a wrapper.
- **`< /dev/null`** - close stdin so Codex does not block waiting for input it
  will never receive. See the warning above; this is the highest-frequency
  failure mode in practice.
- Useful additions: **`-m <model>`** to pin the model (otherwise the config
  default is used), **`--output-schema <file>`** to force a structured final
  response, **`--skip-git-repo-check`** to run outside a git repo.
- **`--ephemeral`** - **omitted deliberately**, for the same reason
  `--no-session-persistence` is omitted from the `claude -p` recipe. It
  persists no session, so the delegated run leaves no on-disk rollout for a
  session-store sweep to collect. Persistence is a property of DELEGATION, not
  of one CLI: suppressing it on either side loses the same thing.
  The narrow case where it is right is explicitly throwaway local work, where
  you intend not to keep a resumable transcript. If a run persists something
  you did not want kept, fix that in the session-store or `$HOME`
  configuration; do not reach for this flag to work around it.

## The sandbox / approval ladder

Pick the least privilege that lets the task finish. Granularity Codex exposes:

| Setting | Grants | Use when |
|---|---|---|
| `-s read-only` | Read files; no writes, no commands | Analysis / review only |
| `-s workspace-write` | Write + run inside the workspace; no network | The default for fmt/test/edit loops |
| `-s danger-full-access` | Writes anywhere, network | Almost never; prefer adding `--add-dir` to widen scope precisely |
| `--dangerously-bypass-approvals-and-sandbox` | No sandbox, no prompts | ONLY when the host is already externally sandboxed (CI container, disposable VM) |

Reach for `--dangerously-bypass-approvals-and-sandbox` only in an
already-isolated host. On a developer machine it is the equivalent of handing
out an unsandboxed shell.

## Budget: there is no built-in cap

`codex exec` reports token `usage` only in the final `turn.completed` event —
*after* the work is done — and surfaces no USD figure under ChatGPT-subscription
auth. There is no `--max-budget-usd`. Therefore the bound must come from outside
the process:

```sh
# macOS lacks `timeout`; install coreutils for `gtimeout`, or use a CI step limit
gtimeout 600 codex exec -s workspace-write --json -o ./codex-last.txt "$TASK_PROMPT" < /dev/null
```

Treat an external wall-clock bound (`gtimeout`, a CI job timeout, a wrapper
watchdog) as mandatory for unattended runs. A wedged Codex run will otherwise
consume tokens until it finishes or is killed by hand.

## `codex exec review` — the built-in diff reviewer

0.147.0 ships a `review` subcommand that scopes itself to a diff instead of
needing you to describe one:

```sh
codex exec review --base main --json -o ./review.md < /dev/null
codex exec review --uncommitted --json -o ./review.md < /dev/null
codex exec review --commit <SHA> --json -o ./review.md < /dev/null
```

**The catch:** `--base` / `--uncommitted` / `--commit` are **mutually exclusive
with `[PROMPT]`**. Passing both fails:

```
error: the argument '--base <BRANCH>' cannot be used with '[PROMPT]'
```

So you get either Codex's stock review rubric *or* your own instructions, never
both. It also exposes no `-s` or `-C`, so it is inherently read-only and runs
against the current directory.

Choose accordingly:

| Want | Use |
|---|---|
| A quick review with Codex's own rubric | `codex exec review --base <branch>` |
| A review steered at specific risks, or one that runs the test suite to verify its own claims | plain `codex exec -s workspace-write` with a prompt telling it to `git diff <base>...HEAD` |

For the steered form, add an explicit **"do NOT modify any tracked file"** to the
prompt — `workspace-write` permits edits, and you want the review read-only while
still letting Codex run tests. Confirm with `git status` afterwards; treat a dirty
tree as a failed review run, not a bonus.

## What `--json` emits (for triage)

The stream is JSONL, one event per line. Event shapes observed:

- `thread.started` — `{thread_id}` for the run.
- `turn.started` — a turn begins.
- `item.started` / `item.completed` — each agent action. `item.type` is one of
  `agent_message`, `command_execution` (carries `command`, `aggregated_output`,
  `exit_code`, `status`), or `file_change`.
- `turn.completed` — carries `usage` (`input_tokens`, `cached_input_tokens`,
  `output_tokens`, `reasoning_output_tokens`).

To triage a run: filter `command_execution` items for non-zero `exit_code` to
see what Codex tried and where it stumbled; read the final `agent_message` (or
the `-o` file) for the conclusion; read `turn.completed.usage` for token spend.

## When to delegate to Codex

Delegate when a cross-model perspective is likely to help:

- A bug survived **2+ of your own attempts** — a different model may break the
  fixation.
- Logic- or algorithm-heavy backend work with many edge cases.
- You want an independent second implementation to compare against.

Do **not** delegate:

- Trivial CRUD, UI scaffolding, config edits, or first attempts — the handoff
  overhead exceeds the value.
- Tasks needing genuine multi-turn clarification — `codex exec` is one-shot
  (use the interactive Codex TUI, or stay in Claude Code).
- Work that must not run unsandboxed where you cannot grant `workspace-write`.

For autonomous *Claude* rather than Codex, use `delegating-to-claude-p`. The two
are interchangeable dispatch targets; pick Codex specifically when you want a
different model's reasoning.

## Using a Claude skill (e.g. pr-review) with Codex

Codex does **not** auto-dispatch Claude `SKILL.md` plugin skills — it consults no
skills index. To make Codex follow a specific skill, **inject the skill's content
and name it in the prompt.** Two mechanisms:

- **stdin (best for one-shot)** — pipe the skill body in; Codex appends it as a
  `<stdin>` block. This is the one case where you do NOT redirect from
  `/dev/null`: the pipe supplies stdin and then closes it, which is exactly what
  Codex is waiting for. Name the skill and the task in the prompt arg:
  ```sh
  cat path/to/skills/review/SKILL.md | codex exec -s workspace-write --json \
    -o ./review.md -C /path/to/project \
    "Apply the review skill provided on stdin to review this repo against plan.md. Follow its Report format exactly. Read-only: do not modify files."
  ```
- **`AGENTS.md` (best when reused across runs)** — drop the skill content into an
  `AGENTS.md` at the workspace root; Codex auto-loads it. Still name the skill's
  action in the prompt — like `claude -p`, a one-shot agent binds to explicit
  prompt verbs, not to passively-present docs.

Skills that mandate a **structured output contract** (a pr-review rubric, a
verdict format) transfer especially well: the contract is self-describing, so
Codex reproduces it faithfully. Inject the *whole* skill body, not a paraphrase —
the format section is what steers the output. See Trial T2.

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| Hangs forever, zero events, `Reading additional input from stdin...` | stdin never reaches EOF and Codex waits on it | Add `< /dev/null`. Detect it by the `--json` stream file stalling at ~39 bytes, the length of that banner; a healthy run passes 100KB within a minute |
| Run consumes tokens indefinitely | No built-in budget cap | Wrap in `gtimeout`/CI timeout; `usage` is only reported post-hoc |
| Unscoreable prose transcript | Default output is not JSONL | Add `--json`; read `-o` file for the conclusion |
| `error: unexpected argument '--full-auto'` | Flag removed by 0.147.0 | Use `-s workspace-write`; re-check with `codex exec --help` |
| `--base <BRANCH> cannot be used with [PROMPT]` | `codex exec review` takes its built-in rubric OR custom instructions, not both | Pick one: `review --base` for the stock rubric, or plain `codex exec` with your own prompt |
| Cannot write files / run commands | Default sandbox is `read-only` | Set `-s workspace-write` explicitly |
| Refuses to run | Not inside a git repo | Add `--skip-git-repo-check` |
| Writes need a dir outside the workspace | `workspace-write` is workspace-scoped | Add `--add-dir <dir>` rather than escalating to `danger-full-access` |
| Command fails on a quirky local env (e.g. `pytest` exit 127 under pyenv) | Sandbox shell inherits host PATH quirks | Under `-s workspace-write` Codex often self-recovers (Trial T1); for wrappers, pre-set env via `-c shell_environment_policy...` |

## Trial T1 — empirical reference

A real workspace-write run, recorded 2026-06-08 on `codex-cli 0.137.0`, where
the mode was still spelled `--full-auto`. The invocation below is left as it was
actually executed; on 0.147.0+ substitute `-s workspace-write`.

- **Task**: add `is_palindrome(s)` + a 3-case `pytest` file to a fresh repo, run
  the tests.
- **Invocation**: `codex exec --full-auto --json -o <file> "<task>"` (model =
  config default).
- **Result**: exit 0, **44s** wall-clock, **1 turn**, 18 items
  (8 `agent_message`, 8 `command_execution`, 2 `file_change`), tests passed.
- **Usage** (`turn.completed`): input 237,408 tokens (202,112 cached, ~85% cache
  hit), output 1,139, reasoning 134. No USD figure surfaced under ChatGPT auth.
- **Autonomous recovery**: the first `pytest` call failed (`exit_code 127` —
  pyenv shadowing the binary); Codex retried with
  `PYENV_VERSION=3.12.0 python -m pytest` and got `3 passed`. The `--json`
  stream captured both the failed and the recovered command, which is exactly
  the signal you triage on.

This is a single data point, not a universal claim. Add your own paired trials
before quoting costs or wall-clock for a different task shape.

## Trial T2 — does an injected skill actually steer Codex?

A paired run recorded 2026-06-08, testing the injection mechanism above. Target:
a scratch repo with a 2-milestone `plan.md` whose milestone 2 (`truncate`) was
deliberately left unimplemented, so a correct review must flag the omission.

- **Run A (skill on stdin)**: piped `sdlc/skills/review/SKILL.md`; the prompt
  named it and asked for its Report format. Codex reproduced the skill's exact
  contract — `## Implementation Review`, the Milestone Status table, ⚠️ Omissions
  (Blockers), and the `❌ BLOCKERS FOUND` verdict — correctly flagged the missing
  milestone, and obeyed the skill's read-only/static-review process. 35s; 82,277
  input tokens (87% cached) / 1,406 output.
- **Run B (baseline, no skill)**: same task, generic "review against plan.md".
  Codex returned generic `**Findings**` prose — it found the same facts, but with
  **none** of the skill's structure, and it ran the tests on its own (a different
  process). 45s; 131,776 input / 1,501 output.
- **Adherence check**: all four signature markers
  (`## Implementation Review`, `### Milestone Status`, `Omissions (Blockers)`,
  `BLOCKERS FOUND`) were present in A and absent in B.

Takeaway: injecting a skill and naming it in the prompt **does** steer Codex's
output format and process — but the content must be supplied, since Codex won't
auto-dispatch it. Finding *fidelity* was similar in both runs because the bug was
obvious; skills earn their keep on **structure and process discipline**, which is
exactly what a pr-review skill enforces.

## References

- **`delegating-to-claude-p`** (sibling skill) — the autonomous-Claude dispatch
  recipe and its empirically-validated flag set; read it for the side-by-side on
  what steers a one-shot agent.
- **`experiments:running-experiments`** — the discipline for designing a paired
  trial to extend or contest Trial T1.
- Codex CLI flags here are described by behavior to stay valid across releases;
  verified against `codex-cli 0.137.0` on 2026-06-08, re-verified against
  `0.147.0` on 2026-08-17 (which removed `--full-auto` and added
  `codex exec review`). Re-run `codex exec --help` to confirm flag availability
  in your installed version — this surface has already drifted once between
  documented releases, so treat the check as part of the recipe rather than an
  optional precaution.
