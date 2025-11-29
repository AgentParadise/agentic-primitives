"""Agent runner API - Start and monitor agent tasks."""

import asyncio
import logging
import os
import subprocess
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["agent"])


class AgentTask(BaseModel):
    """Request to start an agent task."""

    prompt: str = Field(..., min_length=1, description="Task for the agent to perform")
    model: str = Field(
        default="claude-haiku-4-5-20251001",
        description="Model to use (haiku is cheapest)",
    )


class AgentTaskResponse(BaseModel):
    """Response when starting an agent task."""

    session_id: str
    status: str = "started"
    message: str


class AgentStatus(BaseModel):
    """Current status of an agent task."""

    session_id: str
    status: str  # "running", "completed", "failed"
    pid: int | None = None


# Track running agents
_running_agents: dict[str, dict] = {}


def _get_project_root() -> Path:
    """Get the agentic-primitives project root."""
    # Go up from backend/src/api to examples/002.../backend to examples to agentic-primitives
    return Path(__file__).parent.parent.parent.parent.parent.parent


@router.post("/run", response_model=AgentTaskResponse)
async def run_agent_task(task: AgentTask):
    """Start an agent task with the given prompt."""
    session_id = str(uuid.uuid4())
    project_root = _get_project_root()

    # Check if we have an API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        # Try loading from .env in example 001
        env_file = project_root / "examples/001-claude-agent-sdk-integration/.env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("ANTHROPIC_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break

    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="ANTHROPIC_API_KEY not set. Add it to examples/001.../.env",
        )

    # Escape prompt for shell - escape both single and double quotes
    escaped_prompt = task.prompt.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'")

    # Start agent using subprocess.Popen (fire and forget)
    _running_agents[session_id] = {"status": "running", "pid": None}

    try:
        env = os.environ.copy()
        env["ANTHROPIC_API_KEY"] = api_key
        # Clear VIRTUAL_ENV to avoid uv confusion
        env.pop("VIRTUAL_ENV", None)

        # Create a simple runner script
        script = f'''
import asyncio
from src.agent import InstrumentedAgent

async def main():
    # Output path points to root .agentic folder
    agent = InstrumentedAgent(
        model="{task.model}",
        output_path="../../.agentic/analytics/events.jsonl",
        session_id="{session_id}"
    )
    result = await agent.run("{escaped_prompt}")
    print("AGENT_DONE:", result.text[:200] if result.text else "No response")

asyncio.run(main())
'''

        # Run the agent
        process = subprocess.Popen(
            ["uv", "run", "python", "-c", script],
            cwd=str(project_root / "examples/001-claude-agent-sdk-integration"),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,  # Detach from parent
        )

        _running_agents[session_id]["pid"] = process.pid
        logger.info(f"Started agent process {process.pid} for session {session_id}")

        # Start background task to monitor process
        asyncio.create_task(_monitor_process(session_id, process))

    except Exception as e:
        logger.error(f"Failed to start agent: {e}")
        _running_agents[session_id] = {"status": "failed", "error": str(e)}
        raise HTTPException(status_code=500, detail=f"Failed to start agent: {e}")

    return AgentTaskResponse(
        session_id=session_id,
        status="started",
        message=f"Agent task started with model {task.model}",
    )


async def _monitor_process(session_id: str, process: subprocess.Popen):
    """Monitor a subprocess and update status when done."""
    try:
        # Wait for process to complete in a thread (non-blocking)
        loop = asyncio.get_event_loop()
        returncode = await loop.run_in_executor(None, process.wait)

        stdout, stderr = process.communicate()

        if returncode == 0:
            _running_agents[session_id]["status"] = "completed"
            logger.info(f"Agent {session_id} completed successfully")
        else:
            _running_agents[session_id]["status"] = "failed"
            error_msg = stderr.decode() if stderr else "Unknown error"
            _running_agents[session_id]["error"] = error_msg[:500]
            logger.error(f"Agent {session_id} failed: {error_msg[:200]}")

    except Exception as e:
        _running_agents[session_id] = {"status": "failed", "error": str(e)}
        logger.error(f"Error monitoring agent {session_id}: {e}")


@router.get("/status/{session_id}", response_model=AgentStatus)
async def get_agent_status(session_id: str):
    """Get the status of a running agent task."""
    if session_id not in _running_agents:
        # Check if session exists in database
        return AgentStatus(session_id=session_id, status="unknown")

    agent_info = _running_agents[session_id]
    return AgentStatus(
        session_id=session_id,
        status=agent_info.get("status", "unknown"),
        pid=agent_info.get("pid"),
    )


@router.get("/models")
async def list_models():
    """List available models."""
    return {
        "models": [
            {
                "id": "claude-haiku-4-5-20251001",
                "name": "Claude Haiku 4.5",
                "description": "Fastest and cheapest - great for testing",
            },
            {
                "id": "claude-sonnet-4-20250514",
                "name": "Claude Sonnet 4",
                "description": "Balanced performance and cost",
            },
            {
                "id": "claude-opus-4-20250514",
                "name": "Claude Opus 4",
                "description": "Most capable, highest cost",
            },
        ]
    }
