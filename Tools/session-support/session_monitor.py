#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import socket
import sys
import time
import secrets
import subprocess
import threading
import webbrowser
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen

TOOLS_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_ROOT))

from session_workflow_support import (  # noqa: E402
    DEFAULT_CATEGORY_CONFIG,
    DEFAULT_SESSIONS_ROOT,
    TurnSummary,
    SessionMetadata,
    classify_turn,
    detect_helper_scripts,
    extract_tool_commands as extract_source_commands,
    extract_user_text,
    find_latest_rollout_file,
    find_rollout_files,
    load_category_config,
    parse_iso_timestamp,
    read_session_metadata,
)

CONTRACT_VERSION = 4
PARSER_STATE_VERSION = 9
STATE_ROOT = Path(os.environ.get("SESSION_MONITOR_STATE_ROOT", Path.home() / ".codex" / "session-monitor"))
SERVER_STATE_PATH = STATE_ROOT / "server.json"
SERVER_LOG_PATH = STATE_ROOT / "server.log"
PHASE_LABELS = {
    "planning": "Planning",
    "review": "Review",
    "doc-review": "Review",
    "implementation": "Implementation",
    "debugging": "Debugging",
    "tooling": "Tooling",
    "doc-maintenance": "Documentation",
    "other": "Other",
}
INCIDENTAL_PHASES = {"Documentation", "Other"}
DEFAULT_THRESHOLDS = {
    "turns": 20,
    "categories": 3,
    "helper_coverage": 0.25,
    "helper_min_turns": 8,
    "phases": 3,
    "context_ratio": 0.75,
}
DEFAULT_PROJECT_CONFIG = TOOLS_ROOT / "project.example.json"


def load_project_config(path: Path) -> dict[str, Any]:
    try:
        config = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"Session monitor project config not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Session monitor project config is invalid JSON: {path}: {exc}") from exc
    if not isinstance(config, dict):
        raise SystemExit("Session monitor project config must be a JSON object.")
    return config


def configured_path(value: object, base: Path) -> Path:
    raw = os.path.expandvars(str(value or ""))
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def helper_detector(prefixes: list[str]):
    def detect(command: str) -> list[str]:
        try:
            tokens = shlex.split(command)
        except ValueError:
            tokens = command.split()
        hits: list[str] = []
        for token in tokens:
            clean = token.strip().strip("()[]{};,")
            lowered = clean.lower()
            if lowered.endswith((".sh", ".py")) and any(prefix.lower() in lowered for prefix in prefixes):
                hits.append(Path(clean).name)
        return list(dict.fromkeys(hits))
    return detect


def descriptive_tool_name(name: object, arguments: object) -> str:
    outer = str(name or "tool")
    raw = str(arguments or "")
    if outer != "exec":
        return outer
    nested = re.findall(r"\btools\.([A-Za-z0-9_]+)\s*\(", raw)
    if not nested:
        return "exec"
    counts = Counter(nested)
    summary = ", ".join(f"{tool} ×{count}" if count > 1 else tool for tool, count in counts.items())
    return f"exec → {summary}"


def extract_tool_commands(arguments_raw: str) -> list[str]:
    commands = extract_source_commands(arguments_raw)
    # Codex custom `exec` calls contain JavaScript rather than a JSON argument
    # object. Decode quoted `cmd` values without retaining unrelated arguments.
    for match in re.finditer(r"\bcmd\s*:\s*(\"(?:\\.|[^\"\\])*\")", arguments_raw):
        try:
            commands.append(str(json.loads(match.group(1))))
        except json.JSONDecodeError:
            continue
    return list(dict.fromkeys(commands))


def repository_name(path: object = None) -> str:
    candidate = Path(str(path or Path.cwd())).expanduser()
    if candidate.is_file():
        candidate = candidate.parent
    try:
        result = subprocess.run(
            ["git", "-C", str(candidate), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip()).name
    except (OSError, subprocess.SubprocessError):
        pass
    return candidate.resolve().name or "Project"


def content_paths(*values: object) -> list[str]:
    text = "\n".join(str(value or "") for value in values)
    matches = re.findall(r"(?:/[^\s`'\"<>]+|(?:\.\.?/|[A-Za-z0-9_.-]+/)[^\s`'\"<>]+)", text)
    return list(dict.fromkeys(match.rstrip(".,:;)") for match in matches))


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return parse_iso_timestamp(str(value))
    except SystemExit:
        return None


@dataclass
class ParserState:
    session_id: str = ""
    session_started_at: str | None = None
    offset: int = 0
    file_device: int | None = None
    file_inode: int | None = None
    partial_line: str = ""
    turn_in_progress: bool = False
    current_user_messages: list[str] = field(default_factory=list)
    current_tool_calls: int = 0
    current_helpers: list[str] = field(default_factory=list)
    current_commands: list[str] = field(default_factory=list)
    current_tool_details: list[dict[str, str]] = field(default_factory=list)
    current_total_token_usage: dict[str, int] = field(default_factory=dict)
    last_token_usage: dict[str, int] = field(default_factory=dict)
    previous_completed_token_usage: dict[str, int] = field(default_factory=dict)
    model_context_window: int | None = None
    current_turn_started_at: str | None = None
    current_first_response_at: str | None = None
    telemetry_availability: dict[str, bool] = field(default_factory=lambda: {
        "tokens": True,
        "cached_input_tokens": True,
        "reasoning_output_tokens": True,
        "context_window": True,
        "child_agents": True,
        "turn_timing": True,
    })
    turns: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ParserState":
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{key: value for key, value in payload.items() if key in allowed})


class IncrementalRolloutParser:
    def __init__(self, rollout: Path, category_config: dict[str, Any], state: ParserState | None = None, detect_helpers=None):
        self.rollout = rollout
        self.category_config = category_config
        self.state = state or ParserState()
        self.detect_helpers = detect_helpers or detect_helper_scripts

    def update(self) -> ParserState:
        stat = self.rollout.stat()
        identity_changed = (
            self.state.file_device is not None
            and (self.state.file_device != stat.st_dev or self.state.file_inode != stat.st_ino)
        )
        if identity_changed or stat.st_size < self.state.offset:
            self.state = ParserState()

        self.state.file_device = stat.st_dev
        self.state.file_inode = stat.st_ino
        with self.rollout.open("rb") as handle:
            handle.seek(self.state.offset)
            chunk = handle.read()
            self.state.offset = handle.tell()

        text = self.state.partial_line + chunk.decode("utf-8", errors="replace")
        lines = text.splitlines(keepends=True)
        self.state.partial_line = ""
        if lines and not lines[-1].endswith(("\n", "\r")):
            self.state.partial_line = lines.pop()
        for line in lines:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            self._consume(event)
        return self.state

    def _consume(self, event: dict[str, Any]) -> None:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        event_kind = event.get("type")
        event_timestamp = str(event.get("timestamp") or "") or None
        if event_kind == "session_meta":
            self.state.session_id = str(payload.get("id") or self.rollout.stem)
            self.state.session_started_at = str(payload.get("timestamp") or "") or None
            return
        if event_kind == "response_item":
            is_user_message = payload.get("type") == "message" and payload.get("role") == "user"
            if self.state.turn_in_progress and self.state.current_first_response_at is None and not is_user_message:
                self.state.current_first_response_at = event_timestamp
            if payload.get("type") == "message" and payload.get("role") == "user":
                user_text = extract_user_text(payload)
                if user_text:
                    self.state.current_user_messages.append(user_text)
            elif payload.get("type") in {"function_call", "custom_tool_call"}:
                self.state.current_tool_calls += 1
                raw_arguments = str(payload.get("arguments") or payload.get("input") or "")
                self.state.current_tool_details.append({
                    "name": descriptive_tool_name(payload.get("name") or payload.get("type"), raw_arguments),
                    "arguments": raw_arguments,
                })
                for command in extract_tool_commands(raw_arguments):
                    self.state.current_commands.append(command)
                    self.state.current_helpers.extend(self.detect_helpers(command))
            return
        if event_kind != "event_msg":
            return
        if payload.get("type") == "token_count":
            info = payload.get("info")
            if isinstance(info, dict):
                self.state.current_total_token_usage = normalize_token_usage(info.get("total_token_usage"))
                self.state.last_token_usage = normalize_token_usage(info.get("last_token_usage"))
                try:
                    self.state.model_context_window = int(info.get("model_context_window") or 0) or None
                except (TypeError, ValueError):
                    self.state.model_context_window = None
        elif payload.get("type") == "task_started":
            self.state.turn_in_progress = True
            self.state.current_user_messages = []
            self.state.current_tool_calls = 0
            self.state.current_helpers = []
            self.state.current_commands = []
            self.state.current_tool_details = []
            self.state.current_turn_started_at = event_timestamp
            self.state.current_first_response_at = None
        elif payload.get("type") == "task_complete":
            user_message = "\n".join(self.state.current_user_messages).strip()
            agent_message = str(payload.get("last_agent_message") or "")
            summary = TurnSummary(
                turn_index=len(self.state.turns) + 1,
                user_message=user_message,
                last_agent_message=agent_message,
                category=classify_turn(
                    user_message,
                    agent_message,
                    self.state.current_tool_calls,
                    self.category_config,
                ),
                tool_call_count=self.state.current_tool_calls,
                helper_invocations=tuple(self.state.current_helpers),
            )
            turn_payload = summary.as_json()
            turn_payload["helper_invocations"] = list(summary.helper_invocations)
            turn_payload["commands"] = list(dict.fromkeys(self.state.current_commands))
            turn_payload["tool_calls"] = list(self.state.current_tool_details)
            turn_payload["token_usage"] = subtract_token_usage(
                self.state.current_total_token_usage,
                self.state.previous_completed_token_usage,
            )
            turn_payload["context_used_tokens"] = int(self.state.last_token_usage.get("input_tokens") or 0)
            turn_payload["context_window_tokens"] = self.state.model_context_window
            started = parse_timestamp(self.state.current_turn_started_at)
            first = parse_timestamp(self.state.current_first_response_at)
            completed = parse_timestamp(event_timestamp)
            turn_payload["duration_ms"] = max(0, int((completed - started).total_seconds() * 1000)) if started and completed else None
            turn_payload["ttft_ms"] = max(0, int((first - started).total_seconds() * 1000)) if started and first else None
            self.state.turns.append(turn_payload)
            self.state.previous_completed_token_usage = dict(self.state.current_total_token_usage)
            self.state.turn_in_progress = False
            self.state.current_user_messages = []
            self.state.current_tool_calls = 0
            self.state.current_helpers = []
            self.state.current_commands = []
            self.state.current_tool_details = []
            self.state.current_turn_started_at = None
            self.state.current_first_response_at = None


