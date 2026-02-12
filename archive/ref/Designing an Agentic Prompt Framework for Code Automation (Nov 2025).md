---
name: Designing an Agentic Prompt Framework for Code Automation
model: gpt-5
date: 2025-11-11
---

Designing an Agentic Prompt Framework for Code Automation

Use Case Focus: Coding Agents with General-Purpose Potential

Your primary goal is to build an agentic prompt framework geared towards coding tasks, while keeping it extensible to general purposes. Initially, the system will specialize in automating coding workflows – performing actions like code generation, static analysis, and running tests via AI agents. However, you want a design that can generalize beyond coding. This mirrors what Anthropic observed with Claude Code: although it started as a coding assistant, its underlying agent harness proved useful for non-coding tasks like research and note-taking ￼. In other words, the framework should handle coding tasks exceptionally well, but not be so specialized that it can’t later support, say, a writing assistant or a data analysis agent.

One key inspiration is the Next.js App Router model. In Next.js, the file/folder structure itself defines routes and functionality. Analogously, you want a structured repository of prompts where directory names and markdown files define the “routes” or tasks for your agents. This provides a predictable, standardized way to add new capabilities. For example, you might have a folder for a category of tasks (like code-review/) with markdown files inside for specific actions (like code-review/find-bugs.md, code-review/improve-style.md). By following a convention, you enable tooling to automatically discover available agent prompts and even validate their consistency. This is similar to how Next.js enforces file conventions – if everything is in the expected place and format, it “just works” and inconsistencies can be caught early.

Benefits of a structured, router-like approach:
	•	Discoverability: A developer (or an AI agent) can easily navigate the repository to find the prompt needed for a given task based on names and paths, much like finding a page or API route by URL structure.
	•	Convention over configuration: If you stick to a naming convention (folder names as high-level features or categories, file names as specific actions), your CLI tool or VS Code extension can automatically load and run the correct prompt. The folder name can provide context to the prompt inside.
	•	Automated validation: Because the structure is standardized, you can write scripts or use the agent itself to verify that files follow the expected naming and content rules. For instance, you could ensure each prompt file has a corresponding metadata file, or that file names match their parent folder’s theme. This is analogous to Next.js ensuring that the file exports the correct handler for a route, etc.
	•	Extensibility: Adding a new capability is as simple as adding a new file/folder in the correct place. The system can pick it up without heavy reconfiguration. Over time, this could enable a plugin-like system where others contribute new prompt “skills” by following the structure.

In practice, you envision not only a library of prompt files but also a CLI (and possibly a VS Code extension) to execute them. This would allow you to run automated commands for things like linting, type-checking, or code review by simply invoking an agent rather than doing it manually. For example, after writing some code, you might run a CLI command like ai-cli run code-review/find-bugs which would load the associated prompt and let the AI analyze your code for bugs. This kind of automation can save significant time in code review and QA by catching issues early and suggesting fixes.

Organizing Prompt “Primitives”: Feature Slices vs Functional Categories

Your repository will consist of many prompt primitives – atomic AI prompt scripts that accomplish specific tasks (e.g., “summarize this file,” “refactor this function,” “generate a unit test,” etc.). A crucial design decision is how to organize these prompts in the file system. There are two major approaches to consider:
	•	Feature-first (Vertical Slice) Organization: Group prompts by project feature or use-case. In software architecture, vertical slice means each feature contains all layers (UI, backend, etc.) for that feature, rather than grouping by layer. Translated to prompts, a feature-first structure would mean each high-level feature or project has its own folder containing all the prompt files related to it. For example, you might have frontend/ vs backend/ folders, each containing relevant prompts (API generation, UI text generation, etc.), or a folder per application/module where prompts for that context live together. This approach localizes everything needed for a feature in one place – which is great when prompts are heavily context-dependent on that feature.
	•	Functional (Category) Organization: Group prompts by the type of task or function they perform, regardless of project feature. This is analogous to organizing by “discipline” or “function” in a prompt library ￼ ￼. For example, you might have a summarization/ folder for all summarizing prompts, a bug-fixing/ folder for prompts that locate or fix issues, a documentation/ folder for prompts that create docs or comments, etc. Each folder is a category of tasks (often identified by the verb or action involved).

Given that your prompts are very atomic and reusable, leaning toward a category-based organization makes sense. In a feature-first scheme, you might end up duplicating similar prompt types under each feature, or scattering small generic prompts across feature folders, making them harder to find and reuse. Instead, grouping by function means all similar prompts live together, which improves reusability and discoverability. For example, an “analyze-code” prompt could be useful in many contexts (frontend, backend, different projects), so having it in a central analysis/ category makes it easy to find and maintain one version of it.

Category organization was also suggested as a best practice in prompt library management – one can organize prompts by function or task, by discipline/department, by project, etc. Function-based organization (i.e. by task) is ideal for small, narrow prompts that do one thing ￼. Project-based grouping (analogous to feature slices) can be useful for very project-specific prompts, but it risks siloing prompts and reducing reuse ￼. Since your “primitives” are meant to be the building blocks (the atoms) that can be composed into larger workflows, a functional grouping ensures these atoms can be mixed and matched across different vertical applications.

To implement this, decide on the top-level categories that make sense for your use cases. Some examples of categories (for a coding-oriented library) might be:
	•	analysis/ – for prompts that analyze code or data (e.g., explaining code, finding bugs).
	•	generation/ – for prompts that generate new code (scaffolding a component, writing a function from description).
	•	refactoring/ – prompts to improve or refactor existing code.
	•	testing/ – prompts that write tests or verify code behavior.
	•	documentation/ – for generating docs or comments from code.
	•	meta-prompts/ – perhaps for higher-level orchestrator prompts that combine sub-agents (more on this later).

Within each category folder, each prompt (or prompt set) can have its own subfolder or file. For instance, under generation/, you might have generate-component.md, implement-function.md, etc., each handling a specific generation task. This approach aligns with advice to categorize by the kind of task (or “AI use-case”) for ease of navigation ￼.

Example: Suppose you want an agent that sets up a new REST API endpoint in a project. This might involve multiple steps: creating a data model, writing controller logic, adding a route, and writing tests. In a feature-based organization, you might put all these under new-endpoint/ feature folder. But in a functional organization, you’d have a prompt in generation/ for creating the model and controller, another in documentation/ for creating API docs, one in testing/ for generating tests, etc. Then you could have a higher-level meta-prompt that orchestrates these primitives for the “new endpoint” workflow (this meta-prompt might live in a separate workflows/ or meta-prompts/ section).

Consistency and naming conventions will be important. The names of your folders and files should clearly convey their purpose (similar to how Next.js uses file names like page.js for pages, etc.). It sounds like you plan for the folder name to hint at context and the file name to specify the action, which is a good approach. Additionally, by maintaining a consistent naming scheme, you could have your CLI tool automatically derive information. For example, if a file is named find-bugs.md, the CLI could infer that this is a prompt that finds bugs in code, possibly even use the name as the command to execute it. You might even have the CLI verify that each prompt file’s name and location matches the metadata inside it (for instance, if metadata says name: find-bugs, then the file name should be find-bugs.md in the appropriate folder). This automatic validation ensures your intended “router-like” constraints are followed.

