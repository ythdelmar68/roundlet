---
name: roundlet
description: Run a lightweight, prompt-native outer loop that selects one actionable GitHub issue at a time, coordinates a persistent Orchestrator, one persistent Worker, and fresh read-only Supervisors, records an append-only GitHub trace, merges only when repository authority permits, and cleans up before selecting the next issue. Use when activating, operating, pausing, stopping, recovering, or auditing a single-repository Roundlet run.
---

# Roundlet

Operate a single-target-repository outer loop through Codex tasks, GitHub, Git worktrees, and two advisory local files. Do not introduce or depend on a Python runtime, database, executable validator, package, migration layer, runtime metrics, or cross-platform compatibility matrix.

## Preserve these invariants

- Use exactly one long-lived Orchestrator task, one phase-aware heartbeat, one authoritative machine, and at most one active leaf issue for a target repository.
- Refuse activation when another live or unreconciled Roundlet run may own that target. The file lease is advisory and never prevents split-brain across machines, clones, or Codex tasks.
- Treat GitHub issues and pull requests as the durable backlog and audit history. Let only the Orchestrator mutate GitHub.
- Keep the same Worker task for initial implementation, repairs, the optional final repair, and cleanup preflight. Create a fresh read-only Supervisor task for every review attempt.
- Bind every Worker and Supervisor turn to explicit issue, pull-request, phase, review epoch/round, and full commit SHA context. Bind each Supervisor turn and result to its attempt number and configured attempt profile. Require each role to reread the live sources defined by the role contract.
- Run only one issue through implementation and cleanup before selecting another issue.
- Keep core orchestration and safety rules in this file. Do not move them into a target repository's `AGENTS.md`.
- Read repository authority only from the root `AGENTS.md` on authoritative `origin/main`. Boolean authority may narrow Roundlet, never override stricter repository or platform policy.
- Fail closed when configured models, reasoning efforts, Supervisor attempt profiles, tools, GitHub permissions, merge method, repository authority, or required state cannot be verified. Never substitute a model, effort, or attempt profile silently.
- Treat GitHub CLI failures observed before GitHub is reachable as connectivity evidence, not credential rejection. When `gh` is required, require the model to request the narrowest scoped network escalation automatically; the skill cannot grant or assume network access. Never replace the request with browser authentication or browser automation. Keep bounded connectivity recovery out of Roundlet state transitions and owner input, and fail closed only when approval is explicitly denied, approval capability is unavailable, reachable GitHub rejects authentication, or bounded recovery proves the required connectivity unavailable.
- Use phase-aware lightweight observations only to prove that the last fully reconciled baseline is unchanged. Fingerprint the complete paginated scheduling graph and the exact active resources required by the phase; any change, omission, overflow, malformed value, due full audit, or action-ready state requires full live reconciliation in the same tick before reasoning or mutation. A fingerprint never authorizes a mutation.
- Never auto-expire, steal, or replace a lease. Recovery requires explicit owner direction after reconciliation.
- Couple a GitHub closing keyword only to the one active leaf that the pull request is intended to close. A negated phrase does not neutralize GitHub's keyword parser.
- Never rebase, force-push, bypass protection, destroy unique work, close an umbrella issue, or claim Supervisor PASS after the review limit.

## Read the operating contract

Before activation or recovery, read all of:

- [`references/roundlet-config.json`](references/roundlet-config.json) for role, heartbeat, review, merge, and owner settings.
- [`references/launcher.md`](references/launcher.md) for the copyable Launcher and recovery prompts.
- [`references/repository-authority.md`](references/repository-authority.md) for the copyable target-repository authority block.
- [`references/operator-guide.md`](references/operator-guide.md) for issue classification, scheduling, lifecycle, trace, blocking, recovery, cleanup rules, and copyable owner command prompts.
- [`references/thread-prompts.md`](references/thread-prompts.md) for Orchestrator, Worker, and Supervisor prompt contracts.

Treat those references as required parts of this skill, not optional background.

## Activate through the Launcher

Use the Launcher prompt verbatim except for its explicit placeholders. The short-lived Launcher must:

