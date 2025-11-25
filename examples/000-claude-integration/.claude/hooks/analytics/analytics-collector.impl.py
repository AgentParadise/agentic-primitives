#!/usr/bin/env python3
"""
Analytics Collector Hook Orchestrator

This is the main entry point for the analytics-collector hook primitive.
It orchestrates the analytics middleware pipeline:
1. Receives hook event from stdin (JSON)
2. Executes event normalizer middleware
3. Executes event publisher middleware
4. Returns result to stdout

The hook is designed to be non-blocking and fail-safe - analytics failures
never prevent the agent from continuing its work.
"""

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional


class AnalyticsHookOrchestrator:
    """Orchestrates the analytics middleware pipeline"""

    def __init__(self, hook_dir: Path):
        """Initialize orchestrator

        Args:
            hook_dir: Path to the analytics-collector hook directory
        """
        self.hook_dir = hook_dir
        self.services_dir = hook_dir.parent.parent.parent.parent.parent / "services" / "analytics"
        self.normalizer_path = self.services_dir / "middleware" / "event_normalizer.py"
        self.publisher_path = self.services_dir / "middleware" / "event_publisher.py"

    async def run_middleware(
        self,
        middleware_path: Path,
        input_data: Dict[str, Any],
        env: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Run a middleware script with input data

        Args:
            middleware_path: Path to middleware script
            input_data: Input data to pass via stdin
            env: Optional environment variables

        Returns:
            Output data from middleware stdout

        Raises:
            RuntimeError: If middleware fails
        """
        if not middleware_path.exists():
            raise RuntimeError(f"Middleware not found: {middleware_path}")

        # Prepare environment
        import os
        middleware_env = os.environ.copy()
        if env:
            middleware_env.update(env)

        # Run middleware using uv (if available) or system python
        # Check if we're in the services/analytics directory with uv
        # middleware_path is services/analytics/middleware/event_normalizer.py
        # So parent.parent is services/analytics/
        services_analytics = middleware_path.parent.parent
        use_uv = (services_analytics / "pyproject.toml").exists()
        
        if use_uv:
            # Use uv to run with the correct environment
            cmd = ["uv", "run", "--directory", str(services_analytics), "python3", str(middleware_path)]
        else:
            # Fall back to system python
            cmd = [sys.executable, str(middleware_path)]
        
        # Run middleware
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=middleware_env,
            )

            # Send input and get output
            input_json = json.dumps(input_data).encode("utf-8")
            stdout, stderr = await process.communicate(input=input_json)

            # Check for errors
            if process.returncode != 0:
                error_msg = stderr.decode("utf-8") if stderr else "Unknown error"
                raise RuntimeError(f"Middleware failed with code {process.returncode}: {error_msg}")

            # Parse output
            if not stdout:
                return {}

            return json.loads(stdout.decode("utf-8"))

        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid JSON output from middleware: {e}")
        except Exception as e:
            raise RuntimeError(f"Middleware execution failed: {e}")

    async def execute(self, hook_event: Dict[str, Any]) -> Dict[str, str]:
        """Execute the analytics pipeline

        Args:
            hook_event: Hook event data from stdin

        Returns:
            Result dictionary with status and message
        """
        try:
            # Stage 1: Normalize event
            # The normalizer expects HookInput format with provider, event, and data
            normalizer_env = {
                "ANALYTICS_PROVIDER": hook_event.get("provider", "claude"),
                "ANALYTICS_DEBUG": "false",
            }

            normalized_event = await self.run_middleware(
                self.normalizer_path,
                hook_event,
                normalizer_env,
            )

            # Stage 2: Publish event
            # The publisher expects a NormalizedEvent from normalizer
            # Use absolute path since publisher runs from services/analytics directory
            import os
            output_path = os.path.abspath("./analytics/events.jsonl")
            publisher_env = {
                "ANALYTICS_PUBLISHER_BACKEND": "file",
                "ANALYTICS_OUTPUT_PATH": output_path,
            }

            await self.run_middleware(
                self.publisher_path,
                normalized_event,
                publisher_env,
            )

            return {
                "status": "success",
                "message": "Analytics event processed successfully",
            }

        except Exception as e:
            # Analytics failures are non-fatal - log error and continue
            error_msg = f"Analytics pipeline failed: {e}"
            print(error_msg, file=sys.stderr)
            return {
                "status": "error",
                "message": error_msg,
            }


async def main() -> None:
    """Main entry point for analytics-collector hook"""
    try:
        # Read hook event from stdin
        input_data = sys.stdin.read()
        if not input_data:
            print(json.dumps({"status": "error", "message": "No input data"}))
            sys.exit(0)  # Non-fatal - analytics doesn't block agent

        hook_event = json.loads(input_data)

        # Get hook directory
        hook_dir = Path(__file__).parent

        # Create orchestrator and execute pipeline
        orchestrator = AnalyticsHookOrchestrator(hook_dir)
        result = await orchestrator.execute(hook_event)

        # Output result
        print(json.dumps(result))
        sys.exit(0)  # Always exit 0 - analytics never blocks

    except json.JSONDecodeError as e:
        error_result = {
            "status": "error",
            "message": f"Invalid JSON input: {e}",
        }
        print(json.dumps(error_result))
        sys.exit(0)  # Non-fatal

    except Exception as e:
        error_result = {
            "status": "error",
            "message": f"Hook orchestrator failed: {e}",
        }
        print(json.dumps(error_result))
        sys.exit(0)  # Non-fatal


if __name__ == "__main__":
    asyncio.run(main())

