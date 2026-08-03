# Codex Audit Checklist

Version: 1.0  
Last reviewed: 2026-08-02  
Purpose: a reusable, evidence-based procedure for auditing code changes, repositories, automations, releases, and implementations with one Codex subscription.

This checklist reduces missed findings; it cannot guarantee that no defect will ever be missed. For regulated, safety-critical, financial-control, privacy-critical, or difficult-to-reverse changes, retain the required human reviewers and specialist sign-offs.

## 1. How to use this checklist

Use the smallest audit profile that covers the risk, but never skip a **Core** item.

- **Core** — required for every audit.
- **Conditional** — required when its trigger applies; otherwise record `N/A` and why.
- **High assurance** — required for security-sensitive, production, data-loss, financial, privacy, compliance, or hard-to-reverse changes.

An unchecked box is not a failure if it is explicitly marked `N/A` with a reason. An unmentioned box is an audit omission.

### Audit profiles

| Profile | Use for | Required coverage |
|---|---|---|
| Change audit | A patch, PR, commit range, or completed plan | Core + relevant conditional modules |
| Repository audit | Broad health, architecture, or readiness review | Core + architecture, tests, supply chain, documentation |
| Automation audit | Scheduled jobs, bots, scrapers, generated artifacts, CI/CD | Core + automation, live state, security, data |
| Release audit | Deployment or production-readiness decision | Core + all release-relevant conditional modules + high assurance |
| Incident audit | A failure, regression, or unexplained operational state | Core + timeline, live evidence, reproduction, containment and recurrence checks |

## 2. Non-negotiable audit rules

- [ ] **Core — Preserve the requested authority boundary.** “Audit,” “review,” “diagnose,” or “report only” does not authorize fixes, commits, pushes, workflow dispatches, production writes, messages, or configuration changes.
- [ ] **Core — Evidence, not confidence, determines the verdict.** Do not call something working because the code looks plausible, a plan says it is done, or an author reports success.
- [ ] **Core — Separate four questions:** was the requirement implemented, does the implementation behave correctly, is it integrated into the real path, and is it operating in the live system?
- [ ] **Core — Do not silently narrow scope.** If a requested platform, product, workflow, page, environment, or edge case cannot be verified, report it as `UNVERIFIED` or `BLOCKED`.
- [ ] **Core — Use primary evidence.** Prefer source, executable tests, generated artifacts, CI logs, deployment metadata, and authoritative APIs over summaries, stale local refs, screenshots without provenance, or other agents’ claims.
- [ ] **Core — Preserve the workspace.** Do not overwrite user work. Avoid creating caches, virtual environments, generated files, lockfile changes, or test data in the repository. Use an isolated worktree or temporary directory when practical.
- [ ] **Core — Never hide environmental limitations.** Record the exact interpreter, toolchain, dependency state, network restrictions, credentials unavailable, and tests not run.
- [ ] **Core — A passing audit must survive a hostile question:** “What evidence would prove this conclusion wrong?”

## 3. Establish the audit charter

Write this block before inspecting implementation details:

```text
Audit profile:
Requested outcome:
Original requirements and acceptance criteria:
Report-only or change-authorized:
Repository / service / environment:
Authoritative base:
Authoritative head:
Local working tree included? yes/no
Live production verification required? yes/no
External systems in scope:
High-risk triggers:
Explicit exclusions:
Known blockers:
```

- [ ] **Core** Convert the user’s wording, issue, plan, PR description, and follow-up instructions into atomic requirements.
- [ ] **Core** Identify the source of truth for each requirement; a later plan is not allowed to erase an earlier user requirement.
- [ ] **Core** Resolve ambiguous terms before assigning a passing verdict. If clarification is not available, state the assumption and audit both plausible interpretations when feasible.
- [ ] **Core** Define “done” as observable outcomes, not file changes.
- [ ] **High assurance** Identify required owners or specialists: security, privacy, data, accessibility, operations, legal/licensing, or domain expert.

## 4. Environment and repository preflight

