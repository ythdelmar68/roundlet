# Operator guide

This is Roundlet's detailed operating contract. The Orchestrator rereads the pinned sources it needs before each mutation. GitHub and Git are authoritative; local state is an advisory recovery index.

## Contents

- [Operating envelope](#operating-envelope)
- [Configuration and capability preflight](#configuration-and-capability-preflight)
- [Repository-defined validation toolchains](#repository-defined-validation-toolchains)
- [Repository-owned external validation](#repository-owned-external-validation)
- [Optional lifecycle observation sink](#optional-lifecycle-observation-sink)
- [Task creation and immutable binding](#task-creation-and-immutable-binding)
- [Repository project/worktree topology](#repository-projectworktree-topology)
- [Advisory local state](#advisory-local-state)
- [Immutable activation contract](#immutable-activation-contract)
- [Observation and heartbeat cadence](#observation-and-heartbeat-cadence)
- [Backlog classification](#backlog-classification)
- [Dependencies and ranking](#dependencies-and-ranking)
- [State machine and one-transition ticks](#state-machine-and-one-transition-ticks)
- [Claim and implementation](#claim-and-implementation)
- [GitHub trace](#github-trace)
- [Review epochs and rounds](#review-epochs-and-rounds)
- [Owner input](#owner-input)
- [Repository authority block](#repository-authority-block)
- [Merge gates](#merge-gates)
- [Leaf closure](#leaf-closure)
- [Ordered cleanup](#ordered-cleanup)
- [Active issue closed, ignored, or withdrawn](#active-issue-closed-ignored-or-withdrawn)
- [Pause, resume, stop, and skill updates](#pause-resume-stop-and-skill-updates)
- [Copyable owner commands](#copyable-owner-commands)
- [Recovery](#recovery)

## Operating envelope

Roundlet operates only inside this envelope:

- one GitHub target repository;
- one authoritative checkout on one authoritative machine;
- one long-lived Orchestrator;
- one recurring phase-aware heartbeat attached to that Orchestrator;
- zero or one active leaf;
- one persistent Worker for that leaf;
- one fresh read-only Supervisor for each review attempt;
- one isolated worktree and one `codex/` branch for that leaf;
- one Orchestrator as the only GitHub mutator;
- zero or one leaf-selected repository-owned lifecycle observation sink invoked only by that Orchestrator;
- one immutable activation-time contract bundle.

Do not start a second run for the same target from another task, clone, or machine. A local lease is advisory and cannot prevent split-brain. Activation preflight, GitHub traces, exact task identities, and refusal to take over reduce risk; they do not create distributed locking.

## Configuration and capability preflight

Read `roundlet-config.json` exactly. Do not default, coerce, or silently fall back.

Before activation, prove:

- every configured model/reasoning-effort pair is selectable;
- Supervisor profile names are unique and their ordered count equals `max_supervisor_attempts_per_round`;
- role tasks can be created, addressed, waited on, inspected, resumed, and archived;
- immutable creator-side task metadata exposes exact task ID, configured model/effort, project/workspace, canonical CWD, and any available stable host/environment identity, while the creator can identify its own source task and requested role;
- one recurring heartbeat can be created, inspected, updated through every configured interval, paused/resumed, and removed;
- Git and the authoritative checkout are usable;
- GitHub identity, repository identity, issues, comments, formal issue relationships, branches, pull requests, reviews, checks, mergeability, and merge operations can be inspected;
- the Orchestrator can perform repository-authorized GitHub mutations;
- the contract file set can be materialized byte-for-byte to a content-addressed bundle and read back: from verified commit objects for `git`, or from the resolved installed directory for `installed-tree`;
- the external creator can resolve the installed Roundlet skill used for new activation to one canonical absolute root and place it in the populated Launcher prompt; the Launcher can read the exact required file set from that root without a role-side skill-catalog entry, alternative-root scan, or substitution;
- root `AGENTS.md` on `origin/main` contains exactly one valid Roundlet authority block;
- when root instructions explicitly declare repository-owned external validation, every referenced contract resolves to one exact authoritative path and byte identity and every declared leaf route uses only `none`, `toolbox`, or `toolbox+disposable-target`;
- when root instructions declare an optional lifecycle observation sink, every referenced contract resolves to one exact authoritative path and byte identity and exposes deterministic prepare, append/read-back, seal/verify, closed-event, and retention capabilities without invocation during activation;
- the configured merge method is supported;
- the checkout is clean and `HEAD == main == origin/main`;
- no other Roundlet run or unreconciled resource may own the target;
- required branch rules and checks can be determined well enough to fail closed at merge time.
- when root instructions declare a validation-toolchain contract, its named documentation, lock, resolver, cache boundary, bootstrap constraint, and receipt verification route are readable and internally consistent; an available bootstrap interpreter satisfies the repository's stated version without becoming validation evidence.

When a role needs `gh`:

1. Treat a failure before GitHub is reachable as inconclusive connectivity evidence.
2. Request the narrowest scoped network approval for the same command. Prefer a read-only request while proving identity.
3. Retry a transient DNS, timeout, or transport failure once in the same turn and once at the next automatic opportunity.
4. Continue automatically after success. Only reachable GitHub rejection proves authentication failure.
5. Never open browser authentication or substitute browser automation without explicit owner direction.

The skill requires requesting approval; it cannot grant or assume it. Enter `NEEDS_OWNER_INPUT` only after explicit denial, unavailable approval machinery, confirmed authentication rejection, or exhausted bounded connectivity recovery.

## Repository-defined validation toolchains

This section applies only when root repository instructions explicitly name a validation-toolchain document or equivalent contract. Do not infer a contract from ordinary dependency files, and do not impose one on another repository.

At activation, read the contract from authoritative `origin/main`, prove that the named files and capability route exist, and record a bounded contract summary for the Orchestrator. Do not provision merely because a run starts. The host may discover any available bootstrap interpreter that satisfies the repository's stated bootstrap version. Record its command and observed version internally; it only runs the resolver and cannot satisfy build, test, packaging, review, or merge evidence.

Before each affected Worker validation:

1. Reread the candidate's root instructions and named toolchain contract from the assigned worktree. Bind the resolver and lock to the exact candidate SHA.
2. Use the contract's explicit shared cache root. For a repository-local shared-cache contract, this is `<authoritative-checkout>/.roundlet/validation-tools`, not a cache below the removable issue worktree.
3. Discover a bootstrap interpreter satisfying the declared version and invoke the candidate resolver with the exact shared cache-root argument. Never install packages into the bootstrap interpreter.
4. If the exact lock/platform cache is absent, invoke the contract's ordinary provision operation. This is the only automatic cache creation path.
5. If a complete receipt exists, verify and reuse it. If the cache or receipt is incomplete, malformed, stale, moved, wrong-platform, wrong-lock, digest-drifted, or fails executable/version read-back, stop without fallback or automatic rebuild. An explicit destructive rebuild remains a separate owner-directed recovery action.
6. Run every affected build, test, packaging, and smoke command through the receipt-bound execution route. Direct use of bootstrap, user, system, or `PATH`-discovered build tools is not evidence.
7. Return the public-safe lock digest, lock/platform cache key, receipt status, platform identity, and command results to the Orchestrator. The Orchestrator uses the envelope's exact local cache path only for private read-back. Handoffs and GitHub trace must omit private paths, raw receipts, and generated artifacts.

The Worker may affect the shared validation cache only by invoking the repository-defined resolver with the exact cache root. It must not edit cache contents directly or use this exception for authoritative source changes. The Orchestrator independently verifies the candidate/lock/receipt/result binding before accepting or publishing validation. Candidate movement or a relevant contract change requires fresh verification.

The shared validation cache is host-owned reusable repository state. It is not run-owned advisory state, is not part of the immutable Roundlet activation bundle, and survives ordinary issue cleanup, stop-after-current, and worktree removal. A valid retained cache does not indicate a stale Roundlet run.

## Repository-owned external validation

This section applies only when authoritative root instructions explicitly declare an external-validation contract. Roundlet supplies generic orchestration; the target repository owns concrete toolbox, disposable-target, commit, action, credential, evidence, rollback, and read-back details.

Each actionable leaf declares exactly one route:

- `none`: no external toolbox or target;
- `toolbox`: use the exact selected repository-owned execution toolbox for read-only validation;
- `toolbox+disposable-target`: use that toolbox plus one exact repository-owned disposable target for read-only observation or separately authorized mutation.

Before provisioning a selected leaf:

1. Read root `AGENTS.md` from authoritative `origin/main` and resolve every referenced operations contract or repository-owned skill used by the route. Bind each path and exact Git blob identity; a candidate-authored copy may narrow but never widen authority.
2. Read the live leaf and canonical scheduling context. Bind the route, gate/evidence class, base, future candidate-binding rule, concrete public repositories, reviewed source commits, one repository-owned executor contract and exact entrypoint identity, target baseline commit, action allowlist, rollback/kill-switch procedure, semantic read-back, evidence-time field, and public-safe projection. Reject floating refs or conflicting declarations.
3. For any external observation, require `allow_external_validation_read_only: true`. For a target mutation, also require `allow_external_validation_disposable_target_mutation: true` and prove that the exact operation is allowlisted for the exact disposable target. Neither switch authorizes mutation of the repository under development.
4. Record a bounded selection binding in advisory state, then include its allowed projection in the ordinary public-safe selection trace only after branch/worktree/Worker provisioning succeeds. Credentials, raw payloads, private paths, logs, and owner-private reasoning remain excluded.

When these bindings and standing switches match, proceed without requesting a new owner approval for each attempt, commit, or replay. Enter `NEEDS_OWNER_INPUT` only for confirmed credential/login failure, repository or commit identity conflict, an operation outside the authoritative allowlist, unavailable required rollback, or observed/ambiguous partial mutation/read-back. Missing authority enters `REPOSITORY_AUTHORITY_REQUIRED`. Never substitute another toolbox, target, credential, action, or branch head.

Immediately before each invocation, resolve and bind the current full candidate SHA plus the already-selected toolbox and target commits. Candidate movement invalidates prior gate evidence and requires a new evidence run under the same standing route; it does not itself request owner approval or start a review epoch.

### Generic executor lifecycle

Roundlet never constructs a repository-specific runner or understands its product profile, provider, Recorder, comparator, storage, or receipt schema. The repository-owned contract supplies one exact executor whose dry validation and live execution share the same parser, entrypoint, plan, component identities, candidate, case, evidence time, and read-back path.

Bind the executor's declared readiness and result schema identities from that exact contract and typed preflight receipts. Do not hard-code a target schema or copy an expected schema from an earlier candidate, executor commit, or binding. A schema mismatch before `ARMED` leaves external action count zero, preserves the failed namespace as diagnostic evidence, and requires a wholly fresh binding derived from the current executor. It is never repaired by changing an assertion inside the already-created namespace.

Track only these generic states:

1. `UNPREPARED`: no executable binding exists; external action count is zero.
2. `PREFLIGHT_READY`: the exact executor has returned a typed, public-safe, unconsumed readiness receipt for the current candidate with external action and mutation counts zero.
3. `ARMED`: the readiness trace is semantically read back and the same one-shot plan is eligible for one invocation.
4. `EXECUTED`: that plan was consumed once and returned one typed result; never retry or substitute unless the repository contract itself returned a bounded, still-unconsumed disposition.
5. `VERIFIED`: repository-defined projection, retention, and semantic read-back all match the original plan.
6. `STALE`: candidate, executor, toolbox, target, case, component, evidence time, plan, or authority identity moved. Preserve prior evidence and build a wholly fresh binding; never stitch it to a new candidate.

If the repository-owned executor exposes epoch, round, attempt, session, or turn values, retain them only as an opaque `external_validation_sequence`. They are not Roundlet Supervisor accounting. Keep `external_validation_sequence` and `external_validation_schema_binding` distinct from the formal `review_epoch`, `review_round`, `review_mode`, and `supervisor_attempt` tuple in advisory state, prompts, trace, recovery, and merge-gate reconciliation. Never copy values between them.

An external-action-free preflight defect stays in implementation and returns to the same Worker or repository-owned toolbox correction. It is not `NEEDS_OWNER_INPUT`, does not consume a Supervisor attempt or review round, and does not publish `VALIDATION_READY` or repeated LIVE trace. Publish one readiness event only at `PREFLIGHT_READY`, and one result event only after `VERIFIED` (or one durable terminal blocked result after a genuinely armed invocation). Use a structured connector when available; a CLI fallback must use an exact body file, never shell-interpolated Markdown, and must read the event marker and required fields back semantically.

Repository standing authority and host command execution are separate. A denial before the selected command reaches GitHub, a provider, or a target is an execution-routing result, not proof that repository authority or credentials are missing. Retry only the same exact operation through an already permitted low-privilege host boundary; never bypass a platform approval or broaden the command.

For historical replay, read the immutable capture time from the evidence bundle using the repository-declared field and pass that value to the repository comparator. Wall-clock execution time is valid only for a contract that explicitly describes a current live decision; it must never replace historical evidence time. Bind the field name, captured value, bundle digest, and comparison result in private state, and publish only their allowed public-safe projection.

## Optional lifecycle observation sink

This contract is opt-in. It applies only when authoritative root instructions reference one repository-owned sink contract and the selected leaf declares that ephemeral lifecycle evidence is required. Otherwise bind `NOT_SELECTED`: do not resolve a window, create storage, call a producer, add a prompt field beyond `not-applicable`, or change any lifecycle transition.

Roundlet treats the sink implementation, command names, filesystem layout, and seal/retention schemas as opaque. The repository-owned contract must expose one exact prepare/arm path, one append/read-back path, and one seal/verify path whose identities can be pinned to authoritative instructions. Roundlet does not import that implementation and does not understand a product profile, phase, gate, comparator, target fixture, or semantic decision.

Before the first transition named by the leaf's `arm before` boundary:

1. Bind the authoritative contract path/blob, entrypoint identities, producer, store, closed event schema, opaque window, exact full candidate SHA, capture-plan/evidence-time identity, and formal `review_epoch`, `review_round`, and `review_mode`. Resolve any repository-supplied identity projection without inventing a value.
2. Invoke the exact prepare path once and require a typed path-free `ARMED` receipt with zero provider, GitHub, target, and product mutation. Semantically read back every required binding. A construction, import, path, schema, or external-action-free readiness defect returns to implementation and is not owner input.
3. Create no role task selected for that observation window, and advance no selected transition, until arming succeeds. Unobserved implementation work may proceed when the leaf's arm-before boundary is later. If a short-lived selected event already occurred while unarmed, that window can never qualify; preserve it as `STALE` and repeat the live sequence only in a genuinely fresh bound window.

Only the Orchestrator invokes the sink. Worker and Supervisor tasks return ordinary structured handoffs/results and never receive credentials, store access, or mutation authority from the sink. At the transition boundary, the Orchestrator supplies only this closed generic fact set through the repository contract:

- opaque repository, window, task, attempt, predecessor, and bounded public-safe artifact identities;
- exact candidate SHA, immutable event time, role (`worker` or `supervisor`), and append sequence;
- formal review epoch, round, mode, and within-round attempt;
- one distinct transition: attempt started/completed, result accepted/unaccepted, candidate moved, or formal round advanced;
- one typed disposition such as pending, cancelled, invalid context, pass, findings, failed, accepted, unaccepted, or stale; and
- accepted-result Boolean plus an optional exact successor candidate for candidate movement.

Raw provider/model input or output, exception prose, credentials, tokens, private paths, task transcripts, hidden reasoning, owner reasoning, UI text, and product-only fields are prohibited. The sink receipt is evidence, not a Roundlet verdict: it cannot accept a Supervisor result, classify prose, consume a formal round, authorize a mutation, or replace GitHub trace.

After each selected event, require append success and semantic receipt read-back before the corresponding Roundlet transition advances. Record only the bounded plan/window identity, sequence, event/head digest, and receipt status in advisory state. The exact candidate, review tuple, sink, schema, producer, store, capture plan, evidence time, predecessor, or receipt moving makes the window `STALE`; never stitch chains or retry with changed bytes under the same sequence.

When the leaf's declared window ends, invoke the exact seal path and independently verify the retained chain, manifest, content identity, evidence time, retention receipt, and zero unauthorized mutation. A selected evidence gate can proceed only in `VERIFIED`. Preserve sealed ledgers beyond task/worktree cleanup. Preserve partial or conflicting windows as non-qualifying diagnostics and open a new live window; never backfill, infer, normalize, or fabricate missing history.

## Task creation and immutable binding

For every Launcher, Orchestrator, Worker, and Supervisor:

1. Record the creator/source task, requested role, exact configured model and effort, and intended task route. For a repository role also record the uniquely resolved saved-project identity, canonical repository path, Git common directory, existing starting ref, and expected full starting SHA. A project/worktree route's actual CWD is creator-resolved after asynchronous creation; it is not a caller-chosen path.
2. Create exactly one role task with only the `ROUNDLET_ROLE_METADATA_REPORT_REQUEST` from the role contract as its first prompt. That metadata-only turn performs no role, repository, GitHub, Git, heartbeat, or filesystem action.
3. Treat any `ROUNDLET_ROLE_METADATA_REPORT` or other returned rendering as advisory. It may be absent, one line, reordered, noncanonical, or omit a self-reported task ID.
4. Wait for task creation to finish, then independently read immutable creator-side metadata before the first populated role prompt. Construct a proposed `CREATOR_TASK_BINDING_ATTESTATION` containing the role task ID, creator/source task, requested role, configured model/effort, route, requested saved project, actual project/workspace and canonical CWD, Git common directory and starting ref/SHA where applicable, and available stable host/environment identity.
5. If the role report explicitly contradicts the proposed attestation, perform exactly one bounded creator-side immutable re-read. If the authoritative values remain complete and match the request, keep the same proposed attestation and treat the report as untrusted contradictory prose. If authoritative metadata is missing, stale, malformed, mismatched, changes across the re-read, or otherwise conflicts, archive the task and fail closed before role work.
6. Require every authoritative field to match the creation request, then record exactly one creator attestation. Only that validated attestation authorizes the first populated role prompt.
7. For a top-level new-activation or recovery Launcher, copy the complete stable attestation into the fixed creator-authority block of the populated Launcher prompt; that Launcher consumes the block and does not perform role-side immutable self-metadata discovery. For roles created by a Launcher or Orchestrator, copy the stable attestation into the role envelope and advisory state where applicable. Recovery and restart normally reuse it. Only contradictory immutable creator-side evidence triggers exactly one bounded re-read against the recorded attestation; an unchanged complete match preserves it, while an unresolved difference fails closed. Neither path creates a second task, second attestation, duplicate dispatch, or duplicate availability event.

Role text never satisfies, alters, or invalidates binding by itself. Missing, short, reordered, differently rendered, title-like, summary-like, or task-ID-free role output proceeds normally when creator read-back matches. Do not repeat task discovery on every turn. Later turns remain bound to the one verified attestation and carry current issue/phase/SHA context.

An `invalid-binding` disposition or public availability trace may name only a creator-evidence class: `CREATOR_METADATA_MISSING`, `CREATOR_METADATA_STALE`, `CREATOR_METADATA_MALFORMED`, `CREATOR_METADATA_MISMATCH`, or `CREATOR_METADATA_CONFLICT_AFTER_REREAD`. Never cite role-report formatting, omitted fields, prose, title, summary, or missing self-reported task ID as the reason. A valid creator attestation plus a noncanonical role report does not consume a Supervisor attempt, advance the attempt profile, consume a review round, or publish a discard trace.

## Repository project/worktree topology

Use this topology for every Git-repository Worker and Supervisor on every supported host:

1. Resolve the target by canonical authoritative-checkout path against the live saved-project list. Require exactly one matching writable Git project. Canonicalize `git rev-parse --git-common-dir` to an absolute path relative to the checkout that produced it before comparison. A missing, duplicate, path-mismatched, or non-Git project blocks provisioning; never guess by display name.
2. Create the candidate branch/ref locally from the exact base before requesting a task; the task route accepts an existing ref and does not create Roundlet's candidate ref.
3. Create the task asynchronously with that saved project, the App-managed worktree environment, and the existing starting ref. Wait for readiness and immutable creator metadata before sending role work.
4. Verify that the actual CWD is the task's App-managed repository worktree, is not the authoritative checkout, and does not equal any retained tombstone path. Require `git rev-parse --show-toplevel` to equal that CWD, the canonical absolute `git rev-parse --git-common-dir` to equal the authoritative repository's common Git directory, `HEAD` to equal the expected full SHA, the checkout to be clean, and `git symbolic-ref -q HEAD` to report detached. Detached `HEAD` is mandatory so only the Orchestrator advances the candidate ref.
5. Reuse the same Worker task and worktree for every repair, main integration, final repair, and cleanup preflight. Never create a replacement worktree for a reachable Worker.
6. Before each Supervisor creation, update an existing local candidate ref to the exact verified candidate SHA. Create a fresh read-only project/worktree task from that ref and verify its independent detached worktree at the same SHA. Worker and Supervisor never share a physical directory.
7. A task record may omit a project ID even though the creator requested a uniquely resolved saved project. Do not invent the missing field. Bind the creator's saved-project request together with actual CWD, Git common-directory, ref, and SHA read-back.
8. Before every project/worktree task dispatch, compare its actual CWD with every unresolved route-probe or run-local task-worktree tombstone. Equality is `CREATOR_METADATA_CONFLICT_AFTER_REREAD` and blocks dispatch; a former tombstone may be retired only after a fresh read proves its physical path absent.

Projectless task creation is not a repository fallback. It may be used only for a non-repository role or when a separately verified capability guarantees a caller-supplied canonical CWD. A `directoryName` or similar output-folder hint is not evidence of task CWD.

On native Windows, Workers additionally use direct normal-sandbox `apply_patch` for every source edit. Do not wrap it in PowerShell, a pipeline, a here-string/here-document, a batch file, or elevation. If the linked-worktree index or `index.lock` resolves outside the Worker's normal writable roots, request only a narrow approval for the exact Git metadata operation; source edits stay in the normal sandbox.

## Advisory local state

Add `.roundlet/` only to the authoritative checkout's local `.git/info/exclude`. Never commit the exclusion or a `.roundlet` file.

Keep:

- `.roundlet/lease.json`: stable run, target, checkout, machine, owner, activation, contract, Orchestrator, and heartbeat identities;
- `.roundlet/current.md`: concise phase and recovery pointers;
- `.roundlet/contracts/<contract-id>/`: the one read-only activation snapshot.

When the repository declares it, `.roundlet/validation-tools/` is a separate host-owned reusable cache governed by the repository validation-toolchain contract. Do not put it in lease/current state, hash it into the activation bundle, treat it as run ownership, or remove it during ordinary Roundlet cleanup.

The lease has no expiry:

```json
{
  "run_id": "unguessable-stable-id",
  "target": "owner/repository",
  "authoritative_checkout": "/absolute/path",
  "authoritative_machine": "stable-machine-identity",
  "owner": "allowlisted-github-login",
  "activated_at": "ISO-8601 timestamp",
  "contract_id": "64-lowercase-hex",
  "contract_bundle": "/absolute/path/.roundlet/contracts/<contract-id>",
  "orchestrator_task": "opaque-task-id",
  "heartbeat": "opaque-heartbeat-id"
}
```

`current.md` records only bounded recovery facts: run/contract IDs, bundle, phase, issue and umbrella numbers/URLs, pull request, Worker/current Supervisor, each active role's creator binding attestation fields, task route, requested saved-project identity, actual worktree/CWD, canonical Git common directory, starting ref/SHA, verified activation route-probe receipt/retained-ledger identity, base and candidate full SHAs, the run-local task-worktree cleanup-ledger identity, repository validation-toolchain summary/cache root and last public-safe lock/receipt status when applicable, selected external-validation route plus authoritative instruction/skill/target/action identities, declared readiness/result schema identities, opaque external-validation sequence, and historical evidence-time binding when applicable, optional lifecycle-sink contract/state plus plan/window/sequence/head/receipt identities, the separate formal review epoch/round/mode/attempt/profile, last verified Supervisor-result event, last verified Worker-repair-handoff event, last durable event, blocking condition, heartbeat interval, last full reconciliation, and bounded observation state. Never alias or copy values between an external-validation or lifecycle-sink sequence and the formal review tuple. Never store the advisory role report, credential, raw external payload, raw sink event, or raw receipt. Do not append transcripts, issue bodies, raw comments, diffs, logs, or reasoning.

Before each tick or mutation, reconcile both files with the bundle, GitHub, Git, tasks, and heartbeat. Prefer live authoritative evidence. Conflicts enter `NEEDS_OWNER_INPUT` with reason `STATE_RECONCILIATION_CONFLICT`; never guess or overwrite them.

## Immutable activation contract

The exact bundle file set is:

- `SKILL.md`
- `agents/openai.yaml`
- `references/launcher.md`
- `references/operator-guide.md`
- `references/repository-authority.md`
- `references/roundlet-config.json`
- `references/thread-prompts.md`

Paths are unique POSIX relative paths without `..`, NUL, CR, or LF and are sorted by unsigned UTF-8 bytes. Hash each file's exact stored bytes without newline normalization.

For a new activation, preflight binds the creator-supplied canonical installed root, this exact seven-path set, and every per-file byte identity before repository access. Immediately before materialization and again before finalizing the contract path, require the same root, path set, and identity map. Each materialized bundle file must equal its preflight identity. This applies to exact verified blob identities for `git` and exact installed bytes for `installed-tree`; same-path drift or a mixed-generation bundle fails closed without a finalized contract or advisory state.

Compute `tree_digest` from ASCII `roundlet-tree/v1\n`, followed for each sorted file by its UTF-8 path, byte `0x00`, 64 lowercase ASCII SHA-256 hex bytes, and byte `0x0a`. Store it as `sha256:<lowercase-hex>`.

The hash-input manifest has exactly:

```json
{
  "contract_schema": "roundlet-contract/v1",
  "contract_version": "roundlet-contract/v1@<source-ref>",
  "files": [
    {"path": "<relative-path>", "sha256": "<64-lowercase-hex>"}
  ],
  "resolved_config": {},
  "source": {"kind": "<git|installed-tree>", "locator": "<string>", "ref": "<string>"},
  "tree_digest": "sha256:<64-lowercase-hex>"
}
```

`resolved_config` is the complete parsed JSON configuration. For `git`, `locator` is canonical `owner/repository` and `ref` is the verified lowercase 40-character OID matching every bundled byte. Materialize and hash Git-sourced files directly from that commit object, never from working-tree bytes; checkout filters, attributes, or line-ending conversion must not affect the bundle. For `installed-tree`, `locator` is the resolved absolute skill directory and `ref` is the exact tree digest. `contract_version` appends that ref.

Serialize with RFC 8785 JCS, no BOM, trailing newline, or floats. The contract ID is SHA-256 of these canonical hash-input bytes. Add only top-level `"contract_id":"<64-lowercase-hex>"` and reserialize. Materialize the exact files and manifest in one new unfinalized staging path below `.roundlet/contracts/`, apply the post-materialization root/path/identity checks above, then atomically finalize it as `.roundlet/contracts/<contract-id>/`. Reuse an existing final path only after exact equality; different bytes are `CONTRACT_BUNDLE_CONFLICT`. Read back every finalized path, byte hash, manifest field, tree digest, role profile, and ID. On failure remove only the exact validated unfinalized staging path and create no lease/current state.

The activation record is immutable for the run. Every role, heartbeat, owner command, and recovery reads only that bundle. An installed change is reported separately but never enters the run. Updating Roundlet requires a safe stop, complete cleanup, installed-skill update, and a new run ID/contract.

## Observation and heartbeat cadence

Use two tiers:

- A lightweight observation asks only whether the last fully reconciled state may still be current.
- Full reconciliation reads all live semantic sources needed for the phase.

A lightweight observation may include `origin/main`, open-issue count/latest update watermark, active issue/PR state and head/check watermarks, active worktree status digest, role task state/cursor, heartbeat identity/interval, watched owner-comment watermark, and direct Orchestrator input cursor. It never authorizes selection, claim, review acceptance, ready conversion, merge, close, cleanup, scope change, or another mutation.

Perform full reconciliation in the same tick when:

- any observed value changes;
- a field is missing, malformed, incomplete, or overflowed;
- the phase is action-ready;
- a role or check becomes terminal;
- owner input arrives;
- installed/authority/contract identity changes;
- `max_lightweight_ticks_before_full_reconciliation` is reached.

After full reconciliation, replace the bounded baseline in `current.md`. Keep only IDs, counts, cursors, full SHAs, timestamps, paths, completeness flags, and digests.

Use `active_minutes` while work is active or observation is inconclusive. After consecutive unchanged IDLE observations, advance through `idle_noop_backoff_minutes`. During unchanged owner-input waits, advance through `owner_input_noop_backoff_minutes`. Update the same heartbeat, verify the new interval, and reset to active on any change or direct owner instruction. `PAUSED` has no recurring polling.

## Backlog classification

Classify every open issue on each full scheduling reconciliation:

- `UMBRELLA`: formal parent/scheduling container; never an implementation candidate.
- `LEAF_READY`: actionable leaf with satisfied exact dependencies and no blocker.
- `STANDALONE_READY`: actionable non-umbrella issue with no formal parent and no blocker.
- `BLOCKED_DEPENDENCY`: an exact leaf/standalone dependency is incomplete.
- `BLOCKED_SCHEDULING`: canonical scheduling context says not yet runnable.
- `NON_ACTIONABLE`: discussion, tracking, support, or insufficient implementation scope.
- `IGNORED`: `roundlet:ignore` or an equivalent repository rule.
- `ALREADY_OWNED`: another live branch/PR/run owns it.

Read all open issues, formal parent/sub-issue relationships, blocking relationships, labels, bodies, and relevant comments. An issue is an umbrella when formal children or canonical scheduling context proves it. Do not infer that every issue mentioning another issue is a child.

Umbrella state is scheduling context only. Never use an umbrella's open, closed, or completed state as a dependency. Runnable dependencies are exact leaf or standalone issue numbers in the live scheduling context.

## Dependencies and ranking

For each ready candidate, build a compact evidence record:

- issue number and URL;
- leaf or standalone classification;
- priority from canonical live context;
- exact dependency list and completion evidence;
- formal parent and relevant Canonical scheduling note;
- external-validation route and exact authoritative contract/standing-authority readiness, or explicit `none`;
- lifecycle observation requirement plus exact authoritative sink-contract readiness, or explicit `NOT_SELECTED`;
- blocker/owner/active-resource evidence;
- readiness reason.

Exclude blocked and ambiguous candidates. Rank ready candidates by:

1. explicit canonical wave/order;
2. priority `P0`, `P1`, `P2`, then unprioritized;
3. blocker-removal value stated in live context;
4. oldest issue number as deterministic tie-breaker.

Selection is read-only until branch/worktree/Worker provisioning verifies successfully.

## State machine and one-transition ticks

Use these phases as recovery labels, not an executable runtime:

`ACTIVATING`, `IDLE`, `ISSUE_PROVISIONING`, `ISSUE_SELECTED`, `IMPLEMENTING`, `DRAFT_PR`, `REVIEWING`, `WAITING_CHECKS`, `MERGE_READY`, `MERGED`, `CLEANING`, `CLEANUP_BLOCKED`, `NEEDS_OWNER_INPUT`, `REPOSITORY_AUTHORITY_REQUIRED`, `OWNER_ABORT_DECISION_REQUIRED`, `PAUSED`, `STOP_AFTER_CURRENT`, and `STOPPED`.

One heartbeat tick may perform at most one externally meaningful transition. Bounded read-back, trace publication that belongs to that transition, and heartbeat interval bookkeeping are part of the transition. Long role work can span ticks; unchanged running work is a no-op.

## Claim and implementation

After selecting one ready leaf:

1. Enter `ISSUE_PROVISIONING` without posting selection.
2. Resolve and verify any repository-owned external-validation route, optional lifecycle-sink contract, standing authority, and the one saved local project matching the authoritative repository; then create one unpublished local `codex/` candidate ref from exact `origin/main`.
3. Create one persistent Worker asynchronously through the saved project's App-managed worktree route using that existing ref.
4. After task readiness, independently verify detached `HEAD`, clean base SHA, candidate ref, App worktree registration/path/status, canonical Git common directory, Worker task/profile/route/requested-project/actual-CWD binding, non-reuse of every retained tombstone path, repository instructions, and absence of conflicting resources.
5. On any provisioning failure, remove only proven empty/unpublished resources, verify cleanup, and return to `IDLE`; otherwise stop in `CLEANUP_BLOCKED`.
6. Only after successful read-back, publish the selection trace to the leaf issue, read it back there, enter `ISSUE_SELECTED`, and send the initial implementation prompt to that same Worker.

The Worker may edit only its assigned worktree and issue scope. It must reread root instructions, use conventional branch/commit rules, preserve unrelated user work, validate proportionally, and return a structured handoff.

After a valid initial handoff:

1. Independently verify before/after SHAs, diff, status, tests, issue scope, and any repository-required candidate/lock/receipt validation binding.
2. On native Windows, verify direct normal-sandbox `apply_patch` for source edits and reject contradictory routing evidence.
3. Require the detached Worker checkout and local candidate ref still at the expected prior SHA. Atomically update that ref from the expected prior SHA to the verified Worker candidate, then push that exact ref/candidate without force and read back the remote head. The detached Worker checkout is never treated as the authoritative ref by itself.
4. Append the initial Worker handoff to the leaf issue and read it back from that issue.
5. Create a draft pull request linking the umbrella non-closing when present and including `Closes #<leaf>` for the active leaf only.
6. Append the draft-PR creation trace to the leaf issue, read it back from that issue, update advisory state, and then use the pull request's top-level Conversation for all later candidate/review/repair/validation evidence.

## GitHub trace

Only the Orchestrator publishes Roundlet trace. Worker and Supervisor results are proposals until independently verified.

### Canonical destination matrix

This matrix is authoritative. **PR Conversation** means a top-level conversation comment on the pull request number, not a submitted review or inline review thread. **PR** means the pull request artifact: any accompanying curated trace goes to its top-level Conversation, while merge-gate inputs and the merge result are read back from pull-request metadata.

| Event | Canonical destination |
| --- | --- |
| Issue selection, scope/owner decision, initial Worker handoff | Issue |
| Draft pull-request creation | Issue |
| After the pull request exists: Worker repair handoff, candidate push/read-back, tests, checks, CI, and Shadow evidence | PR Conversation |
| Supervisor availability, FINDINGS, PASS, and terminal review evidence | PR Conversation |
| Merge-gate decision and merge result | PR |
| Leaf closure, cleanup, `STOPPED`, `NEEDS_OWNER_INPUT`, and abort decision | Issue |

Before each publication, classify the event and populate both the leaf issue number and pull-request number (or explicit `none` before creation). For an Issue or PR Conversation row, select that exact comment surface and number. For a PR row, bind the decision/result to the pull-request number and live metadata; if a curated comment accompanies it, select that same number's PR Conversation separately. Read back the authoritative metadata and any event marker from the same selected surfaces before transitioning. A write to the wrong surface or a same-surface read-back failure is not durable completion.

Every trace comment starts with:

```html
<!-- roundlet:event=<event-id>;run=<run-id>;epoch=<number>;round=<number-or-0>;candidate=<full-sha-or-none> -->
```

Use stable event IDs. Before writing, search both the leaf issue and the pull request's top-level Conversation, when present, for the same event marker. This cross-surface lookup is required before retrying an ambiguous transport result or when pull-request creation may have changed the canonical target; never duplicate an identical event merely because the workflow crossed surfaces. After target selection, write and read back only on the canonical surface.

Never edit, delete, move, or bulk-repost a historical trace to hide or repair a routing error. Preserve the original comment. When recovery needs to make the durable sequence clear, add at most one bounded pointer on the current canonical surface naming the prior event marker and URL without copying raw artifacts or the full prior comment.

Record selection/ranking, Worker handoffs, draft PR creation, verified external-validation readiness/result, invalid Supervisor availability attempts, valid Supervisor results, repairs, terminal review, owner/authority/abort decisions, merge, leaf closure, and cleanup. Keep provider-free executor construction, lifecycle-sink arm/append traffic, and preflight corrections local unless they change the candidate or become one durable blocker; publish at most the repository-allowed arm/seal identities as part of the existing validation readiness/result events. Summarize files, tests, findings/dispositions, SHAs, and risks. Never publish hidden reasoning, credentials, private artifacts, raw sink events, raw task transcripts, or unbounded logs.

## Review epochs and rounds

Start epoch 1, round 1, bound to the exact pushed candidate. Preserve the same epoch, accepted-round count, and next mode across pause, resume, same-task continuation, and authorized recovery when the immutable activation contract, leaf scope, acceptance criteria, and candidate review basis are unchanged. Satisfying or refreshing an already-declared standing external-validation route is not a scope change. Ordinary repairs stay in the epoch.

Formal review accounting is independent of repository-owned external-validation and lifecycle-sink accounting. Only an accepted schema-valid Supervisor result at the exact formal tuple can consume a Roundlet review round. An external executor or sink's epoch/round/attempt, even when numerically identical, never dispatches a Supervisor, satisfies a review result, or enters the merge gate. If a Supervisor was created with a stale external or sink tuple, stop or archive it without accepting or tracing its verdict; interrupt it first when it is still running. Preserve prior accepted results, record the misbound task only as unaccepted local diagnostic evidence, and create one fresh Supervisor at the mechanically correct tuple.

An allowlisted owner change that materially changes scope or acceptance criteria starts a new epoch at round 1 COMPLETE. Main integration also starts a new COMPLETE epoch under the merge-gate rule because the candidate review basis changes. Never start a new epoch merely because the Orchestrator/heartbeat restarts, an unchanged gate is retried, a credential is refreshed, or a previously permitted repository-owned route is mechanically rebound to the same identities.

For each round:

1. Hold epoch, round, mode, and candidate SHA fixed.
2. Select the configured attempt profile at the exact one-based position.
3. Update the existing local candidate ref to the exact candidate SHA, then create one fresh Supervisor through the same saved project's App-managed worktree route with that exact profile/ref. Independently verify its distinct detached worktree, canonical repository common directory, `HEAD`, non-tombstone path, and creator binding attestation. Do not interpret its advisory role report as binding evidence.
4. Before dispatch, record an independent read-only snapshot of that exact worktree: task/CWD/registration identity, detached `HEAD`, full candidate SHA, porcelain-v2 tracked/untracked/index status, and the exact candidate ref OID. Require clean status. Do not digest unrelated refs from the shared Git common directory.
5. Send the read-only review prompt and require a structured result bound to the attempt/profile/epoch/round/mode/SHA.
6. Before accepting any result, repeat the independent snapshot and require exact equality. Any HEAD, tracked/untracked/index, exact-candidate-ref, registration, common-directory, or CWD drift is `INVALID_CONTEXT`; the Supervisor's `read_only: true` field cannot override it. Unrelated shared refs are reconciled independently and never attributed to the Supervisor by this snapshot.
7. If valid, publish it to the PR Conversation and read it back there, archive the Supervisor, perform the mandatory per-task cleanup read-back below, and follow PASS or FINDINGS.
8. If invalid/failed/cancelled/inaccessible/malformed/wrong-context/wrong-SHA, archive it, perform the same mandatory per-task cleanup read-back, publish only bounded availability evidence to the PR Conversation, read it back there, and advance to the next profile. It does not consume the review round or become a finding/PASS.

After every Supervisor archive, wait for task state for at most 30 seconds, then perform exactly one registration/path snapshot and append one `ROUNDLET_TASK_WORKTREE_CLEANUP_RESULT` to the run-local ledger. `REMOVED` permits continuation. A conforming empty tombstone also permits continuation. Any still-active task, registration, `.git`, content, changing state, path reuse, or ambiguous read-back is `BLOCKED` and creates no later Supervisor until reconciled. Final cleanup consumes every ledger entry; it never rediscovers old Supervisor paths by guesswork.

Apply this transition table mechanically:

| Verified result | Candidate | Formal round | Attempt | Required durable transition |
| --- | --- | --- | --- | --- |
| Invalid or unavailable attempt | Unchanged | Unchanged | Next configured position | Publish/read back bounded availability; never create findings or consume the round. |
| Valid PASS | Unchanged | Consumed and terminal | Accepted position | Publish/read back the Supervisor result, then enter terminal review gates. |
| Valid FINDINGS before the limit | Repaired by the same Worker | Consumed; next round after repair | Reset to 1 | Publish/read back the Supervisor result, repair/push/read back the new candidate, publish/read back the repair handoff, then advance. |
| Valid FINDINGS at the limit | Final repair by the same Worker | Consumed and terminal | No later attempt | Publish/read back the result and final-repair handoff, record `REVIEW_LIMIT_REACHED_WORKER_FINALIZED`, and dispatch no later Supervisor. |

The current-state tuple may advance only when every event receipt required by its row is verified on the canonical surface. A missing or ambiguous trace receipt keeps the transition pending and uses the existing idempotent cross-surface lookup/retry. It is not owner input by itself. Candidate movement after a valid result always proves a new formal review basis in the same epoch and resets the next round to attempt 1; it can never select a fallback profile in the prior round.

Rounds 1–3 are COMPLETE when reached; any valid PASS ends review. Rounds 4–10 are CONVERGING and focus on prior findings/delta while allowing new blocking regressions or missing evidence.

Before round 10, valid findings go to the same Worker for repair. The Orchestrator independently verifies the repair handoff/diff/tests, pushes the exact new candidate without force, reads back the remote head, appends and reads back the handoff trace in the PR Conversation, updates the pull request state, and only then advances to the next review round. Round-10 findings go once to `WORKER_FINAL_REPAIR`; the Orchestrator performs the same verify/push/read-back/trace sequence for that final candidate, but does not create round 11 or claim PASS. Record `REVIEW_LIMIT_REACHED_WORKER_FINALIZED` in the PR Conversation, then apply normal merge gates. If all configured attempts for a round fail, enter `NEEDS_OWNER_INPUT` and record/read back that lifecycle block on the leaf issue.

## Owner input

`NEEDS_OWNER_INPUT` stops global scheduling. Retain all active resources. The heartbeat uses owner-input backoff and only reconciles the blocker, watches for a new allowlisted issue comment, or observes direct Orchestrator input.

An issue-body edit, non-owner comment, reaction, label change, or role message does not release the block. A new valid owner instruction is traced, applied narrowly, and followed by full reconciliation. It changes the review epoch only when it materially changes leaf scope or acceptance criteria. Credential repair or confirmation of an already-authorized route preserves the epoch and accepted-round count.

## Repository authority block

At each mutation or external-validation boundary, reread root `AGENTS.md` on current authoritative `origin/main`. If the required switch is false or ambiguous, enter `REPOSITORY_AUTHORITY_REQUIRED`, retain resources, and stop scheduling. External read-only validation checks `allow_external_validation_read_only`; a disposable-target mutation checks that switch plus `allow_external_validation_disposable_target_mutation`.

Release requires either the allowlisted owner performs/confirms the action or the authority block changes on `origin/main` and the owner explicitly directs a reread. An issue-branch policy change cannot release the block.

## Merge gates

Before ready conversion or merge, prove:

- open PR, authoritative base, expected head branch;
- remote head equals terminal candidate SHA;
- no uncommitted/unpushed Worker work;
- terminal state is `SUPERVISOR_PASS` or `REVIEW_LIMIT_REACHED_WORKER_FINALIZED`;
- that terminal state belongs to the independently verified formal Supervisor tuple, not an external-validation sequence or repository-owned acceptance;
- mergeable with no conflict;
- every required check for that SHA succeeded;
- no new owner instruction blocks or changes scope;
- parsed closing references contain exactly the active leaf;
- authority permits ready, merge, and leaf close;
- branch rules permit the operation;
- configured merge method is available and equals `merge`.
- every repository-required validation-toolchain receipt and result is valid for the terminal candidate SHA; bootstrap-only or host-tool output cannot satisfy this gate.
- every selected external-validation binding, evidence-time value, semantic read-back, rollback disposition, and public-safe result is current for the terminal candidate; an ambiguous or partially applied target mutation cannot satisfy this gate.
- every selected lifecycle window is sealed and verified for the terminal candidate and required formal tuple, with a current content/retention receipt and no missing pre-arm event; `UNARMED`, `APPENDING`, `STALE`, partial, or conflicting evidence cannot satisfy this gate.

If `origin/main` advanced, reread mergeability and rules. Merge directly only when GitHub still accepts it and no rule requires an update. Otherwise send the same Worker a main-integration turn that merges `origin/main` into its exact candidate checkout without rebase/force. The Orchestrator independently verifies the integration handoff/diff/tests, updates and pushes the exact candidate ref without force, reads back the remote head, appends and reads back the handoff trace in the PR Conversation, and then starts a new COMPLETE epoch.

Mark ready only with authority. Record the merge-gate decision in the PR Conversation and read its inputs from live pull-request metadata. Merge using a merge commit only with both merge and leaf-close authority. Read the merge result, merge commit, and exact head SHA back from pull-request metadata; put any accompanying curated result trace in the PR Conversation.

## Leaf closure

The PR body includes `Closes #<leaf>` and GitHub must parse only that active leaf as closing. Use plain links or `Parent: #<umbrella>` for non-terminal context.

After merge, read the leaf. If still open and authorized, close it explicitly. Append any closure trace to the leaf issue and read both the comment and closed state back there before cleanup. Never close an umbrella.

## Ordered cleanup

Cleanup is part of the active issue:

1. Read the live pull request and leaf, then fetch the exact remote main and issue-branch refs. Read back the expected remote head and merge commit locally before asking the Worker to prove ancestry. Missing local knowledge is a refreshable preflight state, not owner input and not permission to infer ancestry.
2. Send the same Worker cleanup preflight. It verifies pushed/merged state, leaf state, worktree status, unique commits, untracked files, and absence of unpreserved work against those refreshed refs. It does not remove its own worktree/branch.
3. Independently verify the handoff and archive the Worker.
4. Wait for Worker task state for at most 30 seconds, verify it is no longer active, then perform exactly one registration/path snapshot and append its `ROUNDLET_TASK_WORKTREE_CLEANUP_RESULT` to the same run-local ledger.
5. Consume the complete run-local task-worktree cleanup ledger, then inventory every Orchestrator-created auxiliary worktree and state root. Require one terminal cleanup result for every Worker, Supervisor, and route probe task. Classify every remaining resource as source-only or evidence-bearing from the exact repository-owned contract and live contents. For every unique evidence-bearing artifact, copy exact closed bytes into the repository-declared local retention boundary, record source identity, destination identity, size, and digest, and read every retained byte/size/digest back. Missing task entries, ambiguous/open/changing resources, partially copied artifacts, or unverifiable evidence enters `CLEANUP_BLOCKED`.
6. If authorized, remove any remaining exact Worker and auxiliary linked-worktree registrations non-force only after unique-work and retention proof succeeds. Do not race or duplicate an App removal already proven in progress.
7. Independently prove every removed Git registration absent. A physical task-worktree path also must be absent unless it satisfies the typed tombstone rule below.
8. When an archived, non-active App task has no Git registration, no `.git`, and an exactly empty directory that remains locked after the bounded wait, record one local cleanup-ledger tombstone containing task ID, exact managed-worktree path, archive/non-active evidence, absent-registration evidence, and zero-content read-back. Continue cleanup without retrying deletion. Any registration, file, subdirectory, unique work, changing state, ambiguous ownership, or path outside the App-managed root enters `CLEANUP_BLOCKED`. Never kill Codex or Node to obtain cleanup, and never reuse or silently forget a tombstone.
9. Delete local/remote issue branches only when authorized and their unique work is merged or explicitly abandoned.
10. Fetch, fast-forward local `main`, and prove a clean authoritative checkout with `HEAD == main == origin/main`.
11. Retain repository-declared issue evidence, every sealed lifecycle ledger plus partial/conflicting diagnostic window, and any `.roundlet/validation-tools/` shared cache; none is an issue worktree or ordinary run-owned removal target.
12. Append the cleanup trace to the leaf issue, including the bounded retention-manifest identity, read it back there, and clear issue pointers. If continuing, retain lease/contract and set `IDLE`; if stopping, append/read back `STOPPED` on the issue, remove heartbeat, advisory state, and contract bundle after final reconciliation, then archive the Orchestrator.

Failed ref refresh, surviving registration, a non-tombstone path, unique work, incomplete retention, or ambiguous read-back enters `CLEANUP_BLOCKED` and selects no next issue. A verified typed empty task-worktree tombstone is retained local host-lifecycle evidence and does not reopen the leaf or block the next issue.

## Active issue closed, ignored, or withdrawn

Enter `OWNER_ABORT_DECISION_REQUIRED`. Accept only a new allowlisted comment or direct instruction choosing:

- `resume`;
- `preserve-and-stop`;
- `abandon-and-cleanup` with exact authorized resources.

Never infer abandonment or preserve old issue resources while selecting a new issue.

## Pause, resume, stop, and skill updates

- `pause`: finish an atomic mutation or stop before the next, record `PAUSED`, pause the heartbeat, and preserve resources.
- `resume` and explicit recovery preserve review epoch/round whenever immutable contract, scope, acceptance criteria, and candidate review basis reconcile unchanged; they never manufacture a new epoch to regain an attempt budget.
- `stop-after-current`: finish the active issue and ordered cleanup; if IDLE, stop immediately. Then remove the heartbeat, record `STOPPED`, remove advisory state/bundle after reconciliation, and archive the Orchestrator.
- Installed skill/config drift never changes live instructions. Report it as an update candidate.
- To update Roundlet, stop and fully clean the old run, install the reviewed new skill, and perform New activation with a new run and contract. Do not adopt or migrate in place.

## Copyable owner commands

Send routine commands to the existing Orchestrator. Do not invoke installed `$roundlet`; use only the pinned bundle.

### Inspect status without advancing

```text
In the existing Orchestrator task, inspect the active Roundlet run without advancing it. Resolve and read only the immutable activation bundle; do not invoke or load the installed `$roundlet` skill.

Target repository: <OWNER/REPOSITORY>
Authoritative checkout: <ABSOLUTE_PATH>

Reconcile GitHub, exact Git state, role tasks, heartbeat, lease, and current state. Do not mutate GitHub/Git or advance a tick. Report run/contract/Orchestrator/heartbeat identities, phase, active leaf/PR, Worker/current Supervisor, candidate SHA, review epoch/round/attempt/profile, external-validation state, lifecycle-observation state/window/head, blocker, last durable event, heartbeat interval, last full reconciliation, and next safe action. Stop on contradictory evidence.
```

### Pause at a safe checkpoint

```text
In the same Orchestrator, pause the Roundlet run for <OWNER/REPOSITORY>. Read only the pinned bundle. Reconcile first, finish only an already-started atomic mutation, record PAUSED, pause the one heartbeat, preserve all resources and unique work, and report the checkpoint. Do not archive the Orchestrator or select another issue.
```

### Resume the paused run

```text
In the same Orchestrator, resume the paused Roundlet run for <OWNER/REPOSITORY>. Read only the pinned bundle. Fully reconcile GitHub, Git, tasks, heartbeat, lease, and current state. Stop on conflict. Otherwise reset/resume the same heartbeat at active_minutes and perform at most one idempotent tick. Do not replace a task or heartbeat.
```

### Stop after the current issue

```text
In the existing Orchestrator, set stop-after-current for <OWNER/REPOSITORY>. Read only the pinned bundle. Reconcile and record STOP_AFTER_CURRENT. Finish the active issue through normal review, merge gates, closure, and cleanup, but select no next issue. If IDLE, stop now. At the terminal safe state remove the one heartbeat, record STOPPED, remove advisory state and the contract bundle after read-back, and archive the Orchestrator. Never discard unique work.
```

### Resolve a closed, ignored, or withdrawn active issue

```text
In the existing Orchestrator for <OWNER/REPOSITORY>, read only the pinned bundle and reconcile all live evidence. Apply this owner decision to active leaf <ISSUE_NUMBER_AND_URL>: <resume|preserve-and-stop|abandon-and-cleanup>. For abandon-and-cleanup remove only <EXACT_RESOURCE_LIST>. Preserve anything else and report every retained, removed, and unresolved resource.
```

If the Orchestrator or heartbeat is inaccessible, use the Explicit recovery Launcher.

## Recovery

- An ordinary failed Orchestrator turn may resume idempotently on the next heartbeat when the same task and heartbeat remain accessible.
- An inaccessible Orchestrator/heartbeat requires the explicit recovery prompt and owner direction. A stale-looking file is insufficient.
- An inaccessible persistent Worker requires owner direction before replacement.
- A failed Supervisor is disposable under the bounded attempt rule.
- Verify the immutable activation bundle first, then reconstruct from GitHub trace, exact Git, task/heartbeat evidence, and advisory files.
- Reconstruct and verify the selected repository-owned external-validation binding, declared schema identities, opaque external-validation sequence, and historical evidence-time value when applicable. Reconstruct the formal Supervisor tuple independently. Preserve each sequence on its own exact match; conflict fails closed instead of copying one sequence into the other or resetting review accounting.
- Reconstruct any selected lifecycle-sink contract, exact arm receipt, window/candidate/formal binding, append sequence/head, seal state, and retained receipt independently. Missing pre-arm history or an unverifiable chain stays `STALE` and requires a fresh live window; recovery never creates or backfills an event.
- Treat the installed skill as unrelated candidate material. It cannot repair or replace the active contract.
- Stop on contradictions and append corrections rather than editing old trace.