Prompt Files vs. Metadata: Keeping Instructions and Config Separate

Each prompt (especially those meant for use with an agent framework) often has two parts: the prompt instructions themselves (the text that will be given to the model) and the metadata/configuration that tells the system how or when to use that prompt. In Anthropic’s Claude ecosystem, for example, they use YAML frontmatter at the top of a Markdown file to specify metadata like the prompt’s name, description, and tool usage permissions ￼ ￼. This frontmatter is a fenced YAML block at the very top of the .md file. For instance, a Claude Skill file might look like:

---
name: your-skill-name  
description: Brief description of what this Skill does and when to use it  
allowed-tools: Bash(git diff:*), Web(search)  
---
# Your Skill Name

## Instructions  
... (prompt content) ...

In the Claude Code slash commands feature, the frontmatter can include fields like allowed-tools (to whitelist system commands the prompt can run), description (for documentation and discoverability), argument-hint (to help auto-complete command arguments), and even a specific model to use for that command ￼ ￼. These metadata fields are quite powerful – for example, listing allowed tools enables Claude to safely execute only those commands when the prompt is run ￼. The description helps Claude decide when to invoke a skill or helps users understand what the command does.

However, embedding metadata in the prompt file has a couple of downsides for your use-case. First, if you are feeding the entire Markdown to a model (especially non-Claude models), that YAML frontmatter might be token-consuming noise, or could even confuse models that aren’t expecting it. Claude’s own system likely strips the YAML before feeding the prompt to the model (using it only to configure behavior), but if you create a general prompt file and directly send it to GPT-4, for example, the YAML might just be seen as part of the prompt unless you preprocess it. Second, separating the prompt text from config can be cleaner for maintenance – you might want to update the instructions without risking altering the yaml syntax, or vice versa.

To address this, you’ve proposed a clear solution: use separate files for metadata and prompt text. Instead of one Markdown with frontmatter, each prompt could be split into two files: e.g. build-agentic-prompt.md (containing only the actual prompt text/instructions) and build-agentic-prompt.meta.md (containing the metadata, or perhaps even using a different extension like .yaml or .json if you prefer purely data format). In your example, you suggested:

agentic-prompts/meta-prompts/build-agentic-prompt/
├── build-agentic-prompt.md        (the main prompt script)
└── build-agentic-prompt.meta.md   (the metadata/config for that prompt)

This separation has several advantages:
	•	No extra tokens for metadata: The content in .meta.md can be loaded by your tool to configure the run, but it won’t be sent to the LLM as part of the prompt text. This ensures the model only sees what it needs to see (the instructions and any necessary context), and not internal config lines.
	•	Clarity in editing: A prompt engineer or developer can focus on crafting the prompt in the .md file without wading through YAML. Meanwhile, a config maintainer can update allowed tools or descriptions in the meta file without touching the prompt text. This reduces the chance of formatting errors in frontmatter affecting your prompt.
	•	Flexible format for metadata: You could choose the format that’s most convenient for metadata. Using a Markdown file for meta (with perhaps YAML inside it) is one way, or you might use JSON/YAML directly. The key is that your CLI tool knows how to read it. For example, build-agentic-prompt.meta.md could itself contain a YAML frontmatter (since it’s all metadata anyway), or simply a list of key-values. Because this file isn’t going to the AI, you have freedom in how to structure it.
	•	Allows richer metadata: In the future, you might store not just name/description but other info like the expected input format, examples, or even test cases for that prompt – all in the metadata file without cluttering the prompt. It could serve as documentation for each prompt primitive.

Do note that if you want to leverage some of Claude’s special features (like the built-in way it discovers skills by description), you will need to ensure that when using Claude, you supply it with the relevant metadata. Claude’s agent SDK, for instance, pre-loads the name and description of every installed skill into the system prompt so that Claude knows what tools/skills it has available ￼. If you bypass their file conventions, you might need to replicate that behavior manually. For example, you could programmatically construct a system prompt for Claude that lists all the skill descriptions from your meta files, effectively imitating what Claude would do if you had a SKILL.md. The benefit is you can also do something analogous for GPT-based models: e.g., for GPT, you might not preload all tool descriptions (since GPT has no built-in concept of “skills”), but you could at least use the metadata to show the user a help text or enforce certain behaviors in your orchestrator.

In summary, the metadata file approach is a design choice for flexibility and model-agnosticism. It avoids being locked into Claude’s frontmatter format and keeps your prompts portable. Just ensure your Rust CLI is built to read these meta files and apply their directives (e.g., if meta says allowed-tools: X, and you’re running on Claude, call the Claude API with those tool permissions; if running on GPT, you might ignore that or handle it via function-calling, etc.). This way, your markdown prompt files remain clean and focused, and all configuration lives side by side in an easily parseable form.

Building on the Claude Agent SDK for “Bare-Metal” Control

You’ve chosen to start with Anthropic’s Claude Agent SDK (formerly known as Claude Code SDK) as the backbone of your agent system. This is a great choice for a coding-focused agent, because the Claude Agent SDK essentially gives Claude (the AI) a “computer of its own” to work with ￼. Anthropic’s design principle here is that an AI coding assistant should be able to use the same tools a human developer uses: searching files, editing code, running tests, executing shell commands, etc. By using the SDK, you tap into a powerful tool-handling and context-management framework out of the box.

Figure: The agent feedback loop in Claude Agent SDK – agents gather context, take an action, verify the work, then iterate ￼.

When operating via the Claude Agent SDK, your AI agent isn’t just predicting text based on a prompt – it’s operating in a loop of perceive and act: it can gather context (e.g. read files, get system state), use tools to take actions (e.g. modify files, call APIs, run code), and then verify the results of those actions before deciding what to do next ￼. This loop (illustrated above) is key to enabling complex tasks like coding, where simply producing code isn’t enough – the code must be run and validated, and potentially debugged in subsequent iterations.

