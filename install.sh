#!/bin/sh
# AirFare setup on macOS and Linux: Python 3.12+ (found, or installed with Homebrew on a Mac), AirFare's own
# Python environment and packages, AirFare in the app menu (Linux, where that entry also opens airfare: links)
# or in ~/Applications (macOS), its background checker at every login (an XDG autostart entry on Linux, a
# LaunchAgent on macOS), then a health check. Run it from the AirFare folder:  sh install.sh
# --quiet: no questions and no Settings page at the end (for scripted installs).
# (On Windows, AirFare.exe runs install.ps1 instead.)
# To update, extract a new release into the folder that contains this one and run this again: the previous
# version's background checker and Settings server stop, files it left behind go (MANIFEST.txt), the packages
# update, the data is backed up and migrated (airfare/migrate.py), and the checker starts again. The data folder is
# never deleted. Only one runs at a time: .venv/airfare-install.lock holds its process id from start to end, and
# python -m airfare says that AirFare is being updated while it does. A copy unzipped inside an AirFare folder stops
# before anything.
set -u
cd "$(dirname "$0")" || exit 1
root=$(pwd -P)
quiet=0
[ "${1:-}" = "--quiet" ] && quiet=1
version=$(sed -n 's/^__version__ = "\([^"]*\)".*/\1/p' "$root/airfare/__init__.py" 2>/dev/null)
# What a failed update says: nothing in the data folder has changed, and how to try again or go back.
untouched="Your data is untouched. Fix the problem above and run  sh install.sh  again, or go back by extracting the previous release into the folder that contains this one."
system=$(uname -s)

step() { printf '\n\033[36m== %s\033[0m\n' "$1"; }
finish() {
    release_lock       # before waiting for Enter: this window staying open is no reason to hold anything up
    if [ "$quiet" = 0 ] && [ -t 0 ]; then printf '\nPress Enter to close. '; read -r _; fi
    exit "$1"
}
fail() { printf '\n\033[31m%s\033[0m\n' "$1"; finish 1; }

# The language picked in that folder's Settings; before setup, the system's.
language_of() {
    found=$(sed -n 's/.*"language"[[:space:]]*:[[:space:]]*"\([a-z][a-z]\)".*/\1/p' "$1/data/config.json" 2>/dev/null | head -n 1)
    [ -n "$found" ] || found=$(printf '%s' "${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}" | cut -c1-2)
    echo "$found"
}
pick() { case "$language" in es) echo "$2" ;; ru) echo "$3" ;; *) echo "$1" ;; esac; }

# One installer at a time, for the whole run (no lock command is on every Mac and Linux, so: the file holds this
# process's id, made so that only one can create it; one whose process is gone, or that is hours old, is left over).
lock="$root/.venv/airfare-install.lock"
take_lock() {
    mkdir -p "$root/.venv" 2>/dev/null || return 0     # the steps below will say what's wrong
    ( set -C; echo "$$" > "$lock" ) 2>/dev/null && return 0
    [ -e "$lock" ] || return 0
    holder=$(cat "$lock" 2>/dev/null)
    [ -n "$holder" ] || { sleep 1; holder=$(cat "$lock" 2>/dev/null); }
    case "$holder" in ""|*[!0-9]*) ;; *)
        if kill -0 "$holder" 2>/dev/null && [ -z "$(find "$lock" -mmin +180 2>/dev/null)" ]; then return 1; fi ;;
    esac
    rm -f "$lock"
    ( set -C; echo "$$" > "$lock" ) 2>/dev/null
}
release_lock() {
    if [ "$(cat "$lock" 2>/dev/null)" = "$$" ]; then rm -f "$lock"; fi
}
# Everything in .venv but the lock, so that it stays held while the environment is made again.
clear_venv() {
    find "$root/.venv" -mindepth 1 -maxdepth 1 ! -name airfare-install.lock -exec rm -rf {} +
}

# A copy unzipped inside an AirFare folder (the zip has a top-level AirFare folder): stop before anything is
# installed, and leave both folders' data alone.
outer=$(dirname "$root")
if [ "$outer" != "$root" ] && [ -f "$outer/airfare/__init__.py" ] && [ -d "$outer/data" ]; then
    language=$(language_of "$outer")
    above=$(dirname "$outer")
    name=$(basename "$outer")
    text=$(pick "This copy was unzipped inside your AirFare folder. Delete this inner folder and extract the zip into $above instead." \
                "Esta copia se descomprimió dentro de tu carpeta de AirFare. Borra esta carpeta interior y extrae el zip en $above." \
                "Эта копия распакована внутри вашей папки AirFare. Удалите эту внутреннюю папку и извлеките архив в $above.")
    same=$name
    [ "$system" = Darwin ] && same=$(printf '%s' "$name" | tr 'a-z' 'A-Z' | sed 's/^AIRFARE$/AirFare/')
    if [ "$same" != AirFare ]; then
        text="$text
$(pick "Your AirFare folder is called $name. The zip makes a folder called AirFare, so rename yours to AirFare first." \
       "Tu carpeta de AirFare se llama $name. El zip crea una carpeta llamada AirFare, así que antes cambia el nombre de la tuya a AirFare." \
       "Ваша папка AirFare называется $name. Архив создаёт папку с именем AirFare, поэтому сначала переименуйте свою в AirFare.")"
    fi
    if [ -d "$root/data" ]; then
        text="$text
$(pick "This inner folder has a data folder of its own. If it holds settings or prices you want to keep, move it somewhere safe first." \
       "Esta carpeta interior tiene su propia carpeta data. Si guarda ajustes o precios que quieras conservar, muévela antes a un lugar seguro." \
       "Во внутренней папке есть своя папка data. Если в ней есть нужные настройки или цены, сначала перенесите её в надёжное место.")"
    fi
    fail "$text
$root"
fi

if ! take_lock; then
    language=$(language_of "$root")
    fail "$(pick "AirFare is being updated, try again in a few minutes" \
                 "AirFare se está actualizando; inténtalo de nuevo en unos minutos" \
                 "AirFare обновляется, попробуйте ещё раз через несколько минут")"
fi
trap release_lock EXIT
trap 'exit 1' HUP INT TERM

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
    clear_venv
fi
if [ ! -e "$venv_py" ]; then
    if ! "$python" -m venv "$root/.venv" || ! "$venv_py" -m pip --version >/dev/null 2>&1; then
        clear_venv
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
# From here on the data has been brought up to this version: "untouched" no longer holds.
untouched="Your data is kept and backed up in data/backups. Fix the problem above and run  sh install.sh  again, or go back by extracting the previous release into the folder that contains this one."

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
release_lock           # python -m airfare would otherwise see it held and say AirFare is being updated
nohup "$venv_py" -m airfare setup >/dev/null 2>&1 &
finish 0
