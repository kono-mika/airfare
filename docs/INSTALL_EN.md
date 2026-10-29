# AirFare: install in 10 minutes

AirFare watches the flights you choose and shows a notification when one gets cheaper. It runs on Windows 10 and 11, macOS and Linux.

You need Google Chrome, Microsoft Edge, Brave, Opera or Mozilla Firefox (for Skyscanner and Aviasales prices) and an internet connection. An AI analyst (Claude, ChatGPT or DeepSeek) is optional: without one, AirFare still alerts on the cheapest and fastest fares by its own rules. Google Flights through SerpApi is optional too.

## 1. Unpack and start

1. Unzip **AirFare.zip** into a folder you'll keep, for example `Documents\AirFare` (not Downloads or a temporary folder).
2. Double-click **AirFare.exe**. If Windows says *"Windows protected your PC"*, click **More info**, then **Run anyway**. AirFare isn't signed by a publisher, so Windows asks once.
3. Click **OK** to set it up. A window shows the progress (about 5 minutes). If Python is missing, it offers to install it: type **Y**.

When setup finishes, AirFare adds icons to the desktop and Start menu, starts with Windows, and opens **Settings** in your browser. The next steps happen there.

**On a Mac or on Linux** there is no AirFare.exe. Unzip AirFare.zip into a folder you'll keep, open a terminal, type `cd ` (with a space), drag the AirFare folder into the terminal window, press Enter, then run `sh install.sh`. It needs Python 3.12 or newer: on a Mac without it, it offers to install it with Homebrew; on Linux it tells you which package to install (on Debian and Ubuntu, `sudo apt install python3 python3-venv`). When it finishes, AirFare is in your app menu (Linux) or in the Applications folder of your home folder (macOS), starts every time you log in, and opens **Settings** in your browser.

**Language:** switch between **EN**, **ES** and **RU** at the top right of any AirFare page, at any moment. Nothing you've typed is lost.

## 2. Choose your AI analyst (one is enough, or none)

**No analyst**: in **AI analyst**, choose **No analyst**. AirFare records every price, alerts on the cheapest and fastest fares and draws the dashboard; only the best-value pick, the analysis text and the lowest-price lookups need an analyst.

**Claude, with a Claude Pro or Max subscription**: in **AI analyst**, choose **Claude**, then **My Claude account**, press **Log in to Claude**, sign in in the window that opens, then press **Check again**.

**Claude, with an Anthropic API key** (pay as you go):

1. Sign in at [console.anthropic.com](https://console.anthropic.com), add credit under **Billing** and create a key under **API keys** (it starts with `sk-ant-`).
2. In **AI analyst**, choose **Claude**, then **An Anthropic API key**, paste the key and press **Save key**.

**ChatGPT, with your ChatGPT account** (Plus, Pro, Business and similar plans; no API key):

1. Install OpenAI's Codex app yourself: open PowerShell and run `irm https://chatgpt.com/codex/install.ps1 | iex` (OpenAI's own installer; see developers.openai.com/codex). On a Mac or on Linux, run `curl -fsSL https://chatgpt.com/codex/install.sh | sh` in a terminal instead. Check OpenAI's terms for using a ChatGPT plan through Codex from another program.
2. In **AI analyst**, choose **ChatGPT**, then **My ChatGPT account**.
3. Press **Log in to ChatGPT**, sign in in the browser that opens, then press **Check again**.

**ChatGPT, with an OpenAI API key** (pay as you go, about $0.04 a check with the recommended model):

