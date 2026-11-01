# Changelog

Newest first. Every release keeps the data of the ones before it (see *Update AirFare* in the README).

## 1.5.0

Updates that never lose data, and three filters per route.

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
    opens Settings. If a step fails, the window says what to do, and that the data is untouched or, once it has
    been updated, kept and backed up in `data/backups`.
  - On macOS and Linux, running `sh install.sh` again does the same; until then, `python -m airfare` says
    *Run sh install.sh to finish the update*, also in a desktop notification, and stops with its own exit code, 5.
  - `tools/make_portable.py` adds `MANIFEST.txt`, listing every file in the zip. The update deletes files in
    `airfare/`, `extension/`, `extension-firefox/`, `tools/`, `launcher/` and `assets/` that the manifest
    doesn't list, and never touches `data/`, `.venv/` or anything else. On Windows and macOS it compares paths
    ignoring capitals, so a file renamed only by capitalisation is never deleted.
- **Update steps for users:** the README's new *Update AirFare* section, step 6 of the install guides
  (`docs/INSTALL_*.md`, also in the zip's `Install-*.html`), and, when Check for updates finds a newer
  release, the same steps in short in Settings with the link to the release.
- **Contributing:** the *Users' data keeps working* rule now lists what every change must keep, and
  `tests/fixtures/data-1.4.1/` (invented data) holds a complete 1.4.1 data folder that each release must
  migrate intact.
- **Filters per route.** Each route card has a price range (From, To), max transfers per direction (Any, Direct
  only, Up to 1, Up to 2) and excluded transfer airports (IATA codes; city codes stand for their airports).
  - The route fields `price_min`, `price_max`, `max_stops` and `exclude_airports` are all optional: missing means no
    filter, so routes from earlier versions work as before and no migration is needed. They are in
    `config.ROUTE_FIELDS`, so saving never brings back a filter the user cleared.
  - `airfare/filters.py` applies them once, after prices are read and converted: the dashboard, the alerts, the price
    document and the analyst, the best-value pick, new price-history records and the CSV export only see matching
    fares. Hidden fares are counted per page and reason, and the dashboard's route header and the price document
    say so. The analyst gets the filters in each check's price document, so its rules and conversation stay the same.
  - `Flight.connections` holds each flight's connection airports, from Skyscanner's segments, Aviasales' flight legs
    and SerpApi's layovers. Fares whose connections or price can't be judged stay, marked, and don't count for alerts.
  - Google Flights also gets `stops`, `max_price` and `exclude_conns`. Direct only also sets `preferdirects=true` on
    Skyscanner; the extension doesn't change. The *Prefer direct flights* box keeps its meaning.
  - Changing a route's filters keeps its id, tab, price history and lookups, and restarts its alert references from
    the next check (`history.json` keeps the filters they were set under); Settings says so when saving.
  - New price-history records taken under filters carry them (`filters`). The History page marks records taken under
    other filters than the route's current ones, and the CSV has a `filters` column at its end.
- **Tests:** the check that runs the extension's code in Node.js no longer depends on the machine's speed, the
  test runner's stdin or AirFare's port (it failed once on Windows in CI, waiting for Node.js for 30 seconds).

## 1.4.1

First public release.
