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
task_route: <LOCAL_PROJECT|PROJECT_WORKTREE|PROJECTLESS_NONREPOSITORY>
requested_saved_project: <creator-resolved-project-id-and-canonical-path-or-not-applicable>
task_workspace: <creator-verified-project-or-workspace>
task_cwd: <creator-verified-canonical-cwd>
git_common_dir: <creator-verified-common-dir-or-not-applicable>
starting_ref: <creator-verified-existing-ref-or-not-applicable>
starting_sha: <creator-verified-full-sha-or-not-applicable>
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
branch: <exact-candidate-ref; checkout-is-detached>
worktree: <absolute-path>
last_durable_event: <event-id-or-none>
last_supervisor_result_event: <verified-event-id-or-none>
last_worker_repair_handoff_event: <verified-event-id-or-none>
owner_instruction: <exact-scope-or-none>
validation_toolchain_contract: <repository-defined-summary-or-not-applicable>
validation_cache_root: <absolute-path-or-not-applicable>
external_validation_route: <none|toolbox|toolbox+disposable-target>
external_validation_authority: <allow_external_validation_read_only=true-or-false;allow_external_validation_disposable_target_mutation=true-or-false>
external_validation_binding: <authoritative-path/blob/repository/commit/action/read-back-summary-or-not-applicable>
external_validation_executor: <repository-owned-contract-version/path/blob/entrypoint/identity-or-not-applicable>
external_validation_state: <NOT_APPLICABLE|UNPREPARED|PREFLIGHT_READY|ARMED|EXECUTED|VERIFIED|STALE>
external_validation_schema_binding: <executor-declared-readiness/result-schema-identities-and-digests-or-not-applicable>
external_validation_sequence: <opaque-repository-owned-epoch/round/attempt/session/turn-summary-or-not-applicable>
external_validation_plan: <public-safe-candidate/case/plan/evidence-time/consumption-summary-or-not-applicable>
historical_evidence_time: <repository-field-and-captured-value-or-not-applicable>
lifecycle_observation_sink: <authoritative-contract-path/blob/entrypoint/producer/store-summary-or-not-selected>
lifecycle_observation_state: <NOT_SELECTED|UNARMED|ARMED|APPENDING|SEALED|VERIFIED|STALE>
lifecycle_observation_window: <plan/window/candidate/capture-time/formal-review-binding-or-not-applicable>
lifecycle_observation_head: <append-sequence/event-head/entry-head/seal/retention-receipt-summary-or-not-applicable>
END_ROUNDLET_CONTEXT
```

The Orchestrator populates the envelope from live evidence. The `role` field must equal the attestation's `requested_role`; the other creator-binding fields must equal the same recorded attestation exactly. For a repository role, `task_route` is `PROJECT_WORKTREE`; the creator-requested saved project, actual task CWD, Git common directory, starting ref, and starting SHA form one binding. `starting_ref` is the existing ref requested by the creator and proven to resolve to `starting_sha`; it does not imply the App checkout is attached to that ref. Require detached `HEAD`. An immutable task record may omit its project ID; preserve that field as unavailable instead of inventing it, while requiring the creator request and Git/CWD/SHA read-back to reconcile. `external_validation_schema_binding` and `external_validation_sequence` come only from the exact repository-owned executor binding and typed receipts. Lifecycle observation fields come only from the exact repository-owned sink receipts. Neither external sequence may populate or alter `review_epoch`, `review_round`, `review_mode`, or `supervisor_attempt`, which remain the formal Supervisor tuple. The role rereads the pinned bundle, root repository instructions, and relevant GitHub/Git state before acting. Return `CONTEXT_MISMATCH` without mutation when the envelope conflicts with live evidence.

## Role metadata report and creator binding attestation

Create a Launcher, Orchestrator, Worker, or Supervisor with only this first prompt:

```text
ROUNDLET_ROLE_METADATA_REPORT_REQUEST
requested_role: <LAUNCHER|ORCHESTRATOR|WORKER|SUPERVISOR>
requested_profile: model=<MODEL>;reasoning_effort=<EFFORT>
requested_route: <LOCAL_PROJECT|PROJECT_WORKTREE|PROJECTLESS_NONREPOSITORY>
requested_saved_project: <PROJECT_ID_AND_CANONICAL_PATH_OR_NOT_APPLICABLE>
requested_starting_ref: <EXISTING_REF_OR_NOT_APPLICABLE>
requested_starting_sha: <FULL_SHA_OR_NOT_APPLICABLE>
requested_workspace: <PROJECT_OR_WORKSPACE>
requested_cwd: <CANONICAL_CWD|APP_MANAGED_WORKTREE>
Return any role-visible metadata as a non-authoritative ROUNDLET_ROLE_METADATA_REPORT. Perform no role, repository, GitHub, Git, heartbeat, or filesystem action.
END_ROUNDLET_ROLE_METADATA_REPORT_REQUEST
```

When the task can render the report canonically it may return:

```text
ROUNDLET_ROLE_METADATA_REPORT
reported_role: <role-or-unknown>
reported_profile: <profile-or-unknown>
reported_route: <route-or-unknown>
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
task_route: <LOCAL_PROJECT|PROJECT_WORKTREE|PROJECTLESS_NONREPOSITORY>
requested_saved_project: <exact-creator-request-or-not-applicable>
task_workspace: <exact-project-or-workspace>
task_cwd: <exact-canonical-cwd>
git_common_dir: <exact-common-dir-or-not-applicable>
starting_ref: <exact-existing-ref-or-not-applicable>
starting_sha: <exact-full-sha-or-not-applicable>
stable_host_identity: <exact-value-or-unavailable>
stable_environment_identity: <exact-value-or-unavailable>
binding_source: creator-immutable-readback
END_CREATOR_TASK_BINDING_ATTESTATION
```

If a report explicitly contradicts the proposed envelope, perform exactly one bounded creator-side immutable re-read. A complete unchanged read-back that still matches the request preserves the proposed values and the contradictory report remains non-authoritative. For `PROJECT_WORKTREE`, matching the creation request means the requested saved project/ref/profile equal the creator request and the actual App-managed CWD, canonical absolute Git common directory, detached `HEAD`, and exact SHA equal the resolved repository and expected state; the CWD itself is discovered after asynchronous creation and must differ from every unresolved tombstone path. Missing, stale, malformed, mismatched, or still-conflicting creator metadata fails closed before role work. Only after every authoritative field matches the route-specific request does the creator record exactly one attestation; only that attestation authorizes role work. Invalid-binding evidence may name only the creator failure class; it must never cite report formatting, omitted fields, prose, or a missing self-reported task ID.

The verified attestation remains stable and is copied into later role envelopes. Recovery/restart normally reuses it without duplicate task creation, binding, dispatch, or trace. Only contradictory immutable creator-side evidence triggers exactly one bounded re-read against the recorded attestation. An unchanged complete match preserves it; an unresolved difference fails closed without creating another task, attestation, dispatch, or trace. Do not repeat discovery on every turn.

For a top-level new-activation or recovery Launcher, the external creator copies the complete verified attestation into the fixed `Creator binding authority` block of the populated Launcher prompt. That prompt carries the creator's authoritative read-back across the task boundary. The Launcher validates one complete block and exact equality with the prompt's expected fields; it never rediscovers or requires a role-side immutable self-metadata route. A Launcher or Orchestrator that creates a later role remains that role's creator and performs the same creator-side read-back before copying the resulting attestation into the child role envelope and advisory state.

The Launcher and Orchestrator use the authoritative checkout through `LOCAL_PROJECT`. Every Git-repository Worker uses one persistent `PROJECT_WORKTREE` task, and every Supervisor uses a fresh read-only `PROJECT_WORKTREE` task. Their physical worktrees are distinct; the saved-project request, Git common directory, and exact full SHA establish shared candidate identity. `PROJECTLESS_NONREPOSITORY` is never a repository fallback and requires a separately proven caller-controlled CWD capability.

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

Do not advance review state after a missing or ambiguous trace acknowledgement. Keep the same epoch, round, attempt, and candidate, perform the idempotent cross-surface lookup, and retry only the canonical write/read-back. This pending trace state is not `NEEDS_OWNER_INPUT` unless separate live evidence proves an existing owner-input class.

For external validation, publish `VALIDATION_READY` only after the exact repository-owned executor returns `PREFLIGHT_READY` for one unconsumed candidate-bound plan with zero external action and declares the exact readiness/result schema binding consumed by execution. Never copy an earlier binding's schema expectation. Publish `VALIDATION_RESULT` only after that same plan reaches `VERIFIED`, or one durable terminal blocked result after a genuinely armed invocation. Keep runner construction, import, argument, schema, path, and external-action-free plan defects local; they must not produce repeated LIVE comments. Prefer a structured GitHub connector. A CLI fallback uses an exact body file and semantic marker/field read-back, never shell-interpolated Markdown.

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
requested_role: ORCHESTRATOR
execution_profile: model=<configured-model>;reasoning_effort=<configured-effort>
task_route: LOCAL_PROJECT
requested_saved_project: <creator-resolved-project-id-and-canonical-path>
task_workspace: <authoritative-writable-project>
task_cwd: <authoritative-checkout>
git_common_dir: <creator-verified-common-dir>
starting_ref: not-applicable
starting_sha: not-applicable
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
validation_toolchain_contract: <repository-defined-summary-or-not-applicable>
validation_cache_root: <absolute-path-or-not-applicable>
external_validation_contracts: <bounded-authoritative-path-and-blob-summaries-or-not-applicable>
lifecycle_observation_contracts: <bounded-authoritative-path-and-blob-summaries-or-not-applicable>
selection_allowed: false
END_ROUNDLET_ORCHESTRATOR_BOOTSTRAP
```

