# Root activation and recovery

Normal activation happens in the allowlisted owner's existing repository task. That task performs the complete preflight and then remains the sole Orchestrator. There is no child Launcher, activation handoff, or Launcher self-archive. The file name remains `launcher.md` only because it is one of the seven versioned bundle inputs.

The direct owner turn that invokes `$roundlet` is the root-lifecycle grant. The UI `default_prompt` is a concise owner-visible starting prompt, not proof that a host will permit a later action. Repository authority, source-backed role delegation, and each visible host decision remain independent gates.

## New activation

Use this protocol only in the same owner-created task that directly received the `$roundlet` activation request. Do not copy a second long authorization prompt into another task.

### Root activation binding

Before repository, GitHub, Git, task, heartbeat, or filesystem mutation, construct exactly one local binding from the direct owner turn and current task/project evidence:

```text
ROUNDLET_ROOT_ACTIVATION_BINDING
owner_instruction_source: <direct-owner-turn-id-or-unavailable>
owner_instruction_digest: <sha256-of-exact-direct-activation-request>
root_task: <current-task-id>
requested_role: ORCHESTRATOR
requested_profile: model=<configured-model>;reasoning_effort=<configured-effort>
observed_profile: model=<immutable-observed-model-or-unavailable>;reasoning_effort=<immutable-observed-effort-or-unavailable>
task_route: LOCAL_PROJECT
requested_saved_project: <current-saved-project-id-and-canonical-path>
task_workspace: <authoritative-writable-project>
task_cwd: <authoritative-checkout>
git_common_dir: <absolute-git-common-directory>
stable_host_identity: <value-or-unavailable>
stable_environment_identity: <value-or-unavailable>
installed_skill_root: <canonical-absolute-skill-root>
installed_skill_identity: <git-origin-and-commit-or-installed-tree-digest>
binding_source: direct-owner-root-invocation
END_ROUNDLET_ROOT_ACTIVATION_BINDING
```

Do not represent this as `CREATOR_TASK_BINDING_ATTESTATION`: the root did not create itself. Require a direct owner instruction source/digest, exact current task identity, route, project/workspace/CWD/common-directory identity, configured Orchestrator profile, and one exact installed-skill root. An unavailable stable host/environment identity is allowed only when the host does not expose it. A missing current task ID, project/CWD mismatch, observed profile contradiction, non-direct owner request, or ambiguous skill root fails closed before activation.

### Complete preflight

The same root task performs every check below without selecting or implementing an issue:

