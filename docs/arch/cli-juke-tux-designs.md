# Juke CLI — Terminal UX Design

**Companion to:** `docs/arch/cli-juke-terminal-architecture.md`
**Date:** 2026-03-06
**Status:** Phase 0

---

## Design Philosophy

- **Keyboard is the only input.** No mouse. Every action has a keystroke. Power
  users don't reach for the trackpad.
- **Spatial, not modal.** The screen is divided into panes that are always
  visible. Focus moves between them (`h`/`l` or `Tab`). Overlays (search, help,
  command palette) are the only modals, and they dismiss on `Esc`.
- **Playback is ambient.** The bottom bar is always there, always live. You
  never lose track of what's playing, no matter what pane you're in.
- **Dense but not cramped.** Terminal real estate is precious. Use it — but
  leave one blank line between logical groups so eyes can rest.
- **Vim vocabulary by default.** `j`/`k`/`h`/`l` move, `/` searches, `:` opens
  the command palette, `g`/`G` jump to top/bottom, `?` shows help. Users who
  know vim are instantly productive. Everyone else reads the `?` overlay once.
- **Degrade gracefully.** Truecolor → 256 → 16 → mono. Unicode box-drawing →
  ASCII `|`/`-`/`+` if the terminal lies about its capabilities.

---