The Orchestrator must:

1. Require the envelope to equal the creator binding attestation.
2. Read `SKILL.md`, all required references, the exact configuration, and manifest only from the named bundle.
3. Recompute and verify bundle paths/hashes, tree digest, contract ID, source identity, and configured profiles.
4. Verify target/origin/default branch, clean aligned checkout, `.git/info/exclude`, authority block, owner identity/allowlist, task/heartbeat/Git/GitHub capabilities, absence of stale run ownership, any explicitly declared validation-toolchain contract/capability, every root-referenced external-validation contract path/blob identity, and every optional lifecycle-observation contract path/blob identity. Do not provision a validation cache, select an external route, arm a lifecycle window, or create sink storage during activation.
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
last_supervisor_result_event: <verified-event-id-or-none>
last_worker_repair_handoff_event: <verified-event-id-or-none>
formal_review_tuple: <epoch/round/mode/attempt/profile/candidate-or-not-applicable>
external_validation_tuple: <state/schema-binding/opaque-sequence/plan-or-not-applicable>
lifecycle_observation_tuple: <state/plan/window/sequence/head/seal-receipt-or-not-selected>
next_safe_action: <bounded-description>
END_ROUNDLET_TICK_RESULT
```

## Worker contract

The Worker:

- mutates only its assigned linked worktree and issue scope;
- may affect an exact repository-declared shared validation cache only through the candidate's reviewed resolver and explicit cache-root argument; never edits that cache directly or treats it as source;
- never mutates GitHub;
- never creates/removes worktrees or deletes branches;
- rereads the pinned Worker contract, root repository instructions, issue, pull request when present, and exact Git state;
- preserves unrelated work;
- uses repository conventions and proportional validation;
- commits atomically with required commit format;
- returns structured evidence to the Orchestrator.
- uses only the populated repository-owned external-validation binding; it never discovers or substitutes a toolbox, target, credential, commit, action, replay time, or authority value;
- invokes only the populated repository-owned executor entrypoint; it never creates a candidate-specific wrapper, inspects private product attributes, rewrites a plan, or substitutes a second validate/execute path;
- never invokes or writes the lifecycle observation sink; it returns ordinary structured handoffs to the Orchestrator, which alone appends verified generic transition facts;
- performs no disposable-target mutation. The Orchestrator remains the sole GitHub mutator and independently applies any authorized external mutation/read-back transition.

### Native Windows Worker mutation route

Apply only when the verified runtime is native Windows:

- `task_cwd` and `worktree` are the same verified App-managed project worktree. Do not create a manual anchor or nested linked worktree.
- Use direct normal-sandbox `apply_patch` for source edits. Never invoke it through PowerShell, a shell/pipeline, here-string/here-document, batch wrapper, or elevation.
- If an actual Git operation needs out-of-root linked-worktree metadata, request the narrowest approval for that exact command/worktree only. Do not broaden it to source edits.
- Cleanup may retain only a creator-verified typed empty task-worktree tombstone under the operator-guide rule; the Worker never removes or reuses it.

Do not apply this section to WSL, Linux, macOS, or another host.

### Repository-defined validation toolchain

When `validation_toolchain_contract` is not `not-applicable`, follow the exact operator-guide contract before returning a validation result. Discover a bootstrap interpreter satisfying the target repository's stated version, but use it only to run the candidate resolver. Lazily provision a wholly missing exact cache, verify or reuse a complete receipt, and execute actual validation only through the receipt-bound route. Stop on partial, stale, invalid, or drifted evidence without host-tool fallback or automatic rebuild. The cache root must equal the envelope and remain outside the removable issue worktree when the repository contract requires the authoritative shared cache.

### Repository-owned external validation

When `external_validation_route` is not `none`, reread the exact authoritative path/blob binding in the envelope and the selected leaf before acting. Read-only toolbox work requires the read-only authority switch. Never perform a disposable-target mutation; return the exact requested action and evidence to the Orchestrator, which owns mutation and semantic read-back. Do not discover, print, persist, relay, or automate credentials.

Require the exact `external_validation_executor` identity. Dry validation and execution must use the same repository-owned entrypoint and immutable plan. Return `BLOCKED` without external action when that contract is missing, malformed, stale, or internally inconsistent; do not assemble a replacement runner. Candidate or component movement returns `STALE` and requires a wholly fresh binding under unchanged standing authority. These dispositions consume no Supervisor attempt, review round, or owner approval.

For a historical replay, use only the captured value in `historical_evidence_time` and the immutable evidence bundle. Passing current wall-clock time is `CONTEXT_MISMATCH`. A missing, floating, stale, conflicting, out-of-allowlist, or partially read-back binding returns `BLOCKED` without substitution.

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

Verify a clean worktree and exact candidate. Merge current origin/main into the issue candidate checkout
without rebase or force-push, resolve only in-scope conflicts, validate, commit when needed,
and return WORKER_HANDOFF kind=MAIN_INTEGRATION. Do not push or mutate GitHub.
```

