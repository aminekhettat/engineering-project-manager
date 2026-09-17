# Publishing a reviewed release

Publish only a reviewed snapshot. Do not mirror private development Git history,
workspace memory, machine configuration, authentication files or real project data.
The repository source uses MIT. The rights holder has also authorized a separate
MIT-0 distribution for ClawHub, whose [format rules](https://docs.openclaw.ai/clawhub/skill-format#license)
require MIT-0. This does not change the GitHub license.

## Validate the source

From the public source checkout on Linux:

```sh
python3 -B tools/run_checks.py
python3 -B tools/publication_check.py . --profile repository
git diff --check
```

The scanner reads tracked paths and current working-tree bytes. Stage intended new
files before scanning; commit and validate the exact final candidate. In a private
development workspace, use `publication/project-manager/tools/` for contributor
tools, `skills/project-manager` for the runtime and `--skill-root` on the test runner.
The root private CI configuration is not part of the public facade.

An optional local `--denylist FILE` contains private terms, one per line, and must
stay outside both distributable surfaces. It is never copied or included in a
manifest. If the deliberately public repository identifier overlaps a private
term, pass `--public-repository OWNER/REPO`. That exception applies only to the
exact qualified repository in permitted public contexts, not the owner's name in
arbitrary text. Review new exceptions; do not broadly suppress personal names.

## Runtime archive for GitHub (MIT)

Create an empty parent output directory outside the sources. Every destination
and archive name must be new; the exporter refuses existing paths.

```sh
mkdir -p release
python3 -B tools/export_public_skill.py skills/project-manager   --output release/project-manager   --archive release/project-manager-VERSION.zip
python3 -B tools/publication_check.py release/project-manager   --all-files --require-manifest
```

Replace VERSION with `skills/project-manager/VERSION`. Generate a SHA-256 companion
using the archive's basename. Unpack the ZIP into a new temporary directory, scan
it again with `--all-files --require-manifest` and run the package checker against
the extracted runtime. Do not edit an exported directory after validation.

`tools/build_release.py --output NEW_DIRECTORY` performs archive generation,
checksum creation, extraction and manifest/package validation for the public
checkout. It also rejects a tag version that disagrees with the runtime.

## Public repository from private sources

From the private development checkout:

```sh
python3 -B publication/project-manager/tools/export_public_skill.py   skills/project-manager --format repository --facade publication/project-manager   --output ../public-source-snapshot
python3 -B publication/project-manager/tools/publication_check.py   ../public-source-snapshot --profile repository --all-files --require-manifest
```

Add the private denylist and explicit public repository option locally as needed.
The exporter combines the facade at repository root and the runtime under
`skills/project-manager/`. Each surface receives a manifest. Exported archives
retain them; omit generated `PUBLICATION-MANIFEST.json` files when synchronizing
the editable public source. Preserve the public repository's own reviewed history;
never copy the private `.git` directory or force-push private branches over it.
Use a deliberate public Git author identity.

## Separate ClawHub distribution (MIT-0)

Generate a new runtime with an explicit license conversion:

```sh
python3 -B tools/export_public_skill.py skills/project-manager --license MIT-0   --output release/clawhub-runtime --archive release/project-manager-VERSION-clawhub.zip
python3 -B tools/publication_check.py release/clawhub-runtime   --all-files --require-manifest
```

The source remains unchanged. The copy contains the reviewed MIT-0 license text,
`license: MIT-0` frontmatter and a new manifest. It omits `.bumpversion.cfg` and
`.gitignore`, which the ClawHub client does not upload, so the manifest describes
the actual registry payload. Source version metadata stays unchanged; overriding the repository export's
license is refused. The archive's internal skill folder remains `project-manager`.

Authenticate with your own ClawHub account, review the preview and publish only
the prepared directory. With ClawHub CLI 0.23.3:

```sh
clawhub skill publish release/clawhub-runtime --slug openclaw-project-manager   --name "Project Manager" --version VERSION --changelog "Reviewed release changes" --dry-run
```

After checking ownership, contents, source provenance and intended visibility,
the same command without `--dry-run` publishes it. Supply `--source-repo`,
`--source-commit`, `--source-ref` and `--source-path skills/project-manager` with
the exact public source. Never reuse another service's token or place credentials
in repository files. Check the resulting listing and security/moderation status;
an accepted upload is not automatically an endorsed or verified listing.

## What the checks establish

Profiles are explicit: `runtime` permits operational scripts, references,
templates and runtime documentation; `facade` permits contributor and public
presentation files; `repository` combines them in the documented layout.
Files are UTF-8 text. The facade additionally accepts a restricted static SVG
subset and the fixed static page files with no scripts, embedded applications
or remote page resources. Runtime code, examples and SVG text are privacy-scanned.

Checks reject recognized credentials, private keys, credential-bearing URLs,
personal email/home paths, private addresses/hostnames, local denylist matches,
symlinks/junctions, submodules, unmerged index entries, caches and private paths.
Limits: 2 MiB per file, 10,000 files and 40 MiB per snapshot. Errors identify paths
and categories without echoing matched secret values. Manifests inventory exact
bytes, hashes, version, profile and license; `--require-manifest` also fails when
an artifact's manifest is missing. Each completed output is published atomically
without replacement; a directory and ZIP are not one cross-path OS transaction.

Pattern matching does not prove the absence of every secret, encoded value,
personal fact, proprietary text or rights issue. Review content and provenance.
The optional `--history` audit covers reachable Git commits and blobs, not reflogs,
unreachable objects, LFS payloads, server backups or other clones. If a credential
was exposed, revoke or rotate it at its issuer; deleting a file is insufficient.
Hashes establish snapshot consistency, not author identity or a signature.

## Release and discovery

Keep `VERSION` and `.bumpversion.cfg` synchronized using `bump2version`, update the
changelog and preserve old tags. The public CI matrix validates Python 3.10, 3.12
and 3.13; its packaging job checks installation with the pinned skills CLI and
uploads validated MIT runtime assets. The release workflow requires successful
validation of the tag before attaching those assets to a GitHub release.

GitHub Pages serves only `docs/`. The project overview links to real instructions,
releases, issues and discussions. Registry and directory submissions are separate
actions. For example, [Awesome OpenClaw Skills](https://github.com/VoltAgent/awesome-openclaw-skills/blob/main/CONTRIBUTING.md)
requires a published ClawHub listing and its own review. Do not claim inclusion
until accepted, or manipulate stars, installation counts or security scores.
