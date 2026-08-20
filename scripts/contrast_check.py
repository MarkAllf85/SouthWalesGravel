#!/usr/bin/env python3
"""
WCAG 2.2 contrast check for the site's colour tokens.

The map is dark by default with a light theme behind a toggle, which doubles
the number of foreground-on-background pairings and makes it easy for one of
them to drift below the threshold unnoticed. Six did: muted text failed on the
card hover state in both themes, white type on the accent orange managed only
3.20:1, and white on the dark-theme indigo only 3.84:1.

This reads the two :root blocks out of site/index.html and checks the pairings
that actually occur. The pairing table below is maintained by hand. A parser
that inferred pairings from the CSS would be a small, wrong CSS engine, and
would quietly stop noticing things the day someone nested a rule. Editing this
list when you change what sits on what is the price of it being trustworthy.

Thresholds are WCAG 2.2: 4.5:1 for normal text, 3:1 for large text (18.66px
bold or 24px plain) and for non-text graphics that carry meaning.

Usage:
    python scripts/contrast_check.py
    python scripts/contrast_check.py --verbose    # show passes too
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"

# Both pages carry their own copy of the token block. Checking only index.html
# is how faq.html kept a failing muted grey and a failing primary button through
# a pass that was supposed to have fixed exactly those two things. Any new page
# with its own :root belongs in this list on the day it is written.
PAGES = ["index.html", "faq.html"]

# (foreground token, background token, where it appears, is it large text or a graphic)
PAIRINGS = [
    ("text-primary",   "surface-1", "route names, stat values, detail panel", False),
    ("text-primary",   "surface-0", "search field text", False),
    ("text-secondary", "surface-1", "field labels, header count, card meta", False),
    ("text-secondary", "surface-0", "unpressed chip labels", False),
    ("text-muted",     "surface-1", "section headings, hints, stat keys, card type", False),
    ("text-muted",     "surface-2", "the same, on card hover and when selected", False),
    ("brand",          "surface-1", "wordmark first line", False),
    ("brand-ink",      "brand-fill", "pressed chips, primary buttons", False),
    ("accent-ink",     "accent",    "selected route badge", False),
    ("brand",          "surface-2", "slider fill against its track", True),
    ("accent",         "surface-1", "selected route accent border", True),
    ("brand",          "surface-0", "links in running text on the FAQ", False),
]


def _lin(c):
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hexcolour):
    h = hexcolour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def read_tokens(src, selector, page):
    m = re.search(re.escape(selector) + r"\s*\{(.*?)\n\}", src, re.S)
    if not m:
        raise SystemExit(f"could not find the {selector} block in site/{page}")
    return dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})", m.group(1)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true", help="print passing pairs too")
    args = ap.parse_args()

    failures = []
    checked = 0
    for page in PAGES:
        path = SITE / page
        if not path.exists():
            print(f"\n{page}: not found, skipped")
            continue
        src = path.read_text(encoding="utf-8")
        print(f"\n{'=' * 60}\n{page}\n{'=' * 60}")
        for label, selector in (("light", ":root"), ("dark", ':root[data-theme="dark"]')):
            tokens = read_tokens(src, selector, page)
            print(f"  {label.upper()} THEME")
            before = len(failures)
            for fg, bg, where, large in PAIRINGS:
                if fg not in tokens or bg not in tokens:
                    continue   # a page legitimately need not define every token
                checked += 1
                r = contrast(tokens[fg], tokens[bg])
                need = 3.0 if large else 4.5
                ok = r >= need
                if not ok:
                    failures.append(f"{page} {label}: --{fg} on --{bg} is "
                                    f"{r:.2f}:1, needs {need}:1 ({where})")
                if args.verbose or not ok:
                    print(f"    {'ok' if ok else 'FAIL':<5}{r:5.2f}:1  need {need}  "
                          f"--{fg} on --{bg}   {where}")
            if not args.verbose and len(failures) == before:
                print("    all pairings pass")

    print()
    if failures:
        for f in failures:
            print(f"  FAIL  {f}")
        print(f"\n{len(failures)} contrast failure(s).")
        return 1
    print(f"PASS. {checked} pairing(s) checked across {len(PAGES)} page(s) and both themes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
