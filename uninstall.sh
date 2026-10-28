#!/bin/sh
# Removes AirFare from this computer's login items, app menu (Linux) or Applications (macOS) and airfare: links,
# and stops its background checker. Your settings, keys, reports and history in ./data are kept (and API keys in
# your keychain, under "AirFare"): delete the AirFare folder to remove them too.
# Run it from the AirFare folder:  sh uninstall.sh
set -u
cd "$(dirname "$0")" || exit 1
root=$(pwd -P)

if [ "$(uname -s)" = Darwin ]; then
    agent="$HOME/Library/LaunchAgents/AirFare.FlightPrices.plist"
    if [ -e "$agent" ]; then
        launchctl bootout "gui/$(id -u)/AirFare.FlightPrices" 2>/dev/null
        rm -f "$agent" && echo "Removed $agent"
    fi
    app="$HOME/Applications/AirFare.app"
    if [ -d "$app" ]; then rm -rf "$app" && echo "Removed $app"; fi
else
    autostart="${XDG_CONFIG_HOME:-$HOME/.config}/autostart/airfare.desktop"
    if [ -e "$autostart" ]; then rm -f "$autostart" && echo "Removed $autostart"; fi
    entry="${XDG_DATA_HOME:-$HOME/.local/share}/applications/airfare.desktop"
    if [ -e "$entry" ]; then
        rm -f "$entry" && echo "Removed $entry (AirFare in the app menu, and airfare: links)"
        if command -v update-desktop-database >/dev/null 2>&1; then update-desktop-database "$(dirname "$entry")" 2>/dev/null; fi
    fi
fi

# AirFare's own Python processes (background checker, settings server), started as python -m airfare <command>.
ps -u "$(id -u)" -o pid= -o args= | while read -r pid command; do
    case "$command" in
        *" -m airfare service"*|*" -m airfare setup"*|*" -m airfare run"*|*" -m airfare link"*)
            kill "$pid" 2>/dev/null && echo "Stopped AirFare process $pid" ;;
    esac
done

echo
echo "AirFare no longer starts at login. To remove everything, delete the folder $root"
if [ "$(uname -s)" = Darwin ]; then
    echo "API keys saved in Settings stay in your login Keychain (entries named AirFare); Keychain Access can remove them."
elif command -v secret-tool >/dev/null 2>&1; then
    echo "API keys saved in Settings stay in your keyring; remove them with:  secret-tool clear service AirFare"
fi
echo "In your browser, you can also remove 'AirFare collector' from its extensions page (about:addons in Firefox)."
if [ -t 0 ]; then printf 'Press Enter to close. '; read -r _; fi
