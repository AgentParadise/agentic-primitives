use agentic_primitives::commands;
use agentic_primitives::commands::inspect::{InspectArgs, OutputFormat as InspectFormat};
use agentic_primitives::commands::list::{ListArgs, OutputFormat as ListFormat};
use agentic_primitives::commands::migrate::MigrateArgs;
use agentic_primitives::commands::new::{NewPrimitiveArgs, PrimitiveType, PromptKind};
use agentic_primitives::commands::validate::ValidateArgs;
use agentic_primitives::commands::version::VersionCommand;
use agentic_primitives::config::PrimitivesConfig;
use agentic_primitives::spec_version::SpecVersion;
use agentic_primitives::validators::ValidationLayers;
use clap::{Parser, Subcommand, ValueEnum};
use colored::Colorize;
use std::path::PathBuf;

#[derive(Parser)]
#[command(name = "agentic-p")]
#[command(about = "Manage agentic primitives", long_about = None)]
#[command(version)]
struct Cli {
    /// Specification version to use (v1, experimental)
    #[arg(long, global = true, default_value = "v1")]
    spec_version: String,

    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Initialize a new primitives repository
    Init {
        /// Target directory (default: current directory)
        #[arg(short, long, default_value = ".")]
        path: PathBuf,
    },

    /// Create a new primitive
    New {
        /// Primitive type: prompt, tool, hook
        #[arg(value_enum)]
        prim_type: PrimType,

        /// Category (kebab-case)
        category: String,

        /// Primitive ID (kebab-case)
        id: String,

        /// Prompt kind (required for prompts: agent, command, skill, meta-prompt)
        #[arg(short, long, value_enum)]
        kind: Option<PrimKind>,

        /// Output to experimental directory
        #[arg(long)]
        experimental: bool,
    },

    /// Validate primitives
    Validate {
        /// Path to primitive or directory
        path: PathBuf,

        /// Validation layer to run
        #[arg(long, value_enum, default_value = "all")]
        layer: ValidationLayer,

        /// Output as JSON
        #[arg(long)]
        json: bool,
    },

    /// List primitives with filtering
    List {
        /// Path to primitives directory (optional)
        path: Option<PathBuf>,

        /// Filter by type (prompt, tool, hook)
        #[arg(long)]
        type_filter: Option<String>,

        /// Filter by kind (agent, command, skill, meta-prompt, etc.)
        #[arg(long)]
        kind: Option<String>,

        /// Filter by category
        #[arg(long)]
        category: Option<String>,

        /// Filter by tag
        #[arg(long)]
        tag: Option<String>,

        /// Show all versions
        #[arg(long)]
        all_versions: bool,

        /// Output format
        #[arg(long, value_enum, default_value = "table")]
        format: ListOutputFormat,
    },

    /// Inspect a primitive in detail
    Inspect {
        /// Primitive ID or path
        primitive: String,

        /// Specific version to inspect
        #[arg(long)]
        version: Option<u32>,

        /// Show full content (not just preview)
        #[arg(long)]
        full_content: bool,

        /// Output format
        #[arg(long, value_enum, default_value = "pretty")]
        format: InspectOutputFormat,
    },

    /// Manage primitive versions
    Version {
        #[command(subcommand)]
        command: VersionCommand,
    },

    /// Migrate primitives between spec versions
    Migrate(MigrateArgs),

    /// Build provider-specific outputs
    Build {
        /// Provider (claude, openai)
        #[arg(short, long)]
        provider: String,

        /// Output directory (default: ./build/<provider>/)
        #[arg(short, long)]
        output: Option<PathBuf>,

        /// Build single primitive (path to primitive directory)
        #[arg(long)]
        primitive: Option<String>,

        /// Filter by type (prompt, tool, hook)
        #[arg(long)]
        type_filter: Option<String>,

        /// Filter by kind (agent, command, skill, etc.)
        #[arg(long)]
        kind: Option<String>,

        /// Clean output directory before build
        #[arg(long)]
        clean: bool,

        /// Verbose output
        #[arg(short, long)]
        verbose: bool,
    },

    /// Install built primitives to system or project location
    Install {
        /// Provider (claude, openai)
        #[arg(short, long)]
        provider: String,

        /// Install globally to user directory (default: project)
        #[arg(short, long)]
        global: bool,

        /// Build directory to install from (default: ./build/<provider>/)
        #[arg(long)]
        build_dir: Option<PathBuf>,

        /// Backup existing files before install (default: true)
        #[arg(long, default_value = "true")]
        backup: bool,

        /// Dry-run mode (don't actually copy files)
        #[arg(long)]
        dry_run: bool,

        /// Verbose output
        #[arg(short, long)]
        verbose: bool,
    },

    /// Test a hook locally
    TestHook {
        /// Hook path
        path: String,

        /// Input JSON file or inline JSON
        #[arg(short, long)]
        input: String,

        /// Output JSON format
        #[arg(long)]
        json: bool,

        /// Verbose output (show stdout/stderr)
        #[arg(short, long)]
        verbose: bool,
    },
}

#[derive(Copy, Clone, PartialEq, Eq, PartialOrd, Ord, ValueEnum)]
enum PrimType {
    Prompt,
    Tool,
    Hook,
}

