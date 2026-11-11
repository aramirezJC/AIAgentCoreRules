# Unity Tools

Core tooling, shared by every Unity host project. A host routes to these scripts from the
"Runnable Tools" section of its SystemIndex.

Executable tools an agent (or a person) can run against the Unity project instead of
reconstructing the same analysis by hand each time.

The bar for adding something here: it either **verifies** work, or it performs a
**structured analysis that would otherwise take many exploratory greps to assemble**.
A script that only wraps a single `grep` does not belong here — it costs a layer of
indirection and saves nothing.

## Naming

`{verb-or-noun}.py` — lowercase, hyphenated. Shared helpers are prefixed `_`.

Every script must:

- Run on stock `python3` with no third-party packages
- Find the project root itself by walking up for `ProjectSettings/ProjectVersion.txt`,
  and accept `--project` to override
- Print only what the caller needs to act on — these are run by agents with a limited
  context budget, so quiet-on-success is the default
- Exit non-zero on failure so it can be used in a hook or CI step
- Never write into `Assets/`, and be safe to run while the Unity editor is open

## Scripts

| Script | Purpose |
|---|---|
| `typecheck.py` | Compile assemblies with Unity's bundled Roslyn and report only errors |
| `codeindex.py` | SQLite index of every type and member declaration; relationship queries |
| `usages.py` | Map every use of a type, partitioned by which members each site calls |
| `unitysource.py` | Decompiled Unity engine source (UnityEngine.* / UnityEditor.*), cached per Unity version as it is asked for |
| `_unityproj.py` | Shared model of the generated `.csproj` files (not run directly) |
| `_csparse.py` | Declaration-level C# parser used by `codeindex.py` (not run directly) |

**Which one do I want?**

| Question | Tool |
|---|---|
| Does my change compile? | `typecheck.py` |
| What does this type look like / who implements it? | `codeindex.py` |
| Who *calls* this member? | `usages.py` |
| What does this *Unity engine* API really do? | `unitysource.py` |

`codeindex.py` knows declarations, not call sites. `usages.py` knows call sites, but
lexically. `typecheck.py` is the only one that is authoritative.

---

## typecheck.py

Verifies a change compiles without launching the Unity editor.

```bash
python3 typecheck.py                     # changed assemblies + everything referencing them
python3 typecheck.py Assembly-CSharp     # named assemblies + their dependents
python3 typecheck.py --all
python3 typecheck.py --changed --base develop
python3 typecheck.py --list              # show the plan, compile nothing
python3 typecheck.py --include-new       # also compile new .cs files not yet in a .csproj
python3 typecheck.py Assembly-CSharp-Editor --define USING_TOOLS   # code behind a define that is off
```

Full project check is roughly 7 seconds and a dozen lines of output.

Two behaviours worth knowing:

- **Dependents are checked automatically.** Changing an interface in a low-level package
  and only compiling that package proves nothing; the script pulls in every assembly
  that transitively references what you touched, and builds in topological order.
- **A failed dependency marks its dependents `skip`, not `ok`.** They would otherwise
  link against the stale DLL in `Library/ScriptAssemblies` and report a pass that means
  nothing. Silence is not success.

### Requirements and limits

- Needs the Unity install matching `ProjectVersion.txt`. Searched under
  `/Applications/Unity/Hub/Editor` and `~/Documents/UnityInstalls`; set `UNITY_PATH` to
  the `.app` otherwise.
- Reads the generated `.csproj` files. **If you add or delete a `.cs` file, let Unity
  refresh once first** — a new file that is not yet in a `.csproj` will not be compiled,
  and the script says so when it detects one. `--include-new` attaches such files (from
  the git changes) to the assembly Unity would put them in: nearest `.asmdef`, else the
  predefined assemblies. It only picks up files git reports as changed (`git diff` plus
  `ls-files --others --exclude-standard`): a new `.cs` file in a gitignored folder (such as
  `Assets/GitIgnoreAssets/`) is not compiled, so its types show as CS0246, until Unity
  regenerates the `.csproj` (focus the Editor once).
- Code inside `#if SYMBOL` is compiled out when the `.csproj` does not define `SYMBOL`,
  and the check still reports clean. Pass `--define SYMBOL` (repeatable) to include it.
- **Git worktrees** (background jobs, `.claude/worktrees/<name>`) hold only tracked files,
  so they have no `.csproj`, `Library/` or `GitIgnoredExternals/`. Run the script from
  inside the worktree, by the main checkout's absolute path, and **without `--project`**:
  `python3 <main checkout>/GitIgnoredExternals/AIAgentCoreRules/Tools/unity-tools/typecheck.py`.
  It detects the worktree, compiles the worktree's sources against the main checkout's
  `.csproj` files and `Library/`, and prints which checkout supplied what. Git-ignored
  sources (such as `Assets/GitIgnoreAssets`) come from the main checkout. Files deleted in
  the worktree are skipped. Files added in the worktree are attached automatically
  (`--include-new` is implied). An `.asmdef` added in the worktree is wired into
  `Assembly-CSharp` / `Assembly-CSharp-Editor` when it is `autoReferenced` and the main
  checkout has its `.csproj`. If the main checkout has no `.csproj` for it, its sources
  cannot be compiled: the script prints a warning naming it, and CS0246 errors for its
  types in other assemblies are false — let Unity refresh the main checkout on the branch.
  A `references` entry added to an existing `.asmdef` is not in the main checkout's
  `.csproj` either: CS0246/CS0234 for the newly referenced assembly's types in that
  assembly are false until Unity regenerates the project files (after landing). The
  script warns naming each `assembly -> reference` pair, in a worktree or the main checkout.
