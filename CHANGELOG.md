# Changelog

Newest first. Every release keeps the data of the ones before it (see *Update AirFare* in the README).

## 1.5.0

Updates that never lose data.

- **Data version.** `data/version.json` records which AirFare last brought the data folder up to date and its
  format (`{"app", "schema", "updated"}`). A folder without it is 1.4.1's (schema 1); this release is schema 2.
- **Migration at every start.** `airfare/migrate.py` runs before anything reads the data (background checker,
  Settings, check, links, doctor, and the install scripts as `python -m airfare migrate`), under a file lock so
  two processes never migrate at once. Its steps are ordered, one per schema number, and idempotent; a failed
  step puts the data back as it was. Schema 2 turns the single `min_drop_percent` of settings from before alert
  kinds into the three alert kinds; 1.4.1's files come through unchanged.
- **Backups.** Before a step changes anything, `config.json`, `state.json`, `history.json`,
  `price_history.json`, `price_research.json`, `dashboard.json`, `rates.json` and the `openai/` and `deepseek/`
  folders are copied to `data/backups/<old version>-<YYYYMMDD-HHMM>/`; the newest three are kept. Clean up lists
  the backups with their size and deletes the ones picked; Start over keeps them.
- **Data from a newer AirFare** (after going back to an older release) is never migrated or rewritten. Settings
  and `doctor` say *This data was written by AirFare x.y.z; install that version or newer*; everything else
  keeps working.
- **Settings survive going either way.** `save_config` keeps top-level keys and route fields this version
  doesn't know, so a newer or older AirFare's settings are not lost when Settings saves.
- **Unzipping a new release over the old folder just works.**
  - `.venv/airfare-install.json` records the installed version and the SHA-256 of `requirements.txt`.
  - `AirFare.exe` notices when the code's version differs from the installed one and finishes the update in
    the setup window (`install.ps1 -Upgrade`): it stops the previous version's background checker and Settings
    server, removes files the previous version left behind, installs the packages, backs up and migrates the
    data, adds the shortcuts and registrations again, starts the background checker the settings need, then
    opens Settings. If a step fails, the data stays untouched and the window says what to do.
  - On macOS and Linux, running `sh install.sh` again does the same; until then, `python -m airfare` says
    *Run sh install.sh to finish the update*.
  - `tools/make_portable.py` adds `MANIFEST.txt`, listing every file in the zip. The update deletes files in
    `airfare/`, `extension/`, `extension-firefox/`, `tools/`, `launcher/` and `assets/` that the manifest
    doesn't list, and never touches `data/`, `.venv/` or anything else.
- **Update steps for users:** the README's new *Update AirFare* section, step 6 of the install guides
  (`docs/INSTALL_*.md`, also in the zip's `Install-*.html`), and, when Check for updates finds a newer
  release, the same steps in short in Settings with the link to the release.
- **Contributing:** the *Users' data keeps working* rule now lists what every change must keep, and
  `tests/fixtures/data-1.4.1/` (invented data) holds a complete 1.4.1 data folder that each release must
  migrate intact.
- **Tests:** the check that runs the extension's code in Node.js no longer depends on the machine's speed, the
  test runner's stdin or AirFare's port (it failed once on Windows in CI, waiting for Node.js for 30 seconds).

## 1.4.1

First public release.
