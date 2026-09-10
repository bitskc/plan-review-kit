#!/usr/bin/env python3
"""Turn markdown plan documents into one commentable HTML review board.

Stdlib only. No browser automation, no network, no API keys. The output is a
single self-contained HTML file: a sticky section index, the rendered plan, a
comment box per section, and an Export button that writes reviewer comments to
JSON (also copied to the clipboard). Comments persist in localStorage, so a
reviewer can close the tab and come back.

Usage
-----
    plan_review_board.py OUT.html DOC.md [DOC.md ...]
    plan_review_board.py OUT.html --split-h2 DOC.md      # one section per H2
    plan_review_board.py OUT.html --title "My plan" DOC.md

    # explicit sections: LABEL=FILE:START-END (1-indexed, END may be "end")
    plan_review_board.py OUT.html \
        "Why=proposal.md:1-57" \
        "Decisions=design.md:49-102"

Serve it with:  python3 -m http.server 8899 --directory <dir>
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# markdown -> html (only the constructs real plan docs use)
# --------------------------------------------------------------------------

_LIST_RE = re.compile(r"^(\s*)([-*]|\d+\.) (.*)$")
_HEAD_RE = re.compile(r"^(#{1,4}) (.*)$")
_TABLE_SEP_RE = re.compile(r"^\|[\s\-:|]+\|?\s*$")


def inline(s: str) -> str:
    """Escape, then apply inline code/bold/italic.

    Code spans are swapped for placeholders BEFORE emphasis runs, so bold that
    wraps a code span (``**see `foo`**``) still resolves. Splitting on backticks
    first would leave the ``**`` markers stranded in separate fragments.
    """
    s = html.escape(s)
    spans: list[str] = []

    def stash(m: re.Match[str]) -> str:
        spans.append(m.group(1))
        return f"\x00{len(spans) - 1}\x00"

    s = re.sub(r"`([^`]+)`", stash, s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<i>\1</i>", s)
    return re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{spans[int(m.group(1))]}</code>", s)


def md_to_html(md: str) -> str:
    lines = md.split("\n")
    out: list[str] = []
    stack: list[str] = []
    i = 0

    def close_lists(to: int = 0) -> None:
        while len(stack) > to:
            out.append(f"</{stack.pop()}>")

    while i < len(lines):
        line = lines[i]

        if line.strip().startswith("```"):
            close_lists()
            i += 1
            buf = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(html.escape(lines[i]))
                i += 1
            i += 1
            out.append("<pre>" + "\n".join(buf) + "</pre>")
            continue

        m = _HEAD_RE.match(line)
        if m:
            close_lists()
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>")
            i += 1
            continue

        if line.startswith("|") and i + 1 < len(lines) and _TABLE_SEP_RE.match(lines[i + 1]):
            close_lists()
            hdr = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            th = "".join(f"<th>{inline(c)}</th>" for c in hdr)
            tb = "".join(
                "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows
            )
            out.append(f"<table><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table>")
            continue

        m = _LIST_RE.match(line)
        if m:
            depth = len(m.group(1)) // 2
            kind = "ol" if m.group(2)[0].isdigit() else "ul"
            while len(stack) > depth + 1:
                out.append(f"</{stack.pop()}>")
            if len(stack) < depth + 1:
                stack.append(kind)
                out.append(f"<{kind}>")
            body = m.group(3)
            j = i + 1
            # absorb wrapped continuation lines
            while (
                j < len(lines)
                and lines[j].strip()
                and lines[j].startswith("  ")
                and not _LIST_RE.match(lines[j])
                and not _HEAD_RE.match(lines[j])
            ):
                body += " " + lines[j].strip()
                j += 1
            out.append(f"<li>{inline(body)}</li>")
            i = j
            continue

        if not line.strip():
            close_lists()
            i += 1
            continue

        close_lists()
        para = [line]
        j = i + 1
        while j < len(lines) and lines[j].strip() and not re.match(
            r"^(#{1,4} |\||\s*([-*]|\d+\.) |```)", lines[j]
        ):
            para.append(lines[j])
            j += 1
        out.append("<p>" + inline(" ".join(para)) + "</p>")
        i = j

    close_lists()
    return "\n".join(out)


# --------------------------------------------------------------------------
# section selection
# --------------------------------------------------------------------------


def slice_lines(text: str, start: int, end: int | None) -> str:
    lines = text.split("\n")
    return "\n".join(lines[start - 1 : (end - 1 if end else len(lines))])


def first_heading(chunk: str, fallback: str) -> str:
    for line in chunk.split("\n"):
        m = _HEAD_RE.match(line)
        if m:
            return m.group(2).strip()
    return fallback


def sections_from_h2(paths: list[Path]) -> list[tuple[str, Path, int, int | None]]:
    out = []
    for p in paths:
        lines = p.read_text().split("\n")
        marks = [n for n, line in enumerate(lines, 1) if re.match(r"^## ", line)]
        if not marks:
            out.append((first_heading(p.read_text(), p.stem), p, 1, None))
            continue
        if marks[0] > 1:
            out.append((first_heading("\n".join(lines[: marks[0] - 1]), p.stem), p, 1, marks[0]))
        for idx, start in enumerate(marks):
            end = marks[idx + 1] if idx + 1 < len(marks) else None
            title = lines[start - 1].lstrip("# ").strip()
            out.append((title, p, start, end))
    return out


def parse_spec(spec: str, root: Path) -> tuple[str, Path, int, int | None]:
    label, _, target = spec.partition("=")
    if not target:
        raise SystemExit(f"bad section spec {spec!r}; want LABEL=FILE:START-END")
    fname, _, rng = target.partition(":")
    path = (root / fname).resolve()
    if not path.is_file():
        raise SystemExit(f"no such file: {path}")
    if not rng:
        return label, path, 1, None
    start_s, _, end_s = rng.partition("-")
    end = None if end_s in ("", "end") else int(end_s)
    return label, path, int(start_s), end


# --------------------------------------------------------------------------
# page
# --------------------------------------------------------------------------

CSS = """
/* One knob controls every size. 17px default measured comfortable on a
   1920x1080 / 96dpi laptop with no desktop scaling; the A-/A+ control writes
   --base and persists it, so no reviewer has to zoom the browser. */
