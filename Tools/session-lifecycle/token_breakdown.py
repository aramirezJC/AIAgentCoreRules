"""Where a session's tokens went, and what saved tokens — estimated from the transcript.

Unit: the same as the token report's Total Tokens — the sum, over every model call, of the
context it read (uncached + cache read + cache write) plus its output. Something added to the
context at call k is re-read by every later call until a compaction, so its cost is

    carried(size, k) = size × (calls from k to the end of its segment)

Sizes are characters / 4, which is close enough for proportions. Every number here is an
estimate; the page and metrics.md label it so.

Standardized operations are the framework's own mechanisms: Runnable tools, the session
lifecycle script, skills, rule/process loads and subagents. Everything else a tool did is
ad-hoc; the rest of the total is conversation and base context (system prompt, CLAUDE.md,
replies, reasoning).

Dependency-free: imported by session_lifecycle.py.
"""

import glob
import json
import os
import re

CHARS_PER_TOKEN = 4.0
STANDARDIZED = ["Runnable tools", "Session lifecycle", "Skills", "Rule & process loads", "Subagents"]
AD_HOC = "Ad-hoc tool calls"
BASE = "Conversation & base context"
RUNNABLE_TOOLS = ["typecheck.py", "codeindex.py", "usages.py"]
LIFECYCLE = "session_lifecycle.py"
# Guesstimates of what one Runnable tool call replaces when done by hand: (context tokens, round-trips).
#   codeindex: one exploratory file read plus a grep to find it.
#   usages:    a grep over Assets/ plus two call-site reads.
#   typecheck: grepping the tail of Editor.log, after waiting for the editor to recompile.
AVOIDED_BY_TOOL = {"codeindex.py": (3000, 2), "usages.py": (6000, 3), "typecheck.py": (4000, 2)}
SAVINGS = ["Parallel tool calls", "Subagent delegation", "Partial file reads",
           "codeindex.py", "usages.py", "typecheck.py"]


def size(value):
    """Tokens in a tool input, tool result or text block (chars / 4)."""
    if value is None:
        return 0
    if isinstance(value, list):
        return sum(size(item.get("text") if isinstance(item, dict) and "text" in item else item) for item in value)
    if not isinstance(value, str):
        value = json.dumps(value)
    return int(len(value) / CHARS_PER_TOKEN)


def read_calls(path):
    """[(message_id, context, output)] in order, one per model call (usage is repeated on every
    content block of a message; keep the largest)."""
    calls, index = [], {}
    try:
        handle = open(path, errors="replace")
    except OSError:
        return calls
    with handle:
        for line in handle:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            message = entry.get("message") or {}
            usage = message.get("usage")
            if entry.get("type") != "assistant" or not usage:
                continue
            context = (usage.get("input_tokens") or 0) + (usage.get("cache_read_input_tokens") or 0) \
                + (usage.get("cache_creation_input_tokens") or 0)
            output = usage.get("output_tokens") or 0
            key = message.get("id") or entry.get("uuid")
            if key in index:
                old = calls[index[key]]
                calls[index[key]] = (key, max(old[1], context), max(old[2], output))
            else:
                index[key] = len(calls)
                calls.append((key, context, output))
    return calls


def subagent_runs(transcript_path, session_id):
    """{tool_use_id or file: {total, calls, peak, first}} for each subagent transcript."""
    runs = {}
    folder = os.path.join(os.path.dirname(transcript_path), session_id, "subagents")
    for path in sorted(glob.glob(os.path.join(folder, "*.jsonl"))):
        calls = [c for c in read_calls(path) if c[1] or c[2]]
        if not calls:
            continue
        key = os.path.basename(path)
        try:
            with open(path[:-len(".jsonl")] + ".meta.json") as handle:
                key = json.load(handle).get("toolUseId") or key
        except (OSError, ValueError):
            pass
        runs[key] = {"total": sum(c[1] + c[2] for c in calls), "calls": len(calls),
                     "peak": max(c[1] for c in calls), "first": calls[0][1]}
    return runs


def classify(name, tool_input, roots):
    if name == "Bash":
        command = tool_input.get("command", "")
        if any(re.search(r"python3?\s+\S*" + re.escape(tool), command) for tool in RUNNABLE_TOOLS):
            return "Runnable tools"
        if LIFECYCLE in command:
            return "Session lifecycle"
    elif name == "Skill":
        return "Skills"
    elif name in ("Agent", "Task"):
        return "Subagents"
    elif name == "Read":
        real = os.path.realpath(os.path.expanduser(tool_input.get("file_path", "")))
        if any(real.startswith(root + os.sep) for root in roots):
            return "Rule & process loads"
    return AD_HOC


def partial_read_unread(tool_input):
    """Tokens of a file left unread by a Read with limit/offset, judged from the file as it is now."""
    if not tool_input.get("limit") and not tool_input.get("offset"):
        return 0
    path = tool_input.get("file_path", "")
    try:
        with open(path, errors="replace") as handle:
            lines = handle.readlines()
    except OSError:
        return 0
    if not lines:
        return 0
    start = max(int(tool_input.get("offset") or 1) - 1, 0)
    read = min(int(tool_input.get("limit") or len(lines)), max(len(lines) - start, 0))
    unread_lines = len(lines) - read
    return int(sum(len(line) for line in lines) / CHARS_PER_TOKEN * unread_lines / len(lines))


