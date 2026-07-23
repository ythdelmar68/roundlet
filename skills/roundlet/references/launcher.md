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

Read the complete Roundlet SKILL.md and every reference it requires before acting. Do not implement an issue in this Launcher task.

Perform a fail-closed activation preflight:
1. Resolve the exact installed skill source and configuration. Build the exact `roundlet-contract/v1` JSON object and `roundlet-tree/v1` digest defined in the operator guide—same field names, types, source/ref/version rules, POSIX relative paths, file set, byte framing, ordering, and canonical JSON encoding. Derive the lowercase-hex contract ID from the SHA-256 of canonical manifest bytes with `contract_id` omitted, then add that ID and reserialize under the same rules. Validate that every required configuration value is present and internally consistent. Require unique Supervisor attempt-profile names and an ordered profile count exactly equal to `max_supervisor_attempts_per_round`. Require both heartbeat backoff arrays to start at `active_minutes`, increase strictly, contain positive whole minutes, and support updating one existing heartbeat; require a positive full-reconciliation tick bound.
2. Verify that this Codex host can create, address, wait for, archive, and resume tasks; create, inspect, update, pause/resume, and stop one recurring heartbeat at every configured interval; select every configured model and reasoning effort in every Supervisor attempt profile exactly; and access Git, the target checkout, and GitHub with the required read/write capabilities. Do not substitute an unsupported model, effort, attempt profile, or interval.
3. Verify the target identity, clean authoritative checkout, main branch, origin URL, GitHub default branch, HEAD == local main == origin/main, merge-commit support, issue and pull-request access, and authenticated GitHub identity. Record whether the primary branch is protected. Inspect and obey every existing required check and branch rule; fail closed if existing rules cannot be inspected or conflict with the configured workflow. Absence of branch protection is not itself an activation blocker.
4. When `gh` is installed or a required capability relies on it, run a representative read-only GitHub CLI request in this Launcher task. A failure observed before GitHub is reachable is inconclusive: request scoped network escalation for the same command automatically and follow the bounded connectivity recovery contract. Do not open browser authentication, substitute browser automation, or declare the credential invalid unless reachable GitHub rejects authentication. Record the exact successful path or blocking evidence.
5. Read the root AGENTS.md from authoritative origin/main and parse only the exact Roundlet authority switches defined by the skill. Fail closed on missing, malformed, duplicate, or conflicting values. Require `roundlet.enabled: true`; record every other `false` switch as a later mutation boundary rather than silently changing it or rejecting activation.
6. Add `.roundlet/` to this checkout's local `.git/info/exclude` if it is not already excluded. Never commit that exclusion or any `.roundlet` file.
7. Inspect `.roundlet/lease.json`, `.roundlet/current.md`, `.roundlet/contracts/`, GitHub traces, active codex/* branches and pull requests, local worktrees, and relevant Codex tasks/heartbeats. If any evidence suggests another live or unreconciled run, stop with STALE_OR_ACTIVE_RUN_REQUIRES_OWNER; never expire, steal, replace, or overwrite it.

If and only if all preflight checks pass:
1. Create `.roundlet/contracts/<contract-id>/` by copying the exact manifest inputs without transformation, include the canonical manifest, and read back every path, hash, and resolved role value. If an existing directory with that ID differs, stop with `CONTRACT_BUNDLE_CONFLICT`.
2. Create `.roundlet/lease.json` and `.roundlet/current.md` as the advisory recovery index defined by the skill. Use an unguessable run ID, the exact target identity, this authoritative machine/checkout, the owner identity, activation time, and the Orchestrator task identity once known. Do not add an expiry.
3. Record the same activation and active contract ID and bundle path in both advisory files. Create exactly one long-lived Orchestrator task using role `orchestrator` model and reasoning effort from the pinned bundle. Give it the exact target, checkout, run ID, owner allowlist, resolved authority, pinned configuration, contract ID and bundle path, lease/current paths, and the Orchestrator contract from that bundle. When Launcher preflight relied on `gh`, require the Orchestrator to repeat the representative read-only request in its own task under the same automatic escalation and bounded recovery rules before it answers exactly:
   ACTIVATION_READY run=<run-id> target=<owner/repository> state=IDLE
   without selecting an issue yet.
4. Wait for that exact response. If creation, preflight, or acknowledgement is incomplete or ambiguous, stop and preserve evidence; do not attach a heartbeat.
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

Read only `.roundlet/lease.json` and the minimal contract commit records needed to resolve the effective active bundle, verify that bundle completely, then read its `SKILL.md` and every required reference before acting. Treat installed skill/configuration files only as a separately fingerprinted candidate. This prompt is explicit owner authorization to investigate and propose recovery; it is not authorization to discard, overwrite, merge, close, delete, or otherwise destroy old work.

1. Perform the normal capability, repository, configuration, authority, and identity preflight.
2. Reconcile `.roundlet/lease.json`, `.roundlet/current.md`, the named active contract bundle and manifest, all Roundlet GitHub trace comments, active pull requests, exact branch SHAs, local and remote branches, worktrees, checks, and all identifiable old Orchestrator/Worker/Supervisor tasks and heartbeats. Treat the installed skill/configuration only as a migration candidate.
3. If the old Orchestrator or heartbeat is still live or its ownership is ambiguous, stop with RECOVERY_OWNER_DECISION_REQUIRED and present exact evidence. Do not create a replacement.
4. If the old Orchestrator and heartbeat are conclusively unavailable, reconstruct the current phase from durable GitHub and Git evidence. Preserve the same run ID when identity is certain; otherwise stop for owner input.
5. If an active Worker task is unavailable, stop with WORKER_REPLACEMENT_REQUIRES_OWNER. Do not silently replace it.
6. Create exactly one replacement Orchestrator using the active pinned bundle's configured model and effort. Give it the reconstructed state, evidence, task identities, branch/worktree, candidate SHA, review epoch/round, current Supervisor attempt/profile when applicable, and explicit instruction to acknowledge RECOVERY_READY without advancing work.
7. After that acknowledgement, disable or remove any conclusively stale heartbeat if possible, create one replacement heartbeat at configured `heartbeat.active_minutes`, bind it to the replacement Orchestrator, reconstruct the observation counters without treating stale fingerprints as proof, update the advisory files, and send one recovery tick.
8. Report every retained, replaced, or unresolved resource to the owner and archive this recovery Launcher.

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

Pause the heartbeat and make no GitHub, Git, issue, pull-request, branch, worktree, review,
or cleanup transition. Prove this run predates contract state and has no activation ID,
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
model/effort read-back, evidence digests, and timestamp. The record is valid only when every
field and referenced byte reads back. A partial record has no effect; multiple valid records
or contradictory evidence fail closed.

After the one valid record exists, resolve it as the immutable activation ID, refresh only
derived mirrors, and reply LEGACY_CONTRACT_PINNED with the run ID, task ID, source/ref,
contract ID, record path/hash, retained resources, and repository_transition:none. Keep the
heartbeat paused. Do not adopt the candidate in this turn. If exact activation identity is
not provable, create no record and reply LEGACY_CONTRACT_IDENTITY_REQUIRES_OWNER.
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

Pause the heartbeat. Resolve and read the effective old bundle, reconcile every run resource,
and prove the run is cleanly IDLE with no leaf resources. Verify task metadata shows this
same task and the exact candidate model/effort for this turn. Build and read back the new
bundle and prepared migration record. Make no GitHub or repository transition.

After all gates and a truthful checkpoint pass, reply exactly with CONTRACT_MIGRATION_READY
using mode: BETWEEN_ISSUES. Do not create committed.json, refresh mirrors, resume the
heartbeat, or make any repository transition in this preparation turn. A separate verified
commit turn performs the single commit point.
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

Retain the same run ID, Orchestrator task, heartbeat, active Worker, branch, worktree,
pull request, issue, candidate SHA, and review state. Pause the heartbeat before migration.
Read the old active bundle first. Reconcile GitHub, Git, every retained task, heartbeat,
lease/current pointers, active bundle, installed candidate, authority, and current phase.
Stop on any contradiction or uncommitted atomic mutation.

Verify task metadata proves this exact Orchestrator task is executing this turn under the
candidate model and reasoning effort; self-reported model text is insufficient. Build and
read back the new content-addressed bundle and a prepared migration record without changing
the effective contract. Verify every manifest field/path/hash and every resolved role value.
Write the truthful checkpoint, then reply exactly with the structured
CONTRACT_MIGRATION_READY acknowledgement from thread-prompts.md. Do not create
committed.json, refresh mirrors, resume the heartbeat, or make any repository transition
in this preparation turn. Keep the old bundle and every retained resource unchanged.
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
Expected candidate model/effort: <MODEL> / <EFFORT>
Expected CONTRACT_MIGRATION_READY evidence: <EXACT_ACK_ID_OR_DIGEST>

Verify task metadata, the effective old chain, paused heartbeat, retained resources, bundle,
prepared record, owner authorization, exact READY bytes/digest, and exact truthful checkpoint
bytes/digest again. Require committed.json to bind both verified digests. If any
value differs, create no committed record and report CONTRACT_MIGRATION_COMMIT_BLOCKED.

Create and read back exactly one valid committed.json as the commit point. Resolve the new
effective contract from the complete unique chain. Refresh derived lease/current mirrors,
read them back, reset the semantic baseline, and resume the same heartbeat at active_minutes.
Make no GitHub or repository transition. A pre-commit failure leaves the old contract
effective. If mirror refresh fails after the valid commit, the new contract remains effective:
pause and repair mirrors from the chain before any other transition. Reply exactly with the
CONTRACT_MIGRATION_COMMITTED structure from thread-prompts.md.
```
