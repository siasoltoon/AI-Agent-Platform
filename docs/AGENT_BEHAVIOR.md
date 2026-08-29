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
- `done` is rejected until at least one real tool action has executed and observable evidence supports completion.
- File paths are resolved inside the configured workspace and workspace escapes are rejected.
- Terminal execution is bounded to a maximum 600-second command timeout.
- Runtime task timeouts are bounded to 1–1800 seconds, including large-task execution.
- Terminal commands use an allowlist and reject shell chaining, redirection, and destructive shell operations.
- Agent execution is bounded by `max_agent_steps` (default 12).
- Task prompts are bounded to 200,000 characters by the canonical Task Contract.
- Caller-supplied task IDs are normalized and bounded to 128 characters.
- Task metadata is bounded to 64 keys to prevent unbounded request growth.
- Tool observations are returned to the model so it can inspect results, detect failures, and continue fixing the task.
- Completion records include the executed decision history, tool records, and verification evidence rather than only model-generated text.
- Failed execution is recorded as a failed task with an explicit error before the API reports the failure.
- Unknown task commands are rejected before execution through the command registry/router.

A task is not considered completed merely because the model generated code or claimed completion. Completion requires actual tool execution by the worker and a valid completed execution record with observable verification evidence.
