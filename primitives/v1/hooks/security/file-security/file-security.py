#!/usr/bin/env python3
"""
File Security Hook with Smart Redaction

Instead of blocking sensitive files, this hook:
- Allows reading sensitive files (.env, .key, etc.)
- REDACTS sensitive values with hash + length
- Enables AI to know IF content changed and HOW LONG values are
- Maintains security while providing useful metadata
"""

import json
import sys
import re
import hashlib
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

from agentic_logging import get_logger

logger = get_logger(__name__)


class FileSecurityHook:
    """Smart file security with value redaction"""
    
    # Patterns for sensitive files that need redaction
    SENSITIVE_FILE_PATTERNS = [
        r'\.env$',
        r'\.env\.',
        r'\.aws/credentials',
        r'\.aws/config',
        r'\.ssh/.*',
        r'id_rsa',
        r'id_ed25519',
        r'\.pem$',
        r'\.key$',
        r'\.crt$',
        r'\.cert$',
        r'password',
        r'secret',
        r'token',
        r'api[_-]?key',
        r'credentials',
    ]
    
    # Patterns to detect key=value pairs that need redaction
    VALUE_PATTERNS = [
        # Standard KEY=VALUE
        (r'^([A-Z_][A-Z0-9_]*)\s*=\s*(.+)$', 'env'),
        # JSON keys
        (r'"([^"]+)"\s*:\s*"([^"]*)"', 'json'),
        # YAML keys
        (r'^(\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(.+)$', 'yaml'),
        # INI format [section] key=value
        (r'^([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.*)$', 'ini'),
    ]
    
    # Keywords that indicate sensitive values
    SENSITIVE_KEYWORDS = [
        'password', 'secret', 'token', 'key', 'api', 'auth',
        'credential', 'private', 'pass', 'pwd', 'bearer',
    ]
    
    def __init__(self):
        self.sensitive_regex = [
            re.compile(pattern, re.IGNORECASE) 
            for pattern in self.SENSITIVE_FILE_PATTERNS
        ]
    
    def is_sensitive_file(self, file_path: str) -> bool:
        """Check if file matches sensitive patterns"""
        for pattern in self.sensitive_regex:
            if pattern.search(file_path):
                return True
        return False
    
    def is_sensitive_key(self, key: str) -> bool:
        """Check if key name indicates sensitive data"""
        key_lower = key.lower()
        return any(keyword in key_lower for keyword in self.SENSITIVE_KEYWORDS)
    
    def hash_value(self, value: str) -> str:
        """Create SHA256 hash of value (first 12 chars)"""
        return hashlib.sha256(value.encode()).hexdigest()[:12]
    
    def redact_value(self, value: str) -> Dict[str, Any]:
        """
        Redact a value but provide hash and length
        
        Returns: {
            "redacted": true,
            "hash": "abc123...",  # First 12 chars of SHA256
            "length": 42,
            "original": "[REDACTED]"
        }
        """
        return {
            "redacted": True,
            "hash": self.hash_value(value),
            "length": len(value),
            "original": "[REDACTED]"
        }
    
    def redact_line(self, line: str) -> Tuple[str, bool]:
        """
        Redact sensitive values in a line
        
        Returns: (redacted_line, was_redacted)
        """
        # Try each pattern
        for pattern, format_type in self.VALUE_PATTERNS:
            match = re.match(pattern, line)
            if match:
                if format_type == 'env':
                    key, value = match.groups()
                    if self.is_sensitive_key(key) and value.strip():
                        redact_info = self.redact_value(value.strip())
                        redacted_line = f"{key}=[REDACTED:hash={redact_info['hash']},len={redact_info['length']}]"
                        return redacted_line, True
                
                elif format_type == 'json':
                    key, value = match.groups()
                    if self.is_sensitive_key(key):
                        redact_info = self.redact_value(value)
                        redacted_line = line.replace(
                            f'"{value}"',
                            f'"[REDACTED:hash={redact_info["hash"]},len={redact_info["length"]}]"'
                        )
                        return redacted_line, True
                
                elif format_type == 'yaml':
                    indent, key, value = match.groups()
                    if self.is_sensitive_key(key):
                        redact_info = self.redact_value(value.strip())
                        redacted_line = f"{indent}{key}: [REDACTED:hash={redact_info['hash']},len={redact_info['length']}]"
                        return redacted_line, True
                
                elif format_type == 'ini':
                    key, value = match.groups()
                    if self.is_sensitive_key(key) and value.strip():
                        redact_info = self.redact_value(value.strip())
                        redacted_line = f"{key}=[REDACTED:hash={redact_info['hash']},len={redact_info['length']}]"
                        return redacted_line, True
        
        return line, False
    
    def redact_content(self, content: str) -> Tuple[str, Dict[str, Any]]:
        """
        Redact sensitive values from file content
        
        Returns: (redacted_content, metadata)
        """
        lines = content.split('\n')
        redacted_lines = []
        redaction_count = 0
        redacted_keys = []
        
        for line in lines:
            redacted_line, was_redacted = self.redact_line(line)
            redacted_lines.append(redacted_line)
            
            if was_redacted:
                redaction_count += 1
                # Extract key name for metadata
                for pattern, _ in self.VALUE_PATTERNS:
                    match = re.match(pattern, line)
                    if match:
                        key = match.groups()[0] if format == 'yaml' else match.groups()[0]
                        if isinstance(key, str):
                            key = key.strip()
                            if key not in redacted_keys:
                                redacted_keys.append(key)
                        break
        
        metadata = {
            "redacted": redaction_count > 0,
            "redaction_count": redaction_count,
            "redacted_keys": redacted_keys,
            "total_lines": len(lines),
        }
        
        return '\n'.join(redacted_lines), metadata