class SessionSource:
    name = "unknown"

    def __init__(self, root: Path, detect_helpers):
        self.root = root
        self.detect_helpers = detect_helpers

    def files(self, since: datetime | None) -> list[Path]:
        raise NotImplementedError

    def metadata(self, path: Path) -> SessionMetadata:
        raise NotImplementedError

    def latest(self, since: datetime | None) -> Path:
        candidates = [path for path in self.files(since) if self.metadata(path).session_type != "subagent"]
        if not candidates:
            raise OSError(f"No {self.name} session files found under {self.root}")
        return candidates[-1]

    def parse(self, path: Path, category_config: dict[str, Any], state: ParserState | None) -> ParserState:
        raise NotImplementedError

    def children(self, parent_id: str, since: datetime | None) -> dict[str, Any]:
        return {"available": False, "active": None, "completed": None, "items": []}

    def repository(self, path: Path) -> str | None:
        return None


class CodexSessionSource(SessionSource):
    name = "codex"

    def files(self, since: datetime | None) -> list[Path]:
        return find_rollout_files(self.root, since)

    def metadata(self, path: Path) -> SessionMetadata:
        return read_session_metadata(path)

    def parse(self, path: Path, category_config: dict[str, Any], state: ParserState | None) -> ParserState:
        return IncrementalRolloutParser(path, category_config, state, self.detect_helpers).update()

    def repository(self, path: Path) -> str | None:
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    event = json.loads(line)
                    if event.get("type") == "session_meta" and isinstance(event.get("payload"), dict):
                        cwd = event["payload"].get("cwd")
                        return repository_name(cwd) if cwd else None
        except (OSError, json.JSONDecodeError):
            pass
        return None

    def children(self, parent_id: str, since: datetime | None) -> dict[str, Any]:
        result = child_activity(self.root, parent_id, since)
        result["available"] = True
        return result


def claude_text(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    return "\n".join(
        str(block.get("text") or "").strip()
        for block in content
        if isinstance(block, dict) and block.get("type") == "text" and block.get("text")
    ).strip()


class ClaudeSessionSource(SessionSource):
    name = "claude"

    def files(self, since: datetime | None) -> list[Path]:
        paths = sorted(self.root.expanduser().rglob("*.jsonl"), key=lambda path: (path.stat().st_mtime, str(path)))
        if since is not None:
            paths = [path for path in paths if datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) >= since]
        return paths

    def metadata(self, path: Path) -> SessionMetadata:
        first: dict[str, Any] = {}
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    event = json.loads(line)
                    if event.get("type") in {"user", "assistant"}:
                        first = event
                        break
        except (OSError, json.JSONDecodeError):
            pass
        is_child = "subagents" in path.parts or bool(first.get("agentId") or first.get("isSidechain"))
        parent_id = str(first.get("sessionId") or "") or (path.parent.parent.name if is_child else None)
        session_id = str(first.get("agentId") or (path.stem if is_child else first.get("sessionId")) or path.stem)
        timestamp = parse_timestamp(first.get("timestamp"))
        return SessionMetadata(
            session_id=session_id,
            timestamp=timestamp,
            session_type="subagent" if is_child else "primary",
            source="claude",
            parent_session_id=parent_id if is_child else None,
            agent_path=str(first.get("agentName") or first.get("agentId") or "") or None,
            agent_depth=1 if is_child else None,
        )

    def parse(self, path: Path, category_config: dict[str, Any], state: ParserState | None) -> ParserState:
        # Claude records do not expose Codex byte-offset semantics consistently; rebuild from the
        # source file so prompt/tool-result records can be normalized deterministically.
        parsed = ParserState(telemetry_availability={
            "tokens": True,
            "cached_input_tokens": True,
            "reasoning_output_tokens": False,
            "context_window": False,
            "child_agents": True,
            "turn_timing": False,
        })
        metadata = self.metadata(path)
        parsed.session_id = metadata.session_id
        parsed.session_started_at = metadata.timestamp.isoformat().replace("+00:00", "Z") if metadata.timestamp else None
        current_prompt = ""
        assistant_text = ""
        tool_calls = 0
        helpers: list[str] = []
        commands: list[str] = []
        tool_details: list[dict[str, str]] = []
        turn_usage = {field: 0 for field in TOKEN_FIELDS}

        def finish() -> None:
            nonlocal current_prompt, assistant_text, tool_calls, helpers, commands, tool_details, turn_usage
            if not current_prompt:
                return
            summary = TurnSummary(
                turn_index=len(parsed.turns) + 1,
                user_message=current_prompt,
                last_agent_message=assistant_text,
                category=classify_turn(current_prompt, assistant_text, tool_calls, category_config),
                tool_call_count=tool_calls,
                helper_invocations=tuple(dict.fromkeys(helpers)),
            )
            item = summary.as_json()
            item["helper_invocations"] = list(summary.helper_invocations)
            item["commands"] = list(dict.fromkeys(commands))
            item["tool_calls"] = list(tool_details)
            item["token_usage"] = dict(turn_usage)
            item["context_used_tokens"] = None
            item["context_window_tokens"] = None
            parsed.turns.append(item)
            current_prompt, assistant_text, tool_calls, helpers, commands, tool_details = "", "", 0, [], [], []
            turn_usage = {field: 0 for field in TOKEN_FIELDS}

        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                message = event.get("message") if isinstance(event.get("message"), dict) else {}
                content = message.get("content", [])
                if event.get("type") == "user":
                    text_value = claude_text(content)
                    if text_value and event.get("promptId"):
                        if current_prompt:
                            finish()
                        current_prompt = text_value
                        parsed.turn_in_progress = True
                    continue
                if event.get("type") != "assistant" or not current_prompt:
                    continue
                text_value = claude_text(content)
                if text_value:
                    assistant_text = text_value
                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict) or block.get("type") != "tool_use":
                            continue
                        tool_calls += 1
                        raw = json.dumps(block.get("input") or {})
                        tool_details.append({"name": str(block.get("name") or "tool"), "arguments": raw})
                        for command in extract_tool_commands(raw):
                            commands.append(command)
                            helpers.extend(self.detect_helpers(command))
                usage = message.get("usage") if isinstance(message.get("usage"), dict) else {}
                input_tokens = int(usage.get("input_tokens") or 0)
                cached = int(usage.get("cache_read_input_tokens") or 0)
                cache_creation = int(usage.get("cache_creation_input_tokens") or 0)
                output = int(usage.get("output_tokens") or 0)
                turn_usage["input_tokens"] += input_tokens + cached + cache_creation
                turn_usage["cached_input_tokens"] += cached
                turn_usage["output_tokens"] += output
                turn_usage["total_tokens"] += input_tokens + cached + cache_creation + output
                if message.get("stop_reason") in {"end_turn", "stop_sequence"}:
                    finish()
                    parsed.turn_in_progress = False
        parsed.current_total_token_usage = {
            field: sum(int(turn.get("token_usage", {}).get(field) or 0) for turn in parsed.turns)
            for field in TOKEN_FIELDS
        }
        parsed.offset = path.stat().st_size
        return parsed

    def repository(self, path: Path) -> str | None:
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    event = json.loads(line)
                    cwd = event.get("cwd")
                    if cwd:
                        return repository_name(cwd)
        except (OSError, json.JSONDecodeError):
            pass
        return None

    def children(self, parent_id: str, since: datetime | None) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for path in self.files(since):
            metadata = self.metadata(path)
            if metadata.session_type != "subagent" or metadata.parent_session_id != parent_id:
                continue
            state = self.parse(path, {"categories": [], "fallback_category": "other"}, None)
            items.append({
                "id": metadata.session_id,
                "path": metadata.agent_path,
                "depth": metadata.agent_depth,
                "status": "active" if state.turn_in_progress else "completed",
                "completed_turns": len(state.turns),
            })
        return {
            "available": True,
            "active": sum(item["status"] == "active" for item in items),
            "completed": sum(item["status"] == "completed" for item in items),
            "items": items,
        }