## Layout Anatomy

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ HEADER — logo, username, transport indicator (ws/poll), clock                │ 1 row
├──────┬───────────────────────────────────────────────────────┬───────────────┤
│      │                                                       │               │
│ NAV  │                    CONTENT                            │  NOW PLAYING  │
│      │                                                       │  + FACTS      │ N rows
│ left │   center pane — changes based on nav selection        │  + RECS       │ (flex)
│ rail │                                                       │               │
│      │                                                       │  right side   │
│      │                                                       │               │
├──────┴───────────────────────────────────────────────────────┴───────────────┤
│ PLAYBACK BAR — prev / play-pause / next / seek / track / artist / progress   │ 3 rows
└──────────────────────────────────────────────────────────────────────────────┘
```

Column widths: nav `16ch` fixed, sidebar `32ch` fixed, content takes the rest.
Minimum usable terminal: `100×28`. Below that, sidebar collapses first, then nav.

---

## Main View — Library Selected

```
┌─ juke ───────────────────────────────────────────── melodyqueen · ws · 14:27 ┐
├──────────────┬───────────────────────────────────────────────┬───────────────┤
│              │                                               │ NOW PLAYING   │
│  ▶ Library   │  Search the catalog                           │               │
│    Messages  │                                               │  So What      │
│    Generate  │  Press / to search for genres, artists,       │  Miles Davis  │
│              │  albums, or tracks.                           │  Kind of Blue │
│  ──────────  │                                               │  1959         │
│              │  Recent                                       │               │
│  RECENT      │  ────────────────────────────────────────     │  ███████░░░░  │
│              │  jazz                           3 min ago     │  06:14 / 09:22│
│  jazz        │  miles davis                   12 min ago     │               │
│  miles da…   │  kind of blue                       1h ago    │ ───────────── │
│  bossa no…   │                                               │               │
│              │                                               │ FUN FACT      │
│              │                                               │               │
│              │                                               │ Recorded in   │
│              │                                               │ two sessions  │
│              │                                               │ with almost   │
│              │                                               │ no rehearsal. │
│              │                                               │ Most of the   │
│              │                                               │ band saw the  │
│              │                                               │ charts for    │
│              │                                               │ the first     │
│              │                                               │ time in the   │
│              │                                               │ studio.       │
│              │                                               │          [f]  │
│              │                                               │               │
├──────────────┴───────────────────────────────────────────────┴───────────────┤
│                                                                              │
│  ◀◀ [p]     ▶ [space]     ▶▶ [n]        So What · Miles Davis · Kind of Blue │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━░░░░░░░░░░░░░░░  06:14 / 09:22  │
│                                                                              │
└─────────────────────────────────────────────────────────── ? for help ───────┘
```

**Focus behavior:** the content pane has focus by default. `h` moves focus to
nav, `l` moves to sidebar. Whichever pane is focused gets a brighter border
(lipgloss `BorderForeground`).

**Transport indicator** (`ws` / `poll` in header): subtle, one word, dimmed.
Power users notice; casual users don't care.

---

## Search Overlay

Triggered by `/` from anywhere. Floats over the content pane; nav and sidebar
stay visible but dimmed (lipgloss `Faint`).

```
┌─ juke ───────────────────────────────────────────── melodyqueen · ws · 14:27 ┐
├──────────────┬───────────────────────────────────────────────┬───────────────┤
│░░░░░░░░░░░░░░│                                               │░░░░░░░░░░░░░░░│
│░░▶ Library░░░│  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓    │░NOW PLAYING░░░│
│░░░░Messages░░│  ┃ / jazz█                               ┃    │░░░░░░░░░░░░░░░│
│░░░░Generate░░│  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛    │░░So What░░░░░░│
│░░░░░░░░░░░░░░│                                               │░░Miles Davis░░│
│░░──────────░░│  [g]enres  [a]rtists  [A]lbums  [t]racks      │░░░░░░░░░░░░░░░│
│░░░░░░░░░░░░░░│   ●          ●          ●         ●           │░░░░░░░░░░░░░░░│
│░░RECENT░░░░░░│                                               │░░░░░░░░░░░░░░░│
│░░░░░░░░░░░░░░│  GENRES ──────────────────────────── 3        │░░░░░░░░░░░░░░░│
│░░░░░░░░░░░░░░│  ▸ Jazz                                       │░░░░░░░░░░░░░░░│
│░░░░░░░░░░░░░░│    Smooth Jazz                                │░░░░░░░░░░░░░░░│
│░░░░░░░░░░░░░░│    Latin Jazz                                 │░░░░░░░░░░░░░░░│
│░░░░░░░░░░░░░░│                                               │░░░░░░░░░░░░░░░│
│░░░░░░░░░░░░░░│  ARTISTS ────────────────────────── 127       │░░░░░░░░░░░░░░░│
│░░░░░░░░░░░░░░│    Miles Davis              Jazz, Bebop       │░░░░░░░░░░░░░░░│
│░░░░░░░░░░░░░░│    John Coltrane            Jazz, Avant-Garde │░░░░░░░░░░░░░░░│
│░░░░░░░░░░░░░░│    Herbie Hancock           Jazz Fusion       │░░░░░░░░░░░░░░░│
│░░░░░░░░░░░░░░│                             … 124 more  [Tab] │░░░░░░░░░░░░░░░│
│░░░░░░░░░░░░░░│                                               │░░░░░░░░░░░░░░░│
│░░░░░░░░░░░░░░│  ALBUMS ─────────────────────────── 584       │░░░░░░░░░░░░░░░│
│░░░░░░░░░░░░░░│    Kind of Blue             Miles Davis  1959 │░░░░░░░░░░░░░░░│
│░░░░░░░░░░░░░░│    A Love Supreme           John Coltrane 1965│░░░░░░░░░░░░░░░│
│░░░░░░░░░░░░░░│                             … 582 more  [Tab] │░░░░░░░░░░░░░░░│
│░░░░░░░░░░░░░░│                                               │░░░░░░░░░░░░░░░│
│░░░░░░░░░░░░░░│                  Esc cancel · Enter open      │░░░░░░░░░░░░░░░│
├──────────────┴───────────────────────────────────────────────┴───────────────┤
│  ◀◀     ▶     ▶▶        So What · Miles Davis · Kind of Blue                 │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━░░░░░░░░░░░░░░░  06:14 / 09:22  │
└──────────────────────────────────────────────────────────────────────────────┘
```

- Live filtering: results update as you type (daemon caches, so it's fast).
- `j`/`k` move selection within a section; `Tab` jumps to the next section.
- `g`/`a`/`A`/`t` toggle section filters (mnemonic, lowercase-first).
- `Enter` opens the selected item in the content pane and dismisses the overlay.
- `Esc` dismisses without selection.
- `▸` marks the current selection. Section headers show result counts.

---

## Album Detail (Content Pane)

After `Enter` on an album. Breadcrumb shows the navigation stack (mirrors the
web catalog's breadcrumb model, capped at 10 per
`CATALOG_REDESIGN_ARCHITECTURE.md` decision #9).

```
│  ‹ jazz › Miles Davis › Kind of Blue                              [Bksp] back│
│                                                                              │
│  Kind of Blue                                                                │
│  Miles Davis · 1959 · 5 tracks · 45:44                                       │
│                                                                              │
│  The best-selling jazz record of all time. Recorded in two sessions,         │
│  the album's modal approach — building on scales rather than chord           │
│  changes — redefined what jazz could be.                                     │
│                                                                              │
│  TRACKS ─────────────────────────────────────────────────────────────        │
│                                                                              │
│  ▸ 1  So What                                              9:22    ♪         │
│    2  Freddie Freeloader                                   9:46              │
│    3  Blue in Green                                        5:37              │
│    4  All Blues                                           11:33              │
│    5  Flamenco Sketches                                    9:26              │
│                                                                              │
│  RELATED ─────────────────────────────────────────── via recommender ──      │
│                                                                              │
│    Sketches of Spain         Miles Davis            1960                     │
│    A Love Supreme            John Coltrane          1965                     │
│    Mingus Ah Um              Charles Mingus         1959                     │
│                                                                              │
│                                          Enter play · a queue album · r recs │
```

- `♪` marks the currently playing track.
- `Enter` on a track: IPC `playback.play` with `context_uri` = album and
  `offset_uri` = track (same context-aware play model the web uses —
  see `tasks/web-playback-next-track.md`).
- `a`: play the whole album from track 1.
- `r`: seed recommendations from this album — swaps content pane to recs view.
- `Backspace`: pop the breadcrumb stack.

---

## Now Playing Sidebar — Recommendations Mode

The right sidebar toggles between **Facts** and **Flows Into** with `f` / `r`.

```
│ NOW PLAYING   │
│               │
│  So What      │
│  Miles Davis  │
│  Kind of Blue │
│  1959         │
│               │
│  ███████░░░░  │
│  06:14 / 09:22│
│               │
│ ───────────── │
│               │
│ FLOWS INTO    │
│               │
│ ▸ Freddie     │
│   Freeloader  │
│   Miles Davis │
│               │
│   All Blues   │
│   Miles Davis │
│               │
│   Impressions │
│   J. Coltrane │
│               │
│   Footprints  │
│   W. Shorter  │
│               │
│ Enter queue   │
│ r refresh     │
│          [f]  │
```

Seeded from the currently playing track via `GET /api/v1/recommendations/`.
`Enter` queues the selected rec. `r` re-rolls. `[f]` in the corner reminds
you how to flip back to Facts mode.

---

## Messages View

Nav → `Messages`. Content pane splits into conversation list (left third) and
thread (right two-thirds).

```
│  CONVERSATIONS         │  @grooveking                                        │
│  ─────────────         │  ─────────────────────────────────────────────────  │
│                        │                                                     │
│  ▸ grooveking    2m  ● │                            you gotta hear this      │
│    bassline99    1h    │                            mingus record       2:14 │
│    vinyl_nerd    3d    │                                                     │
│                        │  which one                                    2:14  │
│                        │                                                     │
│                        │                            mingus ah um             │
│                        │                            the opener is wild  2:15 │
│                        │                                                     │
│                        │  ▸ Better Git It in Your Soul                       │
│                        │    Charles Mingus · Mingus Ah Um · 1959             │
│                        │    [Enter to play]                            2:15  │
│                        │                                                     │
│                        │  oh damn ok                                   2:17  │
│                        │                                                     │
│                        │  ─────────────────────────────────────────────────  │
│                        │  ┃ type a message…                              ┃   │
│                        │  ┃                                              ┃   │
│                        │                                                     │
│                        │         i insert · Ctrl+T attach track · Enter send │
```

- `●` on a conversation = unread.
- `j`/`k` in the conversation list; `l` or `Enter` opens a thread.
- Messages from you are right-aligned; from them, left.
- **Shared tracks render as playable cards inline** — `Enter` on a track
  message triggers `playback.play` just like in the catalog. This is the DM
  feature's whole point: frictionless "listen to this."
- `i` enters insert mode in the compose box (vim-style). `Esc` leaves it.
- `Ctrl+T` in insert mode: mini-search to attach a track to the message.
- New messages arrive via IPC `dm.received` event — thread updates live
  without a refresh.

---

## Generate View

Nav → `Generate`. Experimental; the most speculative pane.

```
│  GENERATE MUSIC                                                              │
│  ────────────────────────────────────────────────────────────────────        │
│                                                                              │
│  Describe what you want to hear. Be as specific or as vague as you like.     │
│                                                                              │
│  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓     │
│  ┃ slow modal jazz piano trio, brushed drums, rainy-afternoon feel█   ┃     │
│  ┃                                                                    ┃     │
│  ┃                                                                    ┃     │
│  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛     │
│                                                                              │
│                                                      Ctrl+Enter generate     │
│                                                                              │
│  RECENT ─────────────────────────────────────────────────────────────        │
│                                                                              │
│    ⠙ generating…    "lo-fi hip hop, vinyl crackle"          12s              │
│    ▶ 0:47           "aggressive drum and bass, 174bpm"       4m ago          │
│    ▶ 1:12           "ambient drone, no percussion"           1h ago          │
│                                                                              │
│                                                Enter play · d delete · s save│
```

- Multi-line prompt box — `Enter` inserts newline, `Ctrl+Enter` submits.
- Jobs show a Braille spinner (`⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏`) while generating, progress
  arrives via IPC `gen.progress` events.
- Completed jobs show duration and are playable like any track.
- `s` saves the generated clip to `~/.cache/juke/generated/` and (backend
  permitting) uploads to the user's library.

---

## Help Overlay

`?` from anywhere. Full-screen modal over everything except the playback bar.

```
┌─ KEYBINDINGS ────────────────────────────────────────────────────────────────┐
│                                                                              │
│  GLOBAL                           PLAYBACK                                   │
│  ──────────────────────────       ──────────────────────────                 │
│  /        search                  space    play / pause                      │
│  :        command palette         n        next track                        │
│  ?        this help               p        previous track                    │
│  q        quit                    ←  →     seek -10s / +10s                  │
│  Esc      dismiss overlay         0-9      seek to 0-90%                     │
│                                                                              │
│  NAVIGATION                       CONTENT                                    │
│  ──────────────────────────       ──────────────────────────                 │
│  h  l     focus prev/next pane    Enter    open / play                       │
│  j  k     move selection          Bksp     back (pop breadcrumb)             │
│  g  G     jump to top / bottom    a        play whole album                  │
│  Tab      next section            r        recommendations from this         │
│                                                                              │
│  SIDEBAR                          MESSAGES                                   │
│  ──────────────────────────       ──────────────────────────                 │
│  f        facts mode              i        compose (insert mode)             │
│  r        flows-into mode         Ctrl+T   attach track                      │
│                                   Enter    send / play shared track          │
│                                                                              │
│                              config: ~/.config/juke/config.toml              │
│                                                               Esc to close   │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Command Palette

