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
- Treat a schema-valid Supervisor PASS or FINDINGS as one accepted formal-round result. A valid FINDINGS consumes that round; after the same Worker repairs and the candidate changes, the next Supervisor is always the next formal round at attempt 1. Candidate movement can never be represented as another attempt in the prior fixed round.
- Advance within one fixed round and candidate only for an invalid, failed, cancelled, inaccessible, malformed, wrong-context, or wrong-SHA Supervisor attempt. Persist and read back the canonical Supervisor-result event and, after FINDINGS, the Worker-repair-handoff event before changing round state.
- Create each role task with one metadata-only, mutation-free first turn that may return a non-authoritative role metadata report. Before role work, the creator constructs and, only after successful validation, records exactly one `CREATOR_TASK_BINDING_ATTESTATION` from immutable creator-side read-back: exact role task ID, creator/source task, requested role, configured model and reasoning effort, task route, requested saved project when applicable, actual workspace/CWD, Git common directory and starting ref/SHA for a repository worktree, and available stable host/environment identity. A role report can neither satisfy nor invalidate that attestation. One explicit contradiction permits one bounded creator-side re-read; only missing, stale, malformed, mismatched, or still-conflicting creator evidence fails binding. The top-level creator copies the complete verified attestation into the populated Launcher prompt; the Launcher consumes it as authority and never requires a role-side immutable self-metadata route. Creators of later roles record and copy their attestations into the corresponding role envelopes and advisory state. Bind later turns to the attestation and to explicit issue, pull-request, phase, review epoch/round, and full candidate SHA.
- For every Git-repository Worker or Supervisor, resolve exactly one saved local project whose canonical path and Git common directory identify the authoritative repository, then use the Codex App's asynchronous project/worktree task route. Require the App-managed checkout detached at the requested existing ref's exact SHA. Keep one persistent Worker task/worktree for implementation and repairs. Create each Supervisor as a fresh read-only task/worktree from the candidate ref and independently compare its pre/post Git snapshots. Exact-candidate sharing means identical repository identity and full SHA, never a shared physical worktree. Projectless tasks are allowed only for non-repository roles or after an explicit capability proves a caller-supplied canonical CWD; never use an output-directory hint as CWD evidence.
- Run one issue through implementation and cleanup before selecting another.
- Read repository authority only from root `AGENTS.md` on authoritative `origin/main`. Boolean authority may narrow Roundlet but never override stricter repository or platform policy.
- Fail closed when repository identity, configured profiles, required tools, GitHub permissions, merge method, repository authority, active contract identity, unique work, or live state cannot be verified. Never substitute a model, effort, attempt profile, or contract.
- When root repository instructions explicitly declare a validation-toolchain contract, bind all affected build, test, packaging, and review evidence to that contract as defined in `references/operator-guide.md`. A system-discovered bootstrap interpreter may invoke the repository resolver but is never validation evidence. Provision a wholly absent exact cache lazily on first required validation; reject partial or invalid evidence without falling back to host build tools. A repository-owned cache below the authoritative checkout's `.roundlet/validation-tools/` is generated host state, not a Roundlet runtime or source tree.
- When authoritative root instructions declare repository-owned external-validation routing, use only the generic routes `none`, `toolbox`, and `toolbox+disposable-target`. Bind the selected leaf, referenced instruction/skill paths and exact bytes, concrete repository/commit identities, permitted actions, evidence-time field, rollback, and read-back procedure at selection. Roundlet core never supplies target-specific names or scope.
- Consume external validation only through one exact repository-owned executor contract. Treat its command, schemas, product adapters, projection, recording, retention, and read-back as opaque repository concerns. Never compose a candidate-specific runner, infer product attributes, or rebuild a second plan between validation and execution.
- Derive every accepted readiness/result schema identity from that exact selected executor contract and its typed receipts. Never copy a schema expectation from an earlier candidate, executor, or binding. Keep the executor's opaque sequence identity separate from Roundlet's formal Supervisor epoch/round/attempt; neither sequence may satisfy, reset, overwrite, or advance the other.
- When authoritative root instructions and the selected leaf opt into a repository-owned lifecycle observation sink, bind its exact contract, producer, store, event schema, window, candidate, capture plan, and formal review tuple before the first selected transition. Only the Orchestrator invokes that sink. It emits the closed generic facts defined in `references/operator-guide.md`, requires append/read-back before advancing a qualified transition, and seals/verifies the window before accepting its evidence. A repository with no selected sink has zero sink calls, storage, or lifecycle change.
- Treat `allow_external_validation_read_only` and `allow_external_validation_disposable_target_mutation` as independent repository-authority switches. A matching standing `true` removes repetitive per-attempt approval only inside the exact repository-owned route; it never waives credentials, identity, allowlist, rollback, or semantic read-back gates.
- Historical replay uses the immutable evidence capture time declared by the selected repository contract. Never substitute replay execution wall-clock time for that captured time.
- Treat a GitHub CLI failure before GitHub is reachable as connectivity evidence, not credential rejection. Request the narrowest scoped network approval for the same command, use bounded retry, and never substitute browser authentication or browser automation.
- Use lightweight observations only to prove a fully reconciled baseline unchanged. Any change, omission, overflow, malformed value, due full audit, or action-ready phase requires full live reconciliation in the same tick before mutation.
- Never auto-expire, steal, or replace a lease. Recovery requires explicit owner direction after reconciliation.
- Couple a GitHub closing keyword only to the active leaf intended to close. A negated phrase does not neutralize GitHub's parser.
- Never rebase, force-push, bypass protection, destroy unique work, close an umbrella issue, or claim Supervisor PASS after the review limit.

