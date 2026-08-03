# Universal audit checklist

A portable procedure for auditing work delivered by an AI agent (or a human) against a
specification, when you have **one** reviewer and cannot rely on a second vendor to cover your
blind spots.

Stack-agnostic. Substitute the ecosystem commands in §12; everything else is invariant.

> **Origin.** Written after two independent audits of the same change set reached the same
> verdict but missed different defects. Neither reviewer was less capable than the other. Each
> had a *systematic* instrument bias, and neither bias was written down. Every item below exists
> to close a named failure mode, listed in §11.

---

## 1. When to run this — the pause points

A checklist without a defined trigger is decoration. Run this at exactly these moments:

| Pause point | Depth |
|---|---|
| Before merging agent-authored work you did not watch being written | Full |
| Before trusting a report that says "done", "verified", or "all tests pass" | Full |
| Before a release, migration, or anything hard to reverse | Full |
| After any incident where something reported success while doing nothing | Full |
| Routine small diffs you read line-by-line yourself | §3 card only |

**Do not run this in the same session that produced the work.** See §2.

---

## 2. Independence — the precondition

An *audit* is defined by independence: IEEE 1028 separates it from walkthroughs and technical
reviews precisely because an audit is an independent examination against stated criteria, not a
collaborative read-through. NASA's IV&V programme decomposes independence into three parameters;
adapted for a one-subscription workflow:

| IV&V parameter | Practical rule here |
|---|---|
| **Technical** | The auditor re-derives conclusions from primary artifacts. It never reuses the executor's own verification scripts — those encode the executor's assumptions about what "working" means. |
| **Managerial** | Fresh task/session, no implementation context, no memory of authoring the code. Do not let the author grade its own homework. |
| **Financial** *(analogue)* | The auditor has no stake in the verdict. It is not asked to "confirm the fix" or "check it's ready" — framing that pre-loads the answer. Ask it to *find what is wrong*. |

**A fresh session is necessary but not sufficient.** Session isolation removes *conversational*
contamination. It does not remove *methodological* bias: a reviewer that habitually verifies by
reading rather than executing will do so again in a clean session. That is what this file is
for — the bias lives in the procedure, so the fix must live in the procedure.

---

## 3. The killer-item card — DO-CONFIRM

Gawande's distinction: a **READ-DO** checklist is a recipe you follow step by step; a
**DO-CONFIRM** checklist is run at a pause point *after* you have worked from expertise, to
confirm nothing critical was skipped. Effective cards stay near 5–9 items and under ~90 seconds,
or people start shortcutting.

§4–§10 are READ-DO. **This card is DO-CONFIRM. Run it before writing a single word of report.**

```
□ 1  Audited SHA == deployed SHA, proven from the REMOTE, never a local ref
□ 2  Every requirement has a ledger row — including requirements absent from the spec
□ 3  No requirement closed on inquiry alone (report says so / code exists ≠ works)
□ 4  ≥1 claim per changed unit re-performed BY EXECUTION, not by reading
□ 5  Test suite run by me, in the project's declared environment
□ 6  CI read at LOG level; intended side effect confirmed, not just a green tick
□ 7  ≥1 adversarial probe per fix at N=2 / failure state / empty state
□ 8  For every test cited as evidence, I have named what it mocks
□ 9  Every finding carries a reproduction command, or is labelled PLAUSIBLE
```

Any unticked box is either an audit gap to disclose in §10, or work you have not finished.

---

## 4. Phase A — Criteria and the requirement ledger

**Audit criteria first.** An audit measures a deliverable against *stated criteria*. Establish
them before looking at the diff, or you will unconsciously adopt the executor's framing.

Build a ledger — a requirements traceability matrix, in QA terms. Forward-trace every
requirement to the evidence that closes it, and back-trace every change to a requirement.

| # | Requirement | Source | Evidence class (§5) | Artifact | Status |
|---|---|---|---|---|---|

Rules that make the ledger work:

- **Rows come from the original request, not from the plan.** A plan is the executor's
  interpretation; it is evidence of *intent*, not of *scope*. If the user asked for four things
  and the plan covers three, the ledger has four rows.
- **A requirement with no row is the finding.** The matrix is itself evidence: either the
  requirement was covered, or it was never specified. Silent scope loss between request and plan
  is the single most common way a deliverable is "complete" and wrong.
