#!/usr/bin/env python3
"""Session lifecycle for Claude Code: start, note, compile, open.

One folder per session under the reports root (default: <cwd>/GitIgnoreReports/Sessions):

    <YYYY-MM-DD_HHMM>_<lane>_<id8>/
        session.json   state (source of truth)
        metrics.md     rendered from session.json + token report + router trace
        retro.md       written by /end-session
        tokens/        session-support per-session Markdown report

Subcommands:
    hook-start   SessionStart hook. Reads hook JSON on stdin, prints context for the agent.
    hook-end     SessionEnd hook. Compiles metrics even when /end-session was not run.
    set          Record lane and title.
    note         Log an inaccuracy or iteration.
    compile      Refresh token report, router trace and metrics.md.
    open         Open metrics.md and retro.md in the default viewer.
    path         Print the session folder.

Hooks must never break a session: hook-* subcommands always exit 0.
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys

SCRIPT_PATH = os.path.abspath(__file__)
SESSION_SUPPORT = os.path.join(os.path.dirname(SCRIPT_PATH), "..", "session-support", "session-support")
LANES = ["small_task", "bug_fix", "investigation", "feature", "other"]
RUNNABLE_TOOLS = ["typecheck.py", "codeindex.py", "usages.py"]


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


def current_transcript(project_dir):
    """Newest Claude Code transcript for this project: the running session."""
    encoded = re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(project_dir))
    sessions_dir = os.path.join(os.path.expanduser("~"), ".claude", "projects", encoded)
    if not os.path.isdir(sessions_dir):
        return None, None
    names = [n for n in os.listdir(sessions_dir) if n.endswith(".jsonl")]
    if not names:
        return None, None
    newest = max(names, key=lambda n: os.path.getmtime(os.path.join(sessions_dir, n)))
    return newest[:-len(".jsonl")], os.path.join(sessions_dir, newest)


def resolve(args):
    root = reports_root(args)
    session_id = getattr(args, "session_id", None) or current_transcript(os.getcwd())[0]
    folder = find_folder(root, session_id) or find_folder(root, None)
    if folder is None:
        sys.exit("No session folder found under %s. Was the SessionStart hook installed?" % root)
    return folder, load_state(folder)


def folder_name(state):
    started = datetime.datetime.fromisoformat(state["started_at"])
    parts = [started.strftime("%Y-%m-%d_%H%M")]
    if state.get("lane"):
        parts.append(state["lane"].replace("_", "-"))
    parts.append(state["session_id"][:8])
    return "_".join(parts)


# ---------------------------------------------------------------- router trace

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

def token_report(folder, state):
    """Token telemetry from session-support, only if its 'current' session is this one."""
    if not os.path.isfile(SESSION_SUPPORT):
        return {"available": False, "reason": "session-support not found at %s" % SESSION_SUPPORT}
    base = [sys.executable, SESSION_SUPPORT, "--agent", "claude", "report", "--scope", "current"]
    try:
        result = subprocess.run(base + ["--format", "json"], capture_output=True, text=True, timeout=40)
        data = json.loads(result.stdout)
    except (subprocess.SubprocessError, ValueError) as error:
        return {"available": False, "reason": "report failed: %s" % error}
    sessions = data.get("sessions") or []
    if not sessions or sessions[0].get("id") != state["session_id"]:
        return {"available": False, "reason": "latest session in the project is not this one"}
    subprocess.run(base + ["--format", "markdown", "--per-session", "--output", os.path.join(folder, "tokens")],
                   capture_output=True, text=True, timeout=40)
    session = sessions[0]
    return {"available": True, "total_tokens": session.get("total_tokens"),
            "turns": session.get("completed_turns"), "subagents": session.get("subagents"),
            "categories": session.get("categories"), "warning": session.get("warning")}


# ---------------------------------------------------------------- render

def render(folder, state, project_dir):
    imports, loads, tools = router_trace(state, project_dir)
    tokens = state.get("tokens") or {}
    lines = [
        "# Session Metrics — %s" % (state.get("title") or "untitled"),
        "",
        "| Field | Value |",
        "| --- | --- |",
        "| Session | `%s` |" % state["session_id"],
        "| Lane | %s |" % (state.get("lane") or "**not set**"),
        "| Started | %s |" % state["started_at"],
        "| Ended | %s |" % (state.get("ended_at") or "in progress"),
        "| /end-session run | %s |" % ("yes" if state.get("end_session_run") else "no"),
        "| Inaccuracies | %d |" % len(state["inaccuracies"]),
        "| Iterations | %d |" % len(state["iterations"]),
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
        lines += ["- `%s` %s" % (item["at"][11:19], item["text"]) for item in state[kind]] or ["- none"]
    lines += ["", "## Router trace", "", "Always loaded via CLAUDE.md:", ""]
    lines += ["- `%s`" % item for item in imports] or ["- none"]
    lines += ["", "Loaded on demand, in order:", "", "| # | Time | File | Via (Bash rows are heuristic) |", "| ---: | --- | --- | --- |"]
    lines += ["| %d | %s | `%s` | %s |" % (i + 1, item["at"], item["file"], item["via"]) for i, item in enumerate(loads)]
    if not loads:
        lines.append("| – | – | none | – |")
    lines += ["", "## Runnable tools", ""]
    lines += ["- `%s` × %d" % (tool, count) for tool, count in sorted(tools.items())] or ["- none run"]
    with open(os.path.join(folder, "metrics.md"), "w") as handle:
        handle.write("\n".join(lines) + "\n")


def compile_folder(folder, state, project_dir):
    state["tokens"] = token_report(folder, state)
    save_state(folder, state)
    render(folder, state, project_dir)


# ---------------------------------------------------------------- commands

def read_hook_input():
    try:
        return json.load(sys.stdin)
    except ValueError:
        return {}


def cmd_hook_start(args):
    try:
        hook = {} if sys.stdin.isatty() else read_hook_input()
        inferred_id, inferred_transcript = current_transcript(os.getcwd())
        session_id = hook.get("session_id") or inferred_id or "unknown"
        hook.setdefault("transcript_path", inferred_transcript)
        root = reports_root(args)
        folder = find_folder(root, session_id)
        resumed = folder is not None
        if folder is None:
            state = {"session_id": session_id, "transcript_path": hook.get("transcript_path"),
                     "project_dir": os.getcwd(), "started_at": now_iso(), "lane": None, "title": None,
                     "inaccuracies": [], "iterations": [], "end_session_run": False}
            folder = os.path.join(root, folder_name(state))
            os.makedirs(folder, exist_ok=True)
            save_state(folder, state)
            render(folder, state, os.getcwd())
        else:
            state = load_state(folder)
        print("\n".join([
            "## Session tracking (%s)" % ("resumed" if resumed else "started"),
            "- session_id: %s" % session_id,
            "- folder: %s" % folder,
            "- lifecycle script: %s" % SCRIPT_PATH,
            "- lane: %s" % (state.get("lane") or "not set"),
            "",
            "Required: once the MetaRouter mode is classified, record it:",
            "  python3 \"%s\" set --session-id %s --lane <%s> --title \"<short title>\""
            % (SCRIPT_PATH, session_id, "|".join(LANES)),
            "Log agent corrections with /inaccuracy and deliberate direction changes with /iteration.",
            "Close the session with /end-session (metrics + retrospective).",
        ]))
    except Exception as error:  # a hook must never block the session
        print("Session tracking failed to start: %s" % error)
    return 0


def cmd_hook_end(args):
    try:
        hook = read_hook_input()
        folder = find_folder(reports_root(args), hook.get("session_id"))
        if folder:
            state = load_state(folder)
            state["ended_at"] = state.get("ended_at") or now_iso()
            state["end_reason"] = hook.get("reason")
            compile_folder(folder, state, state.get("project_dir") or os.getcwd())
    except Exception:
        pass
    return 0


def cmd_set(args):
    folder, state = resolve(args)
    if args.lane:
        state["lane"] = args.lane
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
    state[key].append({"at": now_iso(), "text": args.text})
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
    paths = [os.path.join(folder, name) for name in ("metrics.md", "retro.md")
             if os.path.isfile(os.path.join(folder, name))]
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    for path in paths:
        subprocess.run([opener, path])
        print(path)


def cmd_path(args):
    folder, _state = resolve(args)
    print(folder)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reports-root")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("hook-start", help="also safe to run by hand (/start-session)").set_defaults(func=cmd_hook_start)
    sub.add_parser("hook-end").set_defaults(func=cmd_hook_end)
    for name, func in (("set", cmd_set), ("note", cmd_note), ("compile", cmd_compile),
                       ("open", cmd_open), ("path", cmd_path)):
        command = sub.add_parser(name)
        command.add_argument("--session-id", help="defaults to the running session (newest transcript)")
        command.set_defaults(func=func)
        if name == "set":
            command.add_argument("--lane", choices=LANES)
            command.add_argument("--title")
        if name == "note":
            command.add_argument("--kind", choices=["inaccuracy", "iteration"], required=True)
            command.add_argument("text")
        if name == "compile":
            command.add_argument("--final", action="store_true", help="mark /end-session as run")
    args = parser.parse_args()
    sys.exit(args.func(args) or 0)


if __name__ == "__main__":
    main()