### Cleanup-preflight prompt

After the shared envelope:

```text
WORKER_CLEANUP_PREFLIGHT
expected_merge_commit: <full-sha>
expected_remote_head: <full-sha>
expected_origin_main: <full-sha>
refs_refreshed_by_orchestrator: true

Read only. Verify PR merged state, leaf closure, branch push identity, worktree status,
unique commits, untracked files, and absence of unpreserved work. Do not edit, commit, push,
remove the worktree, delete a branch, or mutate GitHub. Treat unavailable expected refs as
CONTEXT_MISMATCH rather than inferring ancestry or requesting owner input. Return
WORKER_CLEANUP_RESULT.
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
branch: <exact-candidate-ref; checkout-is-detached>
worktree: <absolute-path>
before_sha: <full-sha>
candidate_sha: <full-sha>
commits:
- <full-sha> <subject>
files:
- <path>: <summary>
validation:
- <command-or-check>: <result>
validation_toolchain_lock: <public-safe-lock-digest-or-not-applicable>
validation_toolchain_receipt: <VERIFIED|NOT_APPLICABLE|BLOCKED>
validation_toolchain_platform: <public-safe-platform-identity-or-not-applicable>
validation_toolchain_cache: <public-safe-lock-and-platform-cache-key-or-not-applicable>
bootstrap_interpreter: <discovered-command-and-version-or-not-applicable>
external_validation_route: <none|toolbox|toolbox+disposable-target>
external_validation_binding: <public-safe-exact-identities-or-not-applicable>
external_validation_schema_binding: <executor-declared-readiness/result-schema-identities-and-digests-or-not-applicable>
external_validation_sequence: <opaque-repository-owned-sequence-or-not-applicable>
historical_evidence_time: <repository-field-and-captured-value-or-not-applicable>
external_validation_result: <VERIFIED|NOT_APPLICABLE|BLOCKED>
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
origin_main: <full-sha>
refs_refreshed: <true|false>
leaf_closed: <true|false>
worktree_clean: <true|false>
unique_unmerged_commits: <none-or-list>
untracked_or_unpreserved_work: <none-or-list>
cleanup_safe: <true|false>
blocking_evidence: <none-or-bounded-description>
END_WORKER_CLEANUP_RESULT
```

