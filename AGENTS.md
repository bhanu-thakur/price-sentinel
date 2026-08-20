# Agent instructions

## Environment

Run the environment doctor and read its JSON instead of probing the environment.
From this repository, invoke it as `python ../ai-command-center/scripts/doctor.py`.
Running it is fine; writing into `ai-command-center` from here is not.

The earlier instruction named `..\doctor.ps1`, a PowerShell script that sat
outside any repo. It is not on Nebula (checked 2026-08-20), so it was a dead
instruction — a rule nobody could follow is worse than no rule.

## The practice exchange, and this repo's state report

**Pull before comparable work, not at session start.** `~/GitHub/ai-command-center/data/practices.json`
holds techniques other repos proved, each carrying a measurement. Read it when you are about to
solve something another repo may already have solved — reading it every session is a recurring
cost, which is the exact thing that file exists to remove. If a practice clearly does not fit
this repo, say so with a reason; that is yours to decide without asking.

**Push when you prove something**, following *Publishing from another repo* in
`ai-command-center/AGENTS.md`: `result` must contain a number, `does_not_apply_when` is
compulsory, `git pull` immediately before writing, and commit `data/practices.json` alone.
**Findings are the auditor's, not yours** — do not write into `data/findings.json`.

**State report:** follow `repo-state.md` in this repo.

## Tests come first, and they are not negotiable afterwards

This repo watches prices. A test that passes while the number is wrong is worse
than no test, because it buys confidence in a stale figure. So when you implement
anything with a checkable result:

1. **Write the tests first, and say plainly that they are expected to fail.**
2. **Run them and paste the real failure output.** Never proceed on an assumed
   failure — a test that "obviously" fails and actually passes is telling you the
   behaviour already exists, or that the test asserts nothing.
3. **Commit the failing tests on their own**, as `test: failing tests for <thing>`.
   Then any later weakening of a test shows up in a diff instead of hiding inside
   the commit that made it pass.
4. **Implement until green, and do not edit a test to make it pass.** If a test is
   genuinely wrong, stop and say so rather than quietly adjusting it.

**Assert the value, not its shape.** A test asserting a price "is a float", or that
a key exists, or that a list has three entries, is not a test — the scrape can
return yesterday's number and every one of those still passes. Assert that the
value equals the thing it should equal, recomputed from the real source: the
fixture page, the CSV row, the threshold arithmetic.

## Shipping

**Commit, push and deploy finished work without asking.** When work in scope is done and
verified, commit it, push to `main`, and — where this repo's deliverable is a deployed
thing — run its documented build and release too. Do not end a turn with "want me to
commit this?" or "shall I deploy?"; the asking is the waste, not the shipping. Bhanu's
instruction, 2026-08-16.

Deploy this repo's own target by its own documented command. Two things stay
confirm-first, because neither is finished work and neither is undone by a revert:
destroying or migrating data a user would miss, and changing what the project is rather
than what it serves — deleting a site or project, moving a domain, rotating credentials,
altering billing.
