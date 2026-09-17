# Run a release gate from blocked to ready

This **synthetic, offline demonstration** creates a small project, reproduces a
real defect in a toy program, repairs it and runs the actual Project Manager
release gate. It demonstrates deterministic controls. It is not an LLM benchmark,
a SPICE assessment, a certification or verification of a real product.

## Run it

Use Python 3.10+ and Git on Linux, or inside Windows WSL. No third-party
Python packages, account, credentials or network connection are needed. Run from
the full public repository, not an installed runtime-only skill:

```sh
python3 tools/demo_project.py --output /tmp/pm-demo
```

The destination **must not exist**, and its parent must exist. Existing files,
directories and symlinks are refused. The script creates only the specified
destination and its own local Git repository. If a step fails, it stops, keeps
the partial demonstration and its logs, and exits nonzero. Use a different new
destination for another run.

For contributors working in the private repository layout:

```sh
python3 publication/project-manager/tools/demo_project.py \
  --skill-root skills/project-manager \
  --output /tmp/pm-demo
```

The current runtime uses POSIX file locking; native Windows Python is rejected
before the destination is created. WSL runs the real locking implementation.

## What actually happens

| Step | Observable result |
| --- | --- |
| Plan | A P1 task, a high risk (15/25), a blocking problem and a release-required milestone are created through the real CLIs. |
| Reproduce | Executed Python checks show that the toy record checker accepts empty and whitespace-only input. Two checks fail; the nonempty-input check passes. |
| Block | `release_check.py` fails. Its output identifies the task, risk, problem and milestone. Verification evidence and a frozen candidate baseline are also pending. |
| Resolve | The guard is implemented and all three checks execute successfully. Their output and implementation/test hashes form the synthetic verification report. The task is accepted, the risk is mitigated to 2/25, the problem is closed and the milestone is achieved. |
| Record | A candidate baseline is created and frozen. `EV-001` records the executed checks as PASS against the exact requirement revision and `BL-001`. |
| Check again | The complete release gate passes against the clean local commit. The candidate stays FROZEN; nothing is published, deployed or marked RELEASED. |

All lifecycle transitions use the runtime commands. The initial engineering
documents reuse `tests/release_fixture_test.py`; they are deliberately small
teaching artifacts. The demonstration does not replace project onboarding or
establish that these short documents are sufficient for a real project.

Git's `origin` is a reserved `example.invalid` placeholder required by the
repository audit. No fetch, push, remote creation on a server or other network
operation occurs. `CI_COMMIT_SHA` is set to local HEAD only for the gate process;
this simulates the commit comparison and does not claim that hosted CI ran.
The repository uses synthetic local author details and disables commit hooks
and signing. Named actors/reviewers simulate roles, not authenticated people or
independent human review.

## Inspect the results

The console output is short; [expected-output.txt](expected-output.txt) contains
output captured from a successful execution. Paths, hashes and timestamps stay
in the generated project rather than this portable transcript.

Inside your destination:

| File | Purpose |
| --- | --- |
| `00-project/DEMO-PLAN.md` | Scenario and links between the task, risk, problem and milestone. |
| `.demo/summary.json` | Compact before/after results suitable for a local visual or report. |
| `.demo/commands.jsonl` | Executed command arguments, exit codes and associated log files. |
| `.demo/check-before.txt`, `.demo/check-after.txt` | Actual toy check outputs. |
| `.demo/release-blocked.txt`, `.demo/release-pass.txt` | Full outputs from the two real release-gate executions. |
| `05-verification/software/SWE-VERIFICATION-REPORT.md` | Synthetic report with executed output and content hashes, used by the records. |
| `09-risks/RISKS.md`, `07-quality/PROBLEMS.md`, `00-project/management/MILESTONES.md` | Readable views of the audited lifecycle records. |

The `.demo/` diagnostics are ignored by Git so that recording the gate result
does not dirty the candidate. The verification artifact itself is tracked and
sealed by the management/evidence engines. The real command logs retain local
paths; review them before sharing outside your machine.

Sources and the compliance matrix are initialized but empty in this focused
example. External-source applicability, coverage, delegation quality and agent
decision quality are not evaluated. For proposed agent exercises, see
[agent-evaluation.md](../agent-evaluation.md).