## Native Windows only

Apply this section only when the role's verified runtime is native Windows. Do not generalize it to WSL, Linux, macOS, or another host.

- For a repository Worker or Supervisor, the verified App-managed project worktree is its canonical CWD. Do not create a manual per-role folder or a second nested linked worktree.
- Use the dedicated normal-sandbox `apply_patch` tool directly for Worker source edits. Never wrap it in PowerShell, a pipeline, a here-string/here-document, a batch file, or an elevated shell.
- If linked-worktree Git metadata resolves outside normal writable roots, request only the narrowest approval needed for that exact Git metadata operation. Do not broaden approval to source edits or unrelated paths.
- During cleanup, distinguish task archival, Git registration, unique work, and physical-path removal. After every role archive, wait for task state for at most 30 seconds, take exactly one registration/path snapshot, and append the result to one run-local task-worktree cleanup ledger. A surviving path may be retained only as a typed tombstone when creator read-back proves the task non-active, Git registration absent, `.git` absent, and the directory exactly empty. Reject every future task whose actual CWD equals an unresolved tombstone. Any registration, content, unique work, ambiguity, or later repopulation remains `CLEANUP_BLOCKED`. Never repeatedly delete, kill Codex or Node, or treat the tombstone as reusable.
- Before cleanup ancestry proof, fetch and read back the exact remote main, merge commit, and issue-branch refs named by the live pull request. Before removing any Orchestrator-created auxiliary worktree or state root, classify it as source-only or evidence-bearing. Preserve every unique evidence-bearing artifact under the repository-declared local retention boundary with exact size/digest read-back, or enter `CLEANUP_BLOCKED`; never discard it with the worktree.

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

1. Validate the complete creator-supplied binding attestation, immutable model/effort and authoritative writable-checkout fields, plus one canonical absolute installed-skill root supplied by the creator. Read the installed contract only from that root; never require or scan the Launcher's role-side skill catalog.
2. Reconcile all local and remote evidence and stop on any stale or active run.
3. Resolve one unique saved local Git project and complete one metadata-only project/worktree capability probe, including detached exact-SHA/common-directory read-back and a terminal cleanup-ledger result, before reserving a run ID.
4. Reserve one unguessable run ID; build, persist, and read back one immutable activation bundle.
5. Create and read back advisory lease/current state for that run.
6. Create exactly one configured long-lived Orchestrator, record its creator-verified binding attestation once, and require exact `ACTIVATION_READY` without issue selection.
7. Create exactly one recurring heartbeat bound only to that Orchestrator, require exact `HEARTBEAT_BOUND`, verify all IDs agree, and send one initial tick.
8. Report the activation and archive the Launcher, leaving the Orchestrator and heartbeat active.

