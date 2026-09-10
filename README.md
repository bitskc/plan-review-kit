# plan-review-kit

Two agent skills and one dependency-free tool for reviewing implementation plans hard
enough that the defects surface before the code does.

Harness-agnostic: the skills are plain `SKILL.md` files, and the tool is a single
stdlib-only Python script. Works with Claude Code, omp, or any agent runner that reads
skill directories — and the script is useful on its own with no agent at all.

## Why

A plan review that asks "does this look reasonable?" returns "yes" and ships the
defects. On a real 78-task plan, this kit surfaced:

- a headline dollar figure that double-counted the same money in two queues, under a
  proposal that called the figures "non-overlapping"
- three columns the plan queried that do not exist in the schema
- dismissals keyed to `updated_at`, so attaching a photo in the upstream system revived
  a correctly-dismissed false positive
- two central architecture decisions written against the system as it existed *before*
  the last refactor
- four pieces of test substrate the plan assumed existed, including a "CI gate" with no
  CI behind it
- a bearer payment link reachable through a field the plan was about to expose

Three of five reviewers returned BLOCK. Every finding was verified against the repo
before anything was changed.

## The two skills

### `adversarial-plan-review`

Dispatches parallel reviewers chartered to **refute** the plan across five axes —
architecture, security, data grounding, engineering feasibility, product/operator — then
makes you verify each finding against the actual files before acting.

The verification step is the part people skip, and skipping it turns a review into a
rumour mill. Reviewers hallucinate line numbers and occasionally invent problems; a
finding is not actionable until you have read the file yourself.

Also covers: converging reviewers as a strong signal, which findings to escalate to a
human rather than fix silently, and auditing sibling documents for surviving references
to anything you reversed.

### `plan-review-board`

Renders markdown plans into one self-contained HTML board with a comment box and a
`Looks right` / `Concern` / `Blocking` verdict per section. Comments persist in
`localStorage`; `Export comments` emits JSON keyed by section label and source
`file:line`, so feedback maps straight back to the artifact it is about.

## The tool

```bash
# one section per H2 across several docs
python3 scripts/plan_review_board.py /tmp/review/index.html \
  --title "My plan" --split-h2 plan/proposal.md plan/design.md plan/tasks.md

# explicit sections: LABEL=FILE:START-END
python3 scripts/plan_review_board.py /tmp/review/index.html \
  "Why=proposal.md:1-57" "Decisions=design.md:49-102"

python3 -m http.server 8899 --directory /tmp/review
```

Then open `http://127.0.0.1:8899/`. Serve over HTTP rather than `file://` — some browsers
restrict `localStorage` on `file://` and silently lose comments.

Requires Python 3.9+. No pip install, no network, no API keys.

## Install

Drop the skills where your agent looks for them:

```bash
git clone https://github.com/bitskc/plan-review-kit
cd plan-review-kit

# Claude Code / omp (user-level)
cp -r skills/adversarial-plan-review skills/plan-review-board ~/.claude/skills/

# or project-level
mkdir -p .claude/skills && cp -r skills/* .claude/skills/
```

`plan-review-board`'s SKILL.md refers to `scripts/plan_review_board.py`; keep the script
next to the skills, or edit the paths in the skill to point at wherever you put it.

## Sending these to another agent session

Both skills are self-contained markdown. To hand them to a running session, either point
it at this repo:

> Read the skills at https://github.com/bitskc/plan-review-kit and use
> `adversarial-plan-review` on `<your plan>`.

or copy the directories into that session's skills path and let it discover them.

## License

MIT
