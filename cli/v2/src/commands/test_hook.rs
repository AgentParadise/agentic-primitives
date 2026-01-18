use crate::config::PrimitivesConfig;
use crate::primitives::hook::HookMeta;
use anyhow::{anyhow, bail, Context};
use colored::Colorize;
use serde::Serialize;
use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::Instant;

#[derive(Debug)]
pub struct TestHookArgs {
    pub path: String,  // Hook directory path
    pub input: String, // JSON file or inline JSON
    pub json: bool,    // JSON output mode
    pub verbose: bool, // Verbose execution details
}

#[derive(Debug, Serialize)]
pub struct TestHookResult {
    pub hook_id: String,
    pub event: String,
    pub decision: String, // "allow" or "block"
    pub reason: String,
    pub execution_time_ms: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub middleware_results: Option<Vec<serde_json::Value>>,
    pub metrics: HashMap<String, serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub stdout: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub stderr: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub exit_code: Option<i32>,
}

/// Load and validate hook metadata
fn load_hook_metadata(hook_path: &Path) -> anyhow::Result<HookMeta> {
    // Find hook metadata file ({id}.hook.yaml)
    let hook_dir = if hook_path.is_dir() {
        hook_path
    } else {
        hook_path
            .parent()
            .ok_or_else(|| anyhow!("Invalid hook path"))?
    };

    let hook_id = hook_dir
        .file_name()
        .and_then(|n| n.to_str())
        .ok_or_else(|| anyhow!("Could not determine hook ID from path"))?;

    let meta_path = hook_dir.join(format!("{hook_id}.hook.yaml"));

    if !meta_path.exists() {
        // Fallback to legacy hook.meta.yaml
        let legacy_path = hook_dir.join("hook.meta.yaml");
        if legacy_path.exists() {
            return load_hook_meta_file(&legacy_path);
        }
        bail!("Hook metadata not found: {}", meta_path.display());
    }

    load_hook_meta_file(&meta_path)
}

fn load_hook_meta_file(path: &Path) -> anyhow::Result<HookMeta> {
    let content = fs::read_to_string(path)
        .with_context(|| format!("Failed to read hook metadata: {}", path.display()))?;

    let meta: HookMeta = serde_yaml::from_str(&content)
        .with_context(|| format!("Failed to parse hook metadata: {}", path.display()))?;

    // Validate required fields
    if meta.id.is_empty() {
        bail!("Hook metadata missing required field: id");
    }
    if meta.kind != "hook" {
        bail!(
            "Invalid kind in hook metadata: expected 'hook', got '{}'",
            meta.kind
        );
    }

    Ok(meta)
}

/// Find implementation file (prefer directory-named files like bash-validator.py)
fn find_implementation_file(hook_path: &Path) -> Option<PathBuf> {
    let hook_dir = if hook_path.is_dir() {
        hook_path
    } else {
        hook_path.parent()?
    };

    // Get directory name for preferred naming pattern
    let dir_name = hook_dir.file_name()?.to_str()?;

    // Try directory-named files first (NEW PATTERN: bash-validator.py)
    let preferred_patterns = vec![
        format!("{}.py", dir_name),
        format!("{}.ts", dir_name),
        format!("{}.rs", dir_name),
        format!("{}.sh", dir_name),
    ];

    for pattern in preferred_patterns {
        let impl_path = hook_dir.join(&pattern);
        if impl_path.exists() {
            return Some(impl_path);
        }
    }

    // Fallback to old impl.* naming (DEPRECATED)
    let legacy_patterns = vec![
        "impl.python.py",
        "impl.py",
        "impl.typescript.ts",
        "impl.ts",
        "impl.rust.rs",
        "impl.rs",
        "impl.bash.sh",
        "impl.sh",
    ];

    for pattern in legacy_patterns {
        let impl_path = hook_dir.join(pattern);
        if impl_path.exists() {
            return Some(impl_path);
        }
    }

    None
}