class GeminiSessionSource(SessionSource):
    name = "gemini"

    def files(self, since: datetime | None) -> list[Path]:
        paths = sorted(self.root.expanduser().rglob("session-*.json"), key=lambda path: (path.stat().st_mtime, str(path)))
        if since is not None:
            paths = [path for path in paths if datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) >= since]
        return paths

    def _document(self, path: Path) -> dict[str, Any]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}

    def metadata(self, path: Path) -> SessionMetadata:
        try:
            document = self._document(path)
        except (OSError, json.JSONDecodeError):
            document = {}
        return SessionMetadata(
            session_id=str(document.get("sessionId") or path.stem),
            timestamp=parse_timestamp(document.get("startTime")),
            session_type="primary",
            source="gemini",
        )

    def repository(self, path: Path) -> str | None:
        marker = path.parent.parent / ".project_root"
        try:
            return repository_name(marker.read_text(encoding="utf-8").strip())
        except OSError:
            return None

    def parse(self, path: Path, category_config: dict[str, Any], state: ParserState | None) -> ParserState:
        document = self._document(path)
        metadata = self.metadata(path)
        parsed = ParserState(telemetry_availability={
            "tokens": True,
            "cached_input_tokens": True,
            "reasoning_output_tokens": True,
            "context_window": False,
            "child_agents": False,
            "turn_timing": False,
        })
        parsed.session_id = metadata.session_id
        parsed.session_started_at = str(document.get("startTime") or "") or None
        prompt = ""
        responses: list[str] = []
        tool_calls = 0
        helpers: list[str] = []
        commands: list[str] = []
        tool_details: list[dict[str, str]] = []
        usage = {field: 0 for field in TOKEN_FIELDS}

        def finish() -> None:
            nonlocal prompt, responses, tool_calls, helpers, commands, tool_details, usage
            if not prompt:
                return
            answer = "\n".join(responses)
            summary = TurnSummary(
                turn_index=len(parsed.turns) + 1,
                user_message=prompt,
                last_agent_message=answer,
                category=classify_turn(prompt, answer, tool_calls, category_config),
                tool_call_count=tool_calls,
                helper_invocations=tuple(dict.fromkeys(helpers)),
            )
            item = summary.as_json()
            item["helper_invocations"] = list(summary.helper_invocations)
            item["commands"] = list(dict.fromkeys(commands))
            item["tool_calls"] = list(tool_details)
            item["token_usage"] = dict(usage)
            item["context_used_tokens"] = None
            item["context_window_tokens"] = None
            parsed.turns.append(item)
            prompt, responses, tool_calls, helpers, commands, tool_details = "", [], 0, [], [], []
            usage = {field: 0 for field in TOKEN_FIELDS}

        messages = document.get("messages") if isinstance(document.get("messages"), list) else []
        for message in messages:
            if not isinstance(message, dict):
                continue
            if message.get("type") == "user":
                if prompt:
                    finish()
                prompt = str(message.get("content") or "").strip()
                parsed.turn_in_progress = bool(prompt)
                continue
            if message.get("type") != "gemini" or not prompt:
                continue
            content = str(message.get("content") or "").strip()
            if content:
                responses.append(content)
            for tool in message.get("toolCalls") or []:
                if not isinstance(tool, dict):
                    continue
                tool_calls += 1
                tool_details.append({"name": str(tool.get("name") or "tool"), "arguments": json.dumps(tool.get("args") or {})})
                for command in extract_tool_commands(json.dumps(tool.get("args") or {})):
                    commands.append(command)
                    helpers.extend(self.detect_helpers(command))
            tokens = message.get("tokens") if isinstance(message.get("tokens"), dict) else {}
            usage["input_tokens"] += int(tokens.get("input") or 0)
            usage["cached_input_tokens"] += int(tokens.get("cached") or 0)
            usage["output_tokens"] += int(tokens.get("output") or 0)
            usage["reasoning_output_tokens"] += int(tokens.get("thoughts") or 0)
            usage["total_tokens"] += int(tokens.get("total") or 0)
        if prompt and (responses or tool_calls):
            finish()
            parsed.turn_in_progress = False
        parsed.current_total_token_usage = {
            field: sum(int(turn.get("token_usage", {}).get(field) or 0) for turn in parsed.turns)
            for field in TOKEN_FIELDS
        }
        parsed.offset = path.stat().st_size
        return parsed


class JunieSessionSource(SessionSource):
    name = "junie"

    def files(self, since: datetime | None) -> list[Path]:
        paths = sorted(self.root.expanduser().glob("session-*/events.jsonl"), key=lambda path: (path.stat().st_mtime, str(path)))
        index_path = self.root.expanduser() / "index.jsonl"
        matching_ids: set[str] = set()
        try:
            for line in index_path.read_text(encoding="utf-8").splitlines():
                record = json.loads(line)
                if str(record.get("projectDir") or "") == str(Path.cwd().resolve()):
                    matching_ids.add(str(record.get("sessionId") or ""))
        except (OSError, json.JSONDecodeError):
            pass
        if matching_ids:
            paths = [path for path in paths if path.parent.name in matching_ids]
        if since is not None:
            paths = [path for path in paths if datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) >= since]
        return paths

    def metadata(self, path: Path) -> SessionMetadata:
        return SessionMetadata(
            session_id=path.parent.name,
            timestamp=datetime.fromtimestamp(path.stat().st_ctime, timezone.utc),
            session_type="primary",
            source="junie",
        )

    def repository(self, path: Path) -> str | None:
        try:
            for line in (self.root / "index.jsonl").read_text(encoding="utf-8").splitlines():
                record = json.loads(line)
                if str(record.get("sessionId") or "") == path.parent.name:
                    project_dir = record.get("projectDir")
                    return repository_name(project_dir) if project_dir else None
        except (OSError, json.JSONDecodeError):
            pass
        return None

    def parse(self, path: Path, category_config: dict[str, Any], state: ParserState | None) -> ParserState:
        metadata = self.metadata(path)
        parsed = ParserState(telemetry_availability={
            "tokens": True,
            "cached_input_tokens": True,
            "reasoning_output_tokens": False,
            "context_window": False,
            "child_agents": False,
            "turn_timing": False,
        })
        parsed.session_id = metadata.session_id
        parsed.session_started_at = metadata.timestamp.isoformat().replace("+00:00", "Z") if metadata.timestamp else None
        prompt = ""
        answer = ""
        tool_ids: set[str] = set()
        helpers: list[str] = []
        commands: list[str] = []
        tool_details: list[dict[str, str]] = []
        usage = {field: 0 for field in TOKEN_FIELDS}

        def finish() -> None:
            nonlocal prompt, answer, tool_ids, helpers, commands, tool_details, usage
            if not prompt:
                return
            summary = TurnSummary(
                turn_index=len(parsed.turns) + 1,
                user_message=prompt,
                last_agent_message=answer,
                category=classify_turn(prompt, answer, len(tool_ids), category_config),
                tool_call_count=len(tool_ids),
                helper_invocations=tuple(dict.fromkeys(helpers)),
            )
            item = summary.as_json()
            item["helper_invocations"] = list(summary.helper_invocations)
            item["commands"] = list(dict.fromkeys(commands))
            item["tool_calls"] = list(tool_details)
            item["token_usage"] = dict(usage)
            item["context_used_tokens"] = None
            item["context_window_tokens"] = None
            parsed.turns.append(item)
            prompt, answer, tool_ids, helpers, commands, tool_details = "", "", set(), [], [], []
            usage = {field: 0 for field in TOKEN_FIELDS}

        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = event.get("kind")
                if kind == "UserPromptEvent":
                    if prompt:
                        finish()
                    prompt = str(event.get("presentablePrompt") or event.get("prompt") or "").strip()
                    parsed.turn_in_progress = bool(prompt)
                    continue
                if kind == "TaskState" and event.get("state") == "COMPLETED":
                    finish()
                    parsed.turn_in_progress = False
                    continue
                agent_event = event.get("event", {}).get("agentEvent") if isinstance(event.get("event"), dict) else None
                if not isinstance(agent_event, dict) or not prompt:
                    continue
                agent_kind = agent_event.get("kind")
                if agent_kind in {"ResultBlockUpdatedEvent", "MarkdownBlockUpdatedEvent"}:
                    value = str(agent_event.get("result") or agent_event.get("text") or "").strip()
                    if value:
                        answer = value
                if agent_kind in {"TerminalBlockUpdatedEvent", "ToolBlockUpdatedEvent", "ViewFilesBlockUpdatedEvent"}:
                    tool_id = str(agent_event.get("stepId") or f"{agent_kind}:{len(tool_ids)}")
                    if tool_id not in tool_ids:
                        tool_details.append({"name": agent_kind.removesuffix("BlockUpdatedEvent"), "arguments": json.dumps({key: agent_event[key] for key in ("command", "path", "paths") if key in agent_event})})
                    tool_ids.add(tool_id)
                    command = str(agent_event.get("command") or "")
                    if command:
                        commands.append(command)
                        helpers.extend(self.detect_helpers(command))
                if agent_kind == "LlmResponseMetadataEvent":
                    model_usage = agent_event.get("modelUsage") if isinstance(agent_event.get("modelUsage"), list) else []
                    for model in model_usage:
                        if not isinstance(model, dict):
                            continue
                        fresh = int(model.get("inputTokens") or 0)
                        cached = int(model.get("cacheInputTokens") or 0)
                        created = int(model.get("cacheCreateTokens") or 0)
                        output = int(model.get("outputTokens") or 0)
                        usage["input_tokens"] += fresh + cached + created
                        usage["cached_input_tokens"] += cached
                        usage["output_tokens"] += output
                        usage["total_tokens"] += fresh + cached + created + output
        parsed.current_total_token_usage = {
            field: sum(int(turn.get("token_usage", {}).get(field) or 0) for turn in parsed.turns)
            for field in TOKEN_FIELDS
        }
        parsed.offset = path.stat().st_size
        return parsed
