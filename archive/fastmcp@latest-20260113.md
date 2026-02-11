---
# === Identity ===
package_name: fastmcp
semantic_version: latest-20260113
ecosystem: python

# === Source ===
source_url: https://gofastmcp.com/getting-started/quickstart
source_type: official_docs
page_path: /getting-started/quickstart

# === Version Context ===
requested_version: latest
version_range: null
is_latest: true

# === Metadata ===
title: Quickstart - FastMCP
scraped_at: 2026-01-13T19:12:30.636744+00:00

# === Tooling ===
tool: firecrawl-scraper
prompt: doc-scraper/v1
session_id: null

# === Integrity ===
content_hash: sha256:8c1e9c4b7122da217e13b75380efa59e876063bbc45af13a8751466ee3985990
---

[Skip to main content](https://gofastmcp.com/getting-started/quickstart#content-area)

Join us at the inaugural PyAI Conf in San Francisco on March 10th! [Learn More](https://pyai.events/?utm_source=gofastmcp)

[FastMCP home page![light logo](https://mintcdn.com/fastmcp/Lu2sdJVHDyHdvswk/assets/brand/wordmark.png?fit=max&auto=format&n=Lu2sdJVHDyHdvswk&q=85&s=67680e9b1c641023511881a24f296077)![dark logo](https://mintcdn.com/fastmcp/Lu2sdJVHDyHdvswk/assets/brand/wordmark-white.png?fit=max&auto=format&n=Lu2sdJVHDyHdvswk&q=85&s=776d9c0663633c9b9782b9f3f9785960)](https://gofastmcp.com/)

Search...

Navigation

Get Started

Quickstart

Search the docs...

Ctrl K

Documentation

##### Get Started

- [Welcome!](https://gofastmcp.com/getting-started/welcome)
- [Installation](https://gofastmcp.com/getting-started/installation)
- [Quickstart](https://gofastmcp.com/getting-started/quickstart)
- [Updates\\
\\
NEW](https://gofastmcp.com/updates)

##### Servers

- [Overview](https://gofastmcp.com/servers/server)
- Core Components

- Advanced Features

- Authentication

- Deployment


##### Clients

- Essentials

- Core Operations

- Advanced Features

- Authentication


##### Integrations

- Authentication

- Authorization

- AI Assistants

- AI SDKs

- API Integration


##### Patterns

- [Tool Transformation](https://gofastmcp.com/patterns/tool-transformation)
- [Decorating Methods](https://gofastmcp.com/patterns/decorating-methods)
- [CLI](https://gofastmcp.com/patterns/cli)
- [Contrib Modules](https://gofastmcp.com/patterns/contrib)
- [Testing](https://gofastmcp.com/patterns/testing)

##### Development

- [Contributing](https://gofastmcp.com/development/contributing)
- [Tests](https://gofastmcp.com/development/tests)
- [Releases](https://gofastmcp.com/development/releases)
- [Upgrade Guide\\
\\
NEW](https://gofastmcp.com/development/upgrade-guide)
- [Changelog](https://gofastmcp.com/changelog)

On this page

- [Create a FastMCP Server](https://gofastmcp.com/getting-started/quickstart#create-a-fastmcp-server)
- [Add a Tool](https://gofastmcp.com/getting-started/quickstart#add-a-tool)
- [Run the Server](https://gofastmcp.com/getting-started/quickstart#run-the-server)
- [Using the FastMCP CLI](https://gofastmcp.com/getting-started/quickstart#using-the-fastmcp-cli)
- [Call Your Server](https://gofastmcp.com/getting-started/quickstart#call-your-server)
- [Deploy to FastMCP Cloud](https://gofastmcp.com/getting-started/quickstart#deploy-to-fastmcp-cloud)

Welcome! This guide will help you quickly set up FastMCP, run your first MCP server, and deploy a server to FastMCP Cloud.If you haven’t already installed FastMCP, follow the [installation instructions](https://gofastmcp.com/getting-started/installation).

## [​](https://gofastmcp.com/getting-started/quickstart\#create-a-fastmcp-server)  Create a FastMCP Server

A FastMCP server is a collection of tools, resources, and other MCP components. To create a server, start by instantiating the `FastMCP` class.Create a new file called `my_server.py` and add the following code:

my\_server.py

Copy

```
from fastmcp import FastMCP

mcp = FastMCP("My MCP Server")
```

That’s it! You’ve created a FastMCP server, albeit a very boring one. Let’s add a tool to make it more interesting.

## [​](https://gofastmcp.com/getting-started/quickstart\#add-a-tool)  Add a Tool

To add a tool that returns a simple greeting, write a function and decorate it with `@mcp.tool` to register it with the server:

my\_server.py

Copy

```
from fastmcp import FastMCP

mcp = FastMCP("My MCP Server")

@mcp.tool
def greet(name: str) -> str:
    return f"Hello, {name}!"
```

## [​](https://gofastmcp.com/getting-started/quickstart\#run-the-server)  Run the Server

The simplest way to run your FastMCP server is to call its `run()` method. You can choose between different transports, like `stdio` for local servers, or `http` for remote access:

my\_server.py (stdio)

my\_server.py (HTTP)

Copy

```
from fastmcp import FastMCP

mcp = FastMCP("My MCP Server")

@mcp.tool
def greet(name: str) -> str:
    return f"Hello, {name}!"

if __name__ == "__main__":
    mcp.run()
```

This lets us run the server with `python my_server.py`. The stdio transport is the traditional way to connect MCP servers to clients, while the HTTP transport enables remote connections.

Why do we need the `if __name__ == "__main__":` block?The `__main__` block is recommended for consistency and compatibility, ensuring your server works with all MCP clients that execute your server file as a script. Users who will exclusively run their server with the FastMCP CLI can omit it, as the CLI imports the server object directly.

### [​](https://gofastmcp.com/getting-started/quickstart\#using-the-fastmcp-cli)  Using the FastMCP CLI

You can also use the `fastmcp run` command to start your server. Note that the FastMCP CLI **does not** execute the `__main__` block of your server file. Instead, it imports your server object and runs it with whatever transport and options you provide.For example, to run this server with the default stdio transport (no matter how you called `mcp.run()`), you can use the following command:

Copy

```
fastmcp run my_server.py:mcp
```

To run this server with the HTTP transport, you can use the following command:

Copy

```
fastmcp run my_server.py:mcp --transport http --port 8000
```

## [​](https://gofastmcp.com/getting-started/quickstart\#call-your-server)  Call Your Server

Once your server is running with HTTP transport, you can connect to it with a FastMCP client or any LLM client that supports the MCP protocol:

my\_client.py

Copy

```
import asyncio
from fastmcp import Client

client = Client("http://localhost:8000/mcp")

async def call_tool(name: str):
    async with client:
        result = await client.call_tool("greet", {"name": name})
        print(result)

asyncio.run(call_tool("Ford"))
```

Note that:

- FastMCP clients are asynchronous, so we need to use `asyncio.run` to run the client
- We must enter a client context (`async with client:`) before using the client
- You can make multiple client calls within the same context

## [​](https://gofastmcp.com/getting-started/quickstart\#deploy-to-fastmcp-cloud)  Deploy to FastMCP Cloud

[FastMCP Cloud](https://fastmcp.cloud/) is a hosting service run by the FastMCP team at [Prefect](https://www.prefect.io/fastmcp). It is optimized to deploy authenticated FastMCP servers as quickly as possible, giving you a secure URL that you can plug into any LLM client.

FastMCP Cloud is **free for personal servers** and offers simple pay-as-you-go pricing for teams.

To deploy your server, you’ll need a [GitHub account](https://github.com/). Once you have one, you can deploy your server in three steps:

1. Push your `my_server.py` file to a GitHub repository
2. Sign in to [FastMCP Cloud](https://fastmcp.cloud/) with your GitHub account
3. Create a new project from your repository and enter `my_server.py:mcp` as the server entrypoint

That’s it! FastMCP Cloud will build and deploy your server, making it available at a URL like `https://your-project.fastmcp.app/mcp`. You can chat with it to test its functionality, or connect to it from any LLM client that supports the MCP protocol.For more details, see the [FastMCP Cloud guide](https://gofastmcp.com/deployment/fastmcp-cloud).

[Installation\\
\\
Previous](https://gofastmcp.com/getting-started/installation) [FastMCP Updates\\
\\
Next](https://gofastmcp.com/updates)

Ctrl+I

Assistant

Responses are generated using AI and may contain mistakes.