`:` opens a single-line prompt at the bottom (above the playback bar). For
actions that don't deserve a dedicated key.

```
│ :login                                                                       │
├──────────────────────────────────────────────────────────────────────────────┤
│  ◀◀     ▶     ▶▶        So What · Miles Davis · Kind of Blue                 │
```

Commands: `:login`, `:logout`, `:connect spotify`, `:config edit`,
`:daemon restart`, `:daemon install`, `:theme <name>`. Tab-completes.

---

## State Indicators

Small glyphs used consistently throughout:

| Glyph | Meaning |
|---|---|
| `▸` | Current selection (focused list item) |
| `♪` | Currently playing (in track lists) |
| `●` | Unread / attention needed |
| `⠙` (spinner) | In progress |
| `ws` / `poll` | Backend transport mode (header, dimmed) |
| `█` | Text cursor |
| `░` | Dimmed / out-of-focus region |

---

## Responsive Collapse

| Terminal width | Behavior |
|---|---|
| ≥ 100 cols | Full 3-pane layout |
| 80–99 cols | Sidebar collapses. `l` from content opens it as an overlay. |
| 60–79 cols | Nav also collapses. `h` from content opens nav overlay. Single-pane. |
| < 60 cols | Refuse to render. Print "terminal too narrow (need ≥60 cols)" and exit 1. |

