#!/usr/bin/env python3
"""
Claude Code Hooks Integration Example

This example demonstrates how hooks work with Claude Code.
Since hooks are triggered by the Claude Code extension (not Python SDK directly),
this script simulates hook execution to show the flow.

To test with REAL Claude Code:
1. Copy .claude/ to a VS Code project
2. Open in VS Code/Cursor with Claude Code extension
3. Ask Claude to execute commands
4. Watch hooks fire and analytics collect
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any

# Example scenarios that would trigger hooks
SCENARIOS = {
    "dangerous-bash": {
        "description": "Dangerous bash command that should be blocked",
        "event": "PreToolUse",
        "tool": "Bash",
        "input": {"command": "rm -rf /"},
        "expected_decision": "block",
    },
    "safe-bash": {
        "description": "Safe bash command",
        "event": "PreToolUse",
        "tool": "Bash",
        "input": {"command": "ls -la"},
        "expected_decision": "allow",
    },
    "sensitive-file": {
        "description": "Attempt to read sensitive file",
        "event": "PreToolUse",
        "tool": "Read",
        "input": {"file_path": ".env"},
        "expected_decision": "block",
    },
    "normal-file": {
        "description": "Normal file operation",
        "event": "PreToolUse",
        "tool": "Write",
        "input": {"file_path": "src/main.py", "contents": "print('Hello')"},
        "expected_decision": "allow",
    },
    "pii-prompt": {
        "description": "Prompt containing PII",
        "event": "UserPromptSubmit",
        "tool": None,
        "input": {"prompt": "Add my email john.doe@company.com to the config"},
        "expected_decision": "allow",  # Warns but allows
    },
    "normal-prompt": {
        "description": "Normal prompt",
        "event": "UserPromptSubmit",
        "tool": None,
        "input": {"prompt": "Write a Python script that prints Hello World"},
        "expected_decision": "allow",
    },
}


def create_hook_event(scenario: Dict[str, Any]) -> Dict[str, Any]:
    """Create a Claude hook event from scenario"""
    event = {
        "session_id": "example-session-001",
        "transcript_path": str(Path.home() / ".claude/projects/example/session.jsonl"),
        "cwd": str(Path.cwd()),
        "permission_mode": "default",
        "hook_event_name": scenario["event"],
    }
    
    if scenario["tool"]:
        event["tool_name"] = scenario["tool"]
        event["tool_input"] = scenario["input"]
        event["tool_use_id"] = f"toolu_example_{scenario['tool']}"
    elif scenario["event"] == "UserPromptSubmit":
        event["prompt"] = scenario["input"]["prompt"]
    
    return event


def test_hook(hook_path: Path, event: Dict[str, Any], expected: str) -> Dict[str, Any]:
    """Test a hook with an event"""
    if not hook_path.exists():
        return {
            "success": False,
            "error": f"Hook not found: {hook_path}",
        }
    
    try:
        # Run hook with event as stdin
        result = subprocess.run(
            [str(hook_path)],
            input=json.dumps(event).encode(),
            capture_output=True,
            timeout=10,
        )
        
        if result.returncode != 0:
            return {
                "success": False,
                "error": f"Hook failed with code {result.returncode}",
                "stderr": result.stderr.decode(),
            }
        
        # Parse output
        try:
            output = json.loads(result.stdout.decode())
            decision = output.get("decision", "allow")
            
            return {
                "success": True,
                "decision": decision,
                "expected": expected,
                "matched": decision == expected,
                "output": output,
            }
        except json.JSONDecodeError:
            # Some hooks might not return JSON (just allow/block)
            return {
                "success": True,
                "decision": "allow",  # Assume allow if no JSON
                "expected": expected,
                "matched": True,
                "output": result.stdout.decode(),
            }
    
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Hook execution timed out",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def print_result(hook_name: str, scenario_name: str, scenario: Dict[str, Any], result: Dict[str, Any]):
    """Print test result"""
    print(f"\n{'='*60}")
    print(f"Scenario: {scenario_name}")
    print(f"Description: {scenario['description']}")
    print(f"Hook: {hook_name}")
    print(f"Event: {scenario['event']}")
    if scenario['tool']:
        print(f"Tool: {scenario['tool']}")
    print(f"{'='*60}")
    
    if not result["success"]:
        print(f"❌ FAILED: {result['error']}")
        if "stderr" in result:
            print(f"stderr: {result['stderr']}")
        return
    
    decision = result["decision"]
    expected = result["expected"]
    matched = result["matched"]
    
    if matched:
        icon = "✅" if decision == "allow" else "🛡️"
        print(f"{icon} Decision: {decision.upper()} (as expected)")
    else:
        print(f"⚠️  Decision: {decision.upper()} (expected {expected.upper()})")
    
    if isinstance(result["output"], dict):
        if "reason" in result["output"]:
            print(f"Reason: {result['output']['reason']}")
        if "alternative" in result["output"]:
            print(f"Alternative: {result['output']['alternative']}")
        if "warning" in result["output"]:
            print(f"⚠️  Warning: {result['output']['warning']}")


def main():
    parser = argparse.ArgumentParser(description="Test Claude Code hooks")
    parser.add_argument(
        "--scenario",
        choices=list(SCENARIOS.keys()) + ["all"],
        default="all",
        help="Scenario to test (default: all)",
    )
    parser.add_argument(
        "--hook",
        choices=["bash-validator", "file-security", "prompt-filter", "hooks-collector", "all"],
        default="all",
        help="Hook to test (default: all)",
    )
    args = parser.parse_args()
    
    # Get hooks directory
    example_dir = Path(__file__).parent
    hooks_dir = example_dir / ".claude" / "hooks"
    
    if not hooks_dir.exists():
        print(f"❌ Hooks directory not found: {hooks_dir}")
        print("\nRun this first:")
        print("  cd ../.. && cargo run --manifest-path cli/Cargo.toml -- build --provider claude")
        print("  cp -r build/claude/.claude examples/000-claude-integration/")
        sys.exit(1)
    
    # Select scenarios
    scenarios_to_test = (
        SCENARIOS.items() if args.scenario == "all"
        else [(args.scenario, SCENARIOS[args.scenario])]
    )
    
    # Select hooks
    hooks_to_test = {
        "bash-validator": hooks_dir / "security" / "bash-validator.py",
        "file-security": hooks_dir / "security" / "file-security.py",
        "prompt-filter": hooks_dir / "security" / "prompt-filter.py",
        "hooks-collector": hooks_dir / "core" / "hooks-collector.py",
    }
    
    if args.hook != "all":
        hooks_to_test = {args.hook: hooks_to_test[args.hook]}
    
    print("\n" + "="*60)
    print(" Claude Code Hooks Integration Test")
    print("="*60)
    print(f"\nTesting {len(scenarios_to_test)} scenario(s) with {len(hooks_to_test)} hook(s)")
    
    # Test each combination
    total_tests = 0
    passed_tests = 0
    
    for scenario_name, scenario in scenarios_to_test:
        event = create_hook_event(scenario)
        
        for hook_name, hook_path in hooks_to_test.items():
            # Skip irrelevant combinations
            if scenario["event"] == "UserPromptSubmit" and hook_name in ["bash-validator", "file-security"]:
                continue
            if scenario["tool"] == "Bash" and hook_name == "file-security":
                continue
            if scenario["tool"] in ["Read", "Write", "Edit", "Delete"] and hook_name == "bash-validator":
                continue
            
            total_tests += 1
            result = test_hook(hook_path, event, scenario["expected_decision"])
            print_result(hook_name, scenario_name, scenario, result)
            
            if result.get("success") and result.get("matched"):
                passed_tests += 1
    
    # Summary
    print(f"\n{'='*60}")
    print(f" Test Summary")
    print(f"{'='*60}")
    print(f"Total: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {total_tests - passed_tests}")
    print(f"Success Rate: {(passed_tests/total_tests*100):.1f}%")
    
    # Check analytics
    analytics_file = example_dir / ".agentic" / "analytics" / "events.jsonl"
    if analytics_file.exists():
        with open(analytics_file) as f:
            event_count = sum(1 for _ in f)
        print(f"\nAnalytics: {event_count} events logged to {analytics_file}")
    else:
        print(f"\nAnalytics: No events yet (file will be created on first hook execution)")
    
    print("\n" + "="*60)
    print(" Next Steps")
    print("="*60)
    print("\nTo test with REAL Claude Code:")
    print("1. Copy .claude/ to a VS Code project")
    print("2. Open in VS Code/Cursor with Claude Code extension")
    print("3. Ask Claude to execute commands")
    print("4. Watch hooks fire and analytics collect")
    print(f"\nAnalytics will be written to: {analytics_file}")
    print("\nView analytics:")
    print(f"  cat {analytics_file} | jq '.'")
    print("\n" + "="*60)


if __name__ == "__main__":
    main()


