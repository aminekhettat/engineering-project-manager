#!/usr/bin/env python3
"""Negative tests for requirement block integrity and traceability cycles."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pm_common import parse_requirement_record, requirement_definitions
from requirements_compatibility_tests import v11_requirement

SCRIPTS = Path(__file__).resolve().parent


def requirement(number, upstream="ROOT", allocated="NONE"):
    return v11_requirement(
        f"M5_SYS2_REQ_{number:03d}@R1", "The system shall preserve requirement integrity."
    ).replace("Upstream: ROOT", f"Upstream: {upstream}").replace(
        "Allocated_To: NONE", f"Allocated_To: {allocated}"
    )


class RequirementIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary.name)
        self.path = self.project / "01-requirements/REQ.md"
        self.path.parent.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def run_check(self, script, content, expected):
        self.path.write_text(content, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / script), str(self.project), "--strict"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        self.assertEqual(expected, result.returncode, result.stdout)
        return result.stdout

    def test_missing_end_cannot_borrow_next_requirement_terminator(self):
        text = requirement(1).replace("[END_REQ]", "") + requirement(2)
        output = self.run_check("requirements_lint.py", text, 1)
        self.assertIn("M5_SYS2_REQ_001@R1: [END_REQ] missing", output)
        records = [parse_requirement_record(item) for item in requirement_definitions(self.project)]
        self.assertEqual(2, len(records))
        self.assertFalse(records[0]["terminated"])
        self.assertTrue(records[1]["terminated"])
        self.assertNotIn("M5_SYS2_REQ_002", records[0]["requirement_text"])

    def test_duplicate_metadata_is_rejected_case_insensitively(self):
        for duplicate in ("Status: CANCELLED", "status: RELEASED"):
            with self.subTest(duplicate=duplicate):
                text = requirement(1).replace("Status: RELEASED", "Status: RELEASED\n" + duplicate)
                output = self.run_check("requirements_lint.py", text, 1)
                self.assertIn("duplicate attribute: status", output)

    def test_self_reference_cannot_satisfy_its_own_allocation(self):
        text = requirement(1, "M5_SYS2_REQ_001@R1", "SYS2")
        output = self.run_check("traceability_check.py", text, 1)
        self.assertIn("Circular Upstream traceability", output)

    def test_multi_requirement_cycle_is_rejected(self):
        text = requirement(1, "M5_SYS2_REQ_002@R1", "SYS2") + requirement(
            2, "M5_SYS2_REQ_001@R1", "SYS2"
        )
        output = self.run_check("traceability_check.py", text, 1)
        self.assertIn("Circular Upstream traceability", output)

    def test_valid_diamond_traceability_remains_accepted(self):
        text = (requirement(1, allocated="SYS2")
                + requirement(2, "M5_SYS2_REQ_001@R1", "SYS2")
                + requirement(3, "M5_SYS2_REQ_001@R1", "SYS2")
                + requirement(4, "M5_SYS2_REQ_002@R1, M5_SYS2_REQ_003@R1"))
        self.run_check("requirements_lint.py", text, 0)
        self.run_check("traceability_check.py", text, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