Height under 20 rows: playback bar shrinks from 3 rows to 1 (drop the progress
bar, keep controls + track name).

---

## Open Design Questions (to address before/during cli-phase3)

These are stakeholder notes captured 2026-03-06 that the current mockups either
don't cover or partially contradict. Each needs a design resolution and a
mockup update before the relevant pane gets built.

### 1. Playback bar stickiness across catalog views

> As a general design principle, I don't want the whole screen to change very
> much in between views for browsing catalog: albums/artists/genres. In other
> words, let's have the "Now Playing" bottom panel be sticky throughout the
> entirety of the session.

**Current design status:** the Layout Anatomy section already has the 3-row
playback bar as a persistent bottom row. But "the whole screen" not changing
much between catalog drill-downs is a stronger constraint — it implies the nav
rail and sidebar also stay fixed while only the center content pane swaps.
Need to audit every mockup (especially Messages and Generate, which currently
repurpose the content area more heavily) and confirm the bar is drawn in
literally every one. If Messages/Generate want more horizontal room, they can
collapse the sidebar — but not touch the bottom bar.

**Resolve before:** `cli-phase3` (`panes/playback.go` is the sticky bar;
`app.go` layout composition decides what it shares a row with).

### 2. Search input lives in the header, not an overlay

> Anytime the user triggers search, that should show up at the top horizontal
> panel with bigger text font size for emphasizing that action.

