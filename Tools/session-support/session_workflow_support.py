from __future__ import annotations

import json
import re
import shlex
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Sequence


DEFAULT_SESSIONS_ROOT = Path.home() / ".codex/sessions"
DEFAULT_CATEGORY_CONFIG = Path(__file__).resolve().with_name("categories.example.json")
ARTIFACT_PATH_PATTERN = re.compile(
    r"(?P<path>(?:/[\w./@+-]+|Assets/[\w./@+-]+|[\w.-]+/[\w./@+-]+)"
    r"\.(?:md|txt|json|jsonl|schema|prompt))"
)
ROLLOUT_ID_PATTERN = re.compile(
    r"(?P<id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$",
    re.IGNORECASE,
)
INJECTED_USER_TEXT_PREFIXES = (
    "<environment_context>",
    "<permissions instructions>",
    "<recommended_plugins>",
    "# AGENTS.md instructions",
)


def _fail(message: str) -> None:
    raise SystemExit(message)


def load_category_config(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"Category config not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Category config is invalid JSON: {path}: {exc}") from exc


def find_latest_rollout_file(
    root: Path = DEFAULT_SESSIONS_ROOT,
    since: datetime | None = None,
) -> Path:
    rollout_files = find_rollout_files(root, since)
    primary_files = [
        path for path in rollout_files
        if read_session_metadata(path).session_type == "primary"
    ]
    legacy_files = [
        path for path in rollout_files
        if read_session_metadata(path).session_type == "unknown"
    ]
    candidates = primary_files or legacy_files
    if not candidates:
        _fail(f"No rollout files found under {root}")
    return candidates[-1]


def parse_iso_timestamp(value: str, *, local_timezone=None) -> datetime:
    normalized = value.strip()
    if not normalized:
        _fail("--since requires a non-empty ISO date or timestamp")
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
            parsed = datetime.combine(date.fromisoformat(normalized), time.min)
        else:
            parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise SystemExit(f"Invalid ISO date or timestamp for --since: {value}") from exc
    zone = local_timezone or datetime.now().astimezone().tzinfo or timezone.utc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zone)
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class SessionMetadata:
    session_id: str
    timestamp: datetime | None
    session_type: str
    source: object
    parent_session_id: str | None = None
    agent_path: str | None = None
    agent_depth: int | None = None


def classify_session_metadata(payload: dict) -> SessionMetadata:
    source = payload.get("source")
    session_type = "unknown"
    parent_session_id = None
    agent_path = None
    agent_depth = None
    if isinstance(source, str) and source:
        session_type = "primary"
    elif isinstance(source, dict):
        subagent = source.get("subagent")
        spawn = subagent.get("thread_spawn") if isinstance(subagent, dict) else None
        if isinstance(spawn, dict):
            session_type = "subagent"
            parent_session_id = str(spawn.get("parent_thread_id") or "") or None
            agent_path = str(spawn.get("agent_path") or "") or None
            try:
                agent_depth = int(spawn["depth"]) if spawn.get("depth") is not None else None
            except (TypeError, ValueError):
                agent_depth = None
    timestamp_raw = str(payload.get("timestamp") or "")
    timestamp = None
    if timestamp_raw:
        try:
            timestamp = parse_iso_timestamp(timestamp_raw)
        except SystemExit:
            timestamp = None
    return SessionMetadata(
        session_id=str(payload.get("id") or ""),
        timestamp=timestamp,
        session_type=session_type,
        source=source,
        parent_session_id=parent_session_id,
        agent_path=agent_path,
        agent_depth=agent_depth,
    )


def read_session_metadata(path: Path) -> SessionMetadata:
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                obj = json.loads(line)
                if obj.get("type") == "session_meta" and isinstance(obj.get("payload"), dict):
                    metadata = classify_session_metadata(obj["payload"])
                    rollout_match = ROLLOUT_ID_PATTERN.search(path.stem)
                    rollout_id = rollout_match.group("id") if rollout_match else ""
                    if (
                        metadata.session_type == "primary"
                        and metadata.session_id
                        and rollout_id
                        and rollout_id != metadata.session_id
                    ):
                        return replace(
                            metadata,
                            session_id=rollout_id,
                            session_type="subagent",
                            parent_session_id=metadata.session_id,
                            agent_path="/root/inferred-legacy-fork",
                            agent_depth=1,
                        )
                    return metadata
    except (OSError, json.JSONDecodeError):
        pass
    return SessionMetadata(path.stem, None, "unknown", None)


def find_rollout_files(
    root: Path = DEFAULT_SESSIONS_ROOT,
    since: datetime | None = None,
) -> list[Path]:
    rollout_files = sorted(root.expanduser().rglob("rollout-*.jsonl"))
    if since is None:
        return rollout_files
    cutoff = since.astimezone(timezone.utc)
    return [
        path
        for path in rollout_files
        if (metadata := read_session_metadata(path)).timestamp is not None
        and metadata.timestamp >= cutoff
    ]


