# Roundlet source repository policy

## Repository work

- Treat this repository as the source, test, review, and maintenance history for Roundlet.
- Preserve unrelated changes and worktrees. Develop changes in an isolated worktree and merge them only through a reviewed pull request with explicit owner approval.
- Never force-push, reset, rebase, bypass branch protection, publish releases, create tags, or delete unique work while performing ordinary repository work.

## Explicit release operations

- A release is an exceptional, owner-authorized operation; updating this policy, merging an ordinary pull request, or passing checks does not authorize a tag, GitHub Release, artifact, or publication.
- Only a protected GitHub `release` environment with an explicit owner approval may authorize one exact release target. The target must be a full 40-character commit SHA reachable from protected `main`, with required checks complete and a clean worktree; never release from a floating ref, short SHA, dirty source, fork, or unreviewed branch.
- Release tags are exactly `v<major>.<minor>.<patch>-rc.<positive-integer>` or `v<major>.<minor>.<patch>`. Each new release line begins with an RC (the first public candidate is `v0.1.0-rc.1`), later RC numbers increase consecutively, and the matching stable tag may follow only an approved RC.
- Tags are immutable: reject tag reuse, overwrite, movement, deletion-and-recreation, and force update. Do not create a GitHub Release, release artifact, package publication, or other release output outside the explicitly approved operation.
- Release notes must record the tag, full source SHA, installed skill digest, state schema version, protocol version, review-contract version, policy version, supported Python/OS/Codex contract, Apache-2.0 license, and forward-test evidence. These compatibility versions are not package release versions.

## Source layout

- Keep `skills/roundlet` as the canonical skill source root.
- Keep deterministic Python implementation dependency-free in `skills/roundlet/scripts/orchestration_state.py`.
- Keep detailed operator and role documentation one level below `skills/roundlet/references/`; keep `skills/roundlet/SKILL.md` concise and imperative.
- Do not add a README, changelog, installation guide, quick reference, transcript archive, duplicate operator guide, unnecessary icon, or empty optional directory.
- Do not commit credentials, `.env` files, runtime state, test caches, or generated build artifacts.

## Verification

- Run `python3 -m unittest discover -s tests -v`.
- Run the current system `skill-creator/scripts/quick_validate.py` against `skills/roundlet`.
- Validate `skills/roundlet/agents/openai.yaml`, the rules template, prohibited runtime dependencies, bounded artifacts, and the guarded CLI smoke paths.
- Forward-test material workflow revisions with fresh, minimally primed threads when it can be done without live mutations.

## Version control

- Follow [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/) using `<type>(<scope>): <description>` and explain why in the body when useful.
- Keep commits atomic and focused.
- Follow [Conventional Branch](https://conventionalbranch.org/) and use descriptive lowercase branch names. Codex-authored branches use the repository's `codex/` convention.
- Update `.gitignore` whenever new local runtime, test, build, or dependency artifacts are introduced.
