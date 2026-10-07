#!/usr/bin/env python3
"""Session lifecycle for Claude Code: start, note, compile, open.

One folder per session under the reports root (default: <cwd>/GitIgnoreReports/Sessions):

    <YYYY-MM-DD_HHMM>_<lane>_<name>_<id8>/   (lane and name only once set)
        session.json   state (source of truth)
        metrics.md     rendered from session.json + token report + router trace
        retro.md       written by /end-session; its "## Applied" section tracks each proposal
        retro.html     rendered from retro.md (retro_page.py) — progress, per-proposal status, token charts
        tokens/        session-support per-session Markdown report

Subcommands:
    hook-start   SessionStart hook. Reads hook JSON on stdin, prints context for the agent.
    hook-end     SessionEnd hook. Compiles metrics even when /end-session was not run.
    hook-stop    Stop hook. Recompiles after a reply (throttled), for sessions that never exit.
    set          Record name, lane, work type and title.
    note         Log an inaccuracy or iteration.
    compile      Refresh token report, router trace and metrics.md.
    open         Open metrics.md and retro.html (rendered from retro.md) in the default viewer.
    retro        Render retro.html, list proposal statuses, or mark one proposal applied/skipped/pending.
    path         Print the session folder.
    features     List CreateFeature features that are not complete (/active-features).
    prune-empty  Delete session folders with nothing worth keeping (--dry-run to preview).

A session's folder is created on first record (set, note, compile, or after the first reply),
never at session start, so sessions opened and closed without work leave nothing behind.

Hooks must never break a session: hook-* subcommands always exit 0.
"""

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

import retro_page
import token_breakdown

SCRIPT_PATH = os.path.abspath(__file__)
SESSION_SUPPORT = os.path.join(os.path.dirname(SCRIPT_PATH), "..", "session-support", "session-support")
LANES = ["small_task", "bug_fix", "investigation", "feature", "other"]
# Work type is what the work is; lane is which process ran it. Kept separate for the meta-analysis.
WORK_TYPES = ["bug_fix", "small_feature", "feature", "question", "other"]
LANE_WORK_TYPE = {"small_task": "small_feature", "bug_fix": "bug_fix", "investigation": "question",
                  "feature": "feature", "other": "other"}
RUNNABLE_TOOLS = ["typecheck.py", "codeindex.py", "usages.py"]
# CreateFeature working folders, relative to the project root (Processes/CreateFeature/index.md
# working_folder). Override with SESSION_FEATURES_ROOT or --features-root.
DEFAULT_FEATURES_DIR = os.path.join("Assets", "GitIgnoreAssets", "Features")
CREATE_FEATURE_INDEX = os.path.join(os.path.dirname(SCRIPT_PATH), "..", "..", "Processes", "CreateFeature", "index.md")
# hook-stop recompiles at most this often; the Stop hook fires after every reply.
STOP_COMPILE_INTERVAL_SECONDS = 120
# Who logged a note. Entries written before sources existed have none and count as engineer.
NOTE_SOURCES = ["engineer", "agent", "retro"]


def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def reports_root(args):
    root = getattr(args, "reports_root", None) or os.environ.get("SESSION_REPORTS_ROOT")
    return os.path.abspath(root or os.path.join(os.getcwd(), "GitIgnoreReports", "Sessions"))


# ---------------------------------------------------------------- state

def find_folder(root, session_id):
    if not os.path.isdir(root):
        return None
    candidates = []
    for name in os.listdir(root):
        state_path = os.path.join(root, name, "session.json")
        if not os.path.isfile(state_path):
            continue
        if session_id:
            try:
                with open(state_path) as handle:
                    if json.load(handle).get("session_id") == session_id:
                        return os.path.join(root, name)
            except (OSError, ValueError):
                continue
        else:
            candidates.append((os.path.getmtime(state_path), os.path.join(root, name)))
    if candidates:
        return max(candidates)[1]
    return None


def load_state(folder):
    with open(os.path.join(folder, "session.json")) as handle:
        return json.load(handle)


def save_state(folder, state):
    with open(os.path.join(folder, "session.json"), "w") as handle:
        json.dump(state, handle, indent=2)


def locate_transcript(session_id, guess):
    """The guessed transcript path when it exists, else <session_id>.jsonl under any project
    folder. Claude Code files a transcript under the directory it was launched from, which is
    not the project root when a session starts in a subdirectory."""
    if (guess and os.path.isfile(guess)) or not session_id:
        return guess
    projects_root = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    if os.path.isdir(projects_root):
        for name in sorted(os.listdir(projects_root)):
            candidate = os.path.join(projects_root, name, session_id + ".jsonl")
            if os.path.isfile(candidate):
                return candidate
    return guess