- `--project` pointing at a different checkout than the one you are in compiles **that
  checkout's** files and can report clean for edits it never saw. The script warns when
  this happens.
- Dependencies you did not ask to rebuild come from `Library/ScriptAssemblies`, so a
  stale `Library` only affects assemblies outside the requested set.
- This is a type check, not a build: no IL post-processing, no asset pipeline, no
  domain reload. It catches signature and reference breakage, which is what refactors
  get wrong. It will not catch a broken `[SerializeField]` wiring or a missing asset.

---

## codeindex.py

A SQLite index of every type and member declaration, so relationship questions can be
answered without reading files. The codebase is ~5,400 indexed files / ~7,300 types /
~71,000 members — roughly 24 MB of source, several times what fits in an agent context.

```bash
python3 codeindex.py build                    # ~8s cold, ~0.5s incremental
python3 codeindex.py implementers IEventManager
python3 codeindex.py subclasses Screen                        # transitive
python3 codeindex.py members DummyEventManager --kind method
python3 codeindex.py bases GemEventManager
python3 codeindex.py where IEventQuery
python3 codeindex.py types --assembly Assembly-CSharp --kind interface
python3 codeindex.py sql "SELECT name, COUNT(*) FROM base_ref GROUP BY name"
python3 codeindex.py schema                   # tables + example queries
```

`--json` on any query. The database lives at `Library/codeindex.sqlite` — gitignored,
and outside `Assets/` so Unity does not try to import it.

**Git worktrees** work without setup, like `typecheck.py`: run it from inside the worktree
without `--project`. It indexes the worktree's own sources, borrows the `.csproj` files from
the main checkout (printing `[worktree: ...]` on stderr), and keeps a separate database in the
worktree's `Library/`.

### Freshness

**Every query refreshes the index first if anything changed**, so it cannot answer from
stale data. That check is a cheap mtime/size comparison; SHA-1 is only computed for
files that look changed, because hashing 24 MB on every invocation to learn that nothing
moved is waste. `--no-auto-build` to inspect a snapshot deliberately.

Gotchas:
- `--no-auto-build` on a stale index exits with "Index is stale…" instead of serving the
  last build. For a read-only snapshot, run `sql` on a copy of the database, or drop the flag.
- `build --force` deletes and re-inserts every file's rows in one transaction, so
  `type.id` / `member.id` change across builds. Key anything persistent (URLs, caches) by
  name, not id.

This covers created, modified, and deleted files — including a file created seconds ago
that Unity has never seen. The `.csproj` files describe only what Unity compiles for the
*current* build target, and only as of the last refresh, so they are not sufficient on
their own. For anything they do not claim, the index reproduces Unity's own attribution
rule: **nearest ancestor `.asmdef` wins, otherwise the predefined assemblies**
(`Assembly-CSharp`, `-Editor` under an `Editor/` folder, `-firstpass` under `Plugins/`).

Those files are marked `in_csproj = 0`. They are indexed and queryable by default —
you want `codeindex.py where GoogleSignInIOS` to find iOS code — but `typecheck.py`
will never verify them, because Unity does not build them for this target. Pass
`--compiled-only` to any query to exclude them.

There is no rebuild command you need to remember. `codeindex.py build` exists, but
queries are correct without it.

### What it knows, and what it does not

Declarations only. It does **not** resolve names or index call sites.

`base_ref` stores the base type as a **simple name**, not a foreign key — resolving
`IEventManager` to a specific declaration needs namespace and `using` resolution, which
this parser cannot do correctly. Faking a foreign key would encode guesses as
certainties. Queries therefore match on simple name, which means two same-named types in
different namespaces will collide. That is why the recursive CTE carries a depth cap: a
name collision can otherwise produce a cycle that `UNION` alone will not terminate.

`#if` branches are **all** indexed and the condition is not recorded, so `DebugReset`
appears even though it is `#if !RC`. The index answers "what exists in source", not
"what exists in an RC build".

Member signatures are stored as the **raw source text**, not parsed into components.
Multi-line signatures, expression bodies, and generic constraints make full parsing
high-noise, and the raw line is what you actually want to read anyway.

The `sql` passthrough runs on a second connection opened `query_only`, so exploring
with raw SQL cannot corrupt the index.

---

