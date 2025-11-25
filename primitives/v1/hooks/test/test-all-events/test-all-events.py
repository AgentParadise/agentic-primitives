#!/usr/bin/env python3
"""Test hook implementation for demonstrating all events"""
import json
import sys

def main():
    # Read event from stdin
    event_data = json.load(sys.stdin)
    
    # Just pass through with allow decision
    response = {
        "action": "allow",
        "metadata": {
            "hook_id": "test-all-events",
            "event_type": event_data.get("event", "unknown")
        }
    }
    
    print(json.dumps(response))
    return 0

if __name__ == "__main__":
    sys.exit(main())