def current_transcript(project_dir):
    """The running session: CLAUDE_CODE_SESSION_ID when set (exact, safe with concurrent
    sessions), else the newest Claude Code transcript for this project (a guess)."""
    encoded = re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(project_dir))
    sessions_dir = os.path.join(os.path.expanduser("~"), ".claude", "projects", encoded)
    env_id = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if env_id:
        return env_id, locate_transcript(env_id, os.path.join(sessions_dir, env_id + ".jsonl"))
    if not os.path.isdir(sessions_dir):
        return None, None
    names = [n for n in os.listdir(sessions_dir) if n.endswith(".jsonl")]
    if not names:
        return None, None
    newest = max(names, key=lambda n: os.path.getmtime(os.path.join(sessions_dir, n)))
    return newest[:-len(".jsonl")], os.path.join(sessions_dir, newest)


def user_turns(transcript_path):
    """Prompts the engineer actually typed (tool results and meta entries excluded)."""
    if not transcript_path or not os.path.isfile(transcript_path):
        return 0
    count = 0
    with open(transcript_path, errors="replace") as handle:
        for line in handle:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("type") != "user" or entry.get("isMeta"):
                continue
            content = (entry.get("message") or {}).get("content")
            if isinstance(content, str) and content.strip():
                count += 1
            elif isinstance(content, list) and any(isinstance(c, dict) and c.get("type") == "text" for c in content):
                count += 1
    return count


def ensure_folder(root, session_id, transcript_path=None, project_dir=None):
    """The session's folder, created on first use. Folders are only made when there is
    something to record (a set/note/compile, or a hook after a real exchange), never at
    session start, so sessions opened and closed without work leave nothing behind.
    Returns None when the session has no transcript to attach a folder to."""
    folder = find_folder(root, session_id)
    if folder:
        return folder
    transcript_path = locate_transcript(session_id, transcript_path)
    if not session_id or not transcript_path or not os.path.isfile(transcript_path):
        return None
    state = {"session_id": session_id, "transcript_path": transcript_path,
             "project_dir": project_dir or os.getcwd(), "tracking_started_at": now_iso(),
             "started_at": transcript_started_at(transcript_path) or now_iso(),
             "name": None, "lane": None, "work_type": None, "title": None,
             "inaccuracies": [], "iterations": [], "end_session_run": False}
    folder = os.path.join(root, folder_name(state))
    os.makedirs(folder, exist_ok=True)
    save_state(folder, state)
    render(folder, state, state["project_dir"])
    return folder


def is_empty_folder(folder, state):
    """Nothing worth keeping: no lane, title, name or notes, no tokens, and no typed prompt."""
    tokens = state.get("tokens") or {}
    return (not state.get("lane") and not state.get("title") and not state.get("name")
            and not state.get("inaccuracies") and not state.get("iterations")
            and not (tokens.get("available") and tokens.get("total_tokens"))
            and not os.path.isfile(os.path.join(folder, "retro.md"))
            and user_turns(locate_transcript(state.get("session_id"), state.get("transcript_path"))) == 0)


def resolve(args):
    root = reports_root(args)
    session_id = getattr(args, "session_id", None) or current_transcript(os.getcwd())[0]
    if not session_id:
        sys.exit("No session id: pass --session-id, or run inside a Claude Code session.")
    # Never fall back to another session's folder: with concurrent sessions that edits the wrong one.
    folder = ensure_folder(root, session_id, project_dir=os.getcwd())
    if folder is None:
        sys.exit("No transcript found for session %s, so there is nothing to record." % session_id)
    return folder, load_state(folder)


def slug(text, limit=40):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:limit].strip("-")


def folder_name(state):
    started = datetime.datetime.fromisoformat(state["started_at"])
    parts = [started.strftime("%Y-%m-%d_%H%M")]
    if state.get("lane"):
        parts.append(state["lane"].replace("_", "-"))
    if state.get("name") and slug(state["name"]):
        parts.append(slug(state["name"]))
    parts.append(state["session_id"][:8])
    return "_".join(parts)


# ---------------------------------------------------------------- router trace

def transcript_started_at(transcript_path):
    """Local ISO time of the transcript's first timestamped entry, or None."""
    if not transcript_path or not os.path.isfile(transcript_path):
        return None
    with open(transcript_path) as handle:
        for line in handle:
            try:
                stamp = json.loads(line).get("timestamp")
            except ValueError:
                continue
            if stamp:
                moment = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                return moment.astimezone().isoformat(timespec="seconds")
    return None


def import_roots(project_dir):
    """Directories imported by CLAUDE.md, plus their real paths (they are often symlinks)."""
    imports, roots = [], set()
    claude_md = os.path.join(project_dir, "CLAUDE.md")
    if os.path.isfile(claude_md):
        with open(claude_md) as handle:
            for line in handle:
                match = re.match(r"\s*@(\S+)", line)
                if match:
                    imports.append(match.group(1))
    for rel in imports:
        parts = rel.split("/")
        top = os.path.join(project_dir, *parts[:2]) if len(parts) > 2 else os.path.join(project_dir, parts[0])
        roots.add(os.path.abspath(top))
        roots.add(os.path.realpath(top))
    return imports, sorted(roots)


