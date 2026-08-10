---
name: roundlet
description: Run a lightweight, prompt-native outer loop that selects one actionable GitHub issue at a time, coordinates a persistent Orchestrator, one persistent Worker, and fresh read-only Supervisors, records a GitHub trace, merges only when repository authority permits, and cleans up before selecting the next issue. Use when activating, operating, pausing, stopping, recovering, or auditing a single-repository Roundlet run.
---

# Roundlet

Operate one target repository through Codex tasks, GitHub, Git worktrees, advisory local state, and one immutable activation-time contract bundle. Do not introduce a Python runtime, database, executable validator, package, live-update layer, metrics runtime, or platform matrix.

## Preserve the core invariants

- Use exactly one long-lived Orchestrator, one phase-aware heartbeat, one authoritative machine, and at most one active leaf issue for a target repository.
- Pin each new run to one content-addressed bundle under `.roundlet/contracts/<contract-id>/`. Include this file, every required reference, the exact resolved configuration, and a manifest of ordered paths and SHA-256 values. When the source is Git, materialize every bundled file from the verified commit object rather than checkout bytes so filters or line-ending conversion cannot change the claimed source. Read live instructions only from that bundle.
- Never migrate or adopt a changed installed skill into a live run. Stop and fully clean the old run, then start a fresh activation from the new installed copy.
- Refuse activation when another live or unreconciled Roundlet run may own the target. The local lease is advisory and never proves exclusivity across machines, clones, or tasks.
- Treat GitHub issues and pull requests as the durable backlog and audit history. Only the Orchestrator mutates GitHub. Route every curated event through the authoritative destination matrix in `references/operator-guide.md`: issue before pull-request creation, top-level pull-request Conversation for candidate/review evidence after the pull request exists, pull-request metadata for merge state, and issue again for leaf lifecycle and cleanup. Search both conversations before an ambiguous retry and read every write back from its selected surface.
- Keep the same Worker task for implementation, repairs, optional final repair, and cleanup preflight. Create a fresh read-only Supervisor for every review attempt.
- Create each role task with one metadata-only, mutation-free first turn that may return a non-authoritative role metadata report. Before role work, the creator constructs and, only after successful validation, records exactly one `CREATOR_TASK_BINDING_ATTESTATION` from immutable creator-side read-back: exact role task ID, creator/source task, requested role, configured model and reasoning effort, project/workspace, canonical CWD, and available stable host/environment identity. A role report can neither satisfy nor invalidate that attestation. One explicit contradiction permits one bounded creator-side re-read; only missing, stale, malformed, mismatched, or still-conflicting creator evidence fails binding. Bind later turns to the attestation and to explicit issue, pull-request, phase, review epoch/round, and full candidate SHA.
- Run one issue through implementation and cleanup before selecting another.
- Read repository authority only from root `AGENTS.md` on authoritative `origin/main`. Boolean authority may narrow Roundlet but never override stricter repository or platform policy.
- Fail closed when repository identity, configured profiles, required tools, GitHub permissions, merge method, repository authority, active contract identity, unique work, or live state cannot be verified. Never substitute a model, effort, attempt profile, or contract.
- When root repository instructions explicitly declare a validation-toolchain contract, bind all affected build, test, packaging, and review evidence to that contract as defined in `references/operator-guide.md`. A system-discovered bootstrap interpreter may invoke the repository resolver but is never validation evidence. Provision a wholly absent exact cache lazily on first required validation; reject partial or invalid evidence without falling back to host build tools. A repository-owned cache below the authoritative checkout's `.roundlet/validation-tools/` is generated host state, not a Roundlet runtime or source tree.
- When authoritative root instructions declare repository-owned external-validation routing, use only the generic routes `none`, `toolbox`, and `toolbox+disposable-target`. Bind the selected leaf, referenced instruction/skill paths and exact bytes, concrete repository/commit identities, permitted actions, evidence-time field, rollback, and read-back procedure at selection. Roundlet core never supplies target-specific names or scope.
- Treat `allow_external_validation_read_only` and `allow_external_validation_disposable_target_mutation` as independent repository-authority switches. A matching standing `true` removes repetitive per-attempt approval only inside the exact repository-owned route; it never waives credentials, identity, allowlist, rollback, or semantic read-back gates.
- Historical replay uses the immutable evidence capture time declared by the selected repository contract. Never substitute replay execution wall-clock time for that captured time.
- Treat a GitHub CLI failure before GitHub is reachable as connectivity evidence, not credential rejection. Request the narrowest scoped network approval for the same command, use bounded retry, and never substitute browser authentication or browser automation.
- Use lightweight observations only to prove a fully reconciled baseline unchanged. Any change, omission, overflow, malformed value, due full audit, or action-ready phase requires full live reconciliation in the same tick before mutation.
- Never auto-expire, steal, or replace a lease. Recovery requires explicit owner direction after reconciliation.
- Couple a GitHub closing keyword only to the active leaf intended to close. A negated phrase does not neutralize GitHub's parser.
- Never rebase, force-push, bypass protection, destroy unique work, close an umbrella issue, or claim Supervisor PASS after the review limit.

