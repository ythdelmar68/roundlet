# Launcher prompts

The Launcher is a short-lived Codex task. It preflights one target repository, creates the configured long-lived Orchestrator task, attaches exactly one heartbeat to that task, transfers the heartbeat identity, and then archives itself.

Replace every `<PLACEHOLDER>` before use. Do not add an implementation request to the Launcher prompt.

## New activation

Copy and paste this entire prompt into a new Codex task:

```text
Use $roundlet as a short-lived Launcher for exactly one target repository.

Target:
- GitHub repository: <OWNER/REPOSITORY>
- Authoritative local checkout: <ABSOLUTE_PATH>
- Expected primary branch: main
- Roundlet configuration: use references/roundlet-config.json within the installed $roundlet skill without changing or defaulting any value
- Expected Launcher task/model/effort: <LAUNCHER_TASK_ID> / <MODEL> / <EFFORT>

Read the complete Roundlet SKILL.md and every reference it requires before acting. Read task metadata and require this exact Launcher task/model/effort to equal the owner-bound expected values above; self-reported profile text is insufficient. Bind that verified profile into the Launcher canary result. Do not implement an issue in this Launcher task.

Perform a fail-closed activation preflight:
1. Resolve the exact installed skill source and configuration. Build the exact `roundlet-contract/v1` JSON object and `roundlet-tree/v1` digest defined in the operator guide—same field names, types, source/ref/version rules, POSIX relative paths, file set, byte framing, ordering, and canonical JSON encoding. Derive the lowercase-hex contract ID from the SHA-256 of canonical manifest bytes with `contract_id` omitted, then add that ID and reserialize under the same rules. Validate that every required configuration value is present and internally consistent. Require unique Supervisor attempt-profile names and an ordered profile count exactly equal to `max_supervisor_attempts_per_round`. Require both heartbeat backoff arrays to start at `active_minutes`, increase strictly, contain positive whole minutes, and support updating one existing heartbeat; require a positive full-reconciliation tick bound. Require `filesystem_canary.required: true` and `approval_retry_limit: 1`; do not default or broaden either value.
2. Verify that this Codex host can create, address, wait for, archive, and resume tasks; create, inspect, update, pause/resume, and stop one recurring heartbeat at every configured interval; select every configured model and reasoning effort in every Supervisor attempt profile exactly; and access Git, the target checkout, and GitHub with the required read/write capabilities. Do not substitute an unsupported model, effort, attempt profile, or interval.
3. Verify the target identity, clean authoritative checkout, main branch, origin URL, GitHub default branch, HEAD == local main == origin/main, merge-commit support, issue and pull-request access, and authenticated GitHub identity. Record whether the primary branch is protected. Inspect and obey every existing required check and branch rule; fail closed if existing rules cannot be inspected or conflict with the configured workflow. Absence of branch protection is not itself an activation blocker.
4. When `gh` is installed or a required capability relies on it, run a representative read-only GitHub CLI request in this Launcher task. A failure observed before GitHub is reachable is inconclusive: request scoped network escalation for the same command automatically and follow the bounded connectivity recovery contract. Do not open browser authentication, substitute browser automation, or declare the credential invalid unless reachable GitHub rejects authentication. Record the exact successful path or blocking evidence.
5. Read the root AGENTS.md from authoritative origin/main and parse only the exact Roundlet authority switches defined by the skill. Fail closed on missing, malformed, duplicate, or conflicting values. Require `roundlet.enabled: true`; record every other `false` switch as a later mutation boundary rather than silently changing it or rejecting activation.
6. Add `.roundlet/` to this checkout's local `.git/info/exclude` if it is not already excluded. Never commit that exclusion or any `.roundlet` file.
7. Inspect `.roundlet/lease.json`, `.roundlet/current.md`, `.roundlet/contracts/`, `.roundlet/canary-evidence/`, GitHub traces, active codex/* branches and pull requests, local worktrees, and relevant Codex tasks/heartbeats. If any evidence suggests another live or unreconciled run, stop with STALE_OR_ACTIVE_RUN_REQUIRES_OWNER; never expire, steal, replace, or overwrite it.
8. Reserve one unguessable stable run ID before creating the contract bundle or any run resource, and use that exact ID in every activation canary result and later lease/current record; reservation alone grants no ownership. Run activation filesystem canaries before creating the contract bundle or run. In this Launcher task, choose a separate unguessable artifact nonce and exact absent path below ignored `.roundlet/`; create a bounded artifact, change it through the mutation route intended for advisory checkpoints, read back exact identity/content, remove it and any empty canary parent, and prove the path absent. Then create a temporary isolated linked worktree at an exact unique path from authoritative `origin/main` and a short-lived canary Worker task using the configured Worker model/effort. That task must capture exact initial HEAD/status/index identity, create and change one unique bounded worktree artifact, read back identity/content, stage only one separate unique unignored canary path, verify its exact index entry/blob/content, unstage only that path, remove both artifacts, and prove HEAD/status/index match the initial values. After artifact/index cleanup proof, keep the clean canary Worker and temporary linked worktree available and unchanged until the complete activation evidence set is built and read back; only then archive the Worker and normally remove the worktree. Use no user path, existing file, unique work, issue branch, commit, or GitHub mutation.

Classify every denial/escalation/execution/capability outcome with the operator guide's exact typed taxonomy. An initial sandbox denial gets at most the configured one narrow host-supported approval retry. A launched non-zero result is not an approval denial. Any failed read-back, identity check, restoration, task cleanup, or worktree cleanup is `FILESYSTEM_CAPABILITY_UNAVAILABLE`; activation stops before issue selection, retains exact bounded evidence, reports any remaining exact canary/task/worktree path, and never claims cleanup that was not proven.

If and only if all preflight checks pass:
1. Create `.roundlet/contracts/<contract-id>/` by copying the exact manifest inputs without transformation, include the canonical manifest, and read back every path, hash, and resolved role value. If an existing directory with that ID differs, stop with `CONTRACT_BUNDLE_CONFLICT`.
2. Create `.roundlet/lease.json` and `.roundlet/current.md` as the advisory recovery index defined by the skill. Reuse the exact stable run ID reserved before the canaries, plus the exact target identity, this authoritative machine/checkout, the owner identity, activation time, and the Orchestrator task identity once known. Do not add an expiry.
3. Record the same activation and active contract ID and bundle path in both advisory files. Create exactly one long-lived Orchestrator task using role `orchestrator` model and reasoning effort from the pinned bundle. Give it the exact target, checkout, run ID, owner allowlist, resolved authority, pinned configuration, contract ID and bundle path, lease/current paths, the verified exact Launcher and activation-Worker canary results plus their hashes as provisional inputs, and the Orchestrator contract from that bundle. Require this Orchestrator task to repeat the unique advisory-state create/edit/read-back/cleanup canary on a new exact path, aggregate all three required results into the canonical activation evidence set, and read back its manifest/digest before readiness. When Launcher preflight relied on `gh`, require the Orchestrator to repeat the representative read-only request in its own task under the same automatic escalation and bounded recovery rules before it answers exactly:
   ACTIVATION_READY run=<run-id> target=<owner/repository> state=IDLE canary_set=<sha256>
   without selecting an issue yet.
4. Wait for that exact response and independently read back the bound aggregate. Then archive the short-lived canary Worker, normally remove its clean temporary worktree, and verify both cleanup actions. This required post-acceptance resource cleanup does not alter the immutable activation result bytes or completed-transition set. If creation, preflight, acknowledgement, aggregate read-back, or resource cleanup is incomplete or ambiguous, stop and preserve evidence; do not attach a heartbeat.
5. Create exactly one recurring heartbeat every configured `heartbeat.active_minutes`, addressed to the long-lived Orchestrator task. Its instruction is: invoke one idempotent Roundlet tick, prove the bounded observation baseline unchanged or perform full reconciliation in the same tick, make at most one safe state transition, maintain the configured phase-aware interval on that same heartbeat, and report the resulting state.
6. Send the heartbeat identity and schedule to the Orchestrator. Require and wait for:
   HEARTBEAT_BOUND run=<run-id> heartbeat=<heartbeat-id> interval=<minutes>m
7. Verify the lease/current files name the same run, Orchestrator, heartbeat, active contract ID, and verified bundle, then send the Orchestrator one initial tick.
8. Report the target, run ID, active contract ID, Orchestrator task, heartbeat, and preflight result to the owner. Archive this Launcher task. The Orchestrator task must remain long-lived.

Never attach the heartbeat to this Launcher. Never create a second Orchestrator or heartbeat. Never begin issue work after a failed or partial preflight.
```

