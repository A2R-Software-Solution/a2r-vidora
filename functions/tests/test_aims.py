import contextlib
from datetime import date, timedelta
from hashlib import sha256
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pydantic import ValidationError
from app.governance.aims import (
    AIMSUnavailable, application_digest, canonical_digest, check_runtime,
    load_package, readiness, runtime_package, verify_evidence,
)
from app.governance.aims_cli import main
from app.governance.aims_models import AIMS, Finding
from app.governance.runtime import Policy

TODAY = date(2026, 9, 5)
DUE = TODAY + timedelta(days=30)
POLICY = Policy(version="test", owner="owner", approved=True, deployment_regions=["eu"],
                evaluated_languages=["en"], operations={"answer": "test-model"})
DRAFT = Path(__file__).parents[1] / "app/governance/aims.json"


def ready_fixture():
    """Synthetic review records for tests only; never a deployable approval package."""
    data = json.loads(DRAFT.read_text())
    data["accountable_owner"] = "owner"
    data["executive_sponsor"] = "sponsor"
    data["evidence"] = {"test-evidence": {"path": "evidence.txt", "sha256": sha256(b"test evidence").hexdigest()}}
    for control in data["controls"]:
        control.update(owner="owner", implemented=True, evidence=["test-evidence"])
    for risk in data["risks"]:
        risk.update(owner="owner", status="treated", residual_likelihood=1, residual_severity=2,
                    accepted_by="sponsor", accepted_on=TODAY.isoformat(),
                    due_on=DUE.isoformat(), evidence=["test-evidence"])
    for review in data["reviews"]:
        review.update(reviewer="independent-reviewer", performed_on=TODAY.isoformat(),
                      next_review_on=DUE.isoformat(), accepted=True, evidence=["test-evidence"], languages=["en"])
    for objective in data["objectives"]:
        objective.update(owner="owner", observed=objective["target"], measured_on=TODAY.isoformat(),
                         next_measurement_on=DUE.isoformat(), evidence=["test-evidence"])
    data["release"].update(id="test-release", requested_by="developer", approved_by="reviewer",
        approved_on=TODAY.isoformat(), review_due_on=DUE.isoformat(),
        policy_sha256=canonical_digest(POLICY), application_sha256="a" * 64, evidence=["test-evidence"])
    return AIMS.model_validate_json(json.dumps(data))


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.aims = ready_fixture()

    def check(self, **overrides):
        args = dict(policy_digest=canonical_digest(POLICY), app_digest="a" * 64,
                    release_id="test-release", retention_hours=24, languages=["en"], today=TODAY)
        args.update(overrides)
        return readiness(self.aims, **args)

    def test_complete_records_pass(self):
        self.assertEqual(self.check(), [])

    def test_bundled_draft_blocks_release(self):
        self.aims = AIMS.model_validate_json(DRAFT.read_text())
        self.assertIn("leadership:unassigned", self.check())
        self.assertIn("release:independent_approval_missing", self.check())

    def test_changed_release_inputs_are_blocked(self):
        for field, value, expected in [
            ("policy_digest", "b" * 64, "release:policy_changed"),
            ("app_digest", "b" * 64, "release:application_changed"),
            ("retention_hours", 48, "release:retention_changed"),
            ("release_id", "other", "release:id_mismatch"),
        ]:
            with self.subTest(field=field):
                self.assertIn(expected, self.check(**{field: value}))

    def test_expiry_is_rechecked_at_due_date(self):
        self.assertIn("release:review_not_current", self.check(today=DUE))
        self.assertIn("review:internal_audit:not_current", self.check(today=DUE))

    def test_future_dated_reviews_cannot_pass(self):
        self.aims.reviews[0].performed_on = TODAY + timedelta(days=1)
        self.assertIn("review:risk_assessment:not_current", self.check())

    def test_post_release_assessment_needs_release_review(self):
        self.aims.release.approved_on = TODAY - timedelta(days=1)
        self.assertIn("review:impact_assessment:release_review_required", self.check())

    def test_unassessed_language_cannot_pass(self):
        self.assertIn("evaluation:language_coverage_missing", self.check(languages=["en", "ja"]))
        self.assertIn("evaluation:language_coverage_missing", self.check(languages=[]))

    def test_review_cannot_be_omitted(self):
        self.aims.reviews = [review for review in self.aims.reviews if review.kind != "supplier_review"]
        self.assertIn("review:supplier_review:missing", self.check())

    def test_residual_risk_must_meet_criteria(self):
        self.aims.risks[0].residual_likelihood = 5
        self.aims.risks[0].residual_severity = 5
        self.assertIn("risk:unsupported-answers:unacceptable", self.check())

    def test_unimplemented_or_excluded_treatment_cannot_pass(self):
        self.aims.controls[4].applicable = False
        self.assertIn("risk:unsupported-answers:treatment_not_implemented", self.check())

    def test_approval_and_audit_independence(self):
        self.aims.release.approved_by = "DEVELOPER"
        next(r for r in self.aims.reviews if r.kind == "internal_audit").reviewer = "OWNER"
        self.assertIn("release:independent_approval_missing", self.check())
        self.assertIn("review:internal_audit:independence_missing", self.check())

    def test_objective_failure_and_stale_measurements(self):
        self.aims.objectives[0].observed = .2
        self.aims.objectives[0].next_measurement_on = TODAY
        self.assertIn("objective:groundedness:target_not_met", self.check())
        self.assertIn("objective:groundedness:not_current", self.check())

    def finding(self, **overrides):
        data = dict(id="incident-1", kind="incident", summary="Sensitive narrative", severity="high",
                    opened_on=TODAY, owner="operator", due_on=DUE)
        data.update(overrides)
        self.aims.findings = [Finding(**data)]

    def test_containment_does_not_close_serious_incident(self):
        self.finding(status="contained")
        self.assertIn("finding:incident-1:unresolved_serious_finding", self.check())

    def test_overdue_lower_severity_finding_blocks(self):
        self.finding(severity="low", due_on=TODAY)
        self.assertIn("finding:incident-1:overdue", self.check())

    def test_closure_requires_cause_action_and_effectiveness_evidence(self):
        self.finding(status="closed", closed_on=TODAY)
        self.assertIn("finding:incident-1:closure_not_verified", self.check())
        self.finding(status="closed", closed_on=TODAY, root_cause="Cause", correction="Correction",
                     corrective_action="Prevent recurrence", effectiveness_checked_by="reviewer", evidence=["test-evidence"])
        self.assertEqual(self.check(), [])

    def test_schema_rejects_duplicate_ids_and_unknown_evidence(self):
        data = self.aims.model_dump(mode="json")
        data["risks"].append(data["risks"][0])
        with self.assertRaises(ValidationError):
            AIMS.model_validate_json(json.dumps(data))
        data = self.aims.model_dump(mode="json")
        data["reviews"][0]["evidence"] = ["missing"]
        with self.assertRaises(ValidationError):
            AIMS.model_validate_json(json.dumps(data))

    def test_schema_rejects_boolean_scores_and_nan(self):
        data = self.aims.model_dump(mode="json")
        data["risks"][0]["likelihood"] = True
        with self.assertRaises(ValidationError):
            AIMS.model_validate_json(json.dumps(data))
        data = self.aims.model_dump(mode="json")
        data["objectives"][0]["observed"] = float("nan")
        with self.assertRaises(ValidationError):
            AIMS.model_validate_json(json.dumps(data))


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.aims = ready_fixture()
        (self.root / "evidence.txt").write_bytes(b"test evidence")
        self.path = self.root / "aims.json"
        self.path.write_text(self.aims.model_dump_json())

    def test_verified_package_loads(self):
        self.assertEqual(load_package(self.path).version, self.aims.version)

    def test_modified_evidence_fails_closed(self):
        (self.root / "evidence.txt").write_text("changed")
        with self.assertRaises(AIMSUnavailable):
            load_package(self.path)

    def test_path_escape_absolute_and_symlink_are_rejected(self):
        with tempfile.TemporaryDirectory() as other:
            external = Path(other) / "artifact.txt"
            external.write_bytes(b"test evidence")
            (self.root / "link.txt").symlink_to(external)
            for value in [str(external), "../artifact.txt", "link.txt"]:
                with self.subTest(value=value):
                    self.aims.evidence["test-evidence"].path = value
                    self.assertEqual(verify_evidence(self.aims, self.root), ["evidence:test-evidence:missing_or_changed"])

    def test_missing_or_malformed_package_fails_closed(self):
        self.path.write_text("not json")
        with self.assertRaises(AIMSUnavailable):
            load_package(self.path)
        with self.assertRaises(AIMSUnavailable):
            load_package(self.root / "missing.json")

    def test_code_and_requirements_changes_invalidate_fingerprint(self):
        app = self.root / "app"
        app.mkdir()
        code = app / "model.py"
        code.write_text("first")
        first = application_digest(app)
        code.write_text("second")
        second = application_digest(app)
        self.assertNotEqual(first, second)
        (self.root / "requirements.txt").write_text("dependency==1")
        self.assertNotEqual(second, application_digest(app))

    def test_runtime_rechecks_dates_even_with_cached_package(self):
        with patch("app.governance.aims.runtime_package", return_value=(self.aims, "a" * 64)), \
             patch("app.governance.aims.datetime") as clock:
            clock.now.return_value.date.return_value = DUE
            digest, blockers = check_runtime(POLICY, release_id="test-release", retention_hours=24)
        self.assertEqual(digest, canonical_digest(self.aims))
        self.assertIn("release:review_not_current", blockers)

    def test_export_contains_inventory_without_incident_narratives(self):
        policy_path = self.root / "policy.json"
        policy_path.write_text(POLICY.model_dump_json())
        output = self.root / "report.json"
        # Real time is intentionally used; this fixture is not a production release.
        args = ["export", "--aims", str(self.path), "--policy", str(policy_path),
                "--release-id", "test-release", "--retention-hours", "24", "--region", "eu", "--output", str(output)]
        with patch("app.governance.aims_cli.application_digest", return_value="a" * 64):
            self.assertIn(main(args), (0, 1))
        report = json.loads(output.read_text())
        self.assertIn("evidence_inventory", report)
        self.assertNotIn("scope", report)
        self.assertNotIn("owner", report)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(args), 2)

    def test_cli_passes_a_complete_matching_release(self):
        from app.governance.inventory import MODEL_INVENTORY
        policy = POLICY.model_copy(update={"operations": MODEL_INVENTORY})
        policy_path = self.root / "policy.json"
        policy_path.write_text(policy.model_dump_json())
        self.aims.release.policy_sha256 = canonical_digest(policy)
        self.path.write_text(self.aims.model_dump_json())
        output = io.StringIO()
        with patch("app.governance.aims_cli.application_digest", return_value="a" * 64), \
             patch("app.governance.aims.datetime") as clock, contextlib.redirect_stdout(output):
            clock.now.return_value.date.return_value = TODAY
            self.assertEqual(main(["check", "--aims", str(self.path), "--policy", str(policy_path),
                "--release-id", "test-release", "--retention-hours", "24", "--region", "eu"]), 0)
        self.assertTrue(json.loads(output.getvalue())["ready"])

    def test_cli_returns_failure_for_draft_and_invalid_json(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["check", "--aims", str(DRAFT)]), 1)
            self.path.write_text("invalid")
            self.assertEqual(main(["check", "--aims", str(self.path)]), 2)

    def tearDown(self):
        runtime_package.cache_clear()


class ProductionBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_production_uses_real_aims_gate_before_model(self):
        from types import SimpleNamespace
        from app.governance.runtime import GovernanceBlocked, governed

        settings = SimpleNamespace(is_production=True, ai_enabled=True, ai_deployment_region="eu",
                                   ai_release_id="test-release", video_retention_hours=24)
        aims = ready_fixture()
        calls = []

        @governed("answer", "test-model")
        async def model():
            calls.append("model")
            return "answer"

        with patch.dict("sys.modules", {"app.core.config": SimpleNamespace(settings=settings)}), \
             patch("app.governance.runtime.get_policy", return_value=POLICY), \
             patch("app.governance.aims.runtime_package", return_value=(aims, "a" * 64)), \
             patch("app.governance.aims.datetime") as clock:
            clock.now.return_value.date.return_value = TODAY
            with self.assertLogs("vidora.governance", level="INFO") as events:
                self.assertEqual(await model(), "answer")
            self.assertEqual(json.loads(events.records[0].getMessage())["aims_sha256"], canonical_digest(aims))
            aims.reviews[0].accepted = False
            with self.assertRaises(GovernanceBlocked):
                await model()
            self.assertEqual(calls, ["model"])

    async def test_missing_aims_blocks_without_exposing_artifact_paths(self):
        from types import SimpleNamespace
        from app.governance.runtime import GovernanceBlocked, governed

        settings = SimpleNamespace(is_production=True, ai_enabled=True, ai_deployment_region="eu",
                                   ai_release_id="test-release", video_retention_hours=24)

        @governed("answer", "test-model")
        async def model():
            self.fail("Unreviewed inference must never execute")

        with patch.dict("sys.modules", {"app.core.config": SimpleNamespace(settings=settings)}), \
             patch("app.governance.runtime.get_policy", return_value=POLICY), \
             patch("app.governance.aims.runtime_package", side_effect=AIMSUnavailable("private/path")):
            with self.assertRaisesRegex(GovernanceBlocked, "evidence is unavailable") as caught:
                await model()
            self.assertNotIn("private/path", str(caught.exception))
