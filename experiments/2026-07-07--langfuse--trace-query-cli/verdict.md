# Verdict

**Go for local trace-query CLI integration; no-go for claiming real LangFuse
queryability.**

`itmux langfuse-trace` is the correct first read primitive because it keeps the
same env-based secret model as the exporter, accepts either a run id or trace
id, and queries a bounded observations window. It also has an explicit
`--api legacy-trace` mode for self-hosted LangFuse deployments that do not
expose the v2 observations endpoint. The missing-config run confirms the
command fails before network access without leaking secrets.

Next proof must be against a real backend: run the OTLP smoke, wait for
LangFuse processing, then query the exported run with `itmux langfuse-trace`
and verify returned observation rows.
