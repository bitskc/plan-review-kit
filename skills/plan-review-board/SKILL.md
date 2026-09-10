---
name: plan-review-board
description: Turn markdown plans, specs, RFCs, or task lists into one clickable HTML review board with a comment box and verdict per section, then serve it locally and read the exported comments back. Use when a human needs to review a long plan and leave feedback per section instead of on the whole document.
---

# Plan review board

Pasting a 400-line plan into chat gets you "looks good". A board with a comment box per
section gets you the twelve specific objections that actually matter.

This skill renders markdown plan documents into a single self-contained HTML file: sticky
section index, rendered plan, and per section a comment box plus `Looks right` /
`Concern` / `Blocking`. Comments persist in `localStorage`, so the reviewer can close the
tab and come back. `Export comments` produces JSON keyed by section label and source
`file:line`, copied to the clipboard.

No API keys, no browser automation, no network, stdlib Python only. The output is one
file you can email, commit, or serve.

## Step 1 — Generate the board

`scripts/plan_review_board.py` ships with this skill.

```bash
# one section per H2 across several docs (the usual case)
python3 scripts/plan_review_board.py /tmp/review/index.html \
  --title "Revenue Surfacer — implementation plan" --split-h2 \
  openspec/changes/add-job-surfacer/{proposal,design,tasks}.md

# whole file per section
python3 scripts/plan_review_board.py /tmp/review/index.html docs/rfc-0007.md

# explicit sections when H2 boundaries are wrong: LABEL=FILE:START-END
python3 scripts/plan_review_board.py /tmp/review/index.html \
  --title "My plan" \
  "Why=proposal.md:1-57" \
  "Decisions D1-D4=design.md:49-102" \
  "Tasks=tasks.md:1-42"
```

Choosing section boundaries matters more than it looks. `--split-h2` is right when the
doc's H2s are already the reviewable units. Use explicit ranges when a single H2 holds
twenty decisions, or when you want related decisions grouped on one card. Aim for
15–25 sections: fewer and comments are too coarse to act on, more and the reviewer stops
before the end.

Derive the ranges from a heading map rather than guessing, and rebuild them after editing
the source docs — line numbers move.

```bash
grep -n '^## ' plan.md      # H2 line numbers for explicit ranges
```

## Step 2 — Serve it and hand over one link

```bash
python3 -m http.server 8899 --directory /tmp/review
```

Give the human `http://127.0.0.1:8899/`. If your harness has a supervised-process
runner, start the server there so it survives the turn instead of dying with a shell.

`file://` works too, but `localStorage` is partitioned per origin and some browsers
restrict it on `file://`, which silently loses comments. Serve over HTTP.

## Step 3 — Verify it rendered before handing it over

A board that swallowed the plan is worse than no board. Check, in the actual browser:

- section count matches what you intended, and the nav has the same count
- no raw markdown leaked into the text (`**`, `- [ ]` rendering as literals)
- tables, fenced code, and nested lists survived
- a real click on a verdict button toggles it, and typing in a textarea updates the
  reviewed counter
- `Export comments` produces parseable JSON

Programmatic `.click()` passing is not proof that a pointer click works. Test at least one
real pointer click and one real keystroke.

## Step 4 — Read the feedback back

The human clicks `Export comments` and pastes the JSON, or you read it from their
clipboard paste. Each entry carries `label`, `title`, `source`, `verdict`, `comment`.

Because `source` is a `file:line` range, you can go straight to the artifact the comment
is about instead of guessing.

Then, for each comment: restate what you understood, confirm it, and only then edit. A
comment like "this needs to be faster" has several incompatible fixes; guessing wastes a
round trip.

If an export comes back empty, the reviewer submitted before typing, or you rebuilt the
board with a different title (the storage key derives from it) and their notes are under
the old key. Say so plainly instead of inventing feedback — and never adopt a comment
left on a different board as though it were about this plan.

## Notes on the renderer

It handles headings, nested lists with wrapped continuation lines, tables, fenced and
inline code, bold, and italics. That is what plan documents contain.

Code spans are extracted to placeholders *before* emphasis is applied, so bold wrapping a
code span resolves correctly. Splitting on backticks first strands the `**` markers in
separate fragments and leaks them into the page — the exact bug this ordering prevents.

Literal asterisks inside code (`***`, `path/**`) are left alone, which is correct.

## Text size — the default must be readable without zooming


Every size derives from one `--base` custom property on `:root`; everything else is in
`rem`. Default is **17px**, measured comfortable on a 1920x1080 / 96dpi laptop with no
desktop scaling. The `A− / A+ / Reset` control in the toolbar (and Ctrl/Cmd with `+`,
`-`, `0`) rewrites `--base` between 14 and 26px and persists it in `localStorage` under a
**global** key, not a per-plan one — text size is a property of the reader's screen, so it
should carry to the next plan.

Do not ship a 12-14px base and expect reviewers to reach for browser zoom. Secondary text
(source labels, nav, table cells) is the part that actually becomes unreadable, so keep it
at `>= 0.72rem` rather than a fixed small px.

## Verifying in headless Chromium without wedging the page

Measure computed sizes rather than eyeballing a screenshot:

```js
parseFloat(getComputedStyle(document.querySelector('section p')).fontSize)
```

**Do not fire click storms.** Driving 30+ rapid `page.click()` calls to test a control's
clamp wedges the tab's main world: every later `page.evaluate` / `isIntersectingViewport`
dies with `Runtime.callFunctionOn timed out` while `boundingBox()` still answers. That
signature means the tab is wedged, not that the page is broken — open a fresh tab and
retry with two or three real clicks, and exercise clamping with in-page `.click()` calls
inside a single `evaluate` instead.

(An earlier version of this skill blamed that hang on `backdrop-filter`. That was wrong;
the hang reproduced with the property removed and disappeared on a clean tab. The
property is still absent, but for plainness, not performance.)

## Fixing an existing gstack design board's text size

gstack's `design compare` board hardcodes 12-16px chrome with no root `font-size`, and
caps variant images at `width:100%` in a 3-up grid on a 1400px container — so a
1240px-wide page screenshot renders at roughly a third of natural size and its text is
unreadable. `scripts/bump_board_text.py` appends one override `<style>` block to the
generated board. It touches only the artifact under `~/.gstack/.../designs/`, never the
gstack skill or binary, and re-running replaces its own block instead of stacking copies.

The order matters, because the daemon caches a published board **in memory** by id:
patching the file after `--serve` changes nothing, and republishing the same directory
reuses the cached copy.

```bash
# 1. generate only — no --serve, nothing published yet
$D compare --images "$IMAGES" --output "$DIR/design-board.html"
# 2. patch the generated HTML
python3 scripts/bump_board_text.py "$DIR/design-board.html" --base 17 --columns 2
# 3. publish the patched file
$D serve --html "$DIR/design-board.html"
```

If the returned `BOARD_URL` keeps its previous id and the page is still small, the daemon
served its cache. Copy the images to a **new** directory, then repeat 1-3 there; a new
source directory mints a new board id and forces a re-read. Confirm with:

```js
document.documentElement.innerHTML.includes('plan-review-kit:text-size')
```

Verified effect at `--base 17 --columns 2`: root 16 to 17px, header 16 to 25.5px, variant
label 15 to 19px, meta 13 to 15.8px, comment box 13 to 17px, and each screenshot renders
1552px wide instead of 1352px against a 1240px natural width, so section text lands above
1:1 rather than shrunk.