## Native Windows only

Apply this section only when the role's verified runtime is native Windows. Do not generalize it to WSL, Linux, macOS, or another host.

- Create each Worker in a dedicated host-owned task anchor. Its canonical CWD must be the anchor, never the removable linked worktree or a descendant of that worktree.
- Place the linked worktree at a distinct writable child path below the anchor and bind the exact anchor/worktree pair before implementation. A host process retaining the separate anchor CWD is lifecycle evidence, not a holder of the child worktree.
- Use the dedicated normal-sandbox `apply_patch` tool directly for Worker source edits. Never wrap it in PowerShell, a pipeline, a here-string/here-document, a batch file, or an elevated shell.
- If linked-worktree Git metadata resolves outside normal writable roots, request only the narrowest approval needed for that exact Git metadata operation. Do not broaden approval to source edits or unrelated paths.
- During cleanup, distinguish task archival, Git registration, unique work, and physical-path removal. Successful non-force removal plus absent registration/path is sufficient; inspect exact-worktree CWD holders only when ordinary removal fails. Never kill Codex or Node to manufacture cleanup. A surviving host-owned empty anchor is not a Roundlet worktree and does not by itself block verified child-worktree cleanup.

## Read the operating contract

For a new activation, read the installed copies below. For an active run or recovery, resolve the activation record and read the same paths only from its verified immutable bundle. Routine owner commands and recovery prompts must not reload the installed `$roundlet` skill as live instructions.

- [`references/roundlet-config.json`](references/roundlet-config.json): role profiles, heartbeat cadence, review limits, merge method, and owner allowlist.
- [`references/launcher.md`](references/launcher.md): copyable new-activation and explicit-recovery prompts.
- [`references/repository-authority.md`](references/repository-authority.md): copyable target-repository authority block.
- [`references/operator-guide.md`](references/operator-guide.md): scheduling, lifecycle, trace, blocking, recovery, and cleanup rules.
- [`references/thread-prompts.md`](references/thread-prompts.md): Orchestrator, Worker, and Supervisor contracts.

Treat every referenced file as required.

## Activate through the Launcher

Use the New activation prompt in `references/launcher.md` without changing anything except its explicit placeholders. The short-lived Launcher must:

1. Verify its immutable model/effort and authoritative writable-checkout binding, then prove repository, owner, GitHub, task, heartbeat, Git, authority, and cleanup capabilities.
2. Reconcile all local and remote evidence and stop on any stale or active run.
3. Reserve one unguessable run ID; build, persist, and read back one immutable activation bundle.
4. Create and read back advisory lease/current state for that run.
5. Create exactly one configured long-lived Orchestrator, record its creator-verified binding attestation once, and require exact `ACTIVATION_READY` without issue selection.
6. Create exactly one recurring heartbeat bound only to that Orchestrator, require exact `HEARTBEAT_BOUND`, verify all IDs agree, and send one initial tick.
7. Report the activation and archive the Launcher, leaving the Orchestrator and heartbeat active.

Do not attach the heartbeat to the Launcher. Do not create a second Orchestrator or heartbeat. Do not continue after a partial or ambiguous preflight or read-back.

