# Agent Tool Surface

The production agent uses a bounded, workspace-aware tool surface. File mutations prefer dedicated tools so the runtime can independently verify observable results.

## Workspace tools

- `read_file` — read UTF-8 text and return the observed content.
- `write_file` — create/replace UTF-8 text and return path, byte count and written content.
- `file_exists` — verify a file exists.
- `directory_exists` — verify a directory exists.
- `list_directory` — inspect directory entries and file sizes.
- `make_directory` — create a directory tree.
- `search_files` — recursively find files by glob pattern.
- `copy_file` — copy a file while preserving metadata.
- `move_file` — move a file within the workspace.
- `delete_file` — delete a file and report the resulting absence.
- `file_hash` — calculate MD5/SHA-1/SHA-256/SHA-512 for deterministic verification.

## Execution tool

`terminal` provides controlled access to the local development toolchain. Supported commands include Python, pytest, pip, Git, Uvicorn, Ruff, Black, mypy, Node, npm/npx, Vite, Yarn, pnpm, .NET, Java, Go, Cargo/Rust and safe inspection commands such as `dir`, `type`, `fc`, `findstr`, `tree`, `where` and `pwd`.

Shell chaining, redirection and high-risk system/destructive commands remain blocked. Workspace file changes should use dedicated tools whenever possible.

## Completion contract

The model's `done` response is not trusted by itself. The executor records every tool action and constructs `execution_evidence` from observable state. A task may only be returned as completed when evidence supports the requested result. Explicit verification requests require a read/inspection action in addition to the independent filesystem checks. Failed tool actions are retained in `tool_records` and prevent false-positive completion.