- [ ] **Core** Read all applicable repository instructions before acting: root and nested `AGENTS.md`, contributor guidance, setup docs, test docs, and task-specific audit rules.
- [ ] **Core** Run the repository’s prescribed environment discovery or doctor command. Do not substitute ad hoc probing when the repository provides an authoritative command.
- [ ] **Core** Record the exact working directory, OS/shell, runtime executable, runtime version, dependency environment, and relevant tool versions.
- [ ] **Core** Capture the initial repository state, including tracked, untracked, and ignored files.
- [ ] **Core** Distinguish pre-existing changes from audit-created changes. The audit should normally end byte-for-byte clean relative to its starting state.
- [ ] **Core** Check whether the repository is shallow, detached, sparse, in a linked worktree, or missing submodules/LFS objects.
- [ ] **Core** Identify generated files, vendored code, submodules, lockfiles, and binary artifacts so the diff is interpreted correctly.
- [ ] **Conditional — Dependencies unavailable** Use the project’s declared environment first. If it is incomplete, report which checks are blocked; do not install or mutate dependencies without authority.
- [ ] **Conditional — Tests write files** Redirect caches and outputs to a temporary location, disable bytecode/cache generation when supported, or use an isolated worktree.

Suggested read-only Git snapshot, adapted to the repository:

```powershell
git status --short --branch
git status --porcelain=v2 --ignored
git rev-parse --show-toplevel
git rev-parse HEAD
git remote -v
git log --oneline --decorate -n 20
```

## 5. Resolve authoritative scope and remote truth

- [ ] **Core** Name the exact base and head under review. Do not rely on “current branch” or “latest” without resolving them to immutable commit IDs.
- [ ] **Core** Determine whether uncommitted work is included.
- [ ] **Core** Calculate the merge base when auditing a branch or PR.
- [ ] **Core** Inspect both the commit list and the aggregate diff; either alone can conceal scope.
- [ ] **Core** Inspect name/status, statistics, renames, mode changes, deletions, generated files, and submodule changes.
- [ ] **Core** Read the original issue, plan, PR description, review comments, and acceptance criteria if available.
- [ ] **Conditional — Remote or production claim** Query the authoritative remote directly with the Git provider/API/connector or `git ls-remote`. A local `origin/*` reference may be stale.
- [ ] **Conditional — PR audit** Confirm the PR’s actual base/head SHAs, mergeability, required reviews, status checks, changed files, and unresolved review threads.
- [ ] **Conditional — Deployment audit** Map source commit → build → artifact/provenance → deployment/environment. Do not infer deployment from a pushed commit.

Useful commands:

```powershell
git merge-base <base> <head>
git log --oneline <base>..<head>
git diff --name-status <base>...<head>
git diff --stat <base>...<head>
git diff --check <base>...<head>
git ls-remote origin refs/heads/<branch>
gh pr view <number> --json baseRefOid,headRefOid,files,commits,statusCheckRollup,reviews
```

## 6. Build a requirement traceability matrix

Create this table before deciding whether the work is complete:

| ID | Atomic requirement | Source | Implementation evidence | Test evidence | Artifact/UI evidence | Live evidence | Verdict |
|---|---|---|---|---|---|---|---|
| R1 |  |  |  |  |  |  |  |

Allowed verdicts:

- `PASS` — the required evidence exists and was verified.
- `PARTIAL` — some observable part is missing or incorrect.
- `FAIL` — the requirement is absent or contradicted.
- `UNVERIFIED` — implementation may exist, but required execution/live evidence was unavailable.
- `N/A` — not applicable, with a recorded reason.
- `BLOCKED` — a named constraint prevents meaningful verification.

- [ ] **Core** Include every explicit noun and verb in the request: each platform, entity, identifier, page, workflow, schedule, output, and comparison behavior.
- [ ] **Core** Check for “implemented generically but not configured concretely.” A generic multi-platform model does not prove that two real listings are configured, rendered, compared, and updated.
- [ ] **Core** Check for “present but unreachable.” Trace every capability from entry point to observable output.
- [ ] **Core** Check for “visible but inert.” A UI card or report row does not prove that the data collection and automation path works.
- [ ] **Core** Check for “plan applied verbatim but requirement omitted.” Audit against the original intent, not only the implementation plan.
- [ ] **Core** Record explicit negative evidence for missing requirements; do not treat an unsuccessful text search alone as proof.

## 7. Map architecture, data flow, and blast radius