- **Back-trace too.** Any change with no requirement row is unrequested scope — flag it.
- **Split generic capability from instantiated capability.** "The engine can compare retailers"
  and "these products are compared" are two rows. Passing the first does not close the second.
  This distinction has its own failure mode (§11 F5).

---

## 5. Evidence classes — rank every claim

Audit standards rank evidence by reliability: evidence the auditor obtains *directly* beats
evidence obtained by inference; documentary beats oral; auditor-generated beats entity-generated.
Applied to software review, weakest to strongest:

| Class | What it is | Strength |
|---|---|---|
| **E0 Inquiry** | The executor's report, commit message, changelog, code comment, docstring | **Never sufficient alone** |
| **E1 Inspection** | The code exists and reads correctly; the diff matches the spec | Necessary, not sufficient |
| **E2 Observation** | The generated artifact contains the expected output | Good |
| **E3 Reperformance** | *You* executed the unit and compared output to the requirement | Strong |
| **E4 Production** | Confirmed live: deployed SHA, run logs, real side effects | Strongest |

**The governing rule: no requirement closes at E0 or E1 alone.** Every requirement must reach
E2 minimum, and every *behavioural* requirement must reach E3.

This one rule is the whole discipline. A code block copied perfectly from a spec is E1 — it
proves the executor could copy. It does not prove the digit-grouping loop is off-by-one-free.
Only running it does.

**Professional skepticism** is the posture: make a critical assessment, with a questioning mind,
of the validity of evidence, and stay alert to evidence that *contradicts* the report. Believing
the executor is honest and competent does not relieve you of corroboration. Design your probes so
they are not biased toward confirming the report — the documented antidote to confirmation bias
is to pre-register what you will check *before* reading the executor's conclusions.

---

## 6. Phase B — Environment

Establish the interpreter/toolchain **the project declares**, not whatever is on `PATH`.

```
□ Run the project's own environment probe if one exists (doctor script, make check, task doctor)
□ Resolve the exact interpreter/binary; record the absolute path in the report
□ Check for shadowing: multiple installs, foreign venvs, store aliases, version managers
□ If the plan or README creates a scratch environment, USE IT — do not conclude "deps missing"
□ Record encoding/locale settings needed to reproduce output
```

> **Failure mode closed (F1).** An auditor that reads "dependencies not installed" and falls
> back to a partial run has downgraded every subsequent claim from E3 to E1 — and will then
> lean on CI for a result it could have obtained locally in seconds. The declared environment is
> often already in the repo, created by the very plan under audit.

---

## 7. Phase C — Provenance: close the build-to-deploy gap

Supply-chain practice names this precisely: most risk lives in the gap between what was reviewed
and what actually runs. Provenance work exists to chain the running artifact back to a reviewed,
versioned commit. Your audit needs the same chain.

```
□ Resolve the deployed/remote ref FROM THE REMOTE — never a cached local tracking ref
□ Confirm audited SHA == deployed SHA; if not, diff the delta and re-scope
□ Identify who/what produced any commits you did not expect (bots, CI, auto-formatters)
□ Confirm the working tree is clean of unrelated drift before you measure anything
□ Note untracked-but-unignored files that a careless `add .` would capture
```

```bash
git ls-remote origin refs/heads/main      # authoritative
git rev-parse origin/main                 # CACHED — can be stale, never trust alone
git fetch -q origin && git rev-list --left-right --count origin/main...HEAD
git status --porcelain --ignored
```

> **Failure mode closed (F2).** `git rev-parse origin/main` reads a local file that is only as
> fresh as your last fetch. An audit that concludes "what I reviewed is what runs" from a stale
> ref has verified nothing about production. If a CI/bot commits to the branch, this drifts
> within minutes.

---

## 8. Phase D — Conformance (E1)

```
□ Isolate the implementation boundary: which commit(s) are in scope, which predate the work
□ Read the full diff of the change set against the spec, block by block
□ Verify restored/reverted files by byte-identity against the historical object, not by eye
□ Check for patch corruption and whitespace damage
□ Attribute honestly: capability that predates the change set is NOT delivered work
```

```bash
git log --oneline --decorate -n 20
git show --stat <sha>
git diff <base>..<sha> -- <files>
git diff --exit-code <historical-sha> -- <restored-file>   # byte identity
git show --check <sha> ; git diff --check                  # whitespace / corruption
```

