//! Live acceptance battery for `itmux run` (Plan B Task 8).
//!
//! This replaces the retired Python `experiments/standalone_eval.py`: instead of
//! driving the (now-superseded) Python orchestrator, it drives the real Rust
//! `itmux run` binary end-to-end, so the `itmux run` contract is proven
//! pure-Rust with no Python in the loop.
//!
//! ## Two layers, one file
//!
//! 1. **Non-live plumbing** (runs in `cargo test`, NO docker / NO token): the
//!    argv builder, the JSONL event-stream parser, the `AgentRunResult`
//!    extractor, and the R5 event-contract validator - all unit-tested against
//!    a captured sample stream and the vendored eval recipes.
//! 2. **Live cases E1..E7** (gated): each drives `itmux run` against a real
//!    docker workspace with a real agent token. Every live `#[test]` is BOTH
//!    `#[ignore]` AND early-returns unless `AGENTIC_LIVE_EVAL=1` (double
//!    safety), so `cargo test` never touches docker. Run them via
//!    `just eval-live` (see the crate/repo justfile).
//!
//! ## Auth prereq (live only)
//!
//! `itmux` sources host credentials: `~/.claude/.credentials.json` (claude) and
//! `~/.codex/auth.json` (codex). Refresh an expired claude token with
//! `claude setup-token`. Without valid credentials E1/E2 fail with an auth
//! banner (the harness correctly reports `success=false`).

use std::io::{self, BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Command, Output, Stdio};
use std::sync::mpsc;
use std::time::Instant;

use itmux::run::contract::{AgentRunEvent, AgentRunEventPayload, AgentRunResult};

/// The sentinel an E1/E2 recipe agent prints once the task is done. Verified
/// against the captured `session_log` (R1: acceptance must read what the agent
/// produced; `AgentRunResult.session_log` is that channel - no new field
/// needed).
const SENTINEL: &str = "EXPERIMENT_OK";

/// A tag known to name no real docker image, for the E5b bad-image case.
const BAD_IMAGE: &str = "no-such-image:doesnotexist";

// ===========================================================================
// Harness plumbing (unit-tested below, no docker)
// ===========================================================================

/// Inputs for one `itmux run` invocation. `None` fields omit their flag so the
/// binary's own defaults apply (proving the default path stays untouched).
#[derive(Debug, Clone, Default)]
struct RunArgs {
    recipe: PathBuf,
    task: String,
    image: Option<String>,
    /// `Some(false)` emits `--json false`; `None` omits the flag (default true).
    json: Option<bool>,
    result_file: Option<PathBuf>,
    timeout_s: Option<f64>,
}

/// Build the argv (after the binary name) for `itmux run` from [`RunArgs`].
/// Pure and order-stable so it is unit-testable without spawning anything.
fn build_run_argv(args: &RunArgs) -> Vec<String> {
    let mut argv = vec![
        "run".to_string(),
        "--recipe".to_string(),
        args.recipe.display().to_string(),
        "--task".to_string(),
        args.task.clone(),
    ];
    if let Some(image) = &args.image {
        argv.push("--image".to_string());
        argv.push(image.clone());
    }
    if let Some(json) = args.json {
        argv.push("--json".to_string());
        argv.push(json.to_string());
    }
    if let Some(result_file) = &args.result_file {
        argv.push("--result-file".to_string());
        argv.push(result_file.display().to_string());
    }
    if let Some(timeout_s) = args.timeout_s {
        argv.push("--timeout".to_string());
        argv.push(timeout_s.to_string());
    }
    argv
}

/// One line of an `itmux run --json` stdout stream: either a parsed
/// [`AgentRunEvent`] or a line that did not parse as one (a contract violation
/// in `--json` mode - stdout must be PURE event JSONL).
#[derive(Debug)]
enum ParsedLine {
    Event(Box<AgentRunEvent>),
    NonJson(String),
}

/// Parse a stdout blob into per-line results, ONE per line, dropping nothing.
///
/// In `--json` mode stdout is pure event JSONL: every line must parse as an
/// [`AgentRunEvent`], and a blank/whitespace-only line is itself a purity
/// violation (it is not valid event JSONL), so it is surfaced as a
/// [`ParsedLine::NonJson`] for [`validate_event_contract`] to reject rather than
/// silently swallowed. (`str::lines()` already omits a single trailing newline,
/// so a normal `println!`-terminated stream does not produce a spurious blank
/// final line.)
fn parse_lines(stdout: &str) -> Vec<ParsedLine> {
    stdout
        .lines()
        .map(|line| match serde_json::from_str::<AgentRunEvent>(line) {
            Ok(event) => ParsedLine::Event(Box::new(event)),
            Err(_) => ParsedLine::NonJson(line.to_string()),
        })
        .collect()
}

/// The parsed events only (drops any non-JSON lines). Callers that care about
/// stdout purity use [`validate_event_contract`] instead.
fn events_only(parsed: &[ParsedLine]) -> Vec<&AgentRunEvent> {
    parsed
        .iter()
        .filter_map(|line| match line {
            ParsedLine::Event(event) => Some(event.as_ref()),
            ParsedLine::NonJson(_) => None,
        })
        .collect()
}

/// Extract the terminal [`AgentRunResult`] delivered on the stream as a
/// `type:"result"` event (the non-`--result-file` path).
fn extract_result_from_stream(events: &[&AgentRunEvent]) -> Option<AgentRunResult> {
    events.iter().find_map(|event| match &event.payload {
        AgentRunEventPayload::Result { result } => Some((**result).clone()),
        _ => None,
    })
}