Some major benefits of using Claude + Agent SDK, especially at a “close to the metal” level, include:
	•	Rich Tool Ecosystem: Claude Agent SDK comes with a suite of built-in tools and the ability to define new ones. It has file system access, so Claude can read from and write to files in a controlled directory. It can execute shell/Bash commands (with permission), enabling it to run compilers, tests, or custom scripts ￼ ￼. It also supports web search and other extensions via Anthropic’s Model Context Protocol (MCP). Essentially, Claude can act like a developer who can edit code, run the project, check outputs, etc., which is crucial for coding tasks. These tools are “first-class” in Claude’s prompt context – meaning the model is explicitly aware of them and will choose to use them when appropriate. By contrast, a vanilla GPT-4 via the OpenAI API won’t spontaneously run your tests unless you set up a tool system for it.
	•	Automatic Context Management: The SDK provides automatic compaction and summarization of context when it grows too large ￼. This means if your agent has been working for a while and the conversation history or gathered data is about to exceed the context window, Claude will smartly summarize or truncate less relevant parts to keep the important information. This is built on Claude’s internal /compact command. As a developer, you don’t have to manually implement context length checks and summarization; the SDK handles it, ensuring your agent can run for long sessions (important for something like a continuous codebase refactor) without hitting token limits disastrously.
	•	Subagents and Parallelization: Claude supports subagents – essentially spawning child agents with isolated context windows ￼. This can be very powerful for large tasks like “analyze a big codebase” or “search for specific info in many files.” Instead of one agent sequentially reading files (which could be slow and memory-heavy), it can spin up multiple subagents to work in parallel on different pieces and then aggregate the results. The SDK makes this relatively straightforward. For example, you could have one orchestrator prompt that says “Split the following task among N sub-tasks and assign to subagents”. The ability to manage subagents by default is a feature you get by using Claude’s system, and it’s especially useful for scaling up complex jobs.
	•	Permissions and Safety Controls: With great power (like shell access) comes the need for control. The Agent SDK allows fine-grained tool permission settings ￼. You can explicitly allow or disallow certain tools per agent or per skill. For instance, you may want your code-generation agent to be able to run npm test but not rm -rf /! The SDK’s structure (with allowed-tools in frontmatter, or equivalent if you implement it) lets you put guardrails so the AI doesn’t misuse tools or access out-of-scope files. This is vital for trust in automation – you can confidently let the agent act autonomously in your codebase if you know its actions are constrained to safe operations. Additionally, being an enterprise-focused product, Claude’s SDK has built-in monitoring and error handling. It’s designed for production use, meaning it can handle exceptions (say a tool throws an error) and keep the agent running or provide useful feedback.
	•	Optimized Claude Integration: Since you’ll use Claude primarily at first, it’s worth noting that the SDK is optimized for Claude’s models. Anthropic mentions things like prompt caching and performance optimizations as part of the integration ￼. Essentially, they have probably built some efficiencies (like reusing system prompts, etc.) to make the agent run faster and cheaper on Claude. By using the SDK or its patterns, you benefit from those optimizations instead of reinventing them. For example, if you call the same skill repeatedly, the system might cache some of the prompt context to avoid re-sending it every time, etc.

To tie this to your plan: “Pretty close to bare metal” accurately describes your approach. Rather than using a high-level orchestration library (like LangChain or others), you are interfacing directly with the Claude agent capabilities. You’re essentially leveraging Claude’s native “agentic” features (tools, memory, etc.) as your foundation. This should give you better performance and fewer black-box issues, since you control exactly what the prompt and tools do. It’s similar to directly using OS system calls vs. using a heavy framework – more power and responsibility, but also more flexibility.

One thing to clarify: using the Claude Agent SDK doesn’t necessarily mean you have to use Anthropic’s provided libraries (which are in Python/TypeScript as per their docs ￼). Since you plan to build your CLI in Rust, you might instead use the Claude API endpoints to achieve the same effect. That is, the Claude CLI/SDK reads those .claude/commands/ and .claude/skills/ files and then ultimately makes API calls to Claude with a constructed prompt that includes the tools and system instructions. You can replicate that by reading your prompt files and calling Claude’s API via an unofficial Rust SDK or HTTP calls. There are already unofficial Rust crates like anthropic-rs or rllm that can facilitate calling Anthropic’s models ￼. Using those, you could implement the portions of the SDK you need (like sending the right system prompt to enable tools, handling the loop of reading/writing files).

In short, Claude Agent SDK gives you a robust, tested backbone for agent loops. By building on it now, you save time implementing low-level features for the Claude model. As we’ll discuss next, the challenge will be to keep your design flexible enough to later incorporate other models that don’t natively have all these capabilities.

Multi-Model Support and Future Integration (GPT, Cursor, etc.)

While Claude will be your initial workhorse, you wisely anticipate incorporating other AI providers like OpenAI’s GPT (Codex/GPT-4, etc.) and possibly even leveraging Cursor CLI in the future. Ensuring your system can handle multiple backends means defining clear abstractions and understanding the differences in what each model/platform offers.

1. Adapters with a Standard Interface:
The idea of writing adapters for each provider is to have a common interface in your Rust code such as LLMProvider with methods like executePrompt(prompt, context) -> result. Under the hood, one adapter might call Claude via its API, another might call OpenAI, another could even call a local model. This is similar to how some libraries approach it – for example, the Rust crate RLLM was built to unify OpenAI, Anthropic, and others behind a single API using a builder pattern ￼. It defines traits like ChatProvider and CompletionProvider that each backend implements, so the rest of your code can remain the same regardless of which model is in use ￼. You could take inspiration from that: design a trait or interface that encapsulates the necessary operations (e.g., send a prompt and get completion, maybe a method to inject tools or system message). Then implement it for Claude (using the SDK or API calls) and for GPT (using OpenAI’s API).

By doing this, switching models might be as simple as changing a configuration or command-line flag to point to the other backend, without changing your prompt repository or CLI commands. It also allows experimenting with new models in future (say Google’s Gemini or others) by writing a new adapter.

2. Handling Differences in Prompt Format:
One thing to be mindful of is that LLMs are not all prompted the same way. As you noted, models can have biases or preferences. For instance, Anthropic’s Claude was trained heavily with an XML-based prompt format for its system messages, whereas OpenAI’s models tend to respond better to Markdown or chat-completion formats ￼. A prompt tuned for one might underperform on another ￼. Max Leiter’s blog highlights that a prompt that excelled in Claude (with XML structure) did not work as well on GPT-4 until rewritten, because the models have different training biases ￼. Furthermore, things like how they handle instructions (e.g., position of information in the prompt) and their verbosity can differ.

What this means for your project is that truly model-agnostic prompts might be hard – you may need slight variations or at least different system instructions per model. Your adapter layer can account for this. For example, if you have a meta-prompt that orchestrates a 3-agent system (something like an agent that delegates to two sub-agents), the way you implement that with Claude could leverage Claude’s subagent feature internally. Doing the same with GPT-4 might require manually simulating those agents via separate API calls (since GPT doesn’t have a built-in subagent concept). In such a case, you might maintain two versions of that orchestrator prompt or have conditional logic in your code to handle it.

A practical approach is to design prompts in a model-agnostic way where possible, but also embrace the strengths of each model through your adapters. For instance, you can write your prompt instructions in plain English/Markdown (which GPT and Claude both understand well), avoid Anthropic-specific slash commands in the prompt text, etc., making the core content portable. Then, in the Claude adapter, you might wrap that prompt with additional system instructions or use frontmatter tools. In the OpenAI adapter, you might convert that prompt into an OpenAI function call or follow their best practices. This is essentially having a translation layer: the high-level task is the same, but the “prompt packaging” differs.

