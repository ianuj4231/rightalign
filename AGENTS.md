# Project Instructions

- Follow `docs/implementation_spec.md`.
- Do not add features outside the specification.
- Use semantic, self-explanatory names.
- Use Python + MySQL + raw SQL. No ORM.
- Use Pydantic for schemas and structured LLM output.
- Keep the orchestration as a raw deterministic state machine.
- Critical state transitions must not be delegated to the LLM.
- Prefer small reusable functions.
- Use parameterized SQL.
- Add explicit exception handling and transaction boundaries.
- Keep the project CLI-only.