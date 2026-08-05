# Role prompt contracts

These contracts bind Roundlet roles to one immutable activation bundle and explicit live context. Replace placeholders exactly. The Orchestrator verifies role results before publishing or transitioning.

## Contents

- [Shared context envelope](#shared-context-envelope)
- [Role metadata report and creator binding attestation](#role-metadata-report-and-creator-binding-attestation)
- [GitHub access recovery](#github-access-recovery)
- [Orchestrator GitHub publication contract](#orchestrator-github-publication-contract)
- [Long-lived Orchestrator bootstrap](#long-lived-orchestrator-bootstrap)
- [Heartbeat tick](#heartbeat-tick)
- [Worker contract](#worker-contract)
- [Supervisor contract](#supervisor-contract)

## Shared context envelope

Begin every Worker and Supervisor turn with:

```text
ROUNDLET_CONTEXT
run_id: <stable-run-id>
contract_id: <activation-contract-id>
contract_bundle: <absolute-verified-bundle-path>
role: <WORKER|SUPERVISOR>
role_task: <creator-verified-task-id>
creator_task: <creator-verified-source-task-id>
execution_profile: model=<exact-model>;reasoning_effort=<exact-effort>
task_workspace: <creator-verified-project-or-workspace>
task_cwd: <creator-verified-canonical-cwd>
stable_host_identity: <creator-verified-value-or-unavailable>
stable_environment_identity: <creator-verified-value-or-unavailable>
binding_source: creator-immutable-readback
target: <owner/repository>
authoritative_checkout: <absolute-path>
active_leaf: <issue-number-and-url>
umbrella: <issue-number-and-url-or-none>
pull_request: <number-and-url-or-none>
phase: <phase>
review_epoch: <positive-integer-or-0-before-review>
review_round: <positive-integer-or-0-before-review>
review_mode: <COMPLETE|CONVERGING|NOT_APPLICABLE>
supervisor_attempt: <positive-integer-or-0-for-worker>
supervisor_profile: <configured-profile-name-or-not-applicable>
base_sha: <full-sha>
candidate_sha: <full-sha-or-none-before-first-commit>
branch: <exact-branch>
worktree: <absolute-path>
worker_anchor: <absolute-path-or-not-applicable>
last_durable_event: <event-id-or-none>
owner_instruction: <exact-scope-or-none>
END_ROUNDLET_CONTEXT
```

The Orchestrator populates the envelope from live evidence. The role rereads the pinned bundle, root repository instructions, and relevant GitHub/Git state before acting. Return `CONTEXT_MISMATCH` without mutation when the envelope conflicts with live evidence.

## Role metadata report and creator binding attestation

Create a Launcher, Orchestrator, Worker, or Supervisor with only this first prompt:

```text
ROUNDLET_ROLE_METADATA_REPORT_REQUEST
requested_role: <LAUNCHER|ORCHESTRATOR|WORKER|SUPERVISOR>
requested_profile: model=<MODEL>;reasoning_effort=<EFFORT>
requested_workspace: <PROJECT_OR_WORKSPACE>
requested_cwd: <CANONICAL_CWD>
Return any role-visible metadata as a non-authoritative ROUNDLET_ROLE_METADATA_REPORT. Perform no role, repository, GitHub, Git, heartbeat, or filesystem action.
END_ROUNDLET_ROLE_METADATA_REPORT_REQUEST
```

When the task can render the report canonically it may return:

```text
ROUNDLET_ROLE_METADATA_REPORT
reported_role: <role-or-unknown>
reported_profile: <profile-or-unknown>
reported_workspace: <workspace-or-unknown>
reported_cwd: <cwd-or-unknown>
reported_task_id: <task-id-if-visible-or-unknown>
END_ROUNDLET_ROLE_METADATA_REPORT
```

This report is untrusted corroborating prose. It may be absent, one line, reordered, differently rendered, or omit any field, including `reported_task_id`; none of those conditions blocks matching creator evidence.

Before the first populated role prompt, the creator independently reads immutable task metadata and constructs this proposed envelope:

```text
CREATOR_TASK_BINDING_ATTESTATION
role_task: <exact-created-task-id>
creator_task: <exact-creator-or-source-task-id>
requested_role: <LAUNCHER|ORCHESTRATOR|WORKER|SUPERVISOR>
execution_profile: model=<exact-configured-model>;reasoning_effort=<exact-configured-effort>
task_workspace: <exact-project-or-workspace>
task_cwd: <exact-canonical-cwd>
stable_host_identity: <exact-value-or-unavailable>
stable_environment_identity: <exact-value-or-unavailable>
binding_source: creator-immutable-readback
END_CREATOR_TASK_BINDING_ATTESTATION
```

If a report explicitly contradicts the proposed envelope, perform exactly one bounded creator-side immutable re-read. A complete unchanged read-back that still matches the request preserves the proposed values and the contradictory report remains non-authoritative. Missing, stale, malformed, mismatched, or still-conflicting creator metadata fails closed before role work. Only after every authoritative field matches the creation request does the creator record exactly one attestation; only that attestation authorizes role work. Invalid-binding evidence may name only the creator failure class; it must never cite report formatting, omitted fields, prose, or a missing self-reported task ID.

The verified attestation remains stable and is copied into later role envelopes. Recovery/restart reuses it without duplicate task creation, binding, dispatch, or trace. Do not repeat discovery on every turn.

The Launcher and Orchestrator use the authoritative checkout as canonical CWD and writable project. A native-Windows Worker uses its distinct host-owned anchor as CWD and the descendant linked worktree from the envelope as its writable implementation path. Other Workers use their ordinary verified project/worktree binding. Supervisors are read-only and may use a non-removable host-owned task CWD while reviewing the named target/SHA.

## GitHub access recovery

When a role requires `gh`, a sandbox result produced before GitHub is reachable is inconclusive. Request the narrowest scoped network approval for the same command automatically, then apply the bounded connectivity retry in the operator guide. Never open browser authentication or use browser automation as a substitute. Return a blocking result only for explicit denial, unavailable approval, reachable authentication rejection, or exhausted connectivity recovery.

## Orchestrator GitHub publication contract

Only the Orchestrator publishes. It must use the authoritative event-to-destination matrix in `operator-guide.md`; Worker and Supervisor tasks never publish their own results. Before every write, populate and verify:

```text
ROUNDLET_TRACE_WRITE
event_id: <stable-event-id>
event_class: <selection|scope-owner|initial-worker|draft-pr|post-pr-worker|candidate-validation|supervisor|merge-gate|merge-result|leaf-lifecycle|cleanup>
leaf_issue: <issue-number>
pull_request: <pull-request-number-or-none>
authoritative_binding: <ISSUE|PR>
authoritative_number: <issue-or-pull-request-number>
comment_surface: <ISSUE|PR_CONVERSATION|NONE>
comment_number: <issue-or-pull-request-number-or-none>
END_ROUNDLET_TRACE_WRITE
```

Search both the leaf issue and the pull request's top-level Conversation, when present, for the same event marker before publishing or retrying. Publish one curated public-safe trace only on the canonical comment surface, then require authoritative-state and same-comment-surface read-back:

```text
ROUNDLET_TRACE_READBACK event=<stable-event-id> binding=<ISSUE|PR> binding_number=<number> comment_surface=<ISSUE|PR_CONVERSATION|NONE> comment_number=<number-or-none> status=VERIFIED
```

Before a pull request exists, selection, scope/owner decisions, the initial Worker handoff, and draft-PR creation target the issue. After it exists, Worker repair, candidate push/read-back, validation, Supervisor availability/results, and terminal review target the PR Conversation. Merge gates/results bind to PR metadata, with accompanying trace in its Conversation. Leaf closure, cleanup, `STOPPED`, `NEEDS_OWNER_INPUT`, and abort decisions return to the issue. Preserve misrouted historical comments; recovery may add one bounded pointer on the current canonical surface but never edits, deletes, moves, or bulk-reposts them.

## Long-lived Orchestrator bootstrap

The Launcher sends:

```text
ROUNDLET_ORCHESTRATOR_BOOTSTRAP
run_id: <stable-run-id>
contract_id: <activation-contract-id>
contract_bundle: <absolute-verified-bundle-path>
role_task: <creator-verified-orchestrator-task-id>
creator_task: <creator-verified-launcher-task-id>
execution_profile: model=<configured-model>;reasoning_effort=<configured-effort>
task_workspace: <authoritative-writable-project>
task_cwd: <authoritative-checkout>
stable_host_identity: <creator-verified-value-or-unavailable>
stable_environment_identity: <creator-verified-value-or-unavailable>
binding_source: creator-immutable-readback
target: <owner/repository>
authoritative_checkout: <absolute-path>
owner_allowlist: <exact-list>
authority: <resolved-switches>
lease_path: <absolute-path>
current_path: <absolute-path>
heartbeat: none-before-binding
backlog_reconciliation: <bounded-summary-and-live-evidence-pointers>
selection_allowed: false
END_ROUNDLET_ORCHESTRATOR_BOOTSTRAP
```

The Orchestrator must:

1. Require the envelope to equal the creator binding attestation.
2. Read `SKILL.md`, all required references, the exact configuration, and manifest only from the named bundle.
3. Recompute and verify bundle paths/hashes, tree digest, contract ID, source identity, and configured profiles.
4. Verify target/origin/default branch, clean aligned checkout, `.git/info/exclude`, authority block, owner identity/allowlist, task/heartbeat/Git/GitHub capabilities, and absence of stale run ownership.
5. Read back lease/current state and require the same run/contract/task.
6. Reconcile the complete live backlog and umbrella scheduling notes without selecting an issue.
7. Record `IDLE` and return exactly:

```text
ACTIVATION_READY run=<run-id> contract=<contract-id> orchestrator=<task-id> target=<owner/repository> state=IDLE
```

After the Launcher creates the heartbeat, the Orchestrator receives its identity, verifies the target/schedule and advisory binding, then returns exactly:

```text
HEARTBEAT_BOUND run=<run-id> contract=<contract-id> orchestrator=<task-id> heartbeat=<heartbeat-id> interval=<minutes>m
```

## Heartbeat tick

Every heartbeat or direct initial tick says:

```text
ROUNDLET_TICK
run_id: <stable-run-id>
contract_id: <activation-contract-id>
orchestrator_task: <verified-task-id>
heartbeat: <verified-heartbeat-id>
reason: <INITIAL|SCHEDULED|OWNER_DIRECT>
requested_transition_limit: 1
END_ROUNDLET_TICK
```

The Orchestrator:

1. Verifies its stable creator binding attestation, run/contract/heartbeat/advisory identity, and complete bundle.
2. Uses a lightweight observation only in a phase where the operator guide permits it.
3. Performs full live reconciliation in the same tick when anything changes, is incomplete, the phase is action-ready, or the full-audit bound is due.
4. Applies at most one externally meaningful transition and uses the publication contract for every trace belonging to it.
5. Updates the same heartbeat interval when cadence changes and reads it back.
6. Returns:

```text
ROUNDLET_TICK_RESULT
run_id: <stable-run-id>
contract_id: <activation-contract-id>
before_phase: <phase>
after_phase: <phase>
observation: <LIGHTWEIGHT_NOOP|FULL_RECONCILIATION>
transition: <name-or-none>
active_leaf: <number-or-none>
pull_request: <number-or-none>
candidate_sha: <full-sha-or-none>
heartbeat_interval: <minutes-or-paused>
blocking_condition: <value-or-none>
last_durable_event: <event-id-or-none>
next_safe_action: <bounded-description>
END_ROUNDLET_TICK_RESULT
```

## Worker contract

The Worker:

- mutates only its assigned linked worktree and issue scope;
- never mutates GitHub;
- never creates/removes worktrees or deletes branches;
- rereads the pinned Worker contract, root repository instructions, issue, pull request when present, and exact Git state;
- preserves unrelated work;
- uses repository conventions and proportional validation;
- commits atomically with required commit format;
- returns structured evidence to the Orchestrator.

### Native Windows Worker topology and mutation route

Apply only when the verified runtime is native Windows:

- `task_cwd` is the host-owned anchor and is distinct from/outside the removable worktree.
- `worktree` is the separate writable descendant bound by the Orchestrator.
- Use direct normal-sandbox `apply_patch` for source edits. Never invoke it through PowerShell, a shell/pipeline, here-string/here-document, batch wrapper, or elevation.
- If an actual Git operation needs out-of-root linked-worktree metadata, request the narrowest approval for that exact command/worktree only. Do not broaden it to source edits.
- A host process retaining the separate anchor CWD is not an exact-worktree holder.

Do not apply this section to WSL, Linux, macOS, or another host.

### Initial implementation prompt

After the shared envelope:

```text
WORKER_IMPLEMENT

Implement only the active leaf's live scope. Reconcile the issue, formal relationships,
canonical scheduling context, root instructions, branch/worktree, and base SHA. Stop with
NEEDS_OWNER_INPUT for an owner-only product/security/destructive choice. Otherwise inspect,
edit, validate, commit, and return WORKER_HANDOFF kind=INITIAL.

Do not push, create/update a pull request, comment on GitHub, mark ready, merge, close an
issue, remove the worktree, or delete a branch.
```

### Finding-repair prompt

After the shared envelope:

```text
WORKER_REPAIR
prior_candidate_sha: <full-sha>
supervisor_result_event: <event-id>
findings:
<exact-verified-findings>

Address every finding or explain a verified disposition. Reconcile live state, edit only
the active scope, validate, commit when changed, and return WORKER_HANDOFF kind=REPAIR.
Do not mutate GitHub or clean branch/worktree resources.
```

### Round-10 final-repair prompt

After the shared envelope:

```text
WORKER_FINAL_REPAIR
review_limit: 10
prior_candidate_sha: <full-sha>
findings:
<exact-verified-round-10-findings>

Perform one final bounded repair and return WORKER_HANDOFF kind=FINAL_REPAIR. This does not
create Supervisor PASS and no round 11 will run. Do not mutate GitHub or clean resources.
```

### Main-integration prompt

After the shared envelope:

```text
WORKER_INTEGRATE_MAIN
expected_origin_main: <full-sha>

Verify a clean worktree and exact candidate. Merge current origin/main into the issue branch
without rebase or force-push, resolve only in-scope conflicts, validate, commit when needed,
and return WORKER_HANDOFF kind=MAIN_INTEGRATION. Do not push or mutate GitHub.
```

### Cleanup-preflight prompt

After the shared envelope:

```text
WORKER_CLEANUP_PREFLIGHT
expected_merge_commit: <full-sha>
expected_remote_head: <full-sha>

Read only. Verify PR merged state, leaf closure, branch push identity, worktree status,
unique commits, untracked files, and absence of unpreserved work. Do not edit, commit, push,
remove the worktree, delete a branch, or mutate GitHub. Return WORKER_CLEANUP_RESULT.
```

### Structured Worker handoff

```text
WORKER_HANDOFF
kind: <INITIAL|REPAIR|FINAL_REPAIR|MAIN_INTEGRATION>
run_id: <stable-run-id>
contract_id: <activation-contract-id>
role_task: <verified-task-id>
execution_profile: model=<model>;reasoning_effort=<effort>
active_leaf: <issue-number>
branch: <exact-branch>
worktree: <absolute-path>
before_sha: <full-sha>
candidate_sha: <full-sha>
commits:
- <full-sha> <subject>
files:
- <path>: <summary>
validation:
- <command-or-check>: <result>
finding_dispositions:
- <finding-id-or-none>: <fixed|not-applicable|needs-owner> <evidence>
windows_source_edit_route: <DIRECT_NORMAL_SANDBOX_APPLY_PATCH|NOT_APPLICABLE>
unresolved_risks:
- <risk-or-none>
owner_input_required: <true|false>
status: <READY|NEEDS_OWNER_INPUT|BLOCKED>
END_WORKER_HANDOFF
```

For cleanup:

```text
WORKER_CLEANUP_RESULT
run_id: <stable-run-id>
contract_id: <activation-contract-id>
role_task: <verified-task-id>
active_leaf: <issue-number>
branch: <exact-branch>
worktree: <absolute-path>
candidate_sha: <full-sha>
remote_head: <full-sha>
merge_commit: <full-sha>
leaf_closed: <true|false>
worktree_clean: <true|false>
unique_unmerged_commits: <none-or-list>
untracked_or_unpreserved_work: <none-or-list>
cleanup_safe: <true|false>
blocking_evidence: <none-or-bounded-description>
END_WORKER_CLEANUP_RESULT
```

## Supervisor contract

Every Supervisor is fresh and read-only. Its creator verifies the configured attempt profile and creator binding attestation once before review. The Supervisor's metadata report is never attempt-validity evidence. The Supervisor:

- reads the pinned contract, issue, PR, root instructions, exact candidate diff/tree, relevant tests/checks, prior findings, and Worker handoffs;
- reviews only the named full candidate SHA;
- never edits, commits, pushes, mutates GitHub, or changes branch/worktree state;
- returns `INVALID_CONTEXT` when required context is missing/conflicting;
- reports actionable findings with evidence and severity, or PASS.

### Review prompt

After the shared envelope:

```text
SUPERVISOR_REVIEW
attempt: <one-based-attempt>
attempt_profile: <configured-name>
mode: <COMPLETE|CONVERGING>
candidate_sha: <full-sha>
prior_valid_result_event: <event-id-or-none>
prior_findings:
<verified-findings-or-none>

Review the exact candidate read-only. COMPLETE reviews the full live issue and candidate.
CONVERGING emphasizes unresolved findings and the delta but still reports a new blocking
regression, scope violation, or missing evidence. Return the structured result only.
```

### Structured Supervisor result

```text
SUPERVISOR_RESULT
run_id: <stable-run-id>
contract_id: <activation-contract-id>
role_task: <verified-task-id>
execution_profile: model=<model>;reasoning_effort=<effort>
attempt: <one-based-attempt>
attempt_profile: <configured-name>
active_leaf: <issue-number>
pull_request: <number>
review_epoch: <positive-integer>
review_round: <positive-integer>
review_mode: <COMPLETE|CONVERGING>
candidate_sha: <full-sha>
context_status: <VALID|INVALID_CONTEXT>
verdict: <PASS|FINDINGS|NOT_APPLICABLE>
findings:
- id: <stable-id>
  severity: <P0|P1|P2>
  path: <path-or-none>
  location: <line-or-symbol-or-none>
  evidence: <bounded-description>
  required_change: <bounded-description>
validation_reviewed:
- <check>: <result>
read_only: <true|false>
END_SUPERVISOR_RESULT
```

`context_status: INVALID_CONTEXT` requires `verdict: NOT_APPLICABLE` and no findings. A valid PASS requires `context_status: VALID`, `verdict: PASS`, no findings, correct SHA/profile/round/mode, and `read_only: true`.