After every archived App-managed repository role task, the Orchestrator must append exactly one terminal local-only receipt to the run-local task-worktree cleanup ledger:

```text
ROUNDLET_TASK_WORKTREE_CLEANUP_RESULT
scope_id: <stable-run-id-or-activation-probe-id>
active_leaf: <issue-number-or-none>
role: <WORKER|SUPERVISOR|ROUTE_PROBE>
role_task: <creator-verified-task-id>
worktree: <exact-app-managed-absolute-path>
task_state_after_wait: <ARCHIVED_AND_NONACTIVE|ACTIVE|AMBIGUOUS>
wait_bound_seconds: 30
git_registration: <ABSENT|PRESENT|AMBIGUOUS>
dot_git: <ABSENT|PRESENT|AMBIGUOUS>
directory_entries: <nonnegative-integer-or-ambiguous>
path_reuses_prior_tombstone: <true|false|ambiguous>
status: <REMOVED|RETAINED_EMPTY_TOMBSTONE|BLOCKED>
END_ROUNDLET_TASK_WORKTREE_CLEANUP_RESULT
```

`REMOVED` requires absent registration and physical path. `RETAINED_EMPTY_TOMBSTONE` requires an archived/non-active task, absent registration and `.git`, zero directory entries, and no prior-tombstone reuse. Every other result is `BLOCKED`. This receipt is never public GitHub trace, permission to remove content, or a reusable task directory.

