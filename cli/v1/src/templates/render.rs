use super::embedded::Templates;
use crate::error::Result;
use handlebars::Handlebars;
use serde_json::Value;

pub struct TemplateRenderer {
    handlebars: Handlebars<'static>,
}

impl TemplateRenderer {
    /// Create a new renderer with all templates registered
    pub fn new() -> Result<Self> {
        let mut handlebars = Handlebars::new();

        // Register all templates
        handlebars.register_template_string("agent.meta", Templates::AGENT_META)?;
        handlebars.register_template_string("command.meta", Templates::COMMAND_META)?;
        handlebars.register_template_string("skill.meta", Templates::SKILL_META)?;
        handlebars.register_template_string("meta-prompt.meta", Templates::META_PROMPT_META)?;
        handlebars.register_template_string("prompt.content", Templates::PROMPT_CONTENT)?;
        handlebars.register_template_string("tool.meta", Templates::TOOL_META)?;
        handlebars.register_template_string("hook.meta", Templates::HOOK_META)?;
        handlebars.register_template_string("middleware.py", Templates::MIDDLEWARE_PYTHON)?;
        handlebars.register_template_string("middleware.ts", Templates::MIDDLEWARE_TYPESCRIPT)?;

        Ok(Self { handlebars })
    }

    /// Render a template by name with given data
    pub fn render(&self, template_name: &str, data: &Value) -> Result<String> {
        self.handlebars
            .render(template_name, data)
            .map_err(|e| crate::error::Error::Template(e.to_string()))
    }

    /// Render agent meta.yaml
    pub fn render_agent_meta(&self, data: &Value) -> Result<String> {
        self.render("agent.meta", data)
    }

    /// Render command meta.yaml
    pub fn render_command_meta(&self, data: &Value) -> Result<String> {
        self.render("command.meta", data)
    }

    /// Render skill meta.yaml
    pub fn render_skill_meta(&self, data: &Value) -> Result<String> {
        self.render("skill.meta", data)
    }

    /// Render meta-prompt meta.yaml
    pub fn render_meta_prompt_meta(&self, data: &Value) -> Result<String> {
        self.render("meta-prompt.meta", data)
    }

    /// Render prompt.md content
    pub fn render_prompt_content(&self, data: &Value) -> Result<String> {
        self.render("prompt.content", data)
    }

    /// Render tool.meta.yaml
    pub fn render_tool_meta(&self, data: &Value) -> Result<String> {
        self.render("tool.meta", data)
    }

    /// Render hook.meta.yaml
    pub fn render_hook_meta(&self, data: &Value) -> Result<String> {
        self.render("hook.meta", data)
    }

    /// Render Python middleware
    pub fn render_middleware_python(&self, data: &Value) -> Result<String> {
        self.render("middleware.py", data)
    }

    /// Render TypeScript middleware
    pub fn render_middleware_typescript(&self, data: &Value) -> Result<String> {
        self.render("middleware.ts", data)
    }
}

