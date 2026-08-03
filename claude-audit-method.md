# Audit method — how the FIX_PLAN.md audit was carried out

Companion to [`claude-audit-report.md`](claude-audit-report.md). This document records the
procedure, the commands, the reasoning behind each choice, and the limits of what was checked,
so the findings can be reproduced or challenged.

Auditor: Claude Opus 5 (Claude Code) · Date: 2026-08-02
Subject: `D:\GitHub\price-sentinel` @ `7c8a222` (= `origin/main`)
Constraint given: **report only — no code, no fixes.**

---

## 1. Governing principles

**P1 — Verification, not attestation.** The executor's own report is an input, not evidence.
Every claim in the report below is re-derived from a primary artifact: a git object, an
executed function, or a CI step list. Where I could not re-derive a claim, the report says so
(§6).

**P2 — Zero mutation.** "Report only" was read strictly: the audit must leave the working tree
byte-identical. This ruled out the plan's own verification scripts (§3) and forced a different
verification design.

**P3 — Three independent evidence classes per task.** A fix is only "verified" if it passes:

| Class | Question | Instrument |
|---|---|---|
| **Textual conformance** | Does the committed code match the prescribed replacement? | `git show <sha> -- <file>` diffed against the plan's fenced blocks |
| **Behavioural** | Does the code produce the required output for the stated input? | executed probe against pure functions |
| **Production** | Is it actually live and green? | generated `docs/index.html`, `gh run view` step list |

Textual conformance alone is worthless — a block can be copied perfectly and still be wrong.
Behavioural alone is worthless — passing a test the plan wrote proves the plan was internally
consistent, not that the file matches the plan.

**P4 — Adversarial extension.** For each fix, ask: *what input class does this newly reachable
code path not handle?* The plan justified Task 2.1 with a single-listing scenario, so I
constructed the two-listing scenario. That is how Finding A was found; it is not reachable by
running the plan's own verifications.

**P5 — Audit the omissions, not just the diffs.** The user's original ask (cross-platform
comparison) was compared against the plan *and* against the delivered artifact. A plan that
never mentions a requirement cannot be used to prove the requirement was met.

---

## 2. Environment establishment

`CLAUDE.md` → `AGENTS.md` mandate probing the environment through one script rather than
ad-hoc discovery:

```bash
& ..\doctor.ps1
```

Exit 2, `status: "missing-required"`. Two fields changed how the rest of the audit ran:

- `repos[price-sentinel] = { ready: false, surfaces: [{type: "python", installed: false, venvs: []}], missing: ["python:."] }`
  — there is no committed Python surface, confirming `.venv-fix/` (the plan's §0 scratch venv)
  is the only usable interpreter and is outside git's view.
- `problems[] → python-foreign-venv-shadow`: bare `python` resolves to
  `…\hermes-agent\venv\Scripts\python.exe` with no `VIRTUAL_ENV` set, and
  `python-collision` (3 candidate paths).

Consequence: **every Python invocation in this audit uses the explicit interpreter path**
`./.venv-fix/Scripts/python.exe`, never bare `python`. Bare `python` would have silently run
under a foreign venv with a different dependency set and produced misleading test results.
`PYTHONIOENCODING=utf-8` is prefixed on every command that can emit `₹` (cp1252 console).

---

## 3. Why the plan's own verification scripts were not used

FIX_PLAN.md ships three verifications (`verify_1_1.py`, the 1.2 inline `-c` block,
`verify_2.py`). All three call `main.run()`, which writes:

- `data/state.json`
- `data/<listing>.csv` (append)
- `docs/index.html`
- `docs/chart-data/*.json`

The plan itself acknowledges this and makes `git checkout docs/index.html data/state.json`
**mandatory** after each. Under P2 that is unacceptable: a `git checkout` on `data/` discards
real committed price samples if the working tree ever diverges mid-audit, and the CSV appends
are not reverted by that checkout at all — `verify_2.py` would have permanently injected a
synthetic `₹2,799 / in_stock=0` row into `data/amazon-in-*.csv`, corrupting the very history
the tracker scores against.

So the verifications were **re-implemented against the pure layer**. `dashboard.py` separates
cleanly: `build()` is the only function that touches the filesystem; `_money`, `_group_inr`,
`_verdict_line`, `_card`, `_freshness`, `_relative` are pure over `(products, state, now)`.
All of the plan's required assertions are observable at that layer.

---

## 4. Instruments

### 4.1 Static / textual

| Command | Purpose |
|---|---|
| `git log --oneline -20` | locate the change set: `7e91a11` → merge `f111895` → data `7c8a222` |
| `git show --stat 7e91a11 f111895 7c8a222` | scope check — confirm nothing outside the plan's file list was touched |
| `git show 7e91a11 -- dashboard.py main.py .github/workflows/track.yml requirements.txt HANDOFF.md` | full unified diff, read line-by-line against the plan's fenced replacement blocks |
| `diff <(git show 9120a8a:docs/prototype.html) docs/prototype.html` | Task 3.1 restore — byte-identity against the pre-deletion blob, not a "looks right" eyeball |
| `git ls-files \| grep -c "^\.venv-fix/"` | prove the scratch venv was never committed (result `0`) |
| `git check-ignore -v .venv-fix/ .pytest_cache/` | **why** it wasn't committed — output `.venv-fix/.gitignore:1:*`, i.e. `uv`'s own inner ignore file, not a repo rule. Distinguishes "handled" from "lucky". |
| `git status --porcelain --ignored` | full untracked/ignored inventory — surfaced that no root `.gitignore` exists and `__pycache__/` dirs are unignored |
| `git rev-list --left-right --count origin/main...HEAD` | `0 0` — the audited tree is what production runs |

Reading order for the source was deliberate: `FIX_PLAN.md` (the spec) → `HANDOFF.md`
(the contested doc) → `main.py`/`dashboard.py` (the changed code) → `analyze.py`/`fetch.py`/
`catalog.py`/`add_product.py`/`providers/*` (the unchanged code the changes depend on). The
last group is what made Findings A and B possible: Finding A required knowing that
`main._offers_for_product` routes *fresh-but-out-of-stock* offers into `stale`, which is not
visible from the `dashboard.py` diff.

### 4.2 Behavioural probe

Written to the session scratchpad (outside the repo), never to `D:\GitHub\price-sentinel`:

```python
sys.path.insert(0, r"D:\GitHub\price-sentinel")
import dashboard
now = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)   # frozen clock
```

Design notes:

- **Frozen `now`.** `_relative()` output ("3 hr ago", "5d ago") is otherwise non-deterministic
  and unquotable in a report.
- **Hand-built `state` dicts**, shaped to match what `main._record_success` /
  `_update_product_verdict` actually persist — verified against the real `data/state.json`
  before use, so the fixtures are not fiction.
- **Field extraction reuses the plan's own regexes** (`class="price num">(.*?)</div>`,
  `class="mlabel num">(.*?)</div>`, …) so probe output is directly comparable to the
  "Required:" lines in FIX_PLAN.md §2.
- **Scenario matrix**, five cases:

  | # | Scenario | Targets |
  |---|---|---|
  | 1 | 7 currency values + `None`/`0`/negative/fractional | 1.3 |
  | 2 | total outage — `last_checked_ts` set, no `last_success_ts` | 1.1 |
  | 3 | outage with 3h-old and 5d-old last success | 1.1 (both branches) |
  | 4 | single listing, fresh, `in_stock=False` | 2.1 / 2.3 / 2.4 |
  | 5 | **two listings** — Amazon in-stock recommended + Flipkart fresh OOS | **adversarial (P4)** |
  | 6 | verdict with real 180-day `median`, no `basis` | 2.2 (the other branch) |

  Cases 3, 5 and 6 are not in FIX_PLAN.md. Case 5 produced Finding A.

### 4.3 Suite

```bash
PYTHONIOENCODING=utf-8 ./.venv-fix/Scripts/python.exe -m pytest tests -q
```

`30 passed, 5 subtests passed` — matches the plan's stated gate. Immediately followed by
`git status --porcelain` to confirm the suite does not write into `data/` or `docs/`; it does
not, which also means the new CI `Run tests` step cannot dirty a runner mid-job.

Coverage was then measured against the *changed* surface:
`grep -n "def test" tests/*.py` → `tests/test_dashboard.py` contains exactly **one** test, and
the total is the same 30 as before the change set. That is Finding F.

### 4.4 Generated-artifact inspection

The delivered page is evidence in its own right — it is what the user actually sees:

```bash
grep -o 'class="nm">[^<]*'        docs/index.html   # products present
grep -o 'class="sub2">[^<]*'      docs/index.html   # retailer · freshness · stock note
grep -o 'class="price num">[^<]*' docs/index.html
grep -o '<div class="offer">.\{0,320\}' docs/index.html   # the comparison table rows
grep -c -i flipkart               docs/index.html   # → 0
grep -c '"price"'                 docs/index.html   # → 0, charts stayed lazy
```

