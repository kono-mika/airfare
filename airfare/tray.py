"""A AirFare icon in the notification area (system tray), shown by the background checker when Settings asks
for it. Its menu shows when the last check ran and the next is due, runs a check now, opens the Dashboard,
Price history or Settings, and can quit the checker.

pystray draws the icon from assets/airfare-256.png (through Pillow). Without those packages AirFare simply
runs without an icon."""
from __future__ import annotations

import logging
import threading

from . import platform
from .config import PROJECT_DIR
from .i18n import tr

log = logging.getLogger(__name__)

try:
    import pystray
    from PIL import Image
except Exception:            # the packages are optional (see requirements.txt); a Linux without a desktop can't
    pystray = None           # show an icon either
    Image = None

ICON = PROJECT_DIR / "assets" / "airfare-256.png"


def available() -> bool:
    return pystray is not None and Image is not None and ICON.exists()


def open_page(page: str) -> None:
    """Open the Dashboard, Price history or Settings through AirFare's local server (started if needed)."""
    platform.start_detached([platform.background_python(), "-m", "airfare", "setup", "--page", page], PROJECT_DIR)


class Tray:
    """The icon and its menu. run() blocks (call it from the main thread); stop() ends it from any thread."""

    def __init__(self, lang: str | None, on_check, on_quit):
        self.lang, self.on_check, self.on_quit = lang, on_check, on_quit
        self.status = tr("AirFare is running.", lang)
        self.icon = pystray.Icon("AirFare", Image.open(ICON), "AirFare", menu=pystray.Menu(
            pystray.MenuItem(lambda item: self.status, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(tr("Check prices now", lang), self._check),
            pystray.MenuItem(tr("Dashboard", lang), lambda: open_page("dashboard"), default=True),
            pystray.MenuItem(tr("Price history", lang), lambda: open_page("history")),
            pystray.MenuItem(tr("Settings", lang), lambda: open_page("settings")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(tr("Quit AirFare", lang), self._quit),
        ))

    def set_status(self, text: str) -> None:
        self.status = text
        try:
            self.icon.update_menu()
        except Exception:            # the icon isn't up yet, or is already gone
            pass

    def _check(self) -> None:
        threading.Thread(target=self.on_check, daemon=True).start()

    def _quit(self) -> None:
        self.on_quit()
        self.stop()

    def run(self) -> None:
        self.icon.run()

    def stop(self) -> None:
        try:
            self.icon.stop()
        except Exception as e:
            log.debug("tray icon stop: %s", e)
