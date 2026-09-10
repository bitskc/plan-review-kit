---
name: adversarial-plan-review
description: Review an implementation plan, spec, RFC, or design doc by dispatching parallel reviewers chartered to REFUTE it, then verifying every claim against the repo before acting. Use before approving a plan for implementation, when a plan touches security or data models, or when a plan's premises came from a summary rather than from files.
---

# Adversarial plan review

A plan review that only asks "does this look reasonable?" returns "yes" and ships the
defects. This skill returns the defects.

Two rules make it work:

1. **Reviewers are chartered to refute, not to bless.** Their job is to find the reason
   the plan fails in production. A reviewer that returns only praise has not been
   calibrated.
2. **You verify every finding before acting on it.** Reviewers hallucinate line numbers,
   miss context, and occasionally invent problems. A finding is not actionable until you
   have read the file yourself.

Rule 2 is the one people skip, and skipping it converts a review into a rumour mill.

## When to use

- Before approving any plan for implementation.
- When the plan asserts facts about a schema, an API, or an existing code pattern.
- When the plan was written from a conversation summary rather than from files.
- When a plan claims figures (money, counts, SLAs) that a user will act on.

## Step 1 — Establish ground truth first

Before dispatching anyone, list the files that decide whether the plan is right: the DDL
or migrations, the vendored API spec, the module the plan says it copies a pattern from,
the config that governs deploys. Put that list in the shared context. Reviewers that
have to guess where truth lives will invent it.

Also state the plan's own constraints (isolation model, versioning scheme, what is out of
scope) so a reviewer does not "find" a deliberate decision.

## Step 2 — Dispatch reviewers in parallel, one per axis

Five axes cover most plans. Give each its own agent, in a single batch so they run
concurrently. Use a read-only researcher agent for the data-grounding pass and a
review-specialist agent for the rest if your harness has them.

| Axis | Charter |
|---|---|
| Architecture | Is this designed against the system as it exists today, or as it existed before the last refactor? Which decisions should be reversed, and what replaces them? |
| Security | Where is the exploitable hole? Trace every path a secret, bearer token, or PII field can travel. Is isolation enforced by the system, or only by the application behaving correctly? |
| Data grounding | Does every column, field, and endpoint the plan references actually exist? Build a table: claimed name, exists, where, type. This axis is pure fact-checking. |
| Engineering feasibility | Is the task list executable in order? Does any task depend on infrastructure nobody has built? Which acceptance criteria are unverifiable as written? |
| Product / operator | Will the end user get the promised outcome, and are the numbers true? Hunt double-counting, false-positive cost, and workflow abandonment. |

Each task must demand:

- A verdict line: `VERDICT: APPROVE` / `APPROVE_WITH_CHANGES` / `BLOCK`.
- Findings with severity, exact `file:line`, the quoted claim being refuted, the evidence
  actually read, and a concrete fix.
- An explicit list of what the reviewer checked and found **correct** — this is the
  calibration signal. A review with no positives is not trustworthy.
- An `UNVERIFIABLE — needs preflight` section for anything that cannot be settled from
  the repo, instead of asserting it either way.

Tell every reviewer: no formatters, no linters, no project-wide test suites, no edits.
Read-only. Those run once, at the end, by you.

## Step 3 — Verify before you believe

For each finding, read the cited file yourself. Findings sort into three buckets:

- **Confirmed** — the file says what the reviewer claims. Fix the plan.
- **Falsified** — the reviewer misread. Discard it, and note the miss; a reviewer that is
  wrong once is usually wrong about adjacent claims too.
- **Partially right** — common. The defect is real but the diagnosis or the proposed fix
  is wrong. Fix the real defect, not the proposal.

Cheap verification commands beat re-reading whole files: grep the schema for the column,
list the directory for the module, check the highest migration number.

Watch for the trap where a plan cites a module that exists only as build output
(`.pyc`, `dist/`, a generated bundle) with no source in the current checkout. It reads as
"already exists and is reused" and is actually missing. Check for source, not just for
the name.

## Step 4 — Converging reviewers are a strong signal

When two reviewers on different axes independently reach the same conclusion from
different evidence, treat it as near-certain and escalate it above the individual
findings. That pattern usually means a load-bearing premise is wrong, not that a detail
is off.

## Step 5 — Adjudicate, then decide who decides

Fix everything mechanical yourself: wrong column, missing task, unverifiable acceptance
criterion, false precedent citation.

Escalate to the human when a finding changes ownership boundaries, cross-team
coordination, or delivery scope. Present it as a decision with the evidence and a
recommendation, not as a question. The human has context you do not: timing,
relationships, which other work is in flight.

Do not silently adopt an architectural reversal that reassigns work to another team.

## Step 6 — Record the decision and re-validate

- Fix the plan artifacts, then re-run whatever validator the plan format has.
- Audit for surviving references to anything you reversed. Grep for the old construct and
  confirm each remaining hit is a negation ("no longer", "SHALL NOT") rather than a live
  assertion. This catches sibling documents nobody was assigned to edit.
- Commit with the evidence in the message: what was claimed, what the file actually said,
  what changed. Future readers need the trail more than they need the conclusion.

## Failure modes this skill exists to prevent

- **Rubber-stamp review.** Reviewers asked to "check the plan" agree with it.
- **Rumour propagation.** Acting on unverified findings, then defending them.
- **Premise inheritance.** Every task in a 78-task plan resting on a column that does not
  exist.
- **Substrate fiction.** Tests that "prove" behaviour against mocks that cannot express
  the behaviour, or a CI gate with no CI behind it.
- **Sibling drift.** Fixing the design doc and leaving the proposal asserting the
  opposite.