- [ ] **Core** Identify changed entry points, callers, callees, shared helpers, state stores, external interfaces, background jobs, and generated outputs.
- [ ] **Core** Trace the main path end to end: input → validation → transformation → persistence → output → operational trigger.
- [ ] **Core** Identify sibling paths using the same helper or data shape. Test at least one sibling when shared behavior changed.
- [ ] **Core** Search for configuration, documentation, fixtures, schemas, snapshots, templates, and workflows that must remain synchronized.
- [ ] **Core** Identify old code paths that remain reachable and new states that have become reachable.
- [ ] **Conditional — Public interface** Map consumers and backward-compatibility constraints.
- [ ] **Conditional — Persistent data** Map schema versions, writers, readers, migrations, retention, and rollback behavior.
- [ ] **Conditional — External service** Map authentication, quotas, retries, rate limits, timeouts, data contracts, and failure isolation.
- [ ] **High assurance** Create a compact threat/data-flow model and identify trust boundaries.

## 8. Static correctness review

Review the diff and the surrounding implementation, not the diff alone.

- [ ] **Core** Confirm control flow, invariants, state transitions, error propagation, cleanup, and return values.
- [ ] **Core** Check empty, null/missing, malformed, duplicate, stale, partial, and unexpected inputs.
- [ ] **Core** Check off-by-one boundaries, inclusive/exclusive ranges, ordering, sorting, grouping, pagination, and tie behavior.
- [ ] **Core** Check time zones, daylight saving, clocks, locale, currency, rounding, units, precision, and date cutoffs.
- [ ] **Core** Check concurrency, reentrancy, idempotency, retries, duplicate delivery, cancellation, and race windows.
- [ ] **Core** Check resource lifetimes: files, processes, sockets, transactions, locks, and temporary artifacts.
- [ ] **Core** Check exception/error paths for misleading success, swallowed failures, unsafe fallbacks, or loss of diagnostic context.
- [ ] **Core** Check that identifiers are canonicalized consistently and that grouping/lookup keys cannot collide.
- [ ] **Core** Compare comments, names, docs, and type signatures with actual behavior.
- [ ] **Core** Search for every caller and serialization boundary of a changed function, model, field, or format.
- [ ] **Conditional — Performance-sensitive path** Review asymptotic work, repeated I/O, memory growth, batching, caching, backpressure, and realistic input size.
- [ ] **Conditional — Observability** Verify meaningful structured logs/metrics/traces, stable event names, correlation IDs, redaction, and actionable alerts.

## 9. Design tests before trusting existing tests

Use established test-design techniques, not just examples copied from the implementation.

- [ ] **Core — Equivalence partitions** Identify representative valid, invalid, empty, and permission/state classes.
- [ ] **Core — Boundary values** Test immediately below, at, and immediately above important thresholds.
- [ ] **Core — Decision tables** Enumerate combinations of inputs, permissions, feature flags, and external outcomes when behavior branches on several conditions.
- [ ] **Core — State transitions** Test legal and illegal transitions, retries, restarts, and repeated events.
- [ ] **Core — Adversarial cases** Test malformed/untrusted input, partial success, dependency failure, timeout, stale data, duplicate input, and unexpected ordering.
- [ ] **Core — Multi-entity regression** When code was generalized from one item/provider/user to many, test at least two real or realistic siblings simultaneously. This catches overwritten state, incorrect grouping, and single-item assumptions.
- [ ] **Core — Test oracle independence** Expected results must come from the requirement/specification or an independent reference calculation, not by repeating the production algorithm in the test.
- [ ] **Conditional — Algorithmic/data transformation** Add properties/invariants such as round trips, conservation, monotonicity, idempotence, or equivalence to a simpler reference implementation.
- [ ] **Conditional — Historical bug** Reproduce the exact failure and retain a regression case.

## 10. Execute the implementation safely

Static inspection proves presence, not behavior.

- [ ] **Core** Run the narrowest safe executable probe that exercises each new or changed pure behavior.
- [ ] **Core** Use deterministic fixtures, a fixed clock, fixed locale/time zone, and controlled randomness when those affect results.
- [ ] **Core** Record the exact command, exit code, relevant output, environment, and artifact examined.
- [ ] **Core** Exercise happy, empty, error, and multi-item/sibling cases.
- [ ] **Core** Compare actual output with an independently derived expected result.
- [ ] **Core** Inspect outputs semantically, not only for existence or non-zero size.
- [ ] **Conditional — Probe could write/network** Stub or fake the boundary, redirect to a temporary environment, or request authority. Do not contact production as a side effect of an audit.
- [ ] **Conditional — Execution impossible** Downgrade the conclusion to `UNVERIFIED`; list the exact missing dependency or permission and the highest-confidence static conclusion available.

