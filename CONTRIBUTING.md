# Contributing

Discuss changes to requirement identity, revision semantics, lifecycle states,
allocation, baseline integrity or release decisions before implementation.
Keep bug fixes and backward-compatible improvements focused and testable.

1. Create a branch or isolated worktree from the reviewed development base.
2. Reproduce the behavior in a synthetic temporary project.
3. Make a focused change and document user-visible behavior.
4. Run `python3 scripts/run_checks.py` on Linux with Python 3.10+ and Git.
5. Review `git diff --check`, tests and the complete staged diff.
6. Scan the staged skill with `python3 -B scripts/publication_check.py .` before sharing.

Use fictitious owners, repositories and `.example` domains in fixtures.
Keep private infrastructure details, project data and local denylist files
outside this repository. Do not copy formal standards into contributions.

Development may use GitLab or GitHub. CI runner selection belongs to the
maintainer's environment; it must not be hardcoded to one person's machines in
the public distribution. Version changes use `.bumpversion.cfg` and `VERSION`;
the package check detects drift. Preserve old release tags.
Maintainers can use `bump2version` with this configuration to update both files
in one operation. Keep the generated `PUBLICATION-MANIFEST.json` in release
packages only; do not commit a stale release manifest into the editable source.

The full skill runtime targets Linux. Test failures on unsupported native
platforms must not be hidden by replacing production file locks with no-ops.
