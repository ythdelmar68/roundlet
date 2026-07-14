# Roundlet operator guide

## Contents

1. Authority model
2. Install and pin Roundlet
3. Prepare one target repository
4. Synchronization and worktree gate
5. Connector, Git, thread, and permission preflight
6. Install narrow command rules
7. Activate an umbrella scope
8. Verify dependency selection
9. Run the manual smoke path
10. Attach the heartbeat
11. Observe normal operation
12. Pause for Roundlet maintenance
13. Maintain and install Roundlet
14. Resume directly or with assistance
15. Recover idempotently
16. Handle blockers
17. Retain and compact state
18. Complete or replace scope

## Authority model

Keep these independent:

1. The Roundlet source repository governs Roundlet development and publication.
2. The current target repository's trusted instructions govern target work.
3. Codex sandbox, approval policy, permission profile, and command rules bound local capabilities.
4. The GitHub connector authorizes and performs GitHub operations.
5. Host Git credentials and GitHub branch protection constrain fetch, push, checks, and merge.

An explicit target activation authorizes only its current repository, base branch, ordered umbrella set, enabled operations, activation ID, installed digest, and protocol/policy versions. It never authorizes Roundlet source maintenance, installation, another repository, or an omitted mutation.

Treat `approval_policy = "never"` as "do not prompt." It does not grant network, filesystem, connector, organization, or GitHub authority. Fail closed when any layer denies an expected unattended action.

## Install and pin Roundlet

Install only a reviewed source commit or tag after its pull request has explicit owner approval and is merged. Do not install a dirty checkout, unreviewed feature branch, floating default branch, or target-repository candidate.

Record:

- canonical source repository and reviewed commit/tag;
- resolved full commit SHA;
- content digest from `scripts/orchestration_state.py` `skill_content_digest`;
- state, protocol, review-contract, and policy versions;
- installation path and installed `SKILL.md` path.

Place or symlink the exact reviewed skill directory in a user/admin skill location outside every target repository and target worktree. Require the installed files to be read-only to target Workers, or enforce equivalent write isolation. Never make a repository-local skill copy the active runtime: a target candidate could otherwise change the next invocation's contract. Verify that Codex discovers `$roundlet`; restart Codex only when discovery does not refresh automatically.

Never copy credentials, local runtime state, test caches, Git metadata, or an unreviewed rules file with the installation.

Before activation, compute and record the installed digest from the installed directory itself:

```text
python3 <installed-roundlet>/scripts/orchestration_state.py skill-digest \
  --skill-root <installed-roundlet>
```

For a new activation, call `skill_content_digest(<installed-roundlet>)` before creating state. The guarded CLI later compares this digest to both the activation and installed files.

## Prepare one target repository

Open a dedicated Codex project/worktree for exactly one target repository. Do not pass a repository name to Roundlet.

Have the target owner independently adopt restrictive trusted instructions that require:

- explicit `$roundlet` invocation in a dedicated Orchestrator task;
- binding to current-repository identity, exact base, umbrella scope, operations, activation, digest, and versions;
- connector-mediated GitHub mutations by the root Orchestrator only;
- exact-head fresh Supervisor PASS and Worker `READY_TO_MERGE` before merge;
- merge commit, exact selected-issue closure, and ownership-proven cleanup;
- fail-closed behavior for policy drift, cross-repository targets, stale review, failed checks, ambiguity, unique work, or cleanup proof failure;
- permanent denial of force push, reset, rebase, releases, tags, publishing, version bumps, issue deletion, unrelated mutation, protection bypass, and deletion of unique work.

Do not let Roundlet edit or weaken target instructions, protection, required checks, or connector policy during activation.

Add `.codex-log/roundlet/` to the target repository's ignored runtime paths before activation. Commit that governance change through the target's normal review process; do not fold it into an automatically selected task unless explicitly scoped.

## Synchronization and worktree gate