## Explicit recovery

Use this only when the original Orchestrator or heartbeat is genuinely inaccessible. An old lease never authorizes automatic takeover.

Copy and paste this entire prompt into a new Codex task:

```text
Act as a short-lived Roundlet recovery Launcher for exactly one previously activated target. Do not invoke or load the installed `$roundlet` skill.

Target:
- GitHub repository: <OWNER/REPOSITORY>
- Authoritative local checkout: <ABSOLUTE_PATH>
- Existing Roundlet run ID, if known: <RUN_ID_OR_UNKNOWN>
- Owner recovery instruction: reconcile the old run and, only if replacement is safe, create one replacement Orchestrator and heartbeat
- Expected recovery Launcher task/model/effort: <LAUNCHER_TASK_ID> / <MODEL> / <EFFORT>

Read task metadata first and require this exact recovery Launcher task/model/effort to equal the owner-bound expected values above; self-reported profile text is insufficient, and the verified profile is bound into its canary result. Read only `.roundlet/lease.json` and the minimal contract commit records needed to resolve the effective active bundle, verify that bundle completely, then read its `SKILL.md` and every required reference before acting. Treat installed skill/configuration files only as a separately fingerprinted candidate. This prompt is explicit owner authorization to investigate and propose recovery; it is not authorization to discard, overwrite, merge, close, delete, or otherwise destroy old work.

1. Perform the normal capability, repository, configuration, authority, and identity preflight.
2. Reconcile `.roundlet/lease.json`, `.roundlet/current.md`, the named active contract bundle and manifest, all Roundlet GitHub trace comments, active pull requests, exact branch SHAs, local and remote branches, worktrees, checks, and all identifiable old Orchestrator/Worker/Supervisor tasks and heartbeats. Treat the installed skill/configuration only as a migration candidate.
3. Before any advisory, Git, or GitHub transition, run recovery canaries. The recovery Launcher proves the exact ignored advisory-state surface. When an active leaf retains an accessible Worker, that same Worker uses unique paths in its retained linked worktree to prove file create/edit/read-back/cleanup and exact-path stage/index-read-back/unstage/cleanup while restoring the complete initial HEAD/status/index identity; a phase with no Worker does not invent one. Never replace a Worker for a canary. If the old Orchestrator is accessible, it must prove its own advisory route; a replacement Orchestrator must do so before `RECOVERY_READY`. Keep every exact same-phase result byte/hash as a provisional aggregate input. On any failed or stale evidence, retain every run resource, classify the exact typed outcome, and stop in `FILESYSTEM_CAPABILITY_BLOCKED` before transition.
4. If the old Orchestrator or heartbeat is still live or its ownership is ambiguous, stop with RECOVERY_OWNER_DECISION_REQUIRED and present exact evidence. Do not create a replacement.
5. If the old Orchestrator and heartbeat are conclusively unavailable, reconstruct the current phase from durable GitHub and Git evidence. Preserve the same run ID when identity is certain; otherwise stop for owner input.
6. If an active Worker task is unavailable, stop with WORKER_REPLACEMENT_REQUIRES_OWNER. Do not silently replace it.
7. Create exactly one replacement Orchestrator using the active pinned bundle's configured model and effort. Give it the reconstructed state, evidence, task identities, branch/worktree, candidate SHA, review epoch/round, current Supervisor attempt/profile when applicable, and the verified recovery Launcher plus applicable retained-Worker result bytes/hashes. Require it to run its unique `RECOVERY` advisory canary, aggregate every applicable result into the canonical recovery evidence set, read back the manifest/digest, then answer exactly `RECOVERY_READY run=<run-id> state=<reconstructed-phase> canary_set=<sha256>` without advancing work.
8. Only after that exact acknowledgement and independent aggregate read-back, disable or remove any conclusively stale heartbeat if possible, create one replacement heartbeat at configured `heartbeat.active_minutes`, bind it to the replacement Orchestrator, reconstruct the observation counters without treating stale fingerprints as proof, update the advisory files, and send one recovery tick.
9. Report every retained, replaced, or unresolved resource to the owner and archive this recovery Launcher.

Fail closed at every ambiguity. Never infer owner consent for cleanup, abort, merge, or task replacement.
```

