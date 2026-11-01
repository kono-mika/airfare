# Contributing to AirFare

Thanks for helping. AirFare is a small personal tool, and every change keeps it simple, safe and local.

## Before you start

- For anything bigger than a small fix, open an issue first, so the approach is agreed before you write code.
- Security problems go through private reporting, never a public issue: see [SECURITY.md](SECURITY.md).

## Set up

You need Python 3.12 or newer.

Windows (PowerShell, in the project folder):

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt -r requirements-dev.txt
.venv\Scripts\python -m pytest -q
```

macOS and Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

To try your change, run `python -m airfare setup` (Settings) or `python -m airfare run -v` (one check) with the
environment variable `AIRFARE_DATA` set to a scratch folder, so your own settings and price history stay untouched.

## What every change needs

- **Tests** for what changed. The whole suite passes; CI runs it on Windows, macOS and Linux.
- **Three languages:** every new interface text in English, Spanish and Russian (`airfare/translations.py`).
  `python tools/i18n_keys.py` lists any that are missing.
- **The Firefox build:** after changing `extension/`, run `python tools/make_firefox.py`.
  `tests/test_firefox.py` fails while `extension-firefox/` is out of date.
- **Docs:** the README and `docs/INSTALL_*.md` when behaviour or setup changes.
- **Users' data keeps working:** someone who updates from 1.4.1 or any later version keeps all their data:
  settings, API keys, routes and their ids, price history, lowest-price lookups, dashboard tabs, alert
  references, analyst conversations, reports and logs. So:
  - never rename or remove a stored key, or change what a value means, without a migration step in
    `airfare/migrate.py` (bump `SCHEMA`, add the step to `STEPS`; each step is idempotent and backed up first);
  - new keys get their default when read; readers accept missing and unknown fields;
  - route ids never change in a migration; old records are never rewritten except by a migration step;
  - `save_config` keeps top-level keys and route fields it doesn't know, so settings survive going to a newer
    or older version (a new route field the Settings form writes goes into `config.ROUTE_FIELDS`);
  - `tests/fixtures/data-1.4.1/` (invented data) must migrate with every id, record and reference intact;
    add a fixture for any release that changes the format.

## Privacy and safety

- No API keys, tokens, passwords, personal data, real routes or real file paths in any file, commit or pull
  request. Test data is invented and labelled as invented.
- Commit with your GitHub noreply address, not a personal email.

## What AirFare won't accept

AirFare stays a personal tool that uses the price sites gently. Pull requests that do any of these are declined:

- solving or bypassing robot checks, or hiding that AirFare is a program (fake identities, stealth browsers,
  proxies, rotating IP addresses);
- raising the page limits beyond the Personal and Extended levels, or removing them;
- running AirFare for other people, publishing or reselling prices, or turning it into a hosted service.

## Pull requests

- One topic per pull request, from its own branch, with a short description of what changed and why.
- Commit messages: an imperative subject ("Add …", "Fix …") of at most 72 characters, with no full stop at the end.
- By contributing, you agree that your work is released under the MIT License (see [LICENSE](LICENSE)).
