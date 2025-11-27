#!/usr/bin/env python3
"""Generate JSON Schema for analytics events from Pydantic models"""

import json
from pathlib import Path

from analytics.models.events import NormalizedEvent


def main() -> None:
    """Generate JSON Schema and write to specs/v1/analytics-events.schema.json"""
    # Generate schema from Pydantic model
    schema = NormalizedEvent.model_json_schema()

    # Add additional metadata
    schema["$schema"] = "http://json-schema.org/draft-07/schema#"
    schema["title"] = "Analytics Event Schema"
    schema["description"] = (
        "Normalized analytics event structure for agentic-primitives hook system. "
        "This schema is provider-agnostic and represents events after normalization "
        "from provider-specific hook formats (Claude, OpenAI, Cursor, etc.)."
    )

    # Write to specs directory
    specs_dir = Path(__file__).parent.parent.parent / "specs" / "v1"
    specs_dir.mkdir(parents=True, exist_ok=True)

    schema_path = specs_dir / "analytics-events.schema.json"

    with open(schema_path, "w") as f:
        json.dump(schema, f, indent=2)

    print(f"✅ Generated JSON Schema: {schema_path}")
    print(f"📊 Schema size: {len(json.dumps(schema))} bytes")


if __name__ == "__main__":
    main()
