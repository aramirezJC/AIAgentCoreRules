# Code Graph Tool

A small local server that shows the host project's **codeindex** database as a browsable graph,
and answers the same questions as JSON for the agent. It exists to cut down on greps: one request
returns a type's bases, derived types, members and `file:line`. It only reads the database; the
host's `codeindex.py` builds it.

Code: `Tools/code-graph/` (details and the full API in its `README.md`).

## Commands

| Command | What it does |
|---|---|
| `code-graph.sh start [--project DIR] [--db PATH] [--refresh-cmd "<cmd>"]` | Start the server, or reuse the running one, and print its URL |
| `code-graph.sh status` | Show the URL, database and refresh command, or `Stopped` |
| `code-graph.sh stop` | Stop the server |

The database defaults to `<project>/Library/codeindex.sqlite`, built by the core
[[16_UnityTools|`Tools/unity-tools/codeindex.py`]]. The host project's SystemIndex gives the exact
start command, including its refresh command.

## The page

- **Search** (`/` focuses it): types by name, exact matches first.
- **Tree**: assembly → namespace → type.
- **Graph**: the selected type's inheritance — bases above, derived types below. Click a node for
  its details; double-click to expand around it. Depth and direction are set in the corner.
  A dashed amber edge means the base's name is declared in more than one namespace; a dashed
  node is a type outside the indexed sources (Unity, .NET).
- **Details**: kind, namespace, assembly, `file:line` (click to copy), bases, derived types and
  a filterable member list.
- **Force refresh index**: shown when the server was started with `--refresh-cmd`. It runs that
  command (normally a forced codeindex build), shows progress, and reloads the page's data when
  it finishes. The page keeps working on the old index until the rebuild commits.

## For the agent

```bash
curl -s "$URL/api/type?name=IEventManager&members=0"   # bases, derived, location
curl -s "$URL/api/graph?name=Screen&direction=down&depth=1"
curl -s "$URL/api/search?q=GemEvent"
```

The server runs until stopped; it is not tied to a session.

## Tests

```bash
python3 -m unittest discover -s Tools/code-graph/tests -p 'test_*.py'
```
