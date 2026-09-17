#!/usr/bin/env python3
"""Verify a copied skill installation against the canonical runtime on Linux.

Only reads the installation: compare every non-cache file and directory, check
the package, then execute five real entry points with --help. No project is
created. An installation must be a separate directory, not a symlink.
"""

import argparse
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import sys


HELP_SCRIPTS = (
    "bootstrap_project.py", "project_setup.py", "project_state.py",
    "management_init.py", "release_check.py",
)
CACHE_DIRECTORIES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


class InstallationError(ValueError):
    pass


def inventory(root):
    """Return file hashes and directory names, rejecting links and special files."""
    root = Path(root).expanduser().absolute()
    if root.is_symlink():
        raise InstallationError(f"symlink root is not a copied installation: {root}")
    if not root.is_dir():
        raise InstallationError(f"runtime directory does not exist: {root}")
    files, directories = {}, set()

    def walk_error(error):
        raise error

    for current, children, names in os.walk(root, followlinks=False, onerror=walk_error):
        current = Path(current)
        for name in children + names:
            path = current / name
            relative = path.relative_to(root).as_posix()
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise InstallationError(f"symlink is not allowed: {relative}")
            if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                raise InstallationError(f"special file is not allowed: {relative}")
        children.sort()
        in_cache = any(part in CACHE_DIRECTORIES for part in current.relative_to(root).parts)
        for name in children:
            if not in_cache and name not in CACHE_DIRECTORIES:
                directories.add((current / name).relative_to(root).as_posix())
        for name in sorted(names):
            if in_cache or name.endswith((".pyc", ".pyo")):
                continue
            path = current / name
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            files[path.relative_to(root).as_posix()] = digest.hexdigest()
    if not files:
        raise InstallationError(f"runtime is empty: {root}")
    return files, directories


def compare_inventory(expected, installed):
    expected_files, expected_dirs = expected
    actual_files, actual_dirs = installed
    errors = []
    for kind, source, target in (("file", expected_files, actual_files),
                                 ("directory", expected_dirs, actual_dirs)):
        errors.extend(f"missing {kind}: {name}" for name in sorted(set(source) - set(target)))
        errors.extend(f"unexpected {kind}: {name}" for name in sorted(set(target) - set(source)))
    errors.extend(f"SHA256 mismatch: {name}" for name in sorted(expected_files.keys() & actual_files.keys())
                  if expected_files[name] != actual_files[name])
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("installed", type=Path, help="Copied skill runtime directory to verify")
    parser.add_argument("--skill-root", type=Path,
                        default=Path(__file__).resolve().parent.parent / "skills/project-manager",
                        help="Canonical runtime (default: skills/project-manager in the public checkout)")
    args = parser.parse_args(argv)
    if sys.platform != "linux":
        parser.error("Installation smoke checks require a real Linux Python interpreter")
    canonical = args.skill_root.expanduser().absolute()
    installed = args.installed.expanduser().absolute()
    try:
        expected = inventory(canonical)
        actual = inventory(installed)
        if os.path.samefile(canonical, installed):
            raise InstallationError("canonical runtime and installation must be separate directories")
        errors = compare_inventory(expected, actual)
        if errors:
            for error in errors:
                print(f"FAIL: {error}")
            return 1
        print(f"PASS: installation matches {len(expected[0])} files by SHA256", flush=True)
        checker = Path(__file__).resolve().parent / "skill_package_check.py"
        checks = [("installed package", [sys.executable, "-B", str(checker), str(installed)])]
        checks += [(f"{name} --help", [sys.executable, "-B", str(installed / "scripts" / name), "--help"])
                   for name in HELP_SCRIPTS]
        env = {key: value for key, value in os.environ.items()
               if key not in {"PYTHONPATH", "PYTHONHOME", "PM_SKILL_ROOT"}}
        env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
        for label, command in checks:
            result = subprocess.run(command, cwd=installed, env=env, capture_output=True,
                                    text=True, encoding="utf-8", timeout=30)
            if result.returncode:
                print(f"FAIL: {label}\n{result.stdout}{result.stderr}")
                return 1
            print(f"PASS: {label}", flush=True)
        if inventory(installed) != actual:
            raise InstallationError("installation changed during read-only smoke checks")
    except (InstallationError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("INSTALL SMOKE: PASS", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