/// Read the terminal [`AgentRunResult`] from a `--result-file` (the other
/// delivery path, R7).
fn read_result_file(path: &Path) -> io::Result<AgentRunResult> {
    let bytes = std::fs::read(path)?;
    serde_json::from_slice(&bytes).map_err(io::Error::other)
}

/// How the final result is expected to be delivered, for [`validate_event_contract`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ResultDelivery {
    /// Delivered as a `type:"result"` line on stdout (default `itmux run`).
    OnStream,
    /// Written to a `--result-file`; stdout carries ONLY lifecycle events (R7).
    ResultFile,
}

/// R5 event-contract validator. Asserts, for any captured run, the CLI JSONL
/// contract every live case must uphold:
///
/// * zero non-JSON lines on stdout (`--json` mode is pure event JSONL);
/// * `seq` monotonic from 0 with no gaps;
/// * `run_id` identical across every line;
/// * exactly one `session_end`, and it is the LAST lifecycle event - no
///   `tool_start`/`tool_end`/`token_usage`/further `session_end` may follow it
///   (in BOTH modes). In `OnStream` mode the terminal `type:"result"` line is
///   the only event allowed after `session_end`; in `ResultFile` mode nothing
///   may follow it;
/// * the final result is delivered via the expected channel: exactly one
///   `type:"result"` line for [`ResultDelivery::OnStream`], and ZERO for
///   [`ResultDelivery::ResultFile`] (stdout stays pure lifecycle events).
///
/// Returns `Err(reason)` on the first violation so tests get a precise message.
fn validate_event_contract(parsed: &[ParsedLine], delivery: ResultDelivery) -> Result<(), String> {
    // Purity: no non-JSON lines.
    if let Some(bad) = parsed.iter().find_map(|line| match line {
        ParsedLine::NonJson(raw) => Some(raw),
        ParsedLine::Event(_) => None,
    }) {
        return Err(format!("non-JSON stdout line in --json mode: {bad:?}"));
    }

    let events = events_only(parsed);
    if events.is_empty() {
        return Err("stream carried no events".to_string());
    }

    // seq monotonic from 0, no gaps.
    for (index, event) in events.iter().enumerate() {
        let expected = index as u64;
        if event.seq != expected {
            return Err(format!(
                "seq not monotonic-from-0: line {index} has seq {} (expected {expected})",
                event.seq
            ));
        }
    }

    // run_id consistent across all lines.
    let run_id = &events[0].run_id;
    if let Some(mismatch) = events.iter().find(|event| &event.run_id != run_id) {
        return Err(format!(
            "inconsistent run_id: expected {run_id:?}, saw {:?}",
            mismatch.run_id
        ));
    }

    // Exactly one session_end.
    let session_ends = events
        .iter()
        .filter(|event| matches!(event.payload, AgentRunEventPayload::SessionEnd { .. }))
        .count();
    if session_ends != 1 {
        return Err(format!(
            "expected exactly one session_end, found {session_ends}"
        ));
    }

    // session_end is the TERMINAL lifecycle event: the orchestrator emits it
    // last, immediately before the (optional) terminal result. So nothing but a
    // `result` line may appear after it - any lifecycle event
    // (tool_start/tool_end/token_usage/another session_end) following
    // session_end is a contract violation in BOTH modes. (`ResultFile` also
    // forbids result lines entirely, below, so there it means NOTHING follows.)
    let session_end_index = events
        .iter()
        .position(|event| matches!(event.payload, AgentRunEventPayload::SessionEnd { .. }))
        .expect("exactly one session_end confirmed above");
    for (offset, event) in events.iter().enumerate().skip(session_end_index + 1) {
        if !matches!(event.payload, AgentRunEventPayload::Result { .. }) {
            return Err(format!(
                "session_end is not terminal: a non-result event (seq {}, line {offset}) follows it",
                event.seq
            ));
        }
    }

    // Final-result delivery channel.
    let result_lines = events
        .iter()
        .filter(|event| matches!(event.payload, AgentRunEventPayload::Result { .. }))
        .count();
    match delivery {
        ResultDelivery::OnStream => {
            if result_lines != 1 {
                return Err(format!(
                    "expected exactly one type:\"result\" line on stream, found {result_lines}"
                ));
            }
            // The result line must come last (after session_end).
            let last_is_result = matches!(
                events.last().map(|event| &event.payload),
                Some(AgentRunEventPayload::Result { .. })
            );
            if !last_is_result {
                return Err("type:\"result\" line is not the final stream line".to_string());
            }
        }
        ResultDelivery::ResultFile => {
            if result_lines != 0 {
                return Err(format!(
                    "with --result-file, stdout must carry ZERO result lines, found {result_lines}"
                ));
            }
        }
    }

    Ok(())
}

// ===========================================================================
// docker orphan sweep
// ===========================================================================

/// Container names (running OR stopped) whose name starts with `prefix`.
/// `itmux` names run containers `interactive-tmux-<recipe>-<suffix>`, so the
/// recipe-scoped prefix is a precise orphan probe. Returns an empty vec when
/// docker is unavailable or nothing matches.
fn docker_ps_names(prefix: &str) -> Vec<String> {
    let output = Command::new("docker")
        .args([
            "ps",
            "-a",
            "--filter",
            &format!("name={prefix}"),
            "--format",
            "{{.Names}}",
        ])
        .output();
    match output {
        Ok(out) => String::from_utf8_lossy(&out.stdout)
            .lines()
            .map(str::trim)
            .filter(|line| !line.is_empty())
            .map(str::to_string)
            .collect(),
        Err(_) => Vec::new(),
    }
}