Perform this gate before the dedicated Orchestrator, every Worker dispatch, resume, and next-task selection:

1. Resolve the Git root with `git rev-parse --show-toplevel`.
2. Resolve the common directory with `git rev-parse --git-common-dir`.
3. Resolve exactly one `origin`, canonical owner/name, and repository ID when the connector supplies it.
4. Fetch exactly `git fetch origin <base-branch>`.
5. Resolve full SHAs for `HEAD`, `refs/heads/<base>`, and `refs/remotes/origin/<base>`.
6. Require a clean orchestration checkout and equality of all three SHAs.
7. Inspect `git worktree list --porcelain` and the status/ownership of every current-repository worktree.

Block on:

- missing or ambiguous origin;
- detached context that cannot be tied to this Git common directory;
- repository ID or origin fingerprint mismatch;
- dirty, ahead, behind, or diverged orchestration checkout;
- dirty/uncommitted, unmerged, uniquely owned, or ambiguously owned worktree;
- unrelated active work that could conflict with the selected branch or files.

Never switch, reset, clean, rebase, delete, or otherwise mutate another checkout to make the gate pass. Let the owner finish or explicitly disposition that work first.

The dedicated Orchestrator checkout may be detached at the exact remote-base SHA when the owner's primary checkout already holds the local base branch. In that case, the guarded refresh/sync advances only detached HEAD and accepts a stale local base ref only while `git worktree list --porcelain` proves another worktree owns it. Treat equality by full commit identity, and do not advance another checkout behind the owner's back.

## Connector, Git, thread, and permission preflight

Verify each expected capability with the same identity and permission mode that the heartbeat will use.

### GitHub connector

Verify current-repository-only reads for:

- umbrella and sub-issue body, comments, formal relationships, state, and revisions;
- PR metadata, discussion, diff, head/base, checks, mergeability, conflict, and merged state;
- existing branch/PR ownership evidence.

Verify the exact authorized writes for:

- curated issue and PR comments;
- draft PR creation;
- draft-to-ready transition;
- merge method `merge` with expected full head SHA;
- exact selected-issue close after merge;
- exact recorded remote-branch deletion after cleanup proof.

Do not silently fall back to `gh`, shell HTTP, a different connector, or a credential copied into the project.

### Host Git credentials

Verify unattended:

- exact base fetch;
- push of one recorded `codex/` task branch;
- fast-forward-only synchronization;
- safe local branch deletion after merged reachability.

Do not store the credential, helper path, token, or authentication output in state, mailboxes, prompts, or GitHub comments.

### Codex tasks and schedule

Verify the root Orchestrator can:

- create a project worktree Worker with explicit model/reasoning;
- create a fresh local-project read-only Supervisor each round;
- continue the same Worker task;
- inspect and archive child tasks;
- attach, pause, update, and reactivate one schedule on the existing Orchestrator task.

### Permissions

Prefer `workspace-write` with narrow reviewed rules. Verify every exact operation can run unattended. If managed policy disallows the expected mode or non-interactive approval behavior, stop before activation.

## Install narrow command rules

Treat `assets/roundlet.rules` as an inert reviewed template. Copy it to the target's trusted project rules layer only as a separate owner-reviewed setup action.

Replace every placeholder with an absolute immutable value:

- `<PYTHON>`: exact approved Python executable;
- `<ROUNDLET_SCRIPT>`: exact installed `orchestration_state.py` path;
- `<SKILL_ROOT>`: exact installed reviewed skill root;
- `<STATE_DIR>`: exact target `.codex-log/roundlet` directory;
- `<ACTIVATION_ID>`: exact active ID;
- `<INSTALLED_DIGEST>`: exact installed content digest;
- `<BASE_BRANCH>`: exact resolved base branch;
- `<TARGET_ROOT>` and `<TASK_WORKTREE>` where present.

Keep each rule's `match` and `not_match` examples and test it with `codex execpolicy check`. Confirm:

