"""Shared paths for tests kept outside the installable runtime.

The validation runner supplies PM_SKILL_ROOT. When running one test directly in
the public checkout, skills/project-manager is selected automatically.
"""

from pathlib import Path
import sys

TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))
from validation_paths import resolve_layout

LAYOUT = resolve_layout()
SOURCE, SKILL, SCRIPTS, TESTS, TOOLS = (LAYOUT.source, LAYOUT.skill, LAYOUT.scripts,
                                      LAYOUT.tests, LAYOUT.tools)
for path in (TOOLS, TESTS, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

if not (SCRIPTS / "bootstrap_project.py").is_file():
    raise RuntimeError("Runtime not found. Set PM_SKILL_ROOT to the skill directory or use tools/run_checks.py --skill-root.")
