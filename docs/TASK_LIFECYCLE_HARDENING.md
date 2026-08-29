# Task Lifecycle Hardening

The controller treats task lifecycle as a durable state machine rather than a collection of mutable strings.

## States

- `queued -> running`
- `running -> completed`
- `running -> failed`
- `queued -> cancelled`
- `running -> cancelled`
- `running -> queued` only during controller restart recovery

Terminal states (`completed`, `failed`, `cancelled`) are immutable.

## Audit trail

Every task receives an append-only event history. Creation, claiming, lifecycle transitions, restart recovery and cancellation are recorded in SQLite.

## Cancellation

`POST /tasks/{task_id}/cancel` atomically cancels queued or running tasks. Cancellation is authoritative: if a long-running worker call finishes after cancellation, the runner will not overwrite the cancelled state with `completed`.

`GET /tasks/{task_id}/events` exposes the durable execution timeline.

## Task listing

`GET /tasks/?limit=100&status=running` supports bounded history retrieval and status filtering.

## Production principle

The lifecycle store is the source of truth. Model output, HTTP responses and worker claims cannot independently mutate a terminal task state. Every persisted transition is validated centrally.
