# Project Manager 1.2.0

This release improves project setup, delegation guidance, operational visibility,
integrity and public packaging while retaining existing requirement, task, CR,
baseline and verification schemas.

## Changes

- Guided initialization collects scope, disciplines, owners, constraints,
  infrastructure, repository policy, CI and worker configuration. A resolved plan
  is reviewed before bootstrap. Resuming preserves existing project records.
- Delegation contracts bound work by task, base revision, outputs, write paths,
  dependencies, concurrency, retries and acceptance criteria. The coordinator
  verifies returned evidence and accepts results.
- Consolidated read-only reporting and migration assessment help agents start
  from the actual project state.
- Integrity checks reject malformed requirement blocks, duplicated metadata,
  traceability cycles, invalid task dependencies, missing evidence artifacts,
  invalid evidence supersession and deletion of enablement markers to bypass audits.
- Open changes on a requirement also block a candidate containing its newer
  revision. Baselines cannot supersede themselves.
- Portable documentation and workflows support a history-free public release,
  with privacy checks, reproducible ZIP export and a file hash manifest.
- SPICE-inspired scope, lack of certification and the limits of automated checks
  are stated explicitly. Git remains the canonical engineering record.

## Compatibility and limits

Linux, Python 3.10+ and Git are required for the complete runtime. Existing
bootstrap arguments and accepted legacy requirements remain supported. Existing
generated projects are not silently rewritten or upgraded. Model changes for
risks, problems, milestones, intake and compliance remain pending design decisions;
see the [roadmap](INDUSTRIALIZATION-ROADMAP.md).

The setup review digest detects plan changes; it is not identity authentication.
Delegation path checks are planning controls, not a security sandbox. No tool
result constitutes certification, a formal assessment, guaranteed compliance,
or a guarantee of freedom from liability.
