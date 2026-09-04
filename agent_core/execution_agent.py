"""Production agentic execution loop with bounded tools and evidence-based completion."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_core.action_parser import ActionParseError, ActionParser
from agent_core.mission_policy import MissionPolicy
from backend.services.ollama_service import OllamaService
from tool_system.file_tools import (
    CopyFileTool, DeleteFileTool, DirectoryExistsTool, FileExistsTool, FileHashTool,
    ListDirectoryTool, MakeDirectoryTool, MoveFileTool, ReadFileTool, SearchFilesTool, WriteFileTool,
)
from tool_system.terminal_tools import TerminalTool


class AgentExecutionError(RuntimeError):
    def __init__(self, message: str, *, partial_result: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.partial_result = partial_result


class AgentExecutor:
    _WORKSPACE_TOOLS = {"read_file", "write_file", "file_exists", "directory_exists", "list_directory", "make_directory", "search_files", "copy_file", "move_file", "delete_file", "file_hash"}
    _TERMINAL_ALIASES = {"type", "cat", "dir", "ls", "pwd", "where", "findstr", "fc", "tree", "more", "echo", "mkdir", "mktemp", "whoami", "hostname", "ver", "date", "time", "python", "py", "pytest", "pip", "pip3", "git", "uvicorn", "ruff", "black", "mypy", "node", "npm", "npx", "vite", "yarn", "pnpm", "dotnet", "java", "javac", "go", "cargo", "rustc", "pytest.exe", "python.exe", "node.exe", "npm.exe", "git.exe"}
    _TOOLS = _WORKSPACE_TOOLS | {"terminal"}
    _MUTATING_TOOLS = {"write_file", "make_directory", "copy_file", "move_file", "delete_file"}

    def __init__(self, ollama: OllamaService, workspace_root: str | None = None, max_steps: int = 32, max_output_chars: int = 12000) -> None:
        self.ollama = ollama
        self.workspace = Path(workspace_root or Path.cwd()).resolve()
        self.max_steps = max(1, min(int(max_steps), 64))
        self.max_output_chars = max(256, int(max_output_chars))
        self.read_file = ReadFileTool(); self.write_file = WriteFileTool(); self.file_exists = FileExistsTool(); self.directory_exists = DirectoryExistsTool(); self.list_directory = ListDirectoryTool(); self.make_directory = MakeDirectoryTool(); self.search_files = SearchFilesTool(); self.copy_file = CopyFileTool(); self.move_file = MoveFileTool(); self.delete_file = DeleteFileTool(); self.file_hash = FileHashTool(); self.terminal = TerminalTool(workspace_root=self.workspace)

    def _safe_path(self, path: str) -> Path:
        value = str(path).strip()
        if not value: raise AgentExecutionError("Path cannot be empty.")
        candidate = Path(value)
        if not candidate.is_absolute(): candidate = self.workspace / candidate
        candidate = candidate.resolve()
        if candidate != self.workspace and self.workspace not in candidate.parents: raise AgentExecutionError("Path escapes the configured workspace.")
        return candidate

    @classmethod
    def _normalize_decision(cls, decision: dict[str, Any]) -> dict[str, Any]: return ActionParser.normalize(decision, cls._TOOLS, cls._TERMINAL_ALIASES)

    @staticmethod
    def _arg(args: dict[str, Any], *names: str, default: Any = "") -> Any:
        for name in names:
            value = args.get(name)
            if value is not None and str(value).strip(): return value
        return default

    def _relative(self, path: Path) -> str: return "." if path == self.workspace else path.relative_to(self.workspace).as_posix()

    def _alias_command(self, name: str, args: dict[str, Any]) -> str:
        path = str(self._arg(args, "path", "file_path", "filepath", default="")).strip(); quoted = f'"{self._safe_path(path)}"' if path else ""
        if name in {"type", "cat", "dir", "ls", "pwd", "where", "tree", "more"}: return f"{name} {quoted}".strip()
        if name == "findstr":
            pattern = str(self._arg(args, "pattern", "query", "text", default=""))
            if not pattern or not path: raise AgentExecutionError("findstr requires pattern/query and path.")
            return f'findstr /N "{pattern}" {quoted}'
        if name == "fc":
            other = str(self._arg(args, "other", "compare", "path2", default=""))
            if not other or not path: raise AgentExecutionError("fc requires path and compare/path2.")
            return f'fc {quoted} "{self._safe_path(other)}"'
        if name == "echo": return f"echo {self._arg(args, 'text', 'message', 'content', default='')}".strip()
        command = str(self._arg(args, "command", "cmd", default=name)).strip()
        return command if command and command.split()[0].lower() == name.lower() else f"{name} {command}".strip()

    def _tool(self, name: str, args: dict[str, Any]) -> Any:
        if name == "read_file":
            path = self._safe_path(self._arg(args, "path", "file_path", "filepath")); return {"ok": True, "path": self._relative(path), "content": self.read_file.execute(str(path))}
        if name == "write_file":
            path = self._safe_path(self._arg(args, "path", "file_path", "filepath")); content = str(self._arg(args, "content", "text", "body")); return {**self.write_file.execute(str(path), content), "path": self._relative(path), "content": content}
        if name == "file_exists":
            path = self._safe_path(self._arg(args, "path", "file_path", "filepath")); return {**self.file_exists.execute(str(path)), "path": self._relative(path), "ok": True}
        if name == "directory_exists":
            path = self._safe_path(self._arg(args, "path", "directory", default=".")); return {**self.directory_exists.execute(str(path)), "path": self._relative(path), "ok": True}
        if name == "list_directory":
            path = self._safe_path(self._arg(args, "path", "directory", default=".")); return {"ok": True, **self.list_directory.execute(str(path)), "path": self._relative(path)}
        if name == "make_directory":
            path = self._safe_path(self._arg(args, "path", "directory")); result = self.make_directory.execute(str(path)); result["path"] = self._relative(path); return result
        if name == "search_files":
            path = self._safe_path(self._arg(args, "path", "directory", default=".")); result = self.search_files.execute(str(path), str(self._arg(args, "pattern", default="*"))); result["path"] = self._relative(path); result["matches"] = [self._relative(Path(p).resolve()) for p in result.get("matches", [])]; return {"ok": True, **result}
        if name in {"copy_file", "move_file"}:
            source = self._safe_path(self._arg(args, "source", "src", "path")); destination = self._safe_path(self._arg(args, "destination", "dest", "target", "path2")); result = (self.copy_file if name == "copy_file" else self.move_file).execute(str(source), str(destination)); result["source"] = self._relative(source); result["destination"] = self._relative(destination); return result
        if name == "delete_file":
            path = self._safe_path(self._arg(args, "path", "file_path", "filepath")); result = self.delete_file.execute(str(path)); result["path"] = self._relative(path); return result
        if name == "file_hash":
            path = self._safe_path(self._arg(args, "path", "file_path", "filepath")); result = self.file_hash.execute(str(path), str(args.get("algorithm", "sha256"))); result["path"] = self._relative(path); return result
        command = str(self._arg(args, "command", "cmd", default="")).strip() if name == "terminal" else self._alias_command(name, args)
        if not command: raise AgentExecutionError("Terminal command cannot be empty.")
        timeout = int(args.get("timeout", 120))
        if timeout < 1 or timeout > 600: raise AgentExecutionError("Terminal timeout must be between 1 and 600 seconds.")
        return {**self.terminal.execute(command, timeout=timeout), "command": command}

    @staticmethod
    def _verification_requested(task: str) -> bool:
        lower = task.lower(); return any(word in lower for word in ("verify", "check", "confirm", "ensure", "exactly", "read"))

    def _verify_evidence(self, task: str, records: list[dict[str, Any]], policy: MissionPolicy | None = None) -> dict[str, Any]:
        policy = policy or MissionPolicy.from_task(task)
        successful = [r for r in records if r.get("ok") is True]; failed = [r for r in records if r.get("ok") is not True]; checks: list[dict[str, Any]] = []
        writes = [r for r in successful if r.get("tool") == "write_file"]; reads = [r for r in successful if r.get("tool") == "read_file"]
        write_contents = {r.get("result", {}).get("path"): r.get("result", {}).get("content") for r in writes if r.get("result", {}).get("path")}
        for record in writes:
            result = record.get("result", {}); rel = result.get("path"); expected = result.get("content")
            if not rel: continue
            path = self._safe_path(rel); checks.append({"type": "file_exists", "path": rel, "passed": path.is_file()})
            if path.is_file() and isinstance(expected, str):
                try: checks.append({"type": "file_content_matches_write", "path": rel, "expected_content": expected, "passed": path.read_text(encoding="utf-8") == expected})
                except OSError as exc: checks.append({"type": "file_content_readable", "path": rel, "passed": False, "error": str(exc)})
        for record in reads:
            result = record.get("result", {}); rel = result.get("path")
            if not rel: continue
            path = self._safe_path(rel); checks.append({"type": "read_verified_exists", "path": rel, "passed": path.is_file()})
            if rel in write_contents: checks.append({"type": "read_content_matches_write", "path": rel, "expected_content": write_contents[rel], "actual_content": result.get("content"), "passed": result.get("content") == write_contents[rel]})
        for record in successful:
            tool = record.get("tool"); result = record.get("result", {})
            if tool == "make_directory" and result.get("path"): checks.append({"type": "directory_exists", "path": result["path"], "passed": self._safe_path(result["path"]).is_dir()})
            elif tool == "copy_file" and result.get("destination"): checks.append({"type": "copied_file_exists", "path": result["destination"], "passed": self._safe_path(result["destination"]).is_file()})
            elif tool == "move_file" and result.get("source") and result.get("destination"): checks.extend([{"type": "move_destination_exists", "path": result["destination"], "passed": self._safe_path(result["destination"]).exists()}, {"type": "move_source_absent", "path": result["source"], "passed": not self._safe_path(result["source"]).exists()}])
            elif tool == "delete_file" and result.get("path"): checks.append({"type": "file_absent_after_delete", "path": result["path"], "passed": not self._safe_path(result["path"]).exists()})
            if tool in {"terminal", *self._TERMINAL_ALIASES}: checks.append({"type": "terminal_success", "command": result.get("command"), "passed": result.get("code") == 0 and not result.get("timed_out", False)})
        verification_requested = self._verification_requested(task); required = [c for c in checks if c["type"] != "terminal_success"]; failed_checks = [c for c in required if not c.get("passed")]; mutating = any(r.get("tool") in self._MUTATING_TOOLS for r in successful)
        policy_evidence = policy.evidence(records)
        verified = bool(successful) and not failed_checks and policy_evidence["compliant"]
        if writes and verification_requested and not reads: verified = False
        if mutating and not required: verified = False
        return {"verified": verified, "checks": checks, "successful_tool_actions": len(successful), "failed_tool_actions": len(failed), "policy": policy_evidence}

    @staticmethod
    def _result_from_records(actions, records, evidence, summary="Task completed."): return {"status": "completed", "execution_mode": "agentic", "summary": summary, "steps": actions, "execution_evidence": evidence, "tool_records": records}
    def _verified_result(self, task, actions, records, summary="Task completed.", policy=None):
        evidence = self._verify_evidence(task, records, policy)
        return self._result_from_records(actions, records, evidence, summary) if evidence["verified"] else None
    def _partial_result(self, task, actions, records, policy=None): return self._result_from_records(actions, records, self._verify_evidence(task, records, policy)) if records else None

    def execute(self, task: str) -> dict[str, Any]:
        if not task or not task.strip(): raise AgentExecutionError("Task cannot be empty.")
        policy = MissionPolicy.from_task(task); verification_requested = self._verification_requested(task)
        system = """You are the production autonomous coding agent.