TOKEN_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)


def normalize_token_usage(value: object) -> dict[str, int]:
    source = value if isinstance(value, dict) else {}
    return {field: max(0, int(source.get(field) or 0)) for field in TOKEN_FIELDS}


def subtract_token_usage(current: dict[str, int], previous: dict[str, int]) -> dict[str, int]:
    return {
        field: max(0, int(current.get(field) or 0) - int(previous.get(field) or 0))
        for field in TOKEN_FIELDS
    }


def token_payload(state: ParserState) -> dict[str, Any]:
    availability = dict(state.telemetry_availability)
    totals = normalize_token_usage(state.current_total_token_usage)
    latest = normalize_token_usage(state.last_token_usage)
    totals["uncached_input_tokens"] = max(0, totals["input_tokens"] - totals["cached_input_tokens"])
    latest["uncached_input_tokens"] = max(0, latest["input_tokens"] - latest["cached_input_tokens"])
    context_window = state.model_context_window
    context_used = latest["input_tokens"]
    trend: list[dict[str, Any]] = []
    for turn in state.turns:
        usage = normalize_token_usage(turn.get("token_usage"))
        usage["uncached_input_tokens"] = max(
            0,
            usage["input_tokens"] - usage["cached_input_tokens"],
        )
        window = turn.get("context_window_tokens")
        used = int(turn.get("context_used_tokens") or 0)
        trend.append({
            "turn": int(turn.get("turn_index") or len(trend) + 1),
            "category": str(turn.get("category") or "other"),
            **usage,
            "context_used_tokens": used,
            "context_window_tokens": int(window) if window else None,
            "context_used_ratio": round(used / int(window), 4) if window else None,
        })
    payload = {
        "availability": availability,
        "session": totals,
        "latest_model_call": latest,
        "context": {
            "used_tokens": context_used,
            "window_tokens": context_window,
            "used_ratio": round(context_used / context_window, 4) if context_window else None,
        },
        "trend": trend,
    }
    if not availability.get("tokens", True):
        payload["session"] = {key: None for key in totals}
        payload["latest_model_call"] = {key: None for key in latest}
        payload["trend"] = []
    else:
        if not availability.get("cached_input_tokens", True):
            for bucket in (payload["session"], payload["latest_model_call"]):
                bucket["cached_input_tokens"] = None
                bucket["uncached_input_tokens"] = None
            for point in payload["trend"]:
                point["cached_input_tokens"] = None
                point["uncached_input_tokens"] = None
        if not availability.get("reasoning_output_tokens", True):
            payload["session"]["reasoning_output_tokens"] = None
            payload["latest_model_call"]["reasoning_output_tokens"] = None
            for point in payload["trend"]:
                point["reasoning_output_tokens"] = None
    if not availability.get("context_window", True):
        payload["context"] = {"used_tokens": None, "window_tokens": None, "used_ratio": None}
        for point in payload["trend"]:
            point["context_used_tokens"] = None
            point["context_window_tokens"] = None
            point["context_used_ratio"] = None
    return payload


def analytics_payload(state: ParserState) -> dict[str, Any]:
    categories: dict[str, dict[str, Any]] = {}
    diagnostics: list[dict[str, Any]] = []
    for turn in state.turns:
        category = str(turn.get("category") or "other")
        usage = normalize_token_usage(turn.get("token_usage"))
        uncached = max(0, usage["input_tokens"] - usage["cached_input_tokens"])
        bucket = categories.setdefault(category, {
            "turns": 0,
            "total_tokens": 0,
            "uncached_input_tokens": 0,
            "output_tokens": 0,
            "cached_input_tokens": 0,
            "input_tokens": 0,
        })
        bucket["turns"] += 1
        bucket["total_tokens"] += usage["total_tokens"]
        bucket["uncached_input_tokens"] += uncached
        bucket["output_tokens"] += usage["output_tokens"]
        bucket["cached_input_tokens"] += usage["cached_input_tokens"]
        bucket["input_tokens"] += usage["input_tokens"]
        tool_count = int(turn.get("tool_call_count") or 0)
        tool_names = [str(item.get("name") or "tool") for item in turn.get("tool_calls", []) if isinstance(item, dict)]
        if len(tool_names) < tool_count:
            command_count = min(len(turn.get("commands") or []), tool_count - len(tool_names))
            tool_names.extend(["command"] * command_count)
            tool_names.extend(["unidentified tool"] * (tool_count - len(tool_names)))
        diagnostics.append({
            "turn": int(turn.get("turn_index") or len(diagnostics) + 1),
            "category": category,
            "total_tokens": usage["total_tokens"],
            "uncached_input_tokens": uncached,
            "cache_ratio": round(usage["cached_input_tokens"] / usage["input_tokens"], 4) if usage["input_tokens"] else None,
            "tool_calls": tool_count,
            "tool_names": tool_names,
            "duration_ms": turn.get("duration_ms"),
            "ttft_ms": turn.get("ttft_ms"),
        })
    for bucket in categories.values():
        bucket["cache_ratio"] = round(bucket["cached_input_tokens"] / bucket["input_tokens"], 4) if bucket["input_tokens"] else None
        del bucket["cached_input_tokens"]
        del bucket["input_tokens"]
    totals = normalize_token_usage(state.current_total_token_usage)
    return {
        "average_cache_ratio": round(totals["cached_input_tokens"] / totals["input_tokens"], 4) if totals["input_tokens"] else None,
        "unique_helpers": len({helper for turn in state.turns for helper in turn.get("helper_invocations", [])}),
        "category_costs": categories,
        "turn_diagnostics": diagnostics,
        "timing_available": bool(state.telemetry_availability.get("turn_timing")),
    }


