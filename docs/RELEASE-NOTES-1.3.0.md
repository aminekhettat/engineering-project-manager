# Project Manager 1.3.0

This release completes the approved management extensions and prepares the
skill for independent, public reuse under the MIT license. It retains the
established requirement, task, change, baseline and verification models.

## Working additions

- Risks: probability/impact scoring, owners, mitigation evidence, residual risk,
  explicitly reasoned acceptance with a review date, closure and reopening.
- Problems: triage, investigation, disposition, resolution evidence, recorded
  verification, verified closure, duplicate validation and release blocking.
- Milestones: due dates, criteria, task links, dependency checks, hashed evidence,
  reviewed achievement and explicit waivers for required cancelled milestones.
- Intake: source provenance, version, rights/confidentiality declarations,
  original artifact hashes, reviewed obligation inventories and supersession.
- Obligation coverage: reasoned applicability/exclusions, exact requirement
  revision and evidence links, missing-obligation detection and PASS coverage.
- Integration: new-project initialization, explicit existing-project opt-in,
  read-only migration/status reporting, generated project tooling and CI, and
  management checks in the real release gate.
- Integrity: serialized atomic single-record writes, replayable history,
  no identifier reuse, confined paths, self-referential-proof rejection,
  deleted-registry detection through available Git history and recovery guidance.
- Distribution: MIT license, standalone skill at the repository root,
  privacy-scanned exports, deterministic release ZIP and SHA-256 manifest,
  pinned GitHub Actions and a three-version Python validation matrix.

## Upgrade

Install the complete skill directory. Existing projects are not automatically
rewritten. Run `migration_assess.py PROJECT --json`, review applicability and
initialize the approved extensions with `management_init.py PROJECT --actor ROLE`.
Existing legacy documents remain in place; creating an empty registry does not
migrate their records. Use the respective commands to enter reviewed records.

Generated projects preserve their copied tools on resume. Upgrade those tools
as an explicit, reviewed change before relying on the new management gate.
Finish source review, mappings, risk/problem dispositions and required milestone
decisions before freezing a candidate. Record the existing verification results
through the established evidence workflow after the freeze.

## Validation and limits

`python3 -B scripts/run_checks.py` discovers the behavioral suites and runs
syntax, package and self-check validation. Tests cover state transitions,
rejected writes, tampering, concurrent updates, legacy compatibility, bootstrap
recovery and a complete managed project through the actual release command.
Publication scanning is a separate check on the final snapshot.

The full runtime requires Linux, Python 3.10+ and Git. Labels are not authenticated
identities; ledger hashes are not digital signatures. No transaction spans all
registries. Git history is inspected only where available. A freshly initialized
empty registry is not evidence of complete real-world risk or source discovery.

The skill is SPICE-inspired and **not certified, endorsed or a conformity
assessment**. Covered obligations are operational traceability results, not
proof of legal, regulatory or contractual compliance. See [scope](SPICE-SCOPE.md)
and the [capability inventory](INDUSTRIALIZATION-ROADMAP.md) for the remaining
document workflows and limits.