/// Assert the orphan sweep for `prefix` is clean, panicking with the leftover
/// names otherwise. Best-effort cleanup is the caller's job (`docker rm -f`).
fn assert_no_orphans(prefix: &str) {
    let leftover = docker_ps_names(prefix);
    assert!(
        leftover.is_empty(),
        "orphan sweep found leftover containers for {prefix:?}: {leftover:?}"
    );
}

/// Best-effort removal of any containers matching `prefix` (test hygiene, so a
/// failing case does not poison the next one). Never fails the test.
fn sweep_containers(prefix: &str) {
    for name in docker_ps_names(prefix) {
        let _ = Command::new("docker").args(["rm", "-f", &name]).output();
    }
}

// ===========================================================================
// process drivers (live only)
// ===========================================================================

/// Path to the freshly-built `itmux` binary (cargo sets this for integration
/// tests).
fn itmux_bin() -> &'static str {
    env!("CARGO_BIN_EXE_itmux")
}

/// Absolute path to a fixture under `tests/fixtures/`.
fn fixture(rel: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures")
        .join(rel)
}

/// Run `itmux <argv>` to completion, capturing stdout/stderr. For the cases
/// that do not need to react mid-stream (E1, E2, E5b, E6, E7).
fn run_to_completion(argv: &[String]) -> io::Result<Output> {
    Command::new(itmux_bin()).args(argv).output()
}

/// Sends OS signals to a running child by pid via `kill`, avoiding `unsafe` and
/// extra deps (the crate forbids `unsafe_code`). Unix-only, like the driver.
struct Signaler {
    pid: u32,
}

impl Signaler {
    fn send(&self, signal: &str) {
        let _ = Command::new("kill")
            .args([&format!("-{signal}"), &self.pid.to_string()])
            .output();
    }

    fn sigint(&self) {
        self.send("INT");
    }

    fn sigterm(&self) {
        self.send("TERM");
    }
}

/// A streamed run: every stdout line tagged with its arrival [`Instant`]. Used
/// by E3 (arrival spread) and E4 (signal at a stream boundary). The terminal
/// verdict is read from the parsed result, not the process exit code, so no
/// exit status is retained here.
struct StreamedRun {
    lines: Vec<(Instant, String)>,
}

impl StreamedRun {
    fn stdout(&self) -> String {
        self.lines
            .iter()
            .map(|(_, line)| line.as_str())
            .collect::<Vec<_>>()
            .join("\n")
    }
}

/// Spawn `itmux <argv>`, streaming stdout line-by-line. `on_line` is invoked
/// for each arriving line with the line and a [`Signaler`] for the child, so a
/// case can send a signal at a deterministic stream boundary (R4). stderr is
/// discarded (human-only per R6).
fn stream_run(
    argv: &[String],
    mut on_line: impl FnMut(&str, &Signaler),
) -> io::Result<StreamedRun> {
    let mut child = Command::new(itmux_bin())
        .args(argv)
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()?;
    let signaler = Signaler { pid: child.id() };
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| io::Error::other("child stdout not piped"))?;

    let (tx, rx) = mpsc::channel::<(Instant, String)>();
    let reader = std::thread::spawn(move || {
        for line in BufReader::new(stdout).lines() {
            match line {
                Ok(line) => {
                    if tx.send((Instant::now(), line)).is_err() {
                        break;
                    }
                }
                Err(_) => break,
            }
        }
    });

    let mut lines = Vec::new();
    while let Ok((at, line)) = rx.recv() {
        on_line(&line, &signaler);
        lines.push((at, line));
    }
    let _ = reader.join();
    // Reap the child so it does not linger as a zombie; the terminal verdict is
    // taken from the parsed result stream, not this exit status.
    let _ = child.wait()?;
    Ok(StreamedRun { lines })
}

/// Is a line a `tool_end submit` or `tool_start await` event? That is the
/// deterministic post-provision boundary E4 fires its cancel at (R4: "after
/// first ToolStart" is NOT robust because provision is a blocking first phase).
fn is_cancel_boundary(line: &str) -> bool {
    match serde_json::from_str::<AgentRunEvent>(line) {
        Ok(event) => match &event.payload {
            AgentRunEventPayload::ToolEnd { tool_name, .. } => tool_name == "submit",
            AgentRunEventPayload::ToolStart { tool_name, .. } => tool_name == "await",
            _ => false,
        },
        Err(_) => false,
    }
}

/// Whether the live battery is armed. Live cases early-return unless this is
/// true, on TOP of `#[ignore]`, so `cargo test` can never reach docker even if
/// someone drops `--ignored`.
fn live_enabled() -> bool {
    std::env::var("AGENTIC_LIVE_EVAL").as_deref() == Ok("1")
}

/// PASS reporter (visible under `--nocapture`). Failures surface via the test
/// harness's own assertion output, so this only needs to mark the happy path.
fn pass(case: &str, detail: &str) {
    eprintln!("[PASS] {case}: {detail}");
}

/// Skip notice for a disarmed live case.
fn skip(case: &str) {
    eprintln!("[SKIP] {case}: set AGENTIC_LIVE_EVAL=1 (+ docker + token) to run");
}

// ===========================================================================
// Non-live unit tests (run in `cargo test`, no docker)
// ===========================================================================

