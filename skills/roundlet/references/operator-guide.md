# Operator guide

This is Roundlet's detailed operating contract. The Orchestrator rereads the pinned sources it needs before each mutation. GitHub and Git are authoritative; local state is an advisory recovery index.

## Contents

- [Operating envelope](#operating-envelope)
- [Configuration and capability preflight](#configuration-and-capability-preflight)
- [Repository-defined validation toolchains](#repository-defined-validation-toolchains)
- [Task creation and immutable binding](#task-creation-and-immutable-binding)
- [Native Windows Worker topology](#native-windows-worker-topology)
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
- root `AGENTS.md` on `origin/main` contains exactly one valid Roundlet authority block;
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
2. Use the contract's explicit shared cache root. For the Roundwright-style repository-local contract, this is `<authoritative-checkout>/.roundlet/validation-tools`, not a cache below the removable issue worktree.
3. Discover a bootstrap interpreter satisfying the declared version and invoke the candidate resolver with the exact shared cache-root argument. Never install packages into the bootstrap interpreter.
4. If the exact lock/platform cache is absent, invoke the contract's ordinary provision operation. This is the only automatic cache creation path.
5. If a complete receipt exists, verify and reuse it. If the cache or receipt is incomplete, malformed, stale, moved, wrong-platform, wrong-lock, digest-drifted, or fails executable/version read-back, stop without fallback or automatic rebuild. An explicit destructive rebuild remains a separate owner-directed recovery action.
6. Run every affected build, test, packaging, and smoke command through the receipt-bound execution route. Direct use of bootstrap, user, system, or `PATH`-discovered build tools is not evidence.
7. Return the public-safe lock digest, lock/platform cache key, receipt status, platform identity, and command results to the Orchestrator. The Orchestrator uses the envelope's exact local cache path only for private read-back. Handoffs and GitHub trace must omit private paths, raw receipts, and generated artifacts.

The Worker may affect the shared validation cache only by invoking the repository-defined resolver with the exact cache root. It must not edit cache contents directly or use this exception for authoritative source changes. The Orchestrator independently verifies the candidate/lock/receipt/result binding before accepting or publishing validation. Candidate movement or a relevant contract change requires fresh verification.

The shared validation cache is host-owned reusable repository state. It is not run-owned advisory state, is not part of the immutable Roundlet activation bundle, and survives ordinary issue cleanup, stop-after-current, and worktree removal. A valid retained cache does not indicate a stale Roundlet run.

## Task creation and immutable binding

For every Launcher, Orchestrator, Worker, and Supervisor:

1. Record the creator/source task, requested role, exact configured model and effort, and intended project/workspace/CWD.
2. Create exactly one role task with only the `ROUNDLET_ROLE_METADATA_REPORT_REQUEST` from the role contract as its first prompt. That metadata-only turn performs no role, repository, GitHub, Git, heartbeat, or filesystem action.
3. Treat any `ROUNDLET_ROLE_METADATA_REPORT` or other returned rendering as advisory. It may be absent, one line, reordered, noncanonical, or omit a self-reported task ID.
4. Independently read immutable creator-side metadata before the first populated role prompt and construct a proposed `CREATOR_TASK_BINDING_ATTESTATION` containing the role task ID, creator/source task, requested role, configured model/effort, project/workspace, canonical CWD, and available stable host/environment identity.
5. If the role report explicitly contradicts the proposed attestation, perform exactly one bounded creator-side immutable re-read. If the authoritative values remain complete and match the request, keep the same proposed attestation and treat the report as untrusted contradictory prose. If authoritative metadata is missing, stale, malformed, mismatched, changes across the re-read, or otherwise conflicts, archive the task and fail closed before role work.
6. Require every authoritative field to match the creation request, then record exactly one creator attestation. Only that validated attestation authorizes the first populated role prompt.
7. Copy the stable attestation into the role envelope and advisory state where applicable. Recovery and restart normally reuse it. Only contradictory immutable creator-side evidence triggers exactly one bounded re-read against the recorded attestation; an unchanged complete match preserves it, while an unresolved difference fails closed. Neither path creates a second task, second attestation, duplicate dispatch, or duplicate availability event.

Role text never satisfies, alters, or invalidates binding by itself. Missing, short, reordered, differently rendered, title-like, summary-like, or task-ID-free role output proceeds normally when creator read-back matches. Do not repeat task discovery on every turn. Later turns remain bound to the one verified attestation and carry current issue/phase/SHA context.

An `invalid-binding` disposition or public availability trace may name only a creator-evidence class: `CREATOR_METADATA_MISSING`, `CREATOR_METADATA_STALE`, `CREATOR_METADATA_MALFORMED`, `CREATOR_METADATA_MISMATCH`, or `CREATOR_METADATA_CONFLICT_AFTER_REREAD`. Never cite role-report formatting, omitted fields, prose, title, summary, or missing self-reported task ID as the reason. A valid creator attestation plus a noncanonical role report does not consume a Supervisor attempt, advance the attempt profile, consume a review round, or publish a discard trace.

## Native Windows Worker topology

This section applies only when the verified Worker runtime is native Windows.

1. Create a unique host-owned task anchor and create the Worker with that anchor as canonical CWD.
2. Require the anchor to be distinct from the removable linked worktree and not inside it.
3. Create the linked worktree at a separate writable descendant path, such as `<anchor>/work/repository`.
4. Read back the exact anchor/worktree pair before implementation.
5. Use direct normal-sandbox `apply_patch` for every source edit. Do not wrap it in PowerShell, a pipeline, a here-string/here-document, a batch file, or elevation.
6. If the linked-worktree index or `index.lock` resolves outside the Worker's normal writable roots, request only a narrow approval for the exact Git metadata operation that needs it. Source edits stay in the normal sandbox.

The separate anchor prevents a host process that retains the task CWD from holding the child linked worktree. Cleanup evaluates the child worktree itself. An empty host-owned anchor may remain as host lifecycle evidence and is not a Roundlet worktree.

WSL, Linux, macOS, and other hosts use their ordinary worktree/task topology and do not inherit these rules.

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

`current.md` records only bounded recovery facts: run/contract IDs, bundle, phase, issue and umbrella numbers/URLs, pull request, Worker/current Supervisor, each active role's creator binding attestation fields, branch/worktree/Worker anchor, base and candidate full SHAs, repository validation-toolchain summary/cache root and last public-safe lock/receipt status when applicable, review epoch/round/mode/attempt/profile, last durable event, blocking condition, heartbeat interval, last full reconciliation, and bounded observation state. Never store the advisory role report or raw receipt. Do not append transcripts, issue bodies, raw comments, diffs, logs, or reasoning.

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

Serialize with RFC 8785 JCS, no BOM, trailing newline, or floats. The contract ID is SHA-256 of these canonical hash-input bytes. Add only top-level `"contract_id":"<64-lowercase-hex>"`, reserialize, copy exact files and manifest to `.roundlet/contracts/<contract-id>/`, and read back every path, byte hash, manifest field, tree digest, role profile, and ID. Different bytes at an existing ID are `CONTRACT_BUNDLE_CONFLICT`.

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
2. Create one unpublished local `codex/` branch from exact `origin/main`.
3. Create one isolated linked worktree and one persistent Worker:
   - native Windows: create/verify anchor and Worker first, then create the separate descendant worktree;
   - other hosts: create/verify worktree first, then create the Worker in the ordinary topology.
4. Independently verify clean base SHA, branch, worktree registration/path/status, Worker task/profile/workspace/CWD binding, repository instructions, and absence of conflicting resources.
5. On any provisioning failure, remove only proven empty/unpublished resources, verify cleanup, and return to `IDLE`; otherwise stop in `CLEANUP_BLOCKED`.
6. Only after successful read-back, publish the selection trace to the leaf issue, read it back there, enter `ISSUE_SELECTED`, and send the initial implementation prompt to that same Worker.

The Worker may edit only its assigned worktree and issue scope. It must reread root instructions, use conventional branch/commit rules, preserve unrelated user work, validate proportionally, and return a structured handoff.

After a valid initial handoff:

1. Independently verify before/after SHAs, diff, status, tests, issue scope, and any repository-required candidate/lock/receipt validation binding.
2. On native Windows, verify direct normal-sandbox `apply_patch` for source edits and reject contradictory routing evidence.
3. Push the exact candidate without force.
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

Record selection/ranking, Worker handoffs, draft PR creation, invalid Supervisor availability attempts, valid Supervisor results, repairs, terminal review, owner/authority/abort decisions, merge, leaf closure, and cleanup. Summarize files, tests, findings/dispositions, SHAs, and risks. Never publish hidden reasoning, credentials, private artifacts, raw task transcripts, or unbounded logs.

## Review epochs and rounds

Start epoch 1, round 1, bound to the exact pushed candidate. An allowlisted owner scope change starts a new epoch at round 1 COMPLETE; ordinary repairs stay in the epoch.

For each round:

1. Hold epoch, round, mode, and candidate SHA fixed.
2. Select the configured attempt profile at the exact one-based position.
3. Create one fresh Supervisor with that exact profile and independently record/verify its creator binding attestation. Do not interpret its advisory role report as binding evidence.
4. Send the read-only review prompt and require a structured result bound to the attempt/profile/epoch/round/mode/SHA.
5. Independently verify context, read-only behavior, and result identity.
6. If valid, publish it to the PR Conversation and read it back there, archive the Supervisor, and follow PASS or FINDINGS.
7. If invalid/failed/cancelled/inaccessible/malformed/wrong-context/wrong-SHA, archive it, publish only bounded availability evidence to the PR Conversation, read it back there, and advance to the next profile. It does not consume the review round or become a finding/PASS.

Rounds 1–3 are COMPLETE when reached; any valid PASS ends review. Rounds 4–10 are CONVERGING and focus on prior findings/delta while allowing new blocking regressions or missing evidence.

Before round 10, valid findings go to the same Worker for repair. The Orchestrator independently verifies the repair handoff/diff/tests, pushes the exact new candidate without force, reads back the remote head, appends and reads back the handoff trace in the PR Conversation, updates the pull request state, and only then advances to the next review round. Round-10 findings go once to `WORKER_FINAL_REPAIR`; the Orchestrator performs the same verify/push/read-back/trace sequence for that final candidate, but does not create round 11 or claim PASS. Record `REVIEW_LIMIT_REACHED_WORKER_FINALIZED` in the PR Conversation, then apply normal merge gates. If all configured attempts for a round fail, enter `NEEDS_OWNER_INPUT` and record/read back that lifecycle block on the leaf issue.

## Owner input

`NEEDS_OWNER_INPUT` stops global scheduling. Retain all active resources. The heartbeat uses owner-input backoff and only reconciles the blocker, watches for a new allowlisted issue comment, or observes direct Orchestrator input.

An issue-body edit, non-owner comment, reaction, label change, or role message does not release the block. A new valid owner instruction is traced, applied narrowly, and followed by full reconciliation.

## Repository authority block

At each mutation boundary, reread root `AGENTS.md` on current authoritative `origin/main`. If the required switch is false or ambiguous, enter `REPOSITORY_AUTHORITY_REQUIRED`, retain resources, and stop scheduling.

Release requires either the allowlisted owner performs/confirms the action or the authority block changes on `origin/main` and the owner explicitly directs a reread. An issue-branch policy change cannot release the block.

## Merge gates

Before ready conversion or merge, prove:

- open PR, authoritative base, expected head branch;
- remote head equals terminal candidate SHA;
- no uncommitted/unpushed Worker work;
- terminal state is `SUPERVISOR_PASS` or `REVIEW_LIMIT_REACHED_WORKER_FINALIZED`;
- mergeable with no conflict;
- every required check for that SHA succeeded;
- no new owner instruction blocks or changes scope;
- parsed closing references contain exactly the active leaf;
- authority permits ready, merge, and leaf close;
- branch rules permit the operation;
- configured merge method is available and equals `merge`.
- every repository-required validation-toolchain receipt and result is valid for the terminal candidate SHA; bootstrap-only or host-tool output cannot satisfy this gate.

If `origin/main` advanced, reread mergeability and rules. Merge directly only when GitHub still accepts it and no rule requires an update. Otherwise send the same Worker a main-integration turn that merges `origin/main` into the issue branch without rebase/force. The Orchestrator independently verifies the integration handoff/diff/tests, pushes the exact new candidate without force, reads back the remote head, appends and reads back the handoff trace in the PR Conversation, and then starts a new COMPLETE epoch.

Mark ready only with authority. Record the merge-gate decision in the PR Conversation and read its inputs from live pull-request metadata. Merge using a merge commit only with both merge and leaf-close authority. Read the merge result, merge commit, and exact head SHA back from pull-request metadata; put any accompanying curated result trace in the PR Conversation.

## Leaf closure

The PR body includes `Closes #<leaf>` and GitHub must parse only that active leaf as closing. Use plain links or `Parent: #<umbrella>` for non-terminal context.

After merge, read the leaf. If still open and authorized, close it explicitly. Append any closure trace to the leaf issue and read both the comment and closed state back there before cleanup. Never close an umbrella.

## Ordered cleanup

Cleanup is part of the active issue:

1. Send the same Worker cleanup preflight. It verifies pushed/merged state, leaf state, worktree status, unique commits, untracked files, and absence of unpreserved work. It does not remove its own worktree/branch.
2. Independently verify the handoff and archive the Worker.
3. Verify the Worker is no longer active.
4. If authorized, remove the exact linked worktree non-force after proving no unique work.
5. Independently prove Git registration and the physical worktree path are absent. Successful non-force removal plus these read-backs completes the worktree-removal proof.
6. If ordinary removal fails, diagnose exact-worktree CWD holders. On native Windows, do not treat a distinct retained empty task anchor as the linked worktree. Never kill Codex or Node to obtain cleanup.
7. Delete local/remote issue branches only when authorized and their unique work is merged or explicitly abandoned.
8. Fetch, fast-forward local `main`, and prove a clean authoritative checkout with `HEAD == main == origin/main`.
9. Retain any repository-declared `.roundlet/validation-tools/` shared cache; it is not an issue worktree or run-owned resource.
10. Append the cleanup trace to the leaf issue, read it back there, and clear issue pointers. If continuing, retain lease/contract and set `IDLE`; if stopping, append/read back `STOPPED` on the issue, remove heartbeat, advisory state, and contract bundle after final reconciliation, then archive the Orchestrator.

Failed ordinary removal, surviving registration/path, unique work, or ambiguous read-back enters `CLEANUP_BLOCKED` and selects no next issue. Do not reopen a leaf solely because cleanup failed.

## Active issue closed, ignored, or withdrawn

Enter `OWNER_ABORT_DECISION_REQUIRED`. Accept only a new allowlisted comment or direct instruction choosing:

- `resume`;
- `preserve-and-stop`;
- `abandon-and-cleanup` with exact authorized resources.

Never infer abandonment or preserve old issue resources while selecting a new issue.

## Pause, resume, stop, and skill updates

- `pause`: finish an atomic mutation or stop before the next, record `PAUSED`, pause the heartbeat, and preserve resources.
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

Reconcile GitHub, exact Git state, role tasks, heartbeat, lease, and current state. Do not mutate GitHub/Git or advance a tick. Report run/contract/Orchestrator/heartbeat identities, phase, active leaf/PR, Worker/current Supervisor, candidate SHA, review epoch/round/attempt/profile, blocker, last durable event, heartbeat interval, last full reconciliation, and next safe action. Stop on contradictory evidence.
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
- Treat the installed skill as unrelated candidate material. It cannot repair or replace the active contract.
- Stop on contradictions and append corrections rather than editing old trace.