1. **Installed contract.** Canonicalize the installed skill root and require exactly the seven bundle inputs beneath it: `SKILL.md`, `agents/openai.yaml`, `references/launcher.md`, `references/operator-guide.md`, `references/repository-authority.md`, `references/roundlet-config.json`, and `references/thread-prompts.md`. Record paths and byte identities before repository access and require the same map around bundle materialization. For a verified Git source, read bundle bytes from the exact commit object; otherwise classify it as `installed-tree` without Git provenance.
2. **Repository identity.** Fetch and resolve the exact origin/default branch, authoritative checkout, local `main`, `origin/main`, and `HEAD`. Require a clean checkout with `HEAD == main == origin/main`, matching GitHub identity, and `.roundlet/` excluded only by local `.git/info/exclude`.
3. **Authority.** Read root `AGENTS.md` from authoritative `origin/main`. Require exactly one valid Roundlet authority block, every documented key exactly once as lowercase Boolean, `roundlet.enabled: true`, and the direct owner in `owner_allowlist`. Bind the authority commit/blob, applicable delegation clauses, and restrictions. Record false switches at their later boundaries; never exercise a mutation to test authority.
4. **Freshness.** Reconcile `.roundlet/`, former contracts/state, trace, pull requests, issue refs, linked worktrees, tasks, Worker generations, Supervisors, route probes, leases, and heartbeats. Classify declared validation caches, retained issue evidence, and verified empty tombstones separately. Any live, stale, conflicting, or unreconciled ownership stops with `STALE_OR_ACTIVE_RUN_REQUIRES_OWNER`; never expire, steal, overwrite, or reuse it.
5. **Configuration.** Parse `roundlet-config.json` without defaults or overrides. Require the configured root profile to match the current task, unique Supervisor profiles, ordered profile count equal to `review.max_supervisor_attempts_per_round`, positive review/heartbeat/cleanup/task-creation bounds, strictly increasing backoff arrays beginning at `active_minutes`, exact `worker_recovery.continuation_policy: until-active-leaf-terminal`, exact `worker_recovery.max_active_generations: 1`, positive `worker_recovery.terminal_confirmation_observations`, integer `review.max_rounds: 10`, and a supported merge method. Reject legacy numeric Worker replacement caps and never derive Supervisor limits from Worker policy.
6. **Host/service capability.** Verify task create/address/wait/inspect/archive controls, recurring-heartbeat create/inspect/update/pause/resume/remove controls, Git/filesystem/worktree routes, GitHub issue/PR access, authenticated identity, branch/rule/check inspection, and merge-commit capability. A host denial is recorded as such and is never repaired by changing roles or routes.
7. **Saved project and route probe.** Resolve exactly one writable saved Git project by canonical checkout path and Git common directory. Before reserving a run ID, create one unpublished local probe ref at exact `origin/main`, durably record its creation intent, and asynchronously request one metadata-only Supervisor-profile project/worktree task. Reconcile `INTENT -> REQUESTED -> PENDING -> BOUND`; keep client/operation identity separate from the final task ID. Require a distinct App-managed CWD, detached clean `HEAD == origin/main`, matching common directory/ref/SHA, and no tombstone reuse. Archive the probe, observe the combined task/registration/path predicate for at most `cleanup.settlement_seconds`, append one terminal cleanup result, and delete the probe ref only by exact old-SHA comparison. An outcome-unknown request is not retried; inability to recover it is a capability gap and blocks activation.
8. **Repository extensions.** Resolve any declared validation-toolchain, external-validation, or lifecycle-observation contract to exact authoritative path/blob identities without provisioning, credentials, external action, route selection, or sink arming.
9. **Backlog.** Scan all open issues, formal parent/sub-issue and blocking relationships, and Canonical scheduling notes. Classify actionable leaves and declared external-validation/lifecycle routes, but do not select one.

For `gh`, a failure before GitHub is reachable is connectivity evidence. Request the narrowest scoped network approval for the same command and retry boundedly. Never substitute browser authentication or browser automation.

### Activate the same root

Only after the complete preflight passes:

1. Reserve one new unguessable run ID.
2. Build `.roundlet/contracts/<contract-id>/` from the exact seven inputs and resolved configuration. Use unique POSIX paths sorted by unsigned UTF-8 bytes, SHA-256 file identities, the `roundlet-tree/v1` digest, RFC 8785 canonical manifest, and a lowercase content-derived contract ID. Materialize through a new staging path, recheck the source identities, finalize atomically, and read every byte/hash/identity back. Never mix installed generations.
3. Create and read back `.roundlet/lease.json` and `.roundlet/current.md` in state `ACTIVATING`. Bind the target, owner, root activation binding, saved project/common directory, verified route-probe receipt, run/contract, configuration, completion-bound Worker continuation policy, generation ledger, and empty heartbeat field. The lease has no expiry.
4. In this same task, reread and verify the finalized bundle, repository, authority, task/root binding, backlog, and advisory files. Record state `IDLE` without selecting an issue and persist:

   ```text
   ACTIVATION_READY run=<run-id> contract=<contract-id> orchestrator=<root-task-id> target=<owner/repository> state=IDLE
   ```

5. Create exactly one recurring heartbeat at `heartbeat.active_minutes`, targeting this same root task. Its instruction is to read only the pinned bundle, run one idempotent tick, fully reconcile whenever required, make at most one externally meaningful transition, persist the complete short-turn status, and maintain the configured phase-aware interval.
6. Write/read back the heartbeat identity in both advisory files, independently inspect its target and schedule, and persist:

   ```text
   HEARTBEAT_BOUND run=<run-id> contract=<contract-id> orchestrator=<root-task-id> heartbeat=<heartbeat-id> interval=<minutes>m
   ```