def infer_phase_history(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    categories = [str(turn.get("category") or "other") for turn in turns]
    for index, category in enumerate(categories):
        phase = PHASE_LABELS.get(category, "Other")
        previous = history[-1]["name"] if history else None
        next_phase = PHASE_LABELS.get(categories[index + 1], "Other") if index + 1 < len(categories) else None
        if phase in INCIDENTAL_PHASES and previous and next_phase == previous:
            history[-1]["end_turn"] = index + 1
            history[-1]["evidence"].append(category)
            continue
        if previous == phase:
            history[-1]["end_turn"] = index + 1
            history[-1]["evidence"].append(category)
            continue
        history.append({
            "name": phase,
            "start_turn": index + 1,
            "end_turn": index + 1,
            "confidence": "likely",
            "evidence": [category],
        })
    return history


def apply_phase_edits(phases: list[dict[str, Any]], controls: dict[str, Any]) -> list[dict[str, Any]]:
    edited = [dict(phase, evidence=list(phase["evidence"])) for phase in phases]
    names = controls.get("phase_names")
    if isinstance(names, dict):
        for index_raw, name in names.items():
            try:
                index = int(index_raw)
            except (TypeError, ValueError):
                continue
            clean_name = str(name).strip()[:60]
            if clean_name and 0 <= index < len(edited):
                edited[index]["name"] = clean_name
                edited[index]["confidence"] = "confirmed"
    merges = controls.get("phase_merges")
    merge_indexes = sorted(
        {
            int(value)
            for value in (merges if isinstance(merges, list) else [])
            if str(value).isdigit() and int(value) > 0
        },
        reverse=True,
    )
    for index in merge_indexes:
        if index >= len(edited):
            continue
        previous = edited[index - 1]
        current = edited[index]
        previous["end_turn"] = current["end_turn"]
        previous["evidence"].extend(current["evidence"])
        previous["confidence"] = "confirmed"
        edited.pop(index)
    return edited


def normalized_thresholds(value: object) -> dict[str, float | int]:
    supplied = value if isinstance(value, dict) else {}
    result: dict[str, float | int] = dict(DEFAULT_THRESHOLDS)
    integer_fields = ("turns", "categories", "helper_min_turns", "phases")
    ratio_fields = ("helper_coverage", "context_ratio")
    for field in integer_fields:
        try:
            result[field] = max(1, min(1000, int(supplied.get(field, result[field]))))
        except (TypeError, ValueError):
            pass
    for field in ratio_fields:
        try:
            result[field] = max(0.0, min(1.0, float(supplied.get(field, result[field]))))
        except (TypeError, ValueError):
            pass
    return result


def warning_state(
    turns: list[dict[str, Any]],
    phases: list[dict[str, Any]],
    dismissed_key: str | None,
    thresholds: dict[str, float | int] | None = None,
    context_ratio: float | None = None,
    baseline_thresholds: dict[str, float | int] | None = None,
) -> dict[str, Any]:
    baseline = normalized_thresholds(baseline_thresholds)
    limits = normalized_thresholds(thresholds or baseline)
    count = len(turns)
    categories = Counter(str(turn.get("category") or "other") for turn in turns)
    helper_turns = sum(bool(turn.get("helper_invocations")) for turn in turns)
    coverage = helper_turns / count if count else 0.0
    triggered: list[str] = []
    turns_rule = f"{limits['turns']}+ completed turns"
    categories_rule = f"{limits['categories']}+ workflow categories"
    helper_rule = "low helper-turn coverage"
    if count >= limits["turns"]:
        triggered.append(turns_rule)
    if len(categories) >= limits["categories"]:
        triggered.append(categories_rule)
    if count >= limits["helper_min_turns"] and coverage <= limits["helper_coverage"]:
        triggered.append("low helper-turn coverage")
    if len(phases) >= limits["phases"]:
        triggered.append(f"{limits['phases']}+ work phases")
    if context_ratio is not None and context_ratio >= limits["context_ratio"]:
        triggered.append(f"context at or above {limits['context_ratio'] * 100:.0f}%")
    phase_names = [item["name"] for item in phases]
    if any(a == "Review" and b == "Implementation" for a, b in zip(phase_names, phase_names[1:])):
        triggered.append("review transitioned into implementation")

    severity = "healthy"
    if (
        len(categories) >= limits["categories"]
        or len(phases) >= limits["phases"]
        or count >= limits["turns"]
        or (context_ratio is not None and context_ratio >= limits["context_ratio"])
    ):
        severity = "advisory"
    if {turns_rule, categories_rule, helper_rule}.issubset(triggered):
        severity = "split"
    key = "|".join([severity, *triggered])
    acknowledged = bool(key and dismissed_key == key)
    if severity == "split":
        reason = "The session is long, spans several categories, and has sparse repo-helper coverage."
        action = "Finish the current deliverable, then continue the next category in a new session."
    elif severity == "advisory":
        reason = "The session has crossed a drift threshold."
        action = "Keep the next action within the current phase and owner seam."
    else:
        reason = "The session remains within the baseline split thresholds."
        action = "Continue on the current seam."
    return {
        "severity": severity,
        "triggered_rules": triggered,
        "reason": reason,
        "recommended_action": action,
        "key": key,
        "acknowledged": acknowledged,
        "thresholds": limits,
        "thresholds_overridden": limits != baseline,
    }


class SessionMonitor:
    def __init__(
        self,
        sessions_root: Path,
        since: datetime | None = None,
        rollout: Path | None = None,
        *,
        agent: str = "codex",
        project_config: dict[str, Any] | None = None,
    ):
        self.sessions_root = sessions_root
        self.since = since
        self.explicit_rollout = rollout
        self.project_config = project_config or {}
        base = Path(str(self.project_config.get("_base") or Path.cwd()))
        category_path = configured_path(self.project_config.get("category_config") or DEFAULT_CATEGORY_CONFIG, base)
        self.category_config = load_category_config(category_path)
        prefixes = [str(value) for value in self.project_config.get("helper_path_prefixes", ["tools/", "scripts/"])]
        detect_helpers = helper_detector(prefixes)
        source_types = {
            "codex": CodexSessionSource,
            "claude": ClaudeSessionSource,
            "gemini": GeminiSessionSource,
            "junie": JunieSessionSource,
        }
        self.source = source_types.get(agent, CodexSessionSource)(sessions_root, detect_helpers)
        self.agent = self.source.name
        self.labels = dict(self.project_config.get("labels") or {})
        configured_project = str(self.labels.get("project") or "").strip()
        self.project_name = repository_name() if not configured_project else configured_project
        self.continuation = dict(self.project_config.get("continuation") or {})
        self.default_thresholds = normalized_thresholds(self.project_config.get("thresholds"))
        state_setting = STATE_ROOT if os.environ.get("SESSION_MONITOR_STATE_ROOT") else self.project_config.get("state_root") or STATE_ROOT
        self.state_root = configured_path(
            state_setting,
            base,
        )
        self.selected_session_id: str | None = None
        self.lock = threading.RLock()
        self.history_cache: dict[str, tuple[int, float, dict[str, Any]]] = {}

    def _target(self) -> Path:
        if self.explicit_rollout:
            return self.explicit_rollout
        if self.selected_session_id:
            for path in reversed(self.source.files(self.since)):
                metadata = self.source.metadata(path)
                if metadata.session_id == self.selected_session_id and metadata.session_type != "subagent":
                    return path
            self.selected_session_id = None
        return self.source.latest(self.since)

    def _state_path(self, session_id: str) -> Path:
        safe_id = "".join(char for char in session_id if char.isalnum() or char in "-_") or "unknown"
        return self.state_root / f"{safe_id}.json"

    def _load_parser_state(self, rollout: Path) -> ParserState:
        metadata = self.source.metadata(rollout)
        path = self._state_path(metadata.session_id or rollout.stem)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if (
                payload.get("rollout_file") != str(rollout)
                or payload.get("parser_version") != PARSER_STATE_VERSION
            ):
                return ParserState()
            return ParserState.from_json(payload.get("parser", {}))
        except (OSError, json.JSONDecodeError, TypeError):
            return ParserState()

    def _load_controls(self, session_id: str) -> dict[str, Any]:
        try:
            payload = json.loads(self._state_path(session_id).read_text(encoding="utf-8"))
            return dict(payload.get("controls") or {})
        except (OSError, json.JSONDecodeError, TypeError):
            return {}

    def _save(self, rollout: Path, state: ParserState, controls: dict[str, Any]) -> None:
        self.state_root.mkdir(parents=True, exist_ok=True)
        target = self._state_path(state.session_id or rollout.stem)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps({
            "rollout_file": str(rollout),
            "parser_version": PARSER_STATE_VERSION,
            "parser": asdict(state),
            "controls": controls,
        }), encoding="utf-8")
        temporary.replace(target)

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            rollout = self._target()
            state = self.source.parse(rollout, self.category_config, self._load_parser_state(rollout))
            session_id = state.session_id or rollout.stem
            controls = self._load_controls(session_id)
            phases = apply_phase_edits(infer_phase_history(state.turns), controls)
            override = controls.get("phase_override")
            current_phase = override or (phases[-1]["name"] if phases else "Unknown")
            phase_source = "confirmed" if override else ("likely" if phases else "unknown")
            tokens = token_payload(state)
            analytics = analytics_payload(state)
            warning = warning_state(
                state.turns,
                phases,
                controls.get("dismissed_warning"),
                controls.get("thresholds"),
                tokens["context"]["used_ratio"],
                self.default_thresholds,
            )
            children = self.source.children(session_id, self.since)
            session_repository = self.source.repository(rollout) or self.project_name
            started = parse_timestamp(state.session_started_at)
            elapsed = max(0, int((datetime.now(timezone.utc) - started).total_seconds())) if started else None
            counts = Counter(str(turn.get("category") or "other") for turn in state.turns)
            helper_turns = sum(bool(turn.get("helper_invocations")) for turn in state.turns)
            helper_counts = Counter(
                helper
                for turn in state.turns
                for helper in turn.get("helper_invocations", [])
            )
            self._save(rollout, state, controls)
            return {
                "contract_version": CONTRACT_VERSION,
                "generated_at": iso_now(),
                "source": {
                    "agent": self.agent,
                    "project": session_repository,
                    "capabilities": dict(state.telemetry_availability),
                },
                "session": {
                    "id": session_id,
                    "started_at": state.session_started_at,
                    "elapsed_seconds": elapsed,
                    "completed_turns": len(state.turns),
                    "turn_in_progress": state.turn_in_progress,
                    "is_latest": self.selected_session_id is None,
                },
                "phase": {
                    "current": current_phase,
                    "source": phase_source,
                    "history": phases,
                },
                "categories": dict(counts),
                "helpers": {
                    "turns": helper_turns,
                    "coverage": round(helper_turns / len(state.turns), 4) if state.turns else 0.0,
                    "invocations": dict(helper_counts),
                },
                "tokens": tokens,
                "analytics": analytics,
                "subagents": children,
                "warning": warning,
            }

    def set_phase(self, phase: str | None) -> None:
        with self.lock:
            snapshot = self.snapshot()
            session_id = snapshot["session"]["id"]
            rollout = self._target()
            state = self._load_parser_state(rollout)
            controls = self._load_controls(session_id)
            controls["phase_override"] = phase
            self._save(rollout, state, controls)

    def dismiss_warning(self) -> None:
        with self.lock:
            snapshot = self.snapshot()
            session_id = snapshot["session"]["id"]
            rollout = self._target()
            state = self._load_parser_state(rollout)
            controls = self._load_controls(session_id)
            controls["dismissed_warning"] = snapshot["warning"]["key"]
            self._save(rollout, state, controls)

    def edit_phase(self, action: str, index: int, name: str = "") -> None:
        with self.lock:
            snapshot = self.snapshot()
            rollout = self._target()
            state = self._load_parser_state(rollout)
            controls = self._load_controls(snapshot["session"]["id"])
            if action == "rename":
                clean_name = name.strip()[:60]
                if not clean_name:
                    raise ValueError("Phase name is required.")
                names = controls.setdefault("phase_names", {})
                names[str(index)] = clean_name
            elif action == "merge":
                if index <= 0:
                    raise ValueError("The first phase cannot merge into a previous phase.")
                merges = controls.setdefault("phase_merges", [])
                if index not in merges:
                    merges.append(index)
            elif action == "reset":
                controls.pop("phase_names", None)
                controls.pop("phase_merges", None)
            else:
                raise ValueError(f"Unknown phase edit action: {action}")
            self._save(rollout, state, controls)

    def set_thresholds(self, supplied: object) -> None:
        with self.lock:
            snapshot = self.snapshot()
            rollout = self._target()
            state = self._load_parser_state(rollout)
            controls = self._load_controls(snapshot["session"]["id"])
            controls["thresholds"] = normalized_thresholds(supplied)
            self._save(rollout, state, controls)

    def reset_thresholds(self) -> None:
        with self.lock:
            snapshot = self.snapshot()
            rollout = self._target()
            state = self._load_parser_state(rollout)
            controls = self._load_controls(snapshot["session"]["id"])
            controls.pop("thresholds", None)
            self._save(rollout, state, controls)

    def select_session(self, session_id: str | None) -> None:
        with self.lock:
            self.selected_session_id = session_id or None
            self.snapshot()

    def recent_sessions(self, limit: int = 12) -> dict[str, Any]:
        with self.lock:
            items: list[dict[str, Any]] = []
            selected_id = self.snapshot()["session"]["id"]
            files = [
                path
                for path in self.source.files(self.since)
                if self.source.metadata(path).session_type != "subagent"
            ][-max(1, limit):]
            for path in reversed(files):
                stat = path.stat()
                key = str(path)
                cached = self.history_cache.get(key)
                if cached and cached[0] == stat.st_size and cached[1] == stat.st_mtime:
                    item = dict(cached[2])
                else:
                    state = self.source.parse(path, self.category_config, None)
                    phases = infer_phase_history(state.turns)
                    tokens = token_payload(state)
                    started = parse_timestamp(state.session_started_at)
                    elapsed = max(0, int(stat.st_mtime - started.timestamp())) if started else None
                    categories = Counter(str(turn.get("category") or "other") for turn in state.turns)
                    warning = warning_state(
                        state.turns,
                        phases,
                        None,
                        None,
                        tokens["context"]["used_ratio"],
                        self.default_thresholds,
                    )
                    children = self.source.children(state.session_id, self.since)
                    item = {
                        "id": state.session_id or path.stem,
                        "started_at": state.session_started_at,
                        "elapsed_seconds": elapsed,
                        "completed_turns": len(state.turns),
                        "categories": dict(categories),
                        "total_tokens": tokens["session"]["total_tokens"],
                        "warning": warning["severity"],
                        "subagents": (
                            children["active"] + children["completed"]
                            if children.get("available") else None
                        ),
                        "repository": self.source.repository(path) or self.project_name,
                    }
                    self.history_cache[key] = (stat.st_size, stat.st_mtime, dict(item))
                item["selected"] = item["id"] == selected_id
                items.append(item)
            return {"sessions": items}

    def continuation_prompt(self, payload: object) -> dict[str, str]:
        supplied = payload if isinstance(payload, dict) else {}
        snapshot = self.snapshot()

        def clean(field: str, limit: int = 2000) -> str:
            return str(supplied.get(field) or "").strip()[:limit]

        files = [
            line.strip()
            for line in clean("files", 4000).splitlines()
            if (
                line.strip()
                and not line.strip().startswith(("/", "~"))
                and ".." not in Path(line.strip()).parts
            )
        ][:20]
        project = self.project_name
        goal = clean("goal") or str(self.continuation.get("goal") or f"Continue the current {project} work.")
        completed = clean("completed") or f"Completed {snapshot['session']['completed_turns']} turns; current phase is {snapshot['phase']['current']}."
        remaining = clean("remaining") or snapshot["warning"]["recommended_action"]
        constraints = clean("constraints") or str(self.continuation.get("constraints") or "Preserve current behavior and verify the narrow owning seam.")
        lines = [
            str(self.continuation.get("mode") or "Mode: Builder"),
            str(self.continuation.get("system") or f"Project: {project}"),
            f"Goal: {goal}",
            "",
            "Completed:",
            completed,
            "",
            "Remaining:",
            remaining,
            "",
            "Constraints:",
            constraints,
        ]
        if files:
            lines.extend(["", "Relevant files:", *[f"- {path}" for path in files]])
        lines.extend([
            "",
            f"Session context: {snapshot['session']['completed_turns']} completed turns; phase {snapshot['phase']['current']}; warning {snapshot['warning']['severity']}.",
            "Stopping point: finish the remaining slice above, verify it, and hand back any distinct follow-up separately.",
        ])
        return {"prompt": "\n".join(lines)}

    def _report_paths(self, scope: str) -> list[Path]:
        if scope == "current":
            return [self._target()]
        paths = [path for path in self.source.files(self.since) if self.source.metadata(path).session_type != "subagent"]
        return paths[-30:] if scope == "last-30" else paths

    def content_snapshot(self) -> dict[str, Any]:
        path = self._target()
        state = self.source.parse(path, self.category_config, None)
        return {
            "warning": "Sensitive prompts, responses, tool-call arguments, commands, and paths are included by explicit request.",
            "session_id": state.session_id or path.stem,
            "repository": self.source.repository(path) or self.project_name,
            "turns": [{
                "turn": turn.get("turn_index"),
                "prompt": turn.get("user_message") or "",
                "response": turn.get("last_agent_message") or "",
                "commands": turn.get("commands") or [],
                "tool_calls": turn.get("tool_calls") or [{"name": "command", "arguments": command} for command in turn.get("commands", [])],
                "paths": content_paths(turn.get("user_message"), turn.get("last_agent_message"), *(turn.get("commands") or [])),
            } for turn in state.turns],
        }

    def generated_report(self, scope: str, include_content: bool = False) -> dict[str, str]:
        if scope not in {"current", "last-30", "all"}:
            raise ValueError("Report scope must be current, last-30, or all.")
        report_paths = self._report_paths(scope)
        if scope == "current":
            snapshot = self.snapshot()
            sessions = [{
                "repository": snapshot["source"]["project"],
                "started_at": snapshot["session"]["started_at"],
                "completed_turns": snapshot["session"]["completed_turns"],
                "total_tokens": snapshot["tokens"]["session"]["total_tokens"],
                "warning": snapshot["warning"]["severity"],
                "categories": snapshot["categories"],
            }]
        else:
            sessions = self.recent_sessions(30 if scope == "last-30" else 100000)["sessions"]
        categories = Counter()
        for item in sessions:
            categories.update(item["categories"])
        lines = [
            "# Session Support Report", "",
            f"- Agent: `{self.agent}`", f"- Scope: `{scope}`", f"- Sessions: {len(sessions)}", "",
            "## Categories", "", "| Category | Turns |", "| --- | ---: |",
            *[f"| {name} | {count} |" for name, count in categories.most_common()], "",
            "## Sessions", "", "| Repository | Started | Turns | Tokens | Warning |", "| --- | --- | ---: | ---: | --- |",
        ]
        for item in sessions:
            lines.append(f"| {item.get('repository') or self.project_name} | {item.get('started_at') or 'unknown'} | {item['completed_turns']} | {item['total_tokens'] if item['total_tokens'] is not None else 'unavailable'} | {item['warning']} |")
        if include_content:
            lines.extend(["", "> WARNING: This report includes prompts, responses, tool-call arguments, commands, and paths by explicit request."])
            for path in report_paths:
                state = self.source.parse(path, self.category_config, None)
                lines.extend(["", f"## Session Content: {state.session_id or path.stem}", ""])
                for turn in state.turns:
                    commands = turn.get("commands") or []
                    tool_calls = turn.get("tool_calls") or []
                    paths = content_paths(turn.get("user_message"), turn.get("last_agent_message"), *commands)
                    lines.extend([
                        f"### Turn {turn.get('turn_index')}", "",
                        "**Prompt**", "", str(turn.get("user_message") or "<none>"), "",
                        "**Response**", "", str(turn.get("last_agent_message") or "<none>"), "",
                        "**Commands**", "", *(f"- `{command}`" for command in commands),
                        "", "**Tool calls**", "", *(f"- `{item.get('name') or 'tool'}`: `{item.get('arguments') or '<none>'}`" for item in tool_calls if isinstance(item, dict)),
                        "", "**Paths**", "", *(f"- `{value}`" for value in paths), "",
                    ])
        now_stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        if scope == "current" and report_paths:
            state = self.source.parse(report_paths[0], self.category_config, None)
            started = re.sub(r"[^0-9]", "", str(state.session_started_at or ""))[:14] or now_stamp
            identity = re.sub(r"[^A-Za-z0-9_-]", "_", state.session_id or report_paths[0].stem)[:80]
            filename = f"session-report-{identity}-{started}.md"
        else:
            filename = f"session-report-{scope}-{now_stamp}.md"
        if include_content:
            filename = filename.removesuffix(".md") + "-sensitive.md"
        return {"scope": scope, "include_content": include_content, "filename": filename, "content": "\n".join(lines) + "\n"}