3. Tools and Autonomy Across Models:
Claude with the Agent SDK has one big advantage: it can autonomously use tools (like running code) as part of its single API call loop. GPT-4 via the standard OpenAI API won’t do this out-of-the-box – it will only produce text. However, OpenAI has introduced Function Calling in their API, which is a way to give GPT tools by defining functions it can call ￼. In a way, this is OpenAI’s answer to tool use: you describe functions (like {"name": "execute_shell", "parameters": {...}}) and the model can decide to output a JSON calling that function, which your code then executes, and returns the result back into the prompt. It’s not as seamless as Claude’s approach (where the model just writes !command in the middle of its message and the SDK executes it ￼), but it’s effective with proper design.

There’s also mention of OpenAI developing an “OpenAI Agents” framework (in limited beta) with built-in tools ￼. But since that’s not widely available, function calling or manual tool handling is the path. For your adapter, if you want GPT-4 to, say, run tests, you could implement a function run_tests() that your program provides to the model. The model might then respond with a payload like {"function": "run_tests", "arguments": "..."}. Your code executes the tests and returns the output (truncated or summarized) to the model, then the model continues. This is a bit more involved to set up than with Claude, but it is doable.

Alternatively, since you control the CLI, you could opt for a simpler approach with GPT: not to let it autonomously run tools, but rather run a sequence of prompts. For example, your Rust code could handle the loop: send prompt asking GPT “Do X. If you need to run tests, reply with a special token or command.” If GPT replies with “<RUN> npm test</RUN>”, your code sees that and executes it, then feeds the output back in. This is somewhat reinventing what function calling does, but it’s an option if you prefer a custom or more transparent approach. The bottom line is that you’ll need to bridge the gap for tools when not on Claude.

4. Cursor CLI Integration:
Cursor CLI is essentially another layer on top of GPT (and possibly other models) that provides an interface for coding assistance in the terminal ￼ ￼. It has features like interactive and non-interactive modes, parallel agents, and model switching. If your system is well-abstracted, you might not need to directly integrate Cursor’s CLI; instead, you can replicate the useful features it offers:
	•	Model switching: As shown in Cursor CLI, a single command /model can swap the agent’s model (e.g., between Claude 4.5 and GPT-5 in their UI) ￼. In your CLI, you could allow a flag or config setting to choose the model per run, or even at runtime allow switching if that makes sense (though that’s more complex to maintain conversation state across models). Initially, a simpler approach is just a --provider flag when invoking the tool.
	•	Multi-agent parallelism: Cursor can run tasks in parallel (e.g., one agent generating code while another runs tests) ￼. With your system, once you have both Claude and, say, GPT available, you could even use them simultaneously for different roles (this is speculative, but for example: use Claude to write code and GPT to critique it in parallel). Or run two prompts at the same time on different parts of a problem. Implementing this would mean your Rust CLI handles threading or async tasks. This might be a later optimization, but it’s good to keep in mind that your architecture should not assume a strictly single-threaded sequential operation if you want to tap into such capabilities.
	•	MCP and external context: Cursor CLI supports connecting to external data/tools via the Model Context Protocol (MCP) config ￼. In your case, since you have full control, you might not need MCP specifically (which is an Anthropic-defined JSON-RPC protocol for tools ￼). But you could adopt the concept: standardize how external tools are integrated so that both Claude and GPT agents can use them. For example, define that your meta files can include a reference to an external data source or API, and have your code handle feeding that data to the prompt. If down the line you wanted to integrate something like a database or a knowledge base, you could either use Anthropic’s MCP (there’s even a Rust implementation called MCPR for it ￼) for Claude, or use function calling for GPT. Designing an abstraction for “external resource access” could be part of your adapter’s responsibilities.
	•	User interaction vs automation: Cursor CLI has an interactive chat mode and a non-interactive mode for scripts ￼. Your CLI can mirror this: allow a user to drop into a repl-like session with an agent, or just run a command and exit with the result. This is more of a CLI feature than an architecture one, but it influences how you design the prompt usage (interactive mode might maintain state in memory, whereas one-shot mode reads/writes less state).

Figure: Cursor CLI allows switching the underlying AI model with a /model command (here showing options like Claude and GPT) ￼. Such multi-model support is a key inspiration for your framework.

In planning for GPT Codex (OpenAI) integration, note that “Codex” as a standalone model (like code-davinci) has been largely subsumed by GPT-4 and GPT-3.5 with code abilities. By the time you implement, you’ll likely use gpt-4 (and beyond) via OpenAI’s API. GPT-4 can certainly handle code tasks (it’s very strong at it), but as mentioned, it won’t execute code by itself. One advantage GPT has is a larger context window (32k tokens in some versions), which might help with large files where Claude 2 currently has 100k context but in certain environments only 16k for the API. Keep an eye on model capabilities – e.g., OpenAI might release a specialized “GPT-4 Code” or improvements in function calling over time. Designing your system to easily switch or upgrade the model version will pay off.

5. Testing Across Models:
When you do start using multiple models, it will be important to test your prompts on each. As one AI engineer put it: prompts can “overfit” to a model, much like models overfit to data ￼. You may find that a phrasing that yields perfect results on Claude produces mediocre ones on GPT, or vice versa. A general best practice is to iterate your prompt for each model and not assume one-size-fits-all. Your framework could incorporate a testing utility – for instance, a command to run a given prompt through all supported providers and compare outputs. This could even be automated: whenever you add a new prompt, you verify that it works (or at least doesn’t produce errors) on Claude and on GPT. If one model consistently outperforms for certain prompts, you could note that in metadata (maybe a field like recommendedModel:), but ideally every task should be doable by each model albeit with slight tuning.

In summary, adapting to multi-model support means carefully separating the core logic of “what the agent should do” from the specifics of “how to prompt Model X to do it”. Keep your prompt content as neutral as possible, handle tool differences via your code or function calls, and use an abstraction layer to swap out LLMs. By doing so, you’ll create a flexible system where, for example, today Claude might be the best at coding, but tomorrow if GPT-5 or another model leapfrogs, you can switch over easily or even use a combination (each model doing what it’s best at, in a hybrid workflow).

Immediate Next Steps and Implementation Plan

With the above design considerations in mind, here are the immediate action items and a roadmap for building out your repository and toolchain:
	1.	Set Up the Repository Structure: Begin by creating the skeleton of your prompt library. Define the top-level folders for your organizational scheme (e.g. analysis/, generation/, refactoring/, testing/, meta-prompts/, etc. – whatever categories you decided). For each category, add a README or simple index listing what prompts will go there (this can help later as documentation). Create a couple of example prompt files and their corresponding .meta.md files to test your concept. For instance, under analysis/, you might start with find-bugs.md and find-bugs.meta.md containing some dummy content. This will allow you to flesh out the format of the meta files. In the meta file, you can use a YAML format like:

name: find-bugs  
description: "Analyze a given code snippet and identify potential bugs or errors."  
allowed-tools: Bash(pylint:*), Bash(javac:*), Bash(npm run test)  
model: claude-2  