1. Resolve the exact target repository, authoritative checkout, owner identity, and configuration.
2. Perform the capability, repository, GitHub, local-state, model, and authority preflight.
3. Reconcile any existing `.roundlet/lease.json` or `.roundlet/current.md`; never take over automatically.
4. Create the configured long-lived Orchestrator task and wait for its exact `ACTIVATION_READY` response.
5. Attach one heartbeat at configured `heartbeat.active_minutes` to that Orchestrator, send it the heartbeat identity, and archive the Launcher.

Do not attach the heartbeat to the Launcher. Do not proceed after a partial or ambiguous preflight.

## Run the outer loop

On activation and each heartbeat:

1. Read the bounded advisory state and compute the phase-aware observation vector defined in the operator guide. When it is not a complete exact match for the last fully reconciled baseline, perform full GitHub, Git, Codex task, heartbeat, lease, contract, authority, and current-state reconciliation in the same tick before acting.
2. If paused, stopped, awaiting owner input, blocked on repository authority, or already processing an issue, follow that state instead of scheduling.
3. If IDLE observation is unchanged, make no scheduling mutation and apply the configured no-op heartbeat backoff. Otherwise scan every open issue in the target repository, including issues created after activation.
4. Exclude umbrella, scheduling-blocked, ignored, non-actionable, dependency-blocked, and already-owned issues.
5. Rank all ready leaf candidates across umbrellas using the contract in the operator guide.
6. Claim exactly one issue, record selection on GitHub, create one `codex/` branch and isolated worktree, then keep the same Worker task through its lifecycle.
7. After the initial Worker handoff, comment on the issue, push the exact candidate SHA, and create a draft pull request.
8. Run bounded Supervisor/Worker review cycles and append every completed handoff to the pull request.
9. At a valid terminal review state, satisfy live merge gates, mark ready when authorized, merge with the configured merge method, verify or close the leaf issue, and perform ordered cleanup.
10. Select no new issue until cleanup proves the authoritative checkout, `main`, and `origin/main` are aligned and all issue-specific resources are removed.

Keep the heartbeat at `active_minutes` while work is active or an observation is incomplete. After consecutive unchanged IDLE observations, advance through `idle_noop_backoff_minutes`; while waiting for owner input, advance through `owner_input_noop_backoff_minutes`. Reset to the active interval on any change or direct owner instruction. A paused run has no heartbeat polling. Finishing an issue returns to IDLE and continues scheduling unless the owner explicitly requested stop-after-current.

## Bound the inner loop

- Rounds 1–3, when reached, are COMPLETE reviews. Any valid PASS ends review early.
- Rounds 4–10 are CONVERGING reviews. They focus on prior findings and the delta but may report a new blocking regression or missing evidence.
- Keep the review epoch, round, mode, and candidate SHA unchanged while Supervisor attempts advance through the configured ordered profiles. Accept only a valid `SUPERVISOR_RESULT` bound to all of them; never treat task failure text as findings or PASS, and never send an invalid attempt to the Worker.
- A Supervisor attempt that is invalid, fails, is cancelled, is inaccessible, is malformed, or reviews the wrong SHA does not consume a round. Advance only to the next configured attempt profile, without parsing display text to guess a policy or cybersecurity cause. After the configured attempt budget is exhausted, enter `NEEDS_OWNER_INPUT`.
- When round 10 returns findings, send them once to the same Worker for a final repair. Do not run round 11 and do not claim PASS. Record `REVIEW_LIMIT_REACHED_WORKER_FINALIZED`, then apply all normal checks and merge gates.
- An allowlisted owner scope change starts a new review epoch at round 1 COMPLETE.

## Stop safely

- `pause` takes effect at a safe checkpoint, pauses the heartbeat, and preserves the task, lease, branch, worktree, and current state for manual resume.
- `stop-after-current` finishes the active issue and cleanup, then stops the heartbeat, releases the lease, and archives the Orchestrator. If idle, stop immediately.
- A closed, ignored, or withdrawn active issue requires an explicit owner abort decision. Never silently abandon work or continue to the next issue while preserving the old issue's resources.
- Any unresolved ambiguity that could affect scope, dependency order, data safety, or an irreversible mutation enters `NEEDS_OWNER_INPUT` and stops global scheduling.
