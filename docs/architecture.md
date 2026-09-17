# Repository and runtime boundaries

```text
README.md / README.fr.md        Product overview and entry points
skills/project-manager/        Complete installable skill
  SKILL.md                     Agent routing and essential invariants
  scripts/                     Deterministic project operations and audits
  references/                  Conditional workflow guidance
  templates/                   Bootstrap assets and setup example
  docs/                        Data models, limits and operational procedures
  VERSION / .bumpversion.cfg   Single version source
tests/                         Synthetic behavioral and integrity tests
tools/                         Validation, demonstration and clean export
examples/                      Reproducible demo and agent exercises
docs/                          User, contributor and distribution documentation
.github/                       CI and contribution forms
```

The runtime is self-contained. Installing it does not install contributor tests,
release tools or website assets. Supporting references are read only when relevant;
the agent does not need to load the whole directory into its context.

There are three different responsibilities: the coordinating agent plans and
reviews work; the scripts enforce documented record invariants; the configured
hosting and agent runtimes provide authentication, permissions and execution.
Actor labels in JSON are not an authorization service. A delegation plan is not
an OS sandbox or a worker invocation.

Projects contain their own engineering state in Git. The skill is a tool source,
not the canonical location of project records. Runtime upgrades do not rewrite
project history or silently update generated project-local tool copies.

Public distribution combines a reviewed runtime and repository facade, scanning
each with its own allowlist. Release ZIPs include a hash manifest. Private
development history, machine configuration and project data are never mirrored.
See [publication](PUBLICATION.md) for the exact export boundary.
