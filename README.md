# Project Manager

An OpenClaw skill for managing engineering projects with requirements,
traceability, controlled changes, configuration baselines, verification
evidence, risks, problems, milestones and external obligations. It supports software, systems, hardware, machine learning, mechanical
and cybersecurity work, with project-specific tailoring.

**SPICE-like, not certified.** This independent project is not certified,
endorsed or approved by VDA QMC, iNTACS or ISO. It does not certify its users or
their projects. A passing check is a result of this tool's documented rules,
not a formal assessment, capability level or guarantee of compliance. See
[scope and limitations](docs/SPICE-SCOPE.md).

## Install

Use Python 3.10 or newer and Git on Linux (including Raspberry Pi OS).
The registry writers use POSIX file locks. Native Windows is not currently
supported for the full workflow; use a Linux environment. No Python runtime
packages are required. GitHub bootstrap additionally uses an authenticated `gh`;
GitLab requires an authenticated `glab`, including when Git uses SSH. SSH transport
also requires a working SSH client and identity. A fresh bootstrap creates a new
remote repository; it does not adopt an existing remote automatically.

Download a reviewed release, verify its published SHA-256, and extract its
`project-manager` directory under your OpenClaw workspace's `skills/`
directory, or your configured managed skills directory. Preserve the folder
name and its complete contents. Start a fresh agent session and ask it to
use `project-manager`. Installation does not configure accounts or grant access.

For a Git checkout, clone this dedicated repository into
`<OPENCLAW_WORKSPACE>/skills/project-manager` and check out a reviewed release
tag, such as `v1.3.0`. `SKILL.md` is at the repository root; the folder must be
named `project-manager`. Avoid nesting the repository inside another
`project-manager` directory. The skill follows the Agent Skills directory
format and OpenClaw's supported frontmatter extension.

The code and original documentation are distributed under the [MIT license](LICENSE).
External standards and project inputs retain their own terms.

## Start a project

Ask your agent:

> Use project-manager to initialize a new engineering project. First discover
> whether it already exists, then ask me the missing questions about scope,
> disciplines, repository, infrastructure, team, delegation and delivery.
> Show the resolved setup before creating infrastructure.

The agent follows [project initialization](references/project-initialization.md).
An accessible terminal questionnaire and a validated JSON configuration are
also available through `python3 scripts/project_setup.py --help`.

For an existing project, ask for a read-only status and migration assessment.
Do not bootstrap over an unrelated repository or replace project records.

## Capabilities and limits

- Requirements retain stable identities and exact revision references.
- Task, change, baseline and verification records have deterministic CLIs.
- Released requirement changes create a new revision; frozen snapshots retain
  their content and integrity hash.
- Verification attaches to an exact requirement revision and preserves
  execution and artifact evidence.
- Separate versioned registries manage risks, verified problem closure,
  evidence-backed milestones, reviewed source versions and obligation coverage.
  High unresolved risks, blocking problems, required unfinished milestones and
  unresolved external obligations prevent release.
- New projects initialize these registries. Existing projects first receive a
  read-only assessment and opt in explicitly; their old documents are preserved.
- Audits and the release gate expose errors; they do not replace engineering
  review, real tests, safety analysis or acceptance by the responsible people.
- Delegation uses bounded assignments, isolated work and reviewed returns.
  The coordinating agent remains accountable; worker labels are configurable.
- Public exports contain only the reviewed skill snapshot, without the private
  development repository or its history.

The [capability roadmap](docs/INDUSTRIALIZATION-ROADMAP.md) distinguishes working
automation from document workflows and future designs. A generated template is
not proof that a process was performed.

## Useful commands

Run these from the installed skill directory, replacing `PROJECT` with the
project directory:

```bash
python3 scripts/project_setup.py --help
python3 scripts/migration_assess.py PROJECT --json
python3 scripts/project_report.py PROJECT --json
python3 scripts/management_audit.py PROJECT --release
python3 scripts/project_state.py ready PROJECT
python3 scripts/delegation_plan.py --help
python3 scripts/release_check.py PROJECT
python3 scripts/run_checks.py
```

The migration assessment and report do not modify the project. Read
`SKILL.md` for the workflow and follow its links only as needed.
See [management extensions](docs/MANAGEMENT-EXTENSIONS.md) for opt-in,
the individual commands, recovery and the order of operations before a freeze.

## Contribute and distribute

Use an isolated branch, preserve established record semantics, add tests for
observable behavior and run the complete checks. See [contribution guidance](CONTRIBUTING.md),
[security reporting](SECURITY.md) and [publication procedure](docs/PUBLICATION.md).
Never submit real project data, credentials, personal configuration or private
host details in an issue, patch or release.
