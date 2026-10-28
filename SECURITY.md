# Security policy

## Supported versions

Security fixes go into the latest release only. Please update before reporting: Settings shows your version
under **Fine-tuning → Updates**.

## Report a vulnerability privately

Please don't open a public issue for a security problem. Use GitHub's private reporting instead; no email
address is needed:

1. Open this repository's **Security** tab.
2. Click **Report a vulnerability**, describe the problem and how to reproduce it, and submit.

Only the maintainer sees the report. AirFare is a one-person project, so replies are best effort, usually within
a week. Fixes are released as soon as they are ready, and the advisory credits you unless you'd rather it didn't.

## In scope

- The Settings server (`127.0.0.1:8765`) and the extension's job server (`127.0.0.1:8766`): anything that lets a
  web page, another program or another user reach or change them.
- How API keys are stored (Windows DPAPI, the macOS Keychain, the Linux Secret Service), and anything that leaks
  them into pages, logs, reports or the release zip.
- Untrusted text (prices, airline names, web pages, analyst replies) that could run scripts or load content on
  AirFare's pages.
- The browser extension opening or reading anything other than the search result pages it is meant for.
- `airfare:` links, the launcher and the install scripts.

## Not in scope

- The price sites' or AI providers' own terms of use, robot checks or availability.
- Attacks that need someone who already controls your user account or your computer.
- Prices that are wrong or out of date: please open a normal bug report.