## Owner-authorized legacy run contract bootstrap

Use this one time for a pre-contract run whose lease has no activation contract identity. It pins the old instructions before any adoption or migration. Deliver it to the same long-lived Orchestrator with the exact activation-time Orchestrator model/effort override; do not use the candidate settings yet.

```text
Continue the existing legacy Roundlet run only to pin its activation-time contract. Do not invoke or load the currently installed `$roundlet` skill.

Target repository: <OWNER/REPOSITORY>
Authoritative checkout: <ABSOLUTE_PATH>
Run ID and activation time: <RUN_ID> / <LEASE_ACTIVATED_AT>
Expected Orchestrator task: <ORCHESTRATOR_TASK_ID>
Owner-authorized activation source/ref: <EXACT_SOURCE_LOCATOR_AND_IMMUTABLE_REF>
Expected activation-time Orchestrator model/effort: <MODEL> / <EFFORT>
Expected activation-time retained Worker model/effort when one exists: <MODEL> / <EFFORT>

Pause the heartbeat and make no GitHub, Git, issue, pull-request, branch, worktree, review,
or cleanup transition. Use only the following literal owner-authorized bootstrap canary protocol; do not load or infer it from the installed candidate or old activation source.

- The approval retry limit is exactly `1`. For each required surface, prove a unique path absent; create first bytes and read back exact path/bytes/SHA-256; change the same artifact through the intended role mutation route and verify distinct second bytes/hash; remove only that artifact and a canary-created empty parent; then prove path absence and exact surrounding-state restoration. The Worker also stages only a separate initially absent unignored path, verifies exact index path/mode/blob/content, unstages only it, removes it, and proves complete initial/final HEAD, status, index tree, and pre-existing identities equal. No commit, GitHub mutation, source edit, existing path, user work, or route/helper substitution is allowed.
- Retry only an initial restriction once through the narrowest host-supported approval for the same target/operation. The only valid `(approval_retry_count, approval_outcome, execution_outcome)` tuples are `(0, NOT_REQUIRED, SUCCEEDED)`, `(0, NOT_REQUIRED, DIRECT_EXECUTION_FAILED)`, `(1, APPROVED, SUCCEEDED)`, `(1, APPROVED, ESCALATED_EXECUTION_FAILED)`, `(1, ESCALATION_DENIED, NOT_LAUNCHED)`, and `(0, ESCALATION_UNAVAILABLE, NOT_LAUNCHED)`. PASS requires execution `SUCCEEDED`, every required surface PASS, only inapplicable surfaces NOT_APPLICABLE, capability PASS, and cleanup VERIFIED. Every other valid tuple and every failed/missing mutation, read-back, identity, index, restoration, or cleanup requires `FILESYSTEM_CAPABILITY_UNAVAILABLE`; cleanup remains independently truthful and external cleanup never changes the result.
- Store each exact UTF-8 result without BOM or trailing newline in this literal shape:

FILESYSTEM_CANARY_RESULT
phase: LEGACY_BOOTSTRAP
role: <ORCHESTRATOR|WORKER>
run_id: <exact-lease-run-id>
role_task: <exact-task-id>
execution_profile: model=<task-metadata-model>;reasoning_effort=<task-metadata-effort>
host_route_fingerprint: <task-host-checkout-worktree-permission-route-tool-class-digest>
target_paths: <exact-local-canary-paths>
advisory_surface: <PASS|NOT_APPLICABLE|FAIL> <evidence-digest-or-none>
worktree_surface: <PASS|NOT_APPLICABLE|FAIL> <initial-final-identity-digest-or-none>
index_surface: <PASS|NOT_APPLICABLE|FAIL> <initial-final-index-and-entry-digest-or-none>
approval_retry_count: <0|1>
approval_outcome: <NOT_REQUIRED|APPROVED|ESCALATION_DENIED|ESCALATION_UNAVAILABLE>
execution_outcome: <SUCCEEDED|NOT_LAUNCHED|DIRECT_EXECUTION_FAILED|ESCALATED_EXECUTION_FAILED>
capability_outcome: <PASS|FILESYSTEM_CAPABILITY_UNAVAILABLE>
cleanup: <VERIFIED|FAILED> <evidence-digest>
repository_transition: none

- The same Orchestrator must return advisory `PASS` with other surfaces `NOT_APPLICABLE`. When an active leaf retains a Worker, send these literal rules to that same Worker without invoking `$roundlet`; deliver that turn with the proven activation-time Worker model/effort override, verify task metadata and exact `execution_profile` match the proven old resolved configuration, and require advisory `NOT_APPLICABLE`, worktree/index `PASS`, and exact state restoration. A phase with no Worker does not invent one.
- Build exactly `{"schema":"roundlet-filesystem-canary-set/v1","run_id":"<exact-lease-run-id>","transition":"LEGACY_BOOTSTRAP","results":[<entries>]}`. Each entry contains exactly `phase`, `role`, `role_task`, `execution_profile`, `host_route_fingerprint`, `advisory_surface`, `worktree_surface`, `index_surface`, `cleanup`, and `result_sha256`, where the result digest is `sha256:<lowercase-hex>` of exact stored result bytes. Sort entries by the unsigned UTF-8 byte tuple `(phase, role, role_task, execution_profile, host_route_fingerprint)`, reject duplicates, serialize with RFC 8785 JCS without BOM, trailing newline, or floats, and identify the set as `sha256:<lowercase-hex>` of the exact canonical manifest bytes. Decode every result and require the exact line schema/order, a valid typed-outcome combination, run ID equal set run ID, phase equal transition, repository transition `none`, capability `PASS`, cleanup `VERIFIED`, and every projected phase/role/task/profile/route/surface/cleanup value equal the entry. Require exactly the applicable Orchestrator plus retained-Worker roles, all required surfaces `PASS`, and only inapplicable surfaces `NOT_APPLICABLE`; missing, extra, duplicate, cross-run/phase, stale, mismatched, or failed evidence invalidates the set. Store accepted bytes under `.roundlet/canary-evidence/accepted/<aggregate-sha256-hex>/`, with exact results at `results/<zero-padded-ordinal>-<result-sha256-hex>.txt` and `manifest.json` written/read back last. When the exact advisory route can write/read it, store failed attempts under `.roundlet/canary-evidence/failed/<run-id>/<attempt-id>/`. If that advisory route itself fails, retain the exact bounded result only in the existing immutable task response identified by task ID, response/event ID, and digest; do not substitute a route merely to create local evidence. Such no-write evidence is failed-only and can never be accepted. These bounded bytes are immutable, conflicting paths fail closed, and failed evidence is never promoted.

Read back the exact LEGACY_BOOTSTRAP manifest, result bytes, and aggregate SHA-256 before any contract write. On any denial, unavailable approval, launched non-zero execution, read-back mismatch, cleanup mismatch, or invalid aggregate, retain every resource, create no contract record, and report FILESYSTEM_CAPABILITY_BLOCKED with the exact type.
Prove this run predates contract state and has no activation ID,
legacy-activation record, contract bundle, prepared record, or committed record. Reconcile
the lease/current files, original Orchestrator bootstrap and task metadata, durable Roundlet
trace, activation timestamp, installation provenance, and the named source/ref. Require the
complete source bytes and role configuration to agree with that evidence. Current installed
bytes are not activation evidence.

Use these literal owner-authorized bootstrap-format rules without consulting any other skill copy:
- file set: exact old `SKILL.md` plus every reference it names, unique POSIX relative paths
  without `..`, NUL, CR, or LF, sorted by unsigned UTF-8 bytes; SHA-256 exact bytes;
- tree input: ASCII `roundlet-tree/v1\n`, then for each file UTF-8 path, byte 0x00,
  64 lowercase hash hex bytes, byte 0x0a; tree value is `sha256:<lowercase-hex>`;
- hash-input JSON is exactly `{"contract_schema":"roundlet-contract/v1",` plus
  `"contract_version":"roundlet-contract/v1@<source-ref>","files":[{"path":`
  `"<relative>","sha256":"<64-lowercase-hex>"}],"resolved_config":<complete-old-`
  `config-object>,"source":{"kind":"<git|installed-tree>","locator":"<string>",`
  `"ref":"<string>"},"tree_digest":"sha256:<64-lowercase-hex>"}` with no extra field;
  for git use canonical `owner/repository` plus verified lowercase 40-character OID; for
  installed-tree use resolved absolute old skill directory plus the exact tree_digest;
- serialize with RFC 8785 JCS, no BOM/trailing newline/floats; hash those bytes for the
  lowercase contract ID; add only top-level `contract_id`, reserialize, and read back.

Build and read back that deterministic roundlet-contract/v1 bundle from the proven old ref.
Create exactly one canonical `.roundlet/legacy-activation.json` using schema
roundlet-legacy-activation/v1 with run ID, lease SHA-256, activation time, owner authorization
event, source/ref, old contract ID, bundle-manifest hash, same task ID, task-metadata
model/effort read-back, filesystem-canary evidence-set digest, other evidence digests, and timestamp. The record is valid only when every
field and referenced byte reads back. A partial record has no effect; multiple valid records
or contradictory evidence fail closed.

After the one valid record exists, resolve it as the immutable activation ID, refresh only derived mirrors, and return exactly these lines in this order:
LEGACY_CONTRACT_PINNED
run_id: <stable-run-id>
orchestrator_task: <verified-same-task-id>
activation_source_ref: <exact-immutable-source-and-ref>
activation_contract_id: <verified-old-id>
legacy_record: <absolute-path-and-sha256>
filesystem_canary_evidence_set: <verified-aggregate-sha256>
filesystem_canary_evidence_path: <absolute-accepted-path>
orchestrator_model: <task-metadata-readback-model>
reasoning_effort: <task-metadata-readback-effort>
resources_retained: <heartbeat-and-every-reconciled-worker-branch-worktree-pr-issue-sha-or-none>
repository_transition: none
Keep the heartbeat paused. Do not adopt the candidate in this turn. A missing field, unverified evidence path/digest, self-reported or substituted profile, changed resource, or repository transition invalidates the acknowledgement. If exact activation identity is not provable, create no record and reply LEGACY_CONTRACT_IDENTITY_REQUIRES_OWNER.
```

