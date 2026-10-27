# GameProgressSaveSlim — Pseudo-GDD (use-case driven)

> No source GDD exists. This document stands in for one: the problem, the design decisions it
> forces, and the use cases with their expected handling. Once approved it feeds the TDD sections
> and `GameProgressSaveSlim_UseCases.md`.
> Status: **DRAFT v0.1 — 2026-10-23** (local only, not yet published)
>
> Supersedes, for the first release, the [Technical Design Proposal: In Round Game Progress Save](https://socialgamingnetwork.jira.com/wiki/spaces/rainbowstar/pages/5001412774)
> (v0.5, "full resume"), which is on hold. Inputs: the slim-scope summary shared on 2026-10-22, the
> Joe Cho thread and the follow-up decision thread.
>
> Markers: ⚠️ **Design decision** = needs designer input · 🔧 **Engineering discussion** = needs
> engineering alignment · 📐 **TDD detail** = flagged now, designed in the TDD · ✅ **DECIDED** =
> settled in review.

---

## 1. Problem

When the app is killed mid-level (OS kill in the background, swipe-away, crash, device reboot) the
player loses the round. Today they also take a **loss**: the life was spent at level start and is
only refunded on a win, and several systems persist a "you lost" state at round start, on purpose,
so that killing the app cannot be used to dodge a loss (see §3.3).

The most common case is a short interruption: a phone call or a switch to another app, during
which the OS kills the backgrounded game. The player comes back, the level is gone, and so are
their life, win streak and Wishing Star. This is felt as a high-churn moment.

**Goal:** **rewind** an interrupted round. On the next launch the player lands on Home, at the same
level, **as if they had never started the round**: everything the round start charged, zeroed or
rolled is given back, and the run is not counted as a loss. The board is not restored, and nothing
collected during the round is kept. Rewinds are limited, so killing the app on purpose is not a
free way out of a loss.

**Non-goal:** putting the player back into the round (the full-resume proposal). That stays
possible later (§3.1), and is the long-term target for competitor parity.

---

## 2. What the codebase gives us today (survey findings, 2026-10-22 / 23)

| Area | Fact | Evidence |
|---|---|---|
| Soft exit | A short background does **not** reset the level: `AppPauseMessage(true)` pauses gameplay, the timer counts frame time only, and returning shows the pause screen with the board intact | `AppController.cs:275-288`, `StateGameplay.cs:814-826`, `Timer.cs:229` |
| Kill | "Came back and the level was reset" is the OS killing the backgrounded app; the next launch is a cold boot | — (nothing reacts to calls, audio interruptions or low memory: `EnvironmentManager.cs:463-470`) |
| Kill vs swipe | A swipe-away also pauses first: the game cannot tell it apart from an OS kill | `AppController.cs:275` |
| Round start order | `StatePreLevel.GoToGameplay`: `ConsumeLife()` → `PreRoundStartMessage`; `StateGameplay.InitGame` → `RoundStartMessage`; `GameplayController.StartLevelCoroutine` → `GameCreatedGameplayMessage` → `PostPreGameBoosts` | `StatePreLevel.cs:146-149`, `StateGameplay.cs:455-472`, `GameplayController.cs:247-270` |
| Try Again | `StateLevelFailed.TryAgain` charges a life and goes straight to gameplay **without** `PreRoundStartMessage` | `StateLevelFailed.cs:153-167` |
| Round-start charges | Eight systems charge, zero or roll state at round start and only give it back on a win (§3.3) | see §3.3 |
| Kill detection | `LevelTuningManager.activeLevelNumber` + `EnterHomeStateMessage.isStartup` already detects an interrupted round and dispatches `LevelInterruptedMessage` ("count as a loss"). Gaps: only at or above the tuning unlock level, not re-armed on Try Again, stores only a level number | `LevelTuningManager.cs:394-427` |
| Magic item | A kill on a magic-item spawn level leaves `isProcessingMagicItem` set; the next boot settles it as a loss and moves the spawn to a later level | `MagicItemCollector.cs:188-207,259`, `MagicItemCollectorRequirements.cs:142-146` |
| Persistence | StateV3 player data is local **and** server-synced; it is flushed on every `AppPauseMessage` | `TreasuresStateDataManager.cs:158-183` |
| Per-level data | `ILevelPlayerData` holds `level`, `attemptNum`, `autoEaseSeed`; `attemptNum` resets when the level changes | `LevelBlockManager.cs:96-104,958` |
| BI | A killed run is a `round_start` with no `round_end`; nothing is sent on the next launch | — |

---

## 3. Design questions

### 3.1 Approach — rewind vs resume

| | A. Rewind (this proposal) | B. Resume into the round (on hold) |
|---|---|---|
| Player lands on | Home, same level, as if the round never started | The same board, paused |
| In-round progress | Lost (pile, tray, timer, objectives, collected items) | Kept |
| What must be saved | One small record at round start: the values the round start is about to charge | The settled state of ~20 systems, continuously |
| Systems touched | Only those that charge or zero state at round start (~9) | Every system that holds round state (~20 bridges) |
| Boot flow | Unchanged | Jumps into gameplay; Home flow deferred |
| Exploit | Killing the app dodges a loss → needs a guard (§3.4) | None: the snapshot only moves forward |
| Cost | ~17–19 days (to be re-estimated in the TDD) | ~29 days |

> ✅ **DECIDED — A, rewind** (decision thread, after the 2026-10-22 sync).

- **Partial snapshot rejected.** Respawning a fresh pile from the items left on kill still needs
  the timer, tray, objectives, results and every event's in-round state; it costs about as much
  as full resume.
- **Upgrade path.** Rewind is not throw-away work: the per-system "give back" handling is what
  full resume needs anyway for the same systems (the original bridges for level block, HotStreak,
  streak leaderboard, Wishing Star, Lava Quest, level tuning). 📐 TDD detail: what carries over.

### 3.2 Return UX — boot to Home

- **Boot is unchanged.** Title → Home startup flow (conflict resolution, prize flows, offers) as
  today. The rewind is applied while player data loads, **before** any system reads the values it
  gives back, so Home already shows the restored life, streak and Wishing Star.
- **Same level.** The level number and level config are unchanged; the next Play starts the same
  level fresh.
- **Messaging.** ⚠️ **Design decision:** does the player see anything when a round was rewound
  (e.g. "Your level was interrupted, nothing was lost — 1 rewind left"), and when a kill is
  counted as a loss because the limit was reached? Without messaging the rewind is invisible,
  and the limit (§3.4) is a surprise the first time it bites.

### 3.3 Economy impact

Rule of thumb: **a rewind gives back what the round start took; what the player spent or earned
during the round stays as it is after a normal loss.**

| Resource | Today, at round start | Today, after a kill | On rewind | Hook |
|---|---|---|---|---|
| Life | Spent in `StatePreLevel.GoToGameplay` / `StateLevelFailed.TryAgain`; refunded on a win | Lost | **Refunded**, only if one was spent (none with unlimited lives) | Lives |
| HotStreak (win streak) | Saved value zeroed on `GameCreatedGameplayMessage` ("prevent force-closing from saving the streak") | Lost | **Restored** to its pre-round value | HotStreak |
| Wishing Star (Super Light Ball) | Active ball: `_winsProgress = 0` + save on `PreRoundStartMessage` | Lost | **Restored** | Wishing Star |
| Level tuning | `activeLevelNumber` armed; next boot sends `LevelInterruptedMessage` → loss strike | A difficulty-tuning loss | **Not counted**: no `LevelInterruptedMessage` | Level tuning |
| Attempt number | `attemptNum++` (feeds the First Try mission and auto-easing) | Counts as a new attempt | **Rolled back**: the retry is the same attempt | Level block |
| Pre-level boosts | Decremented in `PostPreGameBoosts`; never refunded, win or lose | Lost | **Refunded** | Pre-level boosts |
| Magic item spawn | `isProcessingMagicItem` set on a spawn level | Settled as a loss: no magic item on the retry, charge restarts | **Given back**: the retry is still a spawn level | Magic item |
| Streak Leaderboard multiplier | `ResetMultiplierLevel` + save on `RoundStartMessage` | Lost | **Restored**, if the event is still running (C1) | Streak Leaderboard |
| Lava Quest | State `RoundStarted` + cooldown on `RoundStartMessage`; next boot moves it to cooldown | Quest goes into cooldown | **Stays active**, if the event is still running (C1) | Lava Quest |
| In-level boosts (Magnet, Undo, Fan, Freeze) | Charged on use | Stay spent | Stay spent (same as a loss) | — |
| Coins: extenders, in-level booster purchases | Charged on purchase | Stay spent | Stay spent (same as a loss) | — |
| Collectibles, gacha currency, event pieces, collected magic item | Held in memory, granted only on a win | Lost | Lost (same as a loss) | — |
| Jetpack, Race, BattlePass, CardAlbum, MissionCenter, ProgressionEvent | Nothing charged at round start | Nothing lost beyond in-round collections | Nothing to do | — |

> ✅ **DECIDED — every row marked "Hook" ships in the first release.** Jean-François: "The
> non-interference of the forgiveness must apply across the board, else it will create confusion.
> These events happen all the time." No mandatory / stretch split.

- **Attempt number.** Rolling it back follows from "as if they had never started the round". It
  also rolls back the auto-easing bump a new attempt would give. ✅ follows from §3.1.
- **Magic item.** The rolled item is never saved today: every boot rolls it again, so the retry may
  offer a **different** item than the killed round did. This is today's behaviour and is accepted
  unless design objects. ⚠️ **Design decision** (confirm).
- **Coverage.** This table is the starting inventory. The magic item row was missed in the first
  slim estimate, which shows a hand-kept list drifts: an inventory sweep for other round-start
  writers runs before release (E1). 📐 TDD detail

### 3.4 Exploit control — the rewind limit

Today's round-start charges are deliberate anti-force-quit protection. Rewinding a killed round
turns that protection off, and the game cannot tell a phone call from a player swiping away a
level they are about to lose (§2).

> ✅ **DECIDED — rewinds are limited.** Proposed (Jean-François): **2 per level**; the third kill on
> the same level counts as a loss, exactly as today.

- **What happens past the limit:** today's behaviour. Nothing is given back, the level tuning loss
  fires, and the record is cleared.
- ⚠️ **Design decision — limit rules:** the number (2), whether it is per level, whether it
  resets when the level is won, and whether it **refreshes over time** (Jane Reed / Chris Burris:
  players with real interruptions will hit a permanent limit too). The number should be a remote
  setting either way. 📐 TDD detail: where the counter lives.
- ⚠️ **Design decision — kill on the lose extender:** when the lose-extender popup is open the loss
  is already decided. Options: (a) always counted as a loss, regardless of the limit; (b) treated
  like any other kill and uses up a rewind. (a) closes the most obvious exploit at almost no cost.
- **Kill during the post-game flow** is not a rewind: the level is over (A6).

### 3.5 Extensibility — systems that charge at round start

The full proposal needed a contract for every system holding round state. Rewind only needs one
for systems that **charge, zero or roll** persisted state at round start: a short, slowly changing
list (§3.3). Names and shape are provisional; the architecture is reviewed in the TDD.

- **One record.** A small "round in progress" record in StateV3 player data: the level, whether a
  life was spent, and the pre-round value of each hooked system. It is written in **one step,
  before anything is charged** (before the life in `StatePreLevel` and Try Again), so a kill at any
  later point (even before the systems' own saves finish) still has the right values.
- **One rewind step at boot.** While player data loads, a service decides **rewind** or **count as
  loss** (limit, lose extender, feature switch, minimum level), then each hook writes its value
  back before its system reads it. Event hooks apply when their event loads, and skip if the event
  has ended.
- **Clear at game over.** The record is cleared when the round's result is committed (win, loss or
  quit), before rewards are applied.
- **Making it stick** (strongest first, 📐 TDD detail):
  1. Test time: a test per hook that charges, kills (simulated) and rewinds.
  2. Process: a rule in `MagicMatchProjectRules` and the `RoundLifecycle` system entry: "a new
     feature that charges or zeroes state at round start must add a rewind hook". `/audit` flags
     new round-start writes.
- **Feature switch:** a remote setting turns rewind on/off and sets the minimum level (**level 5**,
  temporary), as in the full proposal (A7).

---

## 4. Use cases

Format: **Scenario → Expected handling.** The **Orig.** column points to the full-resume proposal's
use case this one replaces, where there is one.

### A. Recording the round

| # | Scenario | Expected handling | Orig. |
|---|---|---|---|
| A1 | Player starts a level from the pre-level screen | Before the life is charged, the record is written with the level and every hooked system's pre-round value, and saved. | A1 / A2 |
| A2 | Player taps Try Again after a loss | Same as A1. Try Again skips `PreRoundStartMessage`, so the record is written in `TryAgain` itself. | B7 |
| A3 | Player backgrounds the app mid-level (call, app switch) and comes back before the OS kills it | Nothing changes: pause screen, board intact, as today. No rewind is involved. | A1 |
| A4 | App killed right after round start, before the systems' own saves finish (HotStreak and leaderboard saves are fire-and-forget) | The record already holds the pre-round values, written before anything was charged, so the rewind is still correct. | — |
| A5 | Level won, lost or quit normally | Record cleared when the result is committed, before rewards. Normal win / loss as today. | A10 / A11 |
| A6 | Kill during the win / post-game flow (rewards being granted) | The record was already cleared at game over: no rewind, rewards follow the existing prize flow rules. 📐 Discovery check: no gap between game over and clearing the record. | A8 |
| A7 | Kill on an early level, below the minimum level (5) | No record is written; today's behaviour. The setting also works as the off switch. | A9 |
| A8 | Level started with unlimited lives | The record notes that no life was spent. | B5 |

### B. Rewinding

| # | Scenario | Expected handling | Orig. |
|---|---|---|---|
| B1 | App killed mid-round (OS kill, swipe-away, crash, reboot); the player relaunches | Boot to Home as today, same level. Before any system reads its data, everything in §3.3 marked "Hook" is given back; the run is not counted as a loss (no `LevelInterruptedMessage`); the rewind is counted toward the limit; the record is cleared. | A2 / A3 / B1 |
| B2 | Kill during the intro, after pre-level boosts were spent | Same as B1; the pre-level boosts are refunded. | A5 |
| B3 | Kill while the in-level booster shop is open | Same as B1. The purchase was atomic and stays; coins spent stay spent. | A7 |
| B4 | Kill while the lose-extender popup is open | ⚠️ **Design decision** (§3.4): always a loss, or a normal rewind. | A6 |
| B5 | Kill when the player has used up their rewinds on this level | Counted as a loss, as today: nothing given back, the level tuning loss fires, the record is cleared. ⚠️ Limit rules (§3.4). | — |
| B6 | Kill on a magic-item spawn level | Same as B1: the spawn is given back and the retry spawns a magic item again (possibly a different one, §3.3 ⚠️). | — |
| B7 | Kill again on the retry | Same as B1; it uses another rewind. | B7 |
| B8 | Killed with unlimited lives active; they expire before the relaunch | Same as B1, but no life is refunded, because none was spent. | B5 |
| B9 | Player relaunches after a rewind | ⚠️ **Design decision** (§3.2): message or not; also when B5 applies. | — |

### C. Events and invalidation

| # | Scenario | Expected handling | Orig. |
|---|---|---|---|
| C1 | The event behind a given-back value ended between the kill and the relaunch (Streak Leaderboard, Lava Quest) | That one value is not given back; logged. Everything else is. Events never block a rewind. | C5 |
| C2 | Record unreadable or corrupt | No rewind: today's behaviour. Error + Breadcrumb. | C3 |
| C3 | Player logs into a different account on the device | The record is that player's data; a different player never sees it. | C7 |
| C4 | Relaunch is days later | No expiry: the rewind applies on the next boot, whenever that is. | C8 |
| C5 | App updated between the kill and the relaunch | The record holds no board, so nothing goes stale. A hook added in the new version finds no value and gives nothing back. 📐 TDD detail | C1 |
| C6 | Level config or block changed between the kill and the relaunch | Nothing to validate: the record restores values, not a level. The player plays whatever the level is now. | C2 / C4 |

### D. Multi-device / server

| # | Scenario | Expected handling | Orig. |
|---|---|---|---|
| D1 | App reinstalled, or the player continues on another device | The record lives in StateV3 next to the values it restores, so it travels with them; the rewind applies on the boot that loads it. | C9 / D1 |
| D2 | Account conflict (local vs server) | Conflict resolution runs as today. Whichever copy the player picks carries its own record; if a reload follows, the rewind applies then. 🔧 confirm at Discovery. | C6 |
| D3 | Offline at the kill or the relaunch | Works: local StateV3 data is used and syncs when back online. | D3 |

### E. Extensibility, debug and support

| # | Scenario | Expected handling | Orig. |
|---|---|---|---|
| E1 | A new feature charges, zeroes or rolls state at round start | Must add a rewind hook (§3.5). An inventory sweep runs before release. | E1 |
| E2 | QA needs to test a rewind | Debug command (`#if !RC`): "simulate killed round" (write the record and send the player to Home as after a relaunch), and reset the rewind count. | E3 |
| E3 | Data needs to tell forgiven runs from real losses | BI event on the boot that rewinds (and on a kill counted as a loss), joined to the killed run's `round_start`. 📐 TDD detail | — |
| E4 | CS ticket: "lost my level / life / streak" | Existing CS gifting (lives, boosters, currency). No new CS flow. | E4 |

---

## 5. Open items for team review

**✅ Decided in review**
- Rewind, not resume: boot to Home, same level, as if the round never started (§3.1).
- Every round-start charge is given back in the first release; no mandatory / stretch split (§3.3).
- Board and in-round collections are not restored; in-round spends stay spent (§3.3).
- Rewinds are limited (§3.4).
- Off below a configurable level (5, temporary), through a remote setting that is also the off
  switch (A7).
- Events never block a rewind (C1).

**⚠️ Design decisions** (designers — owners to be set at the kickoff)
1. §3.4: limit rules — number (2 proposed), per level, reset on win, refresh over time.
2. §3.4 / B4: kill on the lose extender — always a loss, or a normal rewind.
3. §3.2 / B9: player messaging on a rewound boot and on a kill counted as a loss.
4. §3.3 / B6: the magic item on the retry may be a different item — accept?

**🔧 Engineering discussions**
1. Boot order: every hook writes back before its system reads the value (HotStreak, Wishing Star,
   magic item, leaderboard load) (A4, B1).
2. The record's save at round start must reach disk before the first charge (A1, A4).
3. D2: interaction with account conflict resolution.

**📐 Flagged for the TDD**
- Record shape, the rewind service, and the hook contract (§3.5).
- Where the rewind counter lives — after the limit rules are decided (§3.4).
- What carries over to a later full resume (§3.1).
- Inventory sweep for other round-start writers (§3.3, E1).
- BI event (E3) and the debug commands (E2).
- No gap between game over and clearing the record (A6).
