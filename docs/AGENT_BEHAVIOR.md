# Agent execution behavior

The default `agent.execute` command is agentic: the model decides the next action, the worker executes that action in the configured workspace, observes the result, and continues until completion or a bounded failure.

The agent can currently:

- inspect files with `read_file`
- create/update files with `write_file`
- run approved project commands with `terminal`

## Execution guarantees

- The model must return a structured JSON action for every turn.
- Supported actions are `read_file`, `write_file`, `terminal`, and `done`.
- Tool shorthands such as `{ "action": "write_file", "args": {...} }` are normalized to the canonical tool contract.
- `done` is rejected until at least one real tool action has executed.
- File paths are resolved inside the configured workspace and workspace escapes are rejected.
- Terminal execution is bounded to a maximum 600-second timeout.
- Terminal commands use an allowlist and reject shell chaining, redirection, and destructive shell operations.
- Agent execution is bounded by `max_agent_steps` (default 12).
- Tool observations are returned to the model so it can inspect results, detect failures, and continue fixing the task.
- Completion records include the executed decision history rather than only model-generated text.

A task is not considered completed merely because the model generated code or claimed completion. Completion requires actual tool execution by the worker and a valid completed execution record.