## 11. Test portfolio and execution

- [ ] **Core** Identify the project’s canonical test, lint, format, type-check, build, and validation commands from repository instructions or CI.
- [ ] **Core** Run focused tests for the changed behavior, then the full relevant suite when feasible.
- [ ] **Core** Run tests with the project’s intended interpreter/environment, and report exact discovered/selected/skipped/failed counts.
- [ ] **Core** Confirm new behavior has tests in the same change unless there is a documented reason.
- [ ] **Core** Inspect the tests as carefully as production code: weak assertions, over-mocking, tautological expectations, snapshot churn, missing negatives, and assertions that never run.
- [ ] **Core** Ask: would this test fail if the implementation were reverted or the key condition were inverted? Verify this with a safe mutation when risk and tooling justify it.
- [ ] **Core** Classify the evidence: unit/component, integration, contract, end-to-end, exploratory/manual, and live/canary. Do not present one class as a substitute for all others.
- [ ] **Core** Distinguish hermetic tests from tests that depend on files, localhost services, networks, credentials, timing, or external systems.
- [ ] **Core** Investigate skips, retries, flakes, quarantines, and tests that pass only in a particular order.
- [ ] **Conditional — Baseline available** Run relevant checks on the base revision or otherwise identify pre-existing failures, without erasing or minimizing failures on the head revision.
- [ ] **Conditional — CI differs from local** Reproduce the CI runtime, matrix entry, environment variables, path, permissions, and command as closely as practical.
- [ ] **High assurance** Use mutation, fuzz, property-based, load, failure-injection, or concurrency testing where the risk model warrants it.

## 12. Generated artifacts and deterministic builds

- [ ] **Conditional — Generated output** Identify the canonical generator and source inputs; never audit generated output as if it were independently authored.
- [ ] Regenerate in an isolated worktree or temporary directory using the documented command.
- [ ] Compare regenerated output bytewise and semantically with the committed artifact.
- [ ] Parse structured formats (JSON/YAML/XML/HTML/CSV) and validate schema, counts, identifiers, links, ordering, and escaping.
- [ ] Confirm all required entities appear and no entity overwrites or masks a sibling.
- [ ] Confirm output contains no secrets, local paths, debug data, synthetic test data, or stale timestamps.
- [ ] Run the generator twice with identical inputs and check for unexplained nondeterminism.
- [ ] Check a no-op run: it should not create meaningless commits, timestamp-only churn, or perpetual diffs.
- [ ] Verify freshness per entity. A global maximum timestamp can make stale items appear current.
- [ ] Verify failure behavior: partial output, previous-good artifact retention, atomic replacement, and exit status.

## 13. Data, migrations, and state

- [ ] **Conditional — Persistent state** Inventory affected tables/files/objects, producers, consumers, constraints, retention, and personally sensitive data.
- [ ] Validate schema compatibility across old/new readers and writers during rollout and rollback.
- [ ] Test migration on representative size and shape, including empty, malformed legacy, duplicate, and maximum-size data.
- [ ] Verify uniqueness, foreign keys, nullability, defaults, indexes, precision, encodings, and time zones.
- [ ] Verify idempotency and safe restart after partial failure.
- [ ] Verify transaction/atomicity guarantees and failure recovery.
- [ ] Compare before/after row counts, checksums, or domain invariants; document acceptable differences.
- [ ] Confirm rollback/roll-forward strategy and backup/restore readiness.
- [ ] Ensure tests cannot contaminate production/history and synthetic records are unmistakably isolated.
- [ ] **High assurance** Rehearse migration and recovery on a production-like copy with sensitive data appropriately protected.

## 14. APIs, contracts, and compatibility

- [ ] **Conditional — Interface change** Identify all producers and consumers, including old clients, scheduled jobs, webhooks, exported files, and third parties.
- [ ] Compare wire names, types, required/optional fields, defaults, enums, status/error codes, and pagination.
- [ ] Verify authentication and authorization for every operation and object scope.
- [ ] Verify validation, size limits, rate limits, timeouts, retries, idempotency keys, and duplicate delivery.
- [ ] Verify forward/backward compatibility during rolling deployment.
- [ ] Add or run consumer/provider contract tests where feasible.
- [ ] Check documentation/examples against the actual contract.
- [ ] Treat silent semantic changes as breaking even if the schema is unchanged.

## 15. UI and accessibility

