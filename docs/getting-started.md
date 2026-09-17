# Your first project

## 1. Check the environment

Use Linux, Python 3.10+ and Git. Raspberry Pi OS and Linux under WSL are suitable
execution environments. There are no third-party Python runtime packages.
`gh` or `glab` authentication is needed only for the selected repository bootstrap
provider. SSH transport also needs a configured SSH client and identity.
Installation alone grants no account, repository or infrastructure permissions.

## 2. Install the complete skill

From your OpenClaw workspace, use the [skills CLI](https://github.com/vercel-labs/skills):

```sh
npx skills@1.6.0 add aminekhettat/engineering-project-manager --skill project-manager -a openclaw --copy
```

The installer needs Node.js 22.20+ / npm and network access. Inspect its proposed path;
avoid the global option unless you intend a shared installation. The CLI may send
anonymous installation telemetry; set `DISABLE_TELEMETRY=1` to disable it.

For an archive installation, download `project-manager-VERSION.zip` and its
`.sha256` companion from the [release page](https://github.com/aminekhettat/engineering-project-manager/releases/latest).
Run `sha256sum -c project-manager-VERSION.zip.sha256` in the download directory.
Extract its complete `project-manager/` folder into `<OPENCLAW_WORKSPACE>/skills/`
or the managed skills directory you configured. Start a fresh agent session.
Use `openclaw skills info project-manager` to inspect discovery and requirements.

From a source checkout, copy only `skills/project-manager/` to the destination.
The repository root is the project website and contributor workspace; it is not
the installable skill. Templates and scripts must accompany `SKILL.md`.

## 3. Give the agent the project intent

> Use project-manager for this engineering project. First look for an existing
> canonical project. Ask missing questions in small groups, reuse known answers
> and show the resolved setup before creating infrastructure.

Expect questions about objective and scope, acceptance criteria, disciplines,
stakeholders and ownership, constraints, repository and branch, CI and execution
environment, credentials by reference, team capabilities and delegation, delivery
milestones, external obligations and release expectations. Never paste secrets.

The agent uses [initialization guidance](../skills/project-manager/references/project-initialization.md).
An existing project receives an assessment before any explicit migration. A fresh
bootstrap creates a new remote; it does not silently adopt a populated remote.

## 4. Inspect state and evidence

From the installed skill directory, pass the absolute project directory as `PROJECT`:

```sh
python3 scripts/migration_assess.py PROJECT --json
python3 scripts/project_report.py PROJECT --json
python3 scripts/project_state.py ready PROJECT
python3 scripts/release_check.py PROJECT
```

The first two commands are read-only. A newly initialized project is not release
ready: unfinished requirements, evidence, risks or milestones are expected blockers.

## Update or troubleshoot

Back up any local customization and replace the installed runtime with a reviewed
release. Restart the agent session, then check discovery. Updating a skill does
not migrate existing project records or replace the tool copies already generated
inside projects; assess and approve those changes separately.

If discovery fails, inspect the destination and `SKILL.md` name. If execution fails,
check Python/Git availability and [platform support](compatibility.md). If the gate
fails, inspect its findings and the exact candidate commit; do not weaken the
checks or invent evidence. Use synthetic data when [reporting a bug](../CONTRIBUTING.md).