def detect_helper_scripts(command: str) -> list[str]:
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()

    hits: list[str] = []

    def normalize(token: str) -> str:
        return token.strip().strip("()[]{};,")

    def is_helper_path(token: str) -> bool:
        token = normalize(token)
        return bool(
            token.endswith(".sh")
            and (
                "/tools/" in token.lower()
                or token.lower().startswith(("tools/", "scripts/"))
            )
        )

    for index, token in enumerate(tokens):
        token = normalize(token)
        if not is_helper_path(token):
            continue
        if index == 0 or tokens[index - 1] == "bash":
            hits.append(Path(token).name)
    return hits


def extract_tool_commands(arguments_raw: str) -> list[str]:
    try:
        parsed = json.loads(arguments_raw)
    except json.JSONDecodeError:
        return detect_helper_scripts(arguments_raw)

    commands: list[str] = []

    def visit(value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"cmd", "command"} and isinstance(child, str):
                    commands.append(child)
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(parsed)
    return commands


def is_injected_user_text(text: str) -> bool:
    normalized = text.lstrip()
    return any(normalized.startswith(prefix) for prefix in INJECTED_USER_TEXT_PREFIXES)


def extract_user_text(payload: dict) -> str:
    content = payload.get("content")
    if not isinstance(content, list):
        return ""
    chunks: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "input_text":
            continue
        text = str(item.get("text") or "")
        if is_injected_user_text(text):
            continue
        chunks.append(text)
    return "\n".join(chunks).strip()


def classify_turn(user_message: str, last_agent_message: str, tool_calls: int, category_config: dict) -> str:
    text = f"{user_message}\n{last_agent_message}".lower()
    for rule in category_config.get("categories", []):
        include = [item.lower() for item in rule.get("include", [])]
        exclude = [item.lower() for item in rule.get("exclude", [])]
        require_any = [item.lower() for item in rule.get("require_any", [])]
        min_tool_calls = int(rule.get("min_tool_calls") or 0)
        include_ok = all(item in text for item in include) if rule.get("match_all") else any(item in text for item in include)
        if not include_ok and min_tool_calls and tool_calls >= min_tool_calls:
            include_ok = True
        if not include_ok:
            continue
        if require_any and not any(item in text for item in require_any):
            continue
        if exclude and any(item in text for item in exclude):
            continue
        return str(rule.get("name") or "other")
    return str(category_config.get("fallback_category") or "other")


def _turn_text(turn: "TurnSummary") -> str:
    return f"{turn.user_message}\n{turn.last_agent_message}".lower()


def _artifact_paths(text: str) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for match in ARTIFACT_PATH_PATTERN.finditer(text):
        path = match.group("path").strip().rstrip(".,:;)")
        if path not in seen:
            seen.add(path)
            paths.append(path)
    return paths


def _has_any(text: str, needles: Sequence[str]) -> bool:
    return any(needle in text for needle in needles)


def _first_artifact(text: str, suffixes: Sequence[str]) -> str | None:
    for path in _artifact_paths(text):
        if any(path.endswith(suffix) for suffix in suffixes):
            return path
    return None