- [ ] **Conditional — User-visible change** Exercise the actual UI path, not only rendering helpers or snapshots.
- [ ] Verify loading, empty, stale, partial, error, retry, permission-denied, and offline/slow states.
- [ ] Verify multi-item and long/translated content, narrow/wide screens, zoom, and high data volume.
- [ ] Verify keyboard-only operation, logical focus order, visible focus, focus restoration, and no keyboard traps.
- [ ] Verify semantic names/roles/states, headings, labels, error association, live-region behavior, and image alternatives.
- [ ] Check contrast, non-color cues, target size, reflow, and reduced-motion behavior where applicable.
- [ ] Use automated accessibility checks plus knowledgeable manual evaluation; automation alone cannot establish conformance.
- [ ] Capture screenshots or recordings for visual evidence when helpful, with commit/build and viewport identified.
- [ ] Check analytics/telemetry consent and redaction if the UI introduces tracking.

## 16. Security and privacy

Use OWASP ASVS for application security requirements and OWASP WSTG for test coverage. Scale depth by likelihood × impact.

- [ ] **Conditional — Untrusted boundary or sensitive change** Enumerate entry points and trust boundaries before testing.
- [ ] Review authentication, session handling, authorization, tenancy/object ownership, privilege changes, and fail-closed behavior.
- [ ] Review input validation and output encoding for injection classes relevant to the stack.
- [ ] Review SSRF, unsafe redirects, path traversal, file upload/download, archive extraction, deserialization, template execution, and command execution where reachable.
- [ ] Review secret handling, token scopes, log/telemetry redaction, error messages, test fixtures, and repository history exposure.
- [ ] Review cryptography, key management, randomness, transport security, and certificate validation; do not invent custom cryptography.
- [ ] Review abuse controls, rate limits, replay, enumeration, resource exhaustion, and denial-of-service paths.
- [ ] Review data minimization, purpose, consent, retention, deletion, export, access logging, and regional/compliance constraints.
- [ ] Review dependency and build-pipeline trust, including install scripts and untrusted code execution.
- [ ] Describe each security finding with entry point, preconditions, exploit path, affected asset, impact, and evidence. Avoid unsupported severity inflation.
- [ ] **High assurance** Obtain an independent security specialist review and use the organization’s approved threat model and testing standard.

## 17. Dependencies and software supply chain

- [ ] **Conditional — Dependency/build change** Inspect manifest and lockfile together; identify direct and material transitive changes.
- [ ] Confirm versions resolve reproducibly and are compatible with supported runtimes/platforms.
- [ ] Check known vulnerabilities, maintainer/source legitimacy, release provenance where available, licenses, and operational maintenance risk.
- [ ] Prefer immutable pins for executable CI actions and other high-trust build inputs; document update strategy.
- [ ] Check for newly enabled install hooks, downloaded binaries, dynamic execution, broad network access, or unexpected platform packages.
- [ ] Verify dependency-review/secret-scanning/SAST results where configured; inspect findings rather than trusting a green summary alone.
- [ ] **High assurance** Produce or validate an SBOM and artifact provenance/attestation; verify the artifact was built by the expected hosted, isolated process from the expected source.

## 18. CI/CD, workflows, and automation

For automations, inspect configuration, actual run history/logs, generated state, and live outcome. Any one alone is insufficient.

- [ ] **Conditional — Workflow/automation in scope** Read every changed and relevant workflow/job/script, including reusable workflows and called actions.
- [ ] Verify triggers, branches/tags, paths, schedules, event payload assumptions, default-branch behavior, and manual triggers.
- [ ] Inspect recent actual run history and logs for the exact workflow and commit. Step conclusions alone can hide warnings, no-op churn, retries, or misleading success.
- [ ] For scheduled jobs, verify observed cadence, delays/drops, disabled state, inactivity rules, time zone/UTC interpretation, and overlapping runs.
- [ ] Verify permissions are least-privilege at workflow/job level and secrets are scoped to trusted contexts.
- [ ] Treat PR titles, branch names, issue bodies, event fields, and repository content as untrusted input; avoid direct interpolation into shell/code.
- [ ] Scrutinize `pull_request_target`, `workflow_run`, self-hosted runners, third-party actions, writable tokens, and checkout of untrusted code.
- [ ] Pin third-party actions to reviewed immutable commit SHAs where risk requires it.
- [ ] Verify job dependencies, conditions, failure propagation, cancellation, timeouts, retries, and concurrency groups.
- [ ] Verify tests/validation happen before publish/deploy/commit steps unless the ordering is explicitly justified and safely recoverable.
- [ ] Verify generated commits avoid no-op churn and do not rely on workflow-trigger behavior that `GITHUB_TOKEN` intentionally suppresses.
- [ ] Verify artifact naming, retention, integrity, provenance, environment protection, approvals, deployment target, and rollback.
- [ ] Verify idempotency, duplicate-trigger safety, partial failure handling, notification behavior, and recovery from a killed run.
- [ ] Confirm the automation updates the actual user-visible index/output and all configured entities, not just its internal data.

