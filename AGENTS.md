# Agent instructions

## Environment

Run `doctor.ps1` and read its JSON instead of probing the environment. From this
repository, invoke it as `& ..\doctor.ps1`.

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