def display_path(path, project_dir, roots):
    real = os.path.realpath(path)
    for root in roots:
        if real.startswith(os.path.realpath(root) + os.sep):
            return os.path.relpath(real, os.path.dirname(os.path.realpath(root)))
    return os.path.relpath(path, project_dir) if path.startswith(project_dir) else path


def transcript_files(transcript_path, session_id):
    files = []
    if transcript_path and os.path.isfile(transcript_path):
        files.append((transcript_path, "main"))
        sub_dir = os.path.join(os.path.dirname(transcript_path), session_id)
        if os.path.isdir(sub_dir):
            for base, _dirs, names in os.walk(sub_dir):
                for name in sorted(names):
                    if name.endswith(".jsonl"):
                        files.append((os.path.join(base, name), "subagent"))
    return files


def router_trace(state, project_dir):
    imports, roots = import_roots(project_dir)
    loads, tools, seen = [], {}, set()
    md_in_command = re.compile(r"[\w./~-]+\.md")
    for path, via in transcript_files(state.get("transcript_path"), state["session_id"]):
        try:
            handle = open(path)
        except OSError:
            continue
        with handle:
            for line in handle:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                content = (entry.get("message") or {}).get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    tool_input = block.get("input") or {}
                    targets, bases = [], [project_dir]
                    if block.get("name") == "Read":
                        targets = [tool_input.get("file_path", "")]
                    elif block.get("name") == "Bash":
                        command = tool_input.get("command", "")
                        for tool in RUNNABLE_TOOLS:
                            count = len(re.findall(r"python3?\s+\S*" + re.escape(tool), command))
                            if count:
                                tools[tool] = tools.get(tool, 0) + count
                        # Relative paths after `cd <dir>` resolve against that dir.
                        for cd_target in re.findall(r"\bcd\s+([^\s;&|]+)", command):
                            cd_target = os.path.expanduser(cd_target.strip("\"'"))
                            bases.insert(0, cd_target if os.path.isabs(cd_target)
                                         else os.path.join(project_dir, cd_target))
                        targets = md_in_command.findall(command)
                    for target in targets:
                        target = os.path.expanduser(target)
                        candidates = [target] if os.path.isabs(target) else [os.path.join(b, target) for b in bases]
                        absolute = next((c for c in candidates if os.path.isfile(c)), candidates[-1])
                        real = os.path.realpath(absolute)
                        if not any(real.startswith(os.path.realpath(r) + os.sep) for r in roots):
                            continue
                        key = (real, via)
                        if key in seen:
                            continue
                        seen.add(key)
                        loads.append({"file": display_path(absolute, project_dir, roots),
                                      "via": "%s · %s" % (via, block.get("name")),
                                      "at": entry.get("timestamp", "")[11:19]})
    return imports, loads, tools


# ---------------------------------------------------------------- tokens

def load_session_support():
    """Import the vendored session-support CLI as a module (it is a script without .py)."""
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader("session_support_cli", SESSION_SUPPORT)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def token_report(folder, state):
    """Token telemetry for exactly this session.

    The CLI's `report --scope current` means "newest session", which is wrong with concurrent
    sessions. The package's SessionMonitor accepts an explicit rollout file, so we drive the
    same report functions with this session's transcript instead of editing the vendored code.
    """
    transcript = state.get("transcript_path")
    if not os.path.isfile(SESSION_SUPPORT):
        return {"available": False, "reason": "session-support not found at %s" % SESSION_SUPPORT}
    if not transcript or not os.path.isfile(transcript):
        return {"available": False, "reason": "transcript not found"}
    try:
        from pathlib import Path
        cli = load_session_support()
        args = argparse.Namespace(project_config=Path(os.path.dirname(SESSION_SUPPORT)) / "project.example.json",
                                  agent="claude", sessions_root=Path(os.path.dirname(transcript)), since=None)
        monitor = cli.load_monitor(args)
        monitor.explicit_rollout = Path(transcript)
        session = cli.support_report(monitor, "current")["sessions"][0]
        tokens_dir = os.path.join(folder, "tokens")
        os.makedirs(tokens_dir, exist_ok=True)
        for report in monitor.generated_session_reports("current", False):
            with open(os.path.join(tokens_dir, report["filename"]), "w") as handle:
                handle.write(report["content"])
    except Exception as error:  # telemetry is best-effort; never fail the compile
        return {"available": False, "reason": "report failed: %s" % error}
    if session.get("id") != state["session_id"]:
        return {"available": False, "reason": "report described session %s" % session.get("id")}
    return {"available": True, "total_tokens": session.get("total_tokens"),
            "turns": session.get("completed_turns"), "subagents": session.get("subagents"),
            "categories": session.get("categories"), "warning": session.get("warning")}


