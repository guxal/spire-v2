# ADR-0015: CLI interaction, pickers and wizards

## Status

Accepted

## Decision

Every Spire CLI command supports explicit parameters. Interactive discovery is
an opt-in convenience only when an identifier is missing, the choices are a
finite discoverable set, and selection is safe.

Pickers are appropriate for account or read-only campaign selection. A
wizard is reserved for onboarding, multi-step configuration, OAuth, and other
intentionally guided workflows. Mutation ambiguity is never silently resolved;
an interactive campaign picker may run before a `ChangeSpec` exists, and the
selected target must be shown and bound to the resulting run.

`--no-input` and non-interactive stdin always fail with a stable error instead
of waiting. Explicit arguments override discovery. Human approval remains a
separate authority boundary and is never replaced by a picker or wizard.

MCP tools never depend on terminal input. Human-readable output is the default;
commands provide `--json` where practical for scripts and automation.

## Consequences

CLI adapters own parsing, prompting, serialization, and composition only.
Business logic remains in the existing application services. MCP uses the same
services without exposing physical storage, credentials, or approval methods.
