# EXP-02: codex-in-tmux-in-docker

## Question
Can an interactive `codex` CLI session running inside a tmux pane inside a Docker container be driven from the host via `docker exec tmux send-keys` and observed via `tmux capture-pane`?

## Hypothesis
1. A containerized `codex` (`@openai/codex`) can authenticate from mounted host credentials (`-v ~/.codex:/root/.codex`) and start interactively.
2. Prompt submission from the host requires a two-step sequence for the first user message.
3. A second prompt can be sent afterward and produces a context-aware follow-up response.
4. Responses are detectable by pane text patterns, making completion programmatically testable.

## Method

### Environment
- Image built locally from a minimal Ubuntu + `tmux` + `node` + `@openai/codex@0.139.0`.
- Runtime config/auth mounted from host: `-v "$tmpdir/.codex:/root/.codex"`.

### Image (reference)
```Dockerfile
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates git tmux nodejs npm && rm -rf /var/lib/apt/lists/*
RUN npm install -g @openai/codex@0.139.0
ENV TERM=xterm-256color
WORKDIR /workspace
CMD ["bash"]
```

### Send / wait / capture recipe

For each run (example below):

```bash
TMPDIR=$(mktemp -d)
cp -a "$HOME/.codex/"* "$TMPDIR/.codex/"

docker run -d --name exp02-codex-host -v "$TMPDIR/.codex:/root/.codex" exp02-codex-image:latest tail -f /dev/null

docker exec exp02-codex-host tmux new-session -d -s codex-session

docker exec exp02-codex-host tmux send-keys -t codex-session "codex --no-alt-screen" C-m
# confirm trust banner appears
sleep 2

docker exec exp02-codex-host tmux send-keys -t codex-session "1" C-m
# close hook-review menu
sleep 1
docker exec exp02-codex-host tmux send-keys -t codex-session Escape
sleep 1

# first message (known gotcha path)
docker exec exp02-codex-host tmux send-keys -t codex-session "What is 2+2?" C-m
sleep 1
# this often does not submit (observed)

docker exec exp02-codex-host tmux send-keys -t codex-session "What is 2+2?" C-j C-m
for i in $(seq 1 30); do
  OUT=$(docker exec exp02-codex-host tmux capture-pane -p -t codex-session | tail -n 120)
  echo "$OUT"
  if echo "$OUT" | rg -q "2 \+ 2 = 4"; then
    break
  fi
  sleep 1
done

# follow-up
# in normal runs this follows same submit sequence

docker exec exp02-codex-host tmux send-keys -t codex-session "Multiply that by 10." C-j C-m
for i in $(seq 1 30); do
  OUT=$(docker exec exp02-codex-host tmux capture-pane -p -t codex-session | tail -n 140)
  echo "$OUT"
  if echo "$OUT" | rg -q "4 × 10 = 40|4 \* 10 = 40"; then
    break
  fi
  sleep 1
done
```

Teardown:
```bash
docker stop exp02-codex-host
docker rm exp02-codex-host
```

## Results (Evidence)

Run 1 (single full successful run):

- Startup/auth:
  - `codex --no-alt-screen` launched and presented trust banner, then proceeded to interactive shell (`gpt-5.5 default · /workspace`).
  - No interactive ChatGPT login prompt appeared; session accepted command flow after trust and used existing mounted credentials.
- First-send behavior:
  - Sending `prompt + C-m` once only placed the prompt text into the pane and left it unsent.
  - Sending the same prompt again with `C-j C-m` transitioned into Working state and submitted.
- Response 1 completion:
  - Text match observed: `• 2 + 2 = 4`
  - Appeared after ~17–22 capture polls in this run.
- Response 2 completion:
  - Text match observed: `• 4 × 10 = 40`
  - Appeared after ~15 capture polls in this run.
- Capturing:
  - `tmux capture-pane -p -t codex-session | tail -n N` reliably retrieved current model output and state.
  - `• Working (...)` marker appeared during generation and resolved by answer text presence.

Observed extras (non-fatal):
- Codex printed MCP warnings (`mcp_agent_mail` connection failure) during startup and operation.
- Hook review screen appears once at startup; must be dismissed with `Esc` before submitting prompts.

## Conclusions
- `codex` is controllable from host via tmux send/capture in this repository context.
- The first user-submit gotcha is real and must be handled explicitly.
- Back-and-forth interactive context works once first-submit handling is followed.

## Difference notes vs typical Claude CLI expectations
- Claude workspaces in this repo generally used approval gating; Codex here showed **no explicit approval prompts** for this simple run when config had `approval_policy = "never"` in mounted config.
- Codex presented a **trust prompt + hooks review flow** before normal input.
- Codex needs an explicit **model name flag** for pinning (`--model gpt-5.5`) vs provider default conventions.
- Bypass flags used here: `--ask-for-approval never` (optional in later runs) and `--no-alt-screen`; no claude-like `--approval-mode` required in this run.