# ---------------------------------------------------------------- render

def count_by_source(items):
    """'3' when every note came from the engineer, else '3 (engineer 1 · agent 1 · retro 1)'."""
    counts = {source: 0 for source in NOTE_SOURCES}
    for item in items:
        counts[item.get("source", "engineer")] = counts.get(item.get("source", "engineer"), 0) + 1
    if counts["engineer"] == len(items):
        return str(len(items))
    return "%d (%s)" % (len(items), " · ".join("%s %d" % (s, n) for s, n in counts.items() if n))


def render(folder, state, project_dir):
    imports, loads, tools = router_trace(state, project_dir)
    tokens = state.get("tokens") or {}
    lines = [
        "# Session Metrics — %s" % (state.get("name") or state.get("title") or "untitled"),
        "",
        "| Field | Value |",
        "| --- | --- |",
        "| Session | `%s` |" % state["session_id"],
        "| Name | %s |" % (state.get("name") or "–"),
        "| Title | %s |" % (state.get("title") or "–"),
        "| Lane | %s |" % (state.get("lane") or "**not set**"),
        "| Work type | %s |" % ((state["work_type"] + (" (from lane)" if state.get("work_type_source") == "lane" else ""))
                                if state.get("work_type") else "**not set**"),
    ]
    if state.get("feature"):
        lines += ["| Feature | %s |" % state["feature"],
                  "| Phase | %s |" % (phase_label(state["phase"]) if state.get("phase") else "**not set**")]
    lines += [
        "| Started | %s |" % state["started_at"],
        "| Tracking since | %s |" % state.get("tracking_started_at", state["started_at"]),
        "| Ended | %s |" % (state.get("ended_at") or "in progress"),
        "| /end-session run | %s |" % ("yes" if state.get("end_session_run") else "no"),
        "| Inaccuracies | %s |" % count_by_source(state["inaccuracies"]),
        "| Iterations | %s |" % count_by_source(state["iterations"]),
    ]
    if tokens.get("available"):
        lines += ["| Total tokens | %s |" % "{:,}".format(tokens["total_tokens"] or 0),
                  "| Turns | %s |" % tokens.get("turns"),
                  "| Subagents | %s |" % tokens.get("subagents"),
                  "| Health | %s |" % tokens.get("warning")]
    else:
        lines.append("| Tokens | unavailable (%s) |" % tokens.get("reason", "not compiled yet"))
    for kind in ("inaccuracies", "iterations"):
        lines += ["", "## %s" % kind.capitalize(), ""]
        lines += ["- `%s` %s%s" % (item["at"][11:19], item["text"],
                                   "" if item.get("source", "engineer") == "engineer" else " _(%s)_" % item["source"])
                  for item in state[kind]] or ["- none"]
    lines += ["", "## Lane changes", ""]
    lines += ["- `%s` %s → %s" % (item["at"][11:19], item["from"], item["to"])
              for item in state.get("lane_history", [])] or ["- none"]
    lines += ["", "## Work type changes", ""]
    lines += ["- `%s` %s → %s" % (item["at"][11:19], item["from"], item["to"])
              for item in state.get("work_type_history", [])] or ["- none"]
    lines += ["", "## Router trace", "", "Always loaded via CLAUDE.md:", ""]
    lines += ["- `%s`" % item for item in imports] or ["- none"]
    lines += ["", "Loaded on demand, in order:", "", "| # | Time | File | Via (Bash rows are heuristic) |", "| ---: | --- | --- | --- |"]
    lines += ["| %d | %s | `%s` | %s |" % (i + 1, item["at"], item["file"], item["via"]) for i, item in enumerate(loads)]
    if not loads:
        lines.append("| – | – | none | – |")
    lines += ["", "## Runnable tools", ""]
    lines += ["- `%s` × %d" % (tool, count) for tool, count in sorted(tools.items())] or ["- none run"]
    lines += breakdown_lines(state)
    with open(os.path.join(folder, "metrics.md"), "w") as handle:
        handle.write("\n".join(lines) + "\n")


def session_comparison(folder, state):
    """[{id, lane, tokens, calls, current}] for every session under the reports root with tokens,
    totals de-duplicated per model call (token_breakdown.session_total) so sessions compare fairly."""
    root = os.path.dirname(folder)
    sessions = []
    for name in sorted(os.listdir(root)):
        try:
            other = state if os.path.join(root, name) == folder else load_state(os.path.join(root, name))
        except (OSError, ValueError):
            continue
        transcript = locate_transcript(other.get("session_id"), other.get("transcript_path"))
        total = token_breakdown.session_total(transcript, other.get("session_id"))
        if total and total[0]:
            sessions.append({"id": other["session_id"][:8], "lane": other.get("lane"), "tokens": total[0],
                             "calls": total[1], "current": other is state})
    return sessions


