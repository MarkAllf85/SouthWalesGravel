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

INDEX = Path(__file__).resolve().parent.parent / "site" / "index.html"

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


def read_tokens(src, selector):
    m = re.search(re.escape(selector) + r"\s*\{(.*?)\n\}", src, re.S)
    if not m:
        raise SystemExit(f"could not find the {selector} block in site/index.html")
    return dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})", m.group(1)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true", help="print passing pairs too")
    args = ap.parse_args()

    src = INDEX.read_text(encoding="utf-8")
    themes = [("light", read_tokens(src, ":root")),
              ("dark", read_tokens(src, ':root[data-theme="dark"]'))]

    failures = []
    for label, tokens in themes:
        print(f"\n{label.upper()} THEME")
        missing = {t for pair in PAIRINGS for t in pair[:2]} - set(tokens)
        if missing:
            print(f"  note: token(s) not defined in this theme, skipped: {sorted(missing)}")
        for fg, bg, where, large in PAIRINGS:
            if fg not in tokens or bg not in tokens:
                continue
            r = contrast(tokens[fg], tokens[bg])
            need = 3.0 if large else 4.5
            ok = r >= need
            if not ok:
                failures.append(f"{label}: --{fg} on --{bg} is {r:.2f}:1, needs {need}:1 ({where})")
            if args.verbose or not ok:
                print(f"  {'ok' if ok else 'FAIL':<5}{r:5.2f}:1  need {need}  "
                      f"--{fg} on --{bg}   {where}")
        if not args.verbose and not any(f.startswith(label) for f in failures):
            print("  all pairings pass")

    print()
    if failures:
        for f in failures:
            print(f"  FAIL  {f}")
        print(f"\n{len(failures)} contrast failure(s).")
        return 1
    print(f"PASS. {len(PAIRINGS) * 2} pairing(s) checked across both themes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