Only after `LEGACY_CONTRACT_PINNED` is externally verified may the owner use the applicable between-issue adoption or active in-place migration protocol.

## Owner-authorized between-issue contract adoption

Use this only in the existing long-lived Orchestrator task when the fully reconciled phase is `IDLE` and no active leaf, branch, worktree, Worker, pull request, unique work, or unresolved cleanup remains. Deliver the prompt as a same-task follow-up with the candidate's exact Orchestrator model and reasoning effort override. Before contract work, require task metadata read-back proving the same task identity and actual turn model/effort.

```text
Continue the existing Roundlet run as an owner-authorized between-issue contract adoption. Do not invoke or load the installed `$roundlet` skill as active instructions.

Target repository: <OWNER/REPOSITORY>
Authoritative checkout: <ABSOLUTE_PATH>
Expected current contract ID: <OLD_CONTRACT_ID>
Expected current contract bundle: <ABSOLUTE_OLD_BUNDLE_PATH>
Owner-authorized candidate source/ref: <EXACT_CANDIDATE_IDENTITY>
Expected same Orchestrator task: <ORCHESTRATOR_TASK_ID>
Expected candidate Orchestrator model/effort: <MODEL> / <EFFORT>
Expected candidate Worker model/effort: <MODEL> / <EFFORT>

Use only this literal owner-authorized BETWEEN_ISSUES_ADOPTION canary protocol for this preparation; do not load it from the installed candidate or assume the old bundle contains it.
- The approval retry limit is exactly `1`. For each required file surface, prove a unique path absent; create first bytes and verify exact path/bytes/SHA-256; change the same artifact through the intended role route and verify distinct second bytes/hash; remove only it and a canary-created empty parent; then prove absence and exact surrounding-state restoration. The Worker also stages only a separate initially absent unignored path, verifies exact index path/mode/blob/content, unstages only it, removes it, and proves complete initial/final HEAD, status, index tree, and pre-existing identities equal. No commit, GitHub mutation, source edit, existing path, user work, or helper/route substitution is allowed.
- Store each result as exact UTF-8 without BOM or trailing newline with these lines in this order: `FILESYSTEM_CANARY_RESULT`; `phase: BETWEEN_ISSUES_ADOPTION`; `role: <ORCHESTRATOR|WORKER>`; `run_id: <exact-run-id>`; `role_task: <exact-task-id>`; `execution_profile: model=<task-metadata-model>;reasoning_effort=<task-metadata-effort>`; `host_route_fingerprint: <task-host-checkout-worktree-permission-route-tool-class-digest>`; `target_paths: <exact-local-canary-paths>`; `advisory_surface: <PASS|NOT_APPLICABLE|FAIL> <evidence-digest-or-none>`; `worktree_surface: <PASS|NOT_APPLICABLE|FAIL> <initial-final-identity-digest-or-none>`; `index_surface: <PASS|NOT_APPLICABLE|FAIL> <initial-final-index-and-entry-digest-or-none>`; `approval_retry_count: <0|1>`; `approval_outcome: <NOT_REQUIRED|APPROVED|ESCALATION_DENIED|ESCALATION_UNAVAILABLE>`; `execution_outcome: <SUCCEEDED|NOT_LAUNCHED|DIRECT_EXECUTION_FAILED|ESCALATED_EXECUTION_FAILED>`; `capability_outcome: <PASS|FILESYSTEM_CAPABILITY_UNAVAILABLE>`; `cleanup: <VERIFIED|FAILED> <evidence-digest>`; `repository_transition: none`.
- Retry only an initial restriction once through the narrowest host-supported approval for the same target/operation. The only valid `(approval_retry_count, approval_outcome, execution_outcome)` tuples are `(0, NOT_REQUIRED, SUCCEEDED)`, `(0, NOT_REQUIRED, DIRECT_EXECUTION_FAILED)`, `(1, APPROVED, SUCCEEDED)`, `(1, APPROVED, ESCALATED_EXECUTION_FAILED)`, `(1, ESCALATION_DENIED, NOT_LAUNCHED)`, and `(0, ESCALATION_UNAVAILABLE, NOT_LAUNCHED)`. PASS requires execution `SUCCEEDED`, every required surface PASS, only inapplicable surfaces NOT_APPLICABLE, capability PASS, and cleanup VERIFIED. Every other valid tuple and every failure requires `FILESYSTEM_CAPABILITY_UNAVAILABLE`; cleanup remains independently truthful and external cleanup never changes it.
- Require exactly the same Orchestrator with advisory PASS and other surfaces NOT_APPLICABLE, plus one short-lived Worker whose turn is delivered with the exact candidate Worker model/effort override, whose task metadata and `execution_profile` equal the candidate resolved configuration, and whose advisory is NOT_APPLICABLE with worktree/index PASS.
- Build exactly `{"schema":"roundlet-filesystem-canary-set/v1","run_id":"<exact-run-id>","transition":"BETWEEN_ISSUES_ADOPTION","results":[<entries>]}`. Each entry contains exactly `phase`, `role`, `role_task`, `execution_profile`, `host_route_fingerprint`, `advisory_surface`, `worktree_surface`, `index_surface`, `cleanup`, and `result_sha256`; the result digest is `sha256:<lowercase-hex>` of exact result bytes. Sort entries by the unsigned UTF-8 byte tuple `(phase, role, role_task, execution_profile, host_route_fingerprint)`, reject duplicates, serialize with RFC 8785 JCS without BOM/trailing newline/floats, and identify the set as `sha256:<lowercase-hex>` of the exact canonical manifest bytes. Decode every result and require its exact schema/order, valid typed-outcome combination, run ID equal set run ID, phase equal transition, repository transition none, capability PASS, cleanup VERIFIED, and every projected phase/role/task/profile/route/surface/cleanup value equal the entry. Require exactly the roles/surfaces above; missing, extra, duplicate, stale, cross-run/phase, failed, overwritten, or mismatched evidence invalidates the set. Read back exact result bytes, manifest bytes, and aggregate digest before relying on it. Store accepted bytes under `.roundlet/canary-evidence/accepted/<aggregate-sha256-hex>/`, with exact results at `results/<zero-padded-ordinal>-<result-sha256-hex>.txt` and `manifest.json` written/read back last. When the exact advisory route can write/read it, store failed attempts under `.roundlet/canary-evidence/failed/<run-id>/<attempt-id>/`. If that advisory route itself fails, retain the exact bounded result only in the existing immutable task response identified by task ID, response/event ID, and digest; do not substitute a route merely to create local evidence. Such no-write evidence is failed-only and can never be accepted. These bounded bytes are immutable, conflicting paths fail closed, and failed evidence is never promoted.

Pause the heartbeat. Resolve and read the effective old bundle, reconcile every run resource,
and prove the run is cleanly IDLE with no leaf resources. Before contract work, this
Orchestrator must pass a unique ignored advisory create/edit/read-back/cleanup canary; create
a temporary linked worktree plus short-lived candidate-configured Worker to pass the unique
worktree file and exact Git-index stage/read-back/unstage canaries with exact artifact/index cleanup proof. Aggregate both role results as the exact BETWEEN_ISSUES_ADOPTION evidence set and read back its manifest/digest; only then archive/remove the clean short-lived Worker/worktree and verify that resource cleanup. The completed-transition set remains immutable evidence for this preparation but cannot authorize a later transition. Classify typed outcomes and stop before contract work on any failure. Verify task metadata shows this
same task and the exact candidate model/effort for this turn. Build and read back the new bundle. Create `prepared.json` as RFC 8785 canonical JSON with no BOM or trailing newline and exactly these fields: `schema` = `roundlet-contract-migration-prepared/v1`; positive integer `sequence`; `migration_id`; `run_id`; `mode`; `old_contract_id`; `new_contract_id`; `candidate_source`; `candidate_ref`; `owner_authorization_event`; `orchestrator_task`; `orchestrator_model`; `reasoning_effort`; `model_readback_source`; `filesystem_canary_evidence_set_digest`; `filesystem_canary_evidence_path`; `bundle_manifest_sha256`; and `prepared_at`. Hash values use `sha256:<64-lowercase-hex>`. Write it at `.roundlet/migrations/<sequence>-<migration-id>/prepared.json`, read back exact bytes/fields, and fail closed on any existing conflicting path. Make no GitHub or repository transition.

After all gates and a truthful checkpoint pass, return exactly these lines in this order:
CONTRACT_MIGRATION_READY
mode: BETWEEN_ISSUES
run_id: <stable-run-id>
orchestrator_task: <verified-same-task-id>
old_contract_id: <verified-old-id>
new_contract_id: <verified-new-id>
orchestrator_model: <task-metadata-readback-model>
reasoning_effort: <task-metadata-readback-effort>
model_readback_source: <task-metadata-source>
filesystem_canary_evidence_set: <verified-aggregate-sha256>
filesystem_canary_evidence_path: <absolute-accepted-path>
prepared_record: <absolute-path-and-sha256>
truthful_checkpoint: <absolute-path-and-sha256>
phase: <retained-phase>
resources_retained: <orchestrator-heartbeat-and-every-reconciled-optional-resource-or-none>
repository_transition: none
A missing field, wrong mode/task, self-reported or substituted model/effort, changed retained resource, unpaused heartbeat, unverifiable bundle/prepared record/checkpoint/evidence set, or repository transition invalidates the acknowledgement.
Do not create committed.json, refresh mirrors, resume the heartbeat, or make any repository transition in this preparation turn. A separate verified commit turn performs the single commit point.
```