def breakdown_lines(state):
    """metrics.md section: where the tokens went and what saved tokens (estimates)."""
    breakdown = state.get("breakdown") or {}
    if not breakdown.get("total"):
        return ["", "## Token breakdown (estimated)", "",
                "- unavailable (%s)" % (breakdown.get("error") or "not compiled yet")]
    total = breakdown["total"]
    lines = ["", "## Token breakdown (estimated)", "",
             "Total %s across %d model calls, each counted once (the token report counts a call once per "
             "content block). A tool result costs its size × every later call that re-reads it."
             % ("{:,}".format(total), breakdown["calls"]), "",
             "| Category | Standardized | Tokens | Share |", "| --- | --- | ---: | ---: |"]
    for name, tokens in breakdown["categories"].items():
        lines.append("| %s | %s | %s | %.1f%% |" % (name, "yes" if name in token_breakdown.STANDARDIZED else "–",
                                                   "{:,}".format(tokens), 100.0 * tokens / total))
    lines.append("| **Standardized operations** | | **%s** | **%.1f%%** |"
                 % ("{:,}".format(breakdown["standardized"]), 100.0 * breakdown["standardized"] / total))
    lines += ["", "| Saving mechanism | Uses | Tokens saved | Round-trips saved |", "| --- | ---: | ---: | ---: |"]
    for name, saving in sorted(breakdown["savings"].items(), key=lambda item: -item[1]["tokens"]):
        lines.append("| %s | %d | %s | %d |" % (name, saving["count"], "{:,}".format(saving["tokens"]),
                                                saving["round_trips"]))
    return lines


def compile_folder(folder, state, project_dir):
    # The hook payload's path can be wrong for a session launched from a subdirectory.
    state["transcript_path"] = locate_transcript(state["session_id"], state.get("transcript_path"))
    # A resumed session's transcript may predate tracking; report the real start.
    state["started_at"] = transcript_started_at(state.get("transcript_path")) or state["started_at"]
    state["tokens"] = token_report(folder, state)
    try:   # estimates for the retro charts; best-effort like the token report
        state["breakdown"] = token_breakdown.analyse(state.get("transcript_path"), state["session_id"],
                                                     import_roots(project_dir)[1])
        state["comparison"] = session_comparison(folder, state)
    except Exception as error:
        state["breakdown"] = {"error": str(error)}
    state["compiled_at"] = now_iso()
    save_state(folder, state)
    render(folder, state, project_dir)


# ---------------------------------------------------------------- commands

def read_hook_input():
    try:
        return json.load(sys.stdin)
    except ValueError:
        return {}


def hook_project_dir(hook):
    """Hooks may not run in the project dir; the hook payload's cwd is authoritative."""
    project_dir = hook.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    os.chdir(project_dir)
    return project_dir


def hook_log(args, event, hook, outcome):
    """One line per hook run, so a hook that fires but finds nothing leaves evidence."""
    try:
        root = reports_root(args)
        os.makedirs(root, exist_ok=True)
        with open(os.path.join(root, "hooks.log"), "a") as handle:
            handle.write("%s %s session=%s source=%s reason=%s cwd=%s -> %s\n" % (
                now_iso(), event, (hook.get("session_id") or "?")[:8], hook.get("source"),
                hook.get("reason"), os.getcwd(), outcome))
    except Exception:
        pass


def cmd_hook_start(args):
    try:
        hook = {} if sys.stdin.isatty() else read_hook_input()
        hook_project_dir(hook)
        inferred_id, inferred_transcript = current_transcript(os.getcwd())
        session_id = hook.get("session_id") or inferred_id or "unknown"
        hook.setdefault("transcript_path", inferred_transcript)
        root = reports_root(args)
        # No folder yet: it is created on the first set/note/compile or after the first real
        # exchange (hook-stop), so sessions opened and closed without work leave nothing behind.
        folder = find_folder(root, session_id)
        resumed = folder is not None
        state = load_state(folder) if folder else {}
        print("\n".join([
            "## Session tracking (%s)" % ("resumed" if resumed else "started"),
            "- session_id: %s" % session_id,
            "- folder: %s" % (folder or "created on first record (set, note, or after the first reply)"),
            "- lifecycle script: %s" % SCRIPT_PATH,
            "- name: %s" % (state.get("name") or "not set"),
            "- lane: %s" % (state.get("lane") or "not set"),
            "- work type: %s" % (state.get("work_type") or "not set"),
            "",
            "Required: once the MetaRouter mode is classified, record it and the work type:",
            "  python3 \"%s\" set --session-id %s --lane <%s> --work-type <%s> --title \"<short title>\""
            % (SCRIPT_PATH, session_id, "|".join(LANES), "|".join(WORK_TYPES)),
            "If the engineer named the session (/start-session <name>), also pass --name \"<name>\".",
            "The engineer logs corrections with /inaccuracy and direction changes with /iteration.",
            "When you retract a claim or the engineer rejects your approach, log it yourself at once:",
            "  python3 \"%s\" note --session-id %s --kind inaccuracy --source agent \"<what was wrong>\""
            % (SCRIPT_PATH, session_id),
            "Close the session with /end-session (metrics + retrospective).",
        ] + feature_hint(os.getcwd(), state)))
        hook_log(args, "start", hook, ("resumed " + folder) if resumed else "folder deferred until there is something to record")
    except Exception as error:  # a hook must never block the session
        print("Session tracking failed to start: %s" % error)
        hook_log(args, "start", locals().get("hook") or {}, "ERROR %s" % error)
    return 0


