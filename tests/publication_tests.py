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

from test_support import TOOLS

from export_public_skill import MANIFEST, export_skill
from publication_check import (MAX_FILE_BYTES, PublicationError, load_denylist,
                               check_manifest, read_snapshot, scan_text, source_paths, svg_findings)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="pm-publication-test-")
        self.base = Path(self.temporary.name)
        self.root = self.base / "source"
        self.root.mkdir()
        self.write("SKILL.md", "---\nname: project-manager\nlicense: MIT\ndescription: Fictional test skill.\n---\n# Project Manager\n")
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
        self.assertEqual(set(manifest), {"schema_version", "name", "version", "distribution", "profile", "license", "files"})
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
        self.assertEqual(scan_text("README.md", "npx skills@1.6.0 add demo/project-manager"), [])

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

    def make_facade(self):
        facade = self.base / "facade"
        facade.mkdir()
        (facade / "README.md").write_text("# Public documentation\n", encoding="utf-8")
        (facade / "README.fr.md").write_text("# Documentation\n", encoding="utf-8")
        (facade / "LICENSE").write_text("Synthetic MIT license for fixture\n", encoding="utf-8")
        (facade / "docs/assets").mkdir(parents=True)
        (facade / "docs/assets/workflow.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="40"><text x="3" y="20">Workflow</text></svg>', encoding="utf-8")
        return facade

    def test_repository_export_combines_only_both_checked_surfaces(self):
        facade = self.make_facade()
        result = export_skill(self.root, self.base / "repo", self.base / "repo.zip", all_files=True,
                              profile="repository", facade=facade)
        self.assertEqual(result["status"], "PASS")
        root = self.base / "repo"
        self.assertTrue((root / "README.fr.md").is_file())
        self.assertTrue((root / "skills/project-manager/SKILL.md").is_file())
        self.assertFalse((root / "skills/project-manager/README.fr.md").exists())
        payload, findings = read_snapshot(root, source_paths(root, True), (), "repository")
        self.assertEqual(findings, [])
        self.assertEqual(check_manifest(payload, "repository"), [])
        runtime = root / "skills/project-manager"
        inner, findings = read_snapshot(runtime, source_paths(runtime, True), ())
        self.assertEqual(findings + check_manifest(inner), [])

    def test_repository_source_leak_blocks_every_output(self):
        facade = self.make_facade()
        (facade / "docs/private.md").write_text("person@" + "private-company.invalid", encoding="utf-8")
        result = export_skill(self.root, self.base / "repo", all_files=True, profile="repository", facade=facade)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse((self.base / "repo").exists())

    def test_qualified_public_repository_exception_is_narrow_and_explicit(self):
        repository = "fictional-owner/project-manager"
        denylist = ("fictional-owner",)
        public = "https://github.com/" + repository + ".git\n[badge](https://img.shields.io/github/stars/" + repository + ")"
        self.assertTrue(scan_text("README.md", public, denylist))
        self.assertEqual(scan_text("README.md", public, denylist, repository), [])
        for value in ("fictional-owner", "fictional-owner/other-project", repository + "-private", "mail@" + "fictional-owner.invalid",
                      "/home/" + "fictional-owner/project-manager"):
            self.assertTrue(scan_text("README.md", value, denylist, repository), value)
        credential = "password=" + repository
        self.assertTrue(any(item.category == "credential-assignment" for item in scan_text("README.md", credential, denylist, repository)))

    def test_runtime_rejects_marketing_tools_tests_and_svg(self):
        for path in ("README.fr.md", "tools/tool.py", "tests/check.py", "scripts/publication_check.py", "scripts/feature_tests.py",
                     "media/image.svg", ".github/workflows/ci.yml", "examples/sample.json"):
            target = self.write(path, "Synthetic distribution file")
            payload, findings = read_snapshot(self.root, ["SKILL.md", "VERSION", "LICENSE", path], ())
            self.assertTrue(findings, path)
            target.unlink()

    def test_svg_scripts_external_resources_entities_and_encoded_private_data_fail(self):
        samples = ['<svg><script>alert(1)</script></svg>', '<svg onload="run()"/>',
                   '<svg><use href="https://example.com/image.svg"/></svg>', '<svg><foreignObject/></svg>',
                   '<svg><style>text{fill:red}</style></svg>', '<!DOCTYPE svg [<!ENTITY demo "x">]><svg/>',
                   '<svg><text>private&#45;customer</text></svg>']
        for value in samples:
            self.assertTrue(svg_findings("docs/assets/workflow.svg", value, ("private-customer",)), value)
        self.assertEqual(svg_findings("docs/assets/workflow.svg", '<svg><defs><rect id="shape" width="20" height="20"/></defs><use href="#shape"/></svg>', ()), [])

    def test_canonical_registry_exception_requires_exact_public_identity(self):
        repository = "fictional-owner/project-manager"
        denylist = ("fictional-owner",)
        listing = "https://clawhub.ai/fictional-owner/skills/project-manager"
        for text in (listing, "[ClawHub](" + listing + ")", '<a href="' + listing + '">Skill</a>'):
            self.assertTrue(scan_text("README.md", text, denylist))
            self.assertEqual(scan_text("README.md", text, denylist, repository), [])
        for text in ("fictional-owner", listing + "-private", listing + "/private", listing + ".evil",
                     listing.replace("clawhub.ai", "example.com"), listing.replace("https:", "http:"),
                     "https://example.com/" + listing, listing + "?private=true"):
            self.assertTrue(scan_text("README.md", text, denylist, repository), text)
        self.assertTrue(scan_text("README.md", listing + "\n" + "/home/" + "fictional-owner", denylist, repository))

    def test_static_page_uses_only_packaged_resources_and_no_active_content(self):
        facade = self.make_facade()
        css = facade / "docs/site.css"
        css.write_text("body { color: #123; font-family: sans-serif; }", encoding="utf-8")
        html = facade / "docs/index.html"
        html.write_text('<!doctype html><html><head><link rel="stylesheet" href="site.css"></head><body><img src="assets/workflow.svg" alt="Workflow"><a href="https://example.com">Source</a></body></html>', encoding="utf-8")
        _, findings = read_snapshot(facade, source_paths(facade, True), (), "facade")
        self.assertEqual(findings, [])
        for content in ('<script>run()</script>', '<img src="https://example.com/image.svg">',
                        '<meta http-equiv="refresh" content="0;url=https://example.com">', '<img src="missing.svg">'):
            html.write_text(content, encoding="utf-8")
            self.assertTrue(read_snapshot(facade, source_paths(facade, True), (), "facade")[1])
        html.write_text('<html><body>Safe</body></html>', encoding="utf-8")
        css.write_text('@import "https://example.com/style.css";', encoding="utf-8")
        self.assertTrue(read_snapshot(facade, source_paths(facade, True), (), "facade")[1])

    def test_mit_zero_is_separate_reproducible_copy_and_never_changes_source(self):
        self.write(".bumpversion.cfg", "[bumpversion]\ncurrent_version = 1.2.3\n")
        self.write(".gitignore", "__pycache__/\n")
        original = {name: (self.root / name).read_bytes() for name in
                    ("SKILL.md", "LICENSE", ".bumpversion.cfg", ".gitignore")}
        result = export_skill(self.root, self.base / "clawhub", self.base / "clawhub.zip", all_files=True, license_override="MIT-0")
        self.assertEqual(result["license"], "MIT-0")
        output = self.base / "clawhub"
        self.assertIn("license: MIT-0", (output / "SKILL.md").read_text(encoding="utf-8"))
        self.assertIn("MIT No Attribution", (output / "LICENSE").read_text(encoding="utf-8"))
        self.assertTrue(all((self.root / name).read_bytes() == content for name, content in original.items()))
        expected = {"SKILL.md", "VERSION", "LICENSE", "docs/guide.md", MANIFEST}
        payload, findings = read_snapshot(output, source_paths(output, True), ())
        self.assertEqual(set(payload), expected)
        self.assertEqual(findings + check_manifest(payload), [])
        manifest = json.loads(payload[MANIFEST])
        self.assertEqual({record["path"] for record in manifest["files"]}, expected - {MANIFEST})
        with zipfile.ZipFile(self.base / "clawhub.zip") as bundle:
            self.assertEqual(set(bundle.namelist()), {"project-manager/" + name for name in expected})
            for name, content in payload.items():
                self.assertEqual(bundle.read("project-manager/" + name), content)
        export_skill(self.root, self.base / "again", self.base / "again.zip", all_files=True, license_override="MIT-0")
        self.assertEqual((self.base / "clawhub.zip").read_bytes(), (self.base / "again.zip").read_bytes())
        facade = self.make_facade()
        with self.assertRaises(PublicationError):
            export_skill(self.root, self.base / "repo", all_files=True, profile="repository", facade=facade, license_override="MIT-0")

    def test_mit_runtime_and_repository_keep_development_dotfiles(self):
        expected = {".bumpversion.cfg": "[bumpversion]\ncurrent_version = 1.2.3\n",
                    ".gitignore": "__pycache__/\n"}
        originals = {name: self.write(name, text).read_bytes() for name, text in expected.items()}
        facade = self.make_facade()
        for profile in ("runtime", "repository"):
            output = self.base / profile
            result = export_skill(self.root, output, all_files=True, profile=profile,
                                  facade=facade if profile == "repository" else None)
            self.assertEqual(result["license"], "MIT")
            runtime = output / "skills/project-manager" if profile == "repository" else output
            for name, content in originals.items():
                self.assertEqual((runtime / name).read_bytes(), content)
            payload, findings = read_snapshot(output, source_paths(output, True), (), profile)
            self.assertEqual(findings + check_manifest(payload, profile), [])

    def test_clawhub_omitted_dotfiles_still_receive_privacy_review(self):
        for name in (".bumpversion.cfg", ".gitignore"):
            with self.subTest(name=name):
                self.write(name, "person@" + "private-company.invalid")
                output = self.base / "clawhub"
                result = export_skill(self.root, output, all_files=True, license_override="MIT-0")
                self.assertEqual(result["status"], "FAIL")
                self.assertFalse(output.exists())
                (self.root / name).unlink()

    def test_manifest_license_claim_must_match_skill(self):
        self.export()
        root = self.base / "distribution"
        payload, _ = read_snapshot(root, source_paths(root, True), ())
        manifest = json.loads(payload[MANIFEST])
        manifest["license"] = "MIT-0"
        payload[MANIFEST] = json.dumps(manifest).encode()
        self.assertTrue(check_manifest(payload))

    def test_archive_publish_failure_rolls_back_new_directory(self):
        from export_public_skill import rename_exclusive
        def fail_archive(source, target):
            if target.suffix == ".zip":
                raise OSError("Synthetic archive publication failure")
            return rename_exclusive(source, target)
        with patch("export_public_skill.rename_exclusive", side_effect=fail_archive):
            with self.assertRaises(PublicationError):
                self.export(archive=self.base / "archive.zip")
        self.assertFalse((self.base / "distribution").exists())
        self.assertFalse((self.base / "archive.zip").exists())

    def test_atomic_publication_waits_until_every_file_is_ready(self):
        from export_public_skill import rename_exclusive
        output = self.base / "distribution"
        def check_and_rename(source, target):
            self.assertFalse(output.exists())
            self.assertTrue((source / MANIFEST).is_file())
            self.assertTrue((source / "docs/guide.md").is_file())
            return rename_exclusive(source, target)
        with patch("export_public_skill.rename_exclusive", side_effect=check_and_rename):
            self.export()
        self.assertTrue(output.is_dir())

    def test_competing_destination_is_preserved_without_overwrite(self):
        from export_public_skill import rename_exclusive
        output = self.base / "distribution"
        def compete(source, target):
            output.mkdir()
            (output / "keep.txt").write_text("Competitor content", encoding="utf-8")
            return rename_exclusive(source, target)
        with patch("export_public_skill.rename_exclusive", side_effect=compete):
            with self.assertRaises(PublicationError):
                self.export()
        self.assertEqual((output / "keep.txt").read_text(encoding="utf-8"), "Competitor content")
        self.assertFalse((output / "SKILL.md").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
