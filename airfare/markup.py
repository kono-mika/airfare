"""Markdown to HTML for text AirFare doesn't control: the analyst's replies, which echo flight data and web pages.

Raw HTML in the text is shown as text, not run, and links keep only web, mail and in-page addresses. So a
reply can format itself (headings, lists, tables, links) but can't put a script or a javascript: link on a
AirFare page. Images become their description: a page opened from disk would otherwise fetch them from
whatever server the text names, telling it the reader's address.
"""
from __future__ import annotations

import markdown
from markdown.treeprocessors import Treeprocessor

SAFE_SCHEMES = ("http://", "https://", "mailto:", "#")


class _SafeLinks(Treeprocessor):
    def run(self, root):
        for el in root.iter():
            if el.tag == "img":
                alt = el.get("alt") or ""
                el.tag, el.text = "span", alt
                el.attrib.clear()
                continue
            value = el.get("href")
            if value is not None and not value.strip().lower().startswith(SAFE_SCHEMES):
                del el.attrib["href"]


def to_html(text: str) -> str:
    md = markdown.Markdown(extensions=["tables"])
    md.preprocessors.deregister("html_block")
    md.inlinePatterns.deregister("html")
    md.treeprocessors.register(_SafeLinks(md), "safe_links", 0)
    return md.convert(text)