- only the exact `guarded-refresh` invocation may perform the validated base fetch;
- guarded push permits only the state-recorded current-repository `codex/` branch;
- guarded sync uses fetch plus fast-forward-only merge;
- worktree removal and local branch deletion call the guarded script and prove ownership;
- arbitrary Python, shell, repository, branch, worktree, remote, `git push`, force, reset, rebase, and remote deletion do not match.

These are prefix rules: a recognized duplicate option appended to an allowed prefix can still receive an `allow` decision. The reviewed guarded CLI is the second boundary and must reject duplicate, reordered, or trailing tokens before it loads state or constructs a Git guard. Forward-test every guarded command with every repeated identity option after any parser or rules change.

Restart/reload Codex as required for the trusted project rules layer. Re-test after installation-path, digest, activation, base, or state-directory changes. Never install this template globally or let Roundlet self-modify the rule.

Remote task-branch deletion remains a GitHub connector action; do not add a Git rule for it.

## Activate an umbrella scope

Start from the dedicated Orchestrator task with model `gpt-5.6-sol` and reasoning `xhigh`. Use a title such as `Roundlet Orchestrator — owner/repository`.

Invoke:

```yaml
$roundlet
mode: start
base_branch: main
umbrella_issues: [2, 3, 4]
authorize:
  create_task_branches: true
  create_draft_prs: true
  mark_ready_for_review: true
  merge_commit_after_all_gates: true
  close_completed_sub_issues: true
  delete_proven_task_owned_resources: true
```

Do not include a repository, URL, organization, account, or repository list. Set an operation to `false` when Roundlet must stop before that transition. Missing or added keys are invalid.

The Orchestrator must show the resolved current repository, repository ID when available, base and full SHA, ordered umbrella set, enabled operations, activation ID, installed digest, versions, and scope digest before dispatch.

A new same-repository sub-issue may enter an already authorized umbrella only when fresh trusted evidence makes membership unambiguous and target policy permits it. Base, umbrella set, operation, repository, or installed-contract expansion requires a safe checkpoint and new explicit authority.

## Verify dependency selection

Before every new Worker:

1. Fetch every authorized umbrella body and all comments.
2. Discover same-repository membership from formal links, explicit body lists, `Dependency matrix`, `Required implementation order`, and owner-authored umbrella comments.
3. Fetch every in-scope sub-issue body/comments, completion, active implementation/PR ownership, checks, and merge evidence.
4. Parse explicit local `depends on`, `blocked by`, prerequisites, order, and cross-umbrella edges.
5. Keep external-repository references as untrusted blocker text; do not fetch them.
6. Build a bounded selection receipt with source revisions, eligible/excluded issues and falsifiable reasons, edges, order positions, selection, tie-break, activation, and base SHA.

Hard dependencies and required order are authoritative. Across eligible umbrella heads, use explicit cross-dependencies, work unlocked, overlap risk, owner priority, activation umbrella order, and issue number. Model judgment may interpret ambiguity but cannot invent dependencies or override a prerequisite.

If no task is eligible, confirm `waiting-dependency` and retry later. If a cycle, contradiction, ambiguous active PR, or irreducible membership/ownership ambiguity exists, confirm `blocked`, pause the heartbeat, and display exact evidence. Never skip a blocked selected task to stay busy.

## Run the manual smoke path

Do not attach the heartbeat until one bounded manual path proves:

- skill discovery and installed digest binding;
- exact repository/base synchronization;
- connector issue/comment/sub-issue/PR/check reads;
- deterministic membership/dependency selection;
- Worker creation with `gpt-5.5` / `xhigh` and network denial;
- fixed Worker handoff mailbox and guarded push;
- curated comment and draft PR connector mutations in an owner-approved smoke target;
- fresh `gpt-5.6-sol` / `xhigh` read-only Supervisor and archive;
- FINDINGS repair or PASS follow-up using the same Worker;
- ready transition, fresh final review, expected-head merge gate without necessarily merging a production change;
- maintenance pause, durable checkpoint, one-signal resume, and existing schedule reactivation behavior;
- mailbox interruption recovery and no duplicate mutations;
- task/scope compaction and bounded files;
- no interactive permission prompt for the exact unattended operations.