:root{--base:17px}
html{font-size:var(--base);-webkit-text-size-adjust:100%;text-size-adjust:100%}
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,system-ui,sans-serif;
  background:#f6f7f9;color:#101828;font-size:1rem;line-height:1.6;display:flex;align-items:flex-start}
nav{position:sticky;top:0;flex:0 0 21rem;max-height:100vh;overflow-y:auto;padding:1.1rem .9rem;
  background:#fff;border-right:1px solid #e4e7ec}
nav h2{font-size:.75rem;text-transform:uppercase;letter-spacing:.5px;color:#667085;margin:0 0 .6rem}
nav a{display:block;padding:.42rem .55rem;border-radius:7px;color:#1d2939;text-decoration:none;font-size:.84rem}
nav a:hover{background:#f2f4f7}
nav a b{display:inline-block;width:1.5rem;color:#3538cd}
nav a span{display:block;margin-left:1.5rem;color:#98a2b3;font-size:.7rem;font-family:ui-monospace,monospace}
nav a.done b{color:#079455}
main{flex:1;min-width:0;max-width:64rem;padding:0 1.6rem 5rem}
.hdr{padding:1.6rem .25rem 0}
.hdr h1{font-size:1.7rem;margin:0 0 .25rem;line-height:1.25}
.hdr p{color:#475467;margin:0;font-size:.95rem}
.bar{position:sticky;top:0;z-index:5;display:flex;gap:.55rem;align-items:center;flex-wrap:wrap;
  background:#f6f7f9;padding:.85rem .25rem;margin-top:.85rem;border-bottom:1px solid #e4e7ec}
button{font:inherit;font-weight:600;font-size:.84rem;border-radius:8px;padding:.5rem .8rem;cursor:pointer;
  border:1px solid #d0d5dd;background:#fff;color:#1d2939;min-height:2.3rem}
button.primary{background:#3538cd;border-color:#3538cd;color:#fff}
button:hover{filter:brightness(.97)}
.zoom{display:flex;gap:.3rem;align-items:center;margin-left:.4rem}
.zoom button{min-width:2.3rem;padding:.5rem .6rem;font-size:.95rem;line-height:1}
.zoom span{color:#667085;font-size:.78rem;min-width:3.1rem;text-align:center}
.count{margin-left:auto;color:#475467;font-size:.84rem}
section{background:#fff;border:1px solid #e4e7ec;border-radius:12px;padding:1.4rem 1.6rem;margin:1.1rem 0}
.shead{display:flex;justify-content:space-between;align-items:center;gap:.75rem;margin-bottom:.4rem}
.tag{display:inline-block;background:#eef4ff;color:#3538cd;border:1px solid #c7d7fe;border-radius:999px;
  padding:.18rem .6rem;font-size:.72rem;font-weight:700;letter-spacing:.3px;text-transform:uppercase}
.src{font-size:.72rem;color:#98a2b3;font-family:ui-monospace,monospace}
section h1{font-size:1.4rem;margin:.25rem 0 .75rem;line-height:1.3}
section h2{font-size:1.18rem;margin:1.25rem 0 .4rem;padding-bottom:.3rem;border-bottom:1px solid #eaecf0}
section h3{font-size:1.02rem;margin:1rem 0 .3rem}
section h4{font-size:.8rem;margin:.8rem 0 .25rem;color:#475467;text-transform:uppercase;letter-spacing:.3px}
p{margin:.45rem 0}
ul,ol{margin:.4rem 0;padding-left:1.4rem}
li{margin:.2rem 0}
code{background:#f2f4f7;border:1px solid #eaecf0;border-radius:4px;padding:.05rem .3rem;
  font-size:.87em;font-family:ui-monospace,monospace}
pre{background:#0c111d;color:#e4e7ec;border-radius:9px;padding:.8rem;overflow-x:auto;
  font-size:.84rem;font-family:ui-monospace,monospace;line-height:1.5}
pre code{background:none;border:0;color:inherit;padding:0;font-size:1em}
table{border-collapse:collapse;width:100%;margin:.7rem 0;font-size:.88rem}
th{background:#f9fafb;text-align:left;padding:.45rem .55rem;border:1px solid #eaecf0;font-weight:600}
td{padding:.45rem .55rem;border:1px solid #eaecf0;vertical-align:top}
.fb{margin-top:1.1rem;border-top:1px dashed #d0d5dd;padding-top:.9rem}
.fb label{display:block;font-size:.75rem;font-weight:700;text-transform:uppercase;
  letter-spacing:.4px;color:#667085;margin-bottom:.35rem}
.fb textarea{width:100%;min-height:5rem;resize:vertical;font:inherit;font-size:.94rem;padding:.6rem .7rem;
  border:1px solid #d0d5dd;border-radius:9px;background:#fcfcfd;line-height:1.5}
.fb textarea:focus{outline:2px solid #b2ccff;border-color:#84adff}
.verdicts{display:flex;gap:.45rem;margin-top:.55rem;flex-wrap:wrap}
.verdicts button.on[data-v="ok"]{background:#dcfae6;border-color:#75e0a7;color:#05603a}
.verdicts button.on[data-v="concern"]{background:#fef0c7;border-color:#fdb022;color:#7a2e0e}
.verdicts button.on[data-v="block"]{background:#fee4e2;border-color:#fda29b;color:#912018}
dialog{border:1px solid #d0d5dd;border-radius:12px;padding:0;max-width:48rem;width:92vw}
dialog form{padding:1.2rem 1.3rem}
dialog h3{margin:0 0 .6rem;font-size:1.1rem}
dialog textarea{width:100%;height:44vh;font-family:ui-monospace,monospace;font-size:.8rem;
  border:1px solid #d0d5dd;border-radius:9px;padding:.7rem}
@media (max-width:900px){body{display:block}nav{position:static;max-height:none;flex:none;
  border-right:0;border-bottom:1px solid #e4e7ec}main{max-width:none;padding:0 .9rem 4rem}}
"""

JS = """
const KEY = 'planreview:' + (document.body.dataset.planid || location.pathname);
const load = () => { try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch { return {}; } };
let state = load();

/* Text size. Persisted globally, not per plan, because it is a property of the
   reader's screen rather than of the document. Reviewers should never have to
   reach for browser zoom. */
const ZKEY = 'planreview:basepx';
const ZMIN = 14, ZMAX = 26, ZDEF = 17;
function applyZoom(px) {
  px = Math.max(ZMIN, Math.min(ZMAX, px));
  document.documentElement.style.setProperty('--base', px + 'px');
  localStorage.setItem(ZKEY, String(px));
  const out = document.getElementById('zlevel');
  if (out) out.textContent = px + 'px';
  return px;
}
let basePx = applyZoom(parseInt(localStorage.getItem(ZKEY) || '', 10) || ZDEF);

function paint() {
  let n = 0;
  document.querySelectorAll('section').forEach(sec => {
    const id = sec.id, s = state[id] || {};
    const ta = sec.querySelector('textarea');
    if (ta && document.activeElement !== ta) ta.value = s.comment || '';
    sec.querySelectorAll('.verdicts button').forEach(b =>
      b.classList.toggle('on', b.dataset.v === s.verdict));
    const touched = !!(s.comment || s.verdict);
    if (touched) n++;
    const link = document.querySelector('nav a[href="#' + id + '"]');
    if (link) link.classList.toggle('done', touched);
  });
  document.querySelector('.count').textContent =
    n + ' of ' + document.querySelectorAll('section').length + ' sections reviewed';
}

function save() { localStorage.setItem(KEY, JSON.stringify(state)); paint(); }

document.addEventListener('input', e => {
  const sec = e.target.closest('section');
  if (!sec || e.target.tagName !== 'TEXTAREA') return;
  state[sec.id] = Object.assign({}, state[sec.id], { comment: e.target.value });
  localStorage.setItem(KEY, JSON.stringify(state));
  paint();
});

document.addEventListener('click', e => {
  const vb = e.target.closest('.verdicts button');
  if (vb) {
    const sec = vb.closest('section'), cur = (state[sec.id] || {}).verdict;
    state[sec.id] = Object.assign({}, state[sec.id],
      { verdict: cur === vb.dataset.v ? null : vb.dataset.v });
    save();
    return;
  }
  const zb = e.target.closest('.zoom button');
  if (zb) {
    basePx = applyZoom(zb.dataset.z === 'reset' ? ZDEF : basePx + Number(zb.dataset.z));
    return;
  }
  if (e.target.id === 'export') {
    const out = { plan: document.title, exported: new Date().toISOString(), sections: [] };
    document.querySelectorAll('section').forEach(sec => {
      const s = state[sec.id] || {};
      if (!s.comment && !s.verdict) return;
      out.sections.push({
        label: sec.dataset.label, title: sec.dataset.title, source: sec.dataset.src,
        verdict: s.verdict || null, comment: s.comment || ''
      });
    });
    const text = JSON.stringify(out, null, 2);
    document.getElementById('out').value = text;
    navigator.clipboard && navigator.clipboard.writeText(text).catch(() => {});
    document.getElementById('dlg').showModal();
  }
  if (e.target.id === 'clear' &&
      confirm('Discard all comments and verdicts for this plan?')) {
    state = {}; save();
  }
});

/* Ctrl/Cmd +/-/0 adjust the document instead of the browser, so the setting
   persists for the next plan too. */
document.addEventListener('keydown', e => {
  if (!(e.ctrlKey || e.metaKey)) return;
  if (e.key === '=' || e.key === '+') { basePx = applyZoom(basePx + 1); e.preventDefault(); }
  else if (e.key === '-') { basePx = applyZoom(basePx - 1); e.preventDefault(); }
  else if (e.key === '0') { basePx = applyZoom(ZDEF); e.preventDefault(); }
});
paint();
"""


def build(title: str, subtitle: str, sections: list[tuple[str, Path, int, int | None]],
          root: Path) -> str:
    labels = []
    for i in range(len(sections)):
        # A..Z, then AA, AB, ...
        labels.append(
            chr(65 + i) if i < 26 else chr(65 + i // 26 - 1) + chr(65 + i % 26)
        )

    nav, body = [], []
    for i, (sec_title, path, start, end) in enumerate(sections):
        text = path.read_text()
        chunk = slice_lines(text, start, end)
        try:
            rel = path.relative_to(root)
        except ValueError:
            rel = path
        src = f"{rel}:{start}-{end if end else 'end'}"
        lab = labels[i]
        nav.append(
            f'<a href="#s{i}"><b>{lab}</b> {html.escape(sec_title)}'
            f"<span>{html.escape(str(rel))}</span></a>"
        )
        body.append(
            f'<section id="s{i}" data-label="{lab}" data-title="{html.escape(sec_title, quote=True)}"'
            f' data-src="{html.escape(src, quote=True)}">'
            f'<div class="shead"><span class="tag">Section {lab}</span>'
            f'<span class="src">{html.escape(src)}</span></div>'
            f"<h1>{html.escape(sec_title)}</h1>{md_to_html(chunk)}"
            f'<div class="fb"><label>Your notes on section {lab}</label>'
            f'<textarea placeholder="What is wrong, missing, or unclear here?"></textarea>'
            f'<div class="verdicts">'
            f'<button data-v="ok">Looks right</button>'
            f'<button data-v="concern">Concern</button>'
            f'<button data-v="block">Blocking</button>'
            f"</div></div></section>"
        )

    plan_id = re.sub(r"\W+", "-", title.lower()).strip("-")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>{CSS}</style></head>
<body data-planid="{html.escape(plan_id, quote=True)}">
<nav><h2>Sections</h2>{''.join(nav)}</nav>
<main>
<div class="hdr"><h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p></div>
<div class="bar">
  <button class="primary" id="export">Export comments</button>
  <button id="clear">Clear</button>
  <span class="zoom" title="Text size (also Ctrl/Cmd with plus, minus, or 0)">
    <button data-z="-1" aria-label="Smaller text">A&minus;</button>
    <span id="zlevel">17px</span>
    <button data-z="1" aria-label="Larger text">A+</button>
    <button data-z="reset" aria-label="Reset text size">Reset</button>
  </span>
  <span class="count"></span>
</div>
{''.join(body)}
</main>
<dialog id="dlg"><form method="dialog">
  <h3>Reviewer comments (copied to clipboard)</h3>
  <textarea id="out" readonly></textarea>
  <p><button class="primary">Close</button></p>
</form></dialog>
<script>{JS}</script>
</body></html>"""


def main(argv: list[str]) -> int:
    args = argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    out_path = Path(args[0])
    rest = args[1:]
    title = "Plan review"
    split_h2 = False
    specs: list[str] = []

    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--title":
            title = rest[i + 1]
            i += 2
        elif a == "--split-h2":
            split_h2 = True
            i += 1
        else:
            specs.append(a)
            i += 1

    if not specs:
        print("error: give at least one DOC.md or LABEL=FILE:START-END", file=sys.stderr)
        return 2

    root = Path.cwd()
    if all("=" in s for s in specs):
        sections = [parse_spec(s, root) for s in specs]
    else:
        paths = [Path(s).resolve() for s in specs]
        for p in paths:
            if not p.is_file():
                print(f"error: no such file: {p}", file=sys.stderr)
                return 2
        sections = (
            sections_from_h2(paths)
            if split_h2
            else [(first_heading(p.read_text(), p.stem), p, 1, None) for p in paths]
        )

    subtitle = f"{len(sections)} sections · comment inline, then Export"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(build(title, subtitle, sections, root))
    print(f"wrote {out_path} ({out_path.stat().st_size} bytes, {len(sections)} sections)")
    print(f"serve: python3 -m http.server 8899 --directory {out_path.parent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