## Owner-authorized in-place contract migration

Use this only in the existing long-lived Orchestrator task after an allowlisted owner explicitly authorizes migration to an exact installed candidate. Deliver the prompt as a same-task follow-up with the candidate's exact Orchestrator model and reasoning effort override. Before any pointer or commit work, require task metadata read-back proving the same task identity and actual turn model/effort. It updates the prompt/configuration contract without replacing the run or abandoning active work.

```text
Continue the existing Roundlet run to migrate it in place to the exact owner-authorized candidate contract. Do not invoke or load the installed `$roundlet` skill as active instructions.

Target repository: <OWNER/REPOSITORY>
Authoritative checkout: <ABSOLUTE_PATH>
Expected current contract ID: <OLD_CONTRACT_ID>
Expected current contract bundle: <ABSOLUTE_OLD_BUNDLE_PATH>
Owner-authorized candidate source/ref: <EXACT_CANDIDATE_IDENTITY>
Expected same Orchestrator task: <ORCHESTRATOR_TASK_ID>
Expected candidate Orchestrator model/effort: <MODEL> / <EFFORT>
Expected candidate Worker model/effort when one is retained: <MODEL> / <EFFORT>

Use only this literal owner-authorized ACTIVE_IN_PLACE_MIGRATION canary protocol for this preparation; do not load it from the installed candidate or assume the old bundle contains it.
- The approval retry limit is exactly `1`. For each required file surface, prove a unique path absent; create first bytes and verify exact path/bytes/SHA-256; change the same artifact through the intended role route and verify distinct second bytes/hash; remove only it and a canary-created empty parent; then prove absence and exact surrounding-state restoration. The Worker also stages only a separate initially absent unignored path, verifies exact index path/mode/blob/content, unstages only it, removes it, and proves complete initial/final HEAD, status, index tree, and pre-existing identities equal. No commit, GitHub mutation, source edit, existing path, user work, or helper/route substitution is allowed.
- Store each result as exact UTF-8 without BOM or trailing newline with these lines in this order: `FILESYSTEM_CANARY_RESULT`; `phase: ACTIVE_IN_PLACE_MIGRATION`; `role: <ORCHESTRATOR|WORKER>`; `run_id: <exact-run-id>`; `role_task: <exact-task-id>`; `execution_profile: model=<task-metadata-model>;reasoning_effort=<task-metadata-effort>`; `host_route_fingerprint: <task-host-checkout-worktree-permission-route-tool-class-digest>`; `target_paths: <exact-local-canary-paths>`; `advisory_surface: <PASS|NOT_APPLICABLE|FAIL> <evidence-digest-or-none>`; `worktree_surface: <PASS|NOT_APPLICABLE|FAIL> <initial-final-identity-digest-or-none>`; `index_surface: <PASS|NOT_APPLICABLE|FAIL> <initial-final-index-and-entry-digest-or-none>`; `approval_retry_count: <0|1>`; `approval_outcome: <NOT_REQUIRED|APPROVED|ESCALATION_DENIED|ESCALATION_UNAVAILABLE>`; `execution_outcome: <SUCCEEDED|NOT_LAUNCHED|DIRECT_EXECUTION_FAILED|ESCALATED_EXECUTION_FAILED>`; `capability_outcome: <PASS|FILESYSTEM_CAPABILITY_UNAVAILABLE>`; `cleanup: <VERIFIED|FAILED> <evidence-digest>`; `repository_transition: none`.
- Retry only an initial restriction once through the narrowest host-supported approval for the same target/operation. The only valid `(approval_retry_count, approval_outcome, execution_outcome)` tuples are `(0, NOT_REQUIRED, SUCCEEDED)`, `(0, NOT_REQUIRED, DIRECT_EXECUTION_FAILED)`, `(1, APPROVED, SUCCEEDED)`, `(1, APPROVED, ESCALATED_EXECUTION_FAILED)`, `(1, ESCALATION_DENIED, NOT_LAUNCHED)`, and `(0, ESCALATION_UNAVAILABLE, NOT_LAUNCHED)`. PASS requires execution `SUCCEEDED`, every required surface PASS, only inapplicable surfaces NOT_APPLICABLE, capability PASS, and cleanup VERIFIED. Every other valid tuple and every failure requires `FILESYSTEM_CAPABILITY_UNAVAILABLE`; cleanup remains independently truthful and external cleanup never changes it.
- Require the same Orchestrator with advisory PASS and other surfaces NOT_APPLICABLE plus, only when an active leaf retains a Worker, that same Worker running this canary turn under the exact candidate Worker model/effort override with task metadata and `execution_profile` equal to the candidate resolved configuration, advisory NOT_APPLICABLE, and worktree/index PASS; a phase with no Worker does not invent one.
- Build exactly `{"schema":"roundlet-filesystem-canary-set/v1","run_id":"<exact-run-id>","transition":"ACTIVE_IN_PLACE_MIGRATION","results":[<entries>]}`. Each entry contains exactly `phase`, `role`, `role_task`, `execution_profile`, `host_route_fingerprint`, `advisory_surface`, `worktree_surface`, `index_surface`, `cleanup`, and `result_sha256`; the result digest is `sha256:<lowercase-hex>` of exact result bytes. Sort entries by the unsigned UTF-8 byte tuple `(phase, role, role_task, execution_profile, host_route_fingerprint)`, reject duplicates, serialize with RFC 8785 JCS without BOM/trailing newline/floats, and identify the set as `sha256:<lowercase-hex>` of the exact canonical manifest bytes. Decode every result and require its exact schema/order, valid typed-outcome combination, run ID equal set run ID, phase equal transition, repository transition none, capability PASS, cleanup VERIFIED, and every projected phase/role/task/profile/route/surface/cleanup value equal the entry. Require exactly the roles/surfaces above; missing, extra, duplicate, stale, cross-run/phase, failed, overwritten, or mismatched evidence invalidates the set. Read back exact result bytes, manifest bytes, and aggregate digest before relying on it. Store accepted bytes under `.roundlet/canary-evidence/accepted/<aggregate-sha256-hex>/`, with exact results at `results/<zero-padded-ordinal>-<result-sha256-hex>.txt` and `manifest.json` written/read back last. When the exact advisory route can write/read it, store failed attempts under `.roundlet/canary-evidence/failed/<run-id>/<attempt-id>/`. If that advisory route itself fails, retain the exact bounded result only in the existing immutable task response identified by task ID, response/event ID, and digest; do not substitute a route merely to create local evidence. Such no-write evidence is failed-only and can never be accepted. These bounded bytes are immutable, conflicting paths fail closed, and failed evidence is never promoted.

Retain the same run ID, Orchestrator task, heartbeat, and every reconciled active Worker, branch, worktree, pull request, issue, candidate SHA, and review-state resource that exists; do not invent absent optional resources. Pause the heartbeat before migration.
Before contract work, this Orchestrator must pass a unique ignored advisory
create/edit/read-back/cleanup canary. When an active leaf retains a Worker, that same retained Worker must pass unique linked-
worktree file mutation plus exact-path stage/index-read-back/unstage/cleanup while restoring
its complete initial HEAD/status/index identity; a phase with no Worker does not invent one. Aggregate the Orchestrator and every applicable retained-Worker result as the exact ACTIVE_IN_PLACE_MIGRATION evidence set and read back its manifest/digest. Classify typed outcomes and retain every
resource in FILESYSTEM_CAPABILITY_BLOCKED on any denial, unavailable approval, launched
non-zero execution, identity/read-back mismatch, or cleanup mismatch.
Read the old active bundle first. Reconcile GitHub, Git, every retained task, heartbeat,
lease/current pointers, active bundle, installed candidate, authority, and current phase.
Stop on any contradiction or uncommitted atomic mutation.

Verify task metadata proves this exact Orchestrator task is executing this turn under the
candidate model and reasoning effort; self-reported model text is insufficient. Build and read back the new content-addressed bundle. Create `prepared.json` as RFC 8785 canonical JSON with no BOM or trailing newline and exactly these fields: `schema` = `roundlet-contract-migration-prepared/v1`; positive integer `sequence`; `migration_id`; `run_id`; `mode`; `old_contract_id`; `new_contract_id`; `candidate_source`; `candidate_ref`; `owner_authorization_event`; `orchestrator_task`; `orchestrator_model`; `reasoning_effort`; `model_readback_source`; `filesystem_canary_evidence_set_digest`; `filesystem_canary_evidence_path`; `bundle_manifest_sha256`; and `prepared_at`. Hash values use `sha256:<64-lowercase-hex>`. Write it at `.roundlet/migrations/<sequence>-<migration-id>/prepared.json`, read back exact bytes/fields, and fail closed on any existing conflicting path. This preparation does not change the effective contract. Verify every manifest field/path/hash and every resolved role value.
Write the truthful checkpoint, then return exactly these lines in this order:
CONTRACT_MIGRATION_READY
mode: ACTIVE_IN_PLACE
run_id: <stable-run-id>
orchestrator_task: <verified-same-task-id>
old_contract_id: <verified-old-id>
new_contract_id: <verified-new-id>
orchestrator_model: <task-metadata-readback-model>
reasoning_effort: <task-metadata-readback-effort>
model_readback_source: <task-metadata-source>
filesystem_canary_evidence_set: <verified-aggregate-sha256>
filesystem_canary_evidence_path: <absolute-accepted-path>
prepared_record: <absolute-path-and-sha256>
truthful_checkpoint: <absolute-path-and-sha256>
phase: <retained-phase>
resources_retained: <orchestrator-heartbeat-and-every-reconciled-worker-branch-worktree-pr-issue-sha-or-none>
repository_transition: none
A missing field, wrong mode/task, self-reported or substituted model/effort, changed retained resource, unpaused heartbeat, unverifiable bundle/prepared record/checkpoint/evidence set, or repository transition invalidates the acknowledgement.
Do not create committed.json, refresh mirrors, resume the heartbeat, or make any repository transition in this preparation turn. Keep the old bundle and every retained resource unchanged.
```

