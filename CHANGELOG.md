# Changelog

## 1.4.1 - 2026-09-17

Align the public and development repository names with the ClawHub slug
`engineering-project-manager`. Update installation, documentation and runtime
homepage links; retain `project-manager` as the installed skill identity.
Clarify the reserved ClawHub namespace and ZIP compression reproducibility.
No project record schemas or operational rules change.

## 1.4.0 - 2026-09-17

Separate the installable runtime (`skills/project-manager`) from contributor
tests, publication tools, examples and repository documentation. Add English and
French quickstarts, a reproducible offline FAIL-to-PASS release demonstration,
compatibility guidance, a static project page and distribution checks. Preserve
the existing project registry schemas and release rules. Add separately licensed
MIT-0 export for ClawHub while keeping GitHub source and releases under MIT.

## 1.3.1 - 2026-09-16

Fixed pre-existing Markdown rendering expressions in baseline and verification
views that required Python 3.12 syntax despite the documented 3.10 minimum.
Rendering content and registry semantics are unchanged. The public CI matrix
exercises the actual Python 3.10, 3.12 and 3.13 runtimes to detect compatibility
regressions that syntax checks on a newer interpreter cannot establish.

## 1.3.0 - 2026-09-16

Added five approved, separate authoritative JSON registries: risks, problems,
milestones, external source intake and obligation coverage. Each uses stable
IDs, atomic locked writes, replayable history and generated Markdown views.
Added lifecycle, proof, reference and release checks, explicit opt-in for existing
projects, automatic initialization for new projects, migration/report integration,
and copied tooling/CI for generated projects. Existing requirement, task, change,
baseline and verification schemas are preserved. External intake documents are
excluded from engineering requirement discovery. Added behavioral, security,
concurrency, recovery and real release integration tests. Adopted the MIT license
and prepared a dedicated public distribution with pinned CI actions and Python
3.10, 3.12 and 3.13 validation. See the release notes for practical limits.

## 1.2.0 - 2026-09-16

Added guided project/infrastructure initialization, reviewed configuration,
bounded delegation contracts, consolidated reporting, read-only migration
assessment and portable GitHub/GitLab setup. Strengthened requirement, task,
traceability, baseline and verification integrity. Added privacy scanning,
history-free deterministic publication exports, SHA-256 inventories and explicit
SPICE-inspired/noncertified positioning. Existing canonical models are retained.

## 1.1.3 - 2026-09-05

Added the approved authoritative verification and test evidence model: a
unified minimal JSON registry with generated Markdown views, exact
requirement-revision attachment, prescribed-strategy consistency, locked and
atomic writes, artifact SHA-256 integrity, execution Git-commit proof,
revision-aware coverage, supersession history, and a non-destructive `assess`
report for existing projects. The release gate now invokes the evidence audit
and tolerates committed evidence records after a baseline freeze; bootstrap
initializes evidence management for new projects; legacy projects without the
marker are skipped. Added 42 behavior, negative, tamper and
release-propagation tests, and extended the release fixture to pass the gate
with evidence recorded on the frozen candidate.

## 1.1.2 - 2026-09-05

Corrected V1.1 integrity and completed the first industrialization phase:
restored legacy French normative wording compatibility; aligned generated
requirement templates and domain audits with revision-aware IDs; removed
duplicate linter implementations; enforced a coherent FROZEN candidate and
full release-gate flow; preserved historical baseline validity; rejected
non-RELEASED revision/freeze sources; separated Changed Items from explicit
manual impacts; and hardened the task engine with validation, atomic writes,
exclusive locking, acceptance/WIP gates, cancellation, and concurrency tests.
Added a structured capability roadmap and expanded behavioral, negative,
generated-project, compatibility, and release tests.

## 1.1.1 - 2026-09-05

Stabilized AgentSkill discovery and packaging: replaced the migration-only
skill description with an operational contract, moved the detailed handbook to
references, removed tracked legacy/broken scripts, added deterministic package
and full release-fixture checks, and added GitLab CI. Fixed legacy Markdown
requirement heading detection and blank Current Baseline parsing.

## 1.1.0 - 2026-08-31

Added controlled Change Request workflow and assignment history, recursive
revision-aware impact analysis, safe requirement revision creation, immutable
configuration baselines, configuration audit, release-gate enforcement,
bootstrap integration, migration commands, and deterministic integration
tests. English is canonical throughout active Project Manager assets.

## 1.0.0 - 2026-08-29

First stabilized Project Manager baseline.

Domains:
SYS, SWE, HWE, MLE, CYBER and MECH.

Includes robust bootstrap/resume, GitHub and GitLab support,
domain work products, traceability, quality audits,
strict release gates, CI integration and self-check.
