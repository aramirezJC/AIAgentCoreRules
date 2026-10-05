#!/usr/bin/env python3
"""Install AIAgentCoreRules into a host project, and prepare and list agent worktrees.

Run from anywhere inside the host project (or one of its worktrees); the project root is the
main checkout of the git repository you are in. Override with --project.

Subcommands:
    install            Merge settings fragments into .claude/settings.json, link every layer's
                       skills into .claude/skills/, create CLAUDE.md if it is missing.
                       Safe to re-run: only adds or updates what the fragments define.
    check              Same as `install --dry-run`: report what install would change.
    prepare-worktree   Symlink worktree.symlinkDirectories into a worktree Claude Code did not
                       create (for example one made by hand with `git worktree add`).
    worktrees          List the project's linked worktrees with branch, dirty state, and commits
                       ahead of the current branch (used by /land-worktree).

Layers are the entries of <project>/GitIgnoredExternals/. Each layer may ship:
    Skills/<name>/SKILL.md          linked to .claude/skills/<name>
    Setup/settings.host.json        merged after this layer's Tools/setup/settings.core.json

Merge rules: objects merge key by key, lists of plain values are unioned, other values are set.
Hooks are matched by command string — a hook whose command is already present in that event is
left as it is. A changed settings.json is backed up to settings.json.bak before it is written.
Nothing is ever deleted.
"""

import argparse
import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CORE_ROOT = os.path.realpath(os.path.join(SCRIPT_DIR, "..", ".."))
CORE_FRAGMENT = os.path.join(SCRIPT_DIR, "settings.core.json")
HOST_FRAGMENT = os.path.join("Setup", "settings.host.json")
EXTERNALS = "GitIgnoredExternals"
CORE_NAME = "AIAgentCoreRules"
CORE_IMPORTS = [
    "@GitIgnoredExternals/AIAgentCoreRules/Rules/MetaRouter.md",
    "@GitIgnoredExternals/AIAgentCoreRules/Rules/StopAndVerify.md",
    "@GitIgnoredExternals/AIAgentCoreRules/Rules/CoreTags.md",
]


# ---------------------------------------------------------------------------------------------
# Project and layers

def git(args, cwd):
    result = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {cwd}: {result.stderr.strip()}")
    return result.stdout.strip()


def find_project_root(start):
    common = git(["rev-parse", "--path-format=absolute", "--git-common-dir"], start)
    return os.path.dirname(common)


def find_layers(root):
    """Return [(name, linked_path)] with the core layer first."""
    externals = os.path.join(root, EXTERNALS)
    if not os.path.isdir(externals):
        raise RuntimeError(f"{externals} not found — link AIAgentCoreRules first (Documentation/01_Setup.md)")
    layers = []
    for name in sorted(os.listdir(externals)):
        path = os.path.join(externals, name)
        if os.path.isdir(path):
            layers.append((name, path))
    is_core = lambda layer: os.path.realpath(layer[1]) == CORE_ROOT or layer[0] == CORE_NAME
    layers.sort(key=lambda layer: not is_core(layer))
    if not layers or not is_core(layers[0]):
        raise RuntimeError(f"{CORE_NAME} is not linked under {externals}")
    return layers


def load_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


# ---------------------------------------------------------------------------------------------
# Settings merge

def merge_hooks(target, fragment, source, log):
    hooks = target.setdefault("hooks", {})
    for event, groups in fragment.items():
        existing = hooks.setdefault(event, [])
        commands = {hook.get("command") for group in existing for hook in group.get("hooks", [])}
        for group in groups:
            missing = [hook for hook in group.get("hooks", []) if hook.get("command") not in commands]
            if not missing:
                continue
            existing.append(dict(group, hooks=missing))
            for hook in missing:
                log.append(f"settings: add {event} hook from {source}: {hook.get('command')}")
                commands.add(hook.get("command"))