impl From<PrimType> for PrimitiveType {
    fn from(val: PrimType) -> Self {
        match val {
            PrimType::Prompt => PrimitiveType::Prompt,
            PrimType::Tool => PrimitiveType::Tool,
            PrimType::Hook => PrimitiveType::Hook,
        }
    }
}

#[derive(Copy, Clone, PartialEq, Eq, PartialOrd, Ord, ValueEnum)]
enum PrimKind {
    Agent,
    Command,
    Skill,
    MetaPrompt,
}

impl From<PrimKind> for PromptKind {
    fn from(val: PrimKind) -> Self {
        match val {
            PrimKind::Agent => PromptKind::Agent,
            PrimKind::Command => PromptKind::Command,
            PrimKind::Skill => PromptKind::Skill,
            PrimKind::MetaPrompt => PromptKind::MetaPrompt,
        }
    }
}

#[derive(Copy, Clone, PartialEq, Eq, PartialOrd, Ord, ValueEnum)]
enum ValidationLayer {
    All,
    Structural,
    Schema,
    Semantic,
}

impl From<ValidationLayer> for ValidationLayers {
    fn from(val: ValidationLayer) -> Self {
        match val {
            ValidationLayer::All => ValidationLayers::All,
            ValidationLayer::Structural => ValidationLayers::Structural,
            ValidationLayer::Schema => ValidationLayers::Schema,
            ValidationLayer::Semantic => ValidationLayers::Semantic,
        }
    }
}

#[derive(Copy, Clone, PartialEq, Eq, PartialOrd, Ord, ValueEnum)]
enum ListOutputFormat {
    Table,
    Json,
    Yaml,
}

impl From<ListOutputFormat> for ListFormat {
    fn from(val: ListOutputFormat) -> Self {
        match val {
            ListOutputFormat::Table => ListFormat::Table,
            ListOutputFormat::Json => ListFormat::Json,
            ListOutputFormat::Yaml => ListFormat::Yaml,
        }
    }
}

#[derive(Copy, Clone, PartialEq, Eq, PartialOrd, Ord, ValueEnum)]
enum InspectOutputFormat {
    Pretty,
    Json,
    Yaml,
}

impl From<InspectOutputFormat> for InspectFormat {
    fn from(val: InspectOutputFormat) -> Self {
        match val {
            InspectOutputFormat::Pretty => InspectFormat::Pretty,
            InspectOutputFormat::Json => InspectFormat::Json,
            InspectOutputFormat::Yaml => InspectFormat::Yaml,
        }
    }
}

fn main() {
    let cli = Cli::parse();

    // Parse spec version
    let spec_version: SpecVersion = match cli.spec_version.parse() {
        Ok(v) => v,
        Err(e) => {
            eprintln!("{} {}", "Error:".red(), e);
            std::process::exit(1);
        }
    };

    // Load config (needed for list and inspect commands)
    let config = PrimitivesConfig::load_from_current_dir().unwrap_or_else(|_| {
        // Fallback to default config
        PrimitivesConfig::default()
    });

    // Execute command
    let result = match cli.command {
        Commands::Init { path } => commands::init::init(&path),

        Commands::New {
            prim_type,
            category,
            id,
            kind,
            experimental,
        } => {
            let args = NewPrimitiveArgs {
                prim_type: prim_type.into(),
                category,
                id,
                kind: kind.map(|k| k.into()),
                spec_version,
                experimental,
            };
            commands::new::new_primitive(args)
        }

        Commands::Validate { path, layer, json } => {
            let args = ValidateArgs {
                path,
                spec_version: Some(spec_version),
                layer: layer.into(),
                json,
            };
            commands::validate::validate(args)
        }

        Commands::List {
            path,
            type_filter,
            kind,
            category,
            tag,
            all_versions,
            format,
        } => {
            let args = ListArgs {
                path,
                type_filter,
                kind,
                category,
                tag,
                all_versions,
                format: format.into(),
            };
            commands::list::execute(&args, &config)
        }

        Commands::Inspect {
            primitive,
            version,
            full_content,
            format,
        } => {
            let args = InspectArgs {
                primitive,
                version,
                full_content,
                format: format.into(),
            };
            commands::inspect::execute(&args, &config)
        }

        Commands::Version { command } => commands::version::execute(&command, &config),

        Commands::Migrate(args) => commands::migrate::execute(&args, &config),

        Commands::Build {
            provider,
            output,
            primitive,
            type_filter,
            kind,
            clean,
            verbose,
        } => {
            let args = commands::build::BuildArgs {
                provider,
                output,
                primitive,
                type_filter,
                kind,
                clean,
                verbose,
            };
            commands::build::execute(&args, &config)
        }

        Commands::Install {
            provider,
            global,
            build_dir,
            backup,
            dry_run,
            verbose,
        } => {
            let args = commands::install::InstallArgs {
                provider,
                global,
                build_dir,
                backup,
                dry_run,
                verbose,
            };
            commands::install::execute(&args, &config).map(|_| ())
        }

        Commands::TestHook {
            path,
            input,
            json,
            verbose,
        } => {
            let args = commands::test_hook::TestHookArgs {
                path,
                input,
                json,
                verbose,
            };
            commands::test_hook::execute(&args, &config).map(|_| ())
        }
    };

    // Handle result
    if let Err(e) = result {
        use colored::Colorize;
        eprintln!("{} {}", "Error:".red().bold(), e);
        std::process::exit(1);
    }
}
