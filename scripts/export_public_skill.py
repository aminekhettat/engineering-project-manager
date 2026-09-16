#!/usr/bin/env python3
"""Export a checked, history-free skill snapshot and optional deterministic ZIP."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

from publication_check import (PublicationError, is_link, load_denylist, read_snapshot,
                               scan_text, source_paths)

MANIFEST = "PUBLICATION-MANIFEST.json"


def destination(path: Path, root: Path) -> Path:
    path = path.absolute()
    if path.exists() or is_link(path):
        raise PublicationError("output already exists; overwrite is refused")
    if not path.parent.is_dir():
        raise PublicationError("output parent must already exist")
    if any(is_link(parent) for parent in [path.parent, *path.parents]):
        raise PublicationError("output ancestor is a symlink or junction")
    if path.resolve().is_relative_to(root.resolve()):
        raise PublicationError("output must be outside the source skill")
    return path


def export_skill(root: Path, output: Path, archive: Path | None = None,
                 denylist_path: Path | None = None, all_files: bool = False) -> dict:
    """Read and validate once, then copy only those exact bytes; never copy Git."""
    output = destination(output, root)
    if archive is not None:
        archive = destination(archive, root)
        if archive.suffix.casefold() != ".zip" or archive == output or archive.is_relative_to(output):
            raise PublicationError("archive must be a separate ZIP outside the output directory")
    denylist = load_denylist(denylist_path, root)
    payload, findings = read_snapshot(root, source_paths(root, all_files), denylist)
    if findings:
        return {"status": "FAIL", "files_checked": len(payload),
                "findings": [finding.as_dict() for finding in findings]}
    if not any(payload.get(name, b"").strip() for name in ("LICENSE", "LICENSE.md")):
        raise PublicationError("a nonempty LICENSE or LICENSE.md is required for public export")
    try:
        version = payload["VERSION"].decode("utf-8").strip()
    except (KeyError, UnicodeError) as exc:
        raise PublicationError("VERSION must be readable UTF-8") from exc
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", version) or len(version) > 64:
        raise PublicationError("VERSION must be a short semantic version")
    # A manifest from an earlier snapshot is regenerated, never trusted.
    payload.pop(MANIFEST, None)
    manifest = {
        "schema_version": 1,
        "name": "project-manager",
        "version": version,
        "distribution": "history-free-snapshot",
        "files": [{"path": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
                  for name, content in sorted(payload.items())],
    }
    manifest_bytes = (json.dumps(manifest, indent=2, ensure_ascii=True) + "\n").encode("utf-8")
    if scan_text(MANIFEST, manifest_bytes.decode("utf-8"), denylist):
        raise PublicationError("generated manifest failed privacy review")
    payload[MANIFEST] = manifest_bytes
    # Exclusive creation prevents accidental replacement. On failure, remove only
    # files this invocation created. It never recursively deletes arbitrary paths.
    created_files: list[Path] = []
    created_dirs: list[Path] = []
    archive_created = False
    try:
        output.mkdir(exist_ok=False)
        created_dirs.append(output)
        for name, content in sorted(payload.items()):
            target = output.joinpath(*name.split("/"))
            for parent in reversed(target.relative_to(output).parents):
                folder = output / parent
                if folder != output and not folder.exists():
                    folder.mkdir(exist_ok=False)
                    created_dirs.append(folder)
            with target.open("xb") as stream:
                created_files.append(target)
                stream.write(content)
        if archive is not None:
            with archive.open("xb") as stream:
                archive_created = True
                with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                    for name, content in sorted(payload.items()):
                        entry = zipfile.ZipInfo("project-manager/" + name, date_time=(1980, 1, 1, 0, 0, 0))
                        entry.create_system = 3
                        entry.external_attr = 0o100644 << 16
                        entry.compress_type = zipfile.ZIP_DEFLATED
                        bundle.writestr(entry, content)
    except OSError as exc:
        if archive_created and archive is not None:
            archive.unlink(missing_ok=True)
        for path in reversed(created_files):
            path.unlink(missing_ok=True)
        for path in reversed(created_dirs):
            path.rmdir()
        raise PublicationError("exclusive output creation failed; no existing output was overwritten") from exc
    return {"status": "PASS", "name": "project-manager", "version": version,
            "files_exported": len(payload), "archive_created": archive is not None,
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill", nargs="?", type=Path, default=Path(__file__).absolute().parent.parent)
    parser.add_argument("--output", required=True, type=Path, help="New directory outside source; parent must exist")
    parser.add_argument("--archive", type=Path, help="Optional new ZIP outside source")
    parser.add_argument("--denylist", type=Path, help="Local terms file outside distributable skill")
    parser.add_argument("--all-files", action="store_true", help="Source is a standalone clean snapshot, not a Git checkout")
    args = parser.parse_args()
    try:
        result = export_skill(args.skill, args.output, args.archive, args.denylist, args.all_files)
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return 0 if result["status"] == "PASS" else 1
    except PublicationError as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