def child_activity(root: Path, parent_id: str, since: datetime | None) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for path in find_rollout_files(root, since):
        metadata = read_session_metadata(path)
        if metadata.session_type != "subagent" or metadata.parent_session_id != parent_id:
            continue
        active = False
        completed_turns = 0
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                event = json.loads(line)
                payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
                if event.get("type") == "event_msg" and payload.get("type") == "task_started":
                    active = True
                elif event.get("type") == "event_msg" and payload.get("type") == "task_complete":
                    active = False
                    completed_turns += 1
        except (OSError, json.JSONDecodeError):
            pass
        items.append({
            "id": metadata.session_id,
            "path": metadata.agent_path,
            "depth": metadata.agent_depth,
            "status": "active" if active else "completed",
            "completed_turns": completed_turns,
        })
    return {
        "active": sum(item["status"] == "active" for item in items),
        "completed": sum(item["status"] == "completed" for item in items),
        "items": items,
    }


def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "unknown"
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def render_status(snapshot: dict[str, Any]) -> str:
    session = snapshot["session"]
    helpers = snapshot["helpers"]
    phase = snapshot["phase"]
    warning = snapshot["warning"]
    timeline = " → ".join(item["name"] for item in phase["history"]) or "none"
    categories = ", ".join(f"{key}={value}" for key, value in snapshot["categories"].items()) or "none"
    status = {"healthy": "Healthy", "advisory": "⚠ Consider narrowing", "split": "⚠ Consider splitting"}[warning["severity"]]
    if warning["acknowledged"]:
        status += " (acknowledged)"
    progress = " + active turn" if session["turn_in_progress"] else ""
    tokens = snapshot["tokens"]
    token_totals = tokens["session"]
    context = tokens["context"]
    context_text = (
        f"{context['used_tokens']:,} / {context['window_tokens']:,} ({context['used_ratio'] * 100:.1f}%)"
        if context["window_tokens"]
        else "unknown"
    )
    return "\n".join([
        str(snapshot.get("source", {}).get("project") or "Project") + " Session",
        "────────────────────────────────────────",
        f"Turns:             {session['completed_turns']}{progress}",
        f"Elapsed:           {format_duration(session['elapsed_seconds'])}",
        f"Current phase:     {phase['current']} ({phase['source']})",
        f"Phase history:     {timeline}",
        f"Categories:        {len(snapshot['categories'])} ({categories})",
        f"Helper coverage:   {helpers['turns']} / {session['completed_turns']} turns",
        f"Session tokens:    {token_totals['total_tokens']:,} total · {token_totals['cached_input_tokens']:,} cached"
        if token_totals["total_tokens"] is not None and token_totals["cached_input_tokens"] is not None
        else "Session tokens:    unavailable",
        f"Latest context:    {context_text}",
        f"Sub-agents:        {snapshot['subagents']['active']} active, {snapshot['subagents']['completed']} completed"
        if snapshot["subagents"].get("available") else "Sub-agents:        unavailable",
        f"Status:            {status}",
        "",
        "Reason:",
        warning["reason"],
        "",
        "Next action:",
        warning["recommended_action"],
    ]) + "\n"


