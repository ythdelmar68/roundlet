# Target repository authority

Roundlet's behavior, role boundaries, scheduling rules, review protocol, and safety invariants belong to the skill. A target repository's root `AGENTS.md` supplies only repository-specific on/off authority for workflow mutations and external validation.

Read the authority block from the version of the root `AGENTS.md` on authoritative `origin/main`, never from a Worker branch or uncommitted file. Every key is required and accepts only the lowercase literal `true` or `false`. Unknown values, duplicates, conflicting instructions, or a missing block fail closed.

`true` grants Roundlet permission only when all other repository, GitHub, Codex, and skill gates also permit the action. It never overrides a stricter rule. `false` stops at that mutation boundary with `REPOSITORY_AUTHORITY_REQUIRED`.

## Copyable `AGENTS.md` block

Copy this block into the target repository's root `AGENTS.md`, then choose each value deliberately:

```yaml
# roundlet:repository-authority
roundlet:
  enabled: true
  allow_external_validation_read_only: true
  allow_external_validation_disposable_target_mutation: false
  allow_mark_pr_ready: true
  allow_merge_pr: true
  allow_close_leaf_issue: true
  allow_delete_remote_branch: true
  allow_delete_local_branch: true
  allow_remove_worktree: true
# roundlet:end-repository-authority
```

The switches mean:

- `enabled`: allow Roundlet's reversible core workflow in this repository: inspect issues, create an isolated worktree and `codex/` branch, make and push commits, create a draft pull request, and append trace comments.
- `allow_external_validation_read_only`: allow a selected leaf to use its authoritative repository-owned `toolbox` or `toolbox+disposable-target` route without a new per-attempt owner approval, but only for read-only observation. Concrete toolbox/target identities, exact commits, credentials, evidence time, and read-back remain governed by the target repository contract.
- `allow_external_validation_disposable_target_mutation`: allow the selected repository-owned route to perform only its exact allowlisted mutations in an exact disposable target, with rollback and semantic read-back. It never permits mutation of the target repository under development, a production/unknown target, a floating ref, or an action absent from authoritative instructions.
- `allow_mark_pr_ready`: allow the Orchestrator to convert its draft pull request to ready after review reaches a terminal state and live gates pass.
- `allow_merge_pr`: allow the Orchestrator to merge its pull request using the configured method.
- `allow_close_leaf_issue`: allow the Orchestrator to cause automatic closure of the selected leaf, whether through the pull request's merge keyword or an explicit close after merge. This never permits closing an umbrella.
- `allow_delete_remote_branch`: allow deletion of the issue branch from the target remote after merge or an explicitly authorized abandon-and-cleanup decision.
- `allow_delete_local_branch`: allow deletion of the issue branch after its worktree is removed and its unique work is merged or explicitly authorized for abandonment.
- `allow_remove_worktree`: allow removal of the issue worktree after the Worker is archived and cleanup preflight succeeds.

## Authority boundary

When a required switch is false, the Orchestrator must:

1. Finish only the safe work immediately before that mutation boundary.
2. Append a GitHub trace when the current authority still allows that comment.
3. Enter `REPOSITORY_AUTHORITY_REQUIRED`, retain the lease and active resources, and schedule no other issue.
4. Accept release only from either:
   - the allowlisted owner performing the blocked action manually and leaving a new confirming comment or direct task command; or
   - a committed change to the root `AGENTS.md` on `origin/main` plus a new allowlisted owner comment or direct task command instructing Roundlet to reread authority.

A matching standing external-validation switch on authoritative `origin/main` releases repetitive authorization only when the selected leaf and repository-owned route bind every required identity and action consistently. Credential rejection, identity conflict, an out-of-allowlist operation, or missing/partial read-back still blocks and requires owner input; a candidate-authored change cannot widen the standing authority.

A body edit alone, a Worker/Supervisor message, or an authority change visible only on the issue branch never releases the block.