def analyse(transcript_path, session_id, roots):
    """{"total", "categories": {name: tokens}, "standardized", "savings": {name: {tokens, round_trips,
    count}}, "estimated": True} — or None when the transcript is missing."""
    if not transcript_path or not os.path.isfile(transcript_path):
        return None
    roots = [os.path.realpath(root) for root in roots]
    calls = read_calls(transcript_path)
    position = {key: i for i, (key, _context, _output) in enumerate(calls)}
    boundaries = []                         # call indexes where a compaction started a new segment
    ops = {}                                # tool_use id -> op
    order = []
    extra = []                              # (category, tokens, at) not tied to a tool_use block
    tool_uses_per_call = {}
    last_skill = None
    seen_calls = 0

    with open(transcript_path, errors="replace") as handle:
        for line in handle:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            message = entry.get("message") or {}
            content = message.get("content")
            if entry.get("type") == "system" and entry.get("subtype") == "compact_boundary":
                boundaries.append(seen_calls)
            if entry.get("type") == "assistant":
                key = message.get("id") or entry.get("uuid")
                call = position.get(key, seen_calls)
                seen_calls = max(seen_calls, call + 1)
                for block in content if isinstance(content, list) else []:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    tool_input = block.get("input") or {}
                    op = {"id": block.get("id"), "name": block.get("name"), "input": tool_input, "call": call, "at": call + 1,
                          "tokens": size(tool_input),
                          "category": classify(block.get("name"), tool_input, roots)}
                    ops[block.get("id")] = op
                    order.append(op)
                    tool_uses_per_call[call] = tool_uses_per_call.get(call, 0) + 1
                    if op["name"] == "Skill":
                        last_skill = op
            elif entry.get("type") == "user":
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("tool_use_id") in ops:
                            op = ops[block["tool_use_id"]]
                            op["result"] = size(block.get("content"))
                            op["tokens"] += op["result"]
                            op["at"] = seen_calls
                text = content if isinstance(content, str) else " ".join(
                    b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text") \
                    if isinstance(content, list) else ""
                if entry.get("isMeta") and text.startswith("Base directory for this skill") and last_skill:
                    last_skill["tokens"] += size(text)     # the skill body is injected after the Skill call
                elif "<task-notification>" in text:
                    extra.append(("Subagents", size(text), seen_calls))

    def remaining(at):
        """Calls from index `at` to the end of its compaction segment."""
        end = next((b for b in boundaries if b > at), len(calls))
        return max(end - at, 0)

    def carried(tokens, at):
        return tokens * remaining(at)

    categories = dict.fromkeys(STANDARDIZED + [AD_HOC], 0)
    for op in order:
        categories[op["category"]] += carried(op["tokens"], op["at"])
    for category, tokens, at in extra:
        categories[category] += carried(tokens, at)
    runs = subagent_runs(transcript_path, session_id)
    categories["Subagents"] += sum(run["total"] for run in runs.values())

    total = sum(context + output for _key, context, output in calls) + sum(run["total"] for run in runs.values())
    categories[BASE] = max(total - sum(categories.values()), 0)

    savings = {name: {"tokens": 0, "round_trips": 0, "count": 0} for name in SAVINGS}
    for call, count in tool_uses_per_call.items():
        if count > 1:
            saving = savings["Parallel tool calls"]
            saving["count"] += 1
            saving["round_trips"] += count - 1
            saving["tokens"] += (count - 1) * (calls[call][1] if call < len(calls) else 0)
    for op in order:
        if op["category"] == "Subagents":
            run = runs.get(op["id"])
            if run:
                saving = savings["Subagent delegation"]
                saving["count"] += 1
                saving["round_trips"] += run["calls"]
                kept_out = max(run["peak"] - run["first"] - op.get("result", 0), 0)
                saving["tokens"] += carried(kept_out, op["at"])
        elif op["name"] == "Read":
            unread = partial_read_unread(op["input"])
            if unread:
                saving = savings["Partial file reads"]
                saving["count"] += 1
                saving["tokens"] += carried(unread, op["at"])
        elif op["category"] == "Runnable tools":
            command = op["input"].get("command", "")
            hits = [tool for tool in RUNNABLE_TOOLS
                    for _ in re.findall(r"python3?\s+\S*" + re.escape(tool), command)]
            for tool in hits:
                avoided, round_trips = AVOIDED_BY_TOOL[tool]
                saving = savings[tool]
                saving["count"] += 1
                saving["round_trips"] += round_trips
                saving["tokens"] += carried(max(avoided - op["tokens"] // len(hits), 0), op["at"])

    return {"estimated": True, "total": total, "calls": len(calls), "categories": categories,
            "standardized": sum(categories[name] for name in STANDARDIZED), "savings": savings,
            "assumptions": {tool: {"tokens": t, "round_trips": r} for tool, (t, r) in AVOIDED_BY_TOOL.items()}}


def session_total(transcript_path, session_id):
    """(tokens, model calls) for a session, main thread plus subagents, each call counted once.
    The token report's Total Tokens counts a call once per content block, so it runs ~2-3x higher."""
    if not transcript_path or not os.path.isfile(transcript_path):
        return None
    calls = read_calls(transcript_path)
    runs = subagent_runs(transcript_path, session_id)
    return (sum(context + output for _key, context, output in calls) + sum(run["total"] for run in runs.values()),
            len(calls))