HTML_PATH = TOOLS_ROOT / "web" / "index.html"


def make_handler(monitor: SessionMonitor):
    instance_token = os.environ.get("SESSION_MONITOR_INSTANCE_TOKEN", "")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: object) -> None:
            return

        def _json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
            data = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802
            route = urlparse(self.path).path
            if route == "/api/health":
                self._json({
                    "service": "engineering-session-monitor",
                    "instance_token": instance_token,
                })
                return
            if route == "/api/state":
                try:
                    self._json(monitor.snapshot())
                except Exception as exc:  # dashboard must surface parser errors
                    self._json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            if route == "/api/history":
                try:
                    self._json(monitor.recent_sessions())
                except Exception as exc:
                    self._json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            if route == "/api/events":
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                try:
                    while True:
                        data = json.dumps(monitor.snapshot(), separators=(",", ":"))
                        self.wfile.write(f"event: state\ndata: {data}\n\n".encode("utf-8"))
                        self.wfile.flush()
                        time.sleep(1.0)
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                return
            if route in {"/", "/index.html"}:
                data = HTML_PATH.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            route = urlparse(self.path).path
            length = int(self.headers.get("Content-Length", "0"))
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
                if route == "/api/phase":
                    value = str(payload.get("phase") or "").strip()
                    monitor.set_phase(None if value.lower() == "auto" else value)
                elif route == "/api/dismiss-warning":
                    monitor.dismiss_warning()
                elif route == "/api/phase-history":
                    monitor.edit_phase(
                        str(payload.get("action") or ""),
                        int(payload.get("index") or 0),
                        str(payload.get("name") or ""),
                    )
                elif route == "/api/thresholds":
                    if payload.get("reset"):
                        monitor.reset_thresholds()
                    else:
                        monitor.set_thresholds(payload)
                elif route == "/api/session":
                    monitor.select_session(str(payload.get("id") or "") or None)
                elif route == "/api/continuation":
                    self._json(monitor.continuation_prompt(payload))
                    return
                elif route == "/api/report":
                    self._json(monitor.generated_report(
                        str(payload.get("scope") or "last-30"),
                        bool(payload.get("include_content")),
                    ))
                    return
                elif route == "/api/content":
                    self._json(monitor.content_snapshot())
                    return
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                self._json(monitor.snapshot())
            except (ValueError, TypeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    return Handler


def create_server(monitor: SessionMonitor, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(monitor))


def warning_exit(snapshot: dict[str, Any]) -> int:
    return 1 if snapshot["warning"]["severity"] in {"advisory", "split"} else 0


def load_server_state() -> dict[str, Any] | None:
    try:
        payload = json.loads(SERVER_STATE_PATH.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def read_health(port: int, timeout: float = 0.5) -> dict[str, Any] | None:
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/health", timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload if isinstance(payload, dict) else None
    except (OSError, ValueError):
        return None


def matching_server(state: dict[str, Any] | None) -> bool:
    if not state:
        return False
    try:
        health = read_health(int(state["port"]))
    except (KeyError, TypeError, ValueError):
        return False
    return bool(
        health
        and health.get("service") == "engineering-session-monitor"
        and health.get("instance_token") == state.get("instance_token")
    )


def choose_port(requested_port: int) -> int:
    if requested_port:
        return requested_port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def save_server_state(payload: dict[str, Any]) -> None:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    temporary = SERVER_STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(SERVER_STATE_PATH)


def start_background_server(args: argparse.Namespace, *, open_browser: bool = True) -> int:
    existing = load_server_state()
    if matching_server(existing):
        url = f"http://127.0.0.1:{existing['port']}/"
        print(f"Session monitor already running: {url}")
        if open_browser:
            webbrowser.open(url)
        return 0

    if existing:
        SERVER_STATE_PATH.unlink(missing_ok=True)
    port = choose_port(args.port)
    token = secrets.token_urlsafe(24)
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--agent",
        args.agent,
        "--project-config",
        str(args.project_config.expanduser().resolve()),
        "--sessions-root",
        str(args.sessions_root.expanduser()),
    ]
    if args.since:
        command.extend(["--since", args.since])
    if args.rollout:
        command.extend(["--rollout", str(args.rollout.expanduser().resolve())])
    command.extend(["serve", "--port", str(port)])
    environment = os.environ.copy()
    environment["SESSION_MONITOR_INSTANCE_TOKEN"] = token
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    log_handle = SERVER_LOG_PATH.open("a", encoding="utf-8")
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            env=environment,
            start_new_session=True,
        )
    finally:
        log_handle.close()
    state = {
        "pid": process.pid,
        "port": port,
        "instance_token": token,
        "started_at": iso_now(),
        "log_file": str(SERVER_LOG_PATH),
    }
    save_server_state(state)
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if process.poll() is not None:
            SERVER_STATE_PATH.unlink(missing_ok=True)
            print(f"Session monitor failed to start. See {SERVER_LOG_PATH}", file=sys.stderr)
            return 2
        if matching_server(state):
            url = f"http://127.0.0.1:{port}/"
            print(f"Session monitor started: {url}")
            if open_browser:
                webbrowser.open(url)
            return 0
        time.sleep(0.1)
    process.terminate()
    SERVER_STATE_PATH.unlink(missing_ok=True)
    print(f"Session monitor did not become ready. See {SERVER_LOG_PATH}", file=sys.stderr)
    return 2


