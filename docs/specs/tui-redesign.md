# TUI redesign — spec and implementation plan

## Problems with the current interface

The app is a single scrolling form with every control stacked vertically:

1. **Everything is always on screen.** The token field, three token buttons, list
   picker, export settings, status and preview compete for space. The preview table —
   the thing users most want to see — sits at the very bottom, usually below the fold.
2. **Too many explicit steps.** Save token → Load study lists → pick a list → Fetch
   words → scroll down → Export. Each step is a separate button press.
3. **Status is easy to miss.** A single status box in the middle of the form is
   overwritten by every message; errors and successes look alike apart from a prefix.
4. **Truncated data.** Long explanations and contexts are cut off in the table with no
   way to read them.
5. **No feedback during export.** Exporting a large list with LDOCE lookups can take a
   while and shows only "Exporting…".
6. **Dictionary path is unchecked** until export fails.
7. **Few keyboard shortcuts** (`q`, `r`) for a keyboard-first tool.

## Goals

- The word preview is the main view; setup and export settings appear only when needed.
- Getting from launch to an exported deck takes as few actions as possible.
- Every slow operation shows that it is running; every outcome is clearly reported.
- Fully keyboard-driven, with shortcuts listed in the footer.

Non-goals: changing the export format, the API client, or how tokens are stored.

## Design

### Layout (main screen)

```
┌ Anki Eudic ─────────────────────────────────────────────── Study-list exporter ┐
│ Study lists          │ Unknown words · 248 words           [ Filter words… ]  │
│ ▸ Unknown words (en) │ Word          Phonetic     Explanation            ★    │
│   Hard words (en)    │ abate         əˈbeɪt       v. 减弱，减轻          3    │
│                      │ …                                                      │
│                      ├────────────────────────────────────────────────────────┤
│                      │ abate  /əˈbeɪt/  ★★★  added 2026-09-14                  │
│                      │ v. 减弱，减轻；废除                                    │
│                      │ Context: The storm showed no signs of abating.        │
└──────────────────────┴────────────────────────────────────────────────────────┘
 q Quit  r Refresh  e Export  / Filter  t Token  ^p Palette
```

- **Sidebar**: an `OptionList` of study lists. Selecting one (Enter / click) fetches
  its words straight away — there is no separate "Fetch words" button. Fetched lists are
  cached for the session; `r` reloads the lists and clears the cache. When there is only
  one list it is opened automatically.
- **Summary line**: names the open list and its word count (or the filtered count),
  or tells the user what to do next ("Select a study list", "Press t to connect").
- **Filter**: `/` focuses a filter input that narrows the table by word, explanation or
  context, case-insensitively. Escape clears it and goes back to the table.
- **Table**: Word, Phonetic, Explanation (single line), ★. Rows are selectable with
  the cursor; there is no 500-row limit.
- **Detail pane**: shows the highlighted word in full — phonetic, star rating, added
  date, the complete explanation and context — so nothing truncated is out of reach.
- **Loading states**: the sidebar and table use Textual's `loading` indicator while a
  request is running.
- **Notifications**: outcomes and errors are shown as toasts (`App.notify`), with the
  error severity for failures, instead of one overwritten status box.

### Token screen (modal)

Shown automatically on launch when no token is found, and on demand with `t`.

- Explains where the token comes from and that it is stored only in the OS credential
  store (or that `EUDIC_TOKEN` can be used instead).
- Masked input; Enter = **Save & connect**.
- **Save & connect** first *verifies* the token by loading the study lists, and saves
  it to the keyring only if that works. Errors are shown inline on the screen, so a
  bad token never gets saved and the user doesn't lose their place.
- **Use without saving** connects for this session only (useful when no keyring works).
- **Forget saved token** is shown only when a token has been loaded.
- Escape / **Cancel** closes the screen; the summary line then explains how to reopen it.

### Export screen (modal)

Opened with `e` (shown in the footer only while words are loaded).

- Title: "Export *N* words from *List*".
- Fields: deck name, output file, LDOCE5++ `.mdx` path. Values persist for the session.
- **Live dictionary check** under the path field as the user types:
  "Not set — Eudic data only", "✓ Definitions and audio", "✓ Definitions only (no
  .mdd next to it)", or "✗ File not found". Export is refused while the file is missing.
- **Progress bar** advancing per note during export; inputs and buttons are disabled
  while it runs.
- On completion, the screen shows a summary (notes, enriched, audio, path and the Anki
  import hint) and the button turns into **Done**. Failures are shown inline and the
  user can fix the settings and retry.

### Key bindings

| Key | Action | Where |
| --- | --- | --- |
| `q` | Quit | main |
| `r` | Reload study lists | main |
| `e` | Export (only while words are loaded) | main |
| `/` | Focus filter | main |
| `t` | Token / connection screen | main |
| `escape` | Clear filter · close modal | filter · modals |
| `enter` | Open list · submit form | sidebar · modals |

## Implementation plan

1. **`apkg.export_apkg`: progress callback.** Add an optional keyword
   `progress: Callable[[int], None]` called after each note with the running count.
   Test: the callback receives `1..n`.
2. **`screens.py`: modal screens.**
   - `TokenScreen(ModalScreen[Connection | None])` — verify-then-save worker returning a
     `Connection(token, categories)`.
   - `ExportScreen(ModalScreen[None])` — form, `describe_dictionary()` live check,
     thread worker calling `export_apkg` with a progress callback that updates a
     `ProgressBar` via `call_from_thread`.
   - Pure helpers (`describe_dictionary`, `ExportSettings`) kept free of Textual so they
     are unit-testable.
3. **`app.py`: main screen.** Replace the form with the sidebar / table / detail layout,
   auto-fetch on list selection, per-session word cache, filter, bindings with
   `check_action` so `e` is hidden while nothing is loaded, and toasts for outcomes.
4. **Tests (`tests/test_app.py`)** using Textual's `App.run_test()` pilot with a fake
   `EudicClient` and patched credential functions: first run opens the token screen;
   saving verifies and stores the token; selecting a list fills the table; filtering
   narrows rows; export writes an `.apkg`; `describe_dictionary` cases.
5. **README**: update the usage section for the new flow and shortcuts.
6. Run `ruff check`, `ruff format --check` and `pytest`; open a PR.
