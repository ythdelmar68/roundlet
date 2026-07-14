# Roundlet source repository policy

## Repository work

- Treat this repository as the source, test, review, and maintenance history for Roundlet.
- Preserve unrelated changes and worktrees. Develop changes in an isolated worktree and merge them only through a reviewed pull request with explicit owner approval.
- Never force-push, reset, rebase, bypass branch protection, publish releases, create tags, or delete unique work while performing ordinary repository work.

## Source layout

- Keep the repository root as the canonical skill source root.
- Keep deterministic Python implementation dependency-free in `scripts/orchestration_state.py`.
- Keep detailed operator and role documentation one level below `references/`; keep `SKILL.md` concise and imperative.
- Do not add a README, changelog, installation guide, quick reference, transcript archive, duplicate operator guide, unnecessary icon, or empty optional directory.
- Do not commit credentials, `.env` files, runtime state, test caches, or generated build artifacts.

## Verification

- Run `python3 -m unittest discover -s tests -v`.
- Run the current system `skill-creator/scripts/quick_validate.py` against the repository root.
- Validate `agents/openai.yaml`, the rules template, prohibited runtime dependencies, bounded artifacts, and the guarded CLI smoke paths.
- Forward-test material workflow revisions with fresh, minimally primed threads when it can be done without live mutations.

## Version control

- Follow [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/) using `<type>(<scope>): <description>` and explain why in the body when useful.
- Keep commits atomic and focused.
- Follow [Conventional Branch](https://conventionalbranch.org/) and use descriptive lowercase branch names. Codex-authored branches use the repository's `codex/` convention.
- Update `.gitignore` whenever new local runtime, test, build, or dependency artifacts are introduced.
