#!/usr/bin/env python3
"""Prompt Filter - Detects sensitive data in prompts"""
import json
import sys
import re


class PromptFilter:
    PATTERNS = [
        (r'\b[A-Z0-9]{20,}\b', 'API_KEY'),
        (r'\b\d{3}-\d{2}-\d{4}\b', 'SSN'),
        (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', 'EMAIL'),
        (r'password\s*[:=]\s*\S+', 'PASSWORD'),
    ]
    
    def scan(self, text: str) -> dict:
        findings = []
        for pattern, label in self.PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                findings.append({"type": label, "count": len(matches)})
        return {"found": len(findings) > 0, "findings": findings}


def main():
    try:
        input_data = sys.stdin.read()
        if not input_data:
            print(json.dumps({"action": "allow"}))
            return
        
        hook_event = json.loads(input_data)
        prompt = hook_event.get('prompt', '') or hook_event.get('text', '')
        
        filter = PromptFilter()
        result = filter.scan(prompt)
        
        if result["found"]:
            print(json.dumps({
                "action": "allow",
                "warning": "Sensitive data detected in prompt",
                "metadata": {"hook": "prompt-filter", "findings": result["findings"]}
            }))
        else:
            print(json.dumps({"action": "allow"}))
    except Exception as e:
        print(json.dumps({"action": "allow", "error": str(e)}))
    
    sys.exit(0)


if __name__ == "__main__":
    main()

