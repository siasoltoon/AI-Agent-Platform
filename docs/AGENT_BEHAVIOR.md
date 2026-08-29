# Agent execution behavior

The default `agent.execute` command is now agentic: the model decides the next action, the worker executes that action in the configured workspace, observes the result, and continues until completion or a bounded failure.

The agent can currently:

- inspect files with `read_file`
- create/update files with `write_file`
- run project validation commands with `terminal`

The loop is bounded by `max_agent_steps` (default 12), validates JSON actions, rejects unknown tools, and prevents file paths from escaping the configured workspace.

A task is not considered completed merely because the model generated code. Completion requires the worker to execute the requested actions and return a completed execution record.
