# A2A Skills Generator

## Task

Extract **A2A-compatible skills** from an agent's workflow prompt. Skills describe what the agent can do, enabling other agents to discover and invoke it via the A2A protocol.

## What is an A2A Skill?

An A2A skill is a capability that an agent advertises to other agents. Each skill has:
- **id**: A kebab-case identifier (e.g., "data-analysis", "code-review")
- **name**: A human-readable name (e.g., "Data Analysis", "Code Review")
- **description**: A clear description of what the skill does
- **tags**: Keywords for discovery (e.g., ["analytics", "visualization", "python"])
- **examples**: Sample prompts that would trigger this skill

## Output Format

Return a **valid JSON array** of skill objects. No markdown, no code blocks, just raw JSON.

```
[
  {
    "id": "skill-id-here",
    "name": "Skill Name",
    "description": "What this skill does in 1-2 sentences",
    "tags": ["tag1", "tag2", "tag3"],
    "examples": ["Example prompt 1", "Example prompt 2"]
  }
]
```

## Guidelines

1. **Extract 1-5 skills** - Focus on the most important capabilities
2. **Be specific** - Each skill should represent a distinct capability
3. **Use clear language** - Descriptions should be understandable by other agents
4. **Include good examples** - 2-3 example prompts that would invoke each skill
5. **Relevant tags** - Use 2-5 tags that help with discovery
6. **Lowercase kebab-case IDs** - e.g., "file-analysis" not "FileAnalysis"

## Good Example

For a workflow prompt about a code review agent:

```json
[
  {
    "id": "code-review",
    "name": "Code Review",
    "description": "Reviews code for bugs, security issues, and best practices",
    "tags": ["code", "review", "security", "quality"],
    "examples": ["Review this Python file for security issues", "Check my code for bugs"]
  },
  {
    "id": "refactoring-suggestions",
    "name": "Refactoring Suggestions",
    "description": "Suggests improvements to code structure and readability",
    "tags": ["refactoring", "code-quality", "optimization"],
    "examples": ["How can I improve this function?", "Suggest refactoring for this class"]
  }
]
```

## Bad Examples

- Extracting too many overlapping skills (should consolidate)
- Vague descriptions like "Helps with things" (be specific)
- Missing examples (always include 2-3)
- Using spaces in IDs (use kebab-case)

## Empty Workflow Prompt

If the workflow prompt is empty, minimal, or too vague to extract skills, return an empty array:
```
[]
```

## Context

You'll receive the agent's workflow prompt below. Analyze it and extract the key skills.
