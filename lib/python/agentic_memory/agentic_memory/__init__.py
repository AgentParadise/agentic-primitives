"""agentic-memory: memory primitive contract + doctor for agentic-primitives workspaces.

See ADR-036 and 2026-05-13-memory-primitive-and-doctor-design.md.

This module is intentionally lazy — submodules are imported on demand to
avoid the `RuntimeWarning: found in sys.modules` issue when running
`python -m agentic_memory.doctor`.
"""

__version__ = "0.1.0"
