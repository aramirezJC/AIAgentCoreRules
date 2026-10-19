#!/usr/bin/env python3
"""Start a fresh Claude Code session in a new terminal — Terminal.app or Rider's terminal (macOS).

    python3 new_session.py --in terminal "/small-task MR-20261016-01 from <tickets file>"
    python3 new_session.py --in rider --model sonnet "/resume-work GameProgressSave"
    python3 new_session.py --in rider --dry-run "<prompt>"      # print, run nothing

The prompt is never typed as keystrokes. It goes into a one-shot launcher script
(~/.claude/new-session/<stamp>.sh: cd to the project root, exec claude), and each target only runs
`bash <launcher>`. The launcher deletes itself when it starts.

Targets:
    terminal  a new Terminal.app window (AppleScript `do script`).
    rider     `open -a Rider <project>` to bring that project's window forward, then UI scripting:
              Escape (focus back to the editor, so the next shortcut opens rather than hides the
              terminal), the terminal tool window shortcut, the new-tab shortcut, then types the
              command. Shortcuts default to the "Visual Studio OSX" keymap; change them with
              --terminal-keys / --new-tab-keys.

Permissions (one-time macOS prompts): Automation for Terminal.app / System Events, and for rider,
Accessibility for the app that runs this script (Terminal.app, or Rider when Claude runs inside it).
Without Accessibility the keystrokes are dropped silently.
"""

import argparse
import os
import shlex
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "setup"))
from project_root import find_project_root, logical_cwd  # noqa: E402

LAUNCH_DIR = os.path.expanduser("~/.claude/new-session")
RIDER_TERMINAL_KEYS = "cmd+ctrl+1"   # ActivateTerminalToolWindow, "Visual Studio OSX" keymap
RIDER_NEW_TAB_KEYS = "cmd+t"         # Terminal.NewTab, every Mac keymap
MODIFIERS = {"cmd": "command down", "ctrl": "control down", "alt": "option down",
             "opt": "option down", "shift": "shift down"}
PERMISSION_HINTS = {
    "-1743": "Automation is not allowed: System Settings → Privacy & Security → Automation.",
    "-1719": "Accessibility is not allowed: System Settings → Privacy & Security → Accessibility.",
    "1002": "Keystrokes are not allowed: System Settings → Privacy & Security → Accessibility.",
}


def write_launcher(project, prompt, model):
    """Path of a one-shot script that cds to the project and execs claude with the prompt."""
    command = ["claude"] + (["--model", model] if model else []) + [prompt]
    os.makedirs(LAUNCH_DIR, exist_ok=True)
    path = os.path.join(LAUNCH_DIR, time.strftime("%Y%m%d-%H%M%S") + "-%d.sh" % os.getpid())
    with open(path, "w") as handle:
        handle.write("#!/bin/bash\nrm -f \"$0\"\ncd %s || exit 1\nexec %s\n"
                     % (shlex.quote(project), " ".join(shlex.quote(part) for part in command)))
    os.chmod(path, 0o700)
    return path


def applescript_string(value):
    return '"%s"' % value.replace("\\", "\\\\").replace('"', '\\"')


def keystroke(keys):
    """'cmd+ctrl+1' → AppleScript `keystroke "1" using {command down, control down}`."""
    *mods, key = keys.lower().split("+")
    unknown = [m for m in mods if m not in MODIFIERS]
    if unknown or not key:
        sys.exit("Bad shortcut %r: use modifiers %s plus one key, e.g. cmd+ctrl+1" % (keys, "/".join(MODIFIERS)))
    using = " using {%s}" % ", ".join(MODIFIERS[m] for m in mods) if mods else ""
    return "keystroke %s%s" % (applescript_string(key), using)


def terminal_script(run):
    return 'tell application "Terminal"\n  activate\n  do script %s\nend tell' % applescript_string(run)


def rider_script(run, terminal_keys, new_tab_keys, delay):
    return "\n".join([
        'tell application "System Events"',
        "  key code 53",                          # Escape: focus to the editor
        "  delay 0.3",
        "  " + keystroke(terminal_keys),
        "  delay %.1f" % delay,
        "  " + keystroke(new_tab_keys),
        "  delay %.1f" % (delay * 2),             # the new shell needs longer than the tab
        "  keystroke %s" % applescript_string(run),
        "  key code 36",                          # Return
        "end tell",
    ])


def osascript(script):
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode != 0:
        error = result.stderr.strip()
        hint = next((text for code, text in PERMISSION_HINTS.items() if code in error), "")
        sys.exit("osascript failed: %s%s" % (error, "\n" + hint if hint else ""))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("prompt", help="first message for the new session, e.g. a slash command")
    parser.add_argument("--in", dest="target", choices=["terminal", "rider"], required=True)
    parser.add_argument("--model", help="passed to claude --model")
    parser.add_argument("--project", help="project root (default: the main checkout of the cwd)")
    parser.add_argument("--terminal-keys", default=RIDER_TERMINAL_KEYS, help="rider: open the terminal tool window")
    parser.add_argument("--new-tab-keys", default=RIDER_NEW_TAB_KEYS, help="rider: new terminal tab")
    parser.add_argument("--delay", type=float, default=0.8, help="rider: seconds between steps (default 0.8)")
    parser.add_argument("--dry-run", action="store_true", help="print the launcher and AppleScript, run nothing")
    args = parser.parse_args()

    if sys.platform != "darwin":
        sys.exit("new_session.py drives Terminal.app and Rider through AppleScript: macOS only.")
    project = os.path.abspath(args.project) if args.project else find_project_root(logical_cwd())
    if not project:
        sys.exit("No project root found from %s: pass --project." % logical_cwd())
    keystroke(args.terminal_keys), keystroke(args.new_tab_keys)   # bad shortcuts exit before any file is written

    launcher = write_launcher(project, args.prompt, args.model)
    run = "bash " + shlex.quote(launcher)
    if args.target == "terminal":
        steps = [terminal_script(run)]
    else:
        steps = [rider_script(run, args.terminal_keys, args.new_tab_keys, args.delay)]

    if args.dry_run:
        with open(launcher) as handle:
            print("launcher %s:\n%s" % (launcher, handle.read()))
        os.remove(launcher)
        if args.target == "rider":
            print("open -a Rider %s\n" % shlex.quote(project))
        print("osascript:\n%s" % steps[0])
        return

    if args.target == "rider":
        subprocess.run(["open", "-a", "Rider", project], check=True)
        time.sleep(args.delay * 2)                  # let the project window come to the front
    osascript(steps[0])
    print("Opened a new %s session in %s. If nothing ran, run it by hand: %s"
          % ("Terminal.app" if args.target == "terminal" else "Rider terminal", project, run))


if __name__ == "__main__":
    main()
