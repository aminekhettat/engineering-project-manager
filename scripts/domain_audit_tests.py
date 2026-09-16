#!/usr/bin/env python3
"""Behavioral tests for revision-aware engineering domain audits."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
AUDIT = SCRIPTS / "domain_audit.py"


def requirement(identifier: str) -> str:
    return f"""[{identifier}]
Status: RELEASED
Upstream: ROOT
Allocated_To: NONE
Verification_Method: TEST
Verification_Scope: SOFTWARE
Verification_Activity: VERIFICATION
Verification_Process: SWE6
Implementation_Milestone: M1
Verification_Milestone: M2
Owner: SWE
Priority: MUST
Rationale: Domain audit fixture.
Acceptance_Criteria: The behavior is verified.
Text:
The software shall provide deterministic behavior.
[END_REQ]
"""


class DomainAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary.name)
        self.write(
            "00-project/BOOTSTRAP.json",
            json.dumps({"domains": ["SWE"]}),
        )
        self.identifier = "M5_SWE1_REQ_001@R1"
        self.write(
            "01-requirements/software/SWE-REQUIREMENTS.md",
            requirement(self.identifier),
        )
        evidence = (
            "# Controlled work product\n\n"
            f"{self.identifier}\n\n"
            "Completed engineering content and objective evidence.\n"
        )
        self.write("02-architecture/software/SWE-ARCHITECTURE.md", evidence)
        self.write("03-design/software/SWE-DETAILED-DESIGN.md", evidence)
        self.write("05-verification/software/SWE-TEST-SPECIFICATION.md", evidence)
        self.write("05-verification/software/SWE-VERIFICATION-REPORT.md", evidence)

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, relative: str, content: str) -> None:
        path = self.project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def audit(self, expected: int = 0) -> str:
        result = subprocess.run(
            ["python3", str(AUDIT), str(self.project), "--strict"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self.assertEqual(expected, result.returncode, result.stdout)
        return result.stdout

    def test_v11_process_identity_is_recognized_for_domain(self):
        output = self.audit()
        self.assertIn("Requirements: 1", output)
        self.assertIn("DOMAIN AUDIT: 0 error(s), 0 warning(s)", output)

    def test_requirement_from_wrong_process_does_not_satisfy_domain(self):
        wrong = "M5_HWE1_REQ_001@R1"
        self.write(
            "01-requirements/software/SWE-REQUIREMENTS.md",
            requirement(wrong),
        )
        output = self.audit(expected=1)
        self.assertIn("SWE: no domain requirement defined", output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
