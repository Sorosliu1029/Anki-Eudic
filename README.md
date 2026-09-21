# Anki Eudic

A small Python/Textual application that downloads an **unknown or unfamiliar word
list** from Eudic and exports it as an Anki-ready, tab-separated text file. The API
implementation follows the Eudic development guide included in this repository,
including the category and paginated word-list endpoints.

## Features

- Terminal UI for saving a token, choosing a Eudic study list, previewing its words,
  and choosing the Anki export location and deck name.
- Fetches every API page (up to Eudic's documented maximum page size of 100) and
  removes case-insensitive duplicates.
- Exports word, definition, context, phonetic spelling, added date, and star rating.
- Produces UTF-8 TSV with Anki file headers, HTML-safe content, and preserved line
  breaks. No Anki add-on or running Anki instance is required.
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
4. Review the preview, choose a `.tsv`/`.txt` destination and deck, and export.
5. In Anki Desktop, choose **File → Import**, select the output file, map the six
   columns if necessary, and enable duplicate handling appropriate for your deck.

The first field is the spelling, so mapping **Word** to the note type's first field
lets Anki identify duplicates. The exported headers select tab separation, HTML,
and the chosen deck automatically on Anki versions that support text-file headers.

## Keyboard shortcuts

- `r`: reload study lists
- `q`: quit

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
