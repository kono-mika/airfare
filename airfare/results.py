"""What one price-source page produced: the results feed the extension captured (or SerpApi's parsed
flights), the page text, and how the fetch went."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

EXTRA_WAIT = 15          # seconds to keep waiting when the results feed says it is still loading
ROBOT_WAIT = int(os.environ.get("AIRFARE_ROBOT_WAIT", 180))  # seconds the user gets to solve a robot check; 0 = never ask


@dataclass
class PageResult:
    page: dict                                   # one entry from urls.plan_pages()
    status: str = "pending"                      # ok | no_results | blocked | error
    note: str = ""
    payloads: list = field(default_factory=list)  # results-feed JSON bodies, in arrival order
    text: str = ""                               # visible results text, used when no feed was captured
    final_url: str = ""
    seconds: float = 0.0
    source: str = "Skyscanner"                   # where the prices came from, shown in the report
    parsed: object = None                        # an extract.ParsedPage when the source parsed it already


PRICE_MARKS = ("£", "€", "$", "zł", "kr", "CHF", "¥", "₹", "R$")


def classify(res: PageResult) -> None:
    """Set ok / no_results for a page that loaded without a robot check."""
    if res.payloads or any(m in res.text for m in PRICE_MARKS):
        res.status = "ok"
    else:
        res.status, res.note = "no_results", res.note or "no prices found on the page"