This is just an example – include whatever fields you think are necessary (the above includes name, description, allowed tools, and a preferred model). The description in particular is important if you plan to let an AI choose to invoke this prompt autonomously (as Claude does with skills) or if you list prompts for the user. Keep them brief but informative ￼. The allowed-tools field is critical for Claude; list any shell or other tools the prompt might need. For now, if you are uncertain, you can allow nothing or just allow read-only operations. You could also include other metadata like expected input type (e.g., “requires file path as input”).

	2.	Rust CLI Scaffolding: Start a Rust project for your CLI tool. At first, focus on just a couple of core commands:
	•	A command (or default action) to list available prompts. This should read through your repository folders and gather metadata (name, description, maybe category) of each prompt. This will test that your metadata parsing works. It’s akin to an index of your “skills”. Later, you can format this nicely for users, but initially, even a JSON dump or simple console output is fine.
	•	A command to execute a prompt by name. For example, agentic run analysis/find-bugs --input code.py. This should locate analysis/find-bugs.md and its meta, read them, and then perform the call to the AI model. At first, implement this just for Claude (since that’s your initial focus). You might use an unofficial Anthropic API client in Rust or simply do an HTTP POST with reqwest to the Anthropic completion endpoint, including the prompt. Ensure you include whatever system instructions are needed to enable Claude’s tools. (If using the Claude SDK indirectly: maybe put the find-bugs.md content as a user message, and in the system message, include Claude’s default system instruction for tool use. Anthropic’s docs might have examples of the API payload for using the agent – often it involves sending a conversation where one message is something like <system>\nYou are an AI developer with access to a terminal... and listing tools. Since you have the SDK, you can find how to invoke a command via the API.)
At this stage, you don’t have to allow model switching yet – just hardcode it to Claude or read from the meta’s model field to pick Claude’s model ID.
	3.	Implement Claude-Specific Features: Once you can call Claude with a prompt and get a completion, expand to cover the tool execution loop. For instance, if the prompt expects to run pylint or compile code, Claude might output a special sequence (maybe something like a command in the text, or if using the streaming SDK it might have a channel message). You might need to use the Claude Agent SDK’s Python or TS library as reference for how it handles tool outputs. Alternatively, you can simplify by not giving Claude free reign at first: maybe initially, you’ll not allow any dangerous tool use, and test with something like allowed-tools: Bash(ls). See if Claude attempts to use them spontaneously. The Anthropic engineering blog and docs give insight: Claude’s agent will insert tool calls when appropriate, for example using a syntax like ! prefix for bash commands ￼ or @filename for file references ￼. Your program should watch the Claude responses for those patterns. For each tool call it emits, execute the command (in a sandbox directory ideally), capture the output, and feed it back to Claude’s context, then continue the conversation. This is the most complex part of the loop, but it’s what gives the agent autonomy. You don’t have to perfect it right away; perhaps constrain to a simple known command to ensure it works, then iterate.
	4.	Add Multi-Model Abstraction: With Claude execution working, start abstracting the code to prepare for OpenAI integration. Define a trait like LLMAdapter with methods sendPrompt(prompt, tools, metadata). Implement one for Claude that does what you wrote in step 3. Then implement a dummy one for OpenAI (for now, it could simply call GPT-4 with no tools, just to test switching). You might use OpenAI’s official Rust library (if one exists) or HTTP calls to chat/completions. The simplest test: take one of your prompt files (maybe a pure Q&A type prompt) and see if you can get a response from GPT-4. You’ll quickly notice differences (for example, GPT might not stop when it should, or it might not know what to do with certain instructions). Adjust accordingly. For now, if GPT can’t do tools, you might strip out allowed-tools instructions when sending to it.
Essentially, at this step, introduce a way to specify which model to use when running a prompt. Perhaps your CLI can have an option -m openai:gpt-4 vs -m anthropic:claude-2. Or the .meta.md could have model: claude-2 as shown, and you provide an override flag to use a different one. This will allow experimenting with how the same prompt behaves on each.
	5.	Prototype Cursor CLI Workflow (Optional): If one of your goals is to integrate Cursor or at least learn from it, you might want to install Cursor CLI and use it manually to see how it behaves for similar tasks. Cursor uses the OpenAI (and possibly Claude) under the hood and adds its sugar. Direct integration is not straightforward (since Cursor isn’t just an API you call; it’s a CLI on its own). But you could conceive of a mode where your tool, instead of directly calling OpenAI, delegates to Cursor CLI. For instance, agentic run generation/implement-function --via-cursor. That might spawn a subprocess of cursor-agent with the appropriate prompt. However, unless Cursor has a programmatic interface, this could be clunky. Another route: simply take inspiration from Cursor’s features (like those listed earlier) and plan to incorporate the most valuable ones into your CLI over time.
	6.	Repository of Primitives: As you build out the technical side, continue fleshing out the prompt content for your “primitives”. This is more of a creative prompt-engineering task:
	•	Write the actual content of the prompts in each .md file. Remember, these are essentially instructions to the AI. For example, in find-bugs.md, you might write something like: “You are a code analysis agent. The user will provide a piece of source code. Analyze it for any potential bugs or errors, including logical mistakes, misuse of APIs, or style issues. Provide a report of issues found, each with an explanation.” Keep them clear and direct ￼, and possibly include examples if needed. Since these are intended for automation, concise and deterministic outputs might be ideal (like maybe a list of issues).
	•	If using Claude, consider using the “role” or persona style in the prompt (Claude and GPT both respond well to being given a specific role in the system message ￼). Your metadata might include something akin to a system prompt too. E.g., a general system instruction like “You are an expert software engineer.” could be globally applied. Claude’s .claude/CLAUDE.md mechanism allows persistent instructions across a project ￼ – you could have an equivalent in your system (like a global config for the agent’s personality or rules).
	•	For each prompt, ensure the metadata description is specific about when it should be used ￼. This is crucial if you ever enable an autonomous mode where the AI decides to invoke a tool (skill) based on the description. Claude uses that description to match user requests to skills. Even if you don’t use that now, it’s good practice to write it as if you will.
	7.	Version Control and Collaboration: Initialize a git repository for all this (if you haven’t). Prompt libraries benefit from versioning – you can track improvements to prompts over time, roll back if a change made a prompt worse, etc. It also enables collaboration if you open source it or share with a team. Anthropic’s approach for skills is to share via git and automatically load team-shared skills ￼. You could emulate that by having your CLI pull from a central repo or just by encouraging usage of the repo. Write a good README explaining the structure and how to contribute a new prompt (with a meta file, etc.). This documentation will also help clarify your own thinking.
	8.	Testing & Refinement: Finally, as you reach a minimally viable product with a few prompts and the CLI working for Claude, start using it in real scenarios! Run the agents on actual coding tasks in a sample project. See where the pain points are. Perhaps the agent gets stuck in a loop, or maybe the output formatting isn’t ideal, or a prompt needs more explicit guidance. This hands-on usage will inform how to improve prompts and whether the architecture holds up. It’s likely you’ll find that some prompts need to call sub-functions or that you want meta-prompts (like the “build-agentic-prompt” meta-workflow you mentioned, which presumably creates a multi-agent chain). You can then implement those higher-level orchestrations, possibly by writing an orchestrator that uses your primitives (maybe even having an agent read from the repository and assemble a plan – truly eating your own dogfood!).

