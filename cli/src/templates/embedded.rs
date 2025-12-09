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
    pub const TOOL_IMPL_PYTHON: &'static str = include_str!("./templates/tool.impl.py.hbs");
    pub const TOOL_IMPL_TYPESCRIPT: &'static str = include_str!("./templates/tool.impl.ts.hbs");
    pub const TOOL_PYPROJECT: &'static str = include_str!("./templates/tool.pyproject.hbs");
    pub const TOOL_PACKAGE_JSON: &'static str = include_str!("./templates/tool.package-json.hbs");
    pub const TOOL_TSCONFIG: &'static str = include_str!("./templates/tool.tsconfig.hbs");
    pub const TOOL_TEST_PYTHON: &'static str = include_str!("./templates/tool.test.py.hbs");
    pub const TOOL_TEST_TYPESCRIPT: &'static str = include_str!("./templates/tool.test.ts.hbs");
    pub const TOOL_README: &'static str = include_str!("./templates/tool.readme.hbs");

    // Hook templates
    pub const HOOK_META: &'static str = include_str!("./templates/hook.meta.yaml.hbs");

    // Middleware templates
    pub const MIDDLEWARE_PYTHON: &'static str = include_str!("./templates/middleware.py.hbs");
    pub const MIDDLEWARE_TYPESCRIPT: &'static str = include_str!("./templates/middleware.ts.hbs");
}
