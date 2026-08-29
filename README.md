# AI-Agent-Platform

A modular local AI agent platform for managing tasks, tools, workspaces and automation.

## Core Modules
- Agent Core
- Task Engine
- Tool System
- Workspace Manager
- Git Manager
- Test Engine
- Dashboard
- Backend

## Production execution guarantees

The controller uses the canonical Task Contract and routes `agent.execute` tasks to the real agentic execution path. Tasks are persisted in SQLite so lifecycle state survives backend restarts, and the backend exposes liveness/readiness probes for deployment health checks.

The agent is considered complete only after real tool execution and observable verification evidence. It does not treat model-generated suggested code as task completion.