Do not attach the heartbeat to the Launcher. Do not create a second Orchestrator or heartbeat. Do not continue after a partial or ambiguous preflight or read-back.

## Run the outer loop

On activation and each heartbeat:

1. Resolve and verify the one immutable activation bundle. Fingerprint the installed skill separately but never adopt it into the live run.
2. Fully reconcile whenever the bounded observation is not an exact match, the phase is action-ready, or the full-audit bound is due.
3. Honor pause, stop-after-current, owner-input, authority, and active-issue states before scheduling.
4. Scan every open issue, exclude umbrellas and non-runnable/dependency-blocked/owned items, classify any repository-declared external-validation route, and rank ready leaf candidates by the operator contract.
5. Select exactly one leaf. Bind any repository-owned external-validation contract, optional lifecycle observation sink, and standing authority before provisioning. Resolve the authoritative repository's unique saved local project, create one unpublished local `codex/` candidate ref, and asynchronously create one persistent Worker through the project/worktree route using that existing ref. Wait for immutable task metadata, then verify the App-managed worktree, Git common directory, clean starting state, and exact starting SHA before role work.
6. Record selection only after the branch, worktree, Worker identity, and clean starting state read back correctly. Send implementation to that same Worker.
7. Publish the initial Worker handoff on the leaf issue, push the exact candidate, create a draft pull request, and publish/read back that creation event on the leaf issue.
8. After the pull request exists, run bounded fresh-Supervisor/same-Worker review cycles and publish candidate, repair, validation, and review evidence only to its top-level pull-request Conversation.
9. At a valid terminal review state, satisfy live merge gates, mark ready when authorized, merge with the configured method, verify or close the leaf, and perform ordered cleanup.
10. Select no new issue until cleanup proves the authoritative checkout, `main`, and `origin/main` align and all issue resources are removed.

Keep the heartbeat at `active_minutes` while work is active or observations are incomplete. Back off only after consecutive unchanged IDLE or owner-input observations according to configuration. Reset on any change or direct owner instruction. Pause removes polling. Finishing one issue returns to IDLE unless the owner requested stop-after-current.

For a selected external route, keep a generic executor state of `UNPREPARED`, `PREFLIGHT_READY`, `ARMED`, `EXECUTED`, `VERIFIED`, or `STALE`. Publish readiness only after the exact repository executor proves one unconsumed candidate-bound plan is executable with zero external action. Consume it once, then accept only its typed result and semantic read-back. Candidate or component movement makes every prior nonterminal or terminal binding `STALE`; rebuild under the same standing route without changing epoch, round, attempt, or owner authority.

For a selected lifecycle sink, keep a separate generic state of `NOT_SELECTED`, `UNARMED`, `ARMED`, `APPENDING`, `SEALED`, `VERIFIED`, or `STALE`. Arm it before the leaf's declared first ephemeral transition. Append each selected event and semantically read its receipt back before the corresponding Roundlet transition advances. Candidate, review tuple, sink, schema, producer, store, capture-plan, time, window, predecessor, or receipt movement makes the window `STALE`. Preserve it and open a genuinely fresh window before repeating the live sequence; never backfill an event that occurred while unarmed.

The external executor may expose its own repository-defined epoch, round, or attempt values. Record those only inside the external-validation binding. Roundlet's `review_epoch`, `review_round`, `review_mode`, and `supervisor_attempt` remain the sole formal-review tuple used for Supervisor dispatch and merge gates. Stop or archive a review created with the wrong formal tuple without accepting or tracing its verdict; interrupt it first when it is still running. Record it only as unaccepted local diagnostic evidence, then create one fresh Supervisor at the mechanically correct tuple.

