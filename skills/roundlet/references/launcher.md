# Launcher prompts

The Launcher is short-lived. It preflights one target, creates exactly one long-lived Orchestrator, binds exactly one heartbeat to that Orchestrator, sends one initial tick, reports the activation, and archives itself. It never selects or implements an issue.

Replace every `<PLACEHOLDER>` before use. Do not change any other value or add an implementation request.

## New activation

Create the Launcher directly against the exact authoritative checkout as its writable local project and use the requested Launcher model/effort. Its first prompt is only:

```text
TASK_BINDING_REQUEST role=LAUNCHER expected_model=<MODEL> expected_effort=<EFFORT> expected_workspace=<ABSOLUTE_PATH> expected_cwd=<ABSOLUTE_PATH>
Discover immutable task metadata, return the resulting TASK_BINDING, and perform no activation, repository, GitHub, Git, heartbeat, or filesystem action.
```

Independently read the creator-side immutable task record and require the same task ID, model, effort, writable project/workspace, and canonical CWD. Archive the task and stop on mismatch. Only after that read-back, replace the placeholders below, including `<LAUNCHER_TASK_ID>`, and send this entire populated activation prompt to the same task:

```text
Use $roundlet as a short-lived Launcher for exactly one completely fresh Roundlet run.

Target:
- GitHub repository: <OWNER/REPOSITORY>
- Authoritative local checkout: <ABSOLUTE_PATH>
- Expected primary branch: main
- Roundlet configuration: use references/roundlet-config.json within the installed $roundlet skill without changing, defaulting, or overriding any value
- Expected Launcher task ID: <LAUNCHER_TASK_ID>
- Expected Launcher model/effort: <MODEL> / <EFFORT>
- Authenticated and allowlisted owner: <OWNER_LOGIN>

Do not recover, resume, reuse, migrate, adopt, or replace any former run or Orchestrator. Read the complete installed Roundlet SKILL.md and every required reference before acting. Do not select or implement an issue in this Launcher.

Before creating any run resource, fail closed unless every item below is freshly proven:

1. Immutable Launcher identity
   - Discover and invoke the immutable task-metadata route.
   - Require the actual Launcher task ID to equal the creator-verified expected task ID.
   - Require the actual Launcher task model and reasoning effort to equal the expected values.
   - Require its canonical CWD and writable local-project workspace to equal the authoritative checkout.
   - Self-report, a projectless task, an unrelated project, a read-only route, or a removable linked worktree is insufficient.

2. Repository and Git identity
   - Fetch and resolve the exact GitHub repository, origin URL, default branch, local main, origin/main, and HEAD.
   - Require a clean authoritative checkout and `HEAD == main == origin/main`.
   - Require origin and GitHub identity to equal the target exactly.
   - Read root AGENTS.md from authoritative origin/main. Require exactly one valid Roundlet authority block with `roundlet.enabled: true`; record every other false switch as a later mutation boundary.
   - Require `.roundlet/` excluded only through this checkout's local `.git/info/exclude`; never commit the exclusion or any runtime state.

3. Freshness and cleanup
   - Reconcile `.roundlet/`, every retained contract/state file, prior run and activation evidence, Roundlet GitHub trace, active Roundlet pull requests, issue branches, linked worktrees, relevant Codex tasks, Workers, Supervisors, leases, and heartbeats.
   - Require all former runs fully stopped and all former run-owned resources absent.
   - Treat host-owned empty task anchors separately from Roundlet worktrees. They do not block activation when no task is active, no exact worktree registration/path/holder or unique work remains, and the anchor is not reused as a run resource.
   - If any live, stale, conflicting, or unreconciled Roundlet ownership remains, stop with `STALE_OR_ACTIVE_RUN_REQUIRES_OWNER`. Never expire, steal, replace, overwrite, or reuse it.

4. Installed contract and configuration
   - Resolve the exact installed skill root and required file set.
   - Require every required reference present and internally consistent.
   - Parse the exact configuration without defaults or overrides.
   - Require unique Supervisor profile names; ordered profile count equal to `max_supervisor_attempts_per_round`; positive review limits; valid merge method; heartbeat arrays beginning at `active_minutes`, strictly increasing, and positive; positive full-reconciliation bound; and the authenticated owner in `owner_allowlist`.
   - Build the exact content-addressed activation bundle defined in the operator guide. Do not include mutable or generated files.

5. Host and service capabilities
   - Verify exact configured task models/efforts, task create/address/wait/archive/inspect controls, recurring-heartbeat create/inspect/update/pause/resume/remove controls, Git, filesystem/worktree routes, GitHub issue/PR access, authenticated identity, branch/rule/check inspection, and merge-commit capability.
   - When `gh` is required, run a representative read-only request. If it fails before GitHub is reachable, request the narrowest scoped network approval for the same command and retry boundedly. Never substitute browser authentication or browser automation. Reachable GitHub authentication rejection, explicit approval denial, unavailable approval, or exhausted connectivity recovery fails closed.
   - Absence of branch protection is not itself an activation blocker. Existing rules and required checks remain mandatory.

6. Backlog reconciliation
   - Scan the complete newly prepared live backlog, formal parent/sub-issue and blocking relationships, and every umbrella Canonical scheduling note.
   - Treat umbrellas as scheduling context only, never as implementation candidates or dependencies.
   - Treat runnable dependencies only as exact leaf or standalone issue numbers recorded in live scheduling context.
   - Do not select, claim, or implement an issue in this Launcher.

If and only if every preflight item passes:

1. Reserve a new unguessable run ID that differs from every former run ID.
2. Build `.roundlet/contracts/<contract-id>/` from the current installed skill and exact resolved configuration:
   - when source kind is `git`, materialize every file directly from the verified commit object; never copy or hash working-tree bytes, even when the checkout is clean;
   - include exact bytes for SKILL.md, every required reference, and agents/openai.yaml;
   - use unique POSIX relative paths sorted by unsigned UTF-8 bytes;
   - record SHA-256 of exact bytes;
   - compute `tree_digest` from ASCII `roundlet-tree/v1\n` followed for each file by UTF-8 path, NUL, 64 lowercase hash hex bytes, and LF;
   - build `roundlet-contract/v1` with exact source identity, resolved configuration, ordered files, and tree digest;
   - serialize with RFC 8785 JCS, no BOM, trailing newline, or floats;
   - derive lowercase-hex contract ID from the canonical manifest with `contract_id` omitted, add only that ID, reserialize, persist the exact files and manifest, and read back every byte, path, hash, role profile, source identity, tree digest, and contract ID.
   - Stop with `CONTRACT_BUNDLE_CONFLICT` if an existing path differs.
3. Create fresh `.roundlet/lease.json` and `.roundlet/current.md` for this run and read them back. Bind the exact target, checkout, owner, run ID, contract ID/bundle, activation time, state `ACTIVATING`, and empty Orchestrator/heartbeat fields. Do not add an expiry.
4. Create exactly one long-lived Orchestrator using the configured Orchestrator model and effort from the pinned bundle. Give it only the binding request from `thread-prompts.md` as its first prompt. Before its populated bootstrap:
   - independently read back its immutable task ID, model, effort, project/workspace, and canonical CWD;
   - require task/profile equality with configuration and project/CWD equality with the authoritative checkout;
   - write the verified Orchestrator task ID to both advisory files and read back the same run/contract/task binding.
5. Send the Orchestrator the exact bootstrap contract from the pinned bundle, including target, checkout, run ID, owner allowlist, resolved authority, configuration, contract ID/path, advisory paths, verified task/profile/workspace identity, live backlog summary, and instruction not to select an issue. Require it to reread the bundle and live identities, repeat any representative `gh` access needed in its own task, update state to `IDLE`, and return exactly:
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

Create the recovery Launcher against the authoritative checkout using the old bundle's configured Orchestrator profile. Its first prompt is only the `TASK_BINDING_REQUEST` from `thread-prompts.md` with role `LAUNCHER`, the old bundle's exact model/effort, and the authoritative workspace/CWD. Independently read back the same immutable task/profile/workspace/CWD, archive and stop on mismatch, then replace `<RECOVERY_LAUNCHER_TASK_ID>`, `<MODEL>`, and `<EFFORT>` below and send the populated recovery prompt to that same task:

```text
Act as a short-lived Roundlet recovery Launcher for exactly one previously activated target. Do not invoke or load the installed `$roundlet` skill.