#[cfg(test)]
mod plumbing_tests {
    use super::*;
    use itmux::adapter::Agent;
    use itmux::run::contract::AgentRunSpec;
    use itmux::run::recipe_loader::load_execution_plan;

    fn good_sample() -> String {
        std::fs::read_to_string(fixture("eval/sample_run_good.jsonl"))
            .expect("sample fixture readable")
    }

    // --- argv builder ------------------------------------------------------

    #[test]
    fn argv_minimal_has_recipe_and_task_only() {
        let argv = build_run_argv(&RunArgs {
            recipe: PathBuf::from("/recipes/hello"),
            task: "do it".to_string(),
            ..Default::default()
        });
        assert_eq!(
            argv,
            vec!["run", "--recipe", "/recipes/hello", "--task", "do it"]
        );
    }

    #[test]
    fn argv_includes_every_optional_flag_when_set() {
        let argv = build_run_argv(&RunArgs {
            recipe: PathBuf::from("/r"),
            task: "t".to_string(),
            image: Some("img:tag".to_string()),
            json: Some(false),
            result_file: Some(PathBuf::from("/tmp/out.json")),
            timeout_s: Some(1.5),
        });
        assert_eq!(
            argv,
            vec![
                "run",
                "--recipe",
                "/r",
                "--task",
                "t",
                "--image",
                "img:tag",
                "--json",
                "false",
                "--result-file",
                "/tmp/out.json",
                "--timeout",
                "1.5",
            ]
        );
    }

    #[test]
    fn argv_omits_json_flag_when_default() {
        let argv = build_run_argv(&RunArgs {
            recipe: PathBuf::from("/r"),
            task: "t".to_string(),
            ..Default::default()
        });
        assert!(!argv.iter().any(|a| a == "--json"), "argv: {argv:?}");
    }

    // --- parser ------------------------------------------------------------

    #[test]
    fn parser_reads_the_full_good_sample_stream() {
        let parsed = parse_lines(&good_sample());
        // Every line parses as an event; none are NonJson.
        assert!(
            parsed
                .iter()
                .all(|line| matches!(line, ParsedLine::Event(_))),
            "all sample lines should be events"
        );
        let events = events_only(&parsed);
        assert_eq!(events.len(), 12);
        assert!(matches!(
            events[10].payload,
            AgentRunEventPayload::SessionEnd { .. }
        ));
        assert!(matches!(
            events[11].payload,
            AgentRunEventPayload::Result { .. }
        ));
    }

    #[test]
    fn parser_flags_a_non_json_line() {
        let stdout = "not json at all\n{\"run_id\":\"r\",\"seq\":0,\"ts\":\"t\",\"type\":\"session_end\",\"outcome\":{\"success\":true,\"summary\":\"ok\"}}";
        let parsed = parse_lines(stdout);
        assert!(matches!(parsed[0], ParsedLine::NonJson(_)));
        assert!(matches!(parsed[1], ParsedLine::Event(_)));
    }

    // --- result extraction (R1 sentinel channel) ---------------------------

    #[test]
    fn extracts_result_and_reads_sentinel_from_session_log() {
        let parsed = parse_lines(&good_sample());
        let events = events_only(&parsed);
        let result = extract_result_from_stream(&events).expect("stream carries a result");
        assert!(result.result.success);
        // R1: the captured output is the acceptance channel - session_log
        // exposes what the agent produced, so the sentinel is verifiable.
        assert!(
            result.session_log.contains(SENTINEL),
            "session_log should carry the {SENTINEL} sentinel: {:?}",
            result.session_log
        );
    }

    #[test]
    fn result_file_round_trips() {
        // Write a result, read it back the way the --result-file path (R7) does.
        let dir = std::env::temp_dir().join(format!("itmux-eval-test-{}", std::process::id()));
        std::fs::create_dir_all(&dir).expect("mkdir");
        let path = dir.join("result.json");
        let parsed = parse_lines(&good_sample());
        let events = events_only(&parsed);
        let result = extract_result_from_stream(&events).unwrap();
        std::fs::write(&path, serde_json::to_vec_pretty(&result).unwrap()).unwrap();
        let back = read_result_file(&path).expect("read result file");
        assert_eq!(back, result);
        let _ = std::fs::remove_dir_all(&dir);
    }

    // --- R5 event-contract validator ---------------------------------------

    #[test]
    fn validator_accepts_the_good_stream_on_stream_delivery() {
        let parsed = parse_lines(&good_sample());
        validate_event_contract(&parsed, ResultDelivery::OnStream).expect("good stream is valid");
    }

    #[test]
    fn validator_rejects_a_non_json_line() {
        let mut stdout = String::from("garbage line\n");
        stdout.push_str(&good_sample());
        let parsed = parse_lines(&stdout);
        let err = validate_event_contract(&parsed, ResultDelivery::OnStream).unwrap_err();
        assert!(err.contains("non-JSON"), "err: {err}");
    }

    #[test]
    fn validator_rejects_an_embedded_blank_line() {
        // A blank line on stdout in --json mode is a purity violation: it is
        // not valid event JSONL and must NOT be silently dropped. Inject one
        // between two otherwise-valid events.
        let sample = good_sample();
        let (head, tail) = sample.split_once('\n').expect("multi-line sample");
        let corrupted = format!("{head}\n\n{tail}");
        let parsed = parse_lines(&corrupted);
        let err = validate_event_contract(&parsed, ResultDelivery::OnStream).unwrap_err();
        assert!(err.contains("non-JSON"), "err: {err}");
    }