def cmd_hook_end(args):
    hook = {}
    try:
        hook = read_hook_input()
        hook_project_dir(hook)
        root = reports_root(args)
        session_id = hook.get("session_id")
        folder = find_folder(root, session_id)
        if folder and is_empty_folder(folder, load_state(folder)):
            shutil.rmtree(folder)
            hook_log(args, "end", hook, "removed empty folder " + folder)
            return 0
        if not folder and user_turns(locate_transcript(session_id, hook.get("transcript_path"))):
            folder = ensure_folder(root, session_id, hook.get("transcript_path"), os.getcwd())
        if folder:
            state = load_state(folder)
            state["ended_at"] = now_iso()   # latest exit; a resumed session ends again
            state["end_reason"] = hook.get("reason")
            compile_folder(folder, state, state.get("project_dir") or os.getcwd())
            hook_log(args, "end", hook, "compiled " + folder)
        else:
            hook_log(args, "end", hook, "nothing to save, no folder")
    except Exception as error:
        hook_log(args, "end", hook, "ERROR %s" % error)
    return 0


# ---------------------------------------------------------------- features

def phase_label(key):
    """'2_discovery' -> 'Phase 2 — Discovery'."""
    number, _, name = (key or "").partition("_")
    return "Phase %s — %s" % (number, name.replace("_", " ").title()) if name else (key or "unknown phase")


def phase_models():
    """phase key -> recommended_model, read from CreateFeature/index.md."""
    models, current = {}, None
    try:
        with open(CREATE_FEATURE_INDEX) as handle:
            for line in handle:
                key = re.match(r"^  (\d+_\w+):\s*$", line)
                if key:
                    current = key.group(1)
                model = re.match(r"^\s+recommended_model:\s*(\w+)", line)
                if model and current:
                    models[current] = model.group(1)
    except OSError:
        pass
    return models


def yaml_value(text, field):
    match = re.search(r"^\s*%s:\s*\"([^\"]*)\"" % field, text, re.MULTILINE)
    return match.group(1) if match else ""


def active_features(project_dir, features_root=None):
    """Every CreateFeature progress file whose status is not complete, newest first."""
    root = features_root or os.environ.get("SESSION_FEATURES_ROOT") or os.path.join(project_dir, DEFAULT_FEATURES_DIR)
    models = phase_models()
    found = []
    if not os.path.isdir(root):
        return found
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name, "%s_Progress.md" % name)
        if not os.path.isfile(path):
            continue
        with open(path, errors="replace") as handle:
            text = handle.read()
        status = yaml_value(text, "status") or "unknown"
        if status == "complete":
            continue
        phase = yaml_value(text, "current_phase")
        found.append({"feature": yaml_value(text, "feature") or name, "phase": phase, "phase_label": phase_label(phase),
                      "status": status, "updated_at": yaml_value(text, "updated_at"),
                      "in_flight": yaml_value(text, "in_flight"), "next": yaml_value(text, "next"),
                      "model": models.get(phase), "progress_file": path})
    return sorted(found, key=lambda f: f["updated_at"], reverse=True)


def resume_command(feature):
    model = " --model %s" % feature["model"] if feature.get("model") else ""
    return "claude%s \"/resume %s\"" % (model, feature["feature"])


def cmd_features(args):
    features = active_features(os.getcwd(), args.features_root)
    if args.json:
        print(json.dumps(features, indent=2))
        return 0
    if not features:
        print("No features in progress.")
        return 0
    print("In-progress features (%d):" % len(features))
    for f in features:
        print("- %s · %s · %s · updated %s" % (f["feature"], f["phase_label"], f["status"], f["updated_at"][:10] or "?"))
        if f["in_flight"]:
            print("  in flight: %s" % f["in_flight"])
        if f["next"]:
            print("  next: %s" % f["next"])
        print("  resume: %s" % resume_command(f))
    return 0


def feature_hint(project_dir, state):
    """Start-context lines naming in-progress features, so a new session can offer /resume."""
    if state.get("feature"):
        return []   # this session already belongs to a feature
    try:
        features = active_features(project_dir)
    except Exception:
        return []
    if not features:
        return []
    lines = ["", "In-progress features (one session per phase; /active-features for details):"]
    lines += ["  - %s · %s · next: %s" % (f["feature"], f["phase_label"], (f["next"] or "see progress file")[:120])
              for f in features[:5]]
    lines.append("If the engineer's first message is not about something else, offer /resume <FeatureName>.")
    return lines


