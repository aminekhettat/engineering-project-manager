#!/usr/bin/env python3
"""Behavioral compatibility tests for Project Manager requirement linting."""

import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
LINTER = SCRIPTS / "requirements_lint.py"


def v11_requirement(identifier: str, wording: str) -> str:
    return f"""[{identifier}]
Status: RELEASED
Upstream: ROOT
Allocated_To: NONE
Verification_Method: TEST
Verification_Scope: SYSTEM
Verification_Activity: VERIFICATION
Verification_Process: SYS5
Implementation_Milestone: M1
Verification_Milestone: M2
Owner: SYS
Priority: MUST
Rationale: Compatibility fixture.
Acceptance_Criteria: The statement is objectively verified.
Text:
{wording}
[END_REQ]
"""


class RequirementCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary.name)
        (self.project / "01-requirements").mkdir(parents=True)

    def tearDown(self):
        self.temporary.cleanup()

    def lint(self, text: str, expected: int = 0) -> str:
        (self.project / "01-requirements/REQUIREMENTS.md").write_text(
            text, encoding="utf-8"
        )
        result = subprocess.run(
            ["python3", str(LINTER), str(self.project), "--strict"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self.assertEqual(expected, result.returncode, result.stdout)
        return result.stdout

    def test_v11_english_canonical_wording_is_accepted(self):
        output = self.lint(
            v11_requirement(
                "M5_SYS2_REQ_001@R1",
                "The system shall detect communication loss within 100 ms.",
            )
        )
        self.assertIn("RESULT: 0 error(s), 0 warning(s)", output)

    def test_legacy_french_normative_forms_remain_accepted(self):
        statements = (
            "Le système doit détecter la perte de communication.",
            "Les composants doivent signaler les défauts.",
            "Le système devra conserver le diagnostic.",
            "Les unités devront publier leur état.",
        )
        blocks = []
        for index, statement in enumerate(statements, 1):
            blocks.append(
                f"## SYS-REQ-{index:03d} — Legacy requirement\n\n"
                f"Verification Method: TEST\n\n{statement}\n"
            )
        output = self.lint("\n".join(blocks))
        self.assertIn("Requirements checked: 4", output)
        self.assertIn("RESULT: 0 error(s), 0 warning(s)", output)

    def test_v11_french_statement_is_accepted_for_migration_compatibility(self):
        output = self.lint(
            v11_requirement(
                "M5_SYS2_REQ_002@R1",
                "Le système doit détecter la perte de communication sous 100 ms.",
            )
        )
        self.assertIn("RESULT: 0 error(s), 0 warning(s)", output)

    def test_non_normative_statement_is_rejected(self):
        output = self.lint(
            v11_requirement(
                "M5_SYS2_REQ_003@R1",
                "Communication loss detection within 100 ms.",
            ),
            expected=1,
        )
        self.assertIn("normative shall wording not detected", output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