## usages.py

Answers "who uses this type, and which of them call the members I want to move out?" —
the question behind any interface split.

```bash
python3 usages.py IEventManager
python3 usages.py IEventManager --members FetchEvents,FetchEvent,RefreshEventStatus
python3 usages.py IPrizeManager --assembly Assembly-CSharp --full
```

Output is three buckets: `DECLARES / IMPLEMENTS`, `CALLS <members>` (listed in full,
with line numbers), and everything else (summarised per assembly unless `--full`).

**The buckets are lexical, not semantic.** A file lands in `CALLS` if a member name
appears with a `(` anywhere in it — a local method with a colliding name will show up.
Use it to narrow a large surface down to the handful of files worth reading, then
confirm with `typecheck.py`, which is authoritative.

Only files belonging to a generated `.csproj` are searched, so results cover code that
actually compiles.

**Events never land in `CALLS`.** `CALLS` matches `Member(`; event members are used as
`Member +=` / `Member -=`. For an event, grep `\bMember\s*[+-]=` instead before reporting a zero.
A zero result is a claim too: state which query produced it and why it could have found a use.

---

## unitysource.py

Decompiled source of the Unity engine's managed modules (`UnityEngine.*`, `UnityEditor.*`) for
the Unity version in `ProjectVersion.txt`. For questions the project code cannot answer: what a
getter really returns, whether a value is copied or wraps native memory, which overloads exist.
It found the DT-20157 root cause (`MinMaxGradientBlittable.ToMinMaxGradient` →
`new Gradient(IntPtr)`, a non-owning view over native memory).

```bash
python3 $R/unitysource.py where MinMaxGradientBlittable           # which module declares it
python3 $R/unitysource.py show Gradient                           # outline: one line per member
python3 $R/unitysource.py show Gradient --member Gradient         # full bodies of the constructors
python3 $R/unitysource.py show ParticleSystem.MainModule --member startColor
python3 $R/unitysource.py show Gradient --full                    # whole type (capped by --max-lines)
python3 $R/unitysource.py module UnityEngine.UIModule             # whole module, for wide greps
python3 $R/unitysource.py grep "new Gradient\(" -C 2              # search everything cached so far
python3 $R/unitysource.py cached                                  # what has been pulled in
python3 $R/unitysource.py status                                  # version, paths, ilspycmd
```

### The cache grows as questions come up

Nothing is decompiled up front — unlike `codeindex.py`, there is no full pass.

| Step | What it caches | Cost |
|---|---|---|
| `where` / first `show` of a type | the type table of each module it had to list, stopping at the first module that declares it (modules named like the query first, then the core modules) | ~0.2 s per module; listing all 136 takes ~30 s and only happens for a name that does not exist |
| `show` | the decompiled top-level type (nested types come with their parent) | ~1 s once |
| `module` | the whole decompiled module | ~1 s (UIModule, 2.6k lines) to ~11 s (CoreModule, 176k lines) once |

Everything lives in `~/Library/Caches/UnityDecompiled/<version>/` (`$XDG_CACHE_HOME` or `~/.cache`
elsewhere; override with `UNITY_SOURCE_CACHE`), outside every repo. The engine DLLs only change
with the Unity version, so entries never go stale; upgrading Unity starts a new folder. `grep`
searches only what is cached — pull more in with `show` or `module`.

### Requirements and limits

- `ilspycmd` (`dotnet tool install -g ilspycmd`, run outside a Unity project folder — inside one,
  dotnet finds several project files and refuses) and a .NET runtime in `~/.dotnet`. The script
  sets `DOTNET_ROOT=~/.dotnet` itself; without it ilspycmd silently writes nothing.
- Finds the Editor under `/Applications/Unity/Hub/Editor/<version>/`; set `UNITY_PATH` to the
  `.app` otherwise.
- A name is ambiguous only among modules already listed. When a simple name might exist in
  several modules, run `where <Name> --all` once.
- **Managed side only.** Native behaviour (what a setter does in C++) is invisible here. Confirm
  on the real object in the Editor.

---

## A note on orphaned `.csproj` files

Unity leaves generated project files behind when an assembly is renamed or removed. This
project currently has ~26 such files dating to 2023–24, still listing sources that have
since moved. Both scripts detect them (under half their references resolve on disk) and
ignore them; `typecheck.py --verbose` lists which. They are harmless but they do shadow
live assemblies in a naive file-to-assembly lookup, which is why the detection exists.

A second kind is not detected: `.csproj` files Unity stopped regenerating (in this project 6
dated 2026-09-17 — Adjust, Disney.RainbowCore.Environment.Android/iOS,
Disney.RainbowCore.SignInWithGoogle.Android/iOS, JamCity.InboxSdk.Editor). Their hint paths
still resolve, so they count as live, but their ProjectReferences are not maintained. A check
that compares `.asmdef` references to `.csproj` must limit itself to `.asmdef` files changed
since the last sync, as `missing_asmdef_references` does.
