#!/usr/bin/env python3
"""
Wrapper script for analytics event validation.

This script imports the validation utilities from the agentic_analytics library.
For the full implementation, see: lib/python/agentic_analytics/agentic_analytics/validation.py

Usage:
    python validate_events.py [jsonl_path]
    python validate_events.py .agentic/analytics/events.jsonl
    python validate_events.py --require-hooks bash-validator,file-security --verbose
"""

from agentic_analytics.validation import main

if __name__ == "__main__":
    main()
