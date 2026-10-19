# new-session

Starts a fresh Claude Code session in a new terminal, with a first prompt. Used by `/new-session`.
macOS only (AppleScript).

```bash
python3 Tools/new-session/new_session.py --in terminal "/small-task MR-20261016-01 from <tickets file>"
python3 Tools/new-session/new_session.py --in rider --model sonnet "/resume-work GameProgressSave"
python3 Tools/new-session/new_session.py --in rider --dry-run "<prompt>"   # print, run nothing
```

## How it works

1. Writes a one-shot launcher, `~/.claude/new-session/<stamp>.sh`: `cd <project root>`, then
   `exec claude [--model M] '<prompt>'`. The launcher deletes itself when it starts. The prompt is
   never typed as keystrokes, so quoting and keyboard layout cannot change it.
2. Runs `bash <launcher>` in the chosen target:
   - **terminal:** a new Terminal.app window (`do script`).
   - **rider:** `open -a Rider <project root>` brings that project's window to the front. System
     Events then presses Escape (focus back to the editor, so the next shortcut opens the terminal
     instead of hiding it), the terminal shortcut, the new-tab shortcut, and types the command.

The project root is the main checkout of the current directory (`Tools/setup/project_root.py`),
so a call from a worktree still opens the session in the main checkout. Override with `--project`.

## Options

| Option | Default | Meaning |
|---|---|---|
| `--in terminal\|rider` | required | Where to open the session |
| `--model` | none | Passed to `claude --model` |
| `--project` | main checkout of the cwd | Directory the session starts in |
| `--terminal-keys` | `cmd+ctrl+1` | Rider: open the terminal tool window ("Visual Studio OSX" keymap; `alt+f12` in the default macOS keymap) |
| `--new-tab-keys` | `cmd+t` | Rider: new terminal tab |
| `--delay` | `0.8` | Rider: seconds between steps; raise it on a slow machine |
| `--dry-run` | off | Print the launcher and the AppleScript, run nothing |

## Permissions

macOS asks once per app:

- **Automation:** the app running the script may control Terminal.app or System Events.
- **Accessibility (rider only):** the app running the script may send keystrokes. That is Terminal.app
  when Claude runs there, or Rider when Claude runs in Rider's terminal. Without it the keystrokes
  are dropped silently and Rider just comes to the front.

On a permission error the script prints which setting to change, and the command to run by hand.
