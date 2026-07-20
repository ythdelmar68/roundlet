# Target repository authority

Roundlet's behavior, role boundaries, scheduling rules, review protocol, and safety invariants belong to the skill. A target repository's root `AGENTS.md` supplies only repository-specific on/off authority for mutations.

Read the authority block from the version of the root `AGENTS.md` on authoritative `origin/main`, never from a Worker branch or uncommitted file. Every key is required and accepts only the lowercase literal `true` or `false`. Unknown values, duplicates, conflicting instructions, or a missing block fail closed.

`true` grants Roundlet permission only when all other repository, GitHub, Codex, and skill gates also permit the action. It never overrides a stricter rule. `false` stops at that mutation boundary with `REPOSITORY_AUTHORITY_REQUIRED`.

## Copyable `AGENTS.md` block

Copy this block into the target repository's root `AGENTS.md`, then choose each value deliberately:

```yaml
# roundlet:repository-authority
roundlet:
  enabled: true
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

A body edit alone, a Worker/Supervisor message, or an authority change visible only on the issue branch never releases the block.