## 19. Live and production verification

- [ ] **Conditional — Operational claim** Verify the current remote SHA, deployed version, workflow run, artifact digest, and environment from authoritative sources.
- [ ] Distinguish “merged,” “built,” “deployed,” “healthy,” and “functionally correct.” They are separate states.
- [ ] Check health signals relevant to the change: errors, latency, saturation, throughput, data freshness, queue/backlog, and business/domain invariants.
- [ ] Validate freshness and correctness per tenant/item/provider/region; aggregates can conceal a broken subset.
- [ ] Compare a release candidate/canary with a control or baseline when rollout risk justifies it.
- [ ] Confirm alert coverage and rollback/kill-switch readiness before broad release.
- [ ] Do not mutate production, dispatch workflows, replay events, or create real transactions during an audit without explicit authority.
- [ ] If live access is unavailable, mark live claims `UNVERIFIED` rather than extrapolating from local or CI evidence.

## 20. Documentation and repository hygiene

- [ ] **Core** Verify documentation, configuration examples, changelog/release notes, runbooks, and comments match actual behavior.
- [ ] **Core** Check for stale TODOs, contradictory plans, debug code, temporary files, audit artifacts, local environments, caches, and accidental binaries.
- [ ] **Core** Check that ignored files are appropriate and no required source/artifact is only present locally.
- [ ] **Core** Confirm error messages and operator instructions are actionable and do not leak secrets.
- [ ] **Conditional — Behavioral or operational change** Confirm support, rollback, monitoring, and incident-response documentation is updated.
- [ ] **Conditional — Deprecated path** Confirm migration guidance, compatibility window, and removal criteria.

## 21. Perform an independent second pass with one subscription

The second pass must use a different review lens and must not merely summarize the first pass.

### Pass 1 — Requirements and implementation

- [ ] Build the traceability matrix from original requirements.
- [ ] Trace each requirement through code, tests, artifacts, workflows, and live state.
- [ ] Record provisional findings with evidence and confidence.

### Pass 2 — Adversarial verification

- [ ] Start a fresh Codex task or clear phase with the checklist and primary artifacts, not the prose conclusions from Pass 1.
- [ ] Ask what Pass 1 assumed, did not execute, or treated as authoritative without verification.
- [ ] Reproduce every material finding independently or downgrade its confidence.
- [ ] Search specifically for false positives: alternate call paths, feature flags, generated sources, platform behavior, and intentional constraints.
- [ ] Search specifically for false negatives: omitted requirements, sibling entities, live divergence, no-op churn, stale refs, partial failures, security boundaries, and cleanup.
- [ ] Reconcile disagreements using stronger evidence, not majority vote or model confidence.

### Pass 3 — Operations and release lens when applicable

- [ ] Inspect CI logs, authoritative remote state, deployment provenance, production signals, rollback, and alerting.
- [ ] Challenge local-only conclusions against operational reality.

For high-assurance work, the independent pass should be performed by a person who did not author the change. One AI subscription can improve independence through a fresh task and explicit adversarial framing, but it does not create organizational separation of duties.

## 22. Finding quality and severity

Every actionable finding must include:

```text
[Severity] Short imperative title
Requirement or invariant:
Impact:
Trigger / preconditions:
Expected:
Actual:
Evidence: file:line, command/log/run/artifact/URL
Reproduction:
Affected scope:
Confidence: high / medium / low
Why existing tests or controls did not catch it:
Remediation direction (no implementation unless authorized):
```

Severity is based on impact, reachability/likelihood, detectability, and recovery difficulty:

