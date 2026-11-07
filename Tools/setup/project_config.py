"""Portable documentation paths shared by setup, lifecycle tools and agents."""
import argparse
import json
import os
from pathlib import Path, PureWindowsPath
import subprocess
import sys

import project_root

CONFIG_NAME = "ai-agent-core.json"
DEFAULT_PATHS = {
    "features": "Assets/GitIgnoreAssets/Features",
    "design_documents": "Assets/GitIgnoreAssets/DesignDocuments",
}


def validate_path(project, value):
    """Validate portable storage paths, including existing symlink parents."""
    if not isinstance(value, str) or not value.strip() or "\\" in value or "\0" in value:
        raise RuntimeError("documentation paths must be nonempty relative paths using / separators")
    path = Path(value)
    if path.is_absolute() or PureWindowsPath(value).drive or ".." in path.parts or path == Path("."):
        raise RuntimeError("documentation paths must be relative folders inside the project: " + value)
    root = Path(project).resolve()
    resolved = (root / path).resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise RuntimeError("documentation path escapes the project: " + value)
    for ancestor in (resolved, *resolved.parents):
        if ancestor == root:
            break
        if ancestor.exists() and not ancestor.is_dir():
            raise RuntimeError("documentation path is not a directory: " + value)
    return path.as_posix()


def load_config(project):
    path = Path(project) / CONFIG_NAME
    if not path.exists():
        if path.is_symlink():
            raise RuntimeError("configuration is a dangling symlink: " + str(path))
        return {"schema_version": 1, "paths": dict(DEFAULT_PATHS)}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RuntimeError("cannot read " + str(path) + ": " + str(error)) from error
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        raise RuntimeError(str(path) + " requires schema_version 1")
    paths = value.get("paths")
    if not isinstance(paths, dict):
        raise RuntimeError(str(path) + " requires a paths object")
    for key in DEFAULT_PATHS:
        if key not in paths:
            raise RuntimeError(str(path) + " is missing paths." + key)
        validate_path(project, paths[key])
    return value


def resolve_path(project, key, override=None, environ=None):
    if key not in DEFAULT_PATHS:
        raise RuntimeError("unknown documentation path: " + key)
    environment = os.environ if environ is None else environ
    selected = override or (environment.get("SESSION_FEATURES_ROOT") if key == "features" else None)
    if selected:
        path = Path(selected)
        return (path if path.is_absolute() else Path(project) / path).resolve()
    return (Path(project) / load_config(project)["paths"][key]).resolve()


def pick_directory(project, key):
    """Native folder chooser; no GUI dependency is required for default/CLI installs."""
    title = "Choose " + key.replace("_", " ") + " folder inside this project"
    if sys.platform == "darwin":
        script = ('on run argv\ntry\nreturn POSIX path of (choose folder with prompt '
                  '(item 1 of argv) default location (POSIX file (item 2 of argv)))\n'
                  'on error number -128\nreturn ""\nend try\nend run')
        try:
            result = subprocess.run(["osascript", "-e", script, title, str(Path(project).resolve())],
                                    capture_output=True, text=True)
        except OSError as error:
            raise RuntimeError("folder picker unavailable; use --features-dir and --design-documents-dir") from error
        if result.returncode:
            raise RuntimeError("folder picker unavailable; use --features-dir and --design-documents-dir")
        selected = result.stdout.strip()
    else:
        try:
            import tkinter
            from tkinter import filedialog
            window = tkinter.Tk()
            try:
                window.withdraw()
                selected = filedialog.askdirectory(parent=window, title=title, initialdir=str(project), mustexist=True)
            finally:
                window.destroy()
        except (ImportError, RuntimeError) as error:
            raise RuntimeError("folder picker unavailable; use --features-dir and --design-documents-dir") from error
        except tkinter.TclError as error:
            raise RuntimeError("folder picker unavailable; use --features-dir and --design-documents-dir") from error
    if not selected:
        raise RuntimeError("documentation folder selection cancelled; no configuration written")
    try:
        relative = Path(selected).resolve().relative_to(Path(project).resolve()).as_posix()
    except ValueError as error:
        raise RuntimeError("choose a documentation folder inside the project") from error
    return validate_path(project, relative)


def prepare_install(args, project):
    """Select and validate before any installer writes. Return a pending config or None."""
    options = {"features": getattr(args, "features_dir", None),
               "design_documents": getattr(args, "design_documents_dir", None)}
    path = Path(project) / CONFIG_NAME
    if path.exists() or path.is_symlink():
        config = load_config(project)
        for key, value in options.items():
            if value is not None and validate_path(project, value) != config["paths"][key]:
                raise RuntimeError(CONFIG_NAME + " already defines paths." + key + "; edit the config and migrate files explicitly")
        return None
    paths = dict(DEFAULT_PATHS)
    for key, value in options.items():
        if value is not None:
            paths[key] = validate_path(project, value)
    interactive = not args.dry_run and sys.stdin.isatty() and not getattr(args, "defaults", False)
    for key in paths:
        if not interactive or options[key] is not None:
            continue
        print("Documentation target: " + key)
        print("  1. Keep default: " + paths[key])
        print("  2. Choose a folder using the directory picker")
        while True:
            try:
                answer = input("Choose 1 or 2 [1]: ").strip()
            except (EOFError, KeyboardInterrupt) as error:
                raise RuntimeError("documentation folder selection cancelled") from error
            if answer in ("", "1"):
                break
            if answer == "2":
                paths[key] = pick_directory(project, key)
                break
            print("Enter 1 or 2.")
    for value in paths.values():
        validate_path(project, value)
    return {"schema_version": 1, "paths": paths}


def write_install(config, project, dry_run, log):
    if config is None:
        return
    log.append(CONFIG_NAME + ": create with documentation paths " + json.dumps(config["paths"], sort_keys=True))
    if not dry_run:
        # Exclusive creation prevents a concurrent installer from overwriting another choice.
        try:
            with (Path(project) / CONFIG_NAME).open("x", encoding="utf-8") as handle:
                json.dump(config, handle, indent=2)
                handle.write("\n")
        except OSError as error:
            raise RuntimeError("cannot create " + CONFIG_NAME + ": " + str(error)) from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", help="project root; otherwise resolve the current working checkout")
    parser.add_argument("command", choices=("get",))
    parser.add_argument("key", choices=tuple(DEFAULT_PATHS))
    args = parser.parse_args()
    project = args.project or project_root.find_working_root(project_root.logical_cwd())
    if not project:
        parser.error("cannot find a project root; pass --project")
    try:
        print(resolve_path(project, args.key))
    except RuntimeError as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