def merge_value(target, fragment, source, log, path=""):
    for key, value in fragment.items():
        key_path = f"{path}.{key}" if path else key
        if key_path == "hooks":
            merge_hooks(target, value, source, log)
        elif isinstance(value, dict):
            child = target.setdefault(key, {})
            if not isinstance(child, dict):
                log.append(f"settings: SKIP {key_path} from {source} — existing value is not an object")
                continue
            merge_value(child, value, source, log, key_path)
        elif isinstance(value, list):
            current = target.setdefault(key, [])
            for item in value:
                if item not in current:
                    current.append(item)
                    log.append(f"settings: add {item!r} to {key_path} ({source})")
        elif target.get(key) != value:
            if key in target:
                log.append(f"settings: change {key_path} {target[key]!r} -> {value!r} ({source})")
            else:
                log.append(f"settings: set {key_path} = {value!r} ({source})")
            target[key] = value


def fragments(layers):
    found = [(f"{CORE_NAME} core", CORE_FRAGMENT)]
    for name, path in layers:
        host = os.path.join(path, HOST_FRAGMENT)
        if os.path.isfile(host):
            found.append((name, host))
    return found


def install_settings(root, layers, dry_run, log):
    settings_path = os.path.join(root, ".claude", "settings.json")
    settings = load_json(settings_path) if os.path.isfile(settings_path) else {}
    before = json.dumps(settings, sort_keys=True)
    for source, path in fragments(layers):
        merge_value(settings, load_json(path), source, log)
    if json.dumps(settings, sort_keys=True) == before or dry_run:
        return
    os.makedirs(os.path.dirname(settings_path), exist_ok=True)
    if os.path.isfile(settings_path):
        with open(settings_path, encoding="utf-8") as src, open(settings_path + ".bak", "w", encoding="utf-8") as dst:
            dst.write(src.read())
    with open(settings_path, "w", encoding="utf-8") as handle:
        json.dump(settings, handle, indent=2)
        handle.write("\n")


# ---------------------------------------------------------------------------------------------
# Skills and CLAUDE.md

def install_skills(root, layers, dry_run, log):
    skills_dir = os.path.join(root, ".claude", "skills")
    claimed = {}
    for layer_name, layer_path in layers:
        layer_skills = os.path.join(layer_path, "Skills")
        if not os.path.isdir(layer_skills):
            continue
        for skill in sorted(os.listdir(layer_skills)):
            if not os.path.isfile(os.path.join(layer_skills, skill, "SKILL.md")):
                continue
            if skill in claimed:
                log.append(f"skills: SKIP {skill} from {layer_name} — already provided by {claimed[skill]}")
                continue
            claimed[skill] = layer_name
            link = os.path.join(skills_dir, skill)
            target = os.path.relpath(os.path.join(root, EXTERNALS, layer_name, "Skills", skill), skills_dir)
            if os.path.lexists(link):
                if os.path.realpath(link) != os.path.realpath(os.path.join(layer_skills, skill)):
                    log.append(f"skills: CONFLICT {link} exists and does not point at {layer_name} — left as is")
                continue
            log.append(f"skills: link {skill} -> {target}")
            if not dry_run:
                os.makedirs(skills_dir, exist_ok=True)
                os.symlink(target, link)


def install_claude_md(root, dry_run, log):
    path = os.path.join(root, "CLAUDE.md")
    if not os.path.isfile(path):
        log.append("CLAUDE.md: create with the core imports — add the host layer's always-on files below them")
        if not dry_run:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("\n".join(CORE_IMPORTS) + "\n")
        return
    with open(path, encoding="utf-8") as handle:
        lines = {line.strip() for line in handle}
    for line in CORE_IMPORTS:
        if line not in lines:
            log.append(f"CLAUDE.md: MISSING {line} — add it by hand")


# ---------------------------------------------------------------------------------------------
# Worktrees

def list_worktrees(root):
    entries, current = [], {}
    for line in git(["worktree", "list", "--porcelain"], root).splitlines() + [""]:
        if not line:
            if current:
                entries.append(current)
            current = {}
            continue
        key, _, value = line.partition(" ")
        current[key] = value or True
    return [entry for entry in entries if os.path.realpath(entry["worktree"]) != os.path.realpath(root)]


def symlink_directories(root):
    settings_path = os.path.join(root, ".claude", "settings.json")
    settings = load_json(settings_path) if os.path.isfile(settings_path) else {}
    return settings.get("worktree", {}).get("symlinkDirectories", [])