Use a real selected task only when its activation explicitly authorizes the mutations. Otherwise stop the smoke path before unauthorized transitions and record the missing owner decision.

## Attach the heartbeat

After the manual smoke path, attach exactly one five-minute schedule to the existing dedicated Orchestrator task. Do not create a standalone task per poll.

Use a durable prompt equivalent to:

```text
$roundlet
Resume the exact activation from .codex-log/roundlet/state.json. Validate current-repository, activation, installed digest, and durable phase. Perform at most one externally visible transition. Before a new Worker dispatch, refresh the full authorized umbrella scope through the GitHub connector and select deterministically. Wait when a child/check/retry is pending. Pause the existing schedule on paused-maintenance, scope-complete, or permanent blocked. Never create another Orchestrator or schedule.
```

Keep the original cadence and schedule ID in state. Review the first several wakes. Confirm that each wake either waits safely or completes one durable transition and receipt.

Scheduled local work requires the machine to remain powered on, the desktop app running, and the project path available.

## Observe normal operation

Expect this lifecycle:

```text
select -> Worker -> draft PR -> fresh Supervisor
  FINDINGS -> same Worker repair -> fresh Supervisor (repeat)
  PASS -> same Worker disposition -> ready -> fresh final Supervisor
  final PASS + READY_TO_MERGE + live gates
  -> merge commit -> exact issue close -> proven cleanup -> sync -> select
```

Every candidate change invalidates PASS. Every Supervisor uses a new task. Immediately read that task back from the task service and durably bind the exact returned task ID and UTC creation time to the next review generation; this is external creation evidence, not a value the Orchestrator may invent. Archive and record each Supervisor immediately after consuming its result, before creating the next one. A bounded recent-ID ledger and rolling archive digest retain freshness evidence without imposing a review-round limit. Before creating any Worker branch, worktree, or task, verify `create_task_branches` both at the external callback boundary and in durable assignment. After draft PR creation or recovery, connector read-back must prove the exact PR is open and still draft before recording it. The Worker task persists until merge/cleanup. The root Orchestrator alone mediates connector reads and writes.

Use curated GitHub comments. Keep raw child prompts, raw transcripts, hidden reasoning, credentials, local paths, checkpoint internals, and internal ranking chains local and bounded.

After the exact merge and issue-close receipts, clean up in this order: archive every remaining Supervisor and the task-owned Worker and call `record_children_archived`; require the recorded worktree's live current branch and exact porcelain branch entry to equal the task branch, then run guarded removal and save `worktree_removed`; run guarded safe local-branch deletion and save `local_branch_deleted`; then delete only the exact recorded remote task branch through the connector and save `record_remote_branch_deleted`. Detached, switched, ambiguous, or uniquely owned work blocks cleanup. Do not enter `sync-base` until all five durable cleanup flags are true. An already absent local resource is success only when the guard independently proves the same task ownership and merged reachability.

## Pause for Roundlet maintenance

In the existing dedicated Orchestrator task, send:

```yaml
$roundlet
mode: maintenance-pause
reason: <short reason>
```

Wait for visible acknowledgement:

```text
PAUSED_FOR_MAINTENANCE
checkpoint_id: <id>
activation_id: <id>
current_task: <issue or none>
pr: <url or none>
installed_roundlet_digest: <digest>
resume_prompt: <exact copy/paste prompt>
```