/// Parse test input from file or inline JSON
fn parse_test_input(input_arg: &str) -> anyhow::Result<serde_json::Value> {
    // Check if input looks like a file path
    if !input_arg.trim().starts_with('{') && !input_arg.trim().starts_with('[') {
        // Treat as file path
        let input_path = Path::new(input_arg);
        if !input_path.exists() {
            bail!("Input file not found: {}", input_path.display());
        }

        let content = fs::read_to_string(input_path)
            .with_context(|| format!("Failed to read input file: {}", input_path.display()))?;

        serde_json::from_str(&content)
            .with_context(|| format!("Failed to parse JSON from file: {}", input_path.display()))
    } else {
        // Treat as inline JSON
        serde_json::from_str(input_arg).context("Failed to parse inline JSON input")
    }
}

/// Execute hook implementation with test input
fn execute_hook_implementation(
    impl_path: &Path,
    test_input: &serde_json::Value,
    verbose: bool,
) -> anyhow::Result<TestHookResult> {
    let start_time = Instant::now();

    // Determine interpreter based on file extension
    let (interpreter, args) = match impl_path.extension().and_then(|e| e.to_str()) {
        Some("py") => ("python3", vec![impl_path.to_str().unwrap()]),
        Some("ts") => ("ts-node", vec![impl_path.to_str().unwrap()]),
        Some("js") => ("node", vec![impl_path.to_str().unwrap()]),
        Some("sh") => ("bash", vec![impl_path.to_str().unwrap()]),
        Some("rs") => bail!("Rust implementations must be compiled first"),
        _ => bail!(
            "Unknown implementation file type: {:?}",
            impl_path.extension()
        ),
    };

    // Prepare stdin input
    let input_json = serde_json::to_string(test_input)?;

    // Execute implementation
    let mut child = Command::new(interpreter)
        .args(&args)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .with_context(|| format!("Failed to execute implementation: {}", impl_path.display()))?;

    // Write input to stdin
    use std::io::Write;
    if let Some(mut stdin) = child.stdin.take() {
        stdin
            .write_all(input_json.as_bytes())
            .context("Failed to write input to hook stdin")?;
    }

    // Wait for completion and capture output
    let output = child
        .wait_with_output()
        .context("Failed to wait for hook execution")?;

    let execution_time_ms = start_time.elapsed().as_millis() as u64;

    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).to_string();

    // Parse hook output JSON
    let hook_output: serde_json::Value = if !stdout.trim().is_empty() {
        serde_json::from_str(&stdout).context("Failed to parse hook output JSON")?
    } else {
        bail!("Hook produced no output");
    };

    // Extract decision and reason
    let decision = hook_output
        .get("decision")
        .and_then(|d| d.as_str())
        .unwrap_or("unknown")
        .to_string();

    let reason = hook_output
        .get("reason")
        .and_then(|r| r.as_str())
        .unwrap_or("")
        .to_string();

    let middleware_results = hook_output
        .get("middleware_results")
        .and_then(|m| m.as_array())
        .cloned();

    let metrics = hook_output
        .get("metrics")
        .and_then(|m| m.as_object())
        .map(|obj| obj.iter().map(|(k, v)| (k.clone(), v.clone())).collect())
        .unwrap_or_default();

    Ok(TestHookResult {
        hook_id: String::new(), // Will be filled by caller
        event: String::new(),   // Will be filled by caller
        decision,
        reason,
        execution_time_ms,
        middleware_results,
        metrics,
        stdout: if verbose { Some(stdout) } else { None },
        stderr: if verbose || !stderr.is_empty() {
            Some(stderr)
        } else {
            None
        },
        exit_code: Some(output.status.code().unwrap_or(-1)),
    })
}

