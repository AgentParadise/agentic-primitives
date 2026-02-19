---
description: Auto-generate documented .env.example from typed config, sync .env idempotently, fail fast on missing required vars
argument-hint: "[language] - python (default), typescript, go"
model: sonnet
allowed-tools: Read, Write, Bash, Glob, Grep
---

# Env Management

**Three components. One rule: code is the source of truth.**

```
  Typed config class          ← single source of truth
  (with descriptions)              field descriptions become docs
         │
         │  generate
         ▼
     .env.example             ← committed to git, always fresh
     (documented, organized)       no manual maintenance, no drift
         │
         │  idempotent sync
         ▼
       .env                   ← gitignored, user secrets
         ├── existing values  →  never overwritten
         ├── new variables    →  added with defaults
         └── unknown vars     →  preserved, flagged
         │
         │  startup validation
         ▼
    fail fast                 ← crash immediately with a clear error
    (required vars checked)        not silently at call-time
```

---

## Philosophy

### 1. Central config at the root

One place defines every environment variable the application uses.
Each field has a **type**, a **default** (or is explicitly required), and a **description**
that says what the variable does and where to get the value.

No scattered `os.environ.get("THING")` calls. No undocumented vars.
No README section that goes stale. The code *is* the documentation.

### 2. Generator removes noise and deadweight

Run one command (`just gen-env`) and `.env.example` is recreated from the config.
Removed fields disappear. New fields appear with their description.
Secrets are always emitted as `KEY=` (never leak defaults).
Required vars are marked `[REQUIRED]`.

Fields that are discovered at runtime (not configured upfront) can be **excluded**
from the template entirely — they don't appear in `.env.example`, and users aren't
confused about whether they need to set them.

Fixed sections (security warnings, deployment notes) live in the generator code —
they survive every regeneration.

### 3. Fail fast on startup

At application boot, validate that all required vars are present and well-formed.
Crash immediately with a clear message pointing to the missing var.
Never let a missing secret surface as a cryptic error buried in a stack trace at 2am.

---

## Workflow

### 1. Audit existing state

```bash
# What env vars does the codebase reference today?
grep -r "os\.environ\|os\.getenv\|process\.env\." --include="*.py" --include="*.ts" -h \
  | grep -oP '(?<=environ\["|getenv\(")[^"]+' | sort -u

# Existing config structure?
find . -name "settings.py" -o -name "config.py" -o -name "env.ts" | head -10

# Generator already exists?
ls scripts/gen* scripts/generate* 2>/dev/null
```

### 2. Design the config class

See `references/<language>/` for a full implementation.

Key decisions:
- **One root config** with nested sub-configs for each concern (GitHub, DB, logging, etc.)
- **Explicit required** — no default means required; fail fast if missing
- **Secrets typed distinctly** — `SecretStr` in Python, `z.string()` with `.min(1)` in TS
- **Descriptions point to where** — "Get from: https://..." not just "The API key"
- **Exclude dynamic fields** — if a value comes from a webhook payload or API response,
  it doesn't belong in `.env`

### 3. Write the generator

See `references/<language>/generate_env_example.py` (or equivalent).

The generator must:
1. Introspect the config class — not hand-written, or it will drift
2. Format field descriptions as comments above each `KEY=value` line
3. Emit secrets as `KEY=` always (never show the default)
4. Mark required fields clearly: `[REQUIRED]`
5. Group vars into named sections with headers
6. Support `exclude={"field_name"}` for dynamic/runtime-discovered values
7. Idempotently sync `.env` — preserving existing values, adding new ones,
   keeping unknown vars in a clearly marked section

### 4. Wire up the command

```makefile
# justfile
gen-env:
    uv run python scripts/generate_env_example.py

# Or Makefile
gen-env:
	python scripts/generate_env_example.py
```

Run it, commit `.env.example`. Never commit `.env`.

### 5. Add startup validation

```python
# At app entry point — not lazily, not on first use
settings = get_settings()  # raises immediately if required vars are missing
```

The config class should raise a clear `ValueError` or `ValidationError` naming
the exact missing variable and how to get it — not just "configuration error".

### 6. Commit and document

```bash
git add .env.example scripts/generate_env_example.py
git commit -m "chore: add auto-generated env management"

# .gitignore
echo ".env" >> .gitignore
```

Add to the project README:
```
## Configuration
Copy `.env.example` to `.env` and fill in the required values.
Run `just gen-env` after adding any new config field.
```

---

## Field Patterns

| Pattern | How |
|---------|-----|
| Required secret | `SecretStr` with no default → emitted as `KEY=`, marked `[REQUIRED]` |
| Optional with default | `str = "info"` → emitted as `KEY=info` |
| Dynamic/runtime value | Use `exclude={"field"}` → hidden from template entirely |
| Feature-gated secret | `SecretStr` with empty default → marked `[REQUIRED when using this feature]` |
| Persistent header | Written in generator code → survives every regeneration |

---

## Report

```markdown
## Env Management Setup

**Config class:** `<path/to/settings.py>`
**Generator:** `scripts/generate_env_example.py`
**Command:** `just gen-env`

**Sections:** <list sections and var counts>

**Excluded (dynamic):** <field names and why>

**Startup validation:** ✅ fails fast on missing required vars

**Next:** run `just gen-env`, commit `.env.example`, add `.env` to `.gitignore`
```

---

## References

- `references/python/` — Full Python implementation (pydantic-settings)
- `sdlc/centralized-configuration` — Broader cross-language patterns
- `sdlc/macos-keychain-secrets` — Securely storing secrets on macOS
