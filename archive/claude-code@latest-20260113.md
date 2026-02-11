---
# === Identity ===
package_name: claude-code
semantic_version: latest-20260113
ecosystem: unknown

# === Source ===
source_url: https://docs.claude.com/en/docs/claude-code/plugins
source_type: official_docs
page_path: /en/docs/claude-code/plugins

# === Version Context ===
requested_version: latest
version_range: null
is_latest: true

# === Metadata ===
title: Create plugins - Claude Code Docs
scraped_at: 2026-01-13T17:59:52.798751+00:00

# === Tooling ===
tool: firecrawl-scraper
prompt: doc-scraper/v1
session_id: null

# === Integrity ===
content_hash: sha256:4838c97f87bb0eda23ca8646918e1e842d0daa83ba3ddaed181e0a176c1af8c2
---

[Skip to main content](https://code.claude.com/docs/en/plugins#content-area)

[Claude Code Docs home page![light logo](https://mintcdn.com/claude-code/o69F7a6qoW9vboof/logo/light.svg?fit=max&auto=format&n=o69F7a6qoW9vboof&q=85&s=536eade682636e84231afce2577f9509)![dark logo](https://mintcdn.com/claude-code/o69F7a6qoW9vboof/logo/dark.svg?fit=max&auto=format&n=o69F7a6qoW9vboof&q=85&s=0766b3221061e80143e9f300733e640b)](https://code.claude.com/docs)

![US](https://d3gk2c5xim1je2.cloudfront.net/flags/US.svg)

English

Search...

Ctrl KAsk AI

Search...

Navigation

Build with Claude Code

Create plugins

[Getting started](https://code.claude.com/docs/en/overview) [Build with Claude Code](https://code.claude.com/docs/en/sub-agents) [Deployment](https://code.claude.com/docs/en/third-party-integrations) [Administration](https://code.claude.com/docs/en/setup) [Configuration](https://code.claude.com/docs/en/settings) [Reference](https://code.claude.com/docs/en/cli-reference) [Resources](https://code.claude.com/docs/en/legal-and-compliance)

On this page

- [When to use plugins vs standalone configuration](https://code.claude.com/docs/en/plugins#when-to-use-plugins-vs-standalone-configuration)
- [Quickstart](https://code.claude.com/docs/en/plugins#quickstart)
- [Prerequisites](https://code.claude.com/docs/en/plugins#prerequisites)
- [Create your first plugin](https://code.claude.com/docs/en/plugins#create-your-first-plugin)
- [Plugin structure overview](https://code.claude.com/docs/en/plugins#plugin-structure-overview)
- [Develop more complex plugins](https://code.claude.com/docs/en/plugins#develop-more-complex-plugins)
- [Add Skills to your plugin](https://code.claude.com/docs/en/plugins#add-skills-to-your-plugin)
- [Add LSP servers to your plugin](https://code.claude.com/docs/en/plugins#add-lsp-servers-to-your-plugin)
- [Organize complex plugins](https://code.claude.com/docs/en/plugins#organize-complex-plugins)
- [Test your plugins locally](https://code.claude.com/docs/en/plugins#test-your-plugins-locally)
- [Debug plugin issues](https://code.claude.com/docs/en/plugins#debug-plugin-issues)
- [Share your plugins](https://code.claude.com/docs/en/plugins#share-your-plugins)
- [Convert existing configurations to plugins](https://code.claude.com/docs/en/plugins#convert-existing-configurations-to-plugins)
- [Migration steps](https://code.claude.com/docs/en/plugins#migration-steps)
- [What changes when migrating](https://code.claude.com/docs/en/plugins#what-changes-when-migrating)
- [Next steps](https://code.claude.com/docs/en/plugins#next-steps)
- [For plugin users](https://code.claude.com/docs/en/plugins#for-plugin-users)
- [For plugin developers](https://code.claude.com/docs/en/plugins#for-plugin-developers)

Plugins let you extend Claude Code with custom functionality that can be shared across projects and teams. This guide covers creating your own plugins with slash commands, agents, Skills, hooks, and MCP servers.Looking to install existing plugins? See [Discover and install plugins](https://code.claude.com/docs/en/discover-plugins). For complete technical specifications, see [Plugins reference](https://code.claude.com/docs/en/plugins-reference).

## [​](https://code.claude.com/docs/en/plugins\#when-to-use-plugins-vs-standalone-configuration)  When to use plugins vs standalone configuration

Claude Code supports two ways to add custom slash commands, agents, and hooks:

| Approach | Slash command names | Best for |
| --- | --- | --- |
| **Standalone** (`.claude/` directory) | `/hello` | Personal workflows, project-specific customizations, quick experiments |
| **Plugins** (directories with `.claude-plugin/plugin.json`) | `/plugin-name:hello` | Sharing with teammates, distributing to community, versioned releases, reusable across projects |

**Use standalone configuration when**:

- You’re customizing Claude Code for a single project
- The configuration is personal and doesn’t need to be shared
- You’re experimenting with slash commands or hooks before packaging them
- You want short slash command names like `/hello` or `/review`

**Use plugins when**:

- You want to share functionality with your team or community
- You need the same slash commands/agents across multiple projects
- You want version control and easy updates for your extensions
- You’re distributing through a marketplace
- You’re okay with namespaced slash commands like `/my-plugin:hello` (namespacing prevents conflicts between plugins)

Start with standalone configuration in `.claude/` for quick iteration, then [convert to a plugin](https://code.claude.com/docs/en/plugins#convert-existing-configurations-to-plugins) when you’re ready to share.

## [​](https://code.claude.com/docs/en/plugins\#quickstart)  Quickstart

This quickstart walks you through creating a plugin with a custom slash command. You’ll create a manifest (the configuration file that defines your plugin), add a slash command, and test it locally using the `--plugin-dir` flag.

### [​](https://code.claude.com/docs/en/plugins\#prerequisites)  Prerequisites

- Claude Code [installed and authenticated](https://code.claude.com/docs/en/quickstart#step-1-install-claude-code)
- Claude Code version 1.0.33 or later (run `claude --version` to check)

If you don’t see the `/plugin` command, update Claude Code to the latest version. See [Troubleshooting](https://code.claude.com/docs/en/troubleshooting) for upgrade instructions.

### [​](https://code.claude.com/docs/en/plugins\#create-your-first-plugin)  Create your first plugin

1

Create the plugin directory

Every plugin lives in its own directory containing a manifest and your custom commands, agents, or hooks. Create one now:

Copy

Ask AI

```
mkdir my-first-plugin
```

2

Create the plugin manifest

The manifest file at `.claude-plugin/plugin.json` defines your plugin’s identity: its name, description, and version. Claude Code uses this metadata to display your plugin in the plugin manager.Create the `.claude-plugin` directory inside your plugin folder:

Copy

Ask AI

```
mkdir my-first-plugin/.claude-plugin
```

Then create `my-first-plugin/.claude-plugin/plugin.json` with this content:

my-first-plugin/.claude-plugin/plugin.json

Copy

Ask AI

```
{
"name": "my-first-plugin",
"description": "A greeting plugin to learn the basics",
"version": "1.0.0",
"author": {
"name": "Your Name"
}
}
```

| Field | Purpose |
| --- | --- |
| `name` | Unique identifier and slash command namespace. Slash commands are prefixed with this (e.g., `/my-first-plugin:hello`). |
| `description` | Shown in the plugin manager when browsing or installing plugins. |
| `version` | Track releases using [semantic versioning](https://code.claude.com/docs/en/plugins-reference#version-management). |
| `author` | Optional. Helpful for attribution. |

For additional fields like `homepage`, `repository`, and `license`, see the [full manifest schema](https://code.claude.com/docs/en/plugins-reference#plugin-manifest-schema).

3

Add a slash command

Slash commands are Markdown files in the `commands/` directory. The filename becomes the slash command name, prefixed with the plugin’s namespace (`hello.md` in a plugin named `my-first-plugin` creates `/my-first-plugin:hello`). The Markdown content tells Claude how to respond when someone runs the slash command.Create a `commands` directory in your plugin folder:

Copy

Ask AI

```
mkdir my-first-plugin/commands
```

Then create `my-first-plugin/commands/hello.md` with this content:

my-first-plugin/commands/hello.md

Copy

Ask AI

```
---
description: Greet the user with a friendly message
---

# Hello Command

Greet the user warmly and ask how you can help them today.
```

4

Test your plugin

Run Claude Code with the `--plugin-dir` flag to load your plugin:

Copy

Ask AI

```
claude --plugin-dir ./my-first-plugin
```

Once Claude Code starts, try your new command:

Copy

Ask AI

```
/my-first-plugin:hello
```

You’ll see Claude respond with a greeting. Run `/help` to see your command listed under the plugin namespace.

**Why namespacing?** Plugin slash commands are always namespaced (like `/greet:hello`) to prevent conflicts when multiple plugins have commands with the same name.To change the namespace prefix, update the `name` field in `plugin.json`.

5

Add slash command arguments

Make your slash command dynamic by accepting user input. The `$ARGUMENTS` placeholder captures any text the user provides after the slash command.Update your `hello.md` file:

my-first-plugin/commands/hello.md

Copy

Ask AI

```
---
description: Greet the user with a personalized message
---

# Hello Command

Greet the user named "$ARGUMENTS" warmly and ask how you can help them today. Make the greeting personal and encouraging.
```

Restart Claude Code to pick up the changes, then try the command with your name:

Copy

Ask AI

```
/my-first-plugin:hello Alex
```

Claude will greet you by name. For more argument options like `$1`, `$2` for individual parameters, see [Slash commands](https://code.claude.com/docs/en/slash-commands).

You’ve successfully created and tested a plugin with these key components:

- **Plugin manifest** (`.claude-plugin/plugin.json`): describes your plugin’s metadata
- **Commands directory** (`commands/`): contains your custom slash commands
- **Command arguments** (`$ARGUMENTS`): captures user input for dynamic behavior

The `--plugin-dir` flag is useful for development and testing. When you’re ready to share your plugin with others, see [Create and distribute a plugin marketplace](https://code.claude.com/docs/en/plugin-marketplaces).

## [​](https://code.claude.com/docs/en/plugins\#plugin-structure-overview)  Plugin structure overview

You’ve created a plugin with a slash command, but plugins can include much more: custom agents, Skills, hooks, MCP servers, and LSP servers.

**Common mistake**: Don’t put `commands/`, `agents/`, `skills/`, or `hooks/` inside the `.claude-plugin/` directory. Only `plugin.json` goes inside `.claude-plugin/`. All other directories must be at the plugin root level.

| Directory | Location | Purpose |
| --- | --- | --- |
| `.claude-plugin/` | Plugin root | Contains only `plugin.json` manifest (required) |
| `commands/` | Plugin root | Slash commands as Markdown files |
| `agents/` | Plugin root | Custom agent definitions |
| `skills/` | Plugin root | Agent Skills with `SKILL.md` files |
| `hooks/` | Plugin root | Event handlers in `hooks.json` |
| `.mcp.json` | Plugin root | MCP server configurations |
| `.lsp.json` | Plugin root | LSP server configurations for code intelligence |

**Next steps**: Ready to add more features? Jump to [Develop more complex plugins](https://code.claude.com/docs/en/plugins#develop-more-complex-plugins) to add agents, hooks, MCP servers, and LSP servers. For complete technical specifications of all plugin components, see [Plugins reference](https://code.claude.com/docs/en/plugins-reference).

## [​](https://code.claude.com/docs/en/plugins\#develop-more-complex-plugins)  Develop more complex plugins

Once you’re comfortable with basic plugins, you can create more sophisticated extensions.

### [​](https://code.claude.com/docs/en/plugins\#add-skills-to-your-plugin)  Add Skills to your plugin

Plugins can include [Agent Skills](https://code.claude.com/docs/en/skills) to extend Claude’s capabilities. Skills are model-invoked: Claude automatically uses them based on the task context.Add a `skills/` directory at your plugin root with Skill folders containing `SKILL.md` files:

Copy

Ask AI

```
my-plugin/
├── .claude-plugin/
│   └── plugin.json
└── skills/
    └── code-review/
        └── SKILL.md
```

Each `SKILL.md` needs frontmatter with `name` and `description` fields, followed by instructions:

Copy

Ask AI

```
---
name: code-review
description: Reviews code for best practices and potential issues. Use when reviewing code, checking PRs, or analyzing code quality.
---

When reviewing code, check for:
1. Code organization and structure
2. Error handling
3. Security concerns
4. Test coverage
```

After installing the plugin, restart Claude Code to load the Skills. For complete Skill authoring guidance including progressive disclosure and tool restrictions, see [Agent Skills](https://code.claude.com/docs/en/skills).

### [​](https://code.claude.com/docs/en/plugins\#add-lsp-servers-to-your-plugin)  Add LSP servers to your plugin

For common languages like TypeScript, Python, and Rust, install the pre-built LSP plugins from the official marketplace. Create custom LSP plugins only when you need support for languages not already covered.

LSP (Language Server Protocol) plugins give Claude real-time code intelligence. If you need to support a language that doesn’t have an official LSP plugin, you can create your own by adding an `.lsp.json` file to your plugin:

.lsp.json

Copy

Ask AI

```
{
  "go": {
    "command": "gopls",
    "args": ["serve"],
    "extensionToLanguage": {
      ".go": "go"
    }
  }
}
```

Users installing your plugin must have the language server binary installed on their machine.For complete LSP configuration options, see [LSP servers](https://code.claude.com/docs/en/plugins-reference#lsp-servers).

### [​](https://code.claude.com/docs/en/plugins\#organize-complex-plugins)  Organize complex plugins

For plugins with many components, organize your directory structure by functionality. For complete directory layouts and organization patterns, see [Plugin directory structure](https://code.claude.com/docs/en/plugins-reference#plugin-directory-structure).

### [​](https://code.claude.com/docs/en/plugins\#test-your-plugins-locally)  Test your plugins locally

Use the `--plugin-dir` flag to test plugins during development. This loads your plugin directly without requiring installation.

Copy

Ask AI

```
claude --plugin-dir ./my-plugin
```

As you make changes to your plugin, restart Claude Code to pick up the updates. Test your plugin components:

- Try your commands with `/command-name`
- Check that agents appear in `/agents`
- Verify hooks work as expected

You can load multiple plugins at once by specifying the flag multiple times:

Copy

Ask AI

```
claude --plugin-dir ./plugin-one --plugin-dir ./plugin-two
```

### [​](https://code.claude.com/docs/en/plugins\#debug-plugin-issues)  Debug plugin issues

If your plugin isn’t working as expected:

1. **Check the structure**: Ensure your directories are at the plugin root, not inside `.claude-plugin/`
2. **Test components individually**: Check each command, agent, and hook separately
3. **Use validation and debugging tools**: See [Debugging and development tools](https://code.claude.com/docs/en/plugins-reference#debugging-and-development-tools) for CLI commands and troubleshooting techniques

### [​](https://code.claude.com/docs/en/plugins\#share-your-plugins)  Share your plugins

When your plugin is ready to share:

1. **Add documentation**: Include a `README.md` with installation and usage instructions
2. **Version your plugin**: Use [semantic versioning](https://code.claude.com/docs/en/plugins-reference#version-management) in your `plugin.json`
3. **Create or use a marketplace**: Distribute through [plugin marketplaces](https://code.claude.com/docs/en/plugin-marketplaces) for installation
4. **Test with others**: Have team members test the plugin before wider distribution

Once your plugin is in a marketplace, others can install it using the instructions in [Discover and install plugins](https://code.claude.com/docs/en/discover-plugins).

For complete technical specifications, debugging techniques, and distribution strategies, see [Plugins reference](https://code.claude.com/docs/en/plugins-reference).

## [​](https://code.claude.com/docs/en/plugins\#convert-existing-configurations-to-plugins)  Convert existing configurations to plugins

If you already have custom commands, Skills, or hooks in your `.claude/` directory, you can convert them into a plugin for easier sharing and distribution.

### [​](https://code.claude.com/docs/en/plugins\#migration-steps)  Migration steps

1

Create the plugin structure

Create a new plugin directory:

Copy

Ask AI

```
mkdir -p my-plugin/.claude-plugin
```

Create the manifest file at `my-plugin/.claude-plugin/plugin.json`:

my-plugin/.claude-plugin/plugin.json

Copy

Ask AI

```
{
  "name": "my-plugin",
  "description": "Migrated from standalone configuration",
  "version": "1.0.0"
}
```

2

Copy your existing files

Copy your existing configurations to the plugin directory:

Copy

Ask AI

```
# Copy commands
cp -r .claude/commands my-plugin/

# Copy agents (if any)
cp -r .claude/agents my-plugin/

# Copy skills (if any)
cp -r .claude/skills my-plugin/
```

3

Migrate hooks

If you have hooks in your settings, create a hooks directory:

Copy

Ask AI

```
mkdir my-plugin/hooks
```

Create `my-plugin/hooks/hooks.json` with your hooks configuration. Copy the `hooks` object from your `.claude/settings.json` or `settings.local.json`—the format is the same:

my-plugin/hooks/hooks.json

Copy

Ask AI

```
{
  "hooks": {
    "PostToolUse": [\
      {\
        "matcher": "Write|Edit",\
        "hooks": [{ "type": "command", "command": "npm run lint:fix $FILE" }]\
      }\
    ]
  }
}
```

4

Test your migrated plugin

Load your plugin to verify everything works:

Copy

Ask AI

```
claude --plugin-dir ./my-plugin
```

Test each component: run your commands, check agents appear in `/agents`, and verify hooks trigger correctly.

### [​](https://code.claude.com/docs/en/plugins\#what-changes-when-migrating)  What changes when migrating

| Standalone (`.claude/`) | Plugin |
| --- | --- |
| Only available in one project | Can be shared via marketplaces |
| Files in `.claude/commands/` | Files in `plugin-name/commands/` |
| Hooks in `settings.json` | Hooks in `hooks/hooks.json` |
| Must manually copy to share | Install with `/plugin install` |

After migrating, you can remove the original files from `.claude/` to avoid duplicates. The plugin version will take precedence when loaded.

## [​](https://code.claude.com/docs/en/plugins\#next-steps)  Next steps

Now that you understand Claude Code’s plugin system, here are suggested paths for different goals:

### [​](https://code.claude.com/docs/en/plugins\#for-plugin-users)  For plugin users

- [Discover and install plugins](https://code.claude.com/docs/en/discover-plugins): browse marketplaces and install plugins
- [Configure team marketplaces](https://code.claude.com/docs/en/discover-plugins#configure-team-marketplaces): set up repository-level plugins for your team

### [​](https://code.claude.com/docs/en/plugins\#for-plugin-developers)  For plugin developers

- [Create and distribute a marketplace](https://code.claude.com/docs/en/plugin-marketplaces): package and share your plugins
- [Plugins reference](https://code.claude.com/docs/en/plugins-reference): complete technical specifications
- Dive deeper into specific plugin components:
  - [Slash commands](https://code.claude.com/docs/en/slash-commands): command development details
  - [Subagents](https://code.claude.com/docs/en/sub-agents): agent configuration and capabilities
  - [Agent Skills](https://code.claude.com/docs/en/skills): extend Claude’s capabilities
  - [Hooks](https://code.claude.com/docs/en/hooks): event handling and automation
  - [MCP](https://code.claude.com/docs/en/mcp): external tool integration

Was this page helpful?

YesNo

[Create custom subagents](https://code.claude.com/docs/en/sub-agents) [Discover and install prebuilt plugins](https://code.claude.com/docs/en/discover-plugins)

Ctrl+I

Assistant

Responses are generated using AI and may contain mistakes.