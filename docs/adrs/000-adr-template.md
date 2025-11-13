---
title: "ADR-XXX: [Short Title]"
status: [draft | proposed | accepted | rejected | deprecated | superseded]
created: YYYY-MM-DD
updated: YYYY-MM-DD
author: [Your Name]
supersedes: [ADR-XXX if applicable]
superseded_by: [ADR-XXX if applicable]
---

# ADR-XXX: [Short Descriptive Title]

## Status

**[Draft | Proposed | Accepted | Rejected | Deprecated | Superseded]**

- Created: YYYY-MM-DD
- Updated: YYYY-MM-DD
- Author(s): [Name(s)]
- Supersedes: ADR-XXX (if applicable)
- Superseded by: ADR-XXX (if applicable)

## Context

What is the issue we're facing? What forces are at play (technical, business, political, social)? Describe the context and constraints that led to this decision.

Keep this section focused on the problem space, not the solution.

**Aim**: 50-150 lines

## Decision

What is the change we're proposing/making? State the decision clearly and concisely.

Use active voice: "We will...", "We have decided to...", "We propose to..."

If there are multiple options, state which one is chosen here, then detail alternatives below.

**Aim**: 20-50 lines

## Alternatives Considered

What other options did we evaluate? For each alternative:

### Alternative 1: [Name]

**Description**: Brief description of this approach

**Pros**:
- Advantage 1
- Advantage 2

**Cons**:
- Disadvantage 1
- Disadvantage 2

**Reason for rejection**: Why this wasn't chosen

---

### Alternative 2: [Name]

[Same structure as Alternative 1]

---

**Aim**: 50-150 lines total for all alternatives

## Consequences

What becomes easier or more difficult because of this decision?

### Positive Consequences
- Benefit 1 with explanation
- Benefit 2 with explanation

### Negative Consequences
- Trade-off 1 with explanation
- Trade-off 2 with explanation

### Neutral Consequences
- Change 1 that's neither good nor bad
- Change 2 that's neither good nor bad

**Aim**: 30-80 lines

## Implementation Notes

Practical guidance for implementing this decision. What needs to change? What needs to be built? What needs to be refactored?

- Specific actions required
- Systems/components affected
- Migration path (if applicable)
- Breaking changes (if applicable)

**Aim**: 20-60 lines

## References

- Links to related documents, discussions, or external resources
- Related ADRs
- Technical documentation
- Research papers or blog posts
- GitHub issues or pull requests

**Format**:
- [Title](URL) - Brief description
- ADR-XXX: Related Decision Title

**Aim**: 10-30 lines

---

## Template Guidelines

### Length Guidelines
- **Target**: 300 lines or less
- **Maximum**: 500 lines (hard limit)
- **Minimum**: 100 lines (ensure sufficient detail)

If an ADR exceeds 500 lines, consider:
1. Splitting into multiple ADRs
2. Moving detailed technical specs to separate docs
3. Summarizing alternatives more concisely
4. Moving implementation details to separate docs

### Writing Style
- **Be concise**: Every word should add value
- **Be specific**: Avoid vague statements
- **Be actionable**: Readers should know what to do
- **Use active voice**: "We will use X" not "X will be used"
- **Avoid jargon**: Explain technical terms when necessary

### Frontmatter Fields

**Required**:
- `title`: ADR number and short title (e.g., "ADR-001: Use Provider-Scoped Models")
- `status`: Current status (see Status Values below)
- `created`: Date when ADR was first written (YYYY-MM-DD)
- `updated`: Date of latest modification/status change (YYYY-MM-DD)
- `author`: Person(s) who wrote this ADR

**Optional**:
- `supersedes`: ADR number this replaces
- `superseded_by`: ADR number that replaces this
- `tags`: Keywords for categorization

**Note**: When first creating an ADR, `created` and `updated` will be the same date. Update the `updated` field whenever the status changes or content is modified.

### Status Values

- **draft**: Work in progress, not ready for review
- **proposed**: Ready for review and discussion
- **accepted**: Decision has been approved and should be implemented
- **rejected**: Decision was considered but rejected
- **deprecated**: Decision was accepted but is no longer recommended
- **superseded**: Replaced by a newer ADR (reference it)

### Section Guidelines

#### Context
Answer:
- What problem are we solving?
- Why is this decision necessary now?
- What constraints do we have?
- What assumptions are we making?

Avoid jumping to solutions in this section.

#### Decision
Answer:
- What exactly are we doing?
- What is the scope of this decision?
- What is explicitly out of scope?

Be clear enough that someone can implement without ambiguity.

#### Alternatives
Include at least 2-3 alternatives to show you've done due diligence.

For each alternative:
- Describe it fairly (no strawmen)
- List real pros and cons
- Explain why it wasn't chosen

#### Consequences
Be honest about trade-offs. Every decision has downsides.

Think about:
- Performance implications
- Maintainability
- Complexity
- Developer experience
- Migration effort
- Operational impact

#### Implementation Notes
Practical guidance that answers:
- What files/modules need to change?
- What new components are needed?
- How do we migrate existing code?
- What breaking changes occur?

Don't replicate implementation details that belong in code docs.

#### References
Link to:
- Related ADRs (creates decision history)
- Technical docs (provides deeper detail)
- External resources (shows research)
- Discussions (captures context)

### Review Checklist

Before marking as "proposed", ensure:
- [ ] Frontmatter is complete
- [ ] Context clearly explains the problem
- [ ] Decision is stated unambiguously
- [ ] At least 2 alternatives are documented
- [ ] Consequences (positive and negative) are listed
- [ ] Implementation notes provide actionable guidance
- [ ] Length is ≤500 lines (ideally ≤300)
- [ ] All technical terms are explained or linked
- [ ] References are included where relevant

### Maintenance

ADRs are **immutable** once accepted. If a decision needs to change:

1. Create a new ADR
2. Set new ADR's `supersedes` field
3. Update old ADR's `status` to `superseded`
4. Update old ADR's `superseded_by` field
5. Link between the two in both directions

This preserves decision history and rationale.

---

## Example Usage

```bash
# Create new ADR
cp docs/adrs/000-adr-template.md docs/adrs/009-versioned-primitives.md

# Edit frontmatter and content
# Mark as draft initially

# When ready for review
# Update status to 'proposed'

# After approval
# Update status to 'accepted'
```

---

**Created**: 2025-11-13  
**Last Updated**: 2025-11-13  
**Version**: 1.0

