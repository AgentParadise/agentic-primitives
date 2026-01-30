/// Embedded templates for scaffolding primitives
pub struct Templates;

impl Templates {
    // Prompt templates
    pub const AGENT_META: &'static str = include_str!("./templates/agent.meta.yaml.hbs");
    pub const COMMAND_META: &'static str = include_str!("./templates/command.meta.yaml.hbs");
    pub const SKILL_META: &'static str = include_str!("./templates/skill.meta.yaml.hbs");
    pub const META_PROMPT_META: &'static str =
        include_str!("./templates/meta-prompt.meta.yaml.hbs");
    pub const PROMPT_CONTENT: &'static str = include_str!("./templates/prompt.md.hbs");

    // Tool templates
    pub const TOOL_META: &'static str = include_str!("./templates/tool.meta.yaml.hbs");

    // Hook templates
    pub const HOOK_META: &'static str = include_str!("./templates/hook.meta.yaml.hbs");

    // Middleware templates
    pub const MIDDLEWARE_PYTHON: &'static str = include_str!("./templates/middleware.py.hbs");
    pub const MIDDLEWARE_TYPESCRIPT: &'static str = include_str!("./templates/middleware.ts.hbs");
}
