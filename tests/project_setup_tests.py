#!/usr/bin/env python3
"""Behavioral regression tests for portable, reviewable project initialization."""

from test_support import SCRIPTS

import argparse
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import bootstrap_project as bootstrap
import project_setup as setup


class ProjectSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.raw = {
            "schema_version": 1,
            "project": {"title": "Demo", "slug": "demo", "path": "projects/demo", "archetype": "embedded",
                        "objective": "Demonstrate controlled development", "in_scope": ["Firmware"], "owners": ["system-owner"]},
            "infrastructure": {"git_backend": "gitlab", "repository": "example/demo", "host": "gitlab.example.test",
                               "protocol": "ssh", "ssh_host": "git-remote", "credential_refs": ["env:PROJECT_GIT_TOKEN"]},
            "delegation": {"enabled": True, "agents": [{"label": "builder", "role": "SWE", "worker": "worker-a"}],
                           "writable_paths": ["03-development/software"]},
        }

    def tearDown(self):
        self.temp.cleanup()

    def config(self):
        return setup.validate_config(self.raw, self.root)

    def write_config(self, data=None):
        path = self.root / "setup.json"
        path.write_text(json.dumps(self.raw if data is None else data), encoding="utf-8")
        return path

    def test_defaults_archetype_ssh_and_stable_fingerprint(self):
        config = self.config()
        self.assertEqual(str(self.root / "projects" / "demo"), config["project"]["path"])
        self.assertEqual("private", config["infrastructure"]["visibility"])
        args = argparse.Namespace(**setup.to_bootstrap_args(config))
        self.assertEqual("git@git-remote:example/demo.git", bootstrap.expected_remote_url(args, {"host": "gitlab.example.test"}))
        self.assertEqual(setup.fingerprint(config), setup.fingerprint(setup.validate_config(config)))
        changed = copy.deepcopy(config)
        changed["infrastructure"]["visibility"] = "public"
        self.assertNotEqual(setup.fingerprint(config), setup.fingerprint(changed))
        self.assertEqual(["SYS", "SWE", "HWE"], bootstrap.ARCHETYPES["embedded"])

    def test_malformed_and_secret_configuration_rejected(self):
        invalid = [
            ("schema_version", False),
            ("project.in_scope", "not a list"), ("project.slug", "../escape"),
            ("project.owners", []), ("project.add_domains", ["UNKNOWN"]),
            ("infrastructure.token", "secret"), ("infrastructure.host", "user:secret" + "@" + "example.invalid"),
            ("infrastructure.repository", "--flag"), ("infrastructure.default_branch", "bad..branch"),
            ("infrastructure.credential_refs", ["plain-secret"]),
            ("infrastructure.drive_url", "https://drive.google.com:bad/file"),
            ("infrastructure.drive_url", "https://" + "user:secret" + "@" + "drive.google.com/file"),
            ("delegation.enabled", "yes"), ("delegation.max_attempts", 0), ("delegation.max_parallel", 4),
            ("delegation.writable_paths", ["../../escape"]), ("delegation.agents", []),
            ("delegation.agents", [{"label": "x", "role": "SWE", "worker": "worker"}] * 2),
        ]
        for location, value in invalid:
            with self.subTest(location=location):
                data = copy.deepcopy(self.raw)
                keys = location.split(".")
                obj = data
                for key in keys[:-1]:
                    obj = obj[key]
                obj[keys[-1]] = value
                with self.assertRaises(setup.SetupError):
                    setup.validate_config(data, self.root)
        for malformed in ([], None, {"schema_version": 1}):
            with self.assertRaises(setup.SetupError):
                setup.validate_config(malformed)

    def test_questionnaire_skips_known_values_and_captures_missing(self):
        config = self.config()
        with patch("builtins.input", side_effect=AssertionError("unexpected question")):
            same = setup.questionnaire(config, ask=lambda _: self.fail("Known configuration asked again"))
        self.assertEqual(config, same)
        del config["project"]["objective"]
        questions = []
        result = setup.questionnaire(config, ask=lambda question: questions.append(question) or "New objective")
        self.assertEqual("New objective", result["project"]["objective"])
        self.assertEqual(1, len(questions))

    def test_dry_run_and_missing_approval_never_call_preflight_or_write(self):
        path = self.write_config()
        with patch.object(bootstrap, "robust_preflight", side_effect=AssertionError("Network called")):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                bootstrap.main(["--config", str(path), "--dry-run"])
            plan = json.loads(output.getvalue())
            self.assertIn("NOT_RUN", plan["infrastructure_check"])
            self.assertEqual(setup.fingerprint(self.config()), plan["approval_sha256"])
            for extra in ([], ["--approve-config", "invalid"]):
                with self.assertRaises(bootstrap.BootstrapError):
                    bootstrap.main(["--config", str(path), *extra])
        self.assertFalse((self.root / "projects").exists())

    def test_matching_approval_reaches_preflight_and_preflight_does_not_setup_credentials(self):
        path = self.write_config()
        with patch.object(bootstrap, "robust_preflight", side_effect=RuntimeError("preflight reached")):
            with self.assertRaisesRegex(RuntimeError, "preflight reached"):
                bootstrap.main(["--config", str(path), "--approve-config", setup.fingerprint(self.config())])
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="workflow", stderr="")
        with patch.object(bootstrap, "run", side_effect=run), patch.object(bootstrap, "command_exists", return_value=True), patch.object(bootstrap, "network_check"):
            backend = bootstrap.github_preflight()
        self.assertEqual("github", backend["backend"])
        self.assertEqual([["gh", "auth", "status", "-h", "github.com"]], calls)

    def test_gitlab_transport_checks_same_ssh_identity_as_remote(self):
        args = argparse.Namespace(**setup.to_bootstrap_args(self.config()))
        result = subprocess.CompletedProcess([], 0, stdout="Welcome to GitLab", stderr="")
        with patch.object(bootstrap, "run", return_value=result) as run, contextlib.redirect_stdout(io.StringIO()):
            bootstrap.gitlab_transport_preflight(args)
        self.assertEqual(["-T", "git@git-remote"], run.call_args.args[0][-2:])

    def test_config_rejects_overrides_and_malformed_json_cleanly(self):
        path = self.write_config()
        with self.assertRaises(bootstrap.BootstrapError):
            bootstrap.parse_args(["--config", str(path), "--visibility", "public"])
        path.write_text('{"secret":"unterminated', encoding="utf-8")
        result = subprocess.run([sys.executable, str(Path(bootstrap.__file__)), "--config", str(path), "--dry-run"],
                                text=True, capture_output=True)
        self.assertNotEqual(0, result.returncode)
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        self.assertNotIn("unterminated", result.stdout + result.stderr)

    def test_legacy_flags_keep_dry_run_and_explicit_path(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            bootstrap.main(["--title", "Legacy", "--slug", "legacy", "--archetype", "desktop", "--git-backend", "github",
                            "--repo", "example/legacy", "--project-dir", str(self.root / "legacy"), "--dry-run"])
        plan = json.loads(output.getvalue())
        self.assertEqual(["SWE"], plan["domains"])
        self.assertEqual(str(self.root / "legacy"), plan["project"])
        self.assertFalse((self.root / "legacy").exists())

    def test_resume_preserves_registries_templates_audits_and_ci(self):
        config = self.config()
        args = argparse.Namespace(**setup.to_bootstrap_args(config), setup_config=config)
        project = Path(args.project_dir)
        backend = {"backend": "gitlab", "profile": "GITLAB_SELF_MANAGED", "host": "gitlab.example.test", "ci_runner_tags": []}
        with contextlib.redirect_stdout(io.StringIO()):
            bootstrap.initialize_structure(project, args, {}, backend, ["SYS", "SWE", "HWE"])
        ci = (project / ".gitlab-ci.yml").read_text(encoding="utf-8")
        self.assertIn("configuration_audit.py", ci)
        self.assertNotIn("tags:", ci)
        protected = {
            "08-configuration/CHANGE-REQUESTS.json": '{"next_number": 7, "changes": [{"id":"CR-006"}]}\n',
            "08-configuration/BASELINE-REGISTRY.json": '{"next_number": 3, "baselines": []}\n',
            "05-verification/EVIDENCE.json": '{"next_number": 4, "evidence": []}\n',
            "00-project/PROJECT.md": "# User-edited project\n",
            "tools/project-audit/project_audit.py": "# Local controlled tooling\n",
            ".gitlab-ci.yml": ci + "# Reviewed local CI adjustment\n",
        }
        for relative, content in protected.items():
            (project / relative).write_text(content, encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            bootstrap.initialize_structure(project, args, {}, backend, ["SYS", "SWE", "HWE"])
        for relative, content in protected.items():
            self.assertEqual(content, (project / relative).read_text(encoding="utf-8"))
        stored = json.loads((project / "00-project/PROJECT-SETUP.json").read_text(encoding="utf-8"))
        self.assertNotIn("path", stored["project"])
        self.assertEqual("builder", stored["delegation"]["agents"][0]["label"])

    def test_resume_rejects_changed_configuration_and_skips_passed_step(self):
        summary = {"slug": "demo", "git_backend": "gitlab", "git_host": "gitlab.example.test", "repository": "example/demo",
                   "domains": ["SWE"], "default_branch": "main", "setup_sha256": "old"}
        state = bootstrap.new_state(summary, {"profile": "GITLAB_SELF_MANAGED"})
        with self.assertRaises(bootstrap.BootstrapError):
            bootstrap.validate_resume(state, dict(summary, default_branch="different"))
        with self.assertRaises(bootstrap.BootstrapError):
            bootstrap.validate_resume(state, dict(summary, setup_sha256="new"))
        state["steps"]["structure"]["status"] = "PASS"
        with contextlib.redirect_stdout(io.StringIO()):
            bootstrap.execute_step(self.root, state, "structure", lambda: self.fail("Repeated passed step"))

    def test_interrupted_template_generation_resumes_with_all_management_registries(self):
        from management_audit import MARKER, MODELS, audit
        templates = self.root / "templates"
        shutil.copytree(bootstrap.TEMPLATES, templates)
        missing = templates / "PROCESS-SCOPE.md"
        missing.unlink()
        config = self.config()
        args = argparse.Namespace(**setup.to_bootstrap_args(config), setup_config=config)
        project = Path(args.project_dir)
        backend = {"backend": "gitlab", "profile": "GITLAB_SELF_MANAGED", "host": "gitlab.example.test"}
        with patch.object(bootstrap, "TEMPLATES", templates), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(bootstrap.BootstrapError):
                bootstrap.initialize_structure(project, args, {}, backend, ["SYS", "SWE", "HWE"])
            project_file = project / "00-project/PROJECT.md"
            self.assertTrue(project_file.is_file())
            project_file.write_text("# Preserved partial project\n", encoding="utf-8")
            shutil.copy2(bootstrap.PM / "templates/PROCESS-SCOPE.md", missing)
            bootstrap.initialize_structure(project, args, {}, backend, ["SYS", "SWE", "HWE"])
        self.assertEqual("# Preserved partial project\n", project_file.read_text(encoding="utf-8"))
        self.assertTrue((project / MARKER).is_file(), "A failed template copy lost new-project management activation")
        for _, relative, _, _ in MODELS:
            self.assertTrue((project / relative).is_file())
        self.assertEqual(([], []), audit(project))

    def test_explicit_management_opt_in_preserves_records_and_legacy_documents(self):
        import management_init
        import risk_manager
        from management_audit import MARKER, MODELS, audit
        from management_common import RecordError
        project = self.root / "legacy"
        project.mkdir()
        old = project / "09-risks/RISK-REGISTER.md"
        old.parent.mkdir()
        old.write_text("# Existing manual risk assessment\n", encoding="utf-8")
        before = old.read_bytes()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, risk_manager.main(["--project", str(project), "init", "--actor", "coordinator"]))
            self.assertEqual(0, risk_manager.main(["--project", str(project), "create", "--actor", "coordinator",
                                                  "--title", "Existing risk", "--owner", "systems", "--description", "Existing assessed exposure",
                                                  "--probability", "1", "--impact", "2"]))
        prior_risks = (project / risk_manager.REGISTRY).read_bytes()
        management_init.initialize(project, "coordinator")
        self.assertEqual(prior_risks, (project / risk_manager.REGISTRY).read_bytes())
        self.assertEqual(before, old.read_bytes())
        authoritative = {relative: (project / relative).read_bytes() for _, relative, _, _ in MODELS}
        authoritative[MARKER] = (project / MARKER).read_bytes()
        management_init.initialize(project, "coordinator")
        self.assertTrue(all(content == (project / relative).read_bytes() for relative, content in authoritative.items()))
        self.assertEqual(([], []), audit(project))
        (project / "07-quality/PROBLEMS.json").unlink()
        with self.assertRaises(RecordError):
            management_init.initialize(project, "coordinator")
        self.assertFalse((project / "07-quality/PROBLEMS.json").exists())
        self.assertTrue(audit(project)[0])

    def test_invalid_existing_management_registry_prevents_partial_opt_in(self):
        import management_init
        from management_audit import MARKER
        from management_common import RecordError
        project = self.root / "invalid-legacy"
        (project / "09-risks").mkdir(parents=True)
        registry = project / "09-risks/RISKS.json"
        registry.write_text('{"records":', encoding="utf-8")
        before = {path.relative_to(project): path.read_bytes() for path in project.rglob("*") if path.is_file()}
        with self.assertRaises(RecordError):
            management_init.initialize(project, "coordinator")
        self.assertFalse((project / MARKER).exists())
        after = {path.relative_to(project): path.read_bytes() for path in project.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_legacy_partial_bootstrap_does_not_silently_enable_new_registries(self):
        from management_audit import MARKER, MODELS, audit
        config = self.config()
        args = argparse.Namespace(**setup.to_bootstrap_args(config), setup_config=None)
        project = Path(args.project_dir)
        project_file = project / "00-project/PROJECT.md"
        project_file.parent.mkdir(parents=True)
        project_file.write_text("# Legacy partial bootstrap\n", encoding="utf-8")
        backend = {"backend": "gitlab", "profile": "GITLAB_SELF_MANAGED", "host": "gitlab.example.test"}
        with contextlib.redirect_stdout(io.StringIO()):
            bootstrap.initialize_structure(project, args, {}, backend, ["SYS", "SWE", "HWE"])
        self.assertEqual("# Legacy partial bootstrap\n", project_file.read_text(encoding="utf-8"))
        self.assertFalse((project / MARKER).exists())
        self.assertTrue(all(not (project / relative).exists() for _, relative, _, _ in MODELS))
        self.assertEqual(([], []), audit(project))

    def test_relocated_skill_generates_self_contained_audits(self):
        relocated = self.root / "portable-skill"
        shutil.copytree(bootstrap.PM, relocated, ignore=shutil.ignore_patterns("__pycache__"))
        project = self.root / "generated"
        config = self.config()
        config["project"]["path"] = str(project)
        config_path = self.write_config(config)
        code = ("import sys; from pathlib import Path; from argparse import Namespace; "
                "sys.path.insert(0, sys.argv[1]); import bootstrap_project as b; import project_setup as s; "
                "config=s.load_config(sys.argv[3]); args=Namespace(**s.to_bootstrap_args(config), setup_config=config); "
                "b.check_templates(['SYS','SWE','HWE']); "
                "b.initialize_structure(Path(sys.argv[2]), args, {}, "
                "{'backend':'gitlab','profile':'GITLAB_SELF_MANAGED','host':'gitlab.example.test'}, ['SYS','SWE','HWE']); print(b.PM)")
        result = subprocess.run([sys.executable, "-c", code, str(relocated / "scripts"), str(project), str(config_path)],
                                text=True, capture_output=True, cwd=self.root)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn(str(relocated), result.stdout)
        self.assertTrue(relocated.resolve().is_relative_to(self.root.resolve()))
        shutil.rmtree(relocated)
        tools = ["project_audit.py", "requirements_lint.py", "traceability_check.py", "delegation_plan.py",
                 "project_report.py", "migration_assess.py", "management_init.py", "management_audit.py",
                 "risk_manager.py", "problem_manager.py", "milestone_manager.py", "intake_manager.py", "compliance_manager.py"]
        # Mutating registry engines depend on POSIX fcntl; Linux integration exercises them.
        if os.name != "nt":
            tools += ["configuration_audit.py", "release_check.py"]
        for tool in tools:
            result = subprocess.run([sys.executable, str(project / "tools/project-audit" / tool), "--help"],
                                    text=True, capture_output=True, cwd=self.root)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        copied = project / "tools/project-audit"
        result = subprocess.run([sys.executable, str(copied / "management_init.py"), str(project), "--actor", "coordinator"],
                                text=True, capture_output=True, cwd=self.root)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        result = subprocess.run([sys.executable, str(copied / "risk_manager.py"), "--project", str(project), "create",
                                 "--actor", "coordinator", "--owner", "systems", "--title", "Portable risk",
                                 "--description", "Risk retained after skill removal", "--probability", "1", "--impact", "2"],
                                text=True, capture_output=True, cwd=self.root)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        result = subprocess.run([sys.executable, str(copied / "management_audit.py"), str(project), "--json"],
                                text=True, capture_output=True, cwd=self.root)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual([], json.loads(result.stdout)["errors"])
        result = subprocess.run([sys.executable, str(copied / "migration_assess.py"), str(project), "--json"],
                                text=True, capture_output=True, cwd=self.root)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        registry_summary = json.loads(result.stdout)["management_extensions"]["registries"]
        self.assertEqual(1, registry_summary["risks"]["total"])
        self.assertTrue(all(item["enabled"] for item in registry_summary.values()))
        if os.name != "nt":
            def command(*arguments):
                result = subprocess.run(list(arguments), text=True, capture_output=True, cwd=project)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                return result.stdout
            engine = str(project / "tools/project-audit/project_state.py")
            command(sys.executable, engine, "init", ".", "--title", "Demo", "--slug", "demo")
            command(sys.executable, engine, "add", ".", "--id", "TASK-001", "--title", "Build firmware",
                    "--acceptance", "Tests pass", "--output", "03-development/software/firmware.py")
            command(sys.executable, engine, "refresh", ".")
            command("git", "init", "-b", "main")
            command("git", "add", "--", "00-project/PROJECT-SETUP.json", "00-project/management/TASKS.json")
            command("git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "Fixture")
            planner = str(project / "tools/project-audit/delegation_plan.py")
            contract = json.loads(command(sys.executable, planner, ".", "TASK-001", "--agent", "builder",
                                          "--write-path", "03-development/software"))
            self.assertFalse(contract["dispatched"])
            self.assertEqual("builder", contract["agent"]["label"])
            self.assertEqual(["03-development/software/firmware.py"], contract["expected_outputs"])
            result = subprocess.run([sys.executable, str(copied / "project_report.py"), str(project), "--json"],
                                    text=True, capture_output=True, cwd=self.root)
            self.assertIn(result.returncode, (0, 1), result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(1, report["management"]["registries"]["risks"]["total"])
            self.assertEqual("NOT_EVALUATED", report["release_readiness"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
