# AI-Agent-Platform Project Rules

## Core Principles

- Inspect project state before every task.
- Avoid duplicate implementations.
- Preserve working functionality.
- Prefer modular architecture.
- Validate every change.
- Track every task with ID, status, history and result.

## Agent Behavior

The Agent must:
- Analyze before modifying.
- Explain planned changes.
- Use tools safely.
- Report failures.
- Retry recoverable failures.
- Stop on unsafe changes.

## Security

Never expose API keys, passwords, tokens or private configuration.
