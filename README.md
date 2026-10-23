# Anki Eudic

A small Python/Textual application that downloads an **unknown or unfamiliar word
list** from Eudic and exports it as an Anki deck (`.apkg`), optionally enriched with
definitions, examples and pronunciation audio from a local LDOCE5++ dictionary. The API
implementation follows the Eudic development guide included in this repository,
including the category and paginated word-list endpoints.

## Features

- Terminal UI for saving a token, choosing a Eudic study list, previewing its words,
  and choosing the Anki export location and deck name.
- Fetches every API page (up to Eudic's documented maximum page size of 100) and
  removes case-insensitive duplicates.
- Exports an Anki package (`.apkg`) with BrE/AmE IPA and audio, part of speech,
  numbered senses with Chinese translations and examples, collocations and word origin
  from LDOCE5++, plus Eudic's own explanation, context, added date and star rating.
- Re-exporting the same list updates existing notes in place and keeps review progress.
- Can still produce UTF-8 TSV with Anki file headers instead. No Anki add-on or running
  Anki instance is required for either format.
- Keeps the authorization token out of the repository and export. Persisted tokens
  are stored by `keyring` in the operating system's credential service—not in a
  plaintext settings file.

## Install

Python 3.10 or newer is required. From a clone of this repository:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install .
anki-eudic
```

For development and tests, use `python -m pip install -e '.[dev]'`.

## Token security

Create or copy your authorization token from Eudic's Open API page. On first run,
paste it into the password field and select **Save token**. Either `abc...` or the
full `NIS abc...` authorization value is accepted. The field is masked and cleared
after saving.

The app delegates persistence to the system credential store through `keyring`
(for example, macOS Keychain, Windows Credential Locker, or a Linux Secret Service).
It deliberately has **no plaintext fallback**. If the machine has no usable keyring,
provide the token only to the launched process:

```bash
EUDIC_TOKEN='NIS your-token' anki-eudic
```

Avoid putting that command in shell history; a prompt is safer:

```bash
read -rsp 'Eudic token: ' EUDIC_TOKEN && export EUDIC_TOKEN && anki-eudic
```

The environment value takes precedence over a saved value. **Forget saved token**
removes only the credential-store value.

## Export and import

1. Start `anki-eudic` (or `python -m anki_eudic`).
2. Save/provide a token, then load the study lists.
3. Pick the list where you keep unknown or unfamiliar words and select **Fetch words**.
4. Review the preview, then choose the format, destination, deck and (for `.apkg`)
   the LDOCE5++ `.mdx` path, and export. The dictionary path defaults to
   `$ANKI_EUDIC_LDOCE` or an `LDOCE5*.mdx` in `~/Library/Eudb_en`; leave it empty to
   export Eudic's data only. Audio comes from the `.mdd` file next to the `.mdx`.
5. In Anki Desktop, choose **File → Import** and select the output file.

### `.apkg` (default)

Notes use the **Anki-Eudic Word** note type (fields: Word, Phonetic, AudioUK, AudioUS,
PartOfSpeech, Definition, Explanation, Context, Extra, Added, Star). Each note is
identified by its lower-cased word, so exporting the list again later and importing
with the default **Update notes: if newer** updates existing cards without resetting
their progress, and adds new words. Words removed from Eudic are not deleted in Anki.
Audio files are named `ldoce_<accent>_<name>.mp3` in Anki's media folder. Sync to
AnkiWeb from Anki as usual. See [docs/anki-development.md](docs/anki-development.md)
for the details.

### `.tsv`

Map the six columns if necessary and enable duplicate handling appropriate for your
deck. The first field is the spelling, so mapping **Word** to the note type's first
field lets Anki identify duplicates. The exported headers select tab separation, HTML,
and the chosen deck automatically on Anki versions that support text-file headers.

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
pytest
ruff check .
```