1. Sign in at [platform.openai.com](https://platform.openai.com) and add credit under **Billing**.
2. Open [API keys](https://platform.openai.com/api-keys), press **Create new secret key** and copy it (it starts with `sk-`).
3. In **AI analyst**, choose **ChatGPT**, then **An OpenAI API key**, paste the key and press **Save key**.

**DeepSeek**, pay as you go (under $0.01 a check):

1. Sign up at [platform.deepseek.com](https://platform.deepseek.com) and add a few dollars under **Top up**.
2. Open **API keys**, press **Create new API key** and copy the key (it starts with `sk-`).
3. In **AI analyst**, choose **DeepSeek**, paste the key and press **Save key**. AirFare saves it and shows your balance.

## 3. Install the browser extension (Skyscanner and Aviasales)

1. In **Price sources**, tick **Skyscanner**, **Aviasales.ru** or both, and pick the browser the extension runs in: Chrome, Edge, Brave, Opera or Firefox. Both sites' terms of use don't allow automated visits; tick them only if that is acceptable to you. AirFare keeps their pages few: see **Limits** under *Good to know*.
2. In Chrome, Edge, Brave or Opera, open its extensions page (Settings shows the address, for example `chrome://extensions`, and copies it) and switch on **Developer mode**.
3. Click **Load unpacked** and choose the `extension` folder inside your AirFare folder.

The browser may remind you that a developer-mode extension is on. That's expected; keep it. Aviasales shows prices in rubles; AirFare converts them to your currency.

**In Firefox**, the extension has its own folder, `extension-firefox`, and two ways to load it:

- **To try it:** open `about:debugging#/runtime/this-firefox` (Settings shows the address and copies it), click **Load Temporary Add-on…** and choose `manifest.json` in the `extension-firefox` folder. Firefox removes it when it restarts.
- **To keep it:** sign it once as an unlisted add-on at addons.mozilla.org. It's free, and nothing is published:

1. Sign in at [addons.mozilla.org/developers](https://addons.mozilla.org/developers/) with a Mozilla account and accept the developer agreement.
2. Open PowerShell in your AirFare folder (in File Explorer, type `powershell` in the address bar and press Enter) and make the upload with an add-on id of your own. It looks like an email address, and nobody else may have signed it: `.venv\Scripts\python tools\make_firefox.py --zip --id airfare-collector@yourname.example`. This writes `dist\airfare-firefox-<version>.zip`. On a Mac or on Linux, run in a terminal in the AirFare folder: `.venv/bin/python tools/make_firefox.py --zip --id airfare-collector@yourname.example`.
3. Press **Submit a New Add-on**, choose **On your own**, upload the zip, tick only **Firefox** and press **Continue**. Answer **No** to the source code question and submit the version.
4. When the email says the add-on is signed (usually within minutes), open it under **My Add-ons**, open the version, and download the signed `.xpi` file.
5. In Firefox, open `about:addons`, click the gear, choose **Install Add-on From File…**, pick the `.xpi` and press **Add**. It stays installed when Firefox restarts.

When AirFare brings a new version of the add-on, repeat steps 2 to 5 with the same id, uploading the zip under **Upload New Version** on the add-on's page.

## 4. Optional: Google Flights through SerpApi

Only needed if you also want Google Flights prices. If you don't, skip this step: Skyscanner and Aviasales work without it.

1. Sign up at [serpapi.com](https://serpapi.com/users/sign_up) and confirm your email (and phone, if asked). The free plan gives about 250 searches a month.
2. Open [serpapi.com/manage-api-key](https://serpapi.com/manage-api-key) and copy your **API Key**.
3. In AirFare **Settings**, under **Price sources**, tick **Google Flights**. The **SerpApi key** field appears.
4. Paste the key and press **Save key**. AirFare saves it at once (no flight needed yet) and shows how many searches are left this month.

Each date combination uses one search per check. Under **When to check**, AirFare shows how many searches a month your schedule needs. To remove the key later, press **Remove saved key**.

## 5. Currency, flights and alerts

1. In **Currency**, pick Euro, Pound, Dollar or Ruble, or another currency under **Other**. Every price is compared and shown in it; prices a site shows in another currency are converted with the day's exchange rate.
2. In **Flights to track**, enter airport or city codes (LHR, BCN, LOND), a date or a range of dates, the adults and, if children travel, their ages (for example `4, 9`).
3. In **Price alerts**, set a threshold for each kind: **Cheapest**, **Fastest** and **Best value**. Each alerts when its price drops by your percentage, or falls to your price limit. You can also ignore very long trips or self-transfers.
4. Press **Save**, then **Test links**.

That's it. AirFare checks prices every time you start your computer (or on the schedule you choose) and shows a **LOW PRICE** notification when a price drops.

## 6. Update to a new version

An update keeps your settings, keys, routes, price history, conversations and everything else in the `data` folder. Before it changes anything there, AirFare makes a copy in `data\backups`.

1. In Settings, **Fine-tuning → Updates → Check for updates** tells you when a new version is out (Settings then shows these steps with the link).
2. Quit AirFare: tray icon → **Quit AirFare** (if you use the tray icon).
3. Download `AirFare.zip` from the [Releases](https://github.com/kono-mika/airfare/releases) page.
4. Unzip it into the **same** AirFare folder and choose to **replace the files**. Never into a new folder: your data stays in the old one.
5. Double-click **AirFare.exe**. It backs up your data, finishes the update in its setup window and opens Settings. If anything goes wrong, your data is untouched and the window says what to do.
   On a Mac or on Linux, run `sh install.sh` in the AirFare folder instead.
6. If Settings says the browser runs an older extension, reload it there (Firefox: sign and install the new `.xpi`).

- **Unzipped into a new folder by mistake?** Close both copies, move the `data` folder from the old folder into the new one, then start the new copy.
- **Going back:** unzip the previous version over the folder the same way. To return to your data as it was before an update, close AirFare and copy the files from a backup in `data\backups` into `data`.

## Good to know

- **Dashboard tabs:** each route has its own tab. If you change a route (for example turn it around), its earlier check stays on its own tab until you remove it.
- **Limits:** AirFare caps the Skyscanner and Aviasales pages it opens (both sites together). With **Personal** (the default), a check opens at most 20 of them, automatic checks open them at most once every 6 hours, and at most 60 a day, manual checks included. **Extended** allows 40 per check, every 3 hours and 150 a day, after a warning you confirm. Pick the level under **Fine-tuning → Limits**. Pages over a limit are left out and the dashboard says so; Google Flights (SerpApi) isn't limited.
- **Tray icon:** under **When to check**, tick *Keep a AirFare icon in the notification area* for an icon whose menu checks prices now, opens the pages and quits AirFare. On a Mac it's in the menu bar; on Linux it needs a desktop with a system tray.
- **Updates:** under **Fine-tuning → Updates**, press **Check for updates**; AirFare can also look once a day when Settings opens.
- **Export:** the **Price history** tab exports the records shown as a CSV file for Excel.
- **Clean up:** the **Clean up** tab deletes old prices, earlier dashboard routes, lookups, check reports and the log, resets alerts or starts fresh analyst conversations. Each button shows how much it deletes, and it can also clean up automatically after every check.
- **Privacy:** this package contains no keys, logins or price history. Everything you enter stays in the `data` folder on your PC; on Windows, your API keys are saved there encrypted for your Windows account (Windows DPAPI), so they can't be read from another account or PC. On a Mac they're kept in your Keychain, and on Linux in your keyring when `secret-tool` is installed (without it they stay in `data`, readable by your user only). Don't share that folder.
- **Another PC:** set it up from the AirFare zip, not from your installed folder.
- **Uninstall:** right-click `uninstall.ps1`, choose **Run with PowerShell**, then delete the AirFare folder. On a Mac or on Linux, run `sh uninstall.sh` in the AirFare folder, then delete the folder.