Return exactly one JSON object per turn: {\"action\":\"tool\",\"tool\":\"TOOL_NAME\",\"args\":{...}} or {\"action\":\"done\",\"summary\":\"...\"}

Workspace tools: read_file, write_file, file_exists, directory_exists, list_directory, make_directory, search_files, copy_file, move_file, delete_file, file_hash. Execution tool: terminal.

Rules: stay inside workspace; inspect before risky changes; prefer dedicated tools; after every mutation ensure the resulting state is observable; never claim completion without evidence; recover from transient failures when possible; return done only when evidence supports success.

MISSION POLICY: If this mission is read-only, you MUST NOT mutate files, directories, or the workspace. Do not use write_file, make_directory, copy_file, move_file, delete_file, or terminal. Use only observation tools. A policy violation is a failed mission and can never be marked verified. These restrictions remain authoritative during recovery."""
        if verification_requested:
            system += """

MANDATORY EXACT-CONTENT VERIFICATION PROTOCOL applies ONLY when the task explicitly requires creating/writing a file and verifying its exact content. Then write_file must be followed immediately by read_file of the same path before done."""
        conversation = f"{system}\n\nTASK:\n{task.strip()}\n\nWORKSPACE:\n{self.workspace}"
        actions: list[dict[str, Any]] = []; records: list[dict[str, Any]] = []
        for step in range(1, self.max_steps + 1):
            try: response = self.ollama.generate(conversation, timeout=self.ollama.timeout)
            except StopIteration as exc:
                verified = self._verified_result(task, actions, records, policy=policy)
                if verified: return verified
                partial = self._partial_result(task, actions, records, policy)
                raise AgentExecutionError("Agent stopped before producing a verified completion.", partial_result=partial) from exc
            try: decision = self._normalize_decision(ActionParser.extract_object(response.get("response", "")))
            except ActionParseError as exc:
                actions.append({"step": step, "decision_error": str(exc)}); conversation += "\n\nACTION FORMAT ERROR: return ONLY one valid JSON object and continue."; continue
            actions.append({"step": step, "decision": decision})
            if decision.get("action") == "done":
                if not records: conversation += "\n\nPREMATURE COMPLETION REJECTED: execute an appropriate tool first."; continue
                evidence = self._verify_evidence(task, records, policy); actions[-1]["verification"] = evidence
                if evidence["verified"]: return self._result_from_records(actions, records, evidence, str(decision.get("summary", "Task completed.")))
                conversation += "\n\nVERIFICATION FAILED. Continue execution and do not claim success."
                continue
            if decision.get("action") != "tool": raise AgentExecutionError("Invalid agent action.", partial_result=self._partial_result(task, actions, records, policy))
            tool = str(decision.get("tool", "")).strip().lower(); args = decision.get("args", {})
            if tool not in self._TOOLS and tool not in self._TERMINAL_ALIASES: raise AgentExecutionError(f"Unknown tool: {tool}", partial_result=self._partial_result(task, actions, records, policy))
            if not isinstance(args, dict): raise AgentExecutionError("Tool args must be an object.", partial_result=self._partial_result(task, actions, records, policy))
            if not policy.allows_tool(tool, args):
                violation = {"step": step, "tool": tool, "ok": False, "policy_violation": True, "error_type": "MissionPolicyViolation", "error": policy.describe_violation(tool, args)}
                records.append(violation); conversation += f"\n\nPOLICY VIOLATION BLOCKED at step {step}: {violation['error']} Continue using permitted observation tools. Do not retry the blocked action."
                continue
            try: result = self._tool(tool, args); record = {"step": step, "tool": tool, "ok": True, "result": result}
            except Exception as exc: record = {"step": step, "tool": tool, "ok": False, "error_type": type(exc).__name__, "error": str(exc)}; result = {"ok": False, "error_type": type(exc).__name__, "error": str(exc)}
            records.append(record); serialized = json.dumps(result, ensure_ascii=False, default=str)
            if len(serialized) > self.max_output_chars: serialized = serialized[:self.max_output_chars] + "...<truncated>"
            conversation += f"\n\nOBSERVATION step {step}: tool={tool}\n{serialized}\n\nContinue, recover, or verify before done."
        verified = self._verified_result(task, actions, records, policy=policy)
        if verified: return verified
        raise AgentExecutionError(f"Agent exceeded maximum execution steps ({self.max_steps}).", partial_result=self._partial_result(task, actions, records, policy))
