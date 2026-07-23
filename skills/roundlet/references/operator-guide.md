# Operator guide

This is the detailed operating contract for Roundlet. The Orchestrator must reread the live sources it depends on before every mutation. Natural-language judgment is intentional; local files provide an advisory recovery index, not deterministic coordination.

## Contents

- [Operating envelope](#operating-envelope)
- [Configuration and capability preflight](#configuration-and-capability-preflight)
- [Advisory local state](#advisory-local-state)
- [Pinned run contract and migration](#pinned-run-contract-and-migration)
- [Lightweight observation and heartbeat cadence](#lightweight-observation-and-heartbeat-cadence)
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
- [Pause, resume, and stop](#pause-resume-and-stop)
- [Copyable owner commands](#copyable-owner-commands)
- [Recovery](#recovery)

## Operating envelope

Roundlet is safe only inside this deliberately narrow envelope:

- one GitHub target repository;
- one authoritative local checkout on one authoritative machine;
- one long-lived Orchestrator Codex task;
- one recurring, phase-aware heartbeat attached to that Orchestrator;
- zero or one active leaf issue;
- one persistent Worker task for that issue;
- one fresh Supervisor task for each review attempt;
- one isolated worktree and one `codex/` branch for that issue;
- one Orchestrator identity as the only GitHub mutator;
- one activation-time, content-addressed active contract bundle.

Do not start a second Roundlet run for the same target from another Codex task, clone, or machine. A local file lease is advisory: two independent actors can both read an apparently free file or cannot see each other's file at all, then both believe they own the run. That is split-brain. The operating envelope, activation preflight, GitHub trace, and refusal to auto-take over reduce the risk; they do not create distributed locking.

## Configuration and capability preflight

Read `roundlet-config.json` exactly. Do not supply defaults, coerce values, or silently fall back.

Before activation, prove all of the following:

- every configured model/reasoning-effort pair is selectable on the current Codex host;
- Supervisor attempt-profile names are unique, the ordered profile count equals `max_supervisor_attempts_per_round`, and every position has an exact model and reasoning effort;
- tasks can be created, addressed, waited on, resumed, and archived;
- a follow-up can target the same task with an exact per-turn model and reasoning-effort override, and task metadata can read back the actual task identity, model, and effort rather than trusting self-report;
- one recurring heartbeat can be created, inspected, paused/resumed, and stopped;
- that same heartbeat can be updated through every configured active, IDLE, and owner-input interval without creating a replacement;
- Git and the authoritative checkout are usable;
- GitHub identity, repository identity, issues, comments, branches, pull requests, reviews, checks, mergeability, and merge operations can be inspected;
- authorized GitHub mutations are available to the Orchestrator;
- the exact installed candidate contract can be copied to a local content-addressed bundle and every copied path/hash can be read back;
- the root authority block on `origin/main` is valid;
- the repository supports the configured merge method;
- `HEAD`, local `main`, and `origin/main` initially name the same full commit;
- the authoritative checkout is clean and no other Roundlet evidence is active or unreconciled;
- the target's rules and required checks can be determined well enough to fail closed at merge time.

When a role uses `gh`, distinguish connectivity from credentials before classifying capability:

1. Treat a result produced before GitHub is reachable, including a misleading invalid-token result inside a network-restricted sandbox, as inconclusive.
2. Request scoped network escalation for the same command automatically. Prefer a read-only request while proving identity or reachability, and never expose token material.
3. For an escalated DNS, timeout, or transport failure, retry once in the same turn and once at the next automatic opportunity: the next heartbeat when one is bound, or once more in the active Launcher or role turn when no heartbeat exists yet. These attempts are supporting checks, not externally meaningful state transitions, review attempts, or review rounds.
4. Continue automatically after any successful request. Only classify authentication as invalid when reachable GitHub rejects it.
5. Never open browser authentication or substitute browser automation for required GitHub CLI capability. Browser authentication requires explicit owner direction after confirmed credential rejection.

This contract requires the role to request escalation; it does not grant or let the role assume network access. The host permission policy remains authoritative.

Enter `NEEDS_OWNER_INPUT` only when approval is explicitly denied, the approval mechanism is unavailable, reachable GitHub rejects authentication, or the bounded attempts prove that required GitHub connectivity remains unavailable. Preserve the exact command, escalation outcome, transport or HTTP evidence, and attempt count.

If any capability cannot be proven, report the exact unsupported value or missing capability and stop. Capability preflight is performed through Codex/tool inspection; it is not an executable validator or cross-platform test matrix.

## Advisory local state

Add `.roundlet/` to the authoritative checkout's local `.git/info/exclude`. Never commit the exclusion or local contract snapshots. Keep only:

- `.roundlet/lease.json`: stable run ownership, task identities, and immutable activation contract ID; any active-contract value is only a derived mirror;
- `.roundlet/current.md`: concise human-readable recovery index for current state and a derived effective-contract mirror;
- `.roundlet/contracts/<contract-id>/`: read-only activation or adoption/migration snapshots containing `SKILL.md`, every required reference, the resolved role configuration, and the canonical manifest;
- `.roundlet/migrations/<sequence>-<migration-id>/prepared.json` and `committed.json`: immutable two-phase records from which the effective contract is resolved.

The lease contains no expiry and authorizes no automatic takeover. A representative lease is:

```json
{
  "run_id": "unguessable-stable-id",
  "target": "owner/repository",
  "authoritative_checkout": "/absolute/path",
  "authoritative_machine": "stable-machine-identity",
  "owner": "allowlisted-github-login",
  "activated_at": "ISO-8601 timestamp",
  "activation_contract_id": "sha256-derived-id",
  "active_contract_id_mirror": "sha256-derived-id",
  "active_contract_bundle_mirror": "/absolute/path/.roundlet/contracts/<contract-id>",
  "orchestrator_task": "opaque-task-id",
  "heartbeat": "opaque-heartbeat-id"
}
```

`current.md` records only pointers and reconciliation facts: phase, immutable activation ID, derived effective-contract ID and bundle path, installed-candidate fingerprint, pending adoption/migration identity when present, issue and umbrella URLs/numbers, pull-request URL/number, Worker task, current Supervisor task when one exists, branch, worktree, base and candidate full SHAs, review epoch/round/mode, Supervisor attempt number/profile, last durable GitHub event, blocking condition, last full reconciliation time, and the bounded semantic baseline plus cadence state defined below. Do not treat it as durable history or append a transcript.

Before every tick or mutation, verify the active bundle and reconcile both files against GitHub, Git, Codex tasks, and the heartbeat. Prefer live authoritative evidence. When evidence conflicts, stop with `STATE_RECONCILIATION_REQUIRES_OWNER`; never guess or overwrite the conflict.

## Pinned run contract and migration

At activation, build a `roundlet-contract/v1` manifest with source kind/locator, a provable full source Git OID or `installed-tree:<root-digest>` fallback, contract schema version, exact resolved role configuration, and every required relative path plus the SHA-256 of its exact bytes. Canonical manifest bytes are UTF-8 without BOM or trailing newline, compact JSON, object keys sorted lexicographically at every level, and files sorted by relative path. The lowercase contract ID is the SHA-256 of those bytes with `contract_id` omitted. Add the ID, copy the exact files into `.roundlet/contracts/<contract-id>/`, and read back the complete bundle. An existing directory with that ID but different bytes is `CONTRACT_BUNDLE_CONFLICT`.

Each `prepared.json` records schema, sequence, migration ID, run ID, mode, old/new contract IDs, candidate source/ref, allowlisted-owner authorization event, same Orchestrator task ID, task-metadata model/effort read-back, bundle-manifest hash, and timestamp. Its sibling `committed.json` contains only schema, migration ID, SHA-256 of the exact prepared bytes, old/new IDs, and commit timestamp. Both use the manifest's canonical JSON rules and are immutable after read-back.

The activation ID in the lease is immutable. The effective active contract is the activation ID followed by the longest unique chain of fully valid `committed.json` records whose `old_contract_id` links exactly to the prior ID and whose prepared record, owner authorization, bundle, model/effort metadata, and hashes all verify. Ignore incomplete prepared records. Multiple valid successors, a gap, malformed record, or mirror disagreement fails closed. Lease/current active values are derived recovery mirrors and never choose the contract.

Every active Orchestrator, Worker, Supervisor, heartbeat, routine owner, and recovery turn reads only the effective bundle; routine and recovery prompts do not invoke the installed `$roundlet` skill. The observation baseline fingerprints the verified effective bundle and installed candidate separately. Installed drift never authorizes a repository transition.

At clean `IDLE` with no leaf resources, drift enters `CONTRACT_ADOPTION_REQUIRED`; after exact allowlisted-owner authorization it may enter `CONTRACT_ADOPTING`. In all other phases it enters `CONTRACT_MIGRATION_REQUIRED`, retains the run, Orchestrator, heartbeat, Worker, branch, worktree, pull request, issue, candidate SHA, and review state, and may enter `CONTRACT_MIGRATING` only after exact authorization. Both paths pause the heartbeat and require a same-task follow-up whose actual candidate model/effort and task identity are proven from task metadata.

Stage and verify the new bundle and `prepared.json`, write a truthful checkpoint, and end the preparation turn with the structured acknowledgement without creating `committed.json`. After external verification, a second same-task follow-up under the same candidate model/effort revalidates every input; creating one fully valid `committed.json` is its single commit point. A failure before it leaves the old contract effective. After it, the new contract is effective even if a derived mirror update fails; pause and reconstruct mirrors from the committed chain before any other transition. Never roll back or guess. Preserve old bundles and migration records until the run stops.

## Lightweight observation and heartbeat cadence

Use two tiers. The observation tier asks only whether the last full reconciliation is still current. The full tier reads and reasons over the live semantic sources. Never use observation metadata to select, claim, review, mark ready, merge, close, clean up, change scope, or make another mutation.

### Bounded semantic baseline and cadence state

After every successful full reconciliation, replace the prior semantic baseline in `current.md` with these bounded facts:

- the verified active contract manifest, a complete bundled-file fingerprint, and the stable lease;
- authoritative `origin/main` full OID, phase, active contract ID and verified bundle fingerprint, separately fingerprinted installed candidate, and last-full-reconciliation time;
- a repository-wide open-issue graph fingerprint and its open-issue count while IDLE;
- active leaf, umbrella, dependency, branch, worktree, candidate-SHA, pull-request, check/review, and role-task fingerprints/cursors required by an active phase;
- watched issue-comment ID/author/time and direct Orchestrator input cursor while waiting for owner input or repository authority;
- explicit `complete` and `overflow` flags for every paginated source.

Maintain a separate cadence state beside that baseline: heartbeat identity and expected current interval, lightweight-tick count since full reconciliation, IDLE and owner-input no-op streaks, last lightweight-observation time, and last successfully matched semantic fingerprint. A successful lightweight no-op updates only this cadence state after the heartbeat schedule update is verified; it does not claim a new full semantic baseline. The next tick compares live heartbeat state with the latest cadence state, so an intentional 5-to-15, 15-to-30, or 30-to-60 update is expected rather than a semantic mismatch.

Keep only digests, counts, IDs, cursors, full SHAs, timestamps, paths, and the last accepted event URL. Do not store issue bodies, comments, diffs, check logs, task transcripts, or tool output in `current.md`.

### Exact IDLE change detector

GitHub Connector remains the primary surface for semantic full reads and all GitHub mutations. Its normalized issue reads do not expose every raw relationship, pagination, or conditional-metadata field needed for an unchanged proof. For this observation only, use authenticated `gh api graphql` with `--paginate` and built-in `--jq`; do not require a separately installed `jq`. Apply the GitHub CLI connectivity-recovery contract before classifying a failure.

Fingerprint all open issues, not only the first page or the previously ready set. For each issue include:

- `id`, `number`, `title`, `state`, and `updatedAt`;
- the complete label-name set;
- comment `totalCount` plus the latest comment's `id`, `updatedAt`, and `author.login`;
- parent `id`, `number`, `state`, and `updatedAt`, or `none`;
- exact sub-issue, blocked-by, and blocking issue `id`, `number`, `state`, and `updatedAt` sets, their summary counts, and each connection's `pageInfo`.

Paginate the root open-issue connection to exhaustion. Canonically order compact records by issue number and relationship ID, keep the raw records inside the command pipeline, and emit only the record count, overflow flags, and one composite `git hash-object` fingerprint into model context. Git is already a Roundlet prerequisite. Require pipeline failure propagation, successful `gh` status, a parseable response, and the expected record count before accepting the digest; hashing empty output after an upstream failure is inconclusive, never an unchanged proof. If a nested relationship or label connection cannot be exhausted in the bounded query, set `overflow`; do not truncate and call the result unchanged.

This vector detects new, closed, edited, relabeled, reparented, newly commented, or dependency-changed issues. A changed umbrella body changes its `updatedAt`; exact relationship sets independently detect parent/sub-issue or dependency changes. The scheduled full-audit bound below protects against an upstream timestamp or fingerprint defect.

### Phase-specific active observations

Add only the live fields needed to detect progress in the current phase:

- For the local issue worktree: exact path, branch, `HEAD`, upstream/remote-head OIDs, and a fingerprint of porcelain status including untracked paths.
- For Worker or Supervisor waits: exact task identity, terminal/running state, and the last consumed task cursor. An unchanged running task may no-op; a new cursor or terminal state requires full reconciliation in the same tick.
- For a pull request: number, state, `updatedAt`, draft state, base/head OIDs, mergeability/merge-state, review decision, exact closing-issue references, latest issue-comment and review watermarks, unresolved review-thread identities, and the latest head commit's status/check rollup. Exhaust or mark overflow for review, thread, and check connections. Check status can change without the pull-request `updatedAt`, so never omit the rollup.
- For `NEEDS_OWNER_INPUT` or `REPOSITORY_AUTHORITY_REQUIRED`: contract/lease/origin fingerprints, the watched issue's latest comment ID/author/time, and the direct Orchestrator input cursor. A direct task instruction wakes its own turn; it does not wait for the next heartbeat. A new issue comment is detected by the lightweight watermark.
- For `PAUSED`: perform no recurring observation because the heartbeat is paused. Resume only on a direct owner instruction followed by full reconciliation.

An action-ready phase always uses full reconciliation. Lightweight no-ops are allowed only for unchanged IDLE, unchanged running-role/check waits, and unchanged owner/authority waits.

### Escalation to full reconciliation

Perform the full tier in the same tick when any fingerprint, count, OID, status, cursor, watermark, heartbeat identity, active contract identity, or installed-candidate fingerprint differs; any required field is missing or malformed; any connection reports overflow; the observation command is inconclusive; the phase is action-ready; or `max_lightweight_ticks_before_full_reconciliation` is reached. Do not wait for another heartbeat to fetch the issue body, comments, canonical note, dependencies, pull-request details, task output, diff, checks, authority, or other full sources.

When the IDLE graph fingerprint changes, fully rescan and classify every open issue because a single composite digest intentionally does not guess which semantic record changed. When a watched owner-comment watermark changes, reread the complete blocked issue, its comments, scheduling context, dependencies, authority, and active resources before accepting the instruction. When an active-resource vector changes, reread the complete phase contract and exact changed resources. Use server-side field selection and bounded summaries for routine metadata; fetch raw check logs or large tool outputs only when diagnosing a specific failure. This reduces context volume without hiding evidence required for a decision.

After a successful full reconciliation, refresh the semantic baseline and reset the applicable cadence counters before any mutation. After a successful lightweight no-op, retain the semantic baseline and update only the verified cadence state. A failed or contradictory full read or cadence update fails closed under the normal state rules.

### One heartbeat, adaptive intervals

Create the one heartbeat initially at `heartbeat.active_minutes`. Update that same heartbeat; never create a replacement merely to change cadence.

- Active work, a changed/incomplete observation, a direct owner instruction, or a resumed run uses `active_minutes`.
- Starting from the active interval, each consecutive unchanged IDLE observation advances to the next value in `idle_noop_backoff_minutes`; remain at the last value after the list is exhausted.
- Each consecutive unchanged owner-input or repository-authority wait advances through `owner_input_noop_backoff_minutes`; remain at its last value.
- Any change, error, overflow, action-ready phase, or accepted owner input resets the relevant no-op streak and interval to `active_minutes` before further work.
- A periodic full reconciliation caused only by the configured lightweight-tick limit resets the lightweight-tick count but may retain the current backoff interval when it proves no change.
- Heartbeat schedule maintenance is bounded control-plane bookkeeping. It does not consume the tick's one externally meaningful repository transition, but its result and exact interval must reconcile before the tick finishes.

With the checked-in configuration, a quiet IDLE run progresses from 5 to 15 to 30 to 60 minutes; an owner-input wait progresses from 5 to 15 to 30 minutes. Pausing stops heartbeat polling. Completing and cleaning a leaf resets the existing heartbeat to the active interval, records `IDLE`, and leaves continuous scheduling enabled. Only an explicit stop-after-current instruction stops the run.

## Backlog classification

Scan all open issues in the target repository on activation, after an IDLE observation change, and at every due full reconciliation. An exact unchanged IDLE graph fingerprint may finish as a lightweight no-op without rereading issue bodies. Include issues created after activation in every full scan.

Classify from live GitHub parent/sub-issue relationships, labels, body, comments, and canonical notes:

- **Umbrella**: an issue with one or more formal GitHub sub-issues and a body containing a clearly identified `Canonical scheduling note`. It is scheduling context, never an implementation candidate, and Roundlet never closes it.
- **Scheduling-blocked parent**: an issue with one or more formal sub-issues but no Canonical scheduling note. Enter `NEEDS_OWNER_INPUT`; do not reinterpret it as a leaf or silently schedule around it.
- **Leaf**: an open issue with no formal sub-issues. It may be a formal sub-issue or a standalone issue with no parent.
- **Ignored**: an issue carrying `roundlet:ignore`. Exclude it even if it would otherwise be a leaf.

Only leaves are implementation candidates. A standalone open leaf is eligible on the same terms as an umbrella sub-issue.

Do not require a rigid issue template. Consider a leaf actionable when its live issue, repository evidence, and scheduling context provide enough scope, boundaries, acceptance intent, and dependency information to proceed safely. Infer ordinary implementation detail when risk is low. If a genuinely owner-only choice, destructive ambiguity, security decision, incompatible acceptance criteria, or missing prerequisite prevents safe progress, select no substitute: enter `NEEDS_OWNER_INPUT` on that leaf and stop global scheduling.

## Dependencies and ranking

Build one live candidate set across every umbrella plus standalone leaves. Use formal sub-issue status, Canonical scheduling notes, explicit dependency statements, linked issues/pull requests, and current repository evidence.

Apply the following order:

1. Exclude ignored, owned, closed, umbrella, and scheduling-blocked issues.
2. Gate on dependency readiness. A leaf is ready only when every required predecessor is complete or the canonical note explicitly says it may proceed.
3. Compare effective priority: `P0`, then `P1`, then `P2`, then unclassified.
4. When a dependency has a lower written priority but blocks a higher-priority ready path, inherit the highest downstream priority it unblocks.
5. Within the effective priority, prefer explicit order in the Canonical scheduling note.
6. Then prefer greater direct and transitive unblock impact.
7. Break remaining ties by oldest creation time, then lowest issue number.

Explain the selected issue and its dependency/priority basis in the selection trace. Never implement the umbrella itself.

## State machine and one-transition ticks

Use these logical phases:

- `IDLE`
- `CONTRACT_ADOPTION_REQUIRED`
- `CONTRACT_ADOPTING`
- `CONTRACT_MIGRATION_REQUIRED`
- `CONTRACT_MIGRATING`
- `SELECTING`
- `WORKER_INITIAL`
- `DRAFT_PR`
- `SUPERVISOR_REVIEW`
- `WORKER_REPAIR`
- `WORKER_FINAL_REPAIR`
- `READY_TO_MERGE`
- `MERGING`
- `CLOSING_ISSUE`
- `CLEANUP_PREFLIGHT`
- `CLEANUP`
- `PAUSED`
- `STOP_AFTER_CURRENT`
- `NEEDS_OWNER_INPUT`
- `REPOSITORY_AUTHORITY_REQUIRED`
- `OWNER_ABORT_DECISION_REQUIRED`
- `CLEANUP_BLOCKED`
- `STOPPED`

Every heartbeat tick must first prove the observation baseline unchanged or perform full live reconciliation, then make at most one externally meaningful state transition. Commands sent directly to the Orchestrator may continue through immediately related read-only checks, but must retain the same idempotence rules. GitHub CLI escalation, bounded connectivity recovery, and heartbeat schedule maintenance are supporting checks: they do not change the phase, consume a review attempt or round, or use the tick's transition allowance.

Do not start another issue while any phase other than `IDLE` or `STOPPED` retains an active issue, branch, worktree, Worker, pull request, unresolved cleanup, or blocking owner decision.

## Claim and implementation

To claim one selected leaf:

1. Recheck that it remains open, eligible, dependency-ready, unignored, and not already claimed by a live Roundlet trace.
2. Record the selection event on the leaf.
3. Create a descriptive `codex/` branch from exact `origin/main` and an isolated worktree.
4. Record the branch, worktree, base SHA, and phase in local state.
5. Create one Worker task with the configured model and effort.
6. Send the Worker the initial contract from `thread-prompts.md`.

Use the same Worker task for every subsequent repair, final repair, and cleanup preflight. The Worker may read GitHub but must never create/edit comments, issues, pull requests, labels, reviews, merges, or branches on GitHub. It modifies the isolated worktree and returns structured handoffs to the Orchestrator.

After a valid initial handoff:

1. Verify the reported before/after SHAs, diff, status, tests, and issue scope independently.
2. Push the exact candidate commit without force.
3. Append the Worker handoff to the leaf issue.
4. Create a draft pull request linking the umbrella with a non-closing reference when present, linking the leaf, and including `Closes #<leaf>` for that active leaf only. Never couple `close`, `closes`, `closed`, `fix`, `fixes`, `fixed`, `resolve`, `resolves`, or `resolved` to an umbrella or any other non-terminal issue number, even inside a negated sentence.
5. Append a draft-pull-request trace to the pull request and update the local recovery index.

If the initial handoff reveals a genuine owner-only decision, enter `NEEDS_OWNER_INPUT`; do not move to a different issue.

## GitHub trace

GitHub is the durable audit trail. The Orchestrator is the sole writer. Worker and Supervisor outputs are proposals until the Orchestrator verifies and publishes them.

Every Roundlet comment starts with one unique marker:

```html
<!-- roundlet:event=<event-id>;run=<run-id>;epoch=<number>;round=<number-or-0>;candidate=<full-sha-or-none> -->
```

Use stable event IDs that identify the intended transition. Before writing, search the live issue or pull request for that event ID and reconcile its contents. If it already records the same transition, do not duplicate it. Never edit or delete a trace to hide a mistake; append a correction event that names the superseded event.

Record at least:

- selection and dependency/ranking rationale on the leaf;
- initial Worker handoff on the leaf;
- draft pull-request creation on the pull request;
- every invalid Supervisor attempt as a bounded availability event naming its attempt, configured profile, task terminal state, review identity, and candidate SHA;
- every valid Supervisor result on the pull request;
- every Worker repair/final-repair handoff on the pull request;
- review terminal result on the pull request;
- owner-input, repository-authority, abort, and correction decisions on the active issue or pull request;
- merge result, leaf closure readback, and cleanup result.

A handoff trace summarizes commit SHA, files, tests, finding dispositions, unresolved risks, and terminal status. For an invalid Supervisor availability event, record a service error identifier only when the task service actually exposes it as a stable typed field; otherwise record `none`. Never infer a cybersecurity, content-policy, or other cause from UI copy, display text, or prose error messages. Do not paste hidden chain-of-thought, credentials, raw task transcripts, blocked response content, or unbounded logs.

## Review epochs and rounds

Start review epoch 1, round 1, bound to the exact pushed candidate SHA. A new allowlisted owner scope change resets to a new epoch at round 1 COMPLETE; ordinary Worker repairs remain in the same epoch.

For every round, keep the review epoch, round, mode, and candidate SHA fixed while attempts advance:

1. Start at attempt 1 or reconcile the last durably recorded attempt after recovery.
2. Select the configured Supervisor attempt profile at that exact one-based position. Never reuse a previous position, skip ahead, or substitute a model or effort.
3. Create a fresh Supervisor task with that exact profile, then give it read-only filesystem and GitHub instructions plus the exact contract in `thread-prompts.md`.
4. Require a structured result bound to the attempt number, profile, review epoch/round/mode, and full candidate SHA.
5. Independently verify that it read the required context, remained read-only, reviewed the named SHA, and returned a valid result for the configured attempt identity.
6. If valid, publish the result to the pull request, archive the task, and follow the normal PASS or FINDINGS path. A valid result from any configured attempt profile has the same review authority.
7. If invalid, archive the task, publish only the bounded availability event, and advance to the next configured profile.

Rounds 1–3 are COMPLETE if reached. Any valid PASS ends review immediately; three rounds are not a minimum.

Rounds 4–10 are CONVERGING. The Supervisor focuses on unresolved prior findings and changes since the previous reviewed candidate, while still reporting a new blocking regression, scope violation, or missing evidence.

`INVALID_CONTEXT`, a failed, cancelled, inaccessible, or restricted task, a missing or malformed result, mutation, incomplete required context, wrong attempt/profile identity, or wrong SHA is invalid and does not consume the round. Reconcile and correct any context mismatch before the next attempt, but preserve the candidate SHA and review round. The invalid attempt consumes only its position in the configured attempt budget; it is never converted into a finding, PASS, or Worker repair request. Route failover from the absence of a valid result, not from a guessed failure category. After `max_supervisor_attempts_per_round` positions are exhausted, enter `NEEDS_OWNER_INPUT` without selecting another issue or merging.

When a valid result has findings before round 10:

1. Send the exact findings to the same Worker.
2. Require a structured repair handoff and a new full candidate SHA.
3. Verify and push without force.
4. Append the Worker handoff to the pull request.
5. Advance to the next review round.

When round 10 has findings:

1. Send the findings once to the same Worker as `WORKER_FINAL_REPAIR`.
2. Verify, push, and publish that handoff.
3. Do not create round 11 and do not state or imply Supervisor PASS.
4. Record terminal state `REVIEW_LIMIT_REACHED_WORKER_FINALIZED`.
5. Continue only through the same live checks and merge gates required after PASS.

When any round returns PASS, record terminal state `SUPERVISOR_PASS` and proceed to merge gating.

## Owner input

`NEEDS_OWNER_INPUT` is a global logical stop, not permission to pick another issue. Retain the lease, Orchestrator, Worker when present, branch, worktree, and pull request. The one heartbeat remains active under `owner_input_noop_backoff_minutes` and only:

- reconciles the current blocking issue and resources;
- looks for a new comment by an identity in `owner_allowlist`; or
- observes a direct instruction in the Orchestrator task.

Do not enter this state for an initial sandbox denial or a transient GitHub CLI transport failure. First exhaust the automatic scoped-escalation and bounded recovery contract. A resulting explicit approval denial, unavailable approval mechanism, confirmed authentication rejection from reachable GitHub, or proven unavailable required connectivity is a valid blocking condition.

An issue-body edit alone never resolves the block. A non-owner comment, reaction, label change, Worker/Supervisor message, or unrelated owner comment never resolves it.

When a valid owner instruction arrives, append an owner-input trace, apply only that instruction, reread all live context, and decide whether it is an ordinary continuation or a scope change requiring a new review epoch.

## Repository authority block

At each mutation boundary, reread the authority block from root `AGENTS.md` on current authoritative `origin/main`. If the required switch is false or ambiguous, enter `REPOSITORY_AUTHORITY_REQUIRED`, retain all current resources, and stop global scheduling.

Release requires either:

- the allowlisted owner performs the blocked action manually and confirms it through a new comment or direct Orchestrator instruction; or
- the authority block is updated on `origin/main` and the allowlisted owner leaves a new comment or direct instruction to reread it.

Never let an issue-body edit or an issue-branch policy change release the block.

## Merge gates

Before marking ready or merging, reread and prove:

- the pull request is open, targets the authoritative primary branch, and names the expected head branch;
- the remote head equals the exact terminal candidate SHA;
- no uncommitted or unpushed Worker change exists;
- review terminal state is either `SUPERVISOR_PASS` or `REVIEW_LIMIT_REACHED_WORKER_FINALIZED`;
- the pull request is mergeable with no conflict;
- every required check for that exact SHA concluded success;
- no new allowlisted owner comment changes scope, requests changes, pauses, stops, or blocks merge;
- GitHub's parsed closing-issue references contain exactly the active leaf and no umbrella or other issue;
- repository authority permits marking ready, merging, and the merge keyword's automatic leaf closure;
- branch rules permit the operation;
- the configured merge method is available and equals `merge`.

If `origin/main` advanced, reread mergeability and repository rules. Merge directly when GitHub considers the branch mergeable, required checks remain valid for the exact candidate, and no rule requires an update. If the branch must be updated, send the same Worker an integration turn. It may merge current `origin/main` into the issue branch; it must not rebase or force-push. The resulting new candidate requires a new review epoch at round 1 COMPLETE.

Mark the pull request ready only when its authority switch is true. Merge using a merge commit only when both `allow_merge_pr` and `allow_close_leaf_issue` are true. Record the resulting merge commit and exact head SHA.

## Leaf closure

The pull request body must include `Closes #<leaf>`, and GitHub must parse exactly that active leaf as the only closing issue. Negation does not make a closing-keyword reference safe; use a plain issue link or `Parent: #<umbrella>` for non-terminal context. After merge:

1. Read the live leaf and verify whether GitHub closed it.
2. If still open and `allow_close_leaf_issue` is true, close it explicitly with a traceable comment.
3. Read it back and require closed state before cleanup.

Never close an umbrella. If the leaf cannot be closed or verified, enter `REPOSITORY_AUTHORITY_REQUIRED` or `NEEDS_OWNER_INPUT` as applicable. Do not schedule another issue, because an open leaf could be selected again.

## Ordered cleanup

Cleanup remains part of the active issue and must be automatic when authorized.

1. Send the same Worker a cleanup-preflight turn. It verifies the issue branch is pushed, the pull request/merge/leaf status, the worktree status, unique commits, untracked files, and absence of unpreserved work. The Worker must not remove its own worktree or delete its own branch.
2. The Orchestrator independently verifies the handoff and archives the Worker task.
3. When `allow_remove_worktree` is true, remove the issue worktree through a non-destructive normal removal. Never force removal of unknown changes.
4. When `allow_delete_local_branch` is true, delete the local issue branch only after proving its unique work is merged or explicitly authorized for abandonment.
5. When `allow_delete_remote_branch` is true, delete the exact remote issue branch only after proving its identity and merge/abandon state.
6. Fetch origin, fast-forward local `main`, and verify the authoritative checkout is clean and `HEAD == main == origin/main`.
7. Append the cleanup trace, clear the issue-specific pointers, reset the same heartbeat to `active_minutes`, and remove the advisory files and retained contract bundles only when stopping; while continuing, retain the lease and set `current.md` to `IDLE` with new observation counters. Do not stop after a completed issue unless stop-after-current is already recorded.

If any cleanup step fails, enter `CLEANUP_BLOCKED`, keep the leaf closed, retain the lease/current evidence, and select no next issue. Never reopen the leaf solely because cleanup failed.

## Active issue closed, ignored, or withdrawn

If the active leaf is closed, gains `roundlet:ignore`, or is withdrawn before the normal merge path completes, enter `OWNER_ABORT_DECISION_REQUIRED`. Accept only a new allowlisted comment or direct Orchestrator instruction choosing:

- `resume`: remove the blocking condition when needed and continue the same work;
- `preserve-and-stop`: keep the task, branch, worktree, pull request, and evidence, pause the heartbeat, and stop scheduling;
- `abandon-and-cleanup`: with exact scope, append a trace, close the pull request if open, archive role tasks, and clean only the explicitly authorized branch/worktree resources before returning to `IDLE`.

There is no preserve-old-work-while-selecting-next option. Never infer abandon-and-cleanup.

## Pause, resume, and stop

- `pause`: finish the current atomic mutation or stop before the next one, record `PAUSED`, pause the heartbeat so it performs no observations, and preserve all state/resources. Resume only in the same Orchestrator after reconciliation and an owner instruction.
- `stop-after-current`: if active, finish the current issue including cleanup; if idle, stop immediately. Then stop the heartbeat, record `STOPPED`, remove advisory state and retained contract bundles after final reconciliation, and archive the Orchestrator.
- An immediate destructive stop is not defined. Use the explicit abort choices for active work.

## Copyable owner commands

Send routine commands to the existing long-lived Orchestrator task. Do not invoke the installed `$roundlet` skill: each prompt first resolves and reads the effective pinned bundle. Do not open a new Launcher, Orchestrator, or heartbeat for status, pause, resume, contract adoption/migration, or stop. Replace every placeholder and keep the target repository and authoritative checkout explicit.

### Inspect status without advancing

```text
In the existing Orchestrator task, inspect the active Roundlet run without advancing it. Resolve and read only the effective pinned contract bundle; do not invoke or load the installed `$roundlet` skill.

Target repository: <OWNER/REPOSITORY>
Authoritative checkout: <ABSOLUTE_PATH>

Address the existing Orchestrator task. Reconcile the live GitHub trace, exact Git state,
Codex task and heartbeat state, `.roundlet/lease.json`, and `.roundlet/current.md`.
Do not create, replace, resume, pause, stop, or archive a task or heartbeat. Do not make a
GitHub or Git mutation and do not perform a Roundlet tick.

Report the run ID, Orchestrator and heartbeat identities, current phase, active leaf and
pull request, Worker and current Supervisor when present, exact candidate SHA, review
epoch/round/attempt/profile, blocking condition, last durable event, and next safe action.
Also report the current heartbeat interval, observation-baseline time, lightweight-tick
count, relevant no-op streak, and whether the last tick used observation or full reconciliation.
Stop on contradictory evidence instead of repairing it.
```

### Pause at a safe checkpoint

```text
In the same long-lived Orchestrator task, pause the existing Roundlet run for <OWNER/REPOSITORY>. Resolve and read only the effective pinned contract bundle; do not invoke or load the installed `$roundlet` skill.

Reconcile live state first. Finish only an already-started atomic mutation, then stop
before the next externally meaningful transition. Record PAUSED, pause the one bound
heartbeat, and preserve the lease, current state, active task identities, branch,
worktree, pull request, and all unique work. Report the exact checkpoint and retained
resources. Do not archive the Orchestrator or select another issue.
```

### Resume the paused run

```text
In the same long-lived Orchestrator task, resume the existing paused Roundlet run for <OWNER/REPOSITORY>. Resolve and read only the effective pinned contract bundle; do not invoke or load the installed `$roundlet` skill.

Reconcile GitHub, Git, task, heartbeat, lease, and current-state evidence before changing
anything. Stop for owner input if identities or state conflict. If reconciliation is
clean, reset and resume the one bound heartbeat at `active_minutes`, leave PAUSED, and perform at most one idempotent
Roundlet tick. Report the before/after phase, transition, active leaf, candidate SHA,
blocking condition, and next safe action. Do not create a replacement task or heartbeat.
```

### Adopt or migrate the pinned contract

When fully reconciled `IDLE` has no leaf resources, use [`between-issue contract adoption`](launcher.md#owner-authorized-between-issue-contract-adoption). Otherwise use [`in-place contract migration`](launcher.md#owner-authorized-in-place-contract-migration). Both keep the same Orchestrator task, require explicit owner authorization for the exact candidate plus task-metadata proof of the actual model/effort override, and make no repository transition.

### Stop after the current issue

```text
In the existing Orchestrator task, set stop-after-current for the active Roundlet run for <OWNER/REPOSITORY>. Resolve and read only the effective pinned contract bundle; do not invoke or load the installed `$roundlet` skill.

Reconcile first and record STOP_AFTER_CURRENT. If an issue is active, finish only that
issue through its normal review, merge gates, leaf closure, and ordered cleanup; select
no next issue. If the run is idle, stop immediately. At the terminal safe state, stop the
one heartbeat, record STOPPED, remove the advisory lease/current files, contract bundles,
and migration records after final reconciliation and read-back, and archive the Orchestrator. Never discard unique work to accelerate
the stop.
```

### Resolve an active issue that was closed, ignored, or withdrawn

Choose exactly one of `resume`, `preserve-and-stop`, or `abandon-and-cleanup`. The last option is destructive and must name the exact resources the owner authorizes Roundlet to remove.

```text
In the existing Orchestrator task for <OWNER/REPOSITORY>, resolve and read only the effective pinned contract bundle; do not invoke or load the installed `$roundlet` skill.

The active leaf is <ISSUE_NUMBER_AND_URL>. After reconciling all live evidence, apply this
owner decision: <resume|preserve-and-stop|abandon-and-cleanup>.

For resume, continue the same work only after the blocking condition is removed. For
preserve-and-stop, retain every task, branch, worktree, pull request, and evidence item,
pause the heartbeat, and stop scheduling. For abandon-and-cleanup, remove only these
explicitly authorized resources: <EXACT_RESOURCE_LIST>. Preserve anything not listed,
append the required trace, and stop on ambiguous or unique work. Report every retained,
removed, and unresolved resource.
```

If the original Orchestrator or heartbeat is inaccessible, do not use a routine command. Use the explicit recovery Launcher in [`launcher.md`](launcher.md#explicit-recovery).

## Recovery

- If an ordinary Orchestrator turn fails but its task and heartbeat remain accessible, the next heartbeat reads the active bundle, reconciles, and resumes idempotently.
- If the Orchestrator or heartbeat is inaccessible, use the explicit recovery Launcher prompt. A stale-looking file is never enough to replace it.
- If the persistent Worker is inaccessible, require owner direction before creating a replacement because same-thread context is part of the contract.
- A failed Supervisor is disposable and may be retried under the bounded attempt rule.

During recovery, verify and read the active contract bundle first, then reconstruct from GitHub trace, exact remote/local Git state, Codex task evidence, and advisory files. Treat installed files only as a migration candidate. Stop on contradictions. Never hide a recovery correction by editing old GitHub comments.
