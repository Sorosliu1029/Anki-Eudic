# Anki Eudic

A small Python/Textual application that downloads an **unknown or unfamiliar word
list** from Eudic and exports it as an Anki deck (`.apkg`), optionally enriched with
definitions, examples and pronunciation audio from a local LDOCE5++ dictionary. The API
implementation follows the Eudic development guide included in this repository,
including the category and paginated word-list endpoints.

## Features

- Keyboard-driven terminal UI: study lists in a sidebar, a filterable word preview
  with a detail pane, and an export dialog with a progress bar.
- Fetches every API page (up to Eudic's documented maximum page size of 100) and
  removes case-insensitive duplicates.
- Exports an Anki package (`.apkg`) with BrE/AmE IPA and audio, part of speech,
  numbered senses with Chinese translations and examples, collocations and word origin
  from LDOCE5++, plus Eudic's context, added date and star rating. Eudic's own
  explanation is used only for words the dictionary does not have.
- Re-exporting the same list updates existing notes in place and keeps review progress.
- No Anki add-on or running Anki instance is required.
- Keeps the authorization token out of the repository and export. Persisted tokens
  are stored by `keyring` in the operating system's credential service—not in a
  plaintext settings file.

## Install

Requires [uv](https://docs.astral.sh/uv/) (it provides Python 3.10 or newer). From a
clone of this repository:

```bash
uv run anki-eudic
```

`uv run` creates `.venv` and installs the locked dependencies on first use. To install
the command globally instead, run `uv tool install .`.

## Token security

Create or copy your authorization token from Eudic's Open API page. On first run,
the **Connect to Eudic** dialog opens; paste it and press Enter (**Save & connect**).
The token is checked against Eudic before it is saved. **Use without saving** keeps it
for the current session only. Either `abc...` or the
full `NIS abc...` authorization value is accepted. The field is masked and cleared
after saving.

The app delegates persistence to the system credential store through `keyring`
(for example, macOS Keychain, Windows Credential Locker, or a Linux Secret Service).
It deliberately has **no plaintext fallback**. If the machine has no usable keyring,
provide the token only to the launched process:

```bash
EUDIC_TOKEN='NIS your-token' uv run anki-eudic
```

Avoid putting that command in shell history; a prompt is safer:

```bash
read -rsp 'Eudic token: ' EUDIC_TOKEN && export EUDIC_TOKEN && uv run anki-eudic
```

The environment value takes precedence over a saved value. Press `t` to reopen the
dialog; **Forget saved token** there removes only the credential-store value.

## Export and import

1. Start `uv run anki-eudic` (or `uv run python -m anki_eudic`).
2. Connect with your token; the study lists appear in the sidebar.
3. Select the list where you keep unknown or unfamiliar words (Enter or click). Its
   words load into the preview; the pane below the table shows the highlighted word in
   full. Press `/` to filter, Escape to clear the filter.
4. Press `e` to export. Choose the deck, output file and LDOCE5++ `.mdx` path; the
   dialog says whether the dictionary will add definitions and audio. The dictionary
   path defaults to `$ANKI_EUDIC_LDOCE` or an `LDOCE5*.mdx` in `~/Library/Eudb_en`;
   leave it empty to export Eudic's data only. Audio comes from the `.mdd` file next
   to the `.mdx`.
5. In Anki Desktop, choose **File → Import** and select the output file.

Shortcuts: `q` quit · `r` reload study lists · `e` export · `/` filter · `t` token.

Notes use the **Anki-Eudic Word** note type (fields: Word, PhoneticUK, PhoneticUS,
AudioUK, AudioUS, PartOfSpeech, Definition, Explanation, Context, Extra, Added, Star).
The front shows the word with British and American IPA and audio; the back adds the
definitions and the rest. Each note is
identified by its lower-cased word, so exporting the list again later and importing
with the default **Update notes: if newer** updates existing cards without resetting
their progress, and adds new words. Words removed from Eudic are not deleted in Anki.
Audio files are named `ldoce_<accent>_<name>.mp3` in Anki's media folder. Sync to
AnkiWeb from Anki as usual. See [docs/anki-development.md](docs/anki-development.md)
for the details.


## Keyboard shortcuts

- `r`: reload study lists
- `q`: quit

## Dictionary lookup (LDOCE5++)

`anki_eudic.dictionary` reads a local *Longman Dictionary of Contemporary English
5++* MDict dictionary (the `.mdx` entries plus the optional `.mdd` audio/resources).
The `.apkg` export uses it; it can also be used directly as a library.

```python
from anki_eudic.dictionary import LdoceDictionary

base = "~/Library/Eudb_en/LDOCE5++ V 1-35"
with LdoceDictionary(f"{base}.mdx", f"{base}.mdd") as ldoce:
    entry = ldoce.lookup("pronounce")          # None when the word is missing
    print(entry.headword, entry.parts_of_speech, entry.pronunciation.ipa_bre)
    for sense in entry.homographs[0].senses:
        print(sense.number, sense.grammar, sense.definition)
        for example in sense.examples:
            print("  ", example.text, example.audio)
    ldoce.extract_audio(entry.pronunciation.audio_bre, "media/")  # writes an .mp3
```

An entry has one `Homograph` per part of speech with IPA (BrE/AmE), audio paths,
frequency/level markers (`S1`, `W2`, `●●●`, Academic Word List), inflections, senses
(signposts, grammar codes, register labels, definitions, Chinese translations, examples,
grammar patterns/collocations, subsenses, cross-references), phrasal verbs, derived
forms, collocation boxes and usage notes, plus the word family and origin.
`@@@LINK=` redirects (e.g. `taken` → `take`) are followed and lookups ignore case.

The dictionary files are only read. On first use a key index (a few tens of MB) is
built in the user cache directory (`~/Library/Caches/anki-eudic` on macOS,
`$XDG_CACHE_HOME/anki-eudic` on Linux; override with `ANKI_EUDIC_CACHE_DIR`), so
lookups take milliseconds. Only MDict 2.x files with zlib or uncompressed blocks are
supported out of the box; LZO-compressed files additionally need `python-lzo`.
The integration test runs against the real files when they exist (set `LDOCE_DIR`
if they are not in `~/Library/Eudb_en`).

## Limitations

- This tool exports study-list content; it does not modify or delete anything in
  Eudic and does not invoke AnkiConnect.
- Availability and unlocking behavior of the credential store depend on the OS.
- Network/API errors are shown in the status panel. Tokens are never included in
  those messages.

## Tests

```bash
uv run pytest
uv run ruff check .
```