The Orchestrator must stop new selection, finish/reconcile an atomic mutation, drain the Worker at a clean safe turn boundary with `drain_worker_for_maintenance`, or invalidate/archive an interrupted Supervisor with `discard_supervisor_for_maintenance`. The drain records whether the same Worker turn must be reactivated; discarding a Supervisor restores `draft-pr` or `ready` so a new Supervisor can be created. Consume/quarantine complete mailboxes, prove no child is mutating, durably store the checkpoint, and pause the single schedule.

Do not begin source maintenance until this acknowledgement appears. For urgent interruption, require stricter reconciliation and a fresh Supervisor for uncertain review identity.

## Maintain and install Roundlet

Maintenance authority comes from the Roundlet source repository owner, not the paused target activation.

1. Synchronize a dedicated Roundlet maintenance checkout with its default branch.
2. Inspect and preserve unrelated worktrees.
3. Create an isolated maintenance branch/worktree following repository conventions.
4. Implement only the approved source change.
5. Run deterministic tests, quick validation, static prohibition scans, rule checks, and forward tests.
6. Create focused Conventional Commits, push, and open a reviewed PR.
7. Obtain explicit owner approval before merge.
8. Merge through the source repository's normal gates.
9. Prove the maintenance branch/worktree is clean and merged before safe reclamation.
10. Synchronize the dedicated source maintenance checkout.
11. Install the exact reviewed commit/tag and compute the installed content digest.

Do not ask the paused target Orchestrator to self-update, infer installation, or activate a floating version.

## Resume directly or with assistance

Prefer the same Orchestrator task:

```yaml
$roundlet
mode: maintenance-resume
checkpoint_id: <checkpoint-id>
installed_roundlet_digest: <reviewed-installed-digest>
```

One explicit signal is sufficient. The Orchestrator must then:

- verify checkpoint, repository, activation, umbrella, base, selected task, and installed digest;
- verify reviewed source merge and installed contents;
- require the target orchestration checkout clean and synchronized;
- compare state/schema/protocol/review/policy versions;
- atomically run only a declared supported migration while preserving the original on failure;
- refresh current-repository issues, comments, PR, discussion, checks, mergeability, merge state, and branch identity;
- reconcile the same Worker, its worktree/branch/base/candidate/clean state, and complete unconsumed mailbox;
- discard incomplete/stale Supervisor identity and create a fresh one when required;
- invalidate PASS for candidate uncertainty or changed review/gate semantics;
- preserve PASS only when connector read-back proves a merged PR in the independent reviewed Roundlet source repository changed exactly `references/operator-guide.md`, and the candidate, schedule, pending action, receipts, and protocol/review/policy contract are unchanged;
- repair mutation receipts before a new visible action;
- resume the recorded durable phase;
- reactivate the same schedule/cadence and restore its normal heartbeat prompt.

Expect:

```text
RESUMED_FROM_MAINTENANCE
checkpoint_id: <id>
phase: <restored phase>
worker: <task id or none>
pr: <url or none>
candidate_sha: <sha or none>
pass_valid: <yes/no>
installed_roundlet_digest: <digest>
next_transition: <bounded action>
```

If working from another Codex task, locate the existing task titled `Roundlet Orchestrator — owner/repository` and send the same resume prompt to it. Do not create another Orchestrator, checkout, state directory, or schedule.

When only the Schedule UI is available, update the paused schedule prompt with the resume fields and reactivate it once. Editing the prompt alone does not wake a paused schedule. After success, restore the normal durable heartbeat prompt.

## Recover idempotently

Treat `state.json` as the sole machine state. Children return structured role handoffs; only the root Orchestrator wraps them with repository/role/thread/phase/SHA/idempotency metadata and writes fixed mailbox names in its state directory. Overwrite only consumed payloads.

For every mailbox:

1. Validate protocol/review versions, activation, selected task, phase, source role/task, base, candidate, and idempotency key. Per mailbox kind, the key must end in a decimal sequence starting at 1 and increasing by exactly 1 (for example, `worker-handoff-000001`).
2. Check durable receipts and connector read-back before repeating a mutation.
3. If completion is proven, record/repair the receipt and phase, then delete the mailbox.
4. If no mutation exists, perform it once, verify when possible, atomically record state, then delete.
5. If mutation identity is ambiguous, block instead of retrying.