def cmd_prune_empty(args):
    """Delete session folders with nothing worth keeping (see is_empty_folder)."""
    root = reports_root(args)
    if not os.path.isdir(root):
        print("No sessions folder at %s." % root)
        return 0
    removed = kept = 0
    for name in sorted(os.listdir(root)):
        folder = os.path.join(root, name)
        if not os.path.isfile(os.path.join(folder, "session.json")):
            continue
        try:
            state = load_state(folder)
        except (OSError, ValueError):
            continue
        if is_empty_folder(folder, state):
            removed += 1
            print("%s %s" % ("would remove" if args.dry_run else "removed", name))
            if not args.dry_run:
                shutil.rmtree(folder)
        else:
            kept += 1
    print("%d empty folder(s) %s, %d kept." % (removed, "found" if args.dry_run else "removed", kept))
    return 0


def cmd_hook_stop(args):
    """Stop hook: recompile after a reply, so metrics exist even for a session that never
    exits (the app marks idle sessions completed without firing SessionEnd). Never marks
    the session ended. Throttled; a compile takes well under a second."""
    hook = {}
    try:
        hook = read_hook_input()
        hook_project_dir(hook)
        root = reports_root(args)
        folder = find_folder(root, hook.get("session_id"))
        if not folder:
            # First reply of a session: now there is something to record.
            if not user_turns(locate_transcript(hook.get("session_id"), hook.get("transcript_path"))):
                return 0
            folder = ensure_folder(root, hook.get("session_id"), hook.get("transcript_path"), os.getcwd())
            if not folder:
                return 0
        state = load_state(folder)
        last = state.get("compiled_at")
        if last:
            age = datetime.datetime.now().astimezone() - datetime.datetime.fromisoformat(last)
            if age.total_seconds() < STOP_COMPILE_INTERVAL_SECONDS:
                return 0
        compile_folder(folder, state, state.get("project_dir") or os.getcwd())
    except Exception as error:
        hook_log(args, "stop", hook, "ERROR %s" % error)   # successes are not logged: one per reply is noise
    return 0


def set_work_type(state, work_type, source):
    if state.get("work_type") and state["work_type"] != work_type:
        state.setdefault("work_type_history", []).append({"at": now_iso(), "from": state["work_type"], "to": work_type})
    state["work_type"] = work_type
    state["work_type_source"] = source


def cmd_set(args):
    folder, state = resolve(args)
    if args.lane:
        # Keep earlier lanes: a mid-session change (e.g. a BugFix detour) must stay auditable.
        if state.get("lane") and state["lane"] != args.lane:
            state.setdefault("lane_history", []).append({"at": now_iso(), "from": state["lane"], "to": args.lane})
        state["lane"] = args.lane
    if args.work_type:
        set_work_type(state, args.work_type, "explicit")
    elif args.lane and state.get("work_type_source") != "explicit":
        # Until a work type is given, follow the lane, so every session gets one.
        set_work_type(state, LANE_WORK_TYPE[args.lane], "lane")
    if args.name:
        state["name"] = args.name
    if args.feature:
        state["feature"] = args.feature
    if args.phase:
        # One session per phase; a phase change mid-session stays auditable like a lane change.
        if state.get("phase") and state["phase"] != args.phase:
            state.setdefault("phase_history", []).append({"at": now_iso(), "from": state["phase"], "to": args.phase})
        state["phase"] = args.phase
    if args.title:
        state["title"] = args.title
    save_state(folder, state)
    target = os.path.join(os.path.dirname(folder), folder_name(state))
    if target != folder and not os.path.exists(target):
        os.rename(folder, target)
        folder = target
    render(folder, state, state.get("project_dir") or os.getcwd())
    print(folder)


def cmd_note(args):
    folder, state = resolve(args)
    key = "inaccuracies" if args.kind == "inaccuracy" else "iterations"
    # source: engineer (/inaccuracy, /iteration), agent (self-corrected live), or retro
    # (found by /end-session and not logged live). Lets reports tell live logging apart.
    state[key].append({"at": now_iso(), "text": args.text, "source": args.source})
    save_state(folder, state)
    render(folder, state, state.get("project_dir") or os.getcwd())
    print("%s #%d logged in %s" % (args.kind, len(state[key]), os.path.join(folder, "metrics.md")))


def cmd_compile(args):
    folder, state = resolve(args)
    if args.final:
        state["end_session_run"] = True
        state["ended_at"] = now_iso()
    compile_folder(folder, state, state.get("project_dir") or os.getcwd())
    print(os.path.join(folder, "metrics.md"))


