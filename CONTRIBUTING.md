# Contributing

Start with a small, reproducible issue using synthetic project data. Discuss
changes to requirement identity, revision semantics, lifecycle states, allocation,
baseline integrity or release decisions before implementation.

1. Create a branch from the reviewed development base.
2. Reproduce the behavior in a temporary synthetic project.
3. Change the runtime in `skills/project-manager/`; add meaningful behavioral
   tests in `tests/` and update relevant documentation.
4. On Linux with Python 3.10+ and Git, run `python3 -B tools/run_checks.py`.
5. Run the [offline demonstration](examples/release-gate/README.md) when changing
   project lifecycle or release behavior. Review `git diff --check` and the diff.
6. Stage intended files, then run `python3 -B tools/publication_check.py . --profile repository`.

In a development workspace that stores this public facade under `publication/`,
use `python3 -B publication/project-manager/tools/run_checks.py --skill-root skills/project-manager`.

Use fictitious owners and reserved example domains. Never submit credentials,
private infrastructure, real project evidence or local privacy denylists.
Report vulnerabilities through [private security reporting](https://github.com/aminekhettat/openclaw-project-manager/security/advisories/new).
Do not copy proprietary standards into this repository.

## Versions and releases

`skills/project-manager/VERSION` and `.bumpversion.cfg` are the single version
source. Run `bump2version` from that directory to update them together, then
update `CHANGELOG.md`. Do not rewrite published tags. Release manifests belong
in generated archives, not editable source. See [publication](docs/PUBLICATION.md).

The public GitLab workflow expects a Linux container runner. Private runner tags
belong in the development environment. Never hide unsupported-platform failures
by replacing production file locks with no-ops.
