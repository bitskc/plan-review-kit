#!/usr/bin/env python3
"""Make a generated gstack design board readable without browser zoom.

gstack's `design compare` board hardcodes 12-16px chrome and no root font-size,
which is small on a 1080p / 96dpi screen. Its variant images are also capped at
`width:100%` inside a 3-up grid on a 1400px container, so a 1240px-wide page
screenshot lands about a third of its natural size and its text becomes
unreadable.

This appends one override <style> block (and nothing else) to the generated
board HTML. It never edits the gstack skill or binary, only the artifact under
~/.gstack/.../designs/. Re-running replaces the previous override rather than
stacking copies, so it is safe to run after every republish.

Usage
-----
    bump_board_text.py BOARD.html [--base 17] [--columns 1] [--max-width 1600]
    bump_board_text.py ~/.gstack/projects/*/designs/*/design-board.html

    --base       root font size in px for the board chrome (default 17)
    --columns    variant grid columns in grid view; 1 or 2 makes each image
                 much larger (default 2; gstack ships 3)
    --max-width  container width in px (default 1600; gstack ships 1400)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

START = "<!-- plan-review-kit:text-size:start -->"
END = "<!-- plan-review-kit:text-size:end -->"


def override_css(base: int, columns: int, max_width: int) -> str:
    return f"""{START}
<style>
/* plan-review-kit readability override.
   Scales the board chrome up from gstack's 12-16px defaults and widens the
   variant grid so screenshot text is legible without zooming. */
html {{ font-size: {base}px; }}
body {{ font-size: 1rem; line-height: 1.55; }}
.variants {{ max-width: {max_width}px !important; }}
.variants.grid-view, .grid-view {{
  grid-template-columns: repeat({columns}, 1fr) !important;
}}
.header h1 {{ font-size: 1.5rem !important; }}
.header .meta, .variant-desc, .pick-confirm {{ font-size: .93rem !important; }}
.pick-label, .submit-status, .submit-btn, .submit-column label {{ font-size: 1rem !important; }}
.variant-label, .submit-column h3 {{ font-size: 1.12rem !important; }}
.view-toggle button {{ font-size: .9rem !important; padding: .4rem .8rem !important; }}
.star {{ font-size: 1.6rem !important; }}
textarea, input, select, button {{ font-size: 1rem !important; }}
textarea {{ line-height: 1.5 !important; min-height: 6rem !important; }}
/* Images: let a tall page screenshot render at natural width instead of being
   squeezed to a third of it. */
.variant img {{ width: 100% !important; max-width: none !important; image-rendering: auto; }}
</style>
{END}"""


def patch(path: Path, base: int, columns: int, max_width: int) -> str:
    html = path.read_text()
    existing = re.search(re.escape(START) + r".*?" + re.escape(END), html, re.S)
    block = override_css(base, columns, max_width)

    if existing:
        html = html[: existing.start()] + block + html[existing.end() :]
        action = "updated"
    elif "</body>" in html:
        idx = html.rindex("</body>")
        html = html[:idx] + block + "\n" + html[idx:]
        action = "inserted"
    else:
        html = html + "\n" + block
        action = "appended"

    path.write_text(html)
    return action


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("boards", nargs="+", type=Path)
    ap.add_argument("--base", type=int, default=17)
    ap.add_argument("--columns", type=int, default=2)
    ap.add_argument("--max-width", type=int, default=1600)
    args = ap.parse_args(argv[1:])

    if not 12 <= args.base <= 30:
        print("error: --base should be 12-30", file=sys.stderr)
        return 2

    rc = 0
    for board in args.boards:
        if not board.is_file():
            print(f"skip (not a file): {board}", file=sys.stderr)
            rc = 1
            continue
        action = patch(board, args.base, args.columns, args.max_width)
        print(f"{action}: {board}  (base={args.base}px, columns={args.columns})")
    if rc == 0:
        print("\nReload the board in your browser. gstack rewrites this file on every")
        print("republish, so re-run this after each `design compare`.")
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