## Bound the inner loop

- Rounds 1–3, when reached, are COMPLETE reviews. Any valid PASS ends review early.
- Rounds 4–10 are CONVERGING reviews. They focus on prior findings and the delta but may report a new blocking regression or missing evidence.
- Keep epoch, round, mode, and candidate SHA unchanged while attempts advance through configured profiles. Invalid, failed, cancelled, inaccessible, malformed, or wrong-SHA attempts do not consume a round and never become findings or PASS.
- Before every Supervisor dispatch, independently snapshot its detached exact-candidate worktree, clean tracked/untracked/index state, exact candidate ref, registration, CWD, and canonical common directory. Repeat and require exact equality before accepting its result; unrelated shared refs are excluded and the role's self-reported `read_only` value is not evidence.
- After every Supervisor archive, wait at most 30 seconds for task state, take one cleanup snapshot, and append a terminal result to the run-local task-worktree cleanup ledger before another Supervisor can be created.
- A valid FINDINGS consumes the current round. Keep the epoch, send the finding to the same Worker, publish/read back the result and repair-handoff receipts, then bind the repaired candidate to the next round at attempt 1. Never dispatch a fourth attempt or retain the prior round after candidate movement.
- When a lifecycle sink is selected, arm it before creating the first observed role task; append task/attempt start after creator read-back, append completion/disposition after the role result is read, append accepted or unaccepted result before formal state changes, append candidate movement after exact push/read-back, and append formal-round advancement before incrementing advisory review state. These local evidence receipts do not replace canonical GitHub trace or formal review accounting.
- A missing or ambiguously acknowledged GitHub trace remains a pending transition and is retried idempotently on the canonical surface. It does not become `NEEDS_OWNER_INPUT` unless live evidence also proves an existing owner-input class such as authority, credential, identity, scope, or partial-mutation conflict.
- Classify an attempt as invalid-binding only from a failed creator binding attestation. A missing, short, reordered, differently rendered, or task-ID-free role report cannot consume a Supervisor attempt, advance a profile, publish a discard reason, or invalidate a matching creator attestation.
- After the configured attempt budget is exhausted, enter `NEEDS_OWNER_INPUT`.
- If round 10 returns findings, send them once to the same Worker for final repair. Do not run round 11 or claim PASS. Record `REVIEW_LIMIT_REACHED_WORKER_FINALIZED`, then apply normal merge gates.
- Preserve epoch, accepted-round count, and review mode across pause, resume, same-task continuation, and authorized recovery when the immutable contract, leaf scope, acceptance criteria, and candidate review basis are unchanged. Satisfying an already-declared standing validation route is not a scope change.
- An allowlisted owner change to scope or acceptance criteria starts a new review epoch at round 1 COMPLETE. The existing main-integration rule also starts a new COMPLETE epoch because it changes the review basis.

## Stop safely

- `pause` takes effect at a safe checkpoint, pauses the heartbeat, and retains current resources for manual resume.
- `stop-after-current` finishes the active issue and cleanup, removes the heartbeat, releases advisory state and contract bundles after final reconciliation, and archives the Orchestrator. If IDLE, stop immediately.
- Normal stop and issue cleanup retain a repository-declared shared validation cache. Remove or rebuild it only as a separate exact owner-directed cache action after validating the target path and preserving evidence of corruption or drift.
- Normal stop and issue cleanup also retain every sealed lifecycle ledger and path-free retention receipt under the repository-declared evidence boundary. Unsealed or conflicting windows remain explicit retained diagnostics; never discard or synthesize them during worktree/task cleanup.
- A closed, ignored, or withdrawn active issue requires an explicit owner abort decision.
- Any unresolved ambiguity affecting scope, dependency order, data safety, unique work, or irreversible mutation enters `NEEDS_OWNER_INPUT` and stops scheduling.
