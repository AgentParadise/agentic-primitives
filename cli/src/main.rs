use clap::{Parser, Subcommand};

#[derive(Parser)]
#[command(name = "agentic")]
#[command(about = "Manage agentic primitives", long_about = None)]
#[command(version)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Initialize a new primitives repository
    Init {
        /// Target directory (default: current directory)
        #[arg(short, long)]
        path: Option<String>,
    },
    /// Create a new primitive
    New {
        // TODO: subcommands for prompt/tool/hook
    },
    /// Validate primitives
    Validate {
        /// Path to validate (default: all)
        path: Option<String>,
    },
    /// List primitives
    List {
        // TODO: filters
    },
    /// Inspect a primitive
    Inspect {
        /// Primitive ID or path
        id: String,
    },
    /// Manage primitive versions
    Version {
        // TODO: subcommands
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

fn main() {
    let cli = Cli::parse();
    
    // TODO: Implement command routing
    match cli.command {
        Commands::Init { path } => {
            println!("Init command not yet implemented (path: {path:?})");
        }
        Commands::New {} => {
            println!("New command not yet implemented");
        }
        Commands::Validate { path } => {
            println!("Validate command not yet implemented (path: {path:?})");
        }
        Commands::List {} => {
            println!("List command not yet implemented");
        }
        Commands::Inspect { id } => {
            println!("Inspect command not yet implemented (id: {id})");
        }
        Commands::Version {} => {
            println!("Version command not yet implemented");
        }
        Commands::Migrate { add_versions } => {
            println!("Migrate command not yet implemented (add_versions: {add_versions})");
        }
        Commands::Build { provider, output } => {
            println!("Build command not yet implemented (provider: {provider}, output: {output:?})");
        }
        Commands::Install { provider, global } => {
            println!("Install command not yet implemented (provider: {provider}, global: {global})");
        }
        Commands::TestHook { path, input } => {
            println!("TestHook command not yet implemented (path: {path}, input: {input})");
        }
    }
}