| Level | Meaning |
|---|---|
| P0 Critical | Active or readily exploitable catastrophic security, safety, financial, privacy, or irreversible data-loss risk; release/operation must stop. |
| P1 High | A material requested capability is missing/broken, or a reachable defect can cause serious incorrect behavior, security exposure, data corruption, or broad outage. |
| P2 Medium | A real defect under plausible edge/operational conditions, limited-scope reliability problem, or meaningful control/test gap. |
| P3 Low | Low-impact correctness, maintainability, observability, documentation, or hygiene defect with a concrete future cost. |
| Note | Useful context or improvement idea that is not a demonstrated defect. Do not inflate it into a finding. |

- [ ] **Core** Give the tightest useful file/line or log/run reference.
- [ ] **Core** State causality and user/operational impact, not merely a code smell.
- [ ] **Core** Include a realistic trigger; if none is known, lower confidence or report an open question.
- [ ] **Core** Keep separate defects separate, but group duplicate manifestations of one root cause.
- [ ] **Core** Report “no findings” only after listing scope, executed evidence, and residual risks.

## 23. Verdict rules

Use a scoped conclusion, never a blanket “looks good.”

```text
Verdict: PASS / PASS WITH RESIDUAL RISK / PARTIAL / FAIL / BLOCKED
Scope actually verified:
Requirements passed / partial / failed / unverified:
Commands and environments executed:
CI/live evidence inspected:
Material findings:
Residual risks and exclusions:
Workspace changed by audit: no / yes (explain)
```

- `PASS` requires all in-scope atomic requirements to pass with the evidence appropriate to their layer.
- `PASS WITH RESIDUAL RISK` requires no known material defect, but names limited evidence or accepted risk.
- `PARTIAL` means some required behavior exists but at least one required outcome is missing or unverified.
- `FAIL` means a material requirement or invariant is contradicted by evidence.
- `BLOCKED` means a named constraint prevents a responsible verdict.
- Static presence can support “implemented,” but not “works.”
- Local tests can support “works locally in this environment,” but not “CI passes” or “production is correct.”
- A green workflow conclusion does not prove the intended work occurred; inspect logs and resulting artifacts.
- A deployed artifact does not prove user-visible behavior; exercise or observe the real path.

## 24. Stop and escalation conditions

Stop, preserve evidence, and request direction when:

- [ ] The base/head, repository, environment, or original requirement cannot be identified reliably.
- [ ] Verification would require a production write, workflow dispatch, destructive command, credential expansion, or external communication not authorized by the request.
- [ ] A command would overwrite user work or an unknown dirty workspace.
- [ ] Secrets, personal data, exploit material, or signs of active compromise require controlled handling.
- [ ] A test/migration could cause data loss, cost, abuse, account lockout, rate-limit exhaustion, or outage.
- [ ] Required dependencies or access are unavailable and no safe representative substitute exists.

Being blocked does not justify guessing. Report what is known, what is not known, the evidence collected, and the smallest action needed to unblock verification.

## 25. Final audit exit checklist

- [ ] The audit charter and exact commit scope are recorded.
- [ ] Applicable repository instructions were followed.
- [ ] The authoritative remote/live state was checked when claimed.
- [ ] Every original requirement appears in the traceability matrix.
- [ ] Changed behavior was executed, or explicitly marked unverified.
- [ ] Happy, empty, error, boundary, partial-failure, and multi-entity/sibling cases were considered.
- [ ] Focused and full relevant checks were run with exact counts, or blockers were reported.
- [ ] Tests were assessed for whether they can actually detect the defect.
- [ ] Generated artifacts and no-op determinism were checked when applicable.
- [ ] CI configuration and actual logs were both inspected when applicable.
- [ ] Security, privacy, accessibility, dependency, data, and operations modules were applied or marked `N/A` with reasons.
- [ ] An adversarial second pass challenged both false positives and false negatives.
- [ ] Every finding has impact, trigger, evidence, reproduction, confidence, and appropriate severity.
- [ ] The verdict distinguishes implemented, locally verified, CI verified, deployed, and live verified.
- [ ] Residual risk and exclusions are explicit.
- [ ] The workspace is unchanged from the audit’s starting state, or every audit-created change is disclosed.

## 26. Codex repository integration

Keep durable repository instructions concise. Add a rule like this to the appropriate `AGENTS.md` only when the repository owner chooses to adopt the checklist:

```markdown
For audit, review, diagnosis, or report-only tasks, read and follow
`codex-audit-checklist.md`. Record skipped conditional sections as `N/A` with a
reason. User instructions and narrower nested `AGENTS.md` files take precedence.
```