def cmd_prepare_worktree(args, root):
    worktree = os.path.realpath(args.path)
    known = [os.path.realpath(entry["worktree"]) for entry in list_worktrees(root)]
    if worktree not in known:
        print(f"error: {worktree} is not a linked worktree of {root}", file=sys.stderr)
        return 1
    for rel in symlink_directories(root):
        source, dest = os.path.join(root, rel), os.path.join(worktree, rel)
        if not os.path.exists(source):
            print(f"skip {rel}: not present in {root}")
        elif os.path.lexists(dest):
            print(f"ok   {rel}: already present")
        else:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            os.symlink(source, dest)
            print(f"link {rel} -> {source}")
    return 0


def default_remote_branch(root):
    try:
        return git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], root)
    except RuntimeError:
        return None


def describe_worktree(root, entry, upstream):
    branch = entry.get("branch", "").replace("refs/heads/", "") or "(detached)"
    info = {"path": entry["worktree"], "branch": branch, "prunable": "prunable" in entry}
    if info["prunable"] or branch == "(detached)":
        return info
    tip = entry["HEAD"]
    info["dirty"] = bool(git(["status", "--porcelain"], entry["worktree"]))
    info["ahead"] = int(git(["rev-list", "--count", f"HEAD..{tip}"], root))
    info["behind"] = int(git(["rev-list", "--count", f"{tip}..HEAD"], root))
    if upstream:
        own = int(git(["rev-list", "--count", f"HEAD..{tip}", "--not", upstream], root))
        info["from_upstream"] = info["ahead"] - own
    return info


def cmd_worktrees(args, root):
    upstream = default_remote_branch(root)
    rows = [describe_worktree(root, entry, upstream) for entry in list_worktrees(root)]
    if args.json:
        print(json.dumps({"project": root, "current_branch": git(["branch", "--show-current"], root),
                          "upstream": upstream, "worktrees": rows}, indent=2))
        return 0
    print(f"project {root} on {git(['branch', '--show-current'], root) or '(detached)'}")
    if not rows:
        print("no linked worktrees")
    for row in rows:
        if row["prunable"]:
            print(f"- {row['path']}  PRUNABLE (folder missing — run git worktree prune)")
            continue
        if "ahead" not in row:
            print(f"- {row['path']}  {row['branch']}")
            continue
        notes = ["DIRTY" if row["dirty"] else "clean", f"{row['ahead']} ahead", f"{row['behind']} behind"]
        if row.get("from_upstream"):
            notes.append(f"{row['from_upstream']} of the ahead commits come from {upstream}")
        print(f"- {row['path']}  {row['branch']}  ({', '.join(notes)})")
    return 0


# ---------------------------------------------------------------------------------------------

def cmd_install(args, root):
    layers = find_layers(root)
    log = []
    install_settings(root, layers, args.dry_run, log)
    install_skills(root, layers, args.dry_run, log)
    install_claude_md(root, args.dry_run, log)
    header = "would change" if args.dry_run else "changed"
    print(f"project {root}  layers: {', '.join(name for name, _ in layers)}")
    print(f"{header}:" if log else "up to date — nothing to change")
    for line in log:
        print(f"  {line}")
    if log and not args.dry_run:
        print("Restart Claude Code sessions in this project to pick up settings and new skills.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", help="host project root (default: main checkout of the current git repo)")
    sub = parser.add_subparsers(dest="command")
    install = sub.add_parser("install", help="merge settings, link skills, create CLAUDE.md")
    install.add_argument("--dry-run", action="store_true")
    install.set_defaults(func=cmd_install)
    sub.add_parser("check", help="install --dry-run").set_defaults(func=cmd_install, dry_run=True)
    prepare = sub.add_parser("prepare-worktree", help="symlink worktree.symlinkDirectories into a worktree")
    prepare.add_argument("path")
    prepare.set_defaults(func=cmd_prepare_worktree)
    worktrees = sub.add_parser("worktrees", help="list linked worktrees and how they relate to the current branch")
    worktrees.add_argument("--json", action="store_true")
    worktrees.set_defaults(func=cmd_worktrees)
    args = parser.parse_args()
    if not args.command:
        args = parser.parse_args(sys.argv[1:] + ["install"])
    try:
        start = args.project or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
        root = os.path.realpath(args.project) if args.project else find_project_root(start)
        return args.func(args, root)
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
