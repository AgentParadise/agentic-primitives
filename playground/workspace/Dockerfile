# Playground Workspace Image
# A minimal Docker image with Claude CLI for playground testing
#
# Build:
#   docker build -t agentic-workspace:latest ./workspace
#
# This image provides:
# - Node.js (for Claude CLI)
# - Claude CLI installed globally
# - Python 3.12 (for hook scripts)
# - Common utilities (git, curl, jq)

FROM node:22-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    git \
    curl \
    jq \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Claude CLI globally
RUN npm install -g @anthropic-ai/claude-code

# Create workspace directory
WORKDIR /workspace

# Create non-root user for security
RUN useradd -m -s /bin/bash agent && \
    chown -R agent:agent /workspace

# Switch to non-root user
USER agent

# Verify installations
RUN claude --version && python3 --version

# Default command
CMD ["bash"]
