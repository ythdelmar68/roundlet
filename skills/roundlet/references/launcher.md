# Launcher prompts

The Launcher is short-lived. It preflights one target, creates exactly one long-lived Orchestrator, binds exactly one heartbeat to that Orchestrator, sends one initial tick, reports the activation, and archives itself. It never selects or implements an issue.

Replace every `<PLACEHOLDER>` before use. Do not change any other value or add an implementation request.

## New activation

Create the Launcher directly against the exact authoritative checkout as its writable local project and use the requested Launcher model/effort. Its first prompt is only:

```text
ROUNDLET_ROLE_METADATA_REPORT_REQUEST
requested_role: LAUNCHER
requested_profile: model=<MODEL>;reasoning_effort=<EFFORT>
requested_route: LOCAL_PROJECT
requested_saved_project: <PROJECT_ID_AND_ABSOLUTE_PATH>
requested_starting_ref: not-applicable
requested_starting_sha: not-applicable
requested_workspace: <ABSOLUTE_PATH>
requested_cwd: <ABSOLUTE_PATH>
Return any role-visible metadata as a non-authoritative ROUNDLET_ROLE_METADATA_REPORT. Perform no activation, repository, GitHub, Git, heartbeat, or filesystem action.
END_ROUNDLET_ROLE_METADATA_REPORT_REQUEST
```

Treat any response as a non-authoritative role report. Independently read the creator-side immutable task record and build the exact `CREATOR_TASK_BINDING_ATTESTATION` from `thread-prompts.md`, including this creator task, requested Launcher role, task ID, model, effort, route `LOCAL_PROJECT`, requested saved project, writable project/workspace, canonical CWD, Git common directory, and available stable host/environment identity. A missing, short, noncanonical, or task-ID-free report does not block matching creator read-back. On an explicit contradiction, perform one bounded creator-side re-read; archive and stop only when authoritative evidence is missing, stale, malformed, mismatched, or still conflicting. Independently resolve the installed Roundlet skill used to read this prompt to one canonical absolute root and verify its required file set. Only after both checks succeed, replace the placeholders below, including `<LAUNCHER_TASK_ID>` and `<INSTALLED_SKILL_ROOT>`, copy the complete attestation into the fixed block, and send this entire populated activation prompt to the same task:

