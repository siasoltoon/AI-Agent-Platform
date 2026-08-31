# Agent Hardening Notes

## Idempotent workspace mutations

The terminal `mkdir` alias is implemented as an idempotent workspace mutation. If an autonomous task has already created a requested directory through the dedicated `make_directory` tool and the model redundantly emits `mkdir`, the second operation succeeds as a no-op rather than failing because the directory already exists.

This preserves the bounded terminal interface while preventing an otherwise harmless duplicate directory operation from derailing a valid task.