    #[test]
    fn validator_rejects_a_lifecycle_event_after_session_end_on_stream() {
        // session_end must be terminal: a tool_start AFTER it (before the
        // result line) is rejected even though counts/seq are otherwise valid.
        let stream = "\
{\"run_id\":\"r\",\"seq\":0,\"ts\":\"t\",\"type\":\"session_end\",\"outcome\":{\"success\":true,\"summary\":\"ok\"}}
{\"run_id\":\"r\",\"seq\":1,\"ts\":\"t\",\"type\":\"tool_start\",\"tool_name\":\"provision\",\"tool_input\":null}
{\"run_id\":\"r\",\"seq\":2,\"ts\":\"t\",\"type\":\"result\",\"result\":{\"result\":{\"success\":true,\"summary\":\"ok\"},\"output_artifacts\":[],\"session_log\":\"\",\"observability\":null}}";
        let parsed = parse_lines(stream);
        let err = validate_event_contract(&parsed, ResultDelivery::OnStream).unwrap_err();
        assert!(err.contains("session_end is not terminal"), "err: {err}");
    }

    #[test]
    fn validator_rejects_a_lifecycle_event_after_session_end_with_result_file() {
        // Same rule in --result-file mode: nothing may follow session_end.
        let stream = "\
{\"run_id\":\"r\",\"seq\":0,\"ts\":\"t\",\"type\":\"session_end\",\"outcome\":{\"success\":true,\"summary\":\"ok\"}}
{\"run_id\":\"r\",\"seq\":1,\"ts\":\"t\",\"type\":\"tool_end\",\"tool_name\":\"capture\",\"success\":true,\"output_summary\":null}";
        let parsed = parse_lines(stream);
        let err = validate_event_contract(&parsed, ResultDelivery::ResultFile).unwrap_err();
        assert!(err.contains("session_end is not terminal"), "err: {err}");
    }

    #[test]
    fn validator_rejects_a_seq_gap() {
        // Drop the seq=1 line so the sequence jumps 0 -> 2.
        let corrupted: String = good_sample()
            .lines()
            .filter(|line| !line.contains("\"seq\":1,"))
            .collect::<Vec<_>>()
            .join("\n");
        let parsed = parse_lines(&corrupted);
        let err = validate_event_contract(&parsed, ResultDelivery::OnStream).unwrap_err();
        assert!(err.contains("monotonic"), "err: {err}");
    }

    #[test]
    fn validator_rejects_two_session_ends() {
        // Duplicate the session_end line (keeps seq contiguous by rewriting).
        let stream = "\
{\"run_id\":\"r\",\"seq\":0,\"ts\":\"t\",\"type\":\"session_end\",\"outcome\":{\"success\":true,\"summary\":\"a\"}}
{\"run_id\":\"r\",\"seq\":1,\"ts\":\"t\",\"type\":\"session_end\",\"outcome\":{\"success\":true,\"summary\":\"b\"}}";
        let parsed = parse_lines(stream);
        let err = validate_event_contract(&parsed, ResultDelivery::OnStream).unwrap_err();
        assert!(err.contains("session_end"), "err: {err}");
    }

    #[test]
    fn validator_rejects_inconsistent_run_id() {
        let stream = "\
{\"run_id\":\"r1\",\"seq\":0,\"ts\":\"t\",\"type\":\"tool_start\",\"tool_name\":\"provision\",\"tool_input\":null}
{\"run_id\":\"r2\",\"seq\":1,\"ts\":\"t\",\"type\":\"session_end\",\"outcome\":{\"success\":true,\"summary\":\"ok\"}}";
        let parsed = parse_lines(stream);
        let err = validate_event_contract(&parsed, ResultDelivery::OnStream).unwrap_err();
        assert!(err.contains("run_id"), "err: {err}");
    }

    #[test]
    fn validator_requires_a_result_line_on_stream_delivery() {
        // A stream that ends at session_end with NO result line fails OnStream.
        let stream = "\
{\"run_id\":\"r\",\"seq\":0,\"ts\":\"t\",\"type\":\"tool_start\",\"tool_name\":\"provision\",\"tool_input\":null}
{\"run_id\":\"r\",\"seq\":1,\"ts\":\"t\",\"type\":\"session_end\",\"outcome\":{\"success\":true,\"summary\":\"ok\"}}";
        let parsed = parse_lines(stream);
        let err = validate_event_contract(&parsed, ResultDelivery::OnStream).unwrap_err();
        assert!(err.contains("result"), "err: {err}");
    }

    #[test]
    fn validator_result_file_mode_forbids_result_lines() {
        // The good sample HAS a result line, so it must FAIL ResultFile mode
        // (stdout must be pure lifecycle events when --result-file is used).
        let parsed = parse_lines(&good_sample());
        let err = validate_event_contract(&parsed, ResultDelivery::ResultFile).unwrap_err();
        assert!(err.contains("ZERO result lines"), "err: {err}");

        // A lifecycle-only stream (no result line) is valid for ResultFile.
        let lifecycle = "\
{\"run_id\":\"r\",\"seq\":0,\"ts\":\"t\",\"type\":\"tool_start\",\"tool_name\":\"provision\",\"tool_input\":null}
{\"run_id\":\"r\",\"seq\":1,\"ts\":\"t\",\"type\":\"session_end\",\"outcome\":{\"success\":true,\"summary\":\"ok\"}}";
        let parsed = parse_lines(lifecycle);
        validate_event_contract(&parsed, ResultDelivery::ResultFile)
            .expect("lifecycle-only stream valid for --result-file");
    }

    // --- cancel-boundary detection (R4) ------------------------------------

    #[test]
    fn cancel_boundary_matches_submit_end_and_await_start_only() {
        assert!(is_cancel_boundary(
            "{\"run_id\":\"r\",\"seq\":5,\"ts\":\"t\",\"type\":\"tool_end\",\"tool_name\":\"submit\",\"success\":true,\"output_summary\":null}"
        ));
        assert!(is_cancel_boundary(
            "{\"run_id\":\"r\",\"seq\":6,\"ts\":\"t\",\"type\":\"tool_start\",\"tool_name\":\"await\",\"tool_input\":null}"
        ));
        // Provision start is NOT the boundary (that is the blocking first phase).
        assert!(!is_cancel_boundary(
            "{\"run_id\":\"r\",\"seq\":0,\"ts\":\"t\",\"type\":\"tool_start\",\"tool_name\":\"provision\",\"tool_input\":null}"
        ));
        assert!(!is_cancel_boundary("not json"));
    }

    // --- fixture sanity (the eval recipes load + carry the sentinel task) ---

    fn plan_for(recipe_rel: &str) -> itmux::run::recipe_loader::RecipeExecutionPlan {
        let spec = AgentRunSpec {
            recipe: fixture(recipe_rel),
            task: format!("task text; remember to print {SENTINEL}"),
            input_artifacts: vec![],
            credentials: Default::default(),
            observability: vec![],
            limits: None,
        };
        load_execution_plan(&spec).expect("eval recipe should load")
    }

    #[test]
    fn claude_eval_recipe_loads_as_claude_with_sentinel_instructions() {
        let plan = plan_for("eval/recipe-claude-hello");
        assert_eq!(plan.agent, Agent::Claude);
        assert!(
            plan.submit_text.contains(SENTINEL),
            "claude recipe submit_text should instruct printing {SENTINEL}"
        );
    }

    #[test]
    fn codex_eval_recipe_loads_as_codex() {
        let plan = plan_for("eval/recipe-codex-hello");
        assert_eq!(plan.agent, Agent::Codex);
        assert!(plan.submit_text.contains(SENTINEL));
    }
}

// ===========================================================================
// Live cases E1..E7 (gated: #[ignore] + AGENTIC_LIVE_EVAL=1)
// ===========================================================================
//
// E5a (forced-startup-timeout orphan guard) is intentionally NOT a live case
// (plan R2): the orchestrator unit tests prove the teardown-on-startup-failure
// path deterministically without docker - see
// `tests/orchestrator.rs` (`start_failure_after_partial_startup_tears_down_and_no_orphan`
// and the hard-cancel-no-handle reap test). A live forced timeout would
// re-test docker, not our logic. E5b (bad image) IS live, below.

/// E1 - claude happy path (R1). Runs the claude eval recipe and asserts the run
/// succeeded, the EXPERIMENT_OK sentinel appears in the captured session_log,
/// and the R5 event-contract holds. Needs a valid claude token.
#[test]
#[ignore = "live: docker + claude token; run via `just eval-live`"]
fn e1_claude_happy_path() {
    if !live_enabled() {
        skip("E1");
        return;
    }
    let prefix = "interactive-tmux-claude-hello";
    sweep_containers(prefix);
    let argv = build_run_argv(&RunArgs {
        recipe: fixture("eval/recipe-claude-hello"),
        task: format!("Create the file then print {SENTINEL}."),
        ..Default::default()
    });
    let output = run_to_completion(&argv).expect("spawn itmux run");
    let stdout = String::from_utf8_lossy(&output.stdout);
    let parsed = parse_lines(&stdout);
    validate_event_contract(&parsed, ResultDelivery::OnStream).expect("E1 event contract");
    let events = events_only(&parsed);
    let result = extract_result_from_stream(&events).expect("E1 result on stream");

    assert!(
        result.result.success,
        "E1 expected success: {:?}",
        result.result
    );
    assert!(
        result.session_log.contains(SENTINEL),
        "E1 expected {SENTINEL} in session_log: {:?}",
        result.session_log
    );
    assert_no_orphans(prefix);
    pass(
        "E1",
        "claude happy-path: success + sentinel + contract + no orphan",
    );
}

/// E2 - codex happy path. Reaching ready + a graceful terminal is the bar;
/// codex may sit at a trust prompt so task success (the sentinel) is a stretch
/// goal, not required (plan T8.3 / E2).
#[test]
#[ignore = "live: docker + codex token; run via `just eval-live`"]
fn e2_codex_happy_path() {
    if !live_enabled() {
        skip("E2");
        return;
    }
    let prefix = "interactive-tmux-codex-hello";
    sweep_containers(prefix);
    let argv = build_run_argv(&RunArgs {
        recipe: fixture("eval/recipe-codex-hello"),
        task: format!("Create the file then print {SENTINEL}."),
        ..Default::default()
    });
    let output = run_to_completion(&argv).expect("spawn itmux run");
    let stdout = String::from_utf8_lossy(&output.stdout);
    let parsed = parse_lines(&stdout);
    validate_event_contract(&parsed, ResultDelivery::OnStream).expect("E2 event contract");
    let events = events_only(&parsed);
    let result = extract_result_from_stream(&events).expect("E2 result on stream");

    // Reached a graceful terminal: exactly one session_end + a delivered
    // result. Task success is a stretch goal (see doc comment), so we do not
    // assert result.success here.
    if result.session_log.contains(SENTINEL) {
        pass(
            "E2",
            "codex reached ready AND produced the sentinel (stretch met)",
        );
    } else {
        pass(
            "E2",
            "codex reached ready + graceful terminal (sentinel not required)",
        );
    }
    assert_no_orphans(prefix);
}

/// E3 - live events arrive incrementally (not one final dump), and a ToolStart
/// precedes the terminal SessionEnd by ts. Uses the claude recipe.
#[test]
#[ignore = "live: docker + claude token; run via `just eval-live`"]
fn e3_live_events_stream_incrementally() {
    if !live_enabled() {
        skip("E3");
        return;
    }
    let prefix = "interactive-tmux-claude-hello";
    sweep_containers(prefix);
    let argv = build_run_argv(&RunArgs {
        recipe: fixture("eval/recipe-claude-hello"),
        task: format!("Create the file then print {SENTINEL}."),
        ..Default::default()
    });
    let streamed = stream_run(&argv, |_line, _sig| {}).expect("stream itmux run");

    // Arrival spread: the first and last lines did NOT arrive in the same
    // instant - events are streamed as the run progresses, not buffered into a
    // single terminal dump.
    let first_at = streamed.lines.first().map(|(at, _)| *at);
    let last_at = streamed.lines.last().map(|(at, _)| *at);
    if let (Some(first), Some(last)) = (first_at, last_at) {
        let spread = last.duration_since(first);
        assert!(
            spread.as_millis() > 50,
            "expected incremental arrival spread, got {spread:?}"
        );
    } else {
        panic!("E3 saw no stream lines");
    }

    // ToolStart precedes SessionEnd by ts.
    let parsed = parse_lines(&streamed.stdout());
    validate_event_contract(&parsed, ResultDelivery::OnStream).expect("E3 event contract");
    let events = events_only(&parsed);
    let first_tool_start_ts = events.iter().find_map(|event| match &event.payload {
        AgentRunEventPayload::ToolStart { .. } => Some(event.ts.clone()),
        _ => None,
    });
    let session_end_ts = events.iter().find_map(|event| match &event.payload {
        AgentRunEventPayload::SessionEnd { .. } => Some(event.ts.clone()),
        _ => None,
    });
    let (ts_start, ts_end) = (
        first_tool_start_ts.expect("a tool_start"),
        session_end_ts.expect("a session_end"),
    );
    // Lexicographic compare is sound here because the emitter
    // (`workspace_executor::now_rfc3339`) always produces fixed-width,
    // second-precision UTC timestamps with a literal `Z` offset
    // (`YYYY-MM-DDThh:mm:ssZ`), so string order equals chronological order. The
    // crate carries no datetime parser (it hand-rolls RFC3339), and adding one
    // solely for this assertion is not worth the dependency weight.
    assert!(
        ts_start <= ts_end,
        "tool_start {ts_start} must be <= session_end {ts_end}"
    );
    assert_no_orphans(prefix);
    pass(
        "E3",
        "events arrived incrementally; tool_start precedes session_end",
    );
}

/// E4 graceful cancellation (R4). Fires a single SIGINT at the submit/await
/// boundary; asserts the run reports a graceful cancel and leaves no orphan.
#[test]
#[ignore = "live: docker + claude token; run via `just eval-live`"]
fn e4_graceful_cancellation() {
    if !live_enabled() {
        skip("E4-graceful");
        return;
    }
    cancellation_case(CancelKind::Graceful, "graceful");
}

/// E4 hard cancellation (R4). Fires two SIGINTs at the boundary; asserts a hard
/// cancel and no orphan.
#[test]
#[ignore = "live: docker + claude token; run via `just eval-live`"]
fn e4_hard_cancellation() {
    if !live_enabled() {
        skip("E4-hard");
        return;
    }
    cancellation_case(CancelKind::Hard, "hard");
}

#[derive(Clone, Copy)]
enum CancelKind {
    Graceful,
    Hard,
}

/// Shared E4 driver: run the claude recipe, signal at the submit/await boundary,
/// then assert the terminal outcome maps and the orphan sweep is clean. Per R4
/// we assert terminal outcome + no orphan, NOT exit latency.
fn cancellation_case(kind: CancelKind, summary_needle: &str) {
    let prefix = "interactive-tmux-claude-hello";
    sweep_containers(prefix);
    let argv = build_run_argv(&RunArgs {
        recipe: fixture("eval/recipe-claude-hello"),
        task: "Wait for further instructions; do not exit.".to_string(),
        ..Default::default()
    });
    let mut fired = false;
    let streamed = stream_run(&argv, |line, sig| {
        if !fired && is_cancel_boundary(line) {
            fired = true;
            match kind {
                CancelKind::Graceful => sig.sigint(),
                CancelKind::Hard => {
                    // Two SIGINTs escalate to a hard cancel (or a SIGTERM).
                    sig.sigint();
                    sig.sigterm();
                }
            }
        }
    })
    .expect("stream itmux run");
    assert!(fired, "E4 never observed the submit/await cancel boundary");

    let parsed = parse_lines(&streamed.stdout());
    validate_event_contract(&parsed, ResultDelivery::OnStream).expect("E4 event contract");
    let events = events_only(&parsed);
    let result = extract_result_from_stream(&events).expect("E4 result on stream");

    assert!(
        !result.result.success,
        "cancelled run must not report success"
    );
    assert!(
        result
            .result
            .summary
            .to_lowercase()
            .contains(summary_needle),
        "E4 {summary_needle} cancel: summary {:?} should mention {summary_needle:?}",
        result.result.summary
    );
    assert_no_orphans(prefix);
    pass("E4", &format!("{summary_needle} cancel mapped + no orphan"));
}

/// E5b - a bad image fails the run and creates no container (orphan sweep clean).
/// E5a is unit-proven (see the module comment above these live cases, plan R2).
#[test]
#[ignore = "live: docker; run via `just eval-live`"]
fn e5b_bad_image_no_container() {
    if !live_enabled() {
        skip("E5b");
        return;
    }
    let prefix = "interactive-tmux-claude-hello";
    sweep_containers(prefix);
    let argv = build_run_argv(&RunArgs {
        recipe: fixture("eval/recipe-claude-hello"),
        task: "noop".to_string(),
        image: Some(BAD_IMAGE.to_string()),
        ..Default::default()
    });
    let output = run_to_completion(&argv).expect("spawn itmux run");
    let stdout = String::from_utf8_lossy(&output.stdout);
    let parsed = parse_lines(&stdout);
    let events = events_only(&parsed);
    let result = extract_result_from_stream(&events);

    // The run failed (either a terminal failure result, or a precondition exit
    // with no stream) - in all cases, non-success.
    if let Some(result) = &result {
        assert!(!result.result.success, "bad image must not succeed");
        // The provision phase reported failure.
        let provision_failed = events.iter().any(|event| {
            matches!(&event.payload, AgentRunEventPayload::ToolEnd { tool_name, success, .. }
                if tool_name == "provision" && !*success)
        });
        assert!(provision_failed, "provision should have reported failure");
    } else {
        assert!(!output.status.success(), "bad image run must exit non-zero");
    }
    // No container was created / left behind.
    assert_no_orphans(prefix);
    pass(
        "E5b",
        "bad image failed, no container created, orphan sweep clean",
    );
}

/// E6 - timeout (R6). A short `--timeout` shorter than the agent can settle
/// yields a `timeout` terminal reason with `success=false` and no orphan.
#[test]
#[ignore = "live: docker + claude token; run via `just eval-live`"]
fn e6_timeout_terminal_reason() {
    if !live_enabled() {
        skip("E6");
        return;
    }
    let prefix = "interactive-tmux-claude-hello";
    sweep_containers(prefix);
    let argv = build_run_argv(&RunArgs {
        recipe: fixture("eval/recipe-claude-hello"),
        task: "Think for a long time before answering.".to_string(),
        // 1s await bound - shorter than the await warmup, so the await times out.
        timeout_s: Some(1.0),
        ..Default::default()
    });
    let output = run_to_completion(&argv).expect("spawn itmux run");
    let stdout = String::from_utf8_lossy(&output.stdout);
    let parsed = parse_lines(&stdout);
    validate_event_contract(&parsed, ResultDelivery::OnStream).expect("E6 event contract");
    let events = events_only(&parsed);
    let result = extract_result_from_stream(&events).expect("E6 result on stream");

    assert!(
        !result.result.success,
        "timed-out run must not report success"
    );
    assert!(
        result.result.summary.to_lowercase().contains("timed out")
            || result.result.summary.to_lowercase().contains("timeout"),
        "E6 summary {:?} should indicate a timeout",
        result.result.summary
    );
    assert_no_orphans(prefix);
    pass(
        "E6",
        "short --timeout produced a timeout terminal reason + no orphan",
    );
}

/// E7 - result-file (R7). With `--result-file`, the result JSON lands in the
/// file AND stdout stays pure lifecycle events (no `type:"result"` line).
#[test]
#[ignore = "live: docker + claude token; run via `just eval-live`"]
fn e7_result_file_keeps_stdout_pure() {
    if !live_enabled() {
        skip("E7");
        return;
    }
    let prefix = "interactive-tmux-claude-hello";
    sweep_containers(prefix);
    let dir = std::env::temp_dir().join(format!("itmux-eval-e7-{}", std::process::id()));
    std::fs::create_dir_all(&dir).expect("mkdir result dir");
    let result_path = dir.join("result.json");
    let argv = build_run_argv(&RunArgs {
        recipe: fixture("eval/recipe-claude-hello"),
        task: format!("Create the file then print {SENTINEL}."),
        result_file: Some(result_path.clone()),
        ..Default::default()
    });
    let output = run_to_completion(&argv).expect("spawn itmux run");
    let stdout = String::from_utf8_lossy(&output.stdout);
    let parsed = parse_lines(&stdout);

    // R7: stdout is pure lifecycle events - ZERO result lines - when a result
    // file is used.
    validate_event_contract(&parsed, ResultDelivery::ResultFile).expect("E7 event contract");

    // The result JSON landed in the file and parses.
    let result = read_result_file(&result_path).expect("E7 result file present + valid");
    // session_end still carries the terminal outcome on the stream.
    let events = events_only(&parsed);
    assert!(
        events
            .iter()
            .any(|event| matches!(event.payload, AgentRunEventPayload::SessionEnd { .. })),
        "E7 stream should still carry a session_end"
    );
    let _ = result; // outcome value is auth-dependent; presence + purity is the contract here.
    let _ = std::fs::remove_dir_all(&dir);
    assert_no_orphans(prefix);
    pass(
        "E7",
        "result landed in file; stdout stayed pure lifecycle events",
    );
}