```text
Act as a short-lived Launcher for exactly one completely fresh Roundlet run, using only the creator-supplied installed Roundlet skill root below.

Target:
- GitHub repository: <OWNER/REPOSITORY>
- Authoritative local checkout: <ABSOLUTE_PATH>
- Installed Roundlet skill root: <INSTALLED_SKILL_ROOT>
- Expected primary branch: main
- Roundlet configuration: use `references/roundlet-config.json` beneath the installed skill root above without changing, defaulting, or overriding any value
- Expected Launcher task ID: <LAUNCHER_TASK_ID>
- Expected Launcher creator/source task ID: <CREATOR_TASK_ID>
- Expected Launcher model/effort: <MODEL> / <EFFORT>
- Expected stable host/environment identity: <STABLE_HOST_IDENTITY_OR_UNAVAILABLE> / <STABLE_ENVIRONMENT_IDENTITY_OR_UNAVAILABLE>
- Authenticated and allowlisted owner: <OWNER_LOGIN>

Creator binding authority:
CREATOR_TASK_BINDING_ATTESTATION
role_task: <LAUNCHER_TASK_ID>
creator_task: <CREATOR_TASK_ID>
requested_role: LAUNCHER
execution_profile: model=<MODEL>;reasoning_effort=<EFFORT>
task_route: LOCAL_PROJECT
requested_saved_project: <PROJECT_ID_AND_ABSOLUTE_PATH>
task_workspace: <ABSOLUTE_PATH>
task_cwd: <ABSOLUTE_PATH>
git_common_dir: <ABSOLUTE_GIT_COMMON_DIR>
starting_ref: not-applicable
starting_sha: not-applicable
stable_host_identity: <STABLE_HOST_IDENTITY_OR_UNAVAILABLE>
stable_environment_identity: <STABLE_ENVIRONMENT_IDENTITY_OR_UNAVAILABLE>
binding_source: creator-immutable-readback
END_CREATOR_TASK_BINDING_ATTESTATION

Do not recover, resume, reuse, migrate, adopt, or replace any former run or Orchestrator. Read `SKILL.md` and every required reference only from the exact installed skill root above before acting. Do not invoke or require a role-side skill catalog. Do not select or implement an issue in this Launcher.

Before creating any run resource, fail closed unless every item below is freshly proven:

1. Immutable Launcher identity
   - Read exactly one complete `CREATOR_TASK_BINDING_ATTESTATION` from this populated prompt. Do not discover or require a role-side immutable self-metadata route; the creator already performed that read-back before sending this prompt.
   - Require its task ID, creator/source task, requested role, model/effort, route, requested saved project, project/workspace, canonical CWD, Git common directory, starting-ref/SHA non-applicability, stable host/environment identity, and `binding_source: creator-immutable-readback` to equal every corresponding expected value above.
   - Require the attested canonical CWD and writable local-project workspace to equal the authoritative checkout.
   - Missing, duplicate, malformed, stale, or mismatched attestation fields fail closed before any repository, GitHub, Git, lease, contract, Orchestrator, or heartbeat action.
   - The creator binding attestation is the authority. A role metadata report is never sufficient and cannot invalidate matching creator evidence; a projectless task, unrelated project, read-only route, or removable linked worktree in Launcher creator read-back fails closed. The Launcher itself uses `LOCAL_PROJECT`; later repository Workers and Supervisors use the separately preflighted `PROJECT_WORKTREE` route.
   - Before any repository, GitHub, or Git access, canonicalize the literal installed-skill-root value above and require it to be absolute and unchanged. Require exactly the seven bundle inputs `SKILL.md`, `agents/openai.yaml`, `references/launcher.md`, `references/operator-guide.md`, `references/repository-authority.md`, `references/roundlet-config.json`, and `references/thread-prompts.md` present strictly beneath that root, with no path escape or ambiguous resolution. Record the exact path set and per-file byte identity for later comparison. A missing, relative, noncanonical, incomplete, escaped, or ambiguous root fails closed here. Do not consult the role-side skill catalog or scan another path.

2. Repository and Git identity
   - Fetch and resolve the exact GitHub repository, origin URL, default branch, local main, origin/main, and HEAD.
   - Require a clean authoritative checkout and `HEAD == main == origin/main`.
   - Require origin and GitHub identity to equal the target exactly.
   - Read root AGENTS.md from authoritative origin/main. Require exactly one valid Roundlet authority block with `roundlet.enabled: true`; record every other false switch as a later mutation boundary.
   - Resolve every external-validation operations contract or repository-owned skill referenced by root instructions to an exact path and Git blob on authoritative origin/main. Record only bounded identities; do not select a route, invoke a toolbox, inspect credentials, or contact a disposable target during activation.
   - Resolve every optional lifecycle-observation contract referenced by root instructions to an exact path and Git blob on authoritative origin/main. Record only bounded identities; do not select a leaf sink, create a window/store, or invoke prepare/append/seal/verify during activation.
   - Require `.roundlet/` excluded only through this checkout's local `.git/info/exclude`; never commit the exclusion or any runtime state.

3. Freshness and cleanup
   - Reconcile `.roundlet/`, every retained contract/state file, prior run and activation evidence, Roundlet GitHub trace, active Roundlet pull requests, issue branches, linked worktrees, relevant Codex tasks, Workers, Supervisors, leases, and heartbeats.
   - When root instructions declare `.roundlet/validation-tools/` as a repository validation cache, classify it separately as host-owned reusable state. A valid cache does not prove stale run ownership and ordinary activation cleanup must not remove or rewrite it.
   - Classify repository-declared retained issue evidence separately from leases, advisory state, contracts, branches, and worktrees. A complete digest-readable retention area from a stopped run does not prove stale ownership and must not be removed or adopted by activation.
   - Require all former runs fully stopped and all former run-owned resources absent.
   - Treat a retained typed empty task-worktree tombstone separately from a live Roundlet worktree. It does not block activation only when its ledger and fresh read-back prove the task archived/non-active, Git registration absent, `.git` absent, directory exactly empty, path under the App-managed worktree root, and no reuse. Any content, registration, ambiguity, or missing ledger evidence remains stale ownership.
   - If any live, stale, conflicting, or unreconciled Roundlet ownership remains, stop with `STALE_OR_ACTIVE_RUN_REQUIRES_OWNER`. Never expire, steal, replace, overwrite, or reuse it.

4. Installed contract and configuration
   - Accept only the one creator-supplied installed skill root above. Require it to be canonical, absolute, existing, and unchanged; never discover, scan for, or substitute a role-side skill-catalog entry or another filesystem root.
   - Resolve every required file strictly beneath that root, reject path escape, ambiguity, missing files, or extra generated inputs, and require the same canonical root, exact seven-path set, and per-file byte-identity map before and after bundle construction.
   - Classify the source as `git` only after verifying the containing repository root, canonical `owner/repository` origin, exact lowercase 40-character commit OID, and the skill root's exact tree prefix at that commit. Require every bundled relative path to map uniquely to an existing blob below that prefix. Otherwise use `installed-tree` and make no Git provenance claim.
   - Require every required reference present and internally consistent.
   - Parse the exact configuration without defaults or overrides.
   - Require unique Supervisor profile names; ordered profile count equal to `max_supervisor_attempts_per_round`; positive review limits; valid merge method; heartbeat arrays beginning at `active_minutes`, strictly increasing, and positive; positive full-reconciliation bound; and the authenticated owner in `owner_allowlist`.
   - Derive and verify the exact content-addressed bundle inputs from that same bound root without persisting a bundle during preflight. Do not include mutable or generated files.

5. Host and service capabilities
   - Verify exact configured task models/efforts, asynchronous task create/address/wait/archive/inspect controls, recurring-heartbeat create/inspect/update/pause/resume/remove controls, Git, filesystem/worktree routes, GitHub issue/PR access, authenticated identity, branch/rule/check inspection, and merge-commit capability.
   - List saved local projects and resolve the target authoritative checkout by canonical path. Require exactly one writable Git project whose canonical repository path and Git common directory match the target. Record its creator-request identity for later role creation. A missing, duplicate, display-name-only, unrelated, or non-Git project fails preflight. Do not use projectless creation as a repository fallback.
   - Before creating a run ID, perform exactly one metadata-only route capability probe. Create one unguessable unpublished local `codex/roundlet-route-probe-*` ref at exact `origin/main`, then asynchronously create one project/worktree task from that existing ref using the first configured Supervisor profile. Send only the role metadata request with requested role `SUPERVISOR`; perform no implementation, source edit, commit, push, GitHub action, external validation, or lifecycle capture.
   - Wait for immutable creator metadata and require a distinct App-managed CWD outside the authoritative checkout and outside every unresolved tombstone path, matching canonical Git common directory, detached `HEAD == origin/main`, exact requested starting ref/SHA, clean porcelain-v2 status, and stable registration. Archive the probe, wait for task state for at most 30 seconds, take exactly one registration/path snapshot, and append a terminal `ROUNDLET_TASK_WORKTREE_CLEANUP_RESULT` to the retained local route-probe ledger. Delete the unpublished probe ref only by exact old-SHA comparison. `REMOVED` or a conforming typed empty tombstone proves cleanup; any active task, registration, `.git`, content, ref conflict, path reuse, drift, or ambiguous read-back fails activation without a run, Worker, GitHub trace, or owner-input request.
   - If root repository instructions explicitly declare a validation-toolchain contract, read its exact named document/lock/resolver/cache boundary. System-discover an available bootstrap interpreter satisfying the declared version and prove the resolver can be invoked, while treating that interpreter as bootstrap-only. Verify that later Worker turns can pass the authoritative checkout's exact shared cache root. Do not provision merely for activation and do not accept host build tools as evidence.
   - If root instructions declare external-validation routing, prove that the generic `none`, `toolbox`, and `toolbox+disposable-target` vocabulary, referenced path/blob identities, executor-declared schema/retention routes, and exact `allow_external_validation_read_only` / `allow_external_validation_disposable_target_mutation` Boolean switches can be read deterministically. Do not require live login or execute a gate before a leaf is selected.
   - If root instructions declare an optional lifecycle observation sink, prove that its referenced contract path/blob and declared prepare, append/read-back, seal/verify, closed-event, and retention capability identities can be read deterministically. Do not arm a window or require the external implementation before a leaf explicitly selects ephemeral capture.
   - When `gh` is required, run a representative read-only request. If it fails before GitHub is reachable, request the narrowest scoped network approval for the same command and retry boundedly. Never substitute browser authentication or browser automation. Reachable GitHub authentication rejection, explicit approval denial, unavailable approval, or exhausted connectivity recovery fails closed.
   - Absence of branch protection is not itself an activation blocker. Existing rules and required checks remain mandatory.

6. Backlog reconciliation
   - Scan the complete newly prepared live backlog, formal parent/sub-issue and blocking relationships, and every umbrella Canonical scheduling note.
   - When root instructions declare external-validation routing, classify every actionable issue's declaration and reject an unknown, missing, floating, or conflicting route. Do not infer mutation authority from the route itself. Otherwise bind `none` without loading an external contract.
   - When a leaf declares ephemeral lifecycle capture, require one exact root-referenced sink contract and an explicit arm-before boundary. Otherwise classify the sink as `NOT_SELECTED`. A missing or conflicting required sink makes the leaf non-runnable; it does not create storage or owner input during Launcher preflight.
   - Treat umbrellas as scheduling context only, never as implementation candidates or dependencies.
   - Treat runnable dependencies only as exact leaf or standalone issue numbers recorded in live scheduling context.
   - Do not select, claim, or implement an issue in this Launcher.

If and only if every preflight item passes:

1. Reserve a new unguessable run ID that differs from every former run ID.
2. Prepare and atomically finalize `.roundlet/contracts/<contract-id>/` from the current installed skill and exact resolved configuration:
   - immediately re-read the creator-supplied canonical root and every derived file identity; require an exact match with preflight before materializing any contract path;
   - when source kind is `git`, select every file directly from the verified commit object; never copy or hash working-tree bytes, even when the checkout is clean;
   - include exact bytes for SKILL.md, every required reference, and agents/openai.yaml;
   - use unique POSIX relative paths sorted by unsigned UTF-8 bytes;
   - record SHA-256 of exact bytes;
   - compute `tree_digest` from ASCII `roundlet-tree/v1\n` followed for each file by UTF-8 path, NUL, 64 lowercase hash hex bytes, and LF;
   - build `roundlet-contract/v1` with exact source identity, resolved configuration, ordered files, and tree digest;
   - serialize with RFC 8785 JCS, no BOM, trailing newline, or floats;
   - derive lowercase-hex contract ID from the canonical manifest with `contract_id` omitted, add only that ID, and reserialize without persisting the final contract path;
   - materialize the exact selected files and manifest into one new unfinalized staging path below `.roundlet/contracts/`;
   - before finalizing any contract path or advisory state, re-read the bound installed root and require its canonical identity, exact seven-path set, and every per-file byte identity to equal preflight; also require each materialized bundle file to equal that preflight identity. Any same-path content drift or mixed-generation bundle fails closed without finalizing the bundle.
   - if the final contract path is absent, atomically finalize the verified staging path there; if it exists, reuse it only after exact equality and remove the redundant staging path, otherwise stop with `CONTRACT_BUNDLE_CONFLICT`;
   - read back every finalized byte, path, hash, role profile, source identity, tree digest, and contract ID; on any failure remove only the new unfinalized staging path after exact path validation and leave no lease/current state.
3. Create fresh `.roundlet/lease.json` and `.roundlet/current.md` for this run and read them back. Bind the exact target, checkout, owner, resolved saved-project request identity, Git common directory, repository role route `PROJECT_WORKTREE`, verified route-probe receipt/cleanup-ledger identity, run ID, contract ID/bundle, activation time, state `ACTIVATING`, and empty Orchestrator/heartbeat fields. Do not add an expiry.
4. Create exactly one long-lived Orchestrator using the configured Orchestrator model and effort from the pinned bundle. Give it only the role metadata report request from `thread-prompts.md` as its first prompt. Before its populated bootstrap:
   - treat its returned report as advisory and independently build the creator binding attestation from immutable task ID, creator task, requested role, model, effort, project/workspace, canonical CWD, and available stable host/environment identity;
   - on an explicit report contradiction, perform one bounded immutable re-read; never reject a matching creator attestation because the report is missing, short, noncanonical, or omits its own task ID;
   - require task/profile equality with configuration, route `LOCAL_PROJECT`, requested saved-project identity, project/CWD equality with the authoritative checkout, and matching Git common directory;
   - write the verified Orchestrator task ID and complete creator binding attestation fields to advisory state, then read back the same run/contract/task/attestation binding.
5. Send the Orchestrator the exact bootstrap contract from the pinned bundle, including target, checkout, resolved saved-project request identity and Git common directory for repository roles, run ID, owner allowlist, resolved authority, configuration, contract ID/path, advisory paths, complete creator binding attestation, live backlog summary, repository-defined validation-toolchain summary/cache root or `not-applicable`, bounded external-validation contract path/blob summaries or `not-applicable`, bounded lifecycle-observation contract path/blob summaries or `not-applicable`, and instruction not to select an issue. Require it to reread the bundle and live identities, repeat any representative `gh` access needed in its own task, update state to `IDLE`, and return exactly:
   `ACTIVATION_READY run=<run-id> contract=<contract-id> orchestrator=<task-id> target=<owner/repository> state=IDLE`
6. Independently inspect that exact populated turn and advisory state. Require the acknowledgement and lease/current files to bind the same run, contract, Orchestrator, target, and state. On any mismatch, create no heartbeat and stop with exact evidence.
7. Create exactly one recurring heartbeat at configured `heartbeat.active_minutes`, bound only to the new Orchestrator. Its instruction is: invoke one idempotent Roundlet tick from the pinned bundle, prove the bounded observation unchanged or fully reconcile in the same tick, make at most one externally meaningful transition, maintain the configured phase-aware interval on this same heartbeat, and report the resulting state.
8. Write the heartbeat ID and interval into both advisory files and read back the exact run/contract/Orchestrator/heartbeat binding. Then send that heartbeat identity and interval to the Orchestrator. Require exactly:
   `HEARTBEAT_BOUND run=<run-id> contract=<contract-id> orchestrator=<task-id> heartbeat=<heartbeat-id> interval=<minutes>m`
9. Independently verify the heartbeat target and schedule plus both advisory files. Require one identical run ID, contract ID, Orchestrator task ID, heartbeat ID, and state.
10. Send exactly one initial Roundlet tick to the Orchestrator.
11. Report the run ID, contract ID, Orchestrator task ID, heartbeat ID, configured role profiles, and initial state. Archive this Launcher. Leave the Orchestrator and its one heartbeat active.

Never attach the heartbeat to this Launcher. Never create a second Orchestrator or heartbeat. Never reuse a former run ID. Never begin implementation here. Fail closed on stale ownership, identity conflict, incomplete cleanup, missing capability, task-profile mismatch, partial bundle, or read-back mismatch.
```

