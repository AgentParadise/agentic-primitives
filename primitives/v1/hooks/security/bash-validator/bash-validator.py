#!/usr/bin/env python3
"""
Bash Command Validator

Specialized security hook for validating Bash commands before execution.
Detects dangerous patterns and can block risky operations.
"""

import json
import re
import sys
from typing import Dict, List, Any, Optional

from agentic_logging import get_logger

logger = get_logger(__name__)


class BashValidator:
    """Validates Bash commands for security risks"""
    
    # Dangerous command patterns
    DANGEROUS_COMMANDS = [
        r'\brm\s+-rf\s+/',  # rm -rf /
        r'\brm\s+-rf\s+\.',  # rm -rf .
        r'\brm\s+-rf\s+\.\.',  # rm -rf ..
        r'\brm\s+-rf\s+~',  # rm -rf ~
        r'\brm\s+-rf\s+\*',  # rm -rf *
        r'\bdd\s+if=.*of=/dev/(sd|hd|nvme)',  # Disk overwrite
        r'\bmkfs\.',  # Format filesystem
        r':\(\)\s*\{.*:\|:&.*\}',  # Fork bomb
        r'\bkill\s+-9\s+-1',  # Kill all processes
        r'\bchmod\s+-R\s+777\s+/',  # Overly permissive
        r'\bsudo\s+rm',  # Sudo rm (risky)
        r'\bcurl.*\|\s*bash',  # Pipe to bash (risky)
        r'\bwget.*\|\s*sh',  # Pipe to sh (risky)
        r'\bgit\s+add\s+-A\b',  # Git add all (dangerous - stages unwanted files)
        r'\bgit\s+add\s+\.\s*$',  # Git add current directory (dangerous - stages unwanted files)
    ]
    
    # Suspicious patterns (warn but don't block)
    SUSPICIOUS_PATTERNS = [
        r'>/dev/(sd|hd|nvme)',  # Direct disk write
        r'\beval\s+',  # Eval usage
        r'\$\([^\)]*\)',  # Command substitution (potential injection)
        r';\s*rm\s+-rf',  # Chained with destructive command
    ]
    
    def __init__(self):
        self.dangerous_regex = [re.compile(pattern, re.IGNORECASE) for pattern in self.DANGEROUS_COMMANDS]
        self.suspicious_regex = [re.compile(pattern, re.IGNORECASE) for pattern in self.SUSPICIOUS_PATTERNS]
    
    def validate_command(self, command: str) -> Dict[str, Any]:
        """
        Validate a Bash command
        
        Returns:
            {
                "safe": bool,
                "risk_level": "low" | "medium" | "high",
                "reason": str,
                "dangerous_patterns": List[str],
                "suspicious_patterns": List[str]
            }
        """
        dangerous_matches = []
        suspicious_matches = []
        
        # Check for dangerous patterns
        for pattern in self.dangerous_regex:
            if pattern.search(command):
                dangerous_matches.append(pattern.pattern)
        
        # Check for suspicious patterns
        for pattern in self.suspicious_regex:
            if pattern.search(command):
                suspicious_matches.append(pattern.pattern)
        
        # Determine risk level and safety
        if dangerous_matches:
            logger.warning(
                "Dangerous command pattern detected",
                extra={
                    "command_preview": command[:100],
                    "dangerous_patterns": dangerous_matches,
                }
            )
            return {
                "safe": False,
                "risk_level": "high",
                "reason": "Dangerous command pattern detected",
                "dangerous_patterns": dangerous_matches,
                "suspicious_patterns": suspicious_matches
            }
        elif len(suspicious_matches) >= 2:
            return {
                "safe": False,
                "risk_level": "medium",
                "reason": "Multiple suspicious patterns detected",
                "dangerous_patterns": [],
                "suspicious_patterns": suspicious_matches
            }
        elif suspicious_matches:
            return {
                "safe": True,  # Allow but warn
                "risk_level": "low",
                "reason": "Suspicious pattern detected (allowing with warning)",
                "dangerous_patterns": [],
                "suspicious_patterns": suspicious_matches
            }
        else:
            logger.debug(
                "Command passed security validation",
                extra={"command_preview": command[:100]}
            )
            return {
                "safe": True,
                "risk_level": "low",
                "reason": "No security concerns detected",
                "dangerous_patterns": [],
                "suspicious_patterns": []
            }


def main():
    """Main entry point"""
    try:
        # Read hook event from stdin
        input_data = sys.stdin.read()
        if not input_data:
            # No input, allow by default
            print(json.dumps({"action": "allow"}))
            return
        
        hook_event = json.loads(input_data)
        
        # Extract command from tool_input
        tool_input = hook_event.get('tool_input', {})
        
        # For Bash tool, command is in 'command' field
        command = tool_input.get('command', '')
        
        if not command:
            # No command to validate, allow
            print(json.dumps({"action": "allow"}))
            return
        
        # Validate command
        validator = BashValidator()
        result = validator.validate_command(command)
        
        # Prepare response
        if not result["safe"]:
            response = {
                "decision": "block",
                "action": "deny",
                "reason": result["reason"],
                "metadata": {
                    "hook": "bash-validator",
                    "risk_level": result["risk_level"],
                    "dangerous_patterns": result["dangerous_patterns"],
                    "suspicious_patterns": result["suspicious_patterns"],
                    "command": command[:100]  # Truncate for safety
                }
            }
        else:
            response = {
                "decision": "allow",
                "action": "allow",
                "metadata": {
                    "hook": "bash-validator",
                    "risk_level": result["risk_level"],
                    "validated": True
                }
            }
            
            # Add warning if suspicious
            if result["suspicious_patterns"]:
                response["warning"] = result["reason"]
                response["metadata"]["suspicious_patterns"] = result["suspicious_patterns"]
        
        print(json.dumps(response))
        sys.exit(0)
    
    except Exception as e:
        # On error, allow but log
        logger.error(
            "Bash validation failed, allowing by default",
            exc_info=True,
            extra={"error": str(e)}
        )
        print(json.dumps({
            "decision": "allow",
            "action": "allow",
            "error": str(e),
            "metadata": {
                "hook": "bash-validator",
                "error": "Validation failed, allowing by default"
            }
        }), file=sys.stdout)
        sys.exit(0)


if __name__ == "__main__":
    main()

