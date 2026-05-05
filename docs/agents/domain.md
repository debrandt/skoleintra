# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root, if it exists
- **`docs/adr/`** at the repo root, if it exists

If either of these files does not exist, proceed silently. Don't flag the absence or suggest creating them upfront.

## File structure

This repo uses a single-context layout:

```text
/
|- CONTEXT.md
|- docs/adr/
`- src/
```

## Use the glossary's vocabulary

When naming domain concepts in issues, tests, refactors, or proposals, use the terms defined in `CONTEXT.md`.

## Flag ADR conflicts

If a proposed change conflicts with an ADR, surface that explicitly rather than silently overriding it.