def main():
    """Main hook entry point"""
    try:
        # Read hook event from stdin
        input_data = sys.stdin.read()
        if not input_data:
            print(json.dumps({"action": "allow"}))
            return
        
        hook_event = json.loads(input_data)
        
        # Extract file path from tool_input
        tool_input = hook_event.get('tool_input', {})
        file_path = tool_input.get('path', '') or tool_input.get('file_path', '')
        
        if not file_path:
            # No file path, allow
            print(json.dumps({"action": "allow"}))
            return
        
        hook = FileSecurityHook()
        
        # Check if this is a sensitive file
        if not hook.is_sensitive_file(file_path):
            # Not sensitive, allow as-is
            logger.debug("File not sensitive, allowing", extra={"file_path": file_path})
            print(json.dumps({
                "action": "allow",
                "metadata": {
                    "hook": "file-security",
                    "sensitive": False,
                    "file_path": file_path
                }
            }))
            return
        
        # Sensitive file - check if reading or writing
        tool_name = hook_event.get('tool_name', '')
        
        # For read operations, allow with redaction
        if tool_name in ['Read', 'read', 'ReadFile', 'read_file']:
            logger.info(
                "Sensitive file read with redaction",
                extra={"file_path": file_path, "tool_name": tool_name}
            )
            print(json.dumps({
                "action": "allow",
                "transform": "redact",
                "metadata": {
                    "hook": "file-security",
                    "sensitive": True,
                    "file_path": file_path,
                    "redaction_enabled": True
                },
                "warning": f"Sensitive file detected: {file_path}. Values will be redacted with hash+length."
            }))
            return
        
        # For write operations to sensitive files, warn but allow
        # (developers may legitimately need to update .env files)
        if tool_name in ['Write', 'write', 'WriteFile', 'write_file', 'Edit', 'edit']:
            logger.warning(
                "Sensitive file write operation",
                extra={"file_path": file_path, "tool_name": tool_name}
            )
            print(json.dumps({
                "action": "allow",
                "metadata": {
                    "hook": "file-security",
                    "sensitive": True,
                    "file_path": file_path,
                    "operation": "write"
                },
                "warning": f"Writing to sensitive file: {file_path}. Ensure no secrets are exposed."
            }))
            return
        
        # For other operations, allow with warning
        print(json.dumps({
            "action": "allow",
            "metadata": {
                "hook": "file-security",
                "sensitive": True,
                "file_path": file_path
            },
            "warning": f"Accessing sensitive file: {file_path}"
        }))
    
    except Exception as e:
        # On error, allow but log
        print(json.dumps({
            "action": "allow",
            "error": str(e),
            "metadata": {
                "hook": "file-security",
                "error": "Validation failed, allowing by default"
            }
        }))
    
    sys.exit(0)


if __name__ == "__main__":
    main()
