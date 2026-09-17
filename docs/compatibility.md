# Compatibility and support

| Surface | Status and practical boundary |
| --- | --- |
| OpenClaw on Linux | Primary integration target; skill discovery and the deterministic runtime are validated. Delegation still depends on available agent tools and permissions. |
| Python 3.10, 3.12, 3.13 | Behavioral checks run in the public CI matrix. Python packages are not needed at runtime. |
| Raspberry Pi OS / Linux | Supported runtime family. Registry writers require POSIX file locks. |
| Windows | Run the workflow inside Linux/WSL. Native Windows runtime is unsupported. |
| macOS | Not part of the release validation matrix; no support claim from POSIX similarity alone. |
| Agent Skills directory format | One complete `skills/project-manager` directory with an entrypoint and supporting resources. Format discovery does not prove host behavior. |
| Other agent products | Can inspect or install the directory if their loader supports the format; end-to-end use and delegation have not been validated here. |
| GitHub/GitLab bootstrap | Uses authenticated `gh`/`glab`; optional SSH remotes need working SSH. No credential provisioning is performed. |
| Existing project migration | Read-only assessment first; management registries are explicitly enabled. Existing data models and history are preserved. |
| ClawHub | Separate MIT-0 packaging. A registry listing is available only after publication succeeds; the GitHub repository alone does not establish it. |

CI tests deterministic software behavior and synthetic records. It does not
measure model quality, independently verify externally reported tests or establish
SPICE conformity. The [agent exercises](../examples/agent-evaluation.md) are a
starting point for host-specific evaluation, with no claimed model benchmark score.

For supported changes, use the current reviewed release and preserve an earlier
archive for rollback. Report the release version, execution platform, failing
command and sanitized reproduction. The project does not promise an SLA.

Format references: [Agent Skills](https://agentskills.io/specification),
[OpenClaw skills](https://docs.openclaw.ai/tools/skills),
[skills installer](https://github.com/vercel-labs/skills).
