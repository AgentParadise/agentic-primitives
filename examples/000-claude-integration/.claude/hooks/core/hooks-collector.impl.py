#!/usr/bin/env python3
"""
Universal Hooks Collector Orchestrator

Generic hook orchestrator that works with ANY agent provider.
Routes events through a configurable middleware pipeline.

Architecture:
- Reads hook event from stdin (JSON with event_type, event_data, etc.)
- Loads middleware config from YAML at runtime
- Executes only enabled middleware in priority order
- Generic - works for ANY event type
- Fail-safe - errors don't block agent
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


class HooksCollectorOrchestrator:
    """Generic orchestrator for middleware pipeline"""
    
    def __init__(self, hook_dir: Path, agent_config: Optional[Dict] = None):
        self.hook_dir = hook_dir
        self.agent_config = agent_config
        
        # Use injected config if provided, otherwise load from YAML (fallback)
        if agent_config:
            self.config = agent_config
            self.middleware = self.load_middleware_from_config(agent_config)
        else:
            self.config = self.load_config_from_yaml()
            self.middleware = self.load_middleware_config()
    
    def load_config_from_yaml(self) -> Dict:
        """Load hook configuration from YAML (fallback for backward compat)"""
        config_file = self.hook_dir / "hooks-collector.hook.yaml"
        if not config_file.exists():
            # Fallback for when run from build directory
            config_file = self.hook_dir.parent.parent.parent.parent.parent.parent / \
                         "primitives" / "v1" / "hooks" / "core" / "hooks-collector" / \
                         "hooks-collector.hook.yaml"
        
        with open(config_file) as f:
            return yaml.safe_load(f)
    
    def load_middleware_from_config(self, config: Dict) -> List[Dict]:
        """Load middleware from agent-specific config"""
        middleware = config.get('middleware', [])
        
        # Filter to enabled only
        enabled = [m for m in middleware if m.get('enabled', True)]
        
        # Sort by priority (lower = earlier)
        enabled.sort(key=lambda m: m.get('priority', 100))
        
        return enabled
    
    def load_middleware_config(self) -> List[Dict]:
        """Get enabled middleware in priority order (legacy)"""
        middleware = self.config.get('middleware', [])
        
        # Filter to enabled only
        enabled = [m for m in middleware if m.get('enabled', True)]
        
        # Sort by priority (lower = earlier)
        enabled.sort(key=lambda m: m.get('priority', 100))
        
        return enabled
    
    def filter_middleware_for_event(self, event_type: str) -> List[Dict]:
        """Filter middleware that should run for this event type"""
        filtered = []
        
        for mw in self.middleware:
            events = mw.get('events', ['*'])
            
            # If middleware supports all events or this specific event
            if '*' in events or event_type in events:
                filtered.append(mw)
        
        return filtered
    
    async def run_middleware(
        self, 
        middleware_def: Dict,
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a single middleware"""
        # Resolve middleware path relative to hook directory
        middleware_path = self.hook_dir / middleware_def['path']
        
        # Check if services directory has pyproject.toml for UV
        services_dir = middleware_path.parent.parent
        use_uv = (services_dir / "pyproject.toml").exists()
        
        if use_uv:
            cmd = ["uv", "run", "--directory", str(services_dir), 
                   "python3", str(middleware_path)]
        else:
            cmd = [sys.executable, str(middleware_path)]
        
        # Execute middleware
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        input_json = json.dumps(input_data).encode()
        stdout, stderr = await process.communicate(input=input_json)
        
        if process.returncode != 0:
            raise RuntimeError(
                f"Middleware '{middleware_def['id']}' failed: {stderr.decode()}"
            )
        
        return json.loads(stdout.decode()) if stdout else {}
    
    async def execute(self, hook_event: Dict[str, Any]) -> Dict:
        """Execute middleware pipeline"""
        try:
            current_data = hook_event
            
            # Determine event type for filtering
            event_type = hook_event.get('event_type') or hook_event.get('type') or 'unknown'
            
            # Filter middleware for this event type
            middleware_to_run = self.filter_middleware_for_event(event_type)
            
            executed_middleware = []
            
            # Execute each middleware in order
            for middleware_def in middleware_to_run:
                try:
                    current_data = await self.run_middleware(
                        middleware_def,
                        current_data
                    )
                    executed_middleware.append(middleware_def['id'])
                except Exception as e:
                    # Log but continue (fail-safe)
                    print(
                        f"⚠️  Middleware '{middleware_def['id']}' failed: {e}",
                        file=sys.stderr
                    )
                    # Safety middleware failures should block
                    if middleware_def.get('type') == 'safety':
                        return {
                            "action": "deny",
                            "reason": f"Safety check failed: {e}"
                        }
            
            # Return default decision
            return {
                "action": self.config.get('default_decision', 'allow'),
                "metadata": {
                    "hook": "hooks-collector",
                    "event_type": event_type,
                    "middleware_available": len(self.middleware),
                    "middleware_filtered": len(middleware_to_run),
                    "middleware_executed": executed_middleware
                }
            }
        
        except Exception as e:
            print(f"❌ Pipeline failed: {e}", file=sys.stderr)
            # Fail-safe: always allow on error
            return {"action": "allow", "error": str(e)}


async def main():
    """Main entry point"""
    try:
        input_data = sys.stdin.read()
        if not input_data:
            print(json.dumps({"action": "allow"}))
            return
        
        hook_event = json.loads(input_data)
        hook_dir = Path(__file__).parent
        
        # Extract agent-specific config if embedded by wrapper
        agent_config = hook_event.pop('__agent_config__', None)
        
        # Create orchestrator with injected config (if available)
        orchestrator = HooksCollectorOrchestrator(hook_dir, agent_config=agent_config)
        result = await orchestrator.execute(hook_event)
        
        print(json.dumps(result))
        sys.exit(0)
    
    except Exception as e:
        print(json.dumps({"action": "allow", "error": str(e)}))
        sys.exit(0)  # Always exit 0 - hooks never block agent


if __name__ == "__main__":
    asyncio.run(main())


