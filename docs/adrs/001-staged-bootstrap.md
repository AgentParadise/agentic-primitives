# ADR-001: Staged Bootstrap Strategy

```yaml
---
status: accepted
created: 2025-11-13
updated: 2025-11-13
deciders: System Architect
consulted: Development Team
informed: All Stakeholders
---
```

## Context

When building a meta-system that generates its own components (like agentic primitives that can generate other primitives), we face a bootstrapping problem: **how do we create the first meta-prompt without already having a meta-prompt to generate it?**

Additionally, we want to demonstrate the system's capability by having it generate its own components, rather than manually crafting everything.

### The Bootstrapping Challenge

1. **Initial State**: No primitives exist
2. **Goal State**: A library of primitives that can generate more primitives
3. **The Paradox**: We need a meta-prompt to generate primitives, but we need primitives to have a meta-prompt

### Alternative Approaches Considered

1. **Full Manual Creation**
   - Manually write all primitives
   - Pros: Complete control, no bootstrapping complexity
   - Cons: Labor-intensive, doesn't demonstrate self-generation capability, creates future maintenance burden

2. **External Generator**
   - Use a one-off external script to generate all primitives
   - Pros: Faster initial creation
   - Cons: External dependency, doesn't validate the system can self-generate

3. **Parallel Bootstrap**
   - Create multiple meta-prompts simultaneously
   - Pros: Potentially faster
   - Cons: Complex coordination, unclear dependencies, risk of inconsistency

4. **Staged Bootstrap** (CHOSEN)
   - Hand-craft the first meta-prompt (`generate-primitive`)
   - Use it to generate specialized meta-prompts
   - Use those to generate the rest
   - Pros: Validates system capability, creates single source of truth, demonstrates composability
   - Cons: Requires careful design of first meta-prompt

## Decision

We will implement a **staged bootstrap strategy** where:

1. **Stage 1: Foundation**
   - Manually create repository structure, schemas, validation engine, and CLI
   - Hand-craft the first meta-prompt: `generate-primitive`
   - This meta-prompt contains complete knowledge of:
     - All primitive types (agents, commands, skills, meta-prompts, tools, hooks)
     - File structure conventions (category/id nested structure)
     - Versioning requirements
     - Meta.yaml schema for each type
     - Best practices for prompt content

2. **Stage 2: Specialized Generation**
   - Use `generate-primitive` to create specialized meta-prompts:
     - `generate-agent` - Expert at creating agent personas
     - `generate-command` - Expert at creating task workflows
     - `generate-skill` - Expert at creating knowledge overlays
     - `generate-tool` - Expert at creating tool specifications
     - `generate-hook` - Expert at creating lifecycle hooks

3. **Stage 3: Library Expansion**
   - Use specialized meta-prompts to generate production primitives:
     - Agents: python-pro, web-architect, devops-sensei
     - Commands: code-review, test-generator, refactor-assistant
     - Skills: testing-patterns, async-patterns, api-design
     - Tools: run-tests, search-code, format-code
     - Hooks: block-dangerous-commands, log-operations, emit-metrics

4. **Stage 4: Validation & Iteration**
   - Validate all generated primitives
   - Test with real use cases (Claude Agent SDK)
   - Refine meta-prompts based on quality of generated output
   - Iterate: better meta-prompts → better primitives

### The Bootstrap Meta-Prompt

The `generate-primitive` meta-prompt must be:

- **Complete**: Encode all conventions, schemas, and best practices
- **Precise**: Generate valid primitives that pass all validation layers
- **Flexible**: Handle all primitive types without specialization
- **Self-documenting**: Include examples and rationale
- **Versioned**: Immutable with hash validation (v1 is foundation)

## Consequences

### Positive

✅ **Single Source of Truth**: The first meta-prompt encodes all conventions, preventing drift

✅ **Self-Validating**: If `generate-primitive` can generate valid primitives, the system works

✅ **Scalable**: Each generated meta-prompt can be refined independently

✅ **Demonstrable**: Shows the system is capable of self-generation from the start

✅ **Maintainable**: Updates to conventions only require updating meta-prompts

✅ **Versioned**: Can benchmark primitive quality across meta-prompt versions

### Negative

⚠️ **Initial Investment**: The first meta-prompt requires significant careful hand-crafting

⚠️ **Single Point of Failure**: If `generate-primitive` is flawed, all generated primitives inherit issues

⚠️ **Iterative Refinement Required**: May need multiple iterations to get quality right

⚠️ **Validation Dependency**: Must have robust validation before trusting generated output

### Mitigations

1. **Extensive Testing**: Thoroughly test `generate-primitive` with multiple primitive types before Stage 2
2. **Manual Review**: Human review of all generated meta-prompts before using them
3. **Validation Checkpoints**: Run full validation after each generation stage
4. **Version Control**: Track meta-prompt versions, enabling rollback if quality degrades
5. **Hash Verification**: Ensure meta-prompts remain immutable once validated

## Implementation Timeline

### Phase 1: Foundation (Milestone 1-23)
- Repository structure
- Schemas and validation
- CLI tools
- Hook infrastructure
- Provider adapters

### Phase 2: Bootstrap Meta-Prompt (Milestone 24)
- Hand-craft `generate-primitive` v1
- Test with sample primitives
- Validate against all three layers
- Calculate and store BLAKE3 hash
- Document design decisions and conventions

### Phase 3: Specialized Generation (Post-MVP)
- Generate `generate-agent` using `generate-primitive`
- Generate `generate-command` using `generate-primitive`
- Generate `generate-skill` using `generate-primitive`
- Generate `generate-tool` using `generate-primitive`
- Generate `generate-hook` using `generate-primitive`
- Validate all generated meta-prompts

### Phase 4: Library Expansion (Ongoing)
- Use specialized meta-prompts to create production primitives
- Continuously validate quality
- Refine meta-prompts based on output
- Track metrics: validation pass rate, manual correction rate

## Success Criteria

The bootstrap strategy is successful when:

1. ✅ `generate-primitive` v1 exists and passes all validation
2. ✅ `generate-primitive` can generate valid primitives for all types
3. ✅ Generated primitives pass all three validation layers without manual fixes
4. ✅ Specialized meta-prompts improve output quality over generic `generate-primitive`
5. ✅ The system can expand the library with minimal human intervention
6. ✅ Meta-prompt versions can be benchmarked for quality improvements

## Related Decisions

- **ADR-002: Strict Validation** - Ensures generated primitives are valid
- **ADR-003: Non-Interactive Scaffolding** - CLI creates structure, AI creates content
- **ADR-009: Versioned Primitives** - Enables benchmarking meta-prompt quality

## References

- [Bootstrapping (compilers)](https://en.wikipedia.org/wiki/Bootstrapping_(compilers))
- [Self-hosting](https://en.wikipedia.org/wiki/Self-hosting_(compilers))
- [Meta-circular evaluator](https://en.wikipedia.org/wiki/Meta-circular_evaluator)
- Claude Agent SDK documentation
- LangChain prompt templates

## Notes

This ADR establishes the philosophical foundation for the entire project: **the system should be capable of generating its own components**. This validates that:

- The primitive abstraction is complete
- The validation system is robust
- The conventions are well-defined
- The system is truly agentic (autonomous)

The first meta-prompt is the most critical component and deserves significant investment in design and testing.

---

**Status**: Accepted  
**Last Updated**: 2025-11-13