## Explicit recovery

Use recovery only after an allowlisted owner explicitly directs it. Recovery uses the existing run's immutable bundle; an installed update is never adopted. If the owner wants a newer skill, stop and clean the old run and use New activation.

Create the recovery Launcher against the authoritative checkout using the old bundle's configured Orchestrator profile. Its first prompt is only the `ROUNDLET_ROLE_METADATA_REPORT_REQUEST` from `thread-prompts.md` with requested role `LAUNCHER`, the old bundle's exact model/effort, route `LOCAL_PROJECT`, the uniquely resolved saved-project identity, and the authoritative workspace/CWD. Treat the response as advisory, independently build the creator binding attestation, use one bounded creator re-read for an explicit contradiction, and archive/stop only on failed authoritative evidence. Then replace every recovery placeholder below, including the recovery Launcher/creator task IDs and stable host/environment identities, copy the complete attestation into the fixed block, and send the populated recovery prompt to that same task:

```text
Act as a short-lived Roundlet recovery Launcher for exactly one previously activated target. Do not invoke or load the installed `$roundlet` skill.

Target:
- GitHub repository: <OWNER/REPOSITORY>
- Authoritative local checkout: <ABSOLUTE_PATH>
- Existing run ID, if known: <RUN_ID_OR_UNKNOWN>
- Expected recovery Launcher task ID: <RECOVERY_LAUNCHER_TASK_ID>
- Expected recovery Launcher creator/source task ID: <RECOVERY_CREATOR_TASK_ID>
- Expected recovery Launcher model/effort: <MODEL> / <EFFORT>
- Expected recovery stable host/environment identity: <STABLE_HOST_IDENTITY_OR_UNAVAILABLE> / <STABLE_ENVIRONMENT_IDENTITY_OR_UNAVAILABLE>
- Owner-authorized Orchestrator/heartbeat replacement: <true|false>
- Owner recovery instruction: <EXACT_OWNER_INSTRUCTION>

Creator binding authority:
CREATOR_TASK_BINDING_ATTESTATION
role_task: <RECOVERY_LAUNCHER_TASK_ID>
creator_task: <RECOVERY_CREATOR_TASK_ID>
requested_role: LAUNCHER
execution_profile: model=<MODEL>;reasoning_effort=<EFFORT>
task_route: LOCAL_PROJECT
requested_saved_project: <PROJECT_ID_AND_ABSOLUTE_PATH>
task_workspace: <ABSOLUTE_PATH>
task_cwd: <ABSOLUTE_PATH>
git_common_dir: <ABSOLUTE_GIT_COMMON_DIR>
starting_ref: not-applicable
starting_sha: not-applicable
stable_host_identity: <STABLE_HOST_IDENTITY_OR_UNAVAILABLE>
stable_environment_identity: <STABLE_ENVIRONMENT_IDENTITY_OR_UNAVAILABLE>
binding_source: creator-immutable-readback
END_CREATOR_TASK_BINDING_ATTESTATION

Before reading any advisory activation pointer or contract bundle, read exactly one complete creator binding attestation from this prompt and verify it against the creator-supplied task/creator IDs, requested role, profile, workspace/CWD, stable host/environment identity, and binding source. Do not discover or require a role-side immutable self-metadata route. Missing, duplicate, malformed, stale, or mismatched fields fail closed before any recovery work.

Only after that validation succeeds, read the advisory activation pointers, resolve the one immutable activation bundle, verify it completely, then read its SKILL.md and every required reference. Treat the installed skill only as an unrelated candidate that cannot enter this run.

1. Perform the bundle's repository, authority, GitHub, host, and capability preflight.
2. Reconcile lease/current state, activation bundle, saved-project request and Git common-directory identity, GitHub traces and pull requests, branches, App-managed worktrees, typed empty task-worktree tombstones, checks, exact candidate SHA, all identifiable role tasks and recorded creator binding attestations, every selected external-validation path/blob/repository/commit/action/schema/opaque-sequence/evidence-time/read-back identity, every selected lifecycle-sink contract/plan/window/sequence/head/seal/retention identity, the independent formal Supervisor tuple, and all heartbeats. Reuse each stable attestation normally. Treat any repository-declared validation cache, retained lifecycle ledger, complete retained issue-evidence area, and still-valid tombstone ledger as retained host-owned state, not run ownership; verify applicable receipt/digest evidence but do not remove, rebuild, adopt, or backfill it during recovery. If contradictory immutable creator-side, route/worktree, external-validation, lifecycle-sink, or formal-review evidence appears, perform exactly one bounded re-read against the recorded identity; unresolved conflict fails closed without a second task, attestation, dispatch, trace, substituted route, copied sequence, synthesized event, or reset review epoch.
3. If the old Orchestrator or heartbeat is live, ownership is ambiguous, the bundle is incomplete, or unique work cannot be attributed, stop with `RECOVERY_OWNER_DECISION_REQUIRED`. Do not replace or delete anything.
4. If both old Orchestrator and heartbeat are conclusively unavailable, reconstruct the phase from durable GitHub and Git evidence. Preserve the run ID only when identity is certain; otherwise stop for owner input.
5. Never silently replace an active or inaccessible Worker. Return `WORKER_REPLACEMENT_REQUIRES_OWNER`.
6. Only when `Owner-authorized Orchestrator/heartbeat replacement` is exactly `true` and the owner instruction expressly authorizes it, create exactly one replacement Orchestrator from the old pinned bundle. Give it only the role metadata report request first, record one creator binding attestation after immutable read-back, and require without advancing work:
   `RECOVERY_READY run=<run-id> contract=<contract-id> orchestrator=<replacement-task-id> state=<reconstructed-phase> transition=none`
7. After that acknowledgement, remove only a conclusively stale heartbeat, create one replacement heartbeat at `active_minutes`, bind it only to the replacement Orchestrator, update and read back advisory state, and send one recovery tick.
8. Report every retained, replaced, removed, or unresolved resource and archive this recovery Launcher.

Fail closed at every ambiguity. Never infer consent for abort, cleanup, merge, issue closure, task replacement, or changing the active contract.
```
