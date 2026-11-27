"""Keep private archive restoration explicitly admitted, not triggered by code pushes."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"


class PrivateReadAdmissionTests(unittest.TestCase):
    def test_private_reads_require_manual_owner_attestation(self):
        for name, job in (
            ("azure-private-workspace.yml", "archived-data-smoke"),
            ("qualify-iqies-sidecar-roundtrip.yml", "roundtrip"),
        ):
            with self.subTest(workflow=name):
                workflow = (WORKFLOWS / name).read_text()
                self.assertIn("  workflow_dispatch:\n    inputs:", workflow)
                self.assertIn("      permitted_private_read:\n", workflow)
                self.assertIn("        default: false\n", workflow)
                self.assertIn("      approval_reference:\n", workflow)
                private_job = workflow.split("\n  " + job + ":\n", 1)[1]
                condition = next(line.strip() for line in private_job.splitlines()
                                 if line.strip().startswith("if:"))
                for required in (
                    "github.event_name == 'workflow_dispatch'",
                    "inputs.permitted_private_read == true",
                    "inputs.approval_reference != ''",
                    "github.repository == 'JeremyHennessy/FacilitySignal'",
                    "github.ref == 'refs/heads/main'",
                ):
                    self.assertIn(required, condition)
                self.assertIn("environment: azure-production", private_job)
                self.assertNotIn("AZURE_STORAGE_KEY", workflow.split("\n  " + job + ":\n", 1)[0])
                self.assertIn("group: facilitysignal-iqies-national-service-recovery", workflow)
                self.assertIn("cancel-in-progress: false", workflow)

    def test_push_roundtrip_still_runs_fixture_qualification(self):
        workflow = (WORKFLOWS / "qualify-iqies-sidecar-roundtrip.yml").read_text()
        self.assertIn("  push:\n    branches: [main]", workflow)
        self.assertIn("python -m unittest discover -s tests -v", workflow)
        self.assertIn("needs: qualify", workflow)