In terms of level of abstraction, by following these steps you maintain a low-level control (you see every prompt and API call), but you are building a light framework on top – your Rust CLI is essentially that framework. It will remain lean if you just stick to managing files, calling APIs, and handling tool I/O. That gives you the benefit of understanding exactly how the AI is reasoning and acting, which is important for trust and debuggability. As a comparison, if one used a heavy library that wraps prompts in multiple layers, one might lose insight into what the AI was actually told. Your approach avoids that by design.

To conclude, your immediate goal is within reach: set up the primitives repo and a basic CLI to manage and run them. From there, incrementally add sophistication: Anthropic SDK features first, then multi-provider support, then polish (parallelism, advanced UX, etc.). By prioritizing a solid organizational scheme and metadata separation now, you're laying the groundwork for a scalable system. In a sense, you're creating your own "standard" for prompt-based agents, which could evolve into a popular open-source approach if done well. Good luck with building this out – it's an exciting project at the frontier of AI developer tooling! 🚀

Final Implementation Specification: The Agentic Primitives Repository

Building on the design principles above and informed by recent developments in the agentic AI ecosystem, this section provides a concrete, implementable specification for the agentic-primitives repository. This specification synthesizes best practices from Anthropic's Agent Skills, GitHub's agentic primitives framework, and the patterns explored throughout this research ￼ ￼.

Project Overview

Name: agentic-primitives

Purpose: A source-of-truth repository of atomic agentic primitives for AI coding systems, organized into two main categories:
	•	Prompt primitives: Reusable natural language instructions and patterns
	•	agents → personas / system-level styles
	•	commands → task / workflow prompts
	•	skills → reusable knowledge overlays (model-agnostic patterns)
	•	meta-prompts → prompts that help build/compose other prompts
	•	Tool primitives: Logical tool specifications with optional provider-specific bindings

This repository serves as the building blocks for agentic systems, not the orchestration layer itself. It's designed to be consumed by runtime orchestrators (like the Claude Agent SDK, OpenAI function calling systems, or custom Rust CLI implementations) rather than being tightly coupled to any single provider.

Non-goals: This repository explicitly does not include runtime orchestration, agent loops, or official Claude .claude/ plugin structures as the source of truth. Those are consumers of this repository, not part of it.

Top-Level Directory Structure

agentic-primitives/
├── README.md
├── primitives.config.yaml        # global settings, validators, defaults
│
├── prompts/
│   ├── agents/                   # personas / roles
│   ├── commands/                 # tasks / workflows
│   ├── skills/                   # reusable knowledge overlays
│   └── meta-prompts/             # higher-order prompt builders
│
├── tools/                        # capability primitives
│   ├── <tool-id>/
│   │   ├── tool.meta.yaml        # logical spec
│   │   ├── impl.claude.yaml      # (optional) Claude binding
│   │   ├── impl.openai.json      # (optional) OpenAI function binding
│   │   └── impl.local.rs         # (optional) local implementation
│   └── ...
│
├── models/                       # model configuration mappings
│   ├── models.config.yaml        # model alias → provider mappings
│   └── README.md                 # documentation for model configuration
│
├── schemas/                      # JSON/YAML schemas for validation
│   ├── prompt-meta.schema.json
│   ├── tool-meta.schema.json
│   └── provider-impl.schema.json
│
└── cli/                          # Rust CLI project
    ├── src/
    │   ├── main.rs
    │   ├── validate.rs
    │   ├── new_prompt.rs
    │   ├── new_tool.rs
    │   ├── list.rs
    │   └── inspect.rs
    └── Cargo.toml

Primitive Types

Prompt Primitives

All prompt primitives live under prompts/ and share a common metadata schema with a kind field that determines their role and usage pattern.

a) Agents (prompts/agents/)

Use: System-level persona or role that provides long-lived context and behavioral characteristics

Folder format:

prompts/agents/<agent-id>/
  ├── prompt.md
  └── meta.yaml

Example IDs: python-pro, web-architect, devops-sensei

Agents typically have context_usage.as_system = true, indicating they're best used as system-level instructions that persist across a session.

b) Commands (prompts/commands/)

Use: Discrete, executable tasks or workflows, often user-triggered for specific operations

Folder format:

prompts/commands/<command-id>/
  ├── prompt.md
  └── meta.yaml

Example IDs: python-scaffold, code-review, test-generator

Commands typically have context_usage.as_user = true, indicating they're invoked as explicit user requests or workflow steps.

c) Skills (prompts/skills/)

Use: Reusable knowledge overlays or patterns that can be injected into context when relevant. These replace the concept of "patterns" with a more general-purpose, model-agnostic approach ￼. Skills follow the progressive disclosure principle pioneered by Anthropic: metadata is always loaded, full content is loaded on-demand, and additional reference files are loaded only when needed ￼.

Folder format:

prompts/skills/<skill-id>/
  ├── prompt.md
  └── meta.yaml

Example IDs: python-testing-patterns, async-python-patterns, api-design-patterns

Skills typically have context_usage.as_overlay = true, indicating they should be injected into context when their domain is relevant, rather than always being present.

d) Meta-prompts (prompts/meta-prompts/)

Use: Higher-order prompts that help generate, combine, or orchestrate other prompts. These are the "prompts about prompts" that enable bootstrapping and composition.

Folder format:

prompts/meta-prompts/<meta-id>/
  ├── prompt.md
  └── meta.yaml

Example: A meta-prompt that takes a task description and generates a new command prompt with appropriate structure and metadata.

Tool Primitives

Each tool has one logical specification (tool.meta.yaml) that defines what the tool does in a provider-agnostic way, plus optional provider-specific implementation bindings:

tools/<tool-id>/
  ├── tool.meta.yaml           # logical spec
  ├── impl.claude.yaml         # optional Claude SDK binding
  ├── impl.openai.json         # optional OpenAI function calling binding
  └── impl.local.rs            # optional local Rust implementation

This separation enables the same logical tool to be implemented differently across providers while maintaining a single source of truth for the tool's purpose and interface.

File Schemas and Conventions

prompt.md (all prompt types)

Pure natural language instructions with no frontmatter or provider-specific syntax. Contains:
	•	Role definition
	•	Goal or purpose
	•	Input/output expectations
	•	Inline examples where helpful

Example for a command:

You are a senior Python project scaffolding assistant.

Goal:
- Given a user request, create a Python project layout with:
  - Clear directory structure
  - Virtual environment / dependency manager setup
  - Testing (pytest)
  - Linting (ruff or flake8)
- Produce:
  - A short explanation of the structure.
  - A list of files with contents or templates.

Constraints:
- Prefer modern tools (uv, Poetry) when requested.
- Do not assume network access unless explicitly stated.

meta.yaml for prompts

