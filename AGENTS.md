# Roundlet repository policy

## Scope and authority

- Treat this repository as the sole source, test, review, and maintenance history for Roundlet.
- Keep Roundlet operationally and artifact-wise independent from any other orchestration runtime.
- Never infer authority over a target repository from changes or approvals in this source repository.
- Develop setup and maintenance changes in an isolated worktree and merge them only through a reviewed pull request with explicit owner approval.
- Do not use a target-repository Roundlet activation to modify, install, approve, merge, release, or activate Roundlet itself.

## GitHub mutations

- Before any mutation, verify the exact repository, issue or pull request, expected head SHA, branch, activation, and authorization.
- Use the Codex-native GitHub connector for GitHub issue, comment, pull request, ready, merge, close, and remote-branch operations.
- Keep public comments curated. Never publish raw prompts, transcripts, hidden reasoning, credentials, private paths, or unbounded state.
- Never force-push, reset, rebase, bypass branch protection, delete issues, publish releases, create tags, or delete unique work.

## Implementation

- Keep the repository root as the canonical skill root.
- Keep deterministic runtime logic dependency-free in `scripts/orchestration_state.py`.
- Keep detailed operator and role contracts one level below `references/`; keep `SKILL.md` concise and imperative.
- Keep runtime state under `.codex-log/roundlet/` and out of version control.
- Do not add a README, changelog, installation guide, quick reference, transcript archive, duplicate operator guide, unnecessary icon, or empty optional directory.
- Do not introduce provider credentials, `.env` files, cross-repository selectors, organization scans, or alternate authority surfaces.

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
