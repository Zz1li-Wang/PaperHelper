# Service contracts

This directory is the language-neutral boundary between deployable units.

- `openapi/`: versioned HTTP APIs and generated-client inputs.
- `events/`: JSON Schema for commands, events, and the shared envelope.
- `mcp/`: exported MCP tool schemas and compatibility snapshots.
- `errors/`: stable public error codes and wire-level error schemas.

Service implementations, ORM models, Python DTOs, and TypeScript interfaces do
not belong here. Generated artifacts must identify their source schema and are
checked by contract tests before a breaking version is released.
