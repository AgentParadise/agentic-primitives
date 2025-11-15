use criterion::{black_box, criterion_group, criterion_main, Criterion};
use std::fs;
use tempfile::TempDir;

fn setup_test_primitives(count: usize) -> TempDir {
    let temp_dir = TempDir::new().unwrap();
    let base_path = temp_dir.path().join("primitives/v1/prompts/agents/testing");
    fs::create_dir_all(&base_path).unwrap();

    for i in 0..count {
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

fn validate_single_primitive(c: &mut Criterion) {
    let temp_dir = setup_test_primitives(1);
    let prim_path = temp_dir
        .path()
        .join("primitives/v1/prompts/agents/testing/test-agent-0");

    c.bench_function("validate_single_primitive", |b| {
        b.iter(|| {
            // This would call your actual validation function
            // For now, just read the files as a placeholder
            let meta_content = fs::read_to_string(prim_path.join("test-agent-0.yaml")).unwrap();
            let content = fs::read_to_string(prim_path.join("test-agent-0.v1.md")).unwrap();
            black_box((meta_content, content));
        });
    });
}

fn validate_100_primitives(c: &mut Criterion) {
    let temp_dir = setup_test_primitives(100);
    let base_path = temp_dir.path().join("primitives/v1/prompts/agents/testing");

    c.bench_function("validate_100_primitives", |b| {
        b.iter(|| {
            for i in 0..100 {
                let prim_id = format!("test-agent-{i}");
                let prim_path = base_path.join(&prim_id);
                let meta_content =
                    fs::read_to_string(prim_path.join(format!("{prim_id}.yaml"))).unwrap();
                let content =
                    fs::read_to_string(prim_path.join(format!("{prim_id}.v1.md"))).unwrap();
                black_box((meta_content, content));
            }
        });
    });
}

criterion_group!(benches, validate_single_primitive, validate_100_primitives);
criterion_main!(benches);
