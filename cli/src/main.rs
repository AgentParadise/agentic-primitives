use agentic_primitives::spec_version::SpecVersion;
use clap::{Parser, Subcommand};

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

    // Parse spec version
    let spec_version: SpecVersion = match cli.spec_version.parse() {
        Ok(v) => v,
        Err(e) => {
            eprintln!("Error: {e}");
            std::process::exit(1);
        }
    };

    println!("Using spec version: {spec_version}");

    // TODO: Implement command routing
    match cli.command {
        Commands::Init { path } => {
            println!(
                "Init command not yet implemented (path: {path:?}, spec_version: {spec_version})"
            );
        }
        Commands::New {} => {
            println!("New command not yet implemented (spec_version: {spec_version})");
        }
        Commands::Validate { path } => {
            println!("Validate command not yet implemented (path: {path:?}, spec_version: {spec_version})");
        }
        Commands::List {} => {
            println!("List command not yet implemented (spec_version: {spec_version})");
        }
        Commands::Inspect { id } => {
            println!(
                "Inspect command not yet implemented (id: {id}, spec_version: {spec_version})"
            );
        }
        Commands::Version {} => {
            println!("Version command not yet implemented (spec_version: {spec_version})");
        }
        Commands::Migrate { add_versions } => {
            println!("Migrate command not yet implemented (add_versions: {add_versions}, spec_version: {spec_version})");
        }
        Commands::Build { provider, output } => {
            println!(
                "Build command not yet implemented (provider: {provider}, output: {output:?}, spec_version: {spec_version})"
            );
        }
        Commands::Install { provider, global } => {
            println!(
                "Install command not yet implemented (provider: {provider}, global: {global}, spec_version: {spec_version})"
            );
        }
        Commands::TestHook { path, input } => {
            println!("TestHook command not yet implemented (path: {path}, input: {input}, spec_version: {spec_version})");
        }
    }
}