> **Failure mode closed (F3).** Pre-existing infrastructure gets silently credited to the
> current change set, inflating "complete" in the ledger. Isolate the boundary *before* you
> assess coverage.

---

## 9. Phase E — Reperformance (E3) — the phase most audits skip

Reperformance is the auditor independently executing the procedure rather than accepting that it
was performed. It is the single highest-value phase and the easiest to rationalise away.

```
□ Identify the PURE layer: functions with no I/O, callable in isolation
□ Execute each changed unit against the spec's own stated cases
□ Extend beyond the spec: null, zero, negative, empty, boundary, unicode, very large
□ Freeze all non-determinism (clock, RNG, locale) so output is quotable in the report
□ Build fixtures from REAL persisted state, not invented shapes — verify the shape first
□ Reuse the spec's own assertion/extraction patterns so results are directly comparable
□ Run the full test suite YOURSELF in the Phase B environment
```

**Mutation-style thinking, without the tooling.** Coverage is the weakest adequacy signal — it
proves execution, not that a fault would propagate to an assertion and be detected. For each
changed unit ask: *if I broke this in a plausible way, would anything here notice?* If the honest
answer is no, that is a finding regardless of the green suite.

**If reperformance would mutate state, do not skip it — relocate it.** Refuse to run the
executor's verification scripts when they append to real data files, rewrite persisted state, or
send anything outward. Instead:

1. Call the pure layer directly (preferred — same coverage, zero side effects).
2. Or run against a temp copy / fixture directory / dry-run flag.
3. Or, last resort, snapshot → run → restore, and **verify the restore**.

Note explicitly in the report which claims rest on inspection because execution was unsafe.

> **Failure mode closed (F4).** "The function exists and reads correctly" is E1 dressed as
> proof. An off-by-one in a grouping loop, an inverted boundary, a wrong default — all survive
> inspection and die instantly under execution.

---

## 10. Phase F–I — Artifact, production, adversarial, silence

### F. Artifact observation (E2)

```
□ Inspect the ACTUAL generated output — rendered page, built bundle, exported file, API response
□ Confirm required content is present AND forbidden content is absent
□ Count things that should have counts (rows, points, entries) — quantitative, not impressionistic
□ Check the artifact reflects real data, not fixtures/samples left behind
```

### G. Production observation (E4)

```
□ Read CI/CD LOGS, not status badges
□ Confirm the intended SIDE EFFECT occurred, not merely that the step exited 0
□ Check schedule/trigger reality against declared config (cron ≠ guaranteed cadence)
□ Sample the run history for gaps, silent no-ops, and unexpected pushes
□ Verify secrets/config the code depends on are actually populated
```

> A green tick means a command exited zero. It does not mean the intended effect happened, that
> environments matched, or that anything was really deployed. Read the log.

> **Failure mode closed (F5).** Step-conclusion reading misses everything interesting: a run
> that did no work, a job that committed nothing, a scheduler that fires at a third of its
> declared rate, an empty secret degrading a whole feature to a silent no-op.

### H. Adversarial probes — N=2 and failure states

Most specs are written and verified against the **happy singular** case. Defects concentrate
where the spec's example stops.

For each fix, construct at minimum:

```
□ N=2  — two items where the spec assumed one (two listings, two users, two tenants, two files)
□ N=0  — empty collection, no data yet, first-run state
□ Partial — one item populated, one not yet fetched/migrated/initialised
□ Failure — dependency down, timeout, malformed response, permission denied
□ Mixed — one item succeeds while another fails simultaneously
```

**Rule: state cascades.** Trace what happens when a flag derived from one item is applied to a
decision about another. Cross-item contamination is the dominant defect class at N=2 and is
structurally invisible at N=1.

**Oracle check.** For every test cited as evidence of correctness, name what it *mocks*. A test
that proves selection logic while stubbing the renderer is evidence about selection only — and
is often exactly why a rendering defect survived to production. A passing test is evidence only
for what it does not mock.

### I. Silence audit — what nobody wrote down

```
□ Requirements in the original request but absent from the plan/spec
□ Behaviour changed with no test added (compare test count before/after)
□ Code comments asserting guarantees the code does not enforce — verify each claim literally
□ Cleanup/teardown instructions in the plan that were not carried out
□ Docs updated to claim resolution of issues that are still open
□ Config/hygiene the change set implies but omits (ignore files, cleanup, index updates)
```

> **Failure mode closed (F6).** The most expensive defects are absences. A diff review can only
> find what is present; only the ledger (§4) and this phase find what is missing.

