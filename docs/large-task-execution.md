# Large Task Execution

The `feature/task-contract-v1` runtime now supports automatic large-task orchestration.

## Execution modes

- Prompts shorter than `LARGE_TASK_THRESHOLD` use the existing single worker call.
- Prompts at or above the threshold use:
  1. mission-context preparation
  2. bounded planning
  3. sequential step execution
  4. final synthesis

The API does not reject large prompts merely because they are large. The runtime
only changes execution strategy. The actual Ollama model context remains the
ultimate technical limit.

## Configuration

```text
WORKER_TIMEOUT=300
LARGE_TASK_TIMEOUT=1800
LARGE_TASK_THRESHOLD=12000
MAX_PLAN_STEPS=12
STEP_CONTEXT_CHARS=12000
MISSION_CONTEXT_CHARS=28000
MISSION_CHUNK_CHARS=16000
```

For missions beyond the configured mission context, the runtime creates bounded
mission-part summaries before planning. This prevents the controller from
blindly repeating an arbitrarily large prompt in every execution call.

## Runtime flow

```text
Dashboard
  -> /tasks/create
  -> AgentRuntime
  -> LargeTaskOrchestrator
  -> planner call
  -> step 1 ... step N
  -> final synthesis call
  -> PC Worker
  -> Ollama
```

## Important scope

This layer is an orchestration foundation. It can reason over a large mission
and split it into model calls, but it does not yet provide filesystem, shell,
Git, browser, database, or other external tools to the model. Those capabilities
must be added as explicit, permissioned agent tools rather than pretending a
text-generation response performed an external action.
