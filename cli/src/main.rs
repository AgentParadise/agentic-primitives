use agentic_primitives::commands;
use agentic_primitives::commands::new::{NewPrimitiveArgs, PrimitiveType, PromptKind};
use agentic_primitives::commands::validate::ValidateArgs;
use agentic_primitives::spec_version::SpecVersion;
use agentic_primitives::validators::ValidationLayers;
use clap::{Parser, Subcommand, ValueEnum};
use colored::Colorize;
use std::path::PathBuf;

#[derive(Parser)]
#[command(name = "agentic")]
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

    /// List primitives
    List {
        // TODO: Wave 7
    },

    /// Inspect a primitive
    Inspect {
        /// Primitive ID or path
        id: String,
    },

    /// Manage primitive versions
    Version {
        // TODO: Wave 7
    },

    /// Migrate primitives to latest format
    Migrate {
        /// Add versioning to primitives
        #[arg(long)]
        add_versions: bool,
    },

    /// Build provider-specific outputs
    Build {
        /// Provider (claude, openai, cursor)
        #[arg(short, long)]
        provider: String,

        /// Output directory
        #[arg(short, long)]
        output: Option<String>,
    },

    /// Install to provider directory
    Install {
        /// Provider (claude, openai, cursor)
        #[arg(short, long)]
        provider: String,

        /// Install globally
        #[arg(short, long)]
        global: bool,
    },

    /// Test a hook locally
    TestHook {
        /// Hook path
        path: String,

        /// Input JSON file
        #[arg(short, long)]
        input: String,
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

        Commands::List {} => {
            eprintln!("List command not yet implemented (Wave 7)");
            std::process::exit(1);
        }

        Commands::Inspect { id } => {
            eprintln!("Inspect command not yet implemented (Wave 7): {id}");
            std::process::exit(1);
        }

        Commands::Version {} => {
            eprintln!("Version command not yet implemented (Wave 7)");
            std::process::exit(1);
        }

        Commands::Migrate { add_versions } => {
            eprintln!("Migrate command not yet implemented (Wave 7): add_versions={add_versions}");
            std::process::exit(1);
        }

        Commands::Build { provider, output } => {
            eprintln!("Build command not yet implemented (Wave 9): provider={provider}, output={output:?}");
            std::process::exit(1);
        }

        Commands::Install { provider, global } => {
            eprintln!("Install command not yet implemented (Wave 9): provider={provider}, global={global}");
            std::process::exit(1);
        }

        Commands::TestHook { path, input } => {
            eprintln!("TestHook command not yet implemented (Wave 10): path={path}, input={input}");
            std::process::exit(1);
        }
    };

    // Handle result
    if let Err(e) = result {
        use colored::Colorize;
        eprintln!("{} {}", "Error:".red().bold(), e);
        std::process::exit(1);
    }
}
