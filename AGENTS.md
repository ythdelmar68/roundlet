# Roundlet source repository policy

## Repository work

- Treat this repository as the source, review, and maintenance history for Roundlet.
- Preserve unrelated changes and worktrees. Develop changes in an isolated worktree and merge them only through a reviewed pull request with explicit owner approval.
- Never force-push, reset, rebase, bypass branch protection, delete unique work, publish a release, or create a tag during ordinary repository work.

## Source layout

- Keep `skills/roundlet` as the canonical skill source root.
- Keep exactly one human-facing `README.md` at the repository root for discovery, architecture, installation, and operating guidance. Do not treat it as part of the installed skill.
- Keep Roundlet prompt-native. Do not add an executable orchestration runtime, database, package, runtime migration, runtime metrics, runtime compatibility layer, or platform matrix.
- Keep fundamental safety and orchestration principles explicit in `skills/roundlet/SKILL.md`.
- Keep detailed operator and role documentation one level below `skills/roundlet/references/`.
- Whenever any file under `skills/roundlet` changes, review and synchronize every affected file under `skills/roundlet/references/` and the root `README.md` in the same pull request. Update affected documentation, or record in the pull request why a reviewed document needs no textual change.
- Do not add another README, a changelog, a separate installation guide, a quick reference, a transcript archive, a duplicate operator guide, an unnecessary icon, an empty optional directory, a CI workflow, a release artifact, or an automated test suite.
- Do not commit credentials, `.env` files, target-repository runtime state, caches, or generated artifacts.

## Verification

- Run the current system `skill-creator/scripts/quick_validate.py` against `skills/roundlet`.
- Validate the JSON and YAML configuration files, reference links, source layout, prohibited executable/runtime artifacts, and `git diff --check`.
- Treat forward testing as separate work under its dedicated issue. Do not mutate a target repository without explicit owner authorization.

## Version control

- Follow Conventional Commits 1.0.0 using `<type>(<scope>): <description>` and explain why in the body when useful.
- Keep commits atomic and focused.
- Use descriptive lowercase Conventional Branch names. Codex-authored branches use the repository's `codex/` convention.