## Contract adoption or migration commit turn

After an externally verified `CONTRACT_MIGRATION_READY` result, deliver this as a second same-task follow-up with the same candidate model and reasoning-effort override. If task metadata or any prepared evidence changed, do not commit.

```text
Complete only the previously prepared Roundlet contract adoption or migration. Do not invoke or load the installed $roundlet skill as active instructions.

Expected Orchestrator task: <ORCHESTRATOR_TASK_ID>
Expected run/mode: <RUN_ID> / <BETWEEN_ISSUES|ACTIVE_IN_PLACE>
Expected old/new contract IDs: <OLD_ID> / <NEW_ID>
Expected prepared.json SHA-256: <PREPARED_SHA256>
Expected truthful checkpoint SHA-256: <CHECKPOINT_SHA256>
Expected filesystem-canary evidence-set SHA-256: <CANARY_EVIDENCE_SET_SHA256>
Expected candidate model/effort: <MODEL> / <EFFORT>
Expected CONTRACT_MIGRATION_READY evidence: <EXACT_ACK_ID_OR_DIGEST>

Verify task metadata, the effective old chain, paused heartbeat, retained resources, bundle,
prepared record, owner authorization, exact READY bytes/digest, exact truthful checkpoint
bytes/digest, and bound filesystem-canary evidence-set manifest and digest again. Require committed.json to bind both verified digests. If any
value differs, create no committed record and report CONTRACT_MIGRATION_COMMIT_BLOCKED.

Create `committed.json` as RFC 8785 canonical JSON with no BOM or trailing newline and exactly these fields: `schema` = `roundlet-contract-migration-committed/v1`; `migration_id`; `prepared_sha256`; `ready_evidence_sha256`; `truthful_checkpoint_sha256`; `old_contract_id`; `new_contract_id`; and `committed_at`. Hash values use `sha256:<64-lowercase-hex>`. Write it beside the verified prepared record, read back exact bytes/fields, and fail closed on any existing conflicting path. That exactly one valid committed.json is the commit point. Resolve the new
effective contract from the complete unique chain. Refresh derived lease/current mirrors,
read them back, reset the semantic baseline, and resume the same heartbeat at active_minutes.
Make no GitHub or repository transition. A pre-commit failure leaves the old contract
effective. If mirror refresh fails after the valid commit, the new contract remains effective:
pause and repair mirrors from the chain before any other transition. Return exactly these lines in this order:
CONTRACT_MIGRATION_COMMITTED
mode: <BETWEEN_ISSUES|ACTIVE_IN_PLACE>
run_id: <stable-run-id>
orchestrator_task: <verified-same-task-id>
old_contract_id: <verified-old-id>
new_contract_id: <verified-new-id>
committed_record: <absolute-path-and-sha256>
ready_evidence_sha256: <verified-digest>
truthful_checkpoint_sha256: <verified-digest>
filesystem_canary_evidence_set: <verified-aggregate-sha256>
effective_chain: <ordered-contract-ids>
derived_mirrors: <VERIFIED|REPAIR_REQUIRED>
heartbeat: <same-id-and-state>
repository_transition: none
A missing or mismatched READY/checkpoint/canary digest is invalid. If no committed record was created, return `CONTRACT_MIGRATION_COMMIT_BLOCKED` and keep the old contract effective. If the commit point succeeded but mirror or heartbeat repair is required, the new contract remains effective; return `REPAIR_REQUIRED`, keep the heartbeat paused, and repair only from the committed chain.
```