/// Print human-readable test results
fn print_human_output(result: &TestHookResult) {
    println!(
        "\n🪝 Testing Hook: {} ({})",
        result.hook_id.cyan().bold(),
        result.event.yellow()
    );
    println!("{}", "━".repeat(60).dimmed());

    // Decision
    let decision_symbol = if result.decision == "allow" {
        "✓"
    } else {
        "✗"
    };
    let decision_color = if result.decision == "allow" {
        "green"
    } else {
        "red"
    };

    println!(
        "Decision: {} {}",
        decision_symbol,
        match decision_color {
            "green" => result.decision.to_uppercase().green().bold(),
            "red" => result.decision.to_uppercase().red().bold(),
            _ => result.decision.to_uppercase().normal(),
        }
    );

    if !result.reason.is_empty() {
        println!("Reason: {}", result.reason);
    }

    // Middleware results
    if let Some(middleware_results) = &result.middleware_results {
        if !middleware_results.is_empty() {
            println!("\nMiddleware Results:");
            for mw in middleware_results {
                if let Some(id) = mw.get("id").and_then(|v| v.as_str()) {
                    let mw_decision = mw
                        .get("decision")
                        .and_then(|v| v.as_str())
                        .unwrap_or("unknown");
                    let mw_symbol = if mw_decision == "block" { "✗" } else { "✓" };
                    let mw_type = mw.get("type").and_then(|v| v.as_str()).unwrap_or("");

                    println!("  {} {} ({})", mw_symbol, id.cyan(), mw_type.dimmed());

                    if let Some(reason) = mw.get("reason").and_then(|v| v.as_str()) {
                        if mw_decision == "block" {
                            println!("    └─ {}: {}", "Blocked".red(), reason);
                        }
                    }
                }
            }
        }
    }

    // Execution time
    println!(
        "\n{}: {}ms",
        "Execution Time".bold(),
        result.execution_time_ms
    );

    // Metrics
    if !result.metrics.is_empty() {
        println!("{}: {:?}", "Metrics".bold(), result.metrics);
    }

    // Verbose output
    if let Some(stdout) = &result.stdout {
        println!("\n{}:", "STDOUT".yellow().bold());
        println!("{}", stdout.dimmed());
    }

    if let Some(stderr) = &result.stderr {
        if !stderr.is_empty() {
            println!("\n{}:", "STDERR".red().bold());
            println!("{stderr}");
        }
    }

    println!();
}

/// Print JSON output
fn print_json_output(result: &TestHookResult) -> anyhow::Result<()> {
    let json =
        serde_json::to_string_pretty(result).context("Failed to serialize result to JSON")?;
    println!("{json}");
    Ok(())
}

pub fn execute(args: &TestHookArgs, _config: &PrimitivesConfig) -> anyhow::Result<()> {
    let hook_path = Path::new(&args.path);

    // 1. Load and validate hook metadata
    let hook_meta = load_hook_metadata(hook_path)?;

    // 2. Parse test input
    let test_input = parse_test_input(&args.input)?;

    // 3. Find implementation file
    let impl_path = find_implementation_file(hook_path)
        .ok_or_else(|| {
            let dir_name = hook_path
                .file_name()
                .and_then(|n| n.to_str())
                .unwrap_or("unknown");
            anyhow!(
                "No implementation file found in hook directory: {}\nLooked for: {}.py, {}.ts, {}.rs, {}.sh (or legacy impl.* files)",
                hook_path.display(),
                dir_name, dir_name, dir_name, dir_name
            )
        })?;

    if args.verbose {
        eprintln!("Hook: {}", hook_meta.id.cyan());
        let events = hook_meta.get_events();
        if events.is_empty() {
            eprintln!("Events: Universal (all agent events)");
        } else {
            eprintln!("Events: {events:?}");
        }
        eprintln!("Implementation: {}", impl_path.display());
        eprintln!("Executing...\n");
    }

    // 4. Execute hook implementation
    let mut result = execute_hook_implementation(&impl_path, &test_input, args.verbose)?;

    // Fill in metadata
    result.hook_id = hook_meta.id.clone();
    let events = hook_meta.get_events();
    result.event = if events.is_empty() {
        "Universal".to_string()
    } else {
        format!("{events:?}")
    };

    // 5. Output results
    if args.json {
        print_json_output(&result)?;
    } else {
        print_human_output(&result);
    }

    // Exit with appropriate code
    if result.decision == "block" {
        std::process::exit(2);
    }

    Ok(())
}
