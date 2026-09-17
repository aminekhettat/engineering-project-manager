#!/usr/bin/env python3
"""Export checked runtime or public-repository snapshots without private history."""
from __future__ import annotations
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import zipfile
from publication_check import (MAX_FILE_BYTES, MAX_FILES, MAX_TOTAL_BYTES, PublicationError, is_link,
    load_denylist, read_snapshot, scan_text, source_paths, validate_public_repository)

MANIFEST = "PUBLICATION-MANIFEST.json"
MIT_ZERO_NORMALIZED_SHA256 = "1a39c0669271db4ffdf304c546561e37c09548ddfa6dd31ef1f835e7abccbe31"


def destination(path: Path, roots: list[Path]) -> Path:
    path = path.absolute()
    if path.exists() or is_link(path):
        raise PublicationError("output already exists; overwrite is refused")
    if not path.parent.is_dir():
        raise PublicationError("output parent must already exist")
    if any(is_link(parent) for parent in [path.parent, *path.parents]):
        raise PublicationError("output ancestor is a symlink or junction")
    if any(path.resolve().is_relative_to(root.resolve()) for root in roots):
        raise PublicationError("output must be outside every source surface")
    return path


def rename_exclusive(source: Path, target: Path) -> None:
    """Atomically publish a completed path while refusing any existing target."""
    if os.name == "nt":
        os.rename(source, target)
        return
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform.startswith("linux") and hasattr(library, "renameat2"):
        result = library.renameat2(-100, os.fsencode(source), -100, os.fsencode(target), 1)
    elif sys.platform == "darwin" and hasattr(library, "renamex_np"):
        result = library.renamex_np(os.fsencode(source), os.fsencode(target), 4)
    else:
        raise PublicationError("atomic no-overwrite export is unavailable on this platform")
    if result:
        raise OSError(ctypes.get_errno(), "exclusive publication failed")


def declared_license(payload: dict[str, bytes]) -> str:
    text = payload["SKILL.md"].decode("utf-8")
    match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.S)
    if not match:
        raise PublicationError("SKILL.md needs valid frontmatter before export")
    values = re.findall(r"^license:[ \t]*([^\r\n]+)\r?$", match.group(1), re.M)
    if len(values) != 1:
        raise PublicationError("SKILL.md needs one explicit license field")
    value = values[0].strip().strip("\"'")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+-]{0,63}", value):
        raise PublicationError("SKILL.md license must be a single SPDX identifier")
    return value


def licensing_copy(payload: dict[str, bytes], license_override: str | None) -> tuple[dict[str, bytes], str]:
    """Prepare the MIT-0 ClawHub payload before sealing its exact inventory."""
    result = dict(payload)
    current = declared_license(result)
    if license_override in (None, "source"):
        return result, current
    if license_override != "MIT-0" or current != "MIT":
        raise PublicationError("MIT-0 preparation requires the explicitly authorized MIT source")
    facade_root = Path(__file__).absolute().parent.parent
    template = facade_root / "licenses/MIT-0.txt"
    if (is_link(template) or is_link(template.parent) or not template.is_file() or
            not template.resolve().is_relative_to(facade_root.resolve())):
        raise PublicationError("reviewed MIT-0 license template is unavailable")
    license_bytes = template.read_bytes()
    normalized = re.sub(r"\s+", " ", license_bytes.decode("utf-8")).strip().encode("utf-8")
    if len(license_bytes) > 8192 or hashlib.sha256(normalized).hexdigest() != MIT_ZERO_NORMALIZED_SHA256:
        raise PublicationError("MIT-0 license template is invalid")
    result.pop("LICENSE.md", None)
    result["LICENSE"] = license_bytes
    skill_text = result["SKILL.md"].decode("utf-8")
    frontmatter, body = skill_text.split("---", 2)[1:]
    frontmatter = re.sub(r"^license:\s*[^\r\n]+", "license: MIT-0", frontmatter, count=1, flags=re.M)
    result["SKILL.md"] = ("---" + frontmatter + "---" + body).encode("utf-8")
    # ClawHub CLI 0.23.3 excludes dotfiles during upload. Omit these two
    # development files before manifest generation so its hashes describe the
    # uploaded inventory. The scanned source and MIT exports keep both files.
    for name in (".bumpversion.cfg", ".gitignore"):
        result.pop(name, None)
    return result, "MIT-0"