impl Default for TemplateRenderer {
    fn default() -> Self {
        Self::new().expect("Failed to initialize template renderer")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_renderer_initialization() {
        let renderer = TemplateRenderer::new();
        assert!(
            renderer.is_ok(),
            "Template renderer should initialize successfully"
        );
    }

    #[test]
    fn test_render_agent_meta() {
        let renderer = TemplateRenderer::new().unwrap();
        let data = json!({
            "id": "test-agent",
            "category": "testing",
            "summary": "A test agent for unit tests"
        });

        let result = renderer.render_agent_meta(&data).unwrap();

        assert!(result.contains("id: test-agent"));
        assert!(result.contains("kind: agent"));
        assert!(result.contains("category: testing"));
        assert!(result.contains("summary: \"A test agent for unit tests\""));
        assert!(result.contains("as_system: true"));
        assert!(result.contains("as_user: false"));
        assert!(result.contains("as_overlay: false"));
        assert!(result.contains("preferred_models:"));
        assert!(result.contains("- claude/sonnet"));
        assert!(result.contains("tools: []"));
        assert!(result.contains("inputs: {}"));
        // Note: spec_version and versions array are added by the `new` command, not in the template
    }

    #[test]
    fn test_render_agent_meta_with_optional_fields() {
        let renderer = TemplateRenderer::new().unwrap();
        let data = json!({
            "id": "python-pro",
            "category": "python",
            "summary": "Expert Python developer agent",
            "domain": "programming",
            "tags": ["python", "coding", "expert"],
            "max_iterations": 10
        });

        let result = renderer.render_agent_meta(&data).unwrap();

        assert!(result.contains("domain: programming"));
        assert!(result.contains("tags:"));
        assert!(result.contains("  - python"));
        assert!(result.contains("  - coding"));
        assert!(result.contains("  - expert"));
        assert!(result.contains("max_iterations: 10"));
    }

    #[test]
    fn test_render_command_meta() {
        let renderer = TemplateRenderer::new().unwrap();
        let data = json!({
            "id": "code-review",
            "category": "review",
            "summary": "Review code for quality and best practices"
        });

        let result = renderer.render_command_meta(&data).unwrap();

        assert!(result.contains("id: code-review"));
        assert!(result.contains("kind: command"));
        assert!(result.contains("category: review"));
        assert!(result.contains("as_system: false"));
        assert!(result.contains("as_user: true"));
        assert!(result.contains("as_overlay: false"));
        assert!(result.contains("inputs: {}"));
    }

    #[test]
    fn test_render_skill_meta() {
        let renderer = TemplateRenderer::new().unwrap();
        let data = json!({
            "id": "pytest-patterns",
            "category": "testing",
            "summary": "Best practices for pytest testing"
        });

        let result = renderer.render_skill_meta(&data).unwrap();

        assert!(result.contains("id: pytest-patterns"));
        assert!(result.contains("kind: skill"));
        assert!(result.contains("category: testing"));
        assert!(result.contains("as_system: false"));
        assert!(result.contains("as_user: false"));
        assert!(result.contains("as_overlay: true"));
    }

    #[test]
    fn test_render_meta_prompt_meta() {
        let renderer = TemplateRenderer::new().unwrap();
        let data = json!({
            "id": "generate-primitive",
            "category": "generation",
            "summary": "Generate new agentic primitives"
        });

        let result = renderer.render_meta_prompt_meta(&data).unwrap();

        assert!(result.contains("id: generate-primitive"));
        assert!(result.contains("kind: meta-prompt"));
        assert!(result.contains("category: generation"));
        assert!(result.contains("domain: meta"));
        assert!(result.contains("- claude/opus"));
        assert!(result.contains("- claude/sonnet"));
        assert!(result.contains("inputs: {}"));
    }

    #[test]
    fn test_render_prompt_content() {
        let renderer = TemplateRenderer::new().unwrap();
        let data = json!({
            "title": "Python Expert",
            "kind": "agent",
            "domain": "python"
        });

        let result = renderer.render_prompt_content(&data).unwrap();

        assert!(result.contains("# Python Expert"));
        assert!(result.contains("## Role"));
        assert!(result.contains("You are a specialized AI assistant for python"));
        assert!(result.contains("## Goal"));
        assert!(result.contains("TODO: Define the specific goal of this agent"));
        assert!(result.contains("## Context"));
        assert!(result.contains("## Instructions"));
        assert!(result.contains("## Output Format"));
        assert!(result.contains("## Examples"));
    }

    #[test]
    fn test_render_prompt_content_with_custom_fields() {
        let renderer = TemplateRenderer::new().unwrap();
        let data = json!({
            "title": "Code Reviewer",
            "kind": "command",
            "domain": "review",
            "role": "You are an expert code reviewer.",
            "goal": "Review code for quality, security, and best practices.",
            "context": "Focus on actionable feedback.",
            "instructions": "1. Check for bugs\n2. Verify security\n3. Suggest improvements",
            "output_format": "Provide a bulleted list of findings.",
            "examples": "Example 1: Security issue found in line 42."
        });

        let result = renderer.render_prompt_content(&data).unwrap();

        assert!(result.contains("You are an expert code reviewer."));
        assert!(result.contains("Review code for quality, security, and best practices."));
        assert!(result.contains("Focus on actionable feedback."));
        assert!(result.contains("1. Check for bugs"));
        assert!(result.contains("Provide a bulleted list of findings."));
        assert!(result.contains("Example 1: Security issue found in line 42."));
        assert!(!result.contains("TODO"));
    }

    #[test]
    fn test_render_tool_meta() {
        let renderer = TemplateRenderer::new().unwrap();
        let data = json!({
            "id": "run-tests",
            "kind": "shell",
            "category": "testing",
            "description": "Run test suite"
        });

        let result = renderer.render_tool_meta(&data).unwrap();

        assert!(result.contains("id: run-tests"));
        assert!(result.contains("kind: shell"));
        assert!(result.contains("category: testing"));
        assert!(result.contains("description: \"Run test suite\""));
        assert!(result.contains("args:"));
        assert!(result.contains("safety:"));
        assert!(result.contains("max_runtime_sec: 60"));
        assert!(result.contains("providers:"));
        assert!(result.contains("local:"));
    }

    #[test]
    fn test_render_hook_meta() {
        let renderer = TemplateRenderer::new().unwrap();
        let data = json!({
            "id": "pre-tool-safety",
            "kind": "safety",
            "category": "lifecycle",
            "event": "PreToolUse",
            "summary": "Block dangerous operations before tool execution",
            "middleware_type": "safety"
        });

        let result = renderer.render_hook_meta(&data).unwrap();

        assert!(result.contains("id: pre-tool-safety"));
        assert!(result.contains("kind: safety"));
        assert!(result.contains("category: lifecycle"));
        assert!(result.contains("event: PreToolUse"));
        assert!(result.contains("execution:"));
        assert!(result.contains("strategy: pipeline"));
        assert!(result.contains("middleware:"));
        assert!(result.contains("- id: main"));
        assert!(result.contains("type: safety"));
        assert!(result.contains("providers:"));
        assert!(result.contains("claude:"));
    }

    #[test]
    fn test_render_hook_meta_with_default_decision() {
        let renderer = TemplateRenderer::new().unwrap();
        let data = json!({
            "id": "pre-tool-safety",
            "kind": "safety",
            "category": "lifecycle",
            "event": "PreToolUse",
            "summary": "Safety hook",
            "middleware_type": "safety",
            "default_decision": "deny"
        });

        let result = renderer.render_hook_meta(&data).unwrap();

        assert!(result.contains("default_decision: deny"));
    }

    #[test]
    fn test_render_middleware_python() {
        let renderer = TemplateRenderer::new().unwrap();
        let data = json!({
            "description": "Block dangerous shell commands",
            "event": "PreToolUse",
            "middleware_type": "safety"
        });

        let result = renderer.render_middleware_python(&data).unwrap();

        assert!(result.contains("#!/usr/bin/env python3"));
        assert!(result.contains("Block dangerous shell commands"));
        assert!(result.contains("Hook Event: PreToolUse"));
        assert!(result.contains("Type: safety"));
        assert!(result.contains("def process_hook(input_data: Dict[str, Any]) -> Dict[str, Any]:"));
        assert!(result.contains("def main():"));
        assert!(result.contains("json.load(sys.stdin)"));
        assert!(result.contains("json.dumps(output)"));
        assert!(result.contains("if __name__ == \"__main__\":"));
    }

    #[test]
    fn test_render_middleware_typescript() {
        let renderer = TemplateRenderer::new().unwrap();
        let data = json!({
            "description": "Log tool usage metrics",
            "event": "PostToolUse",
            "middleware_type": "observability"
        });

        let result = renderer.render_middleware_typescript(&data).unwrap();

        assert!(result.contains("#!/usr/bin/env bun"));
        assert!(result.contains("Log tool usage metrics"));
        assert!(result.contains("Hook Event: PostToolUse"));
        assert!(result.contains("Type: observability"));
        assert!(result.contains("interface HookInput"));
        assert!(result.contains("interface HookOutput"));
        assert!(result.contains("async function processHook"));
        assert!(result.contains("async function main()"));
        assert!(result.contains("await Bun.stdin.json()"));
        assert!(result.contains("console.log(JSON.stringify(output))"));
    }

    #[test]
    fn test_rendered_yaml_is_parseable() {
        let renderer = TemplateRenderer::new().unwrap();
        let data = json!({
            "id": "test-agent",
            "category": "testing",
            "summary": "Test agent"
        });

        let result = renderer.render_agent_meta(&data).unwrap();

        // Verify the output can be parsed as valid YAML
        let parsed = serde_yaml::from_str::<serde_yaml::Value>(&result);
        assert!(parsed.is_ok(), "Rendered YAML should be parseable");

        let yaml = parsed.unwrap();
        assert_eq!(yaml["id"], "test-agent");
        assert_eq!(yaml["kind"], "agent");
        assert_eq!(yaml["category"], "testing");
        // Note: spec_version is added by the `new` command, not in the template
    }

    #[test]
    fn test_all_templates_render_without_error() {
        let renderer = TemplateRenderer::new().unwrap();

        // Agent
        let agent_data = json!({"id": "a", "category": "c", "summary": "s"});
        assert!(renderer.render_agent_meta(&agent_data).is_ok());

        // Command
        let command_data = json!({"id": "c", "category": "cat", "summary": "s"});
        assert!(renderer.render_command_meta(&command_data).is_ok());

        // Skill
        let skill_data = json!({"id": "s", "category": "c", "summary": "sum"});
        assert!(renderer.render_skill_meta(&skill_data).is_ok());

        // Meta-prompt
        let meta_data = json!({"id": "m", "category": "c", "summary": "s"});
        assert!(renderer.render_meta_prompt_meta(&meta_data).is_ok());

        // Prompt content
        let prompt_data = json!({"title": "T", "kind": "agent", "domain": "d"});
        assert!(renderer.render_prompt_content(&prompt_data).is_ok());

        // Tool
        let tool_data = json!({"id": "t", "kind": "shell", "category": "c", "description": "d"});
        assert!(renderer.render_tool_meta(&tool_data).is_ok());

        // Hook
        let hook_data = json!({"id": "h", "kind": "k", "category": "c", "event": "e", "summary": "s", "middleware_type": "safety"});
        assert!(renderer.render_hook_meta(&hook_data).is_ok());

        // Python middleware
        let py_data = json!({"description": "d", "event": "e", "middleware_type": "safety"});
        assert!(renderer.render_middleware_python(&py_data).is_ok());

        // TypeScript middleware
        let ts_data = json!({"description": "d", "event": "e", "middleware_type": "observability"});
        assert!(renderer.render_middleware_typescript(&ts_data).is_ok());
    }
}