Target:
- GitHub repository: <OWNER/REPOSITORY>
- Authoritative local checkout: <ABSOLUTE_PATH>
- Existing run ID, if known: <RUN_ID_OR_UNKNOWN>
- Expected recovery Launcher task ID: <RECOVERY_LAUNCHER_TASK_ID>
- Expected recovery Launcher model/effort: <MODEL> / <EFFORT>
- Owner-authorized Orchestrator/heartbeat replacement: <true|false>
- Owner recovery instruction: <EXACT_OWNER_INSTRUCTION>

Read only the advisory activation pointers first, resolve the one immutable activation bundle, verify it completely, then read its SKILL.md and every required reference. Treat the installed skill only as an unrelated candidate that cannot enter this run.

1. Verify this recovery Launcher's immutable task ID/profile/workspace/CWD against the creator-supplied values and perform the bundle's repository, authority, GitHub, host, and capability preflight.
2. Reconcile lease/current state, activation bundle, GitHub traces and pull requests, branches, worktrees, checks, exact candidate SHA, all identifiable role tasks, and all heartbeats.
3. If the old Orchestrator or heartbeat is live, ownership is ambiguous, the bundle is incomplete, or unique work cannot be attributed, stop with `RECOVERY_OWNER_DECISION_REQUIRED`. Do not replace or delete anything.
4. If both old Orchestrator and heartbeat are conclusively unavailable, reconstruct the phase from durable GitHub and Git evidence. Preserve the run ID only when identity is certain; otherwise stop for owner input.
5. Never silently replace an active or inaccessible Worker. Return `WORKER_REPLACEMENT_REQUIRES_OWNER`.
6. Only when `Owner-authorized Orchestrator/heartbeat replacement` is exactly `true` and the owner instruction expressly authorizes it, create exactly one replacement Orchestrator from the old pinned bundle. Give it only the task-binding request first, verify its immutable task/profile/workspace/CWD once, and require without advancing work:
   `RECOVERY_READY run=<run-id> contract=<contract-id> orchestrator=<replacement-task-id> state=<reconstructed-phase> transition=none`
7. After that acknowledgement, remove only a conclusively stale heartbeat, create one replacement heartbeat at `active_minutes`, bind it only to the replacement Orchestrator, update and read back advisory state, and send one recovery tick.
8. Report every retained, replaced, removed, or unresolved resource and archive this recovery Launcher.

Fail closed at every ambiguity. Never infer consent for abort, cleanup, merge, issue closure, task replacement, or changing the active contract.
```