Location: prompts/<kind>/<id>/meta.yaml

Shared base schema:

id: python-pro            # must match folder name
kind: agent               # one of: agent | command | skill | meta-prompt
domain: python            # optional: high-level domain
summary: "Expert Python engineer for architecture, debugging, and refactoring."
tags:                     # optional
  - python
  - backend
  - architecture

defaults:
  preferred_models:       # generic model aliases, mapped via models/ config
    - claude-sonnet
    - gpt-codex
  max_iterations: 4       # hint to orchestrator

context_usage:            # how an orchestrator should use this prompt
  as_system: true         # good candidate for system-level
  as_user: false
  as_overlay: false       # for skills, often true

tools:                    # logical tool IDs this prompt expects
  - run-tests
  - search-code

inputs:                   # structured expectation for arguments
  - name: project_description
    type: string
    required: true
  - name: stack_hint
    type: string
    required: false

Model Configuration System

Rather than embedding specific model versions (like claude-3.5-sonnet or gpt-4.1-mini) directly in prompt metadata, the system uses generic model aliases (claude-sonnet, gpt-codex, claude-opus, gpt-large) that are resolved through a central configuration. This approach provides several benefits:
	•	Configuration flexibility: Update model versions globally without touching individual prompts
	•	Environment-specific mappings: Different deployments can map aliases to different models
	•	Provider abstraction: The same alias can point to different providers in different contexts
	•	Version management: Track model version changes separately from prompt content

models/models.config.yaml

# Model Configuration Mappings
# Maps generic model aliases to specific provider models
# Update this file to change model versions globally

aliases:
  claude-sonnet:
    provider: anthropic
    model: claude-3.5-sonnet-20241022
    description: "Balanced Claude model for general coding tasks"
    max_tokens: 200000
    supports_tools: true
    
  claude-opus:
    provider: anthropic
    model: claude-3-opus-20240229
    description: "Most capable Claude model for complex reasoning"
    max_tokens: 200000
    supports_tools: true
    
  gpt-codex:
    provider: openai
    model: gpt-4-turbo-2024-11-20
    description: "OpenAI's coding-optimized model"
    max_tokens: 128000
    supports_tools: true
    supports_function_calling: true
    
  gpt-large:
    provider: openai
    model: gpt-4.5-preview
    description: "Latest large OpenAI model"
    max_tokens: 128000
    supports_tools: true
    supports_function_calling: true

# Environment-specific overrides (optional)
# These can be used to point to different models in dev vs prod
environments:
  development:
    gpt-codex:
      model: gpt-4-turbo-preview  # Use preview in dev
  production:
    gpt-codex:
      model: gpt-4-turbo-2024-11-20  # Use stable in prod

This configuration enables prompts to specify preferences like preferred_models: [claude-sonnet, gpt-codex] while the actual model versions are managed centrally and can be updated as new versions are released.

tool.meta.yaml (logical tool schema)

Location: tools/<tool-id>/tool.meta.yaml

id: run-tests
kind: shell                  # or fs, http, db, etc.
description: "Run the project's test suite and return summarized results."
args:
  - name: command
    type: string
    required: false
    default: "pytest"
    description: "Shell command to run the test suite."
safety:
  max_runtime_sec: 600
  working_dir: "."
  allow_write: false
providers:
  - claude
  - openai
  - local

Provider Bindings (optional)

impl.claude.yaml:

tool: run-tests
type: bash       # maps to Claude's Bash tool
command_template: "{{command}}"
allowed_patterns:
  - "pytest"
  - "npm test"
  - "pnpm test"
notes: "Used by testing-related prompts to run tests safely."

impl.openai.json:

{
  "name": "run_tests",
  "description": "Run the project's test suite and return summarized results.",
  "parameters": {
    "type": "object",
    "properties": {
      "command": {
        "type": "string",
        "description": "Command to run (e.g. 'pytest')."
      }
    },
    "required": []
  }
}

impl.local.rs:

pub fn run_tests(command: Option<String>) -> anyhow::Result<String> {
    let cmd = command.unwrap_or_else(|| "pytest".to_string());
    // spawn process, capture output, truncate/summarize as needed
    Ok(format!("Ran command: {cmd}\n<output here>"))
}

Naming & Conventions

	•	Folder name = ID (python-pro, python-scaffold, run-tests)
	•	meta.yaml.id must equal folder name (enforced by CLI validation)
	•	IDs use kebab-case consistently
	•	One primitive per folder (no mixing multiple prompts in one folder)
	•	Providers are additive: Start with impl.claude.yaml, add impl.openai.json later without changing the logical spec
	•	Model references use generic aliases (claude-sonnet, gpt-codex) that resolve via models/models.config.yaml

CLI Specification (Rust)

Binary name: agentic-primitives (or ap for short)

Core commands (v1):

1. init
Creates base folder structure + primitives.config.yaml

agentic-primitives init

2. new prompt <kind> <id>
Creates a new prompt primitive with kind ∈ {agent, command, skill, meta-prompt}

agentic-primitives new prompt agent python-pro

Creates:
	•	prompts/<kind>/<id>/prompt.md (with template)
	•	prompts/<kind>/<id>/meta.yaml (with template based on kind)

3. new tool <id>
Creates a new tool primitive:

agentic-primitives new tool run-tests

Creates:
	•	tools/<id>/tool.meta.yaml (with template)
	•	tools/<id>/impl.claude.yaml (stub)
	•	tools/<id>/impl.openai.json (stub)
	•	tools/<id>/impl.local.rs (stub)

4. validate
Validates the entire repository structure:

agentic-primitives validate

Checks:
	•	Directory + naming rules (folder name = ID in meta)
	•	meta.yaml against prompt-meta.schema.json
	•	tool.meta.yaml against tool-meta.schema.json
	•	Provider implementations against provider-impl.schema.json
	•	Model alias references against models/models.config.yaml

5. list [prompts|tools] [--kind <kind>]
Inventories primitives with summary information:

agentic-primitives list prompts --kind agent
agentic-primitives list tools

6. inspect <id>
Resolves <id> across prompts/tools and outputs a single JSON object with all metadata, path to prompt.md or tool.meta.yaml, and resolved model information:

agentic-primitives inspect python-pro

Output:

{
  "id": "python-pro",
  "kind": "agent",
  "path": "prompts/agents/python-pro",
  "prompt_file": "prompts/agents/python-pro/prompt.md",
  "meta_file": "prompts/agents/python-pro/meta.yaml",
  "metadata": { ... },
  "resolved_models": [
    {
      "alias": "claude-sonnet",
      "provider": "anthropic",
      "model": "claude-3.5-sonnet-20241022"
    }
  ]
}

This output is designed for consumption by orchestrators or SDK consumers.

Optional (future): build --target claude to generate .claude/ plugin files from the repository primitives, allowing seamless integration with Claude Code.

Concrete Example Set: Python Development

To illustrate the system in action, here's a complete set of Python-focused primitives:

Agent: python-pro

prompts/agents/python-pro/prompt.md:

You are "Python Pro", a senior Python engineer.

Your specialties:
- Project architecture and package layout
- Async IO, concurrency, and performance
- Testing strategy and tooling (pytest, coverage)
- Modern packaging and dependency management (uv, Poetry, pip-tools)

When answering:
- Be direct and pragmatic.
- Show code examples where useful.
- Call out tradeoffs and common pitfalls.

prompts/agents/python-pro/meta.yaml:

id: python-pro
kind: agent
domain: python
summary: "Expert Python engineer for architecture, debugging, and refactoring."
tags:
  - python
  - backend
  - architecture

defaults:
  preferred_models:
    - claude-sonnet
    - gpt-codex
  max_iterations: 4

context_usage:
  as_system: true
  as_user: false
  as_overlay: false

tools:
  - run-tests
  - search-code

Command: python-scaffold

prompts/commands/python-scaffold/prompt.md:

You are a Python project scaffolding assistant.

Given a description of a project, you will:
- Propose an appropriate stack (framework, test runner, dependency manager).
- Produce a directory structure.
- Generate file stubs or templates for:
  - main application entry point
  - configuration
  - tests
  - tooling (formatters, linters, CI workflow if relevant)

Output format:
1. Short explanation of chosen stack and rationale.
2. Directory tree.
3. For each key file, a code block with its initial contents.

prompts/commands/python-scaffold/meta.yaml:

id: python-scaffold
kind: command
domain: python
summary: "Scaffold a new Python project with tests, linting, and packaging."

defaults:
  preferred_models:
    - claude-sonnet

context_usage:
  as_system: false
  as_user: true
  as_overlay: false

tools:
  - write-files

inputs:
  - name: project_description
    type: string
    required: true
  - name: stack_hint
    type: string
    required: false

Skill: python-testing-patterns

prompts/skills/python-testing-patterns/prompt.md:

You are an expert in Python testing practices.

Core principles:
- Favor small, focused tests with clear given/when/then structure.
- Use pytest fixtures to manage setup/teardown and reuse.
- Aim for meaningful coverage, not just raw coverage percentage.
- Test behavior and contracts, not implementation details when possible.

When integrated into another agent:
- Suggest improvements to test layout and naming.
- Propose missing test cases for edge conditions and failure modes.
- Highlight common pitfalls, like overusing mocks or brittle integration tests.

prompts/skills/python-testing-patterns/meta.yaml:

id: python-testing-patterns
kind: skill
domain: python
summary: "Principles and patterns for high-quality pytest-based test suites."

defaults:
  preferred_models:
    - claude-sonnet

context_usage:
  as_system: false
  as_user: false
  as_overlay: true

tools: []

Tool: run-tests

tools/run-tests/tool.meta.yaml:

id: run-tests
kind: shell
description: "Run the project's test suite and return summarized results."

args:
  - name: command
    type: string
    required: false
    default: "pytest"
    description: "Test command to run in the project."

safety:
  max_runtime_sec: 600
  working_dir: "."
  allow_write: false

providers:
  - claude
  - openai
  - local

Integration with Runtime Orchestrators

This repository is designed to be consumed by external orchestration systems. For example:

1. Load agent python-pro → use prompt.md as system message, resolve preferred model claude-sonnet to claude-3.5-sonnet-20241022
2. Optionally load skill python-testing-patterns → append to system or as overlay message when working with tests
3. Load command python-scaffold when user triggers that operation
4. Resolve tool IDs (run-tests, write-files) to provider-specific bindings (Claude Bash tool, OpenAI function, local Rust implementation)

The orchestrator stays in control of context management at every step; this repository just provides clean, versionable, testable building blocks.

Recent Ecosystem Developments

Since the initial design of this system, several developments in the agentic AI ecosystem have validated and informed this approach:

GitHub's Agentic Primitives Framework: GitHub has published a comprehensive framework for building reliable AI workflows using "agentic primitives" – reusable, configurable building blocks structured as Markdown files ￼. Their approach uses .instructions.md files for modular guidance, .chatmode.md for role-based expertise with tool boundaries, and .prompt.md for reusable workflows. This closely parallels our agents, skills, and commands structure, confirming that organizing primitives by function rather than feature is becoming an industry best practice.

Progressive Disclosure in Skills: Anthropic's recent work on Agent Skills has formalized the concept of progressive disclosure: skill metadata is always loaded (level 1), full skill content is loaded on-demand (level 2), and additional bundled files are loaded only when needed (level 3+) ￼. This pattern directly maps to our meta.yaml (always loaded) + prompt.md (loaded when relevant) + potential reference files structure.

Natural Language as Code: The industry is increasingly treating prompt primitives as a new form of software that requires proper tooling infrastructure ￼. Just as JavaScript evolved from browser scripts to having Node.js runtimes, package managers, and deployment tooling, agent primitives need similar infrastructure. This validates our CLI-first approach and the emphasis on schemas, validation, and versioning.

Security Through Tool Boundaries: GitHub's framework emphasizes security through MCP tool boundaries – each chat mode receives only the specific tools needed for its domain ￼. This maps directly to our tools field in meta.yaml and the provider-specific impl files that can enforce allowed_patterns and safety constraints.

These parallel developments across industry leaders suggest that the primitives-based approach outlined in this specification is aligned with emerging best practices in agentic AI development.

Sources:
	•	Anthropic Engineering Blog – "Building agents with the Claude Agent SDK" (2025) – discussing how Claude Code evolved into a general agent platform and best practices ￼ ￼ ￼ ￼.
	•	Anthropic Engineering Blog – "Equipping agents for the real world with Agent Skills" (October 2025) – comprehensive guide on the anatomy of skills, progressive disclosure principles, and integration patterns ￼.
	•	Anthropic Claude Documentation – Agent Skills and Commands – on using YAML frontmatter in SKILL.md and command files for name/description and tool permissions ￼ ￼.
	•	GitHub Blog – "How to build reliable AI workflows with agentic primitives and context engineering" by Daniel Meppiel (October 2025) – three-layer framework for AI-native development including Markdown prompt engineering, agent primitives (.instructions.md, .chatmode.md, .prompt.md), and context engineering strategies ￼.
	•	BioErrorLog Tech Blog – "How to Create Custom Slash Commands in Claude Code" – examples of command definitions with frontmatter for allowed-tools and descriptions ￼ ￼.
	•	Randall Pine – "How to Organize and Scale Your Prompt Library" – guidance on organizing prompts by function vs project, etc., emphasizing consistency ￼ ￼ ￼.
	•	Max Leiter – "You should be rewriting your prompts" – notes on model differences (Claude vs GPT) and the need to adapt prompt formats across models ￼ ￼.
	•	Codecademy – "Getting Started with Cursor CLI" – highlights of Cursor CLI features like model switching and multi-agent support ￼ ￼.
	•	Reddit (r/rust) – Introduction of RLLM crate – demonstrating a unified Rust API for OpenAI and Anthropic, illustrating the feasibility of a multi-backend adapter ￼.