@dataclass(frozen=True)
class TurnSummary:
    turn_index: int
    user_message: str
    last_agent_message: str
    category: str
    tool_call_count: int
    helper_invocations: tuple[str, ...]

    def as_json(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SessionSummary:
    rollout_file: Path
    session_id: str
    turns: tuple[TurnSummary, ...]

    def helper_turn_count(self) -> int:
        return sum(1 for turn in self.turns if turn.helper_invocations)

    def helper_turn_ratio(self) -> float:
        if not self.turns:
            return 0.0
        return self.helper_turn_count() / len(self.turns)

    def category_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for turn in self.turns:
            counts[turn.category] = counts.get(turn.category, 0) + 1
        return counts

    def active_category_count(self) -> int:
        return len(self.category_counts())

    def split_warning_flags(self) -> list[str]:
        flags: list[str] = []
        if len(self.turns) >= 20:
            flags.append("20+ turns")
        if self.active_category_count() >= 3:
            flags.append("3+ categories")
        if self.helper_turn_ratio() <= 0.25:
            flags.append("low helper coverage")
        return flags

    def ollama_candidate_recommendations(self) -> list[str]:
        if self.verdict() != "split recommended":
            return []

        recommendations: list[str] = []
        seen_scripts: set[str] = set()

        def add(script: str, artifact: str, reason: str) -> None:
            if script in seen_scripts:
                return
            seen_scripts.add(script)
            recommendations.append(f"{script} {artifact} ({reason})")

        for turn in reversed(self.turns):
            text = _turn_text(turn)
            artifact = _first_artifact(text, (".md", ".txt", ".json", ".jsonl"))
            if not artifact:
                continue

            if _has_any(text, ("review comment", "review-comment", "pr comment", "copied feedback", "review feedback")):
                add("ollama_review_comment_classifier.sh", artifact, "bounded review-comment artifact")
            if _has_any(text, ("follow-up", "followup", "session export", "session summary", "rollout")):
                add("ollama_session_followup_extract.sh", artifact, "bounded session/follow-up artifact")
            if _has_any(text, ("drift candidate", "drift-candidate", "doc drift", "drift triage")):
                add("ollama_doc_drift_triage.sh", artifact, "bounded drift-candidate artifact")
            if _has_any(text, ("summarize", "summary", "summarise")) and artifact.endswith((".md", ".txt")):
                add("ollama_doc_summarize.sh", artifact, "bounded prose artifact")

        return recommendations

    def verdict(self) -> str:
        flags = set(self.split_warning_flags())
        if {"20+ turns", "3+ categories", "low helper coverage"}.issubset(flags):
            return "split recommended"
        return "stay on this seam"

    def drift_label(self) -> str:
        flags = set(self.split_warning_flags())
        if {"20+ turns", "3+ categories", "low helper coverage"}.issubset(flags):
            return "Split recommended"
        if self.active_category_count() >= 3:
            return "Scope drift"
        if len(self.turns) >= 20:
            return "Session getting long"
        if self.helper_turn_ratio() <= 0.25 and len(self.turns) >= 8:
            return "Tooling detour"
        return "Stay on this seam"

    def as_json(self) -> dict:
        return {
            "rollout_file": str(self.rollout_file),
            "session_id": self.session_id,
            "turns": len(self.turns),
            "helper_turns": self.helper_turn_count(),
            "helper_turn_coverage": round(self.helper_turn_ratio(), 4),
            "category_counts": self.category_counts(),
            "flags": self.split_warning_flags(),
            "verdict": self.verdict(),
            "drift_label": self.drift_label(),
            "ollama_candidate_recommendations": self.ollama_candidate_recommendations(),
            "turn_details": [turn.as_json() for turn in self.turns],
        }


def parse_rollout(path: Path, category_config: dict) -> SessionSummary:
    session_id = ""
    turns: list[TurnSummary] = []
    current_turn_tool_calls = 0
    current_turn_user_messages: list[str] = []
    current_turn_helper_invocations: list[str] = []
    turn_counter = 0

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            obj = json.loads(line)
            payload = obj.get("payload")
            if not isinstance(payload, dict):
                payload = {}
            if obj.get("type") == "session_meta":
                session_id = str(payload.get("id") or "")
                continue
            if obj.get("type") == "response_item":
                if payload.get("type") == "message" and payload.get("role") == "user":
                    user_text = extract_user_text(payload)
                    if user_text:
                        current_turn_user_messages.append(user_text)
                elif payload.get("type") in {"function_call", "custom_tool_call"}:
                    current_turn_tool_calls += 1
                    arguments_raw = str(payload.get("arguments") or "")
                    for command in extract_tool_commands(arguments_raw):
                        current_turn_helper_invocations.extend(detect_helper_scripts(command))
                continue
            if obj.get("type") != "event_msg":
                continue
            event_type = payload.get("type")
            if event_type == "task_started":
                current_turn_tool_calls = 0
                current_turn_user_messages = []
                current_turn_helper_invocations = []
                continue
            if event_type == "task_complete":
                turn_counter += 1
                user_message = "\n".join(current_turn_user_messages).strip()
                last_agent_message = str(payload.get("last_agent_message") or "")
                turns.append(
                    TurnSummary(
                        turn_index=turn_counter,
                        user_message=user_message,
                        last_agent_message=last_agent_message,
                        category=classify_turn(user_message, last_agent_message, current_turn_tool_calls, category_config),
                        tool_call_count=current_turn_tool_calls,
                        helper_invocations=tuple(current_turn_helper_invocations),
                    )
                )
                current_turn_tool_calls = 0
                current_turn_user_messages = []
                current_turn_helper_invocations = []

    return SessionSummary(rollout_file=path, session_id=session_id or path.stem, turns=tuple(turns))


def render_split_report(summary: SessionSummary) -> str:
    counts = summary.category_counts()
    category_summary = ", ".join(f"{name}={count}" for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])))
    helper_pct = summary.helper_turn_ratio() * 100.0
    lines = [
        f"Rollout File: {summary.rollout_file}",
        f"Session ID: {summary.session_id}",
        f"Verdict: {summary.verdict()}",
        f"Drift Label: {summary.drift_label()}",
        f"Turns: {len(summary.turns)}",
        f"Categories: {summary.active_category_count()} ({category_summary or 'none'})",
        f"Helper Turns: {summary.helper_turn_count()} / {len(summary.turns)} ({helper_pct:.1f}%)",
        f"Flags: {', '.join(summary.split_warning_flags()) if summary.split_warning_flags() else 'none'}",
    ]
    if summary.verdict() == "split recommended":
        lines.extend(
            [
                "Recommendation: split discovery/reply/doc work from the current implementation or review seam.",
            ]
        )
        candidates = summary.ollama_candidate_recommendations()
        if candidates:
            lines.append("Ollama Candidates:")
            lines.extend(f"- {candidate}" for candidate in candidates)
    elif summary.active_category_count() >= 3:
        lines.extend(
            [
                "Recommendation: keep going only if the remaining work is one narrow seam; otherwise split before adding another category.",
            ]
        )
    return "\n".join(lines) + "\n"