def stop_background_server() -> int:
    state = load_server_state()
    if not state:
        print("Session monitor is not running.")
        return 0
    if not matching_server(state):
        SERVER_STATE_PATH.unlink(missing_ok=True)
        print("Removed stale session-monitor state; no matching server was running.")
        return 0
    try:
        pid = int(state["pid"])
        os.kill(pid, 15)
    except (KeyError, TypeError, ValueError, ProcessLookupError):
        SERVER_STATE_PATH.unlink(missing_ok=True)
        print("Session monitor was already stopped.")
        return 0
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if not matching_server(state):
            SERVER_STATE_PATH.unlink(missing_ok=True)
            print("Session monitor stopped.")
            return 0
        time.sleep(0.1)
    print(f"Session monitor did not stop within 5 seconds (PID {pid}).", file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Live local agent session monitor.")
    parser.add_argument("--agent", choices=("codex", "claude", "gemini", "junie"), help="Session source adapter.")
    parser.add_argument("--project-config", type=Path, default=DEFAULT_PROJECT_CONFIG)
    parser.add_argument("--sessions-root", type=Path)
    parser.add_argument("--since", help="ISO date/timestamp discovery cutoff.")
    parser.add_argument("--rollout", type=Path, help="Monitor one explicit rollout fixture/file.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status")
    subparsers.add_parser("json")
    watch = subparsers.add_parser("watch")
    watch.add_argument("--interval", type=float, default=1.0)
    phase = subparsers.add_parser("phase")
    phase.add_argument("name", help="Phase name, or 'auto'.")
    subparsers.add_parser("dismiss-warning")
    start = subparsers.add_parser("start")
    start.add_argument("--port", type=int, default=0)
    start.add_argument("--no-open", action="store_true", help=argparse.SUPPRESS)
    stop = subparsers.add_parser("stop")
    restart = subparsers.add_parser("restart")
    restart.add_argument("--port", type=int, default=0)
    restart.add_argument("--no-open", action="store_true", help=argparse.SUPPRESS)
    for name in ("serve", "open"):
        command = subparsers.add_parser(name)
        command.add_argument("--port", type=int, default=0)
    return parser


def main(argv: list[str] | None = None) -> int:
    global STATE_ROOT, SERVER_STATE_PATH, SERVER_LOG_PATH, DEFAULT_THRESHOLDS
    args = build_parser().parse_args(argv)
    project_config_path = args.project_config.expanduser().resolve()
    project_config = load_project_config(project_config_path)
    project_config["_base"] = str(project_config_path.parent)
    args.agent = args.agent or str(project_config.get("default_agent") or "codex")
    agent_config = dict((project_config.get("agents") or {}).get(args.agent) or {})
    if args.sessions_root is None:
        configured_root = agent_config.get("sessions_root")
        if configured_root:
            args.sessions_root = configured_path(configured_root, Path(project_config["_base"]))
        elif args.agent == "claude":
            encoded = str(Path.cwd().resolve()).replace("/", "-")
            args.sessions_root = Path.home() / ".claude" / "projects" / encoded
        elif args.agent == "gemini":
            candidates = []
            for directory in (Path.home() / ".gemini" / "tmp").glob("*"):
                marker = directory / ".project_root"
                try:
                    if marker.read_text(encoding="utf-8").strip() == str(Path.cwd().resolve()):
                        candidates.append(directory)
                except OSError:
                    continue
            args.sessions_root = candidates[0] if candidates else Path.home() / ".gemini" / "tmp" / Path.cwd().name.lower()
        elif args.agent == "junie":
            args.sessions_root = Path.home() / ".junie" / "sessions"
        else:
            args.sessions_root = DEFAULT_SESSIONS_ROOT
    configured_thresholds = project_config.get("thresholds")
    if isinstance(configured_thresholds, dict):
        DEFAULT_THRESHOLDS = normalized_thresholds(configured_thresholds)
    state_setting = STATE_ROOT if os.environ.get("SESSION_MONITOR_STATE_ROOT") else project_config.get("state_root") or STATE_ROOT
    STATE_ROOT = configured_path(state_setting, Path(project_config["_base"]))
    SERVER_STATE_PATH = STATE_ROOT / f"server-{args.agent}.json"
    SERVER_LOG_PATH = STATE_ROOT / f"server-{args.agent}.log"
    monitor = SessionMonitor(
        args.sessions_root.expanduser(),
        parse_iso_timestamp(args.since) if args.since else None,
        args.rollout.expanduser().resolve() if args.rollout else None,
        agent=args.agent,
        project_config=project_config,
    )
    if args.command == "phase":
        monitor.set_phase(None if args.name.lower() == "auto" else args.name)
        print(render_status(monitor.snapshot()), end="")
        return 0
    if args.command == "dismiss-warning":
        monitor.dismiss_warning()
        print(render_status(monitor.snapshot()), end="")
        return 0
    if args.command == "start":
        return start_background_server(args, open_browser=not args.no_open)
    if args.command == "stop":
        return stop_background_server()
    if args.command == "restart":
        stopped = stop_background_server()
        return stopped if stopped else start_background_server(args, open_browser=not args.no_open)
    if args.command == "json":
        snapshot = monitor.snapshot()
        print(json.dumps(snapshot, indent=2))
        return warning_exit(snapshot)
    if args.command == "status":
        snapshot = monitor.snapshot()
        print(render_status(snapshot), end="")
        return warning_exit(snapshot)
    if args.command == "watch":
        try:
            while True:
                snapshot = monitor.snapshot()
                print("\033[2J\033[H" + render_status(snapshot), end="", flush=True)
                time.sleep(max(0.1, args.interval))
        except KeyboardInterrupt:
            return 0
    server = create_server(monitor, args.port)
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"Session monitor: {url}", flush=True)
    if args.command == "open":
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
    except SystemExit as exc:
        if not isinstance(exc.code, str):
            raise
        print(exc.code, file=sys.stderr)
        exit_code = 2
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Session monitor source/parser error: {exc}", file=sys.stderr)
        exit_code = 2
    raise SystemExit(exit_code)
