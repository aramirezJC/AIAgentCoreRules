---
name: new-session
description: Open a fresh Claude Code session in a new terminal - Terminal.app or Rider's terminal, the engineer's choice - with a first prompt such as /small-task, /resume-work or /bug-fix. Use when the engineer runs /new-session, or accepts a suggestion to continue some work in a fresh session (a ticket, a lane change, a large or idle context). macOS only.
argument-hint: "<prompt> [--in terminal|rider] [--model <model>]"
---

# New Session

Paths are relative to the AIAgentCoreRules root (the parent of the `Rules/` folder that holds
MetaRouter.md). Does not change this session's lane: starting another session is not work in this one.

```bash
python3 Tools/new-session/new_session.py --in <terminal|rider> [--model <model>] "<prompt>"
python3 Tools/new-session/new_session.py --in rider --dry-run "<prompt>"   # print only
```

```yaml
steps:
  - "Parse $ARGUMENTS: the prompt is everything except --in <target> and --model <model>. No prompt → ask for it (offer the command this session last suggested, if any)."
  - "No --in → ask with AskUserQuestion, one question, header 'Open in': Terminal (a new Terminal.app window) · Rider (a new tab in Rider's terminal, in this project's window). Never pick for the engineer."
  - "The prompt names a file the new session must read (a tickets file, a handoff note) → check it exists in the main checkout first. A file still in $CLAUDE_JOB_DIR/tmp is invisible to the new session: say so and give the cp command instead of launching."
  - "Run the script from the host project (it resolves the main checkout itself). Pass the prompt as one quoted argument."
  - "Report in one line: 'the script sent the keystrokes for <target> with <prompt>; confirm it opened'. Never say it opened: the script cannot see whether the keystrokes landed. The new session is independent: nothing it does reports back here."
  - "osascript failed → relay the script's permission hint verbatim (Automation or Accessibility, System Settings → Privacy & Security) and the by-hand command it printed. Do not retry until the engineer has granted it."
  - "Rider opened but nothing ran → the keystrokes were dropped (Accessibility) or the keymap differs: rerun with --terminal-keys / --new-tab-keys (e.g. alt+f12 for the default macOS keymap) or a larger --delay."
```

The Rider path drives the IDE with keystrokes: keep hands off the keyboard for the ~3 seconds it
takes. Shortcut defaults are the "Visual Studio OSX" keymap: terminal ⌘⌃1, new tab ⌘T.
