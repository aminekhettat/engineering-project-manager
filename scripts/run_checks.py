#!/usr/bin/env python3
"""Run the shipped behavioral tests and package checks from any installation."""

import argparse
import os
from pathlib import Path
import subprocess
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs", type=Path, help="Optional private log directory outside the skill")
    args = parser.parse_args(argv)
    scripts = Path(__file__).resolve().parent
    skill = scripts.parent
    if sys.platform != "linux":
        print("ERROR: Full runtime validation requires Linux/POSIX file locks.", file=sys.stderr)
        return 2
    if args.logs:
        logs = args.logs.resolve()
        if logs == skill or logs.is_relative_to(skill):
            parser.error("Keep validation logs outside the distributable skill")
        logs.mkdir(parents=True, exist_ok=True)
    test_files = sorted(set(scripts.glob("*_tests.py")) | set(scripts.glob("*_test.py")))
    # Syntax-check without adding bytecode caches to a standalone release.
    compile_code = "import pathlib,sys; [compile(p.read_bytes(),str(p),'exec') for p in pathlib.Path(sys.argv[1]).glob('*.py')]"
    checks = [("compile", [sys.executable, "-B", "-c", compile_code, str(scripts)])]
    checks += [(path.stem, [sys.executable, str(path)]) for path in test_files]
    checks += [
        ("package", [sys.executable, str(scripts / "skill_package_check.py"), str(skill)]),
        ("self_check", [sys.executable, str(scripts / "project_manager_self_check.py")]),
    ]
    failures = []
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    for name, command in checks:
        print(f"RUN: {name}", flush=True)
        try:
            result = subprocess.run(command, cwd=skill, capture_output=True, text=True,
                                    env=env, timeout=240)
            output = result.stdout + result.stderr
            passed = result.returncode == 0
        except subprocess.TimeoutExpired:
            output, passed = "Check exceeded its 240 second limit.\n", False
        if args.logs:
            (logs / f"{name}.log").write_text(output, encoding="utf-8")
        if not passed:
            failures.append(name)
            print(output, flush=True)
        print(f"{'PASS' if passed else 'FAIL'}: {name}", flush=True)
    print(f"CHECKS: {len(checks) - len(failures)} PASS, {len(failures)} FAIL", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