def cmd_open(args):
    folder, _state = resolve(args)
    if os.path.isfile(os.path.join(folder, "retro.md")):
        retro_page.render(os.path.join(folder, "retro.md"), SCRIPT_PATH)
    paths = [os.path.join(folder, name) for name in ("metrics.md", "retro.html")
             if os.path.isfile(os.path.join(folder, name))]
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    for path in paths:
        subprocess.run([opener, path])
        print(path)


def retro_folder(args):
    """--folder (a path, a folder name under the reports root, or a unique part of one such as
    the session id's first 8 characters), else the current session. Proposals are often resolved
    in a later session, so marking must reach any session's retro."""
    if not args.folder:
        return resolve(args)[0]
    if os.path.isdir(args.folder):
        return os.path.abspath(args.folder)
    root = reports_root(args)
    names = sorted(name for name in os.listdir(root) if os.path.isdir(os.path.join(root, name))) \
        if os.path.isdir(root) else []
    if args.folder in names:
        return os.path.join(root, args.folder)
    matches = [name for name in names if args.folder in name]
    if len(matches) != 1:
        sys.exit("--folder %s matches %d session folders under %s%s" % (
            args.folder, len(matches), root, (": " + ", ".join(matches)) if matches else ""))
    return os.path.join(root, matches[0])


def cmd_retro(args):
    folder = retro_folder(args)
    retro_path = os.path.join(folder, "retro.md")
    if not os.path.isfile(retro_path):
        sys.exit("No retro.md in %s — /end-session writes it." % folder)
    if args.mark is not None:
        if not args.status:
            sys.exit("--mark needs --status (%s)." % "|".join(retro_page.STATUSES))
        with open(retro_path) as handle:
            text = handle.read()
        try:
            text = retro_page.mark(text, args.mark, args.status, args.note)
        except ValueError as error:
            sys.exit(str(error))
        with open(retro_path, "w") as handle:
            handle.write(text)
    html_path = retro_page.render(retro_path, SCRIPT_PATH)
    with open(retro_path) as handle:
        for item in retro_page.statuses(handle.read()):
            print("#%d %-8s %s%s" % (item["n"], item["status"], item["file"],
                                    (" — " + item["detail"]) if item["detail"] else ""))
    print(html_path)
    if args.open:
        subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", html_path])


def cmd_path(args):
    folder, _state = resolve(args)
    print(folder)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reports-root")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("hook-start", help="also safe to run by hand (/start-session)").set_defaults(func=cmd_hook_start)
    sub.add_parser("hook-end").set_defaults(func=cmd_hook_end)
    sub.add_parser("hook-stop").set_defaults(func=cmd_hook_stop)
    features = sub.add_parser("features", help="list CreateFeature features that are not complete (/active-features)")
    features.add_argument("--features-root", help="default <cwd>/%s, or $SESSION_FEATURES_ROOT" % DEFAULT_FEATURES_DIR)
    features.add_argument("--json", action="store_true")
    features.set_defaults(func=cmd_features)
    prune = sub.add_parser("prune-empty", help="delete session folders with no lane, notes, tokens or typed prompt")
    prune.add_argument("--dry-run", action="store_true")
    prune.set_defaults(func=cmd_prune_empty)
    for name, func in (("set", cmd_set), ("note", cmd_note), ("compile", cmd_compile),
                       ("open", cmd_open), ("path", cmd_path), ("retro", cmd_retro)):
        command = sub.add_parser(name)
        command.add_argument("--session-id", help="defaults to $CLAUDE_CODE_SESSION_ID, else the newest transcript")
        command.set_defaults(func=func)
        if name == "set":
            command.add_argument("--name", help="engineer-given session name; also names the folder")
            command.add_argument("--lane", choices=LANES)
            command.add_argument("--work-type", choices=WORK_TYPES,
                                 help="defaults to the lane's work type until set explicitly")
            command.add_argument("--title")
            command.add_argument("--feature", help="CreateFeature name this session works on (set by /feature, /resume)")
            command.add_argument("--phase", help="CreateFeature phase key, e.g. 2_discovery")
        if name == "note":
            command.add_argument("--kind", choices=["inaccuracy", "iteration"], required=True)
            command.add_argument("--source", choices=NOTE_SOURCES, default="engineer",
                                 help="who logged it: engineer (default), agent (self-correction), retro (/end-session)")
            command.add_argument("text")
        if name == "compile":
            command.add_argument("--final", action="store_true", help="mark /end-session as run")
        if name == "retro":
            command.add_argument("--folder", help="another session's folder: path, folder name, or a unique part "
                                                  "such as the session id's first 8 characters")
            command.add_argument("--mark", type=int, metavar="N", help="proposal number to update")
            command.add_argument("--status", choices=retro_page.STATUSES)
            command.add_argument("--note", help="Applied-line detail, e.g. '<file> — <what changed>'; "
                                                "omitted keeps the existing note")
            command.add_argument("--open", action="store_true", help="open retro.html afterwards")
    args = parser.parse_args()
    sys.exit(args.func(args) or 0)


if __name__ == "__main__":
    main()
