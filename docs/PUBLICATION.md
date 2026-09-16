# Preparing a public distribution

The development repository and its history are private working material. Publish
an independently reviewed, history-free export of the skill. Do not mirror the
development repository, push its branches to a public remote, or upload a parent
workspace. A clean current tree does not make old commits or Git author metadata
safe to publish.

## What the tools check

`scripts/publication_check.py` reads only tracked files below the selected skill
by default. It checks current working-tree bytes, so commit and test the final
candidate before release. Add intended new distributable files to the Git index
before this check; untracked files are deliberately absent from the default export.

The check rejects recognizable credential formats, private keys, credential-bearing
URLs, suspicious credential assignments, personal email addresses, personal home
paths, private network addresses, private hostnames, and local denylist matches.
Email examples must use reserved fictional domains such as `example.com`,
`example.invalid` or a domain ending in `.example`. Test dangerous values by
assembling fictional string fragments; never use a working credential as a fixture.

Only approved root files and the `scripts`, `docs`, `references`, `templates`,
`examples`, `tests` and `.github` directories are distributable. The scanner rejects
runtime/private directories, environment files, backups, credentials, binary or
non-UTF-8 data, control characters, symlinks, Windows junctions, submodules,
unmerged index entries and files over 2 MiB. The full snapshot is limited to
10,000 files and 40 MiB. The current distribution is intentionally text only;
support for another asset type requires a reviewed change to this policy.

Failures print relative paths, categories and line numbers, never matched content.
Local denylist terms are redacted from printed paths. Output contains no absolute
source paths, credentials, remote URLs, Git authors or Git email addresses.

These checks reduce accidental disclosure; they do not prove the absence of all
secrets or personal information. Contextual names, unknown credential formats,
encoded data, confidential business text, copyright issues and proprietary
requirements also need human review. No automated process guarantees a particular
legal outcome or removal of liability.

## Local denylist

Keep a UTF-8 file **outside the distributable skill** with one private term per
line: actual organization or customer names, personal names, machine names,
internal domains, account identifiers and project-specific tokens. Matching is
case-insensitive literal substring matching. Blank lines and lines starting with
`#` are ignored. Entries need at least three characters. Choose sufficiently
specific terms to avoid broad false positives. The file is read locally and is
never copied into the export or recorded in its manifest.

Do not commit this file to a public repository. Do not add private names to the
generic scanner or public test fixtures. When a finding occurs, inspect it locally,
remove unnecessary private context or replace an example manually, then rerun the
check. Never run a blind global replacement over project evidence or source code.

## Review and export

From a development checkout containing `skills/project-manager`, with a local
denylist stored outside that checkout:

```sh
python -B skills/project-manager/scripts/publication_tests.py
python -B skills/project-manager/scripts/publication_check.py skills/project-manager --denylist ../publication-denylist.txt
python -B skills/project-manager/scripts/publication_check.py skills/project-manager --denylist ../publication-denylist.txt --history
```

The optional history audit examines reachable commits, their metadata and unique
skill blobs, reporting categories and counts. It does not inspect reflogs,
unreachable objects, external LFS content, server backups or clones. Historical
findings block a history-inclusive check. They do not force exporting that history:
the exporter checks only the current snapshot and never copies `.git`. If a real
credential was ever exposed, remove it from the candidate and have its owner revoke
or rotate it through the appropriate private channel.

Review the files, test results, `VERSION`, license, security instructions and SPICE
positioning. The package must state that it is an independent SPICE-inspired tool,
not a certification, conformity assessment, or assurance of project compliance.
No claim of affiliation or approval by a standards organization should be implied.
Only distribute a license chosen by the rights holder. Export requires a nonempty
`LICENSE` or `LICENSE.md`; the scanner alone can be used while that choice is pending.

Create the destination parent first. The destination directory and optional ZIP
must not exist and must be outside the source skill:

```sh
mkdir -p release
python -B skills/project-manager/scripts/export_public_skill.py skills/project-manager --denylist ../publication-denylist.txt --output release/project-manager --archive release/project-manager.zip
python -B release/project-manager/scripts/publication_check.py release/project-manager --all-files --denylist ../publication-denylist.txt
```

On PowerShell, replace the first command with
`New-Item -ItemType Directory -Path release` when that parent does not exist.
`--all-files` is intended for an unpacked standalone snapshot and checks everything
present, including unexpected runtime artifacts. Avoid generating bytecode caches
inside the package during validation; the examples use Python's `-B` option.

The exporter reads and scans the candidate once, then writes those exact bytes.
It refuses overwrites and output paths within the source, generates
`PUBLICATION-MANIFEST.json` with the version, relative paths, byte counts and SHA-256
hashes, and optionally creates a deterministic ZIP under a `project-manager/`
prefix. The manifest omits itself from its file list to avoid a circular hash;
its own SHA-256 is printed in the export report. These hashes establish snapshot
consistency, not author identity or a cryptographic signature.
When a manifest is present, the standalone check verifies the entire inventory,
version and file hashes; changed, missing, extra or malformed entries fail.

Do not modify the export after validation. Unpack the ZIP into a fresh temporary
directory and scan it as well before publishing. To publish source files on GitHub,
create a **new repository from the export**, with a deliberate public Git author
identity. The release ZIP retains `PUBLICATION-MANIFEST.json`; omit that generated
manifest from the editable source repository so ordinary contributions do not
leave a stale release inventory. Generate a fresh manifest for each release and
check the resulting package again. Never copy a `.git` directory into it. Review the platform's preview,
visibility, license, release notes and file list before making it public. This
workflow prepares local files; it does not create repositories, send messages,
upload data or change remote visibility.

## Dedicated repository convention

The public source places `SKILL.md`, `README.md`, `LICENSE`, scripts, references,
templates and tests at the repository root. It includes contribution/security
guidance, changelog, release notes and CI. Tag reviewed releases with their
version, attach the exported ZIP and a SHA-256 checksum, and document installation
under the folder name `project-manager`. Never claim registry publication merely
because a GitHub repository exists; listing on another service is a separate step.

These choices follow the self-contained skills and clear installation guidance
used by [Anthropic's skills](https://github.com/anthropics/skills) and
[Vercel's agent skills](https://github.com/vercel-labs/agent-skills), while keeping
one skill in this dedicated repository. The packaging contract follows the
[Agent Skills specification](https://agentskills.io/specification) and
[OpenClaw skills documentation](https://docs.openclaw.ai/tools/skills).
These are publication examples and format references, not endorsements.

## Revalidation and limitations

Run the release's behavior tests, package check and privacy check on each new
candidate. A successful scanner result applies only to the files and bytes it
read, with the denylist used on that run. Changes require another scan and export.
Run the exporter in a trusted local directory without concurrent writers. It is
not designed as a sandbox against another operating-system user racing filesystem
changes. The Git history audit is advisory evidence about its stated scope, not a
history-rewriting or credential-revocation tool.