Use a task-specific audit document for consequential domain invariants that are too detailed for `AGENTS.md`. Keep fast, deterministic, mechanical rules in CI. Convert this checklist into a Codex skill only after the procedure is stable and repeatedly useful.

Maintenance rule: whenever an audit misses a material issue, add the smallest general rule that would have caught it, its trigger, and the evidence required. Review this document after major platform/toolchain changes and at least annually.

## 27. Research basis

This checklist synthesizes senior engineering, QA, security, release, and Codex practices from the following primary or authoritative sources:

- OpenAI Codex, [Best practices](https://learn.chatgpt.com/guides/best-practices.md), [AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md.md), and [Code review](https://learn.chatgpt.com/docs/code-review?surface=app).
- OpenAI, [Custom code review rules for Codex](https://developers.openai.com/blog/custom-code-review-rules-for-codex.md).
- NIST, [Secure Software Development Framework (SP 800-218)](https://csrc.nist.gov/pubs/sp/800/218/final).
- OWASP, [Application Security Verification Standard](https://owasp.org/www-project-application-security-verification-standard/) and [Web Security Testing Guide](https://owasp.org/www-project-web-security-testing-guide/latest/).
- Google Engineering Practices, [The standard of code review](https://google.github.io/eng-practices/review/reviewer/standard.html), [What to look for](https://google.github.io/eng-practices/review/reviewer/looking-for.html), and [Small changes](https://google.github.io/eng-practices/review/developer/small-cls.html).
- Google Testing Blog, [Test sizes](https://testing.googleblog.com/2010/12/test-sizes.html) and [Just say no to more end-to-end tests](https://testing.googleblog.com/2015/04/just-say-no-to-more-end-to-end-tests.html).
- Google SRE Workbook, [Canarying releases](https://sre.google/workbook/canarying-releases/).
- GitHub Docs, [Dependency review](https://docs.github.com/en/pull-requests/how-tos/review-pull-requests/reviewing-dependency-changes-in-a-pull-request), [Protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches), [Push protection](https://docs.github.com/en/code-security/concepts/secret-security/push-protection), [Secure use of GitHub Actions](https://docs.github.com/en/actions/reference/security/secure-use), [Script injections](https://docs.github.com/en/actions/concepts/security/script-injections), [Troubleshooting workflows](https://docs.github.com/en/actions/how-tos/troubleshoot-workflows), [GITHUB_TOKEN](https://docs.github.com/en/actions/concepts/security/github_token), and [Concurrency](https://docs.github.com/en/actions/concepts/workflows-and-actions/concurrency).
- OpenSSF, [Scorecard](https://scorecard.dev/) and [Concise Guide for Developing More Secure Software](https://best.openssf.org/Concise-Guide-for-Developing-More-Secure-Software.html).
- SLSA, [Specification 1.2](https://slsa.dev/spec/v1.2/), [Build requirements](https://slsa.dev/spec/v1.2/build-requirements), and [Source requirements](https://slsa.dev/spec/v1.2/source-requirements).
- SPDX, [SPDX 3.0.1 specification](https://spdx.dev/wp-content/uploads/sites/31/2024/12/SPDX-3.0.1-1.pdf).
- CISA, [Shifting the Balance of Cybersecurity Risk: Principles and Approaches for Security-by-Design and -Default](https://www.cisa.gov/sites/default/files/2023-06/principles_approaches_for_security-by-design-default_508c.pdf).
- W3C, [Web Content Accessibility Guidelines 2.2](https://www.w3.org/TR/WCAG22/) and [Evaluating Web Accessibility](https://www.w3.org/WAI/test-evaluate/).
- ISTQB, [Certified Tester Foundation Level syllabus 4.0.1](https://istqb.org/wp-content/uploads/2024/11/ISTQB_CTFL_Syllabus_v4.0.1.pdf).
- ISO/IEC/IEEE, [29119 software testing series overview](https://committee.iso.org/sites/jtc1sc7/home/projects/flagship-standards/isoiecieee-29119-series.html).
- Martin Fowler, [The Practical Test Pyramid](https://martinfowler.com/articles/practical-test-pyramid.html).
- Hypothesis, [Property-based testing introduction](https://hypothesis.readthedocs.io/en/latest/tutorial/introduction.html).
- PIT, [Mutation testing](https://pitest.org/).

