# Operator guide

This is the detailed operating contract for Roundlet. The Orchestrator must reread the live sources it depends on before every mutation. Natural-language judgment is intentional; local files provide an advisory recovery index, not deterministic coordination.

## Contents

- [Operating envelope](#operating-envelope)
- [Configuration and capability preflight](#configuration-and-capability-preflight)
- [Immutable task-metadata handshake](#immutable-task-metadata-handshake)
- [Filesystem mutation canaries and typed outcomes](#filesystem-mutation-canaries-and-typed-outcomes)
- [Task and worktree resource cleanup](#task-and-worktree-resource-cleanup)
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
- every Worker task can report whether its actual runtime is native Windows, WSL, or another non-Windows environment without inferring it only from a path string;
- GitHub identity, repository identity, issues, comments, branches, pull requests, reviews, checks, mergeability, and merge operations can be inspected;
- authorized GitHub mutations are available to the Orchestrator;
- the exact installed candidate contract can be copied to a local content-addressed bundle and every copied path/hash can be read back;
- `filesystem_canary.required` is exactly `true`, `approval_retry_limit` is exactly `1`, and the role-specific advisory, linked-worktree, and Git-index canaries below pass with cleanup proof;
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

## Immutable task-metadata handshake

Eager task tool exposure is not a complete capability catalog. Before a Launcher or task creator classifies immutable task metadata unavailable, it must exhaust the host's deferred tool-discovery surface and locate the route that exposes the current request's immutable task ID, model, and reasoning effort. Missing eager exposure is inconclusive.

Every newly created Launcher, Orchestrator, Worker, and Supervisor uses this initial handshake before its first canary, implementation, or review turn:

1. Create the task with only the metadata-probe prompt from `thread-prompts.md`. It performs no filesystem, Git, GitHub, heartbeat, contract, issue, or pull-request mutation.
2. In that task, exhaust deferred discovery and invoke the discovered immutable metadata route. Resolve the task ID only when the route's top-level `threadId` and any present immutable `thread_id` and `session_id` fields are mutually equal. Return that value as `role_task`, return the exact immutable turn field separately as `metadata_turn`, and return `model=<id>;reasoning_effort=<effort>` plus the route identity. `turn_id` is never a task ID. Missing or conflicting task/session fields and self-reported profile prose are invalid.
3. The external creator independently reads an immutable creator-side task/turn record and requires the task ID, turn ID, model, and reasoning effort to equal both the requested profile and the probe result. The creator-provided task ID must equal `role_task`, while the creator-provided turn ID must equal only `metadata_turn`. A value copied only from the child response is not independent evidence.
4. Only after that match may the creator send the task's first fully populated role or filesystem-canary prompt.

Every populated role turn, including each Worker canary, implementation, repair, final-repair, integration, and cleanup-preflight turn and each Supervisor review turn, then uses the per-turn gate from `thread-prompts.md`:

1. Before dispatch, the creator independently rereads the stable task record and requires its task ID/model/effort to equal the populated `role_task` and `execution_profile`.
2. On that exact turn and before mutation or review, the role invokes the immutable metadata route, requires the current task ID/model/effort to equal the populated envelope, and records the new `turn_id` only as `metadata_turn`.
3. After the role returns, the creator independently reads back that exact populated task/turn record and requires task ID, turn ID, model, and effort to equal the structured result. Until that read-back passes, reject the result and permit no trace publication, GitHub mutation, review advance, merge, or cleanup transition.

Classify the route as unavailable only after exhaustive discovery or invocation fails, or independent read-back cannot be completed. A task/turn substitution, mismatch, malformed result, substituted profile, or route that exposes only self-report fails closed before the role acts or rejects the returned result before transition. Preserve only bounded task, turn, route, profile, and typed failure evidence.

## Filesystem mutation canaries and typed outcomes

Tool presence, a permission declaration, or a zero-tool decision never proves filesystem mutation capability. Activation, issue claim, recovery, legacy bootstrap, contract adoption/migration, and mutation benchmarks must exercise the exact task, host, checkout/worktree, permission route, and mutation surface that the run will use. Use an unguessable nonce and a bounded artifact whose path is first proven absent. Record the exact target and initial identity before mutation.

Every file-surface canary performs this sequence:

1. Create one unique artifact containing the nonce, run/canary identity, surface, and first expected content; read it back and verify exact path, identity, bytes, and SHA-256.
2. Change that same artifact through the mutation route the role will use for real work; read it back and verify the distinct second expected bytes and hash.
3. Remove only the canary artifact and any canary-created empty parent, then prove the exact path absent and the surrounding state equal to its captured initial identity. A Launcher first satisfies the authoritative writable-workspace binding below. A native-Windows Worker uses the additional empty-parent finalization contract in the native-Windows subsection below; that exception never applies to a Launcher or another runtime.

Every canary turn uses the canary-specific context envelope from `thread-prompts.md`, not the implementation/review envelope. Pre-bundle activation uses `none-before-contract` only for the not-yet-created activation contract fields. Legacy bootstrap uses `none-before-legacy-contract` only for those same fields after proving the run has no activation ID, legacy record, contract bundle, prepared record, or committed record and binds the literal owner-authorized bootstrap protocol as `source_contract`. A standalone benchmark uses `none-for-benchmark` only when its exact candidate is bound separately. Activation, between-issue adoption, legacy bootstrap without retained leaf resources, and a benchmark plan may use `none` only for genuinely absent leaf/branch resources. Both issue-claim roles bind the existing branch and selected leaf, while each binds its own role-specific checkout/worktree. Every recovery/bootstrap/migration phase binds all retained applicable resources. This prevents a healthy pre-contract, benchmark, or leafless canary from failing on invented implementation context while preserving exact task, profile, runtime, route, target, and Git identities.

Required surfaces are:

- **Advisory state:** the Launcher and then the long-lived Orchestrator each use a new ignored path below the authoritative checkout's `.roundlet/`. The Orchestrator result, not the Launcher result, proves the live advisory route.
- **Linked Worker worktree:** at activation, a short-lived task with the configured Worker model/effort uses a temporary isolated linked worktree created from exact `origin/main`. After a leaf worktree and persistent Worker are created, that same Worker proves its exact task/worktree route before initial implementation. During recovery, legacy bootstrap, or active migration, the same retained Worker uses its existing verified topology. Capture and restore exact `HEAD`, worktree status, index tree, and pre-existing staged/unstaged/untracked identities.
- **Linked-worktree Git index:** use a second unique, initially absent, unignored canary path. Resolve the exact index path and capture its complete raw-byte preimage before any operation that may lock or write the index; require its hash to equal `initial_index_sha256`. Stage only the canary path, inspect and verify its exact index mode/blob/content, unstage only that path, and remove it. Restore the exact captured preimage to the same index path through the bounded Git-index route, retain no backup artifact, and verify byte-for-byte length and SHA-256 equality after all remaining HEAD/status/tree/entry identity reads. A semantic tree/status/entry match does not substitute for raw index equality. Never commit the canary.

A canary must not touch an existing path, user work, an issue branch during activation, a GitHub object, or another task's artifact. A short-lived activation Worker is not the persistent issue Worker and its result cannot prove that later task's route. Archive it and normally remove its temporary linked worktree only after read-back and cleanup proof. Run a fresh canary in each newly created persistent Worker before sending implementation. Recovery never replaces an inaccessible retained Worker merely to run a canary.

### Launcher authoritative writable workspace

This subsection applies to every activation and recovery Launcher on every host. It is a platform-neutral route invariant, not an extension of the native-Windows Worker exception below.

Before the metadata-only handshake, the external creator creates the Launcher directly against the exact authoritative checkout as its canonical current directory and normal writable local-project workspace. Creator-side task read-back must prove the task ID, canonical CWD, workspace kind, and writable checkout equality before the populated turn. A projectless task, unrelated project, read-only route, or removable linked worktree is invalid and stops before run reservation or mutation. Scoped approval cannot convert that invalid topology into a valid Launcher.

The Launcher advisory canary creates, changes, and deletes its file through direct `apply_patch` in that normal writable checkout sandbox. It removes a canary-created empty parent through the ordinary exact nonrecursive, non-force directory route and proves the complete surrounding state restored. An out-of-root restriction is `CONTEXT_MISMATCH`, not an approval attempt. A genuine initial restriction after correct binding may use only the configured typed retry. Do not use the native-Windows Worker two-turn empty-parent protocol for a Launcher. Recovery Launchers use the same binding before reading or mutating advisory state.

### Native Windows Worker task anchor

This subsection applies only when `worker_runtime` is `NATIVE_WINDOWS`. It does not alter WSL, Linux, macOS, or any other host/runtime topology.

Create every new native-Windows Worker in a dedicated host-owned task anchor. Bind `native_windows_task_anchor` inside the native-Windows conditional prompt to the task's exact canonical CWD, and create the Roundlet-owned linked worktree as a distinct writable descendant. The task CWD must never equal or be inside the removable worktree. A surviving Codex/Node process whose exact CWD is the distinct anchor is recorded host lifecycle evidence, but it is not a worktree holder after task inactivity, Git-registration absence, unique-work absence, and physical linked-worktree-path absence are independently proven. Never store run state or unique work in the anchor, treat the anchor as the worktree, use it to excuse a surviving linked worktree, force-remove it, or kill a process to release it.

#### Native Windows linked-worktree fixed-body transport and Git-index approval route

This subsection applies only to a Worker canary with `worker_runtime: NATIVE_WINDOWS` whose separated linked-worktree Git index and possible `index.lock` resolve outside that Worker's normal writable roots. It does not apply to a Launcher, WSL, Linux, macOS, another host/runtime, an index already writable through the normal sandbox route, source-file edits, advisory state, or post-archive cleanup. Those routes keep their existing platform-appropriate behavior.

Before extracting either fixed PowerShell body below, the external creator binds `native_windows_operator_guide` to the canonical absolute path formed from the verified instruction root plus the exact relative path `references/operator-guide.md`. Before an activation contract exists, that root is the exact installed candidate already fingerprinted for activation; in a contract-aware phase, it is the verified effective pinned bundle. Bind `native_windows_operator_guide_sha256` to this file's exact SHA-256 in that candidate tree or bundle manifest. For each body, the canonical source-byte range begins at the first byte after the opening `powershell` fence's line terminator and ends immediately before the `CRLF` or `LF` that introduces the closing fence line; that delimiter line terminator and the closing fence are excluded, while every internal byte and original internal line terminator is preserved without normalization. The external creator, not the Worker, must extract the two fixed source bodies by that boundary rule from those verified bytes, populate each named assignment exactly once from the already bound canary values, and put the three complete preflight assignment lines, ten complete compound assignment lines, and SHA-256 of each fully populated source body in the populated native-Windows Worker prompt. The Worker must independently require an absolute path whose final relative components are exactly `references/operator-guide.md`, read the exact file bytes, verify the bound hash, re-extract by the same byte-boundary rule, populate the source bodies by replacing the same named assignment lines exactly once, and require the resulting complete lines and source-body digests to equal the creator-supplied records. Expected lines or digests derived by the Worker from its own already populated body are not independent evidence and must be rejected. A missing file, root-level `operator-guide.md` guess, alternate installed or bundled copy, path/hash mismatch, ambiguous fenced-body extraction, included closing-fence delimiter newline, unauthorized source-body newline normalization, missing creator-supplied canonical record, repeated/missing assignment name, complete-line mismatch, or source-body-digest mismatch is `FILESYSTEM_CAPABILITY_UNAVAILABLE` before artifact creation or approval. This binding belongs only to this native-Windows Worker route; it adds no guide-path, canonical-assignment, body-digest, byte-boundary, or fixed-body extraction requirement to a Launcher, WSL, Linux, macOS, `NON_WINDOWS`, or an ordinary writable-index route.

Never pass the populated compound body as process command-line text. After the populated compound source body passes its original-byte digest and assignment checks, reject any lone `CR` and any terminal line break, then derive the patch-canonical transport representation by replacing every internal `CRLF` with `LF`, leaving an already-LF source otherwise unchanged, and appending exactly one terminal `LF`. This deterministic conversion is the only permitted normalization and is required because direct `apply_patch` emits LF text with a terminal LF on this native-Windows route. The external creator also binds one nonce-qualified `native_windows_compound_transport` path that is a direct child of the verified host-owned Worker task anchor, outside the linked worktree, together with the exact byte length and SHA-256 of that patch-canonical representation. These transport records are separate from the populated source body's original-byte length and digest. The Worker independently derives the same bytes from its verified source body and requires exact equality with both creator transport records before file creation. Before either canary file exists, require that path absent and its parent exactly the ordinary non-reparse task anchor. To serialize the direct Add File patch, remove only the representation's one structural terminal `LF`, split the remainder on `LF`, and emit exactly one `+<line>` patch record for every resulting logical line, including internal empty lines; the patch-record terminators recreate the target line endings. Do not emit an additional terminal empty `+` record. Create the transport only through that direct normal-sandbox `apply_patch`. Read back its exact bytes, length, and digest and parse those file bytes through a bounded short native-Windows command. Immediately before the one approved operation, read back the same file and require the same digest; execute that exact `.ps1` file without any further rewriting, wrapping, splitting, re-encoding, normalizing, or substitution. The transport is not a backup and must never enter the linked worktree or Git status. Delete only the exact transport file through direct `apply_patch` after the operation or any post-creation failure, and bind its absence into cleanup. This transport rule, including its patch-canonical derivation and serialization, applies only to this native-Windows out-of-root Worker route; it adds nothing to the Launcher, WSL, Linux, macOS, `NON_WINDOWS`, an ordinary writable-index route, source edits, advisory state, or another shell operation.

Treat `git write-tree`, index refresh, stage/unstage, and every other command that may create `index.lock` as index-writing operations on this topology. Do not execute a preliminary locking identity command in the normal sandbox merely to discover the expected restriction, and do not spend the one configured retry before the actual canary sequence. Non-locking reads may run normally, but they cannot substitute for the required initial/final tree and index identities.

After the canary file exists through direct normal-sandbox `apply_patch`, an initial restriction on this exact out-of-root index route may receive the sole configured approval retry as one compound operation:

1. Bind the operation to the exact canonical linked worktree, resolved index path, unique canary path, expected raw preimage length/SHA-256, and initial HEAD/status/tree/pre-existing-entry identities. Capture the complete raw index bytes in memory before the first potentially locking or writing command; create no backup artifact.
2. Within that same approved operation, run the required initial locking identity reads, stage only the canary, verify its exact index path/mode/blob/content, restore the captured raw bytes to remove only that staged entry, and run every required final HEAD/status/tree/pre-existing-entry read. Every Git or subprocess non-zero exit terminates the compound operation non-zero; later formatting or output must not mask it.
3. After all Git identity reads, restore the same captured bytes once more inside an unconditional restoration guard, then perform only raw filesystem read-back: require the final index length/SHA-256 to equal the preimage and require `index.lock` absent. Retain no backup or helper artifact. Subsequent direct-`apply_patch` deletion of the two direct-child canary files and the exact anchor transport file must leave no canary-created parent or transport residue. After deletion, run no Git command; prove all three file absences, repeat only raw index length/SHA-256 and lock-file reads, and bind the dedicated patch tool's exact-path change/delete evidence to show that no unrelated worktree or anchor path was mutated.

This native-Windows out-of-root mode has a separate, read-only preflight template. It is not a cross-platform command and makes no Git call. Convert each of the three exact path values to standard padded Base64 of its UTF-8 bytes, validate the encoded value against the template's Base64 grammar and an encode/decode round trip before substitution, and populate only those three encoded assignments. Never insert a raw path into a PowerShell literal. The external creator supplies the three complete canonical assignment lines and populated-body SHA-256 before dispatch. Before parsing or execution, the Worker reads back the three populated assignment lines and requires each complete line and the full body digest to equal those creator-supplied records; require exactly three such assignments and no placeholder, concatenation, interpolation, variable reference, method call, or other expression in any right-hand side. Parse the fully populated body, then execute it unchanged in the normal sandbox before creating either file. The body decodes the values as strict UTF-8 and, before any path access, rejects a single quote or newline in the absolute worktree and rejects `/`, `\`, whitespace, a single quote, or a newline in either direct-child filename. Do not substitute a Worker-authored shell preflight. Require its `PASS`, exact absolute paths, canonical worktree root, and `initial_absence_root_identity_sha256` output. If this or an earlier pre-mutation gate fails, launch no Git command; use only raw filesystem reads to prove both files absent, the raw index length/SHA-256 unchanged, and `index.lock` absent, and report `cleanup: VERIFIED` when that exact proof passes even though capability remains unavailable:

```powershell
$ErrorActionPreference = 'Stop'
$WorktreeBase64 = '<base64-utf8-absolute-linked-worktree>'
$WorktreeCanaryPathBase64 = '<base64-utf8-direct-child-worktree-canary-filename>'
$IndexCanaryPathBase64 = '<base64-utf8-direct-child-index-canary-filename>'

function ConvertFrom-RoundletBase64 {
    param([string]$Value)
    if ($Value -notmatch '^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$') { throw 'invalid Base64 assignment' }
    try { $Bytes = [Convert]::FromBase64String($Value) }
    catch { throw 'invalid Base64 assignment' }
    $Utf8 = [Text.UTF8Encoding]::new($false, $true)
    try { $Decoded = $Utf8.GetString($Bytes) }
    catch { throw 'invalid UTF-8 assignment' }
    if ([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Decoded)) -ne $Value) { throw 'noncanonical Base64 assignment' }
    return $Decoded
}

$Worktree = ConvertFrom-RoundletBase64 $WorktreeBase64
$WorktreeCanaryPath = ConvertFrom-RoundletBase64 $WorktreeCanaryPathBase64
$IndexCanaryPath = ConvertFrom-RoundletBase64 $IndexCanaryPathBase64

function Get-TextSha256 {
    param([string]$Text)
    $Hasher = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($Hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($Text)))).Replace('-', '') }
    finally { $Hasher.Dispose() }
}

if ([string]::IsNullOrWhiteSpace($Worktree)) { throw 'worktree path is empty' }
if ($Worktree.Contains("'") -or $Worktree.Contains("`r") -or $Worktree.Contains("`n")) { throw 'worktree path contains forbidden literal' }
if ([string]::IsNullOrWhiteSpace($WorktreeCanaryPath) -or [string]::IsNullOrWhiteSpace($IndexCanaryPath)) { throw 'canary filename is empty' }
if ($WorktreeCanaryPath -match '[\\/''\s]' -or $IndexCanaryPath -match '[\\/''\s]') { throw 'canary path is not a direct-child filename' }
if ($WorktreeCanaryPath -eq $IndexCanaryPath) { throw 'canary filenames alias' }

$RootItem = Get-Item -LiteralPath ([IO.Path]::GetFullPath($Worktree)) -Force -ErrorAction Stop
if (-not $RootItem.PSIsContainer) { throw 'worktree root is not a directory' }
if (($RootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'worktree root is a reparse point' }
$TrimChars = [char[]]@([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
$CanonicalRoot = [IO.Path]::GetFullPath($RootItem.FullName).TrimEnd($TrimChars)
$WorktreeCanaryAbsolute = [IO.Path]::GetFullPath([IO.Path]::Combine($CanonicalRoot, $WorktreeCanaryPath))
$IndexCanaryAbsolute = [IO.Path]::GetFullPath([IO.Path]::Combine($CanonicalRoot, $IndexCanaryPath))
$WorktreeCanaryParent = [IO.Path]::GetFullPath([IO.Path]::GetDirectoryName($WorktreeCanaryAbsolute)).TrimEnd($TrimChars)
$IndexCanaryParent = [IO.Path]::GetFullPath([IO.Path]::GetDirectoryName($IndexCanaryAbsolute)).TrimEnd($TrimChars)
if (-not [string]::Equals($WorktreeCanaryParent, $CanonicalRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'worktree canary parent mismatch' }
if (-not [string]::Equals($IndexCanaryParent, $CanonicalRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'index canary parent mismatch' }
if (Test-Path -LiteralPath $WorktreeCanaryAbsolute) { throw 'worktree canary pre-exists' }
if (Test-Path -LiteralPath $IndexCanaryAbsolute) { throw 'index canary pre-exists' }

$IdentityRecord = 'runtime=NATIVE_WINDOWS' + "`n" +
    'root=' + $CanonicalRoot + "`n" +
    'root_attributes=' + ([int]$RootItem.Attributes) + "`n" +
    'worktree_canary=' + $WorktreeCanaryAbsolute + "`n" +
    'worktree_canary_absent=True' + "`n" +
    'index_canary=' + $IndexCanaryAbsolute + "`n" +
    'index_canary_absent=True'
$Result = [ordered]@{
    outcome = 'PASS'
    canonical_worktree_root = $CanonicalRoot
    worktree_canary = $WorktreeCanaryAbsolute
    index_canary = $IndexCanaryAbsolute
    initial_absence_root_identity_sha256 = Get-TextSha256 $IdentityRecord
}
ConvertTo-Json -InputObject $Result -Compress
```

Use the next PowerShell body verbatim for the one approved compound operation. This is also a native-Windows Worker template, not a cross-platform command. Because this route consumes the canary's sole approval, choose both canary paths as the same unique direct-child files verified by the preflight; this mode creates no canary parent directory. The nested-parent/two-turn finalization below is not used in this mode. Populate only the ten placeholder assignment values at the top: the four path values are the same validated standard padded Base64 UTF-8 encodings used or derived during preflight, the length is decimal, and every identity is exact fixed-width hexadecimal. Never insert a raw path into a PowerShell literal. Before parsing or creating either canary file, read back all ten populated assignment lines and compare each complete line byte-for-byte with the canonical assignment constructed from the bound value. Require exactly ten assignment lines, every placeholder absent, the four path right-hand sides to be single-quoted Base64 literals, the length right-hand side to be only the bound decimal integer, and the five identity right-hand sides to be only their bound single-quoted hexadecimal literals. A concatenation, interpolation, variable reference, method call such as `.Replace(...)`, or any other expression is invalid even when PowerShell can parse or evaluate it. Parse the fully populated body without executing it only after this literal read-back passes, and bind the populated-body SHA-256 before canary creation so the exact same bytes are submitted later. The body decodes and validates every path before reading the index. Do not rewrite its functions, control flow, Git calls, restoration guard, or output. Its strict Git wrapper keeps native stderr diagnostics separate from returned stdout identities: an exit-zero warning is recorded but cannot contaminate a HEAD/tree/status/entry/blob value, while a real non-zero still throws. After the raw preimage is captured, an encompassing `try`/`catch`/`finally` restores and verifies the exact index bytes on every success, native failure, or validation throw; it rethrows the primary failure after restoration and never masks it with later output. A path/preflight, literal-read-back, or parse failure occurs before canary mutation and is `FILESYSTEM_CAPABILITY_UNAVAILABLE`; never consume the approval or create an artifact after it. After the direct-`apply_patch` files and exact content hashes are verified, require the retained body's SHA-256 to equal the pre-creation populated-body digest and submit those exact same parsed bytes as the single approved shell operation:

```powershell
$ErrorActionPreference = 'Stop'
$WorktreeBase64 = '<base64-utf8-absolute-linked-worktree>'
$IndexPathBase64 = '<base64-utf8-absolute-resolved-index>'
$WorktreeCanaryPathBase64 = '<base64-utf8-posix-relative-worktree-canary-path>'
$IndexCanaryPathBase64 = '<base64-utf8-posix-relative-index-canary-path>'
$ExpectedIndexLength = <decimal-integer>
$ExpectedIndexSha256 = '<64-hex>'
$ExpectedHead = '<40-lowercase-hex>'
$ExpectedTree = '<40-lowercase-hex>'
$ExpectedEntriesSha256 = '<64-hex>'
$ExpectedIndexCanaryFileSha256 = '<64-hex>'

function ConvertFrom-RoundletBase64 {
    param([string]$Value)
    if ($Value -notmatch '^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$') { throw 'invalid Base64 assignment' }
    try { $Bytes = [Convert]::FromBase64String($Value) }
    catch { throw 'invalid Base64 assignment' }
    $Utf8 = [Text.UTF8Encoding]::new($false, $true)
    try { $Decoded = $Utf8.GetString($Bytes) }
    catch { throw 'invalid UTF-8 assignment' }
    if ([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Decoded)) -ne $Value) { throw 'noncanonical Base64 assignment' }
    return $Decoded
}

$Worktree = ConvertFrom-RoundletBase64 $WorktreeBase64
$IndexPath = ConvertFrom-RoundletBase64 $IndexPathBase64
$WorktreeCanaryPath = ConvertFrom-RoundletBase64 $WorktreeCanaryPathBase64
$IndexCanaryPath = ConvertFrom-RoundletBase64 $IndexCanaryPathBase64

function Get-BytesSha256 {
    param([byte[]]$Bytes)
    $Hasher = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($Hasher.ComputeHash($Bytes))).Replace('-', '') }
    finally { $Hasher.Dispose() }
}

function Get-TextSha256 {
    param([string]$Text)
    return Get-BytesSha256 ([Text.Encoding]::UTF8.GetBytes($Text))
}

$script:RoundletGitDiagnostics = New-Object 'System.Collections.Generic.List[string]'

function Invoke-GitStrict {
    param([string[]]$CommandArgs)
    $PriorErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $CommandCombined = @(& git @CommandArgs 2>&1)
        $CommandExit = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $PriorErrorActionPreference
    }
    $CommandStdout = New-Object 'System.Collections.Generic.List[string]'
    $CommandStderr = New-Object 'System.Collections.Generic.List[string]'
    foreach ($Item in $CommandCombined) {
        if ($Item -is [System.Management.Automation.ErrorRecord]) {
            $CommandStderr.Add($Item.ToString())
        }
        else {
            $CommandStdout.Add($Item.ToString())
        }
    }
    if ($CommandStderr.Count -gt 0) {
        $script:RoundletGitDiagnostics.Add(('args=' + ($CommandArgs -join ' ') + ' stderr=' + ($CommandStderr -join ' | ')))
    }
    if ($CommandExit -ne 0) {
        throw ('git failed exit=' + $CommandExit + ' args=' + ($CommandArgs -join ' ') + ' stdout=' + ($CommandStdout -join ' | ') + ' stderr=' + ($CommandStderr -join ' | '))
    }
    return [string[]]$CommandStdout.ToArray()
}

if ([string]::IsNullOrWhiteSpace($Worktree) -or [string]::IsNullOrWhiteSpace($IndexPath)) { throw 'worktree or index path is empty' }
if ($Worktree.Contains("'") -or $Worktree.Contains("`r") -or $Worktree.Contains("`n")) { throw 'worktree path contains forbidden literal' }
if ($IndexPath.Contains("'") -or $IndexPath.Contains("`r") -or $IndexPath.Contains("`n")) { throw 'index path contains forbidden literal' }
if ([IO.Path]::GetFullPath($IndexPath) -eq [IO.Path]::GetFullPath($Worktree)) { throw 'index/worktree alias' }
if ($IndexCanaryPath -match '[\\/''\s]' -or $WorktreeCanaryPath -match '[\\/''\s]') { throw 'canary path is not a direct-child filename' }
$IndexPreimage = [IO.File]::ReadAllBytes($IndexPath)
$PreimageHash = Get-BytesSha256 $IndexPreimage
if ($IndexPreimage.Length -ne $ExpectedIndexLength -or $PreimageHash -ne $ExpectedIndexSha256) { throw 'raw index preimage mismatch' }
if (Test-Path -LiteralPath ($IndexPath + '.lock')) { throw 'index.lock pre-exists' }

$GitBase = [string[]]@('-c', ('safe.directory=' + $Worktree), '-C', $Worktree)
$PrimaryFailure = $null
$RestorationFailure = $null
try {
    $InitialHead = ((Invoke-GitStrict ($GitBase + @('rev-parse', 'HEAD'))) -join "`n").Trim()
    if ($InitialHead -ne $ExpectedHead) { throw 'initial HEAD mismatch' }
    $InitialStatus = [string[]]@(Invoke-GitStrict ($GitBase + @('status', '--porcelain=v1', '--untracked-files=all')))
    $ExpectedStatus = [string[]]@(('?? ' + $WorktreeCanaryPath), ('?? ' + $IndexCanaryPath))
    [Array]::Sort($ExpectedStatus, [StringComparer]::Ordinal)
    if (($InitialStatus -join "`n") -ne ($ExpectedStatus -join "`n")) { throw ('initial status mismatch: ' + ($InitialStatus -join ' | ')) }
    $InitialTree = ((Invoke-GitStrict ($GitBase + @('write-tree'))) -join "`n").Trim()
    if ($InitialTree -ne $ExpectedTree) { throw 'initial tree mismatch' }
    $InitialEntries = (Invoke-GitStrict ($GitBase + @('ls-files', '--stage'))) -join "`n"
    if ((Get-TextSha256 $InitialEntries) -ne $ExpectedEntriesSha256) { throw 'initial entries mismatch' }
    [IO.File]::WriteAllBytes($IndexPath, $IndexPreimage)

    $Null = Invoke-GitStrict ($GitBase + @('add', '--', $IndexCanaryPath))
    $EntryLines = [string[]]@(Invoke-GitStrict ($GitBase + @('ls-files', '--stage', '--', $IndexCanaryPath)))
    if ($EntryLines.Count -ne 1) { throw 'staged entry count mismatch' }
    $EntryParts = $EntryLines[0] -split '\s+', 4
    if ($EntryParts.Count -ne 4 -or $EntryParts[0] -ne '100644' -or $EntryParts[2] -ne '0' -or $EntryParts[3] -ne $IndexCanaryPath) { throw ('staged entry mismatch: ' + $EntryLines[0]) }
    $Blob = ((Invoke-GitStrict ($GitBase + @('hash-object', '--no-filters', '--', $IndexCanaryPath))) -join "`n").Trim()
    if ($EntryParts[1] -ne $Blob) { throw 'staged blob mismatch' }
    $IndexCanaryAbsolute = Join-Path $Worktree ($IndexCanaryPath.Replace('/', [IO.Path]::DirectorySeparatorChar))
    $CanaryFileHash = (Get-FileHash -LiteralPath $IndexCanaryAbsolute -Algorithm SHA256).Hash
    if ($CanaryFileHash -ne $ExpectedIndexCanaryFileSha256) { throw 'canary file hash mismatch' }
    $BlobSize = [int](((Invoke-GitStrict ($GitBase + @('cat-file', '-s', $Blob))) -join "`n").Trim())
    if ($BlobSize -ne (Get-Item -LiteralPath $IndexCanaryAbsolute).Length) { throw 'blob size mismatch' }

    [IO.File]::WriteAllBytes($IndexPath, $IndexPreimage)
    $FinalHead = ((Invoke-GitStrict ($GitBase + @('rev-parse', 'HEAD'))) -join "`n").Trim()
    if ($FinalHead -ne $ExpectedHead) { throw 'final HEAD mismatch' }
    $FinalStatus = [string[]]@(Invoke-GitStrict ($GitBase + @('status', '--porcelain=v1', '--untracked-files=all')))
    if (($FinalStatus -join "`n") -ne ($InitialStatus -join "`n")) { throw 'final status mismatch' }
    $FinalEntries = (Invoke-GitStrict ($GitBase + @('ls-files', '--stage'))) -join "`n"
    $FinalEntriesHash = Get-TextSha256 $FinalEntries
    if ($FinalEntriesHash -ne $ExpectedEntriesSha256) { throw 'final entries mismatch' }
    $FinalTree = ((Invoke-GitStrict ($GitBase + @('write-tree'))) -join "`n").Trim()
    if ($FinalTree -ne $ExpectedTree) { throw 'final tree mismatch' }
}
catch {
    $PrimaryFailure = $_
}
finally {
    try {
        [IO.File]::WriteAllBytes($IndexPath, $IndexPreimage)
        $FinalIndexLength = (Get-Item -LiteralPath $IndexPath).Length
        $FinalIndexSha256 = (Get-FileHash -LiteralPath $IndexPath -Algorithm SHA256).Hash
        if ($FinalIndexLength -ne $ExpectedIndexLength -or $FinalIndexSha256 -ne $ExpectedIndexSha256) { throw 'final raw index mismatch' }
        if (Test-Path -LiteralPath ($IndexPath + '.lock')) { throw 'index.lock remains' }
    }
    catch {
        $RestorationFailure = $_
    }
}
if ($null -ne $PrimaryFailure) {
    if ($null -ne $RestorationFailure) {
        throw ('primary failure: ' + $PrimaryFailure.Exception.Message + '; restoration failure: ' + $RestorationFailure.Exception.Message)
    }
    throw $PrimaryFailure
}
if ($null -ne $RestorationFailure) { throw $RestorationFailure }
$DiagnosticsText = $script:RoundletGitDiagnostics -join "`n"
$Result = [ordered]@{ outcome = 'PASS'; entry = $EntryLines[0]; blob = $Blob; blob_size = $BlobSize; canary_file_sha256 = $CanaryFileHash; initial_head = $InitialHead; final_head = $FinalHead; initial_tree = $InitialTree; final_tree = $FinalTree; final_entries_sha256 = $FinalEntriesHash; final_index_length = $FinalIndexLength; final_index_sha256 = $FinalIndexSha256; index_lock_exists = $false; git_diagnostics_count = $script:RoundletGitDiagnostics.Count; git_diagnostics_sha256 = Get-TextSha256 $DiagnosticsText }
ConvertTo-Json -InputObject $Result -Compress
```

The compound operation is one retry and one typed outcome. It may not be split into multiple approval requests, broadened to another worktree/index/path, reused for implementation or source edits, or treated as permission for file cleanup. Denial, unavailable approval, parse failure, any launched non-zero suboperation, identity mismatch, raw-byte mismatch, lock residue, or incomplete read-back is the corresponding typed failure and `FILESYSTEM_CAPABILITY_UNAVAILABLE`.

#### Native Windows canary empty-parent finalization

This exception applies only to a Worker canary running with `worker_runtime: NATIVE_WINDOWS` whose index route did not consume the configured approval and whose direct patch route left a qualifying nested parent. It does not apply to the out-of-root direct-child-file index mode above, a Launcher, WSL, Linux, macOS, any other host/runtime, an implementation or source-file edit, advisory run state, a task anchor, a linked-worktree root, or post-archive worktree cleanup.

The Worker must still create, change, and delete every canary file through the dedicated `apply_patch` tool in its normal writable-worktree sandbox. If `apply_patch` removes every canary file but leaves the canary-created parent directory, use this two-turn protocol:

1. On the mutation turn, the Worker restores and verifies the exact raw index and every surrounding identity, proves that the parent was initially absent, is the exact nonce-bound child expected by the canary, resolves inside but is not equal to the exact linked-worktree root, is an ordinary directory rather than a symlink, junction, mount point, or other reparse point, and contains zero entries including hidden and system entries. It returns `WINDOWS_CANARY_EMPTY_PARENT_READY`, not `FILESYSTEM_CANARY_RESULT`, and makes no further mutation.
2. The external creator independently verifies the mutation turn's task/profile read-back and all of those path, identity, containment, non-reparse, emptiness, restored-index, and no-transition facts. It may then remove only that exact directory with the narrowest host-supported exact-path directory operation. The operation must be nonrecursive and non-force; for PowerShell this means `Remove-Item -LiteralPath <exact-parent>` without `-Recurse` or `-Force`. It must not delete or modify a file, ancestor, sibling, worktree root, task anchor, `.roundlet` state, repository root, or user path. A restriction may receive only the still-available configured narrow approval retry; ambiguity, nonemptiness, changed identity, denial, unavailable approval, or launched failure stops the canary.
3. The creator reads back exact parent absence and independently rereads the same Worker's stable task/profile. It sends that Worker one fresh metadata-gated read-only finalization turn binding the mutation turn and external-cleanup evidence. The Worker rereads immutable metadata, verifies the parent remains absent, the worktree and raw index still equal the captured initial identities, no canary artifact remains, and no repository transition occurred. Only that finalization turn may return the canonical `FILESYSTEM_CANARY_RESULT` with `cleanup: VERIFIED`; its `metadata_turn` is the finalization turn, while the evidence digest binds both turns and the external removal.

`WINDOWS_CANARY_EMPTY_PARENT_READY` is incomplete evidence and cannot enter an aggregate, authorize a transition, or be relabeled as a failed or successful canonical result. If the external creator or the same Worker cannot complete the exact finalization, the Worker returns a truthful canonical failure when safely possible; otherwise the creator retains the bounded incomplete record and classifies `FILESYSTEM_CAPABILITY_UNAVAILABLE`. Later environment repair never promotes that attempt.

Other runtimes retain their existing platform-appropriate task/worktree topology and cleanup rules without a task-anchor requirement.

Classify the control path exactly:

- `DIRECT_EXECUTION_FAILED`: the normal requested operation required no approval, launched, and returned non-zero or an equivalent launched-failure result.
- `ESCALATION_DENIED`: the host explicitly reports that the requested approval was denied.
- `ESCALATION_UNAVAILABLE`: the host exposes no supported approval path for the required operation.
- `ESCALATED_EXECUTION_FAILED`: approval succeeded and the requested operation launched, but execution returned non-zero or an equivalent launched-failure result.
- `FILESYSTEM_CAPABILITY_UNAVAILABLE`: the exact required create/edit/read-back/identity/restore/cleanup surface is not fully proven. Preserve the more specific approval or execution cause alongside this final capability result.

An initial restricted or sandboxed attempt is evidence only. Request the narrowest host-supported approval for the same exact target and operation, at most `approval_retry_limit` times. Never convert a launched failure into an approval denial, switch to an unproven helper or broader target, prescribe host internals, or retry indefinitely. Every shell wrapper must preserve the first failing Git/subprocess exit as the operation's non-zero result; later output, formatting, or object construction cannot turn it into success. Except for the explicitly runtime-gated native-Windows Worker contracts above, the control taxonomy is independent of operating system, shell, command syntax, and helper executable.

`approval_retry_count` counts actual host-supported approval retries, not the initial normal attempt. Only these control tuples are valid: `(0, NOT_REQUIRED, SUCCEEDED)`, `(0, NOT_REQUIRED, DIRECT_EXECUTION_FAILED)`, `(1, APPROVED, SUCCEEDED)`, `(1, APPROVED, ESCALATED_EXECUTION_FAILED)`, `(1, ESCALATION_DENIED, NOT_LAUNCHED)`, and `(0, ESCALATION_UNAVAILABLE, NOT_LAUNCHED)`. `capability_outcome` is `PASS` only when execution succeeded, every required surface and read-back passed, and cleanup/restoration is `VERIFIED`; every other tuple produces `FILESYSTEM_CAPABILITY_UNAVAILABLE`. Cleanup remains independently truthful even when execution or capability fails.

Any read-back mismatch, index mismatch, stale task/host/route identity, or cleanup/restoration failure yields `FILESYSTEM_CAPABILITY_UNAVAILABLE`. A Launcher/activation-Worker canary failure stops activation before contract creation or persistent run resources. A failure in the required live Orchestrator repeat leaves activation incomplete, attaches no heartbeat, selects no issue, retains truthful bounded evidence and any unclean resource, and removes only artifacts whose cleanup can be proven. A persistent issue Worker failure retains the read-only-selected leaf identity, provisional local branch/worktree/Worker resources, and local or failed-only task-response evidence in `FILESYSTEM_CAPABILITY_BLOCKED`; it creates no GitHub trace or selection, source edit, implementation commit, push, or pull request. Only after a valid aggregate is accepted and read back may the Orchestrator publish the selection trace. Recovery and migration retain all existing tasks, heartbeat, branch, worktree, pull request, issue, SHA, contract, and unique work; pause and enter `FILESYSTEM_CAPABILITY_BLOCKED` before any advisory, Git, or GitHub transition. Do not claim cleanup when an artifact remains.

Store only bounded evidence: phase, role/task ID, task-metadata-verified execution profile in the exact string form `model=<exact-model-id>;reasoning_effort=<exact-effort>`, nonce digest, host/checkout/worktree identity, exact target paths in local recovery state (public traces use only path digests), initial/final state digests, expected/observed content hashes, index entry hash, approval request count, typed approval/execution/capability outcomes, cleanup status, and time. Raw tool output and private permission traces remain local. Before a transition set is accepted, any changed task, host, checkout/worktree, permission route, mutation tool class, or candidate role model/effort invalidates its result and requires a fresh canary. After exact aggregate read-back completes that transition, required archival/removal of a clean short-lived canary task/worktree does not rewrite or invalidate the immutable historical set. That set proves only its named transition and can never authorize a later transition; every later transition builds a fresh applicable set, and continuing live roles must still match their recorded route until that transition completes.

Aggregate every transition's required role results as one canonical `roundlet-filesystem-canary-set/v1` JSON manifest. It contains exactly `schema`, `run_id`, `transition`, and `results`; `transition` is one of the phase values in the role result contract. Each `results` entry contains exactly `phase`, `role`, `role_task`, `execution_profile`, `host_route_fingerprint`, `advisory_surface`, `worktree_surface`, `index_surface`, `cleanup`, and `result_sha256`; `result_sha256` hashes the exact stored UTF-8 `FILESYSTEM_CANARY_RESULT` bytes without BOM or trailing newline. Decode those exact bytes, independently verify its `metadata_turn` against the creator-side exact populated-turn record, and require the result's `run_id` to equal manifest `run_id`, its `phase` to equal manifest `transition`, its `repository_transition` to be `none`, and every projected phase/role/task/profile/route/surface/cleanup value to equal the entry exactly. Sort entries by the unsigned UTF-8 byte tuple `(phase, role, role_task, execution_profile, host_route_fingerprint)`, reject duplicate tuples, serialize with the contract manifest's RFC 8785 rules, and identify the set by `sha256:<lowercase-hex>` of those canonical bytes. A valid set includes every role/surface required for its transition. Every Launcher `execution_profile` must equal task metadata and the exact expected Launcher model/effort bound in the owner-delivered activation or recovery prompt; its `role_task` must equal the metadata-read actual task ID and the task ID independently read back by the external creator after dispatch. Every Orchestrator/Worker `execution_profile` must equal task metadata plus the effective resolved role configuration, or the candidate resolved role configuration for adoption/migration. The set marks every required surface `PASS`, marks only inapplicable surfaces `NOT_APPLICABLE`, records `cleanup: VERIFIED` for every entry, and verifies every result hash and decoded field. Missing, extra, duplicate, cross-run, cross-phase, stale, failed, overwritten, or projection-mismatched entries invalidate the whole set.

Required sets are: activation = Launcher advisory, short-lived activation Worker worktree/index, and live Orchestrator advisory; issue claim = a fresh live Orchestrator advisory result immediately before selection plus the newly created persistent Worker worktree/index result; recovery = recovery Launcher when used plus the recovered live Orchestrator and, when an active leaf retains a Worker, that same Worker on its worktree/index surfaces; legacy bootstrap or active in-place migration = the same Orchestrator advisory plus, when an active leaf retains a Worker, that same Worker worktree/index; between-issue adoption = same Orchestrator advisory plus a short-lived candidate-configured Worker worktree/index; benchmark = every role and all three surfaces named by the benchmark plan. A required retained Worker that is inaccessible invalidates the set; a phase with no Worker does not invent one. Persist and bind only the aggregate digest where a single evidence reference is required. Store each accepted set at `.roundlet/canary-evidence/accepted/<aggregate-sha256-hex>/manifest.json` with its exact result bytes at `results/<zero-padded-ordinal>-<result-sha256-hex>.txt`; write and read back every result first and the canonical manifest last. Once accepted, those bytes are immutable. When the exact advisory route remains writable and readable, store every failed or incomplete attempt under `.roundlet/canary-evidence/failed/<run-id>/<attempt-id>/` with one bounded `attempt.json` plus any exact bounded result bytes. If the failed surface is the advisory route and that exact route cannot create and read back this store, preserve the exact bounded result only in the existing immutable task response, addressed by task ID, response/event ID, and result digest; do not switch helpers or routes merely to create local evidence. This no-write representation is failed evidence only, can never appear under `accepted`, and cannot authorize a transition. Failed evidence is immutable, is never promoted into `accepted`, and contains no raw tool output. An existing path with conflicting bytes fails closed. `current.md` points to the accepted or failed evidence paths and marks each accepted entry as currently applicable or completed-and-cleaned without changing the canonical manifest; only currently applicable live-role entries participate in route-freshness checks, while completed-and-cleaned entries remain immutable evidence for that transition. Activation, recovery, full reconciliation, migration preparation/commit, and stop must enumerate and verify every referenced manifest/result byte before relying on or removing evidence. External cleanup after a failed result is environment repair only and never changes that result or makes its set valid.

Any future model, effort, permission, or contract change that can affect Orchestrator/Worker mutations requires a bounded live benchmark on a disposable authorized target. It must use real task/tool calls on all three surfaces, cover each typed outcome and successful cleanup, and read back no-transition behavior. A zero-tool synthetic benchmark can supplement but never replace this gate.

## Task and worktree resource cleanup

Artifact/index cleanup inside `FILESYSTEM_CANARY_RESULT` and post-acceptance task/worktree cleanup are distinct. Accepting an immutable canary set proves only the former. Archiving a task, removing a Git worktree registration, emptying a directory, and removing the physical candidate path are also distinct facts; no one fact proves the others.

After the aggregate is accepted and read back, the external creator or Orchestrator performs bounded post-archive reconciliation:

1. Capture the exact short-lived task ID, task host, worktree path, Git registration, physical-path identity, unique-work status, and any live process whose current directory equals that exact canonical worktree path before archive.
2. Archive the task and require an archive acknowledgement, then use bounded waits and external read-back rather than the archived task's self-report.
3. Require the task to be non-active, the exact Git worktree registration to be absent, no unique or unpreserved work to remain, no live process to retain that exact canonical path as its current directory, and the physical candidate path to be absent.
4. If the path is empty and unregistered but a current-directory holder survives, do not remove the path or kill the process. Report cleanup incomplete with the exact bounded holder/path evidence and fail closed.
5. If no holder, registration, unique work, or contents remain, normal non-force removal of only the exact candidate path is permitted when authority allows; read back absence. A missing process-inspection or physical-path route is unverified cleanup, not success.

Never force-remove a worktree, terminate Codex/Node or role processes, broaden the target, or relabel later environment repair as historical `cleanup: VERIFIED`. Activation attaches no heartbeat after incomplete short-lived cleanup. Adoption, recovery, migration, issue cleanup, and stop retain their current resources and enter their defined blocked state.

## Advisory local state

Add `.roundlet/` to the authoritative checkout's local `.git/info/exclude`. Never commit the exclusion or local contract snapshots. Keep only:

- `.roundlet/lease.json`: stable run ownership, task identities, and immutable activation contract ID; any active-contract value is only a derived mirror;
- `.roundlet/current.md`: concise human-readable recovery index for current state and a derived effective-contract mirror;
- `.roundlet/contracts/<contract-id>/`: read-only activation or adoption/migration snapshots containing `SKILL.md`, every required reference, the resolved role configuration, and the canonical manifest;
- `.roundlet/canary-evidence/accepted/<aggregate-sha256-hex>/` and `.roundlet/canary-evidence/failed/<run-id>/<attempt-id>/`: immutable bounded canary manifests/results and failed-attempt evidence;
- `.roundlet/legacy-activation.json`: optional one-time immutable activation record for a provably pre-contract run;
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

`current.md` records only pointers and reconciliation facts: phase, immutable activation ID, derived effective-contract ID and bundle path, installed-candidate fingerprint, pending adoption/migration identity when present, last verified filesystem-canary evidence-set digest and accepted/failed evidence paths plus every entry's phase/role/task/execution-profile/host/route identity, issue and umbrella URLs/numbers, pull-request URL/number, Worker task, current Supervisor task when one exists, branch, worktree, base and candidate full SHAs, review epoch/round/mode, Supervisor attempt number/profile, last durable GitHub event, blocking condition, last full reconciliation time, and the bounded semantic baseline plus cadence state defined below. Do not treat it as durable history or append a transcript.

Before every tick or mutation, verify the active bundle and reconcile both files against GitHub, Git, Codex tasks, and the heartbeat. Prefer live authoritative evidence. When evidence conflicts, stop with `STATE_RECONCILIATION_REQUIRES_OWNER`; never guess or overwrite the conflict.

## Pinned run contract and migration

At activation, hash exactly `SKILL.md` and every required reference named by it, including `references/roundlet-config.json`; paths are unique POSIX-style relative paths with no `..`, NUL, CR, or LF and are sorted lexicographically by their unsigned UTF-8 byte sequences. For each path, hash its exact stored bytes without newline normalization. The `roundlet-tree/v1` digest input is ASCII `roundlet-tree/v1\n` followed, for each sorted file, by UTF-8 path bytes, one `0x00` byte, the 64 lowercase ASCII SHA-256 hex bytes, and one `0x0a` byte. `tree_digest` is `sha256:<lowercase-hex>` of that complete byte sequence.

The hash-input manifest has exactly this JSON shape and no extra fields:

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

`resolved_config` is the complete parsed JSON value from `roundlet-config.json` without defaults or coercion. For `git`, `locator` is canonical `owner/repository` and `ref` is the verified 40-character lowercase commit OID whose files match every bundled byte. Otherwise `kind` is `installed-tree`, `locator` is the resolved absolute installed skill directory, and `ref` is the exact `tree_digest`. `contract_version` appends that exact `ref`.

Canonical JSON follows RFC 8785 JSON Canonicalization Scheme exactly and has no BOM or trailing newline. Floating-point values are forbidden; arrays retain source order except `files`, which uses the UTF-8-byte path order above. Compute the lowercase contract ID as SHA-256 of these bytes. Add top-level `"contract_id":"<64-lowercase-hex>"`, reserialize under the same rules, copy the exact files and stored manifest into `.roundlet/contracts/<contract-id>/`, and read back the complete bundle. An existing directory with that ID but different bytes is `CONTRACT_BUNDLE_CONFLICT`.

Each `prepared.json` is an RFC 8785 canonical JSON object with exactly `schema` (`roundlet-contract-migration-prepared/v1`), positive integer `sequence`, `migration_id`, `run_id`, `mode`, `old_contract_id`, `new_contract_id`, `candidate_source`, `candidate_ref`, `owner_authorization_event`, `orchestrator_task`, `orchestrator_model`, `reasoning_effort`, `model_readback_source`, `filesystem_canary_evidence_set_digest`, `filesystem_canary_evidence_path`, `bundle_manifest_sha256`, and `prepared_at`. Its sibling `committed.json` is an RFC 8785 canonical JSON object with exactly `schema` (`roundlet-contract-migration-committed/v1`), `migration_id`, `prepared_sha256`, `ready_evidence_sha256`, `truthful_checkpoint_sha256`, `old_contract_id`, `new_contract_id`, and `committed_at`. Hash fields use `sha256:<64-lowercase-hex>`; both records have no BOM or trailing newline and are immutable after exact read-back.

For a legacy lease without an activation ID, accept exactly one fully verified `roundlet-legacy-activation/v1` record created from an owner-named immutable activation source/ref whose complete bytes agree with the original task/bootstrap metadata, activation time, installation provenance, durable trace, and role configuration. Current installed bytes alone are never evidence. A partial or conflicting record has no effect; multiple valid records fail closed. Once valid, its old contract ID is the immutable activation ID.

The activation ID in a contract-aware lease is immutable. The effective active contract is the activation ID followed by the longest unique chain of fully valid `committed.json` records whose `old_contract_id` links exactly to the prior ID and whose prepared record, owner authorization, bundle, model/effort metadata, externally verified READY evidence, truthful checkpoint, and every recorded hash all verify. Ignore incomplete prepared records. Multiple valid successors, a gap, malformed record, or mirror disagreement fails closed. Lease/current active values are derived recovery mirrors and never choose the contract.

Every active Orchestrator, Worker, Supervisor, heartbeat, routine owner, and recovery turn reads only the effective bundle; routine and recovery prompts do not invoke the installed `$roundlet` skill. The observation baseline fingerprints the verified effective bundle and installed candidate separately. Installed drift never authorizes a repository transition.

At clean `IDLE` with no leaf resources, drift enters `CONTRACT_ADOPTION_REQUIRED`; after exact allowlisted-owner authorization it may enter `CONTRACT_ADOPTING`. In all other phases it enters `CONTRACT_MIGRATION_REQUIRED`, retains the run, Orchestrator, heartbeat, Worker, branch, worktree, pull request, issue, candidate SHA, and review state, and may enter `CONTRACT_MIGRATING` only after exact authorization. Both paths pause the heartbeat and require a same-task follow-up whose actual candidate model/effort and task identity are proven from task metadata.

Stage and verify the new bundle and `prepared.json`, write a truthful checkpoint, and end the preparation turn with the structured acknowledgement without creating `committed.json`. After external verification, a second same-task follow-up under the same candidate model/effort revalidates every input; creating one fully valid `committed.json` is its single commit point. A failure before it leaves the old contract effective. After it, the new contract is effective even if a derived mirror update fails; pause and reconstruct mirrors from the committed chain before any other transition. Never roll back or guess. Preserve old bundles and migration records until the run stops.

## Lightweight observation and heartbeat cadence

Use two tiers. The observation tier asks only whether the last full reconciliation is still current. The full tier reads and reasons over the live semantic sources. Never use observation metadata to select, claim, review, mark ready, merge, close, clean up, change scope, or make another mutation.

### Bounded semantic baseline and cadence state

After every successful full reconciliation, replace the prior semantic baseline in `current.md` with these bounded facts:

- the verified active contract manifest, a complete bundled-file fingerprint, the stable lease, and the last valid filesystem-canary evidence-set digest, accepted evidence path, and every entry's task/execution-profile/host/route fingerprint;
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
- `FILESYSTEM_CAPABILITY_BLOCKED`
- `LEGACY_CONTRACT_BOOTSTRAP_REQUIRED`
- `LEGACY_CONTRACT_BOOTSTRAPPING`
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
2. Provision a descriptive local `codex/` branch from exact `origin/main` solely as the provisional substrate required to test the exact persistent-Worker route. For WSL and non-Windows runtimes, create the isolated worktree now through the existing platform-appropriate flow. For native Windows only, defer linked-worktree creation until the task anchor is bound in step 3. This bounded setup exception is not a claim or implementation transition: make no commit, push, GitHub trace, pull request, or source edit.
3. Create the intended persistent Worker task with the configured model and effort, send only the metadata handshake, and independently verify its immutable task/profile. For native Windows only, record its exact host-owned task-anchor CWD and create the removable worktree as a distinct writable descendant. Other runtimes use the worktree already created in step 2 and retain their prior topology. Read back the branch, worktree, `HEAD`, status, index, and, only on native Windows, task-anchor/path-separation identities before any canary. Record their identities and phase only in local advisory state; send no implementation contract.
4. In the Orchestrator task, run a fresh `ISSUE_CLAIM` advisory canary whose context binds the read-only-selected leaf, the existing provisional branch, and the authoritative checkout as the Orchestrator worktree. Retain its exact verified result bytes. On failure, enter `FILESYSTEM_CAPABILITY_BLOCKED` with the provisional branch/worktree retained before recording selection.
5. Send that Worker the `ISSUE_CLAIM` canary contract from `thread-prompts.md`; bind the same selected leaf and provisional branch, the exact provisional linked worktree as this role's worktree, and, on native Windows only, its exact task anchor. Require worktree/index PASS, cleanup VERIFIED, restored initial identities, and a valid aggregate evidence set with the fresh same-phase Orchestrator result. On failure, enter `FILESYSTEM_CAPABILITY_BLOCKED` with the read-only-selected leaf and provisional resources retained; make no GitHub selection, implementation, commit, push, or pull-request transition.
6. Only after that exact-task canary, immutable aggregate persistence, and aggregate read-back pass, recheck leaf eligibility and record the selection event on GitHub. The provisional branch/worktree/Worker then become the claimed issue resources.
7. Send that same Worker the initial implementation contract from `thread-prompts.md`.

Use the same Worker task for every subsequent repair, final repair, and cleanup preflight. The Worker may read GitHub but must never create/edit comments, issues, pull requests, labels, reviews, merges, or branches on GitHub. It modifies the isolated worktree and returns structured handoffs to the Orchestrator.

For every Worker turn, independently verify the stable Worker task/profile before dispatch, populate `role_task` and `execution_profile`, insert the complete populated-turn metadata gate, and require the returned `role_task`, new `metadata_turn`, and profile to pass creator-side exact-turn read-back before accepting the handoff. Also verify and bind the actual `worker_runtime` value from `thread-prompts.md`. On native Windows only, insert the complete native-Windows topology and patch-routing block into each Worker prompt that may edit files. Canary-artifact create/change/delete operations and source patches must stay on the dedicated `apply_patch` tool in the normal sandbox of the assigned writable worktree; a PowerShell, pipeline, here-string/here-document, batch-wrapper, or elevated-shell invocation is not an alternate patch route. If the dedicated route is absent or cannot write the assigned root, keep the exact issue resources and Git state unchanged, preserve truthful canary cleanup evidence, classify the result as `FILESYSTEM_CAPABILITY_UNAVAILABLE`, and stop through the active typed filesystem contract or `NEEDS_OWNER_INPUT` fallback defined by the Worker prompt. Do not reinterpret it as an approval denial or retry it through host elevation.

This conditional route does not apply to WSL or non-Windows Workers and does not alter their normal editing behavior. It also does not prohibit a separately justified, narrowly approved host operation for GitHub, network, or an authorized out-of-root target when that operation is not a source patch.

After a valid initial handoff:

1. Verify the reported before/after SHAs, diff, status, tests, and issue scope independently.
2. For a native-Windows Worker, verify every applicable canary artifact and source edit used the dedicated normal-sandbox patch route and no shell-wrapped or elevated `apply_patch`; reject and fail closed on missing or contradictory route evidence.
3. Push the exact candidate commit without force.
4. Append the Worker handoff to the leaf issue.
5. Create a draft pull request linking the umbrella with a non-closing reference when present, linking the leaf, and including `Closes #<leaf>` for that active leaf only. Never couple `close`, `closes`, `closed`, `fix`, `fixes`, `fixed`, `resolve`, `resolves`, or `resolved` to an umbrella or any other non-terminal issue number, even inside a negated sentence.
6. Append a draft-pull-request trace to the pull request and update the local recovery index.

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

Do not enter this state for an initial sandbox denial or a transient GitHub CLI transport failure. First apply the bounded GitHub recovery contract or filesystem-canary approval retry, as applicable. For filesystem capability, preserve the exact `DIRECT_EXECUTION_FAILED`, `ESCALATION_DENIED`, `ESCALATION_UNAVAILABLE`, or `ESCALATED_EXECUTION_FAILED` cause and use `FILESYSTEM_CAPABILITY_UNAVAILABLE` only as the final unproven-surface result. A resulting explicit approval denial, unavailable approval mechanism, confirmed authentication rejection from reachable GitHub, or proven unavailable required connectivity is a valid blocking condition.

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
2. The Orchestrator independently verifies the handoff, captures the task/worktree resource-cleanup baseline, and archives the Worker task.
3. Apply the task/worktree resource-cleanup contract. When `allow_remove_worktree` is true, use only non-destructive normal removal after proving no process has the exact Roundlet-owned worktree as its current directory and no Git registration conflict, unique work, or unknown change exists; then read back task inactivity, Git-registration absence, and physical worktree-path absence. Never force removal or terminate a process to release a path.
4. When `allow_delete_local_branch` is true, delete the local issue branch only after proving its unique work is merged or explicitly authorized for abandonment.
5. When `allow_delete_remote_branch` is true, delete the exact remote issue branch only after proving its identity and merge/abandon state.
6. Fetch origin, fast-forward local `main`, and verify the authoritative checkout is clean and `HEAD == main == origin/main`.
7. Append the cleanup trace, clear the issue-specific pointers, reset the same heartbeat to `active_minutes`, and remove the advisory files, retained contract bundles, canary-evidence tree, legacy activation record, and migration records only when stopping; while continuing, retain the lease and set `current.md` to `IDLE` with new observation counters. Do not stop after a completed issue unless stop-after-current is already recorded.

On native Windows only, independently read the archived Worker's exact host-owned anchor as defined in [Native Windows Worker task anchor](#native-windows-worker-task-anchor). A surviving process at that distinct anchor is recorded host lifecycle evidence but is not a worktree holder and does not block removal of the separate linked worktree. This exception does not apply to WSL or any other host/runtime.

If any cleanup step or required external inspection fails, or any process retains the exact Roundlet-owned worktree as current directory, Git registration, unique work, or that physical worktree path survives, enter `CLEANUP_BLOCKED`, keep the leaf closed, retain the lease/current evidence, and select no next issue. Never reopen the leaf solely because cleanup failed.

## Active issue closed, ignored, or withdrawn

If the active leaf is closed, gains `roundlet:ignore`, or is withdrawn before the normal merge path completes, enter `OWNER_ABORT_DECISION_REQUIRED`. Accept only a new allowlisted comment or direct Orchestrator instruction choosing:

- `resume`: remove the blocking condition when needed and continue the same work;
- `preserve-and-stop`: keep the task, branch, worktree, pull request, and evidence, pause the heartbeat, and stop scheduling;
- `abandon-and-cleanup`: with exact scope, append a trace, close the pull request if open, archive role tasks, and clean only the explicitly authorized branch/worktree resources before returning to `IDLE`.

There is no preserve-old-work-while-selecting-next option. Never infer abandon-and-cleanup.

## Pause, resume, and stop

- `pause`: finish the current atomic mutation or stop before the next one, record `PAUSED`, pause the heartbeat so it performs no observations, and preserve all state/resources. Resume only in the same Orchestrator after reconciliation and an owner instruction.
- `stop-after-current`: if active, finish the current issue including cleanup; if idle, stop immediately. Then stop the heartbeat, record `STOPPED`, remove advisory state, retained contract bundles, canary-evidence tree, legacy activation record, and migration records after final reconciliation, and archive the Orchestrator.
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

### Bootstrap, adopt, or migrate the pinned contract

A pre-contract run must first use [`legacy run contract bootstrap`](launcher.md#owner-authorized-legacy-run-contract-bootstrap). After a pinned activation exists, when fully reconciled `IDLE` has no leaf resources, use [`between-issue contract adoption`](launcher.md#owner-authorized-between-issue-contract-adoption). Otherwise use [`in-place contract migration`](launcher.md#owner-authorized-in-place-contract-migration). Both keep the same Orchestrator task, require explicit owner authorization for the exact candidate plus task-metadata proof of the actual model/effort override, and make no repository transition.

### Stop after the current issue

```text
In the existing Orchestrator task, set stop-after-current for the active Roundlet run for <OWNER/REPOSITORY>. Resolve and read only the effective pinned contract bundle; do not invoke or load the installed `$roundlet` skill.

Reconcile first and record STOP_AFTER_CURRENT. If an issue is active, finish only that
issue through its normal review, merge gates, leaf closure, and ordered cleanup; select
no next issue. If the run is idle, stop immediately. At the terminal safe state, stop the
one heartbeat, record STOPPED, remove the advisory lease/current files, contract bundles, canary-evidence tree, legacy activation record,
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

- If an ordinary Orchestrator turn fails but its task and heartbeat remain accessible, the next heartbeat reads the active bundle, reconciles, and resumes idempotently only after current role-specific filesystem canaries remain valid or pass again.
- Recovery runs the advisory canary through the recovering Orchestrator and, when an active leaf retains a Worker, the worktree/index canaries through that same Worker before any checkpoint, Git, or GitHub transition. It aggregates every applicable same-phase result into the canonical recovery set. A failure retains every resource in `FILESYSTEM_CAPABILITY_BLOCKED`.
- If the Orchestrator or heartbeat is inaccessible, use the explicit recovery Launcher prompt. A stale-looking file is never enough to replace it.
- If the persistent Worker is inaccessible, require owner direction before creating a replacement because same-thread context is part of the contract.
- A failed Supervisor is disposable and may be retried under the bounded attempt rule.

During recovery, enumerate and verify every referenced accepted/failed canary-evidence manifest and result byte plus any failed no-write task-response identity/digest, verify and read the active contract bundle, then reconstruct from GitHub trace, exact remote/local Git state, Codex task evidence, and advisory files. Treat installed files only as a migration candidate. Stop on contradictions. Never hide a recovery correction by editing old GitHub comments.
