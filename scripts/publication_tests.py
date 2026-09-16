#!/usr/bin/env python3
"""Behavior tests for privacy checks and clean distribution export."""

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from export_public_skill import MANIFEST, export_skill
from publication_check import (MAX_FILE_BYTES, PublicationError, load_denylist,
                               check_manifest, read_snapshot, scan_text, source_paths)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="pm-publication-test-")
        self.base = Path(self.temporary.name)
        self.root = self.base / "source"
        self.root.mkdir()
        self.write("SKILL.md", "---\nname: project-manager\ndescription: Fictional test skill.\n---\n# Project Manager\n")
        self.write("VERSION", "1.2.3\n")
        self.write("LICENSE", "Synthetic license for temporary test fixtures only.\n")
        self.write("docs/guide.md", "# Guide\nUse placeholders.\n")

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, name, text):
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return target

    def git(self, *arguments):
        subprocess.run(["git", "-C", str(self.root), *arguments], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def check(self):
        return read_snapshot(self.root, source_paths(self.root, True), ())

    def export(self, name="distribution", archive=None, denylist=None, all_files=True):
        return export_skill(self.root, self.base / name, archive, denylist, all_files)

    def test_clean_export_and_manifest_and_unpacked_scan(self):
        archive = self.base / "release.zip"
        result = self.export(archive=archive)
        self.assertEqual(result["status"], "PASS")
        exported = self.base / "distribution"
        manifest = json.loads((exported / MANIFEST).read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], "1.2.3")
        self.assertNotIn(str(self.root), json.dumps(manifest))
        self.assertEqual(set(manifest), {"schema_version", "name", "version", "distribution", "files"})
        for record in manifest["files"]:
            content = (exported / record["path"]).read_bytes()
            self.assertEqual(hashlib.sha256(content).hexdigest(), record["sha256"])
            self.assertEqual(len(content), record["bytes"])
        unpacked = self.base / "unpacked"
        with zipfile.ZipFile(archive) as bundle:
            self.assertTrue(all(name.startswith("project-manager/") for name in bundle.namelist()))
            self.assertFalse(any(".git/" in name for name in bundle.namelist()))
            bundle.extractall(unpacked)
        snapshot = unpacked / "project-manager"
        payload, findings = read_snapshot(snapshot, source_paths(snapshot, True), ())
        self.assertEqual(findings, [])
        self.assertEqual(check_manifest(payload), [])

    def test_manifest_detects_changed_missing_extra_or_malformed_content(self):
        self.export()
        snapshot = self.base / "distribution"
        payload, _ = read_snapshot(snapshot, source_paths(snapshot, True), ())
        for change in ("changed", "missing", "extra", "malformed"):
            altered = dict(payload)
            if change == "changed":
                altered["docs/guide.md"] = b"Changed harmless text"
            elif change == "missing":
                altered.pop("docs/guide.md")
            elif change == "extra":
                altered["docs/extra.md"] = b"Extra harmless file"
            else:
                altered[MANIFEST] = b"{bad-json"
            self.assertTrue(check_manifest(altered), change)

    def test_deterministic_archive(self):
        first = self.base / "first.zip"
        second = self.base / "second.zip"
        self.export("first", first)
        self.export("second", second)
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_only_git_tracked_files_are_exported(self):
        self.git("init", "-q")
        self.git("add", ".")
        self.write("memory/private.md", "Private runtime data")
        self.write("docs/untracked.md", "Untracked work")
        self.assertEqual(self.export(all_files=False)["status"], "PASS")
        exported = self.base / "distribution"
        self.assertFalse((exported / ".git").exists())
        self.assertFalse((exported / "memory").exists())
        self.assertFalse((exported / "docs/untracked.md").exists())

    def test_scan_secrets_private_information_and_redaction(self):
        samples = {
            "service-token": "glpat-" + "SyntheticPrivateValue12345",
            "private-key": "-----BEGIN " + "PRIVATE KEY-----",
            "personal-path": "/home/" + "private-user/project",
            "personal-email": "person@" + "private-company.invalid",
            "private-hostname": "private-host." + "local",
            "private-network-address": ".".join(("192", "168", "12", "4")),
            "credential-url": "https://" + "user:private-password@host.example",
            "credential-assignment": "password" + " = " + "synthetic-secret-value",
        }
        for category, value in samples.items():
            with self.subTest(category=category):
                findings = scan_text("docs/guide.md", value)
                self.assertIn(category, {finding.category for finding in findings})
                self.assertNotIn(value, json.dumps([item.as_dict() for item in findings]))
        self.assertEqual(scan_text("docs/test.md", "person@example.com\nperson@host.example\ntest@example.invalid"), [])

    def test_local_denylist_and_redacted_paths(self):
        denylist = self.base / "local-terms.txt"
        denylist.write_text("# local only\nConfidentialCustomer\n", encoding="utf-8")
        self.write("docs/ConfidentialCustomer.md", "ConfidentialCustomer project")
        result = self.export(denylist=denylist)
        self.assertEqual(result["status"], "FAIL")
        self.assertNotIn("ConfidentialCustomer", json.dumps(result))
        self.assertFalse((self.base / "distribution").exists())

    def test_denylist_cannot_be_packaged_or_unreadable(self):
        inside = self.write("docs/denylist.txt", "private-name")
        with self.assertRaises(PublicationError):
            load_denylist(inside, self.root)
        with self.assertRaises(PublicationError):
            load_denylist(self.base / "missing.txt", self.root)

    def test_runtime_and_backup_files_fail(self):
        for relative in ("workspace/data.md", "memory/data.md", "scripts/__pycache__/module.pyc",
                         "private/notes.md", "docs/file.bak", ".env", "PM_MASTER_PROMPT.txt"):
            with self.subTest(relative=relative):
                target = self.write(relative, "Should never ship")
                _, findings = self.check()
                self.assertTrue(findings)
                target.unlink()

    def test_unsupported_binary_invalid_utf8_and_size_limit_fail(self):
        for content in (b"bad\x00binary", b"bad\xffutf8", b"x" * (MAX_FILE_BYTES + 1)):
            (self.root / "docs/guide.md").write_bytes(content)
            self.assertEqual(self.export()["status"], "FAIL")
            self.assertFalse((self.base / "distribution").exists())
        self.write("docs/guide.md", "clean")
        self.write("docs/image.png", "pretend binary")
        self.assertEqual(self.export()["status"], "FAIL")

    def test_existing_outputs_are_never_overwritten(self):
        self.export()
        with self.assertRaises(PublicationError):
            self.export()
        archive = self.base / "existing.zip"
        archive.write_bytes(b"original")
        with self.assertRaises(PublicationError):
            self.export("new", archive)
        self.assertEqual(archive.read_bytes(), b"original")
        self.assertFalse((self.base / "new").exists())

    def test_output_must_stay_outside_source(self):
        with self.assertRaises(PublicationError):
            export_skill(self.root, self.root / "exported", all_files=True)
        with self.assertRaises(PublicationError):
            export_skill(self.root, self.base / "distribution", self.root / "release.zip", all_files=True)
        self.assertFalse((self.root / "exported").exists())

    def test_relative_path_traversal_is_rejected(self):
        _, findings = read_snapshot(self.root, ["../outside.md", "C:/outside.md", "SKILL.md", "VERSION"], ())
        self.assertEqual(sum(item.category == "unsafe-path" for item in findings), 2)

    def test_symlink_source_is_rejected(self):
        external = self.base / "outside.md"
        external.write_text("Private outside content", encoding="utf-8")
        link = self.root / "docs/link.md"
        try:
            link.symlink_to(external)
        except OSError:
            self.skipTest("host does not permit symlink creation")
        self.assertEqual(self.export()["status"], "FAIL")
        self.assertFalse((self.base / "distribution").exists())

    def test_git_symlink_entries_fail_even_without_os_link_support(self):
        self.git("init", "-q")
        self.git("add", ".")
        result = subprocess.run(["git", "-C", str(self.root), "hash-object", "-w", "--stdin"],
                                input=b"../outside.md", check=True, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        oid = result.stdout.decode("ascii").strip()
        self.git("update-index", "--add", "--cacheinfo", "120000," + oid + ",docs/link.md")
        with self.assertRaises(PublicationError):
            source_paths(self.root)

    def test_private_filename_is_never_echoed(self):
        relative = "docs/" + "person@" + "private-company.invalid.md"
        self.write(relative, "Private filename")
        _, findings = self.check()
        self.assertTrue(findings)
        self.assertNotIn(relative, json.dumps([finding.as_dict() for finding in findings]))

    def test_symlink_directory_is_rejected(self):
        outside = self.base / "outside"
        outside.mkdir()
        link = self.root / "templates"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("host does not permit symlink creation")
        self.assertEqual(self.export()["status"], "FAIL")

    def test_symlink_destination_ancestor_is_rejected(self):
        outside = self.base / "outside"
        outside.mkdir()
        link = self.base / "linked"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("host does not permit symlink creation")
        with self.assertRaises(PublicationError):
            export_skill(self.root, link / "exported", all_files=True)

    def test_scanner_errors_fail_closed_without_writing(self):
        with patch("export_public_skill.source_paths", side_effect=PublicationError("synthetic failure")):
            with self.assertRaises(PublicationError):
                self.export()
        self.assertFalse((self.base / "distribution").exists())

    def test_missing_version_or_invalid_version_fails(self):
        self.write("VERSION", "not a version")
        with self.assertRaises(PublicationError):
            self.export()
        (self.root / "VERSION").unlink()
        self.assertEqual(self.export()["status"], "FAIL")

    def test_public_export_requires_a_license(self):
        (self.root / "LICENSE").unlink()
        with self.assertRaises(PublicationError):
            self.export()

    def test_partial_write_cleanup_preserves_unrelated_files(self):
        unrelated = self.base / "unrelated.txt"
        unrelated.write_text("keep", encoding="utf-8")
        original_open = Path.open
        def fail_on_guide(path, *args, **kwargs):
            if path.name == "guide.md" and args and args[0] == "xb":
                raise OSError("synthetic write failure")
            return original_open(path, *args, **kwargs)
        with patch.object(Path, "open", fail_on_guide):
            with self.assertRaises(PublicationError):
                self.export()
        self.assertFalse((self.base / "distribution").exists())
        self.assertEqual(unrelated.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main(verbosity=2)