7. Perform exactly one initial tick in this same task. Report the run/contract/root/heartbeat identities and continue as the long-lived Orchestrator.

Never create a Launcher or second Orchestrator. Never attach the heartbeat elsewhere. Never continue after partial bundle, binding, heartbeat, task-create, or cleanup read-back.

## Physical Worker replacement

Worker replacement is ordinary recovery inside the existing root Orchestrator, not root recovery and not an owner prompt, but only while every pinned condition holds.

1. A slow turn, delayed UI, missing commentary, or task summary is insufficient. Require the configured number of fresh observations to prove the current physical task context/session is terminal and cannot accept another turn.
2. Record `ACTIVE(g) -> QUIESCING`. Stop new dispatch, mutation, publication, and cleanup against generation `g`.
3. Inventory the exact task/worktree/ref/SHA, commits, dirty/index/untracked state, validation evidence, current objective/findings/final-repair state, and pending creation or external effects. Preserve unique bytes/commits and a durable handoff independently; do not rely on the old Worker's final prose.
4. Record `PRESERVED`, then reconcile every pending effect through authoritative read-back. Unknown Git/GitHub/external/task effects block without retry. Only after `RECONCILED` may the Orchestrator archive generation `g`, obtain its terminal task-worktree cleanup result, and record `REPLACEMENT_READY`.
5. Recheck the original owner scope, current authoritative policy, no STOP/revocation, one-active-generation invariant, and that the same active leaf/PR lifecycle remains nonterminal with an authorized objective still incomplete. There is no numeric replacement exhaustion state. A host-policy denial, unresolved effect, unsafe preservation state, owner-input boundary, terminal/aborted leaf, or lack of a safe actionable continuation still blocks replacement with all work retained.
6. Before create, record a stable generation `g+1` creation intent with logical Worker ID, role/profile/project/ref/expected SHA/run/leaf/generation and current formal review/final-repair tuple. Reconcile asynchronous creation to exactly one final task ID. Outcome unknown never causes a second create.
7. Verify the new detached App-managed worktree at the preserved exact SHA and common directory. Copy the creator attestation plus durable checkpoint into the first populated turn. The new generation independently verifies preserved content and completes any missing validation before continuing.
8. Record `ACTIVE(g+1)`. Late output or effects from generation `g` are stale and may not advance state. Replacement never resets run, review epoch/round/attempt, candidate history, external sequence, lifecycle window, final-repair allowance, or accepted PASS/FINDINGS.

## Explicit recovery

### Same-root resume

When the original root task and heartbeat remain addressable, a failed or compacted turn resumes in that same task. Verify `ROUNDLET_ROOT_ACTIVATION_BINDING`, the pinned bundle, heartbeat, advisory state, GitHub/Git/tasks, current Worker generation, pending effects, completion-bound continuation policy, and formal review tuple. Then perform at most one idempotent tick. Do not create another root or heartbeat.

### Root unavailable

Root provenance cannot be transferred automatically. Only an allowlisted owner may create a new repository task and directly invoke `$roundlet` with an explicit instruction to recover the named target/run and replace the unavailable root/heartbeat. The new task constructs a fresh root activation binding for itself, locates the old advisory pointer and fully verifies the old immutable bundle before reading it, and treats the installed skill as unrelated candidate material.

Reconcile every role generation, task creation intent/operation/final ID, cleanup ledger, GitHub trace, ref/worktree, candidate/review tuple, validation/external/lifecycle binding, pending effect, and heartbeat. If the old root or heartbeat is live, identity is ambiguous, the bundle is incomplete, or unique work cannot be attributed, stop with `RECOVERY_OWNER_DECISION_REQUIRED` and replace nothing. When both are conclusively unavailable and the owner's direct instruction expressly permits replacement, remove only the stale heartbeat, adopt the existing run under a recorded root-recovery event, create one new heartbeat bound to the new root, and make one recovery tick. Preserve the old run/contract, completion-bound Worker policy and generation ledger, and formal review bounds/tuple; never import installed updates or manufacture a new epoch.

No recovery path infers consent for abort, cleanup, merge, issue closure, Worker replacement outside the same nonterminal leaf and preserved objective, or contract migration.