---

## 11. Failure-mode register

Every phase above closes a specific, named, recurring way audits go wrong. Keep this list — it
is the part worth re-reading before you start.

| ID | Failure mode | Closed by |
|---|---|---|
| **F1** | *Environment surrender* — partial run accepted, claims silently downgraded to E1 | §6 |
| **F2** | *Build-to-deploy gap* — audited the local tree, not what runs | §7 |
| **F3** | *Attribution inflation* — pre-existing capability credited to this change set | §8 |
| **F4** | *Reperformance gap* — verified existence, not behaviour | §9 |
| **F5** | *Green-tick fallacy* — status read instead of logs; side effect never confirmed | §10G |
| **F6** | *Silent scope loss* — requirement dropped between request and plan, never re-checked | §4, §10I |
| **F7** | *Happy-singular bias* — verified only the case the spec illustrated | §10H |
| **F8** | *Oracle blindness* — a passing test credited beyond what it actually exercises | §10H |
| **F9** | *Comment-as-proof* — a code comment's guarantee accepted as implemented | §10I |
| **F10** | *Confirmation drift* — probes designed to confirm the report rather than break it | §5 |

---

## 12. Severity and reporting

**Severity is anchored on user-visible consequence, not on how clever the finding is.**

| Level | Definition |
|---|---|
| **Critical** | Data loss, corruption, or a security/privacy exposure |
| **High** | A directly requested outcome is absent or wrong in the real configuration or UI |
| **Medium** | Correct today, but produces wrong results under a realistic supported state |
| **Low** | Hygiene, operational noise, cost, or maintainability |

Ranking rule: an **absent requested outcome outranks a latent defect**. The user asked for a
thing and does not have it; that is the loudest line in the report. A defect that fires only
after the next change is High only if that change is imminent.

**Every finding must carry a reproduction command or a verdict label.** Investigating a
hallucinated finding costs *more* than finding a real one, because you are searching for
something that does not exist. So label honestly:

- **CONFIRMED** — reproduced by execution; the command is in the report.
- **PLAUSIBLE** — derived by tracing; trigger conditions stated; not executed.

Report structure: verdict → requirement ledger → prioritised findings (each with mechanism,
trigger, evidence, reproduction) → confirmed-correct list → **limitations**.

**The limitations section is mandatory.** State what you did not verify and why: unexecuted
paths, no network calls, no browser run, claims resting on inspection. An audit that hides its
own gaps is an audit you cannot calibrate against next time.

---

## 13. Command cookbook

Adapt per ecosystem; the *intent* column is the invariant.

| Intent | Git / GitHub | Node | Python |
|---|---|---|---|
| Deployed ref (E4) | `git ls-remote origin refs/heads/main` | — | — |
| Change boundary | `git show --stat <sha>` · `git diff <base>..<sha>` | — | — |
| Byte-identical restore | `git diff --exit-code <sha> -- <file>` | — | — |
| Patch corruption | `git show --check <sha>` · `git diff --check` | — | — |
| Tree cleanliness | `git status --porcelain --ignored` | — | — |
| Why is this ignored | `git check-ignore -v <path>` | — | — |
| Suite (E3) | — | `npm test` / `npx vitest run` | `<declared-python> -m pytest -q` |
| Reperform a unit (E3) | — | `node -e "…"` | `<declared-python> -c "…"` |
| CI logs (E4) | `gh run view <id> --log` | — | — |
| CI step outcomes | `gh run view <id> --json jobs --jq '.jobs[].steps[]'` | — | — |
| Schedule reality | `gh run list --workflow "<name>" --limit 20 --json createdAt,conclusion,event` | — | — |
| Artifact grep (E2) | `rg -n "<expected>" <artifact>` · `rg -c "<forbidden>" <artifact>` | — | — |

---

## 14. The one-subscription workflow

Four tasks, never fewer. The critical rule: **never let the same task be both author and final
authority.**

**1 — Implement.** Agent implements, tests, documents. Normal working session.

**2 — Audit.** *Fresh task, no implementation context.* Attach this file. Prompt:

> Audit this delivery as an independent adversarial reviewer. Do not fix anything.
> Follow `claude-audit-checklist.md` exactly; it is the audit procedure, not a suggestion.
> Treat the executor's report as untrusted inquiry-class evidence (E0).
> Requirements come from my original request, not from the plan — build the §4 ledger from the
> request and flag anything the plan silently dropped.
> Reperform every behavioural claim by execution (§9). If execution would mutate state, use the
> pure layer or a temp copy — never the executor's own verification scripts.
> Run §10H adversarial probes at N=2 and in failure states.
> Read CI at log level (§10G) and prove the deployed SHA from the remote (§7).
> Label every finding CONFIRMED (with reproduction command) or PLAUSIBLE.
> Finish by ticking the §3 card and disclosing every unticked box in your limitations section.

**3 — Triage.** *You* accept or reject each finding. Human gate; do not delegate it.

**4 — Correct.** Fresh task, given the audit report, fixing only accepted findings. Then a
targeted re-audit of the changed surface — not the whole thing again.

**Objective gates that outrank any model's confidence:** suite green in the declared
environment · `git diff --check` clean · artifact inspected · CI logs read · deployed SHA
proven · working tree clean · every ledger row at E2 or better.

---

## 15. Maintaining this file

This checklist is only as good as its failure-mode register. **Every time an audit misses
something, add the miss to §11 and the closing item to the relevant phase.** A miss that does
not produce a new checklist line will recur — that is the entire premise of the document.

Structured inspection with a defined procedure and defined roles is one of the best-evidenced
practices in software engineering, with reported defect reductions in the 60–90% range. The
procedure is what carries the result, not the individual reviewer.

---

## Sources

- [ISA 500 — Audit Evidence (IAASB)](https://www.icjce.es/images/pdfs/tecnica2/normativainternacional/isa500.pdf) — evidence reliability hierarchy; inspection, observation, inquiry, recalculation, reperformance
- [ISA 500 — Audit evidence (ACCA)](https://www.accaglobal.com/learning-and-events/audit-and-assurance/isa500-audit-evidence.html)
- [ISA 200 — Overall Objectives of the Independent Auditor](https://pasai.squarespace.com/s/isa-200.pdf) — professional skepticism
- [ACCA — Professional Scepticism and Cognitive Biases](https://www.accaglobal.com/content/dam/ACCA_Global/professional-insights/professional-scepticism-audit/PI-PROF-SCEPTICISM-ENGLISH%20v7.pdf) — confirmation bias controls
- [IEEE 1028-2008 — Standard for Software Reviews and Audits](https://standards.ieee.org/standard/1028-2008.html) — audit vs inspection vs walkthrough; independence
- [NASA SWE-141 — Independent Verification and Validation](https://swehb.nasa.gov/display/SWEHBVC/SWE-141+-+Software+Independent+Verification+and+Validation) — technical, managerial, financial independence
- [NASA IV&V Overview](https://www.nasa.gov/ivv-overview/)
- [Atul Gawande, *The Checklist Manifesto* — DO-CONFIRM vs READ-DO, killer items, pause points](https://www.projectmanagement.com/blog-post/21259/creating-a-killer-checklist--lessons-from--the-checklist-manifesto-)
- [Requirements Traceability Matrix in QA](https://www.perforce.com/resources/alm/requirements-traceability-matrix) — forward/bidirectional traceability as coverage evidence
- [A Brief Survey on Oracle-based Test Adequacy Metrics](https://arxiv.org/pdf/2212.06118) — coverage as weakest adequacy metric; fault propagation to oracle
- [Mind the Gap: Coverage vs Mutation Score](https://arxiv.org/pdf/2309.02395)
- [Green Checkmarks, Red Flags: What CI/CD Can't Catch](https://www.conf42.com/DevOps_2026_Tilda_Udufo_cicd_quality_testing) — exit code 0 ≠ intended side effect
- [SLSA build provenance: verifying supply chain integrity from source to deployment](https://www.systemshardening.com/articles/cicd/slsa-build-provenance/) — the build-to-deploy gap
- [Fagan-style software inspection](https://www.isixsigma.com/dictionary/fagan-style-software-inspection/) — roles, severity classes, 60–90% defect reduction
- [Why AI Coding Agents Need an Independent Review Layer (Futurum, 1H 2026)](https://futurumgroup.com/insights/why-ai-coding-agents-need-an-independent-review-layer-trust-not-output-is-the-bottleneck/) — verification as the bottleneck
- [LLM Hallucinations in AI Code Review](https://diffray.ai/blog/llm-hallucinations-code-review/) — cost of investigating hallucinated findings
