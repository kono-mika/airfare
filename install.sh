#!/bin/sh
# AirFare setup on macOS and Linux: Python 3.12+ (found, or installed with Homebrew on a Mac), AirFare's own
# Python environment and packages, AirFare in the app menu (Linux, where that entry also opens airfare: links)
# or in ~/Applications (macOS), its background checker at every login (an XDG autostart entry on Linux, a
# LaunchAgent on macOS), then a health check. Run it from the AirFare folder:  sh install.sh
# --quiet: no questions and no Settings page at the end (for scripted installs).
# (On Windows, AirFare.exe runs install.ps1 instead.)
# To update, unzip a new release over this folder and run this again: the previous version's background
# checker and Settings server stop, files it left behind go (MANIFEST.txt), the packages update, the data is
# backed up and migrated (airfare/migrate.py), and the checker starts again. The data folder is never deleted.
set -u
cd "$(dirname "$0")" || exit 1
root=$(pwd -P)
quiet=0
[ "${1:-}" = "--quiet" ] && quiet=1
version=$(sed -n 's/^__version__ = "\([^"]*\)".*/\1/p' "$root/airfare/__init__.py" 2>/dev/null)
# What a failed update says: nothing in the data folder has changed, and how to try again or go back.
untouched="Your data is untouched. Fix the problem above and run  sh install.sh  again, or go back by unzipping the previous release over this folder."
system=$(uname -s)

step() { printf '\n\033[36m== %s\033[0m\n' "$1"; }
finish() {
    if [ "$quiet" = 0 ] && [ -t 0 ]; then printf '\nPress Enter to close. '; read -r _; fi
    exit "$1"
}
fail() { printf '\n\033[31m%s\033[0m\n' "$1"; finish 1; }

# A Python 3.12+ interpreter: a versioned one on PATH, Homebrew's, python.org's, or python3.
find_python() {
    probe='import sys; print(sys.executable if sys.version_info >= (3, 12) else "")'
    for py in python3.14 python3.13 python3.12 /opt/homebrew/bin/python3 /usr/local/bin/python3 \
              /Library/Frameworks/Python.framework/Versions/3.1[2-9]/bin/python3 python3 python; do
        exe=$(command -v "$py" 2>/dev/null) || continue
        # On a Mac without the developer tools, /usr/bin/python3 only offers to install them (in a window).
        if [ "$system" = Darwin ] && [ "$exe" = /usr/bin/python3 ] && ! xcode-select -p >/dev/null 2>&1; then
            continue
        fi
        out=$("$exe" -c "$probe" 2>/dev/null) && [ -n "$out" ] && { echo "$out"; return 0; }
    done
    return 1
}

echo "Setting up AirFare $version in $root"

step "Python"
python=$(find_python)
if [ -z "$python" ]; then
    echo "AirFare needs Python 3.12 or newer, and it isn't installed on this computer."
    if [ "$system" = Darwin ]; then
        brew=$(command -v brew || ls /opt/homebrew/bin/brew /usr/local/bin/brew 2>/dev/null | head -n 1)
        if [ "$quiet" = 0 ] && [ -n "$brew" ]; then
            echo "AirFare can install Python 3.13 (free, from python.org's sources) with Homebrew."
            printf "Install Python 3.13 now? [Y/n] "
            read -r answer
            case "$answer" in ""|[yY]*) "$brew" install python@3.13 && python=$(find_python) ;; esac
        fi
        [ -n "$python" ] || fail "Install Python from https://www.python.org/downloads/macos/ (or: brew install python@3.13), then run  sh install.sh  again."
    else
        fail "Install Python 3.12 or newer with your system's packages, then run  sh install.sh  again:
  Debian, Ubuntu:  sudo apt install python3 python3-venv
  Fedora:          sudo dnf install python3
  Arch:            sudo pacman -S python"
    fi
fi
echo "Using $python"

step "AirFare's Python environment"
venv_py="$root/.venv/bin/python"
# A .venv copied from another computer points at that computer's Python; start a fresh one if this one
# doesn't run (or has no pip, as when Debian's venv module was missing the first time).
if [ -e "$venv_py" ] && ! "$venv_py" -m pip --version >/dev/null 2>&1; then
    echo "The existing environment doesn't work here; making a new one."
    rm -rf "$root/.venv"
fi
if [ ! -e "$venv_py" ]; then
    if ! "$python" -m venv "$root/.venv" || ! "$venv_py" -m pip --version >/dev/null 2>&1; then
        rm -rf "$root/.venv"
        fail "Couldn't create AirFare's Python environment in $root/.venv.
On Debian and Ubuntu, install Python's venv module first:  sudo apt install python3-venv"
    fi
fi
# A background checker or Settings page still running the previous version, and files the previous version had
# but this one doesn't: both are handled before pip runs.
"$venv_py" -m airfare.upgrade prepare ||
    printf '\033[33m%s\033[0m\n' "Couldn't stop the previous version everywhere; quit AirFare (tray icon, Quit AirFare) if the next step fails."
echo "Installing packages. This takes a few minutes (the Claude Agent SDK is about 130 MB)..."
"$venv_py" -m pip install --upgrade pip --quiet --disable-pip-version-check
"$venv_py" -m pip install -r "$root/requirements.txt" --quiet --disable-pip-version-check ||
    fail "Installing packages failed. Check the internet connection. $untouched"

step "Your data"
# Backed up to data/backups first, then brought up to this version's format; on any problem it is put back.
"$venv_py" -m airfare migrate || fail "Updating the data folder failed. $untouched"

step "App entry and start at login"
"$venv_py" -c '
from airfare import links, platform
from airfare.config import PROJECT_DIR
try:
    print("Added", platform.add_app_entry(PROJECT_DIR))
except Exception as e:
    print("Could not add AirFare to the apps:", e)
if platform.LINUX:
    print("airfare: links open AirFare" if links.register() else
          "airfare: links are not set up (is xdg-utils installed?); notifications open the dashboard file instead")
print("Added", platform.add_login_item(PROJECT_DIR))
' || printf '\033[33m%s\033[0m\n' "Couldn't add AirFare's app entry or its start at login."
# Records what is installed (python -m airfare compares it with the code) and starts the background checker
# again if the settings need it running.
"$venv_py" -m airfare.upgrade finish || fail "Finishing the setup failed. $untouched"

step "Health check"
"$venv_py" -m airfare doctor

echo
if [ "$quiet" = 1 ]; then printf '\033[32mAirFare is installed.\033[0m\n'; exit 0; fi
printf '\033[32m%s\033[0m\n' "AirFare is installed. Its Settings page is opening in your browser (http://127.0.0.1:8765/)."
echo "There, in this order:"
echo "  1. AI analyst: log in to Claude or ChatGPT, paste an API key, or choose 'No analyst'."
echo "  2. Price sources: load the browser extension (steps shown there) and/or paste a SerpApi key."
echo "  3. Add your flights, press Save, then Test links."
if [ "$system" = Darwin ]; then where="AirFare in your Applications folder (~/Applications)"; else where="AirFare in your app menu"; fi
echo "Later, open $where. It checks prices by itself every time you log in."
nohup "$venv_py" -m airfare setup >/dev/null 2>&1 &
finish 0
