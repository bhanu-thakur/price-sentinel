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

## Cheap model workers (Bhanu, standing instruction)

**Cheap model workers for mundane work.** From time to time, hand a mundane,
well-bounded job — a status check, a file search, reading and summarising logs, a diff
or a folder — to a subagent on a cheaper model, and keep the main session as the
authority. In Claude Code that is the Agent tool's `model` parameter: `haiku` by
default, `sonnet` when the job needs judgement. Pass it explicitly, because on a
subscription the built-in Explore agent otherwise runs on Opus. On Anthropic's price
list read 2026-10-13, Haiku 5.5 is $0.10 in / $0.50 out per million tokens against
Opus 5.5's $4 / $20 — forty times cheaper — so a worker that reads 40,000 tokens
costs what Opus spends reading 1,000. Haiku's price rises fivefold above 100,000
tokens in one prompt, so keep each job narrow. Whether the plan's usage limit weighs
the models in the same ratio is not checked yet; workers do spend from the same limit.
Give the worker a self-contained brief that names the repo and tells it to read that
repo's `AGENTS.md` first, because it starts with none of your context. Verify its
load-bearing claims yourself before repeating them — the latest commit, a count, a
pass or a fail: a worker's report is evidence to check, not a finding. Do the job
yourself when the answer is one command away. Bhanu's instruction, 2026-10-13.

## Commit and push automatically (Bhanu, standing instruction)

**Always commit and push automatically.** Every change a session makes in this repo is
committed and pushed to the repo's default branch as soon as that piece of work is done —
without asking first, and without leaving anything uncommitted at the end of a turn. Do
not end a turn with "want me to commit this?" or "shall I push?". This replaces any older
line in this repo that says not to commit or push until Bhanu asks. It does not change
what must never be committed: files `.gitignore` excludes, secrets, credentials and
private data stay out. Stage the files you changed by name rather than with `git add -A`,
so another session's unfinished work is not swept into your commit. Bhanu's instruction,
2026-10-15.

## Pull from GitHub before you start work (Bhanu, standing instruction)

**Pull from GitHub before you start work.** At the start of every session, and again
before each new piece of work, run `git pull` so this checkout holds every commit
already on GitHub. Send that first pull together with your first other command,
not as a step of its own, so it costs no extra round trip. Bhanu works on more than one machine and runs more than one session
at a time, so the thing you are about to do may already be done and pushed. Read the
new commits first; if the work is already there, say so and stop rather than doing it
a second time. Pull again just before you push. If a pull fails or conflicts, do not
discard or overwrite anything to get past it — resolve it, or tell Bhanu. Bhanu's
instruction, 2026-10-27, after a session in `inviteX` finished a change and only found
out when it went to push that another session had already pushed the same change.