**Current design status:** conflicts with the Search Overlay mockup, which
draws search as a centered modal over a dimmed background. The ask is for a
header-integrated search — the top row becomes a big text input when `/` is
pressed, results populate the content pane below. "Bigger text font size" in a
terminal means bold + maybe a `figlet`-style or double-height-via-box-drawing
treatment — need to mock up what "emphasis" looks like when we can't actually
change point size. Likely: the header row grows from 1 line to 3 lines with a
boxed input, then shrinks back on `Esc`.

**Resolve before:** `cli-phase3` (`panes/search.go` — this changes it from an
overlay to a header-embedded component).

### 3. Search-history breadcrumbs with Tab/Shift+Tab navigation

> I think there are API actions for saving navigation search history, so we
> should make use of that in the TUI. Breadcrumbs for what was searched should
> be navigable by Tab (forward) and Shift+Tab (backwards) and the content pane
> should refresh when that is triggered.

**Current design status:** not covered. `backend/catalog/urls.py` registers a
`search-history` ViewSet — confirm its shape (likely `GET` list + `POST` on
each search). The breadcrumb model in the Album Detail mockup is for catalog
drill-down path, not for search-query history — these are two different trails.
Need to decide: does the header show both (drill-down path + recent searches),
or does Tab/Shift+Tab cycle through a separate recent-searches popup? Mockup
needed either way. Also: Tab is currently unbound in the keybinding table —
reserve it here.

**Resolve before:** `cli-phase3` (`internal/api/` adds the search-history
client; `panes/search.go` and/or a new `panes/breadcrumb.go` render the trail;
`keys.go` binds Tab/Shift+Tab).

### 4. Free-form mood/intent queries through the search bar

> We should also support free-form chat messages through the same search bar —
> if the user wants to search for a type of music based on some moods, that
> should be processed by the backend and the response should be given back to
> the user with actions that trigger the desired outcome.

**Current design status:** not covered, and the backend half doesn't exist.
This is a natural-language-to-intent layer: "something mellow for working late"
→ backend resolves to a set of tracks/albums/playlists + suggested actions
("play this playlist" / "queue these 5 tracks"). Open questions before a
mockup makes sense:
- Is the search input always dual-mode (every query goes to both lexical
  search and the intent resolver, results merged), or is there a mode toggle
  (`/` = lexical, `?` or `>` = free-form)?
- What does the response look like when the intent is ambiguous — a
  clarifying-question round-trip in the content pane?
- Does "actions that trigger the desired outcome" mean the response includes
  structured action-buttons the user arrows through, vs. just a result list?
- Backend owner: this is closest to `backend-track-facts-llm` in shape (LLM
  intent extraction) but scoped at search, not at a single track. Likely needs
  its own backend task. cli-phase3 won't block on it — this can land as a
  later enhancement to the search pane.

**Resolve before:** can be deferred past `cli-phase3`. Mockup + a new
`backend-search-intent-resolver` task (or fold into an mlcore phase) once the
interaction model is pinned down.

---

*Document Version: 1.0*
*Last Updated: 2026-03-06*