Plus a JSON pass over `data/state.json`, `docs/chart-data/*.json` and `wc -l data/*.csv` to
check the final-gate claims quantitatively (32 daily points for `amazon-in-b0gsvfv3r4`,
per-product verdict/score/alert/`last_alert_ts`, provider-history point counts).

### 4.5 Production

```bash
gh run list --limit 6 --json displayTitle,status,conclusion,createdAt,headSha,databaseId
gh run view 30715385666 --json jobs --jq '.jobs[].steps[] | "\(.number)\t\(.conclusion)\t\(.name)"'
```

Run `30715385666` is on `7c8a222` — the audited SHA — and its step list shows
`6 success Commit history` followed by `7 success Run tests`. This upgrades Tasks 1.2b and 3.2
from "the YAML looks right" to "the YAML was executed by GitHub Actions in the required order
and passed." Ordering matters: the plan is explicit that tests must not gate the commit.

---

## 5. Confounders checked and eliminated

Findings that were investigated and **killed** before reaching the report:

- **"The automation has stopped running."** `data/state.json` showed
  `last_success_ts = 2026-08-01T19:38:35Z` and no cron data commit after `18:05 UTC`, which
  reads like a dead scheduler. Cross-checking the local clock (working-tree mtimes ≈ 01:14 IST
  = 19:44 UTC) showed only ~6 minutes had elapsed. Not a finding.
- **"The fix commits were never pushed."** `git rev-parse origin/main` equalled `HEAD`, but the
  `origin/main` ref could have been stale (`.git/FETCH_HEAD` mtime predates `7c8a222`).
  Resolved via `gh run list`: GitHub itself reports a workflow run whose `headSha` is
  `7c8a222`, which is only possible if the commit is on the remote. Not a finding.
- **"`.venv-fix/` was committed."** `git ls-files` count `0`. Not a finding — but
  `git check-ignore -v` reclassified it from "handled correctly" to "not committed by luck",
  which *is* reported (Finding E).
- **"The test suite dirties the repo."** `git status --porcelain` after the run is clean of
  `data/` and `docs/`. Not a finding.

Recording these matters: three of the four would have been plausible-sounding false positives.

---

## 6. What was NOT verified (limits of this audit)

1. **Task 1.2a was not executed.** The crash-tolerance simulation calls `main.run()` and writes
   state; under P2 it was assessed by code inspection only. The construct
   (`try/except Exception` → `traceback.print_exc()` → continue to the `[done]` print) is
   unambiguous, but "no non-`Exception` escape" is an inference, not a measurement.
2. **No network I/O against providers.** `pricehistory.app` and `buyhatke.com` were not
   contacted. Whether the adapters still parse live pages, and whether BuyHatke would in fact
   return Flipkart counterparts for these three products, is untested. Finding B describes
   *structural* obstacles read from the code and the committed watchlist, not a failed live run.
3. **No browser execution.** The hand-rolled canvas renderer in `SCRIPT` (tooltips, range
   filtering, `ResizeObserver`, retry path) was read, not run. The known range-window issue
   documented in HANDOFF.md was taken as given.
4. **Whether the executor actually ran the plan's verifications is unknowable** from the repo.
   What is established is that the outcomes those verifications demand are reproducible today.
5. **Findings A, C and D are latent**, not observed in production — they are reachable-state
   analyses. Finding A was demonstrated by executing the real `_card()` against a constructed
   two-listing state; C and D are read from the code with the trigger conditions stated.
6. **Severities are the auditor's judgement.** They weight *proximity to the user's next
   action* — Finding A is HIGH not because it is broken today but because it breaks on the
   first day the requested feature works.

---

## 7. Reproducing this audit

```bash
cd /d/GitHub/price-sentinel
git log --oneline -5
git show 7e91a11 -- dashboard.py main.py .github/workflows/track.yml requirements.txt HANDOFF.md
diff <(git show 9120a8a:docs/prototype.html) docs/prototype.html
PYTHONIOENCODING=utf-8 ./.venv-fix/Scripts/python.exe -m pytest tests -q
git status --porcelain --ignored
gh run view 30715385666 --json jobs --jq '.jobs[].steps[] | "\(.number)\t\(.conclusion)\t\(.name)"'
```

The behavioural probe is not in the repo (P2). Its full source is in the session scratchpad at
`…\486c98e3-…\scratchpad\audit_probe.py`; §4.2 above specifies it completely enough to rebuild.