The durable per-kind high-water mark advances with a new mutation intent. A pending intent must be reconciled before the next sequence. Byte-aware rolling compaction may remove full completed receipts, but it folds their identity into an archive count/digest; every sequence at or below the high-water mark remains permanently consumed for that activation. Never use UUID-only keys, skip a number, reset a sequence between tasks, or treat a missing compacted receipt as permission to mutate again.

Resume only from durable observable state: immutable commits, Git status, task IDs, PR identity, connector state, mailbox/receipt, installed digest, and phase. Do not claim recovery from the middle of model generation.

## Handle blockers

Classify and respond:

| Condition | Action |
| --- | --- |
| Child still running | Wait for next heartbeat. |
| Rate limit or pending check | Record bounded retry metadata and retry later. |
| Connector auth/permission failure | Pause/block with exact authorization repair. |
| Git credential failure | Pause/block; repair host helper outside state. |
| Admin policy denies unattended operation | Block before start or pause safely. |
| Malformed child protocol | Reject result and request a fresh role turn. |
| Stale Supervisor candidate | Discard and create a fresh Supervisor. |
| Failed test/check or conflict | Return safely actionable work to the same Worker. |
| Ambiguous PR/branch/comment/membership/cleanup | Block with evidence. |
| Incomplete dependency | Enter `waiting-dependency` and retry. |
| Cycle/order contradiction | Block the full active scope. |
| Selected task is unimplementable | Block; do not select a later task. |
| Migration unavailable/fails | Preserve original state and remain paused. |
| Resume signal absent | Remain paused; do not infer completion. |
| Scope expansion requested | Reach a safe checkpoint and require new activation. |

Never substitute a model, provider, connector, credential, repository, or task-selection policy to bypass a blocker.

## Retain and compact state

Keep local storage bounded to:

- one `state.json`, capped at 1 MiB;
- at most three fixed transient mailbox files, each capped at 128 KiB;
- mutation receipts capped at 64 KiB inside state;
- one `last-scope-summary.json`, capped at 1 MiB.

Compact completed mutation receipts by serialized byte budget as well as count, while preserving unread mailboxes, pending intents, the per-kind high-water marks, and rolling archive count/digest. Keep at most the bounded recent Supervisor ID ledger; fold immediately archived Supervisor identities into their rolling count/digest.

After a merged task, retain only umbrella/issue, public issue/PR URLs, merge SHA, review-round total, completion time, and final result. Remove full source content, selection detail, prompts, reviews, changed-file detail, archived child IDs, mailboxes, receipts no longer needed, and superseded maintenance detail.

Archive Supervisor tasks immediately after consumption and the Worker after merge/cleanup. Do not create local transcript archives or assume service-side task history can be hard-deleted.

After scope completion, write one summary, empty mailboxes, compact state to a completed header/summary pointer, and pause the schedule. Replace the prior state and summary on the next explicit activation rather than accumulating history.

## Complete or replace scope

Declare completion only after one final full connector refresh proves:

- no authorized open sub-issue still requires implementation;
- completion/merge evidence is verified;
- no active task, PR ownership ambiguity, branch, worktree, child task, or pending mutation remains;
- the dedicated checkout is clean and effectively synchronized: checked-out base/HEAD/local/remote are equal, or detached HEAD equals the remote base while another worktree provably owns the local base ref.

Then enter `scope-complete`, compact, and pause the one heartbeat.

To change repository, base, umbrella list, or operations, complete or safely checkpoint the current task, end the old activation, open the desired repository as the active project, pass synchronization/preflight again, and invoke a new explicit `mode: start`. Never carry state or authority across Git common directories.