Before removing an Orchestrator-created auxiliary worktree or state root, the Orchestrator privately records and reads back:

```text
ROUNDLET_AUXILIARY_RETENTION_RESULT
run_id: <stable-run-id>
active_leaf: <issue-number>
resource: <exact-path-and-registration-or-state-root-identity>
classification: <SOURCE_ONLY|EVIDENCE_BEARING>
retention_boundary: <repository-declared-absolute-path-or-not-applicable>
artifacts:
- source_identity: <exact-relative-identity>
  destination_identity: <exact-retained-relative-identity>
  size: <nonnegative-integer>
  sha256: <sha256:lowercase-hex>
source_destination_readback: <MATCH|NOT_APPLICABLE|MISMATCH>
resource_closed_and_stable: <true|false>
retention_status: <VERIFIED|BLOCKED>
END_ROUNDLET_AUXILIARY_RETENTION_RESULT
```

`SOURCE_ONLY` requires no unique artifact after exact inventory. `EVIDENCE_BEARING` requires every unique artifact to be closed/stable and byte-, size-, and digest-matched at the retained destination. A missing, changing, partially copied, or ambiguous artifact returns `BLOCKED`; the Orchestrator removes no affected resource and selects no next issue. GitHub receives only the bounded retention-manifest identity and status, never private paths or artifact contents.

## Supervisor contract

Every Supervisor is fresh and read-only. Its creator verifies the configured attempt profile and creator binding attestation once before review. The Supervisor's metadata report is never attempt-validity evidence. The Supervisor:

- reads the pinned contract, issue, PR, root instructions, exact candidate diff/tree, relevant tests/checks, prior findings, and Worker handoffs;
- reviews only the named full candidate SHA;
- never edits, commits, pushes, mutates GitHub, or changes branch/worktree state;
- never invokes or writes a lifecycle observation sink; it returns only its structured read-only result to the Orchestrator;
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
validation_toolchain_lock: <public-safe-lock-digest-or-not-applicable>
validation_toolchain_receipt: <VERIFIED|NOT_APPLICABLE|INVALID_CONTEXT>
external_validation_route: <none|toolbox|toolbox+disposable-target>
external_validation_binding: <public-safe-exact-identities-or-not-applicable>
external_validation_schema_binding: <executor-declared-readiness/result-schema-identities-and-digests-or-not-applicable>
external_validation_sequence: <opaque-repository-owned-sequence-or-not-applicable>
external_validation_executor_receipt: <VERIFIED|NOT_APPLICABLE|INVALID_CONTEXT>
historical_evidence_time: <repository-field-and-captured-value-or-not-applicable>
external_validation_reviewed: <VERIFIED|NOT_APPLICABLE|INVALID_CONTEXT>
read_only: <true|false>
END_SUPERVISOR_RESULT
```

`context_status: INVALID_CONTEXT` requires `verdict: NOT_APPLICABLE`, no findings, and `validation_toolchain_receipt: INVALID_CONTEXT`, `external_validation_executor_receipt: INVALID_CONTEXT`, or `external_validation_reviewed: INVALID_CONTEXT` when its required evidence is missing or conflicting. A valid PASS requires `context_status: VALID`, `verdict: PASS`, no findings, correct formal SHA/profile/round/mode, `read_only: true`, a matching `VERIFIED` receipt whenever the repository toolchain contract requires one, and matching executor/identity/evidence-time/read-back evidence whenever the selected external-validation route is not `none`. External-validation sequence values are evidence reviewed by the Supervisor, never replacements for the result's formal review fields.

A schema-valid PASS or FINDINGS at the exact formal Supervisor tuple is an accepted formal-round result. The Orchestrator publishes and reads back its event before any state change. Stop or archive a Supervisor created with a stale, external-validation, or otherwise wrong formal tuple without accepting or tracing its verdict; interrupt it first when it is still running. Retain it only as unaccepted local diagnostic evidence, then create a fresh Supervisor at the mechanically correct formal tuple without changing epoch or accepted-round count. FINDINGS returns to the same Worker; only after repair, exact candidate push/read-back, and a verified repair-handoff event does the Orchestrator increment the formal round and reset `supervisor_attempt` to 1. Invalid or unavailable attempts alone may increment `supervisor_attempt` while epoch, round, mode, and candidate remain fixed.