## Run the outer loop

On activation and each heartbeat:

1. Resolve and verify the one immutable activation bundle. Fingerprint the installed skill separately but never adopt it into the live run.
2. Fully reconcile whenever the bounded observation is not an exact match, the phase is action-ready, or the full-audit bound is due.
3. Honor pause, stop-after-current, owner-input, authority, and active-issue states before scheduling.
4. Scan every open issue, exclude umbrellas and non-runnable/dependency-blocked/owned items, classify any repository-declared external-validation route, and rank ready leaf candidates by the operator contract.
5. Select exactly one leaf. Bind any repository-owned external-validation contract and standing authority before provisioning. Create one unpublished `codex/` branch and isolated worktree, then create and verify one persistent Worker. On native Windows, create the Worker at its distinct anchor before the descendant worktree; on other hosts, use the ordinary worktree-first topology.
6. Record selection only after the branch, worktree, Worker identity, and clean starting state read back correctly. Send implementation to that same Worker.
7. Publish the initial Worker handoff on the leaf issue, push the exact candidate, create a draft pull request, and publish/read back that creation event on the leaf issue.
8. After the pull request exists, run bounded fresh-Supervisor/same-Worker review cycles and publish candidate, repair, validation, and review evidence only to its top-level pull-request Conversation.
9. At a valid terminal review state, satisfy live merge gates, mark ready when authorized, merge with the configured method, verify or close the leaf, and perform ordered cleanup.
10. Select no new issue until cleanup proves the authoritative checkout, `main`, and `origin/main` align and all issue resources are removed.

Keep the heartbeat at `active_minutes` while work is active or observations are incomplete. Back off only after consecutive unchanged IDLE or owner-input observations according to configuration. Reset on any change or direct owner instruction. Pause removes polling. Finishing one issue returns to IDLE unless the owner requested stop-after-current.

## Bound the inner loop

- Rounds 1–3, when reached, are COMPLETE reviews. Any valid PASS ends review early.
- Rounds 4–10 are CONVERGING reviews. They focus on prior findings and the delta but may report a new blocking regression or missing evidence.
- Keep epoch, round, mode, and candidate SHA unchanged while attempts advance through configured profiles. Invalid, failed, cancelled, inaccessible, malformed, or wrong-SHA attempts do not consume a round and never become findings or PASS.
- Classify an attempt as invalid-binding only from a failed creator binding attestation. A missing, short, reordered, differently rendered, or task-ID-free role report cannot consume a Supervisor attempt, advance a profile, publish a discard reason, or invalidate a matching creator attestation.
- After the configured attempt budget is exhausted, enter `NEEDS_OWNER_INPUT`.
- If round 10 returns findings, send them once to the same Worker for final repair. Do not run round 11 or claim PASS. Record `REVIEW_LIMIT_REACHED_WORKER_FINALIZED`, then apply normal merge gates.
- Preserve epoch, accepted-round count, and review mode across pause, resume, same-task continuation, and authorized recovery when the immutable contract, leaf scope, acceptance criteria, and candidate review basis are unchanged. Satisfying an already-declared standing validation route is not a scope change.
- An allowlisted owner change to scope or acceptance criteria starts a new review epoch at round 1 COMPLETE. The existing main-integration rule also starts a new COMPLETE epoch because it changes the review basis.

## Stop safely

- `pause` takes effect at a safe checkpoint, pauses the heartbeat, and retains current resources for manual resume.
- `stop-after-current` finishes the active issue and cleanup, removes the heartbeat, releases advisory state and contract bundles after final reconciliation, and archives the Orchestrator. If IDLE, stop immediately.
- Normal stop and issue cleanup retain a repository-declared shared validation cache. Remove or rebuild it only as a separate exact owner-directed cache action after validating the target path and preserving evidence of corruption or drift.
- A closed, ignored, or withdrawn active issue requires an explicit owner abort decision.
- Any unresolved ambiguity affecting scope, dependency order, data safety, unique work, or irreversible mutation enters `NEEDS_OWNER_INPUT` and stops scheduling.