def add_manifest(payload, version, profile, license_name, denylist, public_repository):
    payload = dict(payload)
    payload.pop(MANIFEST, None)
    manifest = {"schema_version": 2, "name": "project-manager", "version": version,
                "distribution": "history-free-snapshot", "profile": profile, "license": license_name,
                "files": [{"path": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
                          for name, content in sorted(payload.items())]}
    encoded = (json.dumps(manifest, indent=2, ensure_ascii=True) + "\n").encode("utf-8")
    if scan_text(MANIFEST, encoded.decode("utf-8"), denylist, public_repository):
        raise PublicationError("generated manifest failed privacy review")
    payload[MANIFEST] = encoded
    return payload


def write_payload(root, payload):
    for name, content in sorted(payload.items()):
        target = root.joinpath(*name.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(content)


def remove_own_payload(root, payload):
    """Rollback only paths created by this export, never recursively delete."""
    for name in payload:
        (root / name).unlink(missing_ok=True)
    folders = {parent for name in payload for parent in (root / name).parents if parent.is_relative_to(root)}
    for folder in sorted(folders, key=lambda value: len(value.parts), reverse=True):
        folder.rmdir()


def export_skill(root: Path, output: Path, archive: Path | None = None,
                 denylist_path: Path | None = None, all_files: bool = False,
                 profile: str = "runtime", facade: Path | None = None,
                 public_repository: str | None = None, license_override: str | None = None) -> dict:
    """Prepare both surfaces locally; only fully checked bytes reach an output."""
    validate_public_repository(public_repository)
    if profile not in {"runtime", "repository"}:
        raise PublicationError("export format must be runtime or repository")
    if profile == "repository" and facade is None:
        raise PublicationError("repository export needs an explicit facade source")
    if profile == "repository" and license_override not in (None, "source"):
        raise PublicationError("license override is restricted to a separate runtime distribution")
    roots = [root] + ([facade] if profile == "repository" else [])
    output = destination(output, roots)
    if archive is not None:
        archive = destination(archive, roots)
        if archive.suffix.casefold() != ".zip" or archive == output or archive.is_relative_to(output):
            raise PublicationError("archive must be a separate ZIP outside the output directory")
    denylist = load_denylist(denylist_path, root)
    if facade is not None:
        load_denylist(denylist_path, facade)
    payload, findings = read_snapshot(root, source_paths(root, all_files), denylist, "runtime", public_repository)
    facade_payload = {}
    if profile == "repository":
        facade_payload, facade_findings = read_snapshot(facade, source_paths(facade, all_files), denylist, "facade", public_repository)
        findings.extend(facade_findings)
    if findings:
        return {"status": "FAIL", "files_checked": len(payload) + len(facade_payload),
                "findings": [finding.as_dict() for finding in findings]}
    if not any(payload.get(name, b"").strip() for name in ("LICENSE", "LICENSE.md")):
        raise PublicationError("runtime requires a nonempty LICENSE or LICENSE.md")
    if profile == "repository" and not any(facade_payload.get(name, b"").strip() for name in ("LICENSE", "LICENSE.md")):
        raise PublicationError("public repository facade requires its own license")
    version = payload["VERSION"].decode("utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", version) or len(version) > 64:
        raise PublicationError("VERSION must be a short semantic version")
    payload, license_name = licensing_copy(payload, license_override)
    if profile == "repository" and license_name != "MIT":
        raise PublicationError("the authorized public repository must retain its MIT source license")
    for name in ("SKILL.md", "LICENSE"):
        if name in payload and scan_text(name, payload[name].decode("utf-8"), denylist, public_repository):
            raise PublicationError("prepared license or frontmatter failed privacy review")
    payload = add_manifest(payload, version, "runtime", license_name, denylist, public_repository)
    if profile == "repository":
        if "VERSION" in facade_payload and facade_payload["VERSION"].decode("utf-8").strip() != version:
            raise PublicationError("facade and runtime versions differ")
        payload = {**facade_payload, **{"skills/project-manager/" + name: content for name, content in payload.items()}}
        payload = add_manifest(payload, version, "repository", license_name, denylist, public_repository)
    if (len(payload) > MAX_FILES or sum(map(len, payload.values())) > MAX_TOTAL_BYTES or
            any(len(content) > MAX_FILE_BYTES for content in payload.values())):
        raise PublicationError("combined distribution exceeds snapshot limits")
    published = False
    archive_published = False
    try:
        with tempfile.TemporaryDirectory(prefix=".pm-export-", dir=output.parent) as temporary:
            staging = Path(temporary).resolve()
            if not staging.is_relative_to(output.parent.resolve()):
                raise PublicationError("staging directory escaped output parent")
            prepared = staging / "snapshot"
            prepared.mkdir()
            write_payload(prepared, payload)
            if archive is not None:
                descriptor, zip_name = tempfile.mkstemp(prefix=".pm-archive-", suffix=".zip", dir=archive.parent)
                os.close(descriptor)
                prepared_zip = Path(zip_name)
                try:
                    with zipfile.ZipFile(prepared_zip, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                        prefix = "project-manager/" if profile == "runtime" else "openclaw-project-manager/"
                        for name, content in sorted(payload.items()):
                            entry = zipfile.ZipInfo(prefix + name, date_time=(1980, 1, 1, 0, 0, 0))
                            entry.create_system = 3
                            entry.external_attr = 0o100644 << 16
                            entry.compress_type = zipfile.ZIP_DEFLATED
                            bundle.writestr(entry, content)
                    rename_exclusive(prepared, output)
                    published = True
                    rename_exclusive(prepared_zip, archive)
                    archive_published = True
                finally:
                    prepared_zip.unlink(missing_ok=True)
            else:
                rename_exclusive(prepared, output)
                published = True
    except (OSError, PublicationError) as exc:
        if archive_published:
            archive.unlink(missing_ok=True)
        if published:
            remove_own_payload(output, payload)
        raise PublicationError("atomic export failed; no existing output was overwritten") from exc
    return {"status": "PASS", "name": "project-manager", "version": version, "profile": profile,
            "license": license_name, "files_exported": len(payload), "archive_created": archive is not None,
            "manifest_sha256": hashlib.sha256(payload[MANIFEST]).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill", type=Path)
    parser.add_argument("--format", choices=("runtime", "repository"), default="runtime")
    parser.add_argument("--facade", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--denylist", type=Path)
    parser.add_argument("--public-repository")
    parser.add_argument("--license", choices=("source", "MIT-0"), default="source",
                        help="MIT-0 prepares a separate ClawHub runtime and omits .bumpversion.cfg/.gitignore before sealing the manifest")
    parser.add_argument("--all-files", action="store_true", help="Inputs are clean standalone snapshots, not development checkouts")
    args = parser.parse_args()
    try:
        result = export_skill(args.skill, args.output, args.archive, args.denylist, args.all_files,
                              args.format, args.facade, args.public_repository, args.license)
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return 0 if result["status"] == "PASS" else 1
    except (PublicationError, OSError, UnicodeError) as exc:
        message = str(exc) if isinstance(exc, PublicationError) else "source or output cannot be processed"
        print(json.dumps({"status": "FAIL", "error": message}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
