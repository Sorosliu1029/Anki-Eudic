# Anki development research

Research for [issue #2](https://github.com/Sorosliu1029/Anki-Eudic/issues/2):
how Anki data is structured, how to generate decks from code, how to update them
incrementally, how syncing to AnkiWeb works, and how media is packaged. Checked on
2026-10-22.

**Versions checked**

| Component | Version | Source |
| --- | --- | --- |
| Anki desktop / `anki` PyPI wheel | 26.9.3 (2026-09-23), Python >= 3.10 | <https://pypi.org/project/anki/> |
| genanki | 0.13.1 (2023-11-12); last commit on `master` 2024-12-30 | <https://pypi.org/project/genanki/>, <https://github.com/kerrickstaley/genanki> |
| AnkiConnect (add-on `2055492159`) | rewrite with JSON-RPC "API v1"; needs Anki 26.08 or later | <https://git.sr.ht/~foosoft/anki-connect> |

Lines marked **(verified)** were tested locally with `anki==26.9.3` and
`genanki==0.13.1`: a genanki package was built, imported with
`Collection.import_anki_package`, rebuilt, and imported again.

---

## 1. Data model and file formats

Concepts are from the [manual's key concepts](https://docs.ankiweb.net/getting-started.html#key-concepts).
Schema details come from the `.apkg` files built during testing (inspected with `sqlite3`).

| Concept | What it is | Storage (SQLite schema v11 tables) |
| --- | --- | --- |
| **Note** | One fact: an ordered list of field values plus tags. Identified across collections by a `guid` string. | `notes(id, guid, mid, mod, usn, tags, flds, sfld, csum, flags, data)`. `flds` joins field values with `\x1f`. `sfld` is the sort field. `csum` is a checksum of the first field, used for duplicate detection. |
| **Card** | One reviewable item generated from a note by one card template. It holds the scheduling state. | `cards(id, nid, did, ord, mod, type, queue, due, ivl, factor, reps, lapses, ...)`. `ord` is the template index. `did` is the deck. |
| **Note type** (called a "model" in code) | Field names, card templates (`qfmt`/`afmt`, Mustache-like `{{Field}}`), CSS, and the sort field index. Regular or Cloze. | `notetypes`/`fields`/`templates` tables (v18), or JSON in `col.models` (v11). |
| **Deck** | A named container for **cards**, not notes. `::` separates levels, e.g. `Eudic::Unknown`. Uses a deck-options preset. | `decks` table (v18), or JSON in `col.decks` (v11). |
| **Collection** | Everything one profile has: notes, cards, note types, decks, review log, config, plus a separate `collection.media/` folder. | `collection.anki2`, a SQLite file in the profile folder. |

All IDs (note, card, note type, deck) are 64-bit integers, usually creation
timestamps in milliseconds.

### Package / file formats

| File | Contents |
| --- | --- |
| `collection.anki2` | The live SQLite collection in a profile folder. Inside packages it is also the legacy (v1) collection name. |
| `.apkg` | A ZIP containing **part** of a collection (selected decks with their notes, cards and note types), plus media. It is merged into an existing collection on import. This is the format to share or generate decks in. |
| `.colpkg` | A ZIP containing a **whole** collection plus media. Importing it **replaces** the user's collection, so it is only for backup and restore. |
| `.anki21` | Legacy package member: SQLite schema v11 written by Anki 2.1.x (pre-2.1.50). |
| `.anki21b` | Current package member: a **zstd-compressed** SQLite file using schema **v18**. |

The package layout is defined in
[`rslib/src/import_export/package/meta.rs`](https://github.com/ankitects/anki/blob/main/rslib/src/import_export/package/meta.rs)
and [`proto/anki/import_export.proto`](https://github.com/ankitects/anki/blob/main/proto/anki/import_export.proto)
(`PackageMetadata`, `MediaEntries`):

| Version | Detection | Collection member | `media` member |
| --- | --- | --- | --- |
| Legacy 1 | no `meta` file | `collection.anki2` | JSON `{"0": "file.mp3", ...}` |
| Legacy 2 | no `meta`, `collection.anki21` present | `collection.anki21` | JSON map |
| Latest | `meta` protobuf (`version = 3`) | `collection.anki21b` (zstd) | zstd protobuf `MediaEntries` (name, size, sha1) |

Media files sit in the ZIP root, named `0`, `1`, `2`, and so on (zstd-compressed in
the Latest format).

**(verified)** genanki writes Legacy 1 (`collection.anki2`, JSON `media`, `0`).
`Collection.export_anki_package(legacy=False)` writes `meta`, `collection.anki21b`,
and a placeholder `collection.anki2` that contains only a "Please update to the latest
Anki version" note for old clients. Anki 26.9.3 still imports Legacy 1 packages
without complaint.

---

## 2. Building cards and decks from code

| Option | What it is | Needs Anki running? | Output | Fit for this project |
| --- | --- | --- | --- | --- |
| **genanki** | Pure-Python `.apkg` writer, about 120 KB. Depends on `cached-property`, `frozendict`, `chevron`, `pyyaml`. | No | Legacy 1 `.apkg` file; the user imports it | **Best fit.** No Anki dependency, supports media, stable GUIDs. Slow upstream: no release since 2023-11. |
| **`anki` package** (`anki.collection.Collection`) | Anki's own Rust backend plus Python wrapper. Same code as desktop. | No, but it **cannot open a collection that desktop has open** | Writes any collection; exports modern `.apkg`/`.colpkg`; can sync | Most powerful, but heavy (about 26 MB, native wheel, protobuf). Its API follows Anki releases. Good for tests and an optional "direct" mode. |
| **AnkiConnect** | Add-on exposing a local HTTP API (`127.0.0.1:8765`) into the **running** desktop app | **Yes** (desktop 26.08 or later for the v1 API) | Notes go straight into the user's open collection | Best UX for "push words into Anki now and sync". Requires the user to install an add-on and keep Anki open. |
| **Raw SQLite + ZIP** | Hand-writing schema v11 or v18 | No | `.apkg` | Not recommended. It re-implements genanki and is fragile against schema changes. |

### genanki ([README](https://github.com/kerrickstaley/genanki))

```python
import genanki

MODEL_ID = 1_607_392_319   # pick once with random.randrange(1 << 30, 1 << 31), then hard-code
DECK_ID = 2_059_400_110

model = genanki.Model(
    MODEL_ID, "Anki-Eudic Word",
    fields=[{"name": "Word"}, {"name": "Phonetic"}, {"name": "Definition"},
            {"name": "Context"}, {"name": "Audio"}, {"name": "Added"}, {"name": "Star"}],
    templates=[{
        "name": "Recognize",
        "qfmt": "<div class=word>{{Word}}</div>{{Audio}}",
        "afmt": "{{FrontSide}}<hr id=answer>{{Phonetic}}<br>{{Definition}}<br>{{Context}}",
    }],
    css=".card{font-family:sans-serif;text-align:center}.word{font-size:2em}",
)
deck = genanki.Deck(DECK_ID, "Eudic::Unknown words")
deck.add_note(genanki.Note(model=model, fields=[...7 HTML strings...],
                           guid=genanki.guid_for("anki-eudic", "hello")))
pkg = genanki.Package(deck)          # or Package([deck_a, deck_b])
pkg.media_files = ["/path/to/ldoce_hello.mp3"]
pkg.write_to_file("eudic.apkg")      # optional timestamp= for hermetic builds
```

- Field values are **HTML**. Escape them with `html.escape` (the existing `_field()` helper already does this).
- `sort_field` (Browse view) defaults to field 0. You can set it with `sort_field_index=` on `Model`.

### `anki` package ([pylib `collection.py`](https://github.com/ankitects/anki/blob/main/pylib/anki/collection.py))

```python
from anki.collection import Collection, ExportAnkiPackageOptions, DeckIdLimit

col = Collection("/tmp/build/collection.anki2")       # creates if missing
nt = col.models.by_name("Anki-Eudic Word")             # or build one via col.models.new()/add_field/add_template
did = col.decks.id("Eudic::Unknown words")             # get-or-create
note = col.new_note(nt)
note["Word"] = "hello"
note["Audio"] = "[sound:%s]" % col.media.write_data("ldoce_hello.mp3", mp3_bytes)  # returns the stored name
col.add_note(note, did)
col.export_anki_package(out_path="eudic.apkg",
    options=ExportAnkiPackageOptions(with_scheduling=False, with_deck_configs=False,
                                     with_media=True, legacy=False),
    limit=DeckIdLimit(did))
col.close()
```

**(verified)** A second `Collection()` on the same file raises
`DBError: Anki already open, or media currently syncing`. A script must never open
the user's real profile while desktop Anki is running.

### AnkiConnect ([README](https://git.sr.ht/~foosoft/anki-connect/tree/master/item/README.md), [API v1](https://git.sr.ht/~foosoft/anki-connect/tree/master/item/API_V1.md), [legacy API](https://git.sr.ht/~foosoft/anki-connect/tree/master/item/API_LEGACY.md))

AnkiConnect was rewritten. New integrations use JSON-RPC 2.0 at
`POST http://127.0.0.1:8765/api/v1`. The legacy `{"action": ..., "version": 6}`
protocol at `/` still works. Relevant v1 methods:

- `noteTypes.create` and `decks.create` set up the note type and deck.
- `media.store` takes `{filename, source: {data|path|url}, collision: rename|replace|error, skipIfHash}`. Always insert the **returned** filename into `[sound:...]`.
- `notes.validate`/`notes.validateMany`, then `notes.create`/`notes.createMany`. `duplicates: {allow, scope: collection|deck, ...}` controls duplicate checks; `atomic: true` adds a batch in one transaction.
- `notes.search` + `notes.update` for upserts.
- `packages.import` imports an `.apkg` that exists on the machine running Anki.
- `collection.sync` (see section 4).
- Long-running methods return an `operationId`; poll `operations.get` for the result.

```python
import json, urllib.request
def rpc(method, **params):
    req = urllib.request.Request("http://127.0.0.1:8765/api/v1",
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
        headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))
rpc("notes.create", noteType={"name": "Anki-Eudic Word"}, deck={"name": "Eudic::Unknown words"},
    fields={"Word": "hello", "Audio": "[sound:ldoce_hello.mp3]"}, tags=["eudic"])
```

---

## 3. Incremental decks: stable IDs, duplicates, updates

### How `.apkg` import matches existing data

From [`rslib/.../apkg/import/notes.rs`](https://github.com/ankitects/anki/blob/main/rslib/src/import_export/package/apkg/import/notes.rs)
and the [manual on packaged decks](https://docs.ankiweb.net/importing/packaged-decks.html):

- **Notes are matched by `guid` only.** The field contents and the note ID do not matter. A new GUID adds a note. An existing GUID can update that note.
- Updates are controlled by the `UpdateCondition` (import dialog in 23.10+):
  - `IfNewer` (default) updates when `existing.mtime < incoming.mtime`.
  - `Always` updates when `existing.mtime != incoming.mtime`.
  - `Never` keeps the existing note.
  - The decision depends on the note **mtime**, not on whether the content changed.
- **Note types are matched by ID.** If the incoming schema (fields/templates) differs from the existing one, Anki imports a *copy* of the note type. Notes using that copy are logged as **conflicting** and not updated, unless the user ticks **Merge note types** (that forces a one-way full sync).
- **Decks are matched by name**, not by ID ([`apkg/import/decks.rs`](https://github.com/ankitects/anki/blob/main/rslib/src/import_export/package/apkg/import/decks.rs)). An existing deck with the same name is reused, and a new name creates a new deck.
- When an existing note is updated, its **card scheduling is kept** unless the package includes scheduling and the user chooses to import it.

**(verified)** Results of the local test:

- Importing v1 created 1 note.
- After rebuilding the deck **one second later** with a changed definition, re-importing under `IfNewer` gave `updated=1`. The new definition was applied, and the card's existing interval (`ivl=5`) was kept.
- Rebuilding **within the same second** gave `duplicate=1` (no update) even under `Always`, because genanki stamps every note with `mod = int(time.time())` at `write_to_file` time.

### Rules for Anki-Eudic

1. **Hard-code the model ID** as a constant and never randomise it per run: a new model ID creates a new note type on the next import. Decks are matched by name, so the deck ID matters less, but keep it constant too (genanki requires one).
2. **Derive the GUID from the word's identity, not its content**, e.g. `genanki.guid_for("anki-eudic", word.strip().casefold())`. This matches the case-insensitive de-duplication already done when fetching. genanki's default GUID hashes **all** fields, so any definition edit would create a duplicate note.
3. **Freeze the note type schema.** Choose the field list before the first release (include `Audio` and spare fields now). Adding or renaming fields later requires users to tick "Merge note types" on import. Changing only templates or CSS keeps the schema the same and updates cleanly.
4. **Accept that a re-export overwrites Anki-side edits** under the default `IfNewer` (every genanki build is "newer"). Eudic is the source of truth. Users who customise notes in Anki should pick "Never" for updates.
5. Exporting the full list each time is fine: unchanged words update in place, and new words are added. Words removed from Eudic are **not** deleted in Anki, and notes the user deleted in Anki **come back** on the next import (their GUID is no longer present). An "only words added since X" export option (using `added_at`) avoids this.
6. The current TSV path has a weaker version of this. Text import matches on the **first field** (`Word`), and it can carry a `#guid column:` header. The `.apkg` route is more robust ([text import docs](https://docs.ankiweb.net/importing/text-files.html)).

---

## 4. Syncing to AnkiWeb

What exists technically:

- **`anki` package:** `Collection.sync_login(username, password, endpoint) -> SyncAuth`, `sync_collection(auth, sync_media) -> SyncCollectionResponse` (`required` is one of `NO_CHANGES`, `NORMAL_SYNC`, `FULL_SYNC`, `FULL_DOWNLOAD`, `FULL_UPLOAD`), `full_upload_or_download(...)`, `sync_media(auth)`, `sync_status(auth)`. This is the same Rust sync client the desktop app uses (see `pylib/anki/collection.py`).
- **AnkiConnect:** v1 `collection.sync` (`includeMedia`, returns an operation; a full-sync decision is surfaced as `waitingForUser`) and the legacy `sync` action. Both trigger the **desktop app's own** sync with the credentials the user already saved in Anki.
- **Self-hosted sync server:** `pip install anki; SYNC_USER1=user:pass python -m anki.syncserver` ([docs](https://docs.ankiweb.net/sync-server.html)). Clients point at it in Preferences. This is fine for scripts and testing.

Policy limits (the important part):

- The [AnkiWeb Terms](https://ankiweb.net/account/terms) permit sync only through the approved clients (Anki, AnkiMobile, AnkiDroid, AnkiUniversal). They do not allow third-party clients, and they point to AnkiConnect for automating a local collection. Requests are logged for misuse detection ([privacy](https://ankiweb.net/account/privacy)).
- On the forums, the developers say new clients are generally not approved and recommend generating `.apkg` files and syncing from an official client ([thread](https://forums.ankiweb.net/t/what-is-the-process-of-getting-new-clients-approved-for-ankiweb-sync/21350)). Exceptions are handled privately.
- Practical risks:
  - A standalone `anki` collection is a *separate* collection. Its first sync forces a **full upload or download** that would overwrite the user's AnkiWeb data.
  - Storing AnkiWeb passwords would also undo this project's careful keyring design.

**Conclusion:** Anki-Eudic should **not** log in to AnkiWeb itself. It should:

1. produce an `.apkg` that the user imports into desktop Anki, which then syncs normally; or
2. optionally, with AnkiConnect installed, call `packages.import` and then `collection.sync` in the user's running Anki. This is the sanctioned automation path.

---

## 5. Media (audio and images)

- Media files live flat in `collection.media/` next to `collection.anki2`. Notes reference them by **bare filename** in field HTML:
  - audio: `[sound:ldoce_hello.mp3]`
  - images: `<img src="pic.jpg">`
- Template-level files (not referenced by any field) need a leading `_`, e.g. `_eudic.css`, or **Check Media** treats them as unused ([manual](https://docs.ankiweb.net/media.html)).
- Inside an `.apkg`, media are the numbered ZIP members plus the `media` map (section 1).
  - In genanki, set `package.media_files` to paths. The field must contain the full `[sound:basename]` tag, never just a filename or a path.
- **(verified)** After import, the file appears in the target `collection.media/` and `[sound:...]` plays.
- **Name collisions:** if the collection already has a file with the same name but a different SHA-1, the importer adds a hash suffix to the incoming file and **rewrites the references** in the imported notes ([`apkg/import/media.rs`](https://github.com/ankitects/anki/blob/main/rslib/src/import_export/package/apkg/import/media.rs)). Use deterministic, project-prefixed names so the same word maps to the same file across exports.
- Anki normalises filenames: unsafe characters are stripped, names are NFC-normalised, and long names are shortened. Files whose names can't be synced are skipped. Keep names ASCII-safe: `ldoce_<slug>_<uk|us>.mp3`.
- **Format:** MP3 (audio) and MP4 (video) are the most widely supported across desktop, AnkiWeb and mobile ([manual](https://docs.ankiweb.net/media.html)).
  - LDOCE `.mdd` resources are often MP3. Some dictionary builds ship SPX/Ogg, which should be **transcoded to MP3** (e.g. `ffmpeg`) before packaging, so mobile clients can play them.
- Media sync is separate from collection sync but runs in the same sync action. Symlinks in the media folder are not followed.

---

## 6. Recommendation for Anki-Eudic

**Adopt genanki to export `.apkg` files**, with stable IDs and word-derived GUIDs.
Keep the TSV export as a fallback. Add an optional AnkiConnect "send to Anki" mode
later. Do not build AnkiWeb sync.

Why:

- It keeps the current "no add-on, no running Anki" property.
- It is the only file-based route that bundles **audio** (TSV import cannot carry media).
- It gives true upserts through GUIDs.
- Its dependency footprint is small compared with the 26 MB `anki` wheel.

genanki's slow release cadence is acceptable: the Legacy 1 format it writes is still
imported by Anki 26.9.3. The `anki` package can serve as a dev/test dependency to
assert that generated packages import correctly (the probe used for this note).

### Integration sketch against the current code

- `exporter.py`: keep `export_anki` (TSV), and add `export_apkg(words, destination, deck, audio: Mapping[str, Path] | None)`:
  - module constants `MODEL_ID`, `DECK_ID` and the `genanki.Model` (fields: Word, Phonetic, Definition, Context, Audio, Added, Star, plus a spare field such as Image/Extra so the schema doesn't need to change later);
  - reuse `_field()` for HTML escaping. Set `Audio` to `[sound:<name>]` when the LDOCE extractor (sibling task) provides a file for `word.casefold()`;
  - `guid=genanki.guid_for("anki-eudic", word.casefold())`;
  - `pkg.media_files = [the audio paths that were used]`, then `pkg.write_to_file(path)`, forcing an `.apkg` suffix.
- Deck name from the UI: keep using the user's deck name, because import matches decks by name. Derive `DECK_ID` deterministically from the name (e.g. `int(sha256(name)[:8], 16) >> 2`) so builds are reproducible.
- `app.py`: add a format choice (`.apkg` default, `.tsv`) to the existing export controls. The call site at `export_anki(self.words, destination, deck)` branches on it.
- `pyproject.toml`: add `genanki>=0.13.1,<0.14`. Optionally add `anki` to `[dev]` for an import round-trip test.
- Tests:
  - GUID is stable across definition changes;
  - model/deck IDs are constant;
  - the ZIP contains `collection.anki2` and a `media` map naming the audio;
  - optional: `Collection.import_anki_package` round-trip showing `new` then `updated` counts.
- Docs: update the README's "Export and import" section. Import the `.apkg` via **File > Import** and leave "Update notes: if newer" on. Re-exporting the same list later updates existing cards without resetting progress.
- Later (optional): an "AnkiConnect" mode that calls `media.store` and `notes.createMany`/`notes.update` (or `packages.import` on the generated file), followed by `collection.sync`, only when the add-on is reachable on `127.0.0.1:8765`.
