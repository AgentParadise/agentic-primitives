use criterion::{black_box, criterion_group, criterion_main, Criterion};
use std::fs;
use tempfile::TempDir;

fn setup_build_test(prim_count: usize) -> TempDir {
    let temp_dir = TempDir::new().unwrap();
    let base_path = temp_dir.path().join("primitives/v1/prompts/agents/testing");
    fs::create_dir_all(&base_path).unwrap();

    for i in 0..prim_count {
        let prim_id = format!("test-agent-{i}");
        let prim_path = base_path.join(&prim_id);
        fs::create_dir_all(&prim_path).unwrap();

        let meta = format!(
            r#"id: {prim_id}
kind: agent
category: testing
summary: Test agent {i}
model_ref: claude/sonnet
version: 1
status: active
"#
        );

        fs::write(prim_path.join(format!("{prim_id}.yaml")), meta).unwrap();
        fs::write(
            prim_path.join(format!("{prim_id}.v1.md")),
            format!("You are test agent {i}."),
        )
        .unwrap();
    }

    temp_dir
}

fn build_single_primitive(c: &mut Criterion) {
    let temp_dir = setup_build_test(1);

    c.bench_function("build_single_primitive", |b| {
        b.iter(|| {
            // Placeholder for actual build logic
            let prim_path = temp_dir
                .path()
                .join("primitives/v1/prompts/agents/testing/test-agent-0");
            let _meta = fs::read_to_string(prim_path.join("test-agent-0.yaml")).unwrap();
            let content = fs::read_to_string(prim_path.join("test-agent-0.v1.md")).unwrap();

            // Simulate transformation
            let output = format!("# Test Agent\n\n{content}");
            black_box(output);
        });
    });
}

fn build_100_primitives(c: &mut Criterion) {
    let temp_dir = setup_build_test(100);

    c.bench_function("build_100_primitives", |b| {
        b.iter(|| {
            let base_path = temp_dir.path().join("primitives/v1/prompts/agents/testing");

            for i in 0..100 {
                let prim_id = format!("test-agent-{i}");
                let prim_path = base_path.join(&prim_id);
                let _meta = fs::read_to_string(prim_path.join(format!("{prim_id}.yaml"))).unwrap();
                let content =
                    fs::read_to_string(prim_path.join(format!("{prim_id}.v1.md"))).unwrap();

                let output = format!("# Test Agent {i}\n\n{content}");
                black_box(output);
            }
        });
    });
}

criterion_group!(benches, build_single_primitive, build_100_primitives);
criterion_main!(benches);
