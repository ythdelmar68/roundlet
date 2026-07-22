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
1. Resolve the exact installed skill source and configuration. Validate that every required configuration value is present and internally consistent. Require unique Supervisor attempt-profile names and an ordered profile count exactly equal to `max_supervisor_attempts_per_round`.
2. Verify that this Codex host can create, address, wait for, archive, and resume tasks; create and manage one recurring five-minute heartbeat; select every configured model and reasoning effort in every Supervisor attempt profile exactly; and access Git, the target checkout, and GitHub with the required read/write capabilities. Do not substitute an unsupported model, effort, or attempt profile.
3. Verify the target identity, clean authoritative checkout, main branch, origin URL, GitHub default branch, HEAD == local main == origin/main, merge-commit support, issue and pull-request access, and authenticated GitHub identity. Record whether the primary branch is protected. Inspect and obey every existing required check and branch rule; fail closed if existing rules cannot be inspected or conflict with the configured workflow. Absence of branch protection is not itself an activation blocker.
4. Read the root AGENTS.md from authoritative origin/main and parse only the exact Roundlet authority switches defined by the skill. Fail closed on missing, malformed, duplicate, or conflicting values. Require `roundlet.enabled: true`; record every other `false` switch as a later mutation boundary rather than silently changing it or rejecting activation.
5. Add `.roundlet/` to this checkout's local `.git/info/exclude` if it is not already excluded. Never commit that exclusion or any `.roundlet` file.
6. Inspect `.roundlet/lease.json`, `.roundlet/current.md`, GitHub traces, active codex/* branches and pull requests, local worktrees, and relevant Codex tasks/heartbeats. If any evidence suggests another live or unreconciled run, stop with STALE_OR_ACTIVE_RUN_REQUIRES_OWNER; never expire, steal, replace, or overwrite it.

If and only if all preflight checks pass:
1. Create `.roundlet/lease.json` and `.roundlet/current.md` as the advisory recovery index defined by the skill. Use an unguessable run ID, the exact target identity, this authoritative machine/checkout, the owner identity, activation time, and the Orchestrator task identity once known. Do not add an expiry.
2. Create exactly one long-lived Orchestrator task using configured role `orchestrator` model and reasoning effort. Give it the exact target, checkout, run ID, owner allowlist, resolved authority, configuration, lease/current paths, and the Orchestrator contract from the skill. Tell it to reconcile and answer exactly:
   ACTIVATION_READY run=<run-id> target=<owner/repository> state=IDLE
   without selecting an issue yet.
3. Wait for that exact response. If creation, preflight, or acknowledgement is incomplete or ambiguous, stop and preserve evidence; do not attach a heartbeat.
4. Create exactly one recurring heartbeat every configured number of minutes, addressed to the long-lived Orchestrator task. Its instruction is: invoke one idempotent Roundlet tick, reconcile live state first, make at most one safe state transition, and report the resulting state.
5. Send the heartbeat identity and schedule to the Orchestrator. Require and wait for:
   HEARTBEAT_BOUND run=<run-id> heartbeat=<heartbeat-id> interval=<minutes>m
6. Verify the lease/current files name the same run, Orchestrator, and heartbeat, then send the Orchestrator one initial tick.
7. Report the target, run ID, Orchestrator task, heartbeat, and preflight result to the owner. Archive this Launcher task. The Orchestrator task must remain long-lived.

Never attach the heartbeat to this Launcher. Never create a second Orchestrator or heartbeat. Never begin issue work after a failed or partial preflight.
```

## Explicit recovery

Use this only when the original Orchestrator or heartbeat is genuinely inaccessible. An old lease never authorizes automatic takeover.

Copy and paste this entire prompt into a new Codex task:

```text
Use $roundlet as a short-lived recovery Launcher for exactly one previously activated target.

Target:
- GitHub repository: <OWNER/REPOSITORY>
- Authoritative local checkout: <ABSOLUTE_PATH>
- Existing Roundlet run ID, if known: <RUN_ID_OR_UNKNOWN>
- Owner recovery instruction: reconcile the old run and, only if replacement is safe, create one replacement Orchestrator and heartbeat

Read the complete Roundlet SKILL.md and every required reference before acting. This prompt is explicit owner authorization to investigate and propose recovery; it is not authorization to discard, overwrite, merge, close, delete, or otherwise destroy old work.

1. Perform the normal capability, repository, configuration, authority, and identity preflight.
2. Reconcile `.roundlet/lease.json`, `.roundlet/current.md`, all Roundlet GitHub trace comments, active pull requests, exact branch SHAs, local and remote branches, worktrees, checks, and all identifiable old Orchestrator/Worker/Supervisor tasks and heartbeats.
3. If the old Orchestrator or heartbeat is still live or its ownership is ambiguous, stop with RECOVERY_OWNER_DECISION_REQUIRED and present exact evidence. Do not create a replacement.
4. If the old Orchestrator and heartbeat are conclusively unavailable, reconstruct the current phase from durable GitHub and Git evidence. Preserve the same run ID when identity is certain; otherwise stop for owner input.
5. If an active Worker task is unavailable, stop with WORKER_REPLACEMENT_REQUIRES_OWNER. Do not silently replace it.
6. Create exactly one replacement Orchestrator using the configured model and effort. Give it the reconstructed state, evidence, task identities, branch/worktree, candidate SHA, review epoch/round, current Supervisor attempt/profile when applicable, and explicit instruction to acknowledge RECOVERY_READY without advancing work.
7. After that acknowledgement, disable or remove any conclusively stale heartbeat if possible, create one replacement five-minute heartbeat, bind it to the replacement Orchestrator, update the advisory files, and send one recovery tick.
8. Report every retained, replaced, or unresolved resource to the owner and archive this recovery Launcher.

Fail closed at every ambiguity. Never infer owner consent for cleanup, abort, merge, or task replacement.
```
