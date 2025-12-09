#!/usr/bin/env python3
"""
PII (Personally Identifiable Information) Validator

Atomic validator that detects PII patterns in user prompts.
Pure function - no side effects, no analytics, no stdin/stdout handling.

Patterns are loaded from patterns/pii.patterns.yaml for easier maintenance.
"""

import re
from pathlib import Path
from typing import Any

# Load patterns from YAML file
PATTERNS_FILE = Path(__file__).parent / "patterns" / "pii.patterns.yaml"

# Try to load from YAML, fall back to hardcoded patterns
try:
    from ..pattern_loader import load_pii_patterns

    PII_PATTERNS, CONTEXT_PATTERNS = load_pii_patterns(PATTERNS_FILE)
except (ImportError, FileNotFoundError):
    # Fallback to hardcoded patterns
    _PII_RAW: list[tuple[str, str, str]] = [
        (r"\b\d{3}-\d{2}-\d{4}\b", "SSN", "high"),
        (r"\b\d{9}\b", "potential SSN (9 digits)", "medium"),
        (
            r"\b4[0-9]{3}[-\s]?[0-9]{4}[-\s]?[0-9]{4}[-\s]?[0-9]{1,4}\b",
            "Visa card",
            "high",
        ),
        (r"\b4[0-9]{12}(?:[0-9]{3})?\b", "Visa card", "high"),
        (
            r"\b5[1-5][0-9]{2}[-\s]?[0-9]{4}[-\s]?[0-9]{4}[-\s]?[0-9]{4}\b",
            "Mastercard",
            "high",
        ),
        (r"\b5[1-5][0-9]{14}\b", "Mastercard", "high"),
        (r"\b3[47][0-9]{2}[-\s]?[0-9]{6}[-\s]?[0-9]{5}\b", "Amex card", "high"),
        (r"\b3[47][0-9]{13}\b", "Amex card", "high"),
        (
            r"\b6(?:011|5[0-9]{2})[-\s]?[0-9]{4}[-\s]?[0-9]{4}[-\s]?[0-9]{4}\b",
            "Discover card",
            "high",
        ),
        (r"\b6(?:011|5[0-9]{2})[0-9]{12}\b", "Discover card", "high"),
        (
            r"\b(?:\+1[-.\s]?)?\(?[2-9]\d{2}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
            "US phone number",
            "medium",
        ),
        (
            r"\b\+\d{1,3}[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}\b",
            "international phone",
            "medium",
        ),
        (
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            "email address",
            "low",
        ),
        (r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "IP address", "low"),
        (
            r"\b(?:0?[1-9]|1[0-2])[/-](?:0?[1-9]|[12]\d|3[01])[/-](?:19|20)\d{2}\b",
            "date (MM/DD/YYYY)",
            "low",
        ),
        (
            r"\b(?:19|20)\d{2}[/-](?:0?[1-9]|1[0-2])[/-](?:0?[1-9]|[12]\d|3[01])\b",
            "date (YYYY-MM-DD)",
            "low",
        ),
        (r"\b[A-Z]{1,2}\d{6,9}\b", "potential passport number", "medium"),
        (r"\b[A-Z]\d{7,8}\b", "potential DL number", "low"),
    ]

    _CONTEXT_RAW: list[tuple[str, str]] = [
        (r"\bmy\s+(?:ssn|social\s+security)", "SSN context"),
        (r"\bmy\s+(?:credit\s+card|cc\s+number)", "credit card context"),
        (r"\bmy\s+(?:phone|cell|mobile)\s+(?:number|#)", "phone context"),
        (r"\bmy\s+(?:address|home\s+address)", "address context"),
        (r"\bmy\s+(?:password|passwd|pwd)", "password context"),
        (r"\bmy\s+(?:bank\s+account|routing\s+number)", "banking context"),
    ]

    PII_PATTERNS = [(re.compile(p, re.IGNORECASE), d, r) for p, d, r in _PII_RAW]
    CONTEXT_PATTERNS = [(re.compile(p, re.IGNORECASE), d) for p, d in _CONTEXT_RAW]


def validate(
    tool_input: dict[str, Any], context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Validate a prompt for PII patterns.

    Args:
        tool_input: {"prompt": "user prompt text"}
        context: Optional context

    Returns:
        {"safe": bool, "reason": str | None, "metadata": dict | None}
    """
    prompt = tool_input.get("prompt", "")

    if not prompt:
        return {"safe": True}

    detected_pii: list[dict[str, str | int]] = []
    highest_risk = "none"
    risk_order = {"none": 0, "low": 1, "medium": 2, "high": 3}

    # Check for PII patterns (patterns are pre-compiled with flags)
    for pattern, pii_type, risk_level in PII_PATTERNS:
        matches = pattern.findall(prompt)
        if matches:
            detected_pii.append(
                {
                    "type": pii_type,
                    "risk": risk_level,
                    "count": len(matches),
                }
            )
            if risk_order.get(risk_level, 0) > risk_order.get(highest_risk, 0):
                highest_risk = risk_level

    # Check for context patterns (these raise awareness but don't block)
    detected_context: list[str] = []
    for pattern, context_type in CONTEXT_PATTERNS:
        if pattern.search(prompt):
            detected_context.append(context_type)

    # Determine action based on risk level
    if highest_risk == "high":
        pii_types = [str(p["type"]) for p in detected_pii if p["risk"] == "high"]
        return {
            "safe": False,
            "reason": f"High-risk PII detected: {', '.join(pii_types)}",
            "metadata": {
                "detected_pii": detected_pii,
                "detected_context": detected_context,
                "risk_level": "high",
                "prompt_length": len(prompt),
            },
        }

    # Medium/low risk: allow but log
    metadata: dict[str, Any] = {
        "risk_level": highest_risk,
        "prompt_length": len(prompt),
    }

    if detected_pii:
        metadata["detected_pii"] = detected_pii

    if detected_context:
        metadata["detected_context"] = detected_context

    return {
        "safe": True,
        "reason": None,
        "metadata": metadata if (detected_pii or detected_context) else None,
    }


# Standalone testing
if __name__ == "__main__":
    import json
    import sys

    input_data = ""
    if not sys.stdin.isatty():
        input_data = sys.stdin.read()

    if input_data:
        tool_input = json.loads(input_data)
        result = validate(tool_input)
        print(json.dumps(result))
    else:
        print(json.dumps({"safe": True, "message": "No input provided"}))
