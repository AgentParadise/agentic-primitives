#!/usr/bin/env python3
"""
Prompt Filter - Detects sensitive data in prompts

Scans user prompts for PII, API keys, passwords, and other sensitive data.
Allows prompts but warns about detected patterns.

Each decision is logged to the analytics service for audit trail.
"""

import json
import re
import sys
from typing import Any

# Import analytics client for self-logging
try:
    from agentic_analytics import AnalyticsClient, HookDecision
    analytics = AnalyticsClient()
except ImportError:
    # Fallback if analytics not installed
    analytics = None  # type: ignore[assignment]
    HookDecision = None  # type: ignore[assignment, misc]


class PromptFilter:
    """Scans prompts for sensitive data patterns."""

    PATTERNS = [
        (r'\b[A-Z0-9]{20,}\b', 'API_KEY'),
        (r'\b\d{3}-\d{2}-\d{4}\b', 'SSN'),
        (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', 'EMAIL'),
        (r'password\s*[:=]\s*\S+', 'PASSWORD'),
        (r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b', 'CREDIT_CARD'),
        (r'sk-[a-zA-Z0-9]{48}', 'OPENAI_KEY'),
        (r'ghp_[a-zA-Z0-9]{36}', 'GITHUB_TOKEN'),
    ]

    def scan(self, text: str) -> dict[str, Any]:
        """Scan text for sensitive data patterns."""
        findings = []
        for pattern, label in self.PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                findings.append({"type": label, "count": len(matches)})
        return {"found": len(findings) > 0, "findings": findings}


def _log_analytics(
    hook_event: dict[str, Any],
    decision: str,
    findings: list[dict[str, Any]],
) -> None:
    """Log decision to analytics service (fail-safe)."""
    if not analytics or not HookDecision:
        return
    try:
        analytics.log(HookDecision(
            hook_id="prompt-filter",
            event_type=hook_event.get("hook_event_name", "UserPromptSubmit"),
            decision=decision,  # type: ignore[arg-type]
            session_id=hook_event.get("session_id", "unknown"),
            tool_name=None,  # Prompt filter doesn't involve tools
            reason="Sensitive data detected in prompt" if findings else None,
            metadata={
                "findings": findings,
                "findings_count": len(findings),
            },
        ))
    except Exception:
        # Never block on analytics failure
        pass


def main() -> None:
    """Main hook entry point."""
    try:
        input_data = sys.stdin.read()
        if not input_data:
            print(json.dumps({"action": "allow"}))
            return

        hook_event = json.loads(input_data)
        prompt = hook_event.get('prompt', '') or hook_event.get('text', '')

        filter_instance = PromptFilter()
        result = filter_instance.scan(prompt)

        if result["found"]:
            # Log as warning (allow with warning)
            _log_analytics(hook_event, "warn", result["findings"])
            print(json.dumps({
                "action": "allow",
                "decision": "allow",
                "warning": "Sensitive data detected in prompt",
                "metadata": {
                    "hook": "prompt-filter",
                    "findings": result["findings"],
                }
            }))
        else:
            # Log as allow
            _log_analytics(hook_event, "allow", [])
            print(json.dumps({
                "action": "allow",
                "decision": "allow",
                "metadata": {
                    "hook": "prompt-filter",
                }
            }))
    except Exception as e:
        print(json.dumps({
            "action": "allow",
            "decision": "allow",
            "error": str(e),
            "metadata": {
                "hook": "prompt-filter",
                "error": "Scan failed, allowing by default",
            }
        }))

    sys.exit(0)


if __name__ == "__main__":
    main()
