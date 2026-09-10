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

`backdrop-filter` is deliberately absent: it stalls compositing in headless Chromium and
hangs `scrollIntoViewIfNeeded`, which breaks automated verification of the board.
