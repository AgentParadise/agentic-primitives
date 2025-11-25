#!/usr/bin/env python3
"""File Security Validator - Protects sensitive files and validates paths"""
import json
import sys
import re
from pathlib import Path


class FileSecurityValidator:
    SENSITIVE_PATTERNS = [
        r'\.env', r'\.aws/credentials', r'\.ssh/id_rsa', r'id_ed25519',
        r'\.pem$', r'\.key$', r'password', r'secret', r'token', r'api_key'
    ]
    
    PROTECTED_PATHS = [
        '/etc/passwd', '/etc/shadow', '/boot/', '/sys/', '/proc/'
    ]
    
    def validate_path(self, file_path: str) -> dict:
        # Check sensitive patterns
        for pattern in self.SENSITIVE_PATTERNS:
            if re.search(pattern, file_path, re.IGNORECASE):
                return {"safe": False, "reason": f"Sensitive file pattern: {pattern}"}
        
        # Check protected paths
        for protected in self.PROTECTED_PATHS:
            if file_path.startswith(protected):
                return {"safe": False, "reason": f"Protected system path: {protected}"}
        
        return {"safe": True, "reason": "Path validated"}


def main():
    try:
        input_data = sys.stdin.read()
        if not input_data:
            print(json.dumps({"action": "allow"}))
            return
        
        hook_event = json.loads(input_data)
        tool_input = hook_event.get('tool_input', {})
        file_path = tool_input.get('path', '') or tool_input.get('file_path', '')
        
        if not file_path:
            print(json.dumps({"action": "allow"}))
            return
        
        validator = FileSecurityValidator()
        result = validator.validate_path(file_path)
        
        if not result["safe"]:
            print(json.dumps({
                "action": "deny",
                "reason": result["reason"],
                "metadata": {"hook": "file-security", "path": file_path[:100]}
            }))
        else:
            print(json.dumps({
                "action": "allow",
                "metadata": {"hook": "file-security", "validated": True}
            }))
    except Exception as e:
        print(json.dumps({"action": "allow", "error": str(e)}))
    
    sys.exit(0)


if __name__ == "__main__":
    main()

