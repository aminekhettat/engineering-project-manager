# Project Manager 1.4.0

This release makes the skill easier to discover, install, evaluate and contribute
to while preserving the engineering record schemas and deterministic release rules.

- Install only `skills/project-manager/`; tests, examples and publication tools
  now live at repository root in the full source checkout.
- English and French quickstarts, clear compatibility guidance and a static
  project overview explain setup, delegation and release evidence.
- An offline demonstration executes a failing toy check, fixes it and moves the
  complete release gate from BLOCKED to PASS using real project commands.
- CI validates three Python versions, an actual skills CLI installation and
  reproducible MIT runtime archives with SHA-256 inventories.
- ClawHub receives a separately generated MIT-0 runtime; GitHub remains MIT.

Upgrade: replace the installed runtime from the ZIP after backing up any local
changes. If installing from source, use `skills/project-manager/`, not the
repository root. Restart the agent session. Existing projects and generated tool
copies are not migrated automatically.

Requires Linux, Python 3.10+ and Git. The optional skills@1.6.0 installer requires
Node.js 22.20+. Other agent hosts and native Windows runtime are not validated.
SPICE-like, not certified: a passing gate is not conformity, certification or a
capability level. Read the documented scope, security guidance and known limits.
