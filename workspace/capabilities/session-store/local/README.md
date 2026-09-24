# Local session capture

Select `AGENTIC_SESSION_STORE_PROVIDER=local` with a persistent
`AGENTIC_SESSION_STORE_SPOOL` and a host-assigned
`AGENTIC_SESSION_STORE_PARTITION`. No store URL or token is required.

Initialization uses the shared APSS native-root migration and metadata ownership
checks. Claude and Codex transcript roots point into the persistent partition.
The local exporter index lives under
`<spool>/.agentic-session-store/<partition>/envelopes`.

Preflight requires an exporter exposing `--spool-only`, `--spool-list`, and
`--spool-read`. Finalization performs one bounded local sweep. Failed or timed-out
sweeps retain native files for recovery and do not change the agent exit status.
An abrupt container kill may prevent finalization entirely. Reopen the persistent
partition and rerun capture to recover those native files.

Mount the spool explicitly. The default workspace tmpfs cannot survive container
removal. See `docs/persistent-workspace-mounts.md` for the Docker mount contract.

This provider does not contact a remote store, declare workflow coverage complete,
delete retained files, or schedule recovery. The orchestrator owns those actions
and the association between the partition and its workflow run.
