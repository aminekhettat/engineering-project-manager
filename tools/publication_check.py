#!/usr/bin/env python3
"""Fail-closed, redacted privacy checks for a distributable skill snapshot.

This is a conservative release guard, not proof that all private information
has been removed. Use a local denylist and a human review before publication.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from html.parser import HTMLParser
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import xml.etree.ElementTree as ET

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 40 * 1024 * 1024
MAX_FILES = 10000
RUNTIME_DIRS = {"scripts", "docs", "references", "templates"}
RUNTIME_ROOT_FILES = {"SKILL.md", "README.md", "CHANGELOG.md", "VERSION", "LICENSE", "LICENSE.md",
                      "NOTICE", "NOTICE.md", "PUBLICATION-MANIFEST.json", ".gitignore", ".bumpversion.cfg", "SECURITY.md"}
FACADE_DIRS = {"docs", "examples", "tests", "tools", "media", "licenses", ".github", ".codex-plugin", ".claude-plugin"}
PUBLIC_ROOT_FILES = {
    "SKILL.md", "README.md", "CHANGELOG.md", "VERSION", "LICENSE", "LICENSE.md",
    "NOTICE", "NOTICE.md", "CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md",
    "PUBLICATION-MANIFEST.json", ".gitignore", ".bumpversion.cfg", ".gitlab-ci.yml",
    "BASELINE-V1-SHA256.txt", "pyproject.toml", "requirements.txt",
    "README.fr.md", "marketplace.json", ".gitattributes",
}
PROFILES = {"runtime", "facade", "repository"}
TEXT_SUFFIXES = {".md", ".py", ".txt", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".sh"}
DENIED_DIRS = {
    ".git", ".ssh", ".aws", ".gnupg", ".openclaw", "__pycache__", ".pytest_cache",
    "node_modules", ".venv", "venv", "workspace", "workspaces", "memory", "private",
    "backups", "backup", "logs", "runtime", "projects", "sessions",
}
SENSITIVE_NAMES = {"credentials", "credentials.json", "secrets.json", "secrets.yaml",
                   "secrets.yml", "id_rsa", "id_ed25519", "known_hosts", "authorized_keys",
                   "pm_master_prompt.txt", "publication-denylist.txt"}
PRIVATE_NETS = tuple(ipaddress.ip_network(".".join(map(str, octets)) + "/" + str(prefix))
                     for octets, prefix in (((10, 0, 0, 0), 8), ((172, 16, 0, 0), 12),
                                            ((192, 168, 0, 0), 16), ((127, 0, 0, 0), 8),
                                            ((169, 254, 0, 0), 16)))
TOKEN_PATTERNS = (
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----")),
    ("service-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,}|glpat-[A-Za-z0-9_-]{16,}|xox[baprs]-[A-Za-z0-9-]{15,}|sk-(?:proj-)?[A-Za-z0-9_-]{24,})\b")),
    ("cloud-key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b|\bAIza[0-9A-Za-z_-]{35}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("credential-url", re.compile(r"\b(?:[a-z][a-z0-9+.-]*://[^\s/:@]+:[^\s/@]+@|https?://[^\s/@]+@)", re.I)),
    ("personal-path", re.compile(r"(?i)(?:[a-z]:[\\/]Users[\\/]|/(?:home|Users)/)[a-z0-9_.-]+")),
    ("private-hostname", re.compile(r"\b[a-z0-9][a-z0-9.-]*\.(?:local|lan|internal|home|corp)\b(?!\s*\()", re.I)),
)
EMAIL_RE = re.compile(r"\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)\b")
IPV4_RE = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
IPV6_RE = re.compile(r"(?<![\w:])(?:[0-9a-fA-F]{0,4}:){2,}[0-9a-fA-F:]{0,39}(?![\w:])")
ASSIGNMENT_RE = re.compile(
    r"(?im)^\s*(?:export\s+)?[\"']?(?:[A-Z0-9_]*_)?(?:api_?key|token|password|passwd|secret|client_secret|access_key|private_key)[\"']?\s*[:=]\s*[\"']?([^\s\"',;#}\]]{8,})")
PLACEHOLDERS = {"changeme", "change_me", "placeholder", "example", "redacted", "your_token", "your_api_key", "not-set"}


@dataclass(frozen=True)
class Finding:
    path: str
    category: str
    line: int | None = None

    def as_dict(self) -> dict:
        result = {"path": self.path, "category": self.category}
        if self.line is not None:
            result["line"] = self.line
        return result


class PublicationError(ValueError):
    """Error messages intentionally contain no input values or absolute paths."""


def load_denylist(path: Path | None, root: Path) -> tuple[str, ...]:
    if path is None:
        return ()
    try:
        if is_link(path):
            raise PublicationError("denylist must not be a symlink or junction")
        resolved = path.resolve(strict=True)
        if resolved.is_relative_to(root.resolve()):
            raise PublicationError("denylist must be outside the distributable skill")
        if resolved.stat().st_size > MAX_FILE_BYTES:
            raise PublicationError("denylist exceeds size limit")
        values = tuple(line.strip().casefold() for line in resolved.read_text(encoding="utf-8").splitlines()
                       if line.strip() and not line.lstrip().startswith("#"))
        if any(len(value) < 3 for value in values):
            raise PublicationError("denylist entries must contain at least three characters")
        return values
    except (OSError, UnicodeError) as exc:
        raise PublicationError("denylist cannot be read as UTF-8") from exc


def safe_path(relative: str, denylist: tuple[str, ...] = ()) -> str:
    value = relative
    for term in denylist:
        value = re.sub(re.escape(term), "[redacted]", value, flags=re.I)
    return "".join(char if char.isprintable() else "?" for char in value)


def path_findings(relative: str, denylist: tuple[str, ...], profile: str = "runtime") -> list[Finding]:
    path = PurePosixPath(relative)
    label = safe_path(relative, denylist)
    findings = []
    parts = [part.casefold() for part in path.parts]
    if not path.parts or path.is_absolute() or ".." in path.parts or "\\" in relative or ":" in relative:
        return [Finding("[invalid-path]", "unsafe-path")]
    if any(part in DENIED_DIRS for part in parts):
        findings.append(Finding(label, "runtime-or-private-directory"))
    name = path.name.casefold()
    if (name in SENSITIVE_NAMES or name == ".env" or name.startswith(".env.") or
            name.endswith((".pem", ".key", ".p12", ".pfx", ".sqlite", ".db", ".pyc", ".pyo", "~")) or
            any(marker in name for marker in (".bak", ".backup", ".legacy-", ".broken-"))):
        findings.append(Finding(label, "sensitive-or-backup-file"))
    if profile not in PROFILES:
        raise PublicationError("unknown distribution profile")
    if profile == "repository" and path.parts[:2] == ("skills", "project-manager"):
        return path_findings("/".join(path.parts[2:]), denylist, "runtime")
    directories = RUNTIME_DIRS if profile == "runtime" else FACADE_DIRS
    root_files = RUNTIME_ROOT_FILES if profile == "runtime" else PUBLIC_ROOT_FILES
    if (len(path.parts) == 1 and path.name not in root_files or
            len(path.parts) > 1 and path.parts[0] not in directories):
        findings.append(Finding(label, "outside-distribution-allowlist"))
    static_svg = (profile != "runtime" and (path.parts[0] == "media" or path.parts[:2] == ("docs", "assets"))
                  and path.suffix.casefold() == ".svg")
    static_page = profile != "runtime" and relative in {"docs/index.html", "docs/site.css", "docs/.nojekyll"}
    if len(path.parts) > 1 and path.suffix.casefold() not in TEXT_SUFFIXES and not static_svg and not static_page:
        findings.append(Finding(label, "unsupported-file-type"))
    if profile == "runtime" and (path.name.endswith(("_tests.py", "_test.py")) or path.name in {
            "publication_check.py", "export_public_skill.py", "run_checks.py", "skill_package_check.py",
            "project_manager_self_check.py", "test_support.py", "validation_paths.py"}):
        findings.append(Finding(label, "development-file-in-runtime"))
    if any(term in relative.casefold() for term in denylist):
        findings.append(Finding(label, "local-denylist"))
    return findings


def fictional_domain(domain: str) -> bool:
    domain = domain.casefold()
    return (domain.endswith(".example") or domain == "example" or
            any(domain == item or domain.endswith("." + item)
                for item in ("example.com", "example.net", "example.org", "example.invalid")))


def validate_public_repository(value: str | None) -> str | None:
    if value is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", value):
        raise PublicationError("public repository must be a qualified OWNER/REPOSITORY name")
    return value


def scan_text(relative: str, text: str, denylist: tuple[str, ...] = (), public_repository: str | None = None) -> list[Finding]:
    label = safe_path(relative, denylist)
    findings: set[tuple[str, int]] = set()
    def add(category: str, offset: int) -> None:
        findings.add((category, text.count("\n", 0, offset) + 1))
    for category, pattern in TOKEN_PATTERNS:
        for match in pattern.finditer(text):
            add(category, match.start())
    for match in EMAIL_RE.finditer(text):
        # Pinned package syntax (package@1.2.3) has no alphabetic mail domain.
        # Actual private IP literals remain covered by the independent IP check.
        if re.fullmatch(r"[0-9.]+", match.group(1)):
            continue
        if not fictional_domain(match.group(1)):
            add("personal-email", match.start())
    for match in IPV4_RE.finditer(text):
        try:
            address = ipaddress.ip_address(match.group())
            if any(address in network for network in PRIVATE_NETS):
                add("private-network-address", match.start())
        except ValueError:
            pass
    for match in IPV6_RE.finditer(text):
        try:
            address = ipaddress.ip_address(match.group())
            if (address in ipaddress.ip_network("fc00" + ":" * 2 + "/7") or address.is_link_local or address.is_loopback):
                add("private-network-address", match.start())
        except ValueError:
            pass
    for match in ASSIGNMENT_RE.finditer(text):
        value = match.group(1)
        if (value.casefold() not in PLACEHOLDERS and not value.startswith(("<", "$", "{", "os.environ", "getenv("))
                and not re.fullmatch(r"[Xx*._-]+", value)):
            add("credential-assignment", match.start())
    authorized = []
    if validate_public_repository(public_repository) is not None:
        pattern = re.compile(r"(?<![A-Za-z0-9_.@-])" + re.escape(public_repository) + r"(?:\.git)?(?![A-Za-z0-9_.-])")
        authorized = [(match.start(), match.end()) for match in pattern.finditer(text)]
    for term in denylist:
        for match in re.finditer(re.escape(term), text, re.I):
            if not any(start <= match.start() and match.end() <= end for start, end in authorized):
                add("local-denylist", match.start())
    return [Finding(label, category, line) for category, line in sorted(findings, key=lambda item: (item[1], item[0]))]


def svg_findings(relative: str, text: str, denylist: tuple[str, ...], public_repository=None) -> list[Finding]:
    """Accept only a small inert SVG vocabulary; never resolve external content."""
    label = safe_path(relative, denylist)
    upper = text.upper()
    if "<!DOCTYPE" in upper or "<!ENTITY" in upper or re.search(r"<\?(?!xml\s)", text, re.I):
        return [Finding(label, "unsafe-svg-declaration")]
    tags = {"svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text", "tspan",
            "defs", "linearGradient", "radialGradient", "stop", "clipPath", "mask", "title", "desc", "use"}
    attrs = {"id", "width", "height", "viewBox", "role", "aria-label", "aria-labelledby", "fill", "stroke",
             "stroke-width", "stroke-linecap", "stroke-linejoin", "stroke-dasharray", "opacity", "fill-opacity",
             "stroke-opacity", "transform", "x", "y", "x1", "x2", "y1", "y2", "cx", "cy", "r", "rx", "ry",
             "d", "points", "font-family", "font-size", "font-weight", "text-anchor", "dominant-baseline", "dx", "dy",
             "offset", "stop-color", "stop-opacity", "gradientUnits", "gradientTransform", "spreadMethod", "clip-path",
             "mask", "href", "preserveAspectRatio", "version", "xml:space", "letter-spacing", "word-spacing"}
    try:
        root = ET.fromstring(text)
        if root.tag not in {"svg", "{http://www.w3.org/2000/svg}svg"}:
            raise ValueError("root")
        semantic = []
        count = 0
        for element in root.iter():
            count += 1
            if count > 10000:
                raise ValueError("nodes")
            tag = element.tag
            if tag.startswith("{http://www.w3.org/2000/svg}"):
                tag = tag.split("}", 1)[1]
            if tag not in tags:
                raise ValueError("tag")
            semantic.extend([element.text or "", element.tail or ""])
            for key, value in element.attrib.items():
                key = key.replace("{http://www.w3.org/1999/xlink}href", "href").replace("{http://www.w3.org/XML/1998/namespace}space", "xml:space")
                if key not in attrs:
                    raise ValueError("attribute")
                if key == "href" and not re.fullmatch(r"#[A-Za-z_][A-Za-z0-9_.:-]*", value):
                    raise ValueError("link")
                clean = re.sub(r"url\(\s*#[A-Za-z_][A-Za-z0-9_.:-]*\s*\)", "", value)
                if re.search(r"url\s*\(|(?:https?|file|data|javascript):|//|@import|expression\s*\(", clean, re.I):
                    raise ValueError("external content")
                semantic.append(value)
        return scan_text(relative, "\n".join(semantic), denylist, public_repository)
    except (ET.ParseError, ValueError, RecursionError):
        return [Finding(label, "unsafe-or-malformed-svg")]


def page_findings(relative, text, payload, denylist, public_repository=None):
    label = safe_path(relative, denylist)
    if relative == "docs/.nojekyll":
        return [] if not text.strip() else [Finding(label, "nonempty-static-site-marker")]
    if relative == "docs/site.css":
        if re.search(r"@import|url\s*\(|expression\s*\(|javascript:|behavior\s*:|\\|<", text, re.I):
            return [Finding(label, "unsafe-static-css")]
        return []
    if relative != "docs/index.html":
        return []
    errors = []
    semantic = []
    class StaticPage(HTMLParser):
        def handle_decl(self, value):
            if value.casefold() != "doctype html":
                errors.append(Finding(label, "unsafe-html-declaration"))
        def handle_pi(self, value):
            errors.append(Finding(label, "unsafe-html-processing-instruction"))
        def handle_data(self, value):
            semantic.append(value)
        def handle_starttag(self, tag, attributes):
            allowed_tags = {"html", "head", "title", "meta", "link", "body", "main", "header", "footer", "nav",
                            "section", "article", "aside", "div", "span", "h1", "h2", "h3", "h4", "h5", "h6", "p",
                            "a", "img", "ul", "ol", "li", "pre", "code", "table", "thead", "tbody", "tr", "th", "td",
                            "br", "hr", "strong", "em", "small", "details", "summary", "figure", "figcaption", "blockquote"}
            allowed_attributes = {"href", "src", "class", "id", "title", "lang", "charset", "name", "content", "rel",
                                  "type", "width", "height", "alt", "aria-label", "aria-labelledby", "aria-hidden", "role",
                                  "target", "loading", "decoding"}
            if tag not in allowed_tags or len({key for key, _ in attributes}) != len(attributes):
                errors.append(Finding(label, "unsafe-static-html"))
            for key, value in attributes:
                value = value or ""
                semantic.append(value)
                if key not in allowed_attributes:
                    errors.append(Finding(label, "unsafe-html-attribute"))
                if key in {"href", "src"}:
                    if tag == "a" and key == "href" and (value.startswith("https://") or value.startswith("#")):
                        continue
                    # Every fetched page resource must be relative and packaged.
                    if (not value or value.startswith(("/", "\\")) or ":" in value or "?" in value or
                            "\\" in value or ".." in PurePosixPath(value).parts or "%" in value):
                        errors.append(Finding(label, "external-or-unsafe-page-resource"))
                        continue
                    resource = "docs/" + value.split("#", 1)[0]
                    if resource not in payload:
                        errors.append(Finding(label, "missing-static-page-resource"))
                    if key == "src" and not resource.endswith(".svg"):
                        errors.append(Finding(label, "unsupported-static-page-resource"))
                    if tag == "link" and (resource != "docs/site.css" or dict(attributes).get("rel") != "stylesheet"):
                        errors.append(Finding(label, "unsupported-static-page-link"))
        handle_startendtag = handle_starttag
    try:
        parser = StaticPage(convert_charrefs=True)
        parser.feed(text)
        parser.close()
    except (ValueError, RecursionError):
        errors.append(Finding(label, "malformed-static-html"))
    errors.extend(scan_text(relative, "\n".join(semantic), denylist, public_repository))
    return errors


def git(root: Path, *arguments: str) -> bytes:
    try:
        result = subprocess.run(["git", "-C", str(root), *arguments], stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, check=False, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PublicationError("Git read failed") from exc
    if result.returncode:
        raise PublicationError("Git read failed; use --all-files only for a standalone snapshot")
    return result.stdout


def is_link(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def source_paths(root: Path, all_files: bool = False) -> list[str]:
    if is_link(root) or not root.is_dir():
        raise PublicationError("skill root must be an existing directory, not a symlink")
    if all_files:
        paths = []
        def walk_error(_error):
            raise PublicationError("cannot enumerate every snapshot directory")
        for folder, directories, files in os.walk(root, followlinks=False, onerror=walk_error):
            for name in list(directories):
                path = Path(folder) / name
                if is_link(path) or name.casefold() in DENIED_DIRS:
                    paths.append(path.relative_to(root).as_posix())
                    directories.remove(name)
            paths.extend((Path(folder) / name).relative_to(root).as_posix() for name in files)
            if len(paths) > MAX_FILES:
                raise PublicationError("file count exceeds limit")
    else:
        raw = git(root, "ls-files", "--stage", "-z", "--", ".")
        try:
            paths = []
            for item in raw.split(b"\0"):
                if not item:
                    continue
                header, encoded_path = item.split(b"\t", 1)
                mode, _oid, stage = header.split()
                if mode not in (b"100644", b"100755") or stage != b"0":
                    raise PublicationError("Git contains symlink, submodule or unmerged entries")
                paths.append(encoded_path.decode("utf-8", "strict"))
        except UnicodeError as exc:
            raise PublicationError("Git contains non-UTF-8 paths") from exc
    if not paths or len(paths) > MAX_FILES:
        raise PublicationError("empty snapshot or file count exceeds limit")
    return sorted(set(paths))


def read_snapshot(root: Path, paths: list[str], denylist: tuple[str, ...], profile: str = "runtime",
                  public_repository: str | None = None) -> tuple[dict[str, bytes], list[Finding]]:
    validate_public_repository(public_repository)
    root = root.absolute()
    payload = {}
    findings = []
    total = 0
    for relative in paths:
        if scan_text("[file-name]", relative, denylist):
            errors = [Finding("[redacted-file-name]", "private-file-name")]
        else:
            errors = path_findings(relative, denylist, profile)
        findings.extend(errors)
        if errors:
            continue
        label = safe_path(relative, denylist)
        path = root.joinpath(*PurePosixPath(relative).parts)
        try:
            # Check every component without following a link outside the source.
            current = root
            linked = is_link(root)
            for component in PurePosixPath(relative).parts:
                current = current / component
                linked = linked or is_link(current)
            if linked or not path.resolve().is_relative_to(root.resolve()):
                findings.append(Finding(label, "symlink-or-path-escape"))
                continue
            metadata = path.stat()
            if not stat.S_ISREG(metadata.st_mode):
                findings.append(Finding(label, "non-regular-file"))
                continue
            if metadata.st_size > MAX_FILE_BYTES:
                findings.append(Finding(label, "oversized-file"))
                continue
            with path.open("rb") as stream:
                content = stream.read(MAX_FILE_BYTES + 1)
            total += len(content)
            if len(content) > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
                findings.append(Finding(label, "snapshot-size-limit"))
                continue
            decoded = content.decode("utf-8", "strict")
            if "\0" in decoded or any(ord(char) < 32 and char not in "\n\r\t" for char in decoded):
                findings.append(Finding(label, "binary-or-control-characters"))
                continue
            findings.extend(scan_text(relative, decoded, denylist, public_repository))
            if PurePosixPath(relative).suffix.casefold() == ".svg":
                findings.extend(svg_findings(relative, decoded, denylist, public_repository))
            payload[relative] = content
        except UnicodeError:
            findings.append(Finding(label, "non-utf8-or-binary-file"))
        except OSError:
            findings.append(Finding(label, "unreadable-file"))
    required_files = {"runtime": ("SKILL.md", "VERSION"), "facade": ("README.md",),
                      "repository": ("README.md", "skills/project-manager/SKILL.md", "skills/project-manager/VERSION")}
    for required in required_files[profile]:
        if required not in payload:
            findings.append(Finding(required, "required-file-missing"))
    if profile != "runtime":
        for relative in ("docs/index.html", "docs/site.css", "docs/.nojekyll"):
            if relative in payload:
                findings.extend(page_findings(relative, payload[relative].decode("utf-8"), payload, denylist, public_repository))
    return payload, findings


def audit_history(root: Path, denylist: tuple[str, ...]) -> dict:
    """Audit reachable Git objects without exposing messages, authors or values."""
    commits = git(root, "rev-list", "--all").splitlines()
    counts: dict[str, int] = {}
    seen = set()
    for commit in commits:
        record = git(root, "cat-file", "commit", commit.decode("ascii"))
        # Author metadata and commit messages are private release surfaces too.
        for finding in scan_text("[git-metadata]", record.decode("utf-8", "replace"), denylist):
            counts[finding.category] = counts.get(finding.category, 0) + 1
        tree = git(root, "ls-tree", "-rz", commit.decode("ascii"), "--", ".")
        for entry in tree.split(b"\0"):
            if not entry:
                continue
            header, relative_bytes = entry.split(b"\t", 1)
            mode, object_type, oid = header.split()
            if oid in seen:
                continue
            seen.add(oid)
            if mode == b"120000":
                counts["historical-symlink"] = counts.get("historical-symlink", 0) + 1
                continue
            if object_type != b"blob":
                continue
            size = int(git(root, "cat-file", "-s", oid.decode("ascii")))
            if size > MAX_FILE_BYTES:
                counts["historical-oversized-file"] = counts.get("historical-oversized-file", 0) + 1
                continue
            try:
                data = git(root, "cat-file", "blob", oid.decode("ascii")).decode("utf-8", "strict")
                relative = relative_bytes.decode("utf-8", "strict")
            except UnicodeError:
                counts["historical-binary-file"] = counts.get("historical-binary-file", 0) + 1
                continue
            for finding in scan_text("[historical-file]", relative + "\n" + data, denylist):
                counts[finding.category] = counts.get(finding.category, 0) + 1
    return {"commits": len(commits), "unique_objects": len(seen), "findings_by_category": counts,
            "scope": "reachable commits and skill blobs; excludes reflogs, unreachable objects, LFS content and server copies"}


def check_manifest(payload: dict[str, bytes], profile="runtime") -> list[Finding]:
    """Validate a distribution's inventory and hashes when its manifest exists."""
    name = "PUBLICATION-MANIFEST.json"
    if name not in payload:
        return []
    try:
        manifest = json.loads(payload[name].decode("utf-8"))
        fields = {"schema_version", "name", "version", "distribution", "files"}
        if isinstance(manifest, dict) and manifest.get("schema_version") == 2:
            fields |= {"profile", "license"}
        version_file = "skills/project-manager/VERSION" if profile == "repository" else "VERSION"
        if (not isinstance(manifest, dict) or set(manifest) != fields or
                type(manifest["schema_version"]) is not int or manifest["schema_version"] not in {1, 2} or
                manifest["name"] != "project-manager" or
                manifest["distribution"] != "history-free-snapshot" or
                manifest["version"] != payload[version_file].decode("utf-8").strip() or
                manifest.get("profile", "runtime") != profile or
                not isinstance(manifest.get("license", "source"), str) or
                not isinstance(manifest["files"], list)):
            return [Finding(name, "invalid-publication-manifest")]
        expected = [{"path": path, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
                    for path, content in sorted(payload.items()) if path != name]
        if manifest["files"] != expected:
            return [Finding(name, "publication-manifest-mismatch")]
        if manifest["schema_version"] == 2:
            skill_name = "skills/project-manager/SKILL.md" if profile == "repository" else "SKILL.md"
            frontmatter = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", payload[skill_name].decode("utf-8"), re.S)
            values = re.findall(r"^license:[ \t]*([^\r\n]+)\r?$", frontmatter.group(1), re.M) if frontmatter else []
            if len(values) != 1 or values[0].strip().strip("\"'") != manifest["license"]:
                return [Finding(name, "publication-license-mismatch")]
        if profile == "repository":
            prefix = "skills/project-manager/"
            inner = {key[len(prefix):]: value for key, value in payload.items() if key.startswith(prefix)}
            return check_manifest(inner, "runtime")
    except (ValueError, KeyError, UnicodeError, TypeError):
        return [Finding(name, "invalid-publication-manifest")]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill", nargs="?", type=Path)
    parser.add_argument("--profile", choices=sorted(PROFILES), default="runtime")
    parser.add_argument("--public-repository", help="Explicit qualified public repository; no general personal-name exemption")
    parser.add_argument("--denylist", type=Path, help="Local UTF-8 terms file outside skill; never packaged")
    parser.add_argument("--all-files", action="store_true", help="Scan every file in a standalone unpacked snapshot")
    parser.add_argument("--history", action="store_true", help="Also audit reachable Git history; counts only")
    parser.add_argument("--require-manifest", action="store_true", help="Require export manifests when verifying a completed artifact")
    args = parser.parse_args()
    if args.skill is None:
        facade = Path(__file__).absolute().parent.parent
        args.skill = facade / "skills/project-manager" if args.profile == "runtime" else facade
    try:
        denylist = load_denylist(args.denylist, args.skill)
        payload, findings = read_snapshot(args.skill, source_paths(args.skill, args.all_files), denylist, args.profile, args.public_repository)
        findings.extend(check_manifest(payload, args.profile))
        if args.require_manifest:
            required = ["PUBLICATION-MANIFEST.json"]
            if args.profile == "repository":
                required.append("skills/project-manager/PUBLICATION-MANIFEST.json")
            findings.extend(Finding(name, "required-manifest-missing") for name in required if name not in payload)
        report = {"status": "FAIL" if findings else "PASS", "files_checked": len(payload),
                  "findings": [finding.as_dict() for finding in findings]}
        if args.history:
            report["history"] = audit_history(args.skill, denylist)
            if report["history"]["findings_by_category"]:
                report["status"] = "FAIL"
        print(json.dumps(report, indent=2, ensure_ascii=True))
        return 1 if report["status"] == "FAIL" else 0
    except PublicationError as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
