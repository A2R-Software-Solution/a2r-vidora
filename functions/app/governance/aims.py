"""Read-only AIMS release checks and evidence inventory; no provider/database I/O."""
from datetime import date, datetime, timezone
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
import json
import os

from app.governance.aims_models import AIMS, CONTROL_AREAS, REVIEW_KINDS


class AIMSUnavailable(Exception):
    """The release evidence could not be loaded or verified."""


def canonical_digest(record) -> str:
    data = record.model_dump(mode="json") if hasattr(record, "model_dump") else record
    return sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def application_digest(app_root: Path | None = None) -> str:
    """Bind review to backend source and dependency declarations, not secrets or data."""
    root = app_root or Path(__file__).resolve().parents[1]
    files = sorted(root.rglob("*.py"))
    requirements = root.parent / "requirements.txt"
    digest = sha256()
    for path in files + ([requirements] if requirements.exists() else []):
        name = path.relative_to(root.parent).as_posix()
        content = path.read_bytes()
        digest.update(f"{name}\0{len(content)}\0".encode())
        digest.update(content)
    return digest.hexdigest()


def verify_evidence(aims: AIMS, base: Path) -> list[str]:
    """Only hash bounded local artifacts inside the reviewed evidence directory."""
    problems = []
    root = base.resolve()
    for key, evidence in aims.evidence.items():
        try:
            relative = Path(evidence.path)
            path = (root / relative).resolve()
            if relative.is_absolute() or not path.is_relative_to(root) or not path.is_file():
                raise ValueError("Evidence must be a file within its package")
            if path.stat().st_size > 10 * 1024 * 1024:
                raise ValueError("Evidence exceeds 10 MiB")
            if sha256(path.read_bytes()).hexdigest() != evidence.sha256:
                raise ValueError("Evidence digest mismatch")
        except (OSError, ValueError, RuntimeError):
            problems.append(f"evidence:{key}:missing_or_changed")
    return problems


def readiness(aims: AIMS, *, policy_digest: str, app_digest: str, release_id: str,
              retention_hours: int, languages: list[str], today: date | None = None) -> list[str]:
    """Project release criteria; this is deliberately not an ISO conformity score."""
    today = today or datetime.now(timezone.utc).date()
    problems = []

    def require(condition, key):
        if not condition:
            problems.append(key)

    def current(start, due):
        return start is not None and due is not None and start <= today < due

    require(aims.accountable_owner and aims.executive_sponsor, "leadership:unassigned")
    release = aims.release
    require(release.id == release_id and bool(release_id), "release:id_mismatch")
    require(release.policy_sha256 == policy_digest, "release:policy_changed")
    require(release.application_sha256 == app_digest, "release:application_changed")
    require(release.retention_hours == retention_hours, "release:retention_changed")
    require(release.requested_by and release.approved_by
            and release.requested_by.casefold() != release.approved_by.casefold(), "release:independent_approval_missing")
    require(current(release.approved_on, release.review_due_on), "release:review_not_current")
    require(release.evidence, "release:evidence_missing")

    require(set(CONTROL_AREAS) <= {c.area for c in aims.controls}, "controls:area_coverage_missing")
    for control in aims.controls:
        require(control.owner and control.evidence, f"control:{control.id}:owner_or_evidence_missing")
        require(not control.applicable or control.implemented, f"control:{control.id}:not_implemented")
    controls = {c.id: c for c in aims.controls}
    require(aims.risks, "risk:assessment_missing")
    for risk in aims.risks:
        score = (risk.residual_likelihood or 0) * (risk.residual_severity or 0)
        require(risk.owner and risk.accepted_by and risk.evidence, f"risk:{risk.id}:acceptance_missing")
        require(risk.status != "open" and 0 < score <= aims.maximum_residual_risk, f"risk:{risk.id}:unacceptable")
        require(risk.due_on is not None, f"risk:{risk.id}:due_date_missing")
        require(risk.accepted_on is not None and risk.accepted_on <= today,
                f"risk:{risk.id}:acceptance_date_missing")
        require(risk.accepted_on is not None and release.approved_on is not None
                and risk.accepted_on <= release.approved_on, f"risk:{risk.id}:release_review_required")
        require(all(controls[key].applicable and controls[key].implemented for key in risk.control_ids),
                f"risk:{risk.id}:treatment_not_implemented")

    reviews = {review.kind: review for review in aims.reviews}
    for kind in REVIEW_KINDS:
        review = reviews.get(kind)
        require(review is not None, f"review:{kind}:missing")
        if review:
            require(review.accepted and review.reviewer and review.evidence, f"review:{kind}:not_accepted")
            require(current(review.performed_on, review.next_review_on), f"review:{kind}:not_current")
            require(review.performed_on is not None and release.approved_on is not None
                    and review.performed_on <= release.approved_on, f"review:{kind}:release_review_required")
    audit = reviews.get("internal_audit")
    if audit and audit.reviewer and aims.accountable_owner:
        require(audit.reviewer.casefold() != aims.accountable_owner.casefold(), "review:internal_audit:independence_missing")
    evaluation = reviews.get("evaluation")
    require(languages and evaluation and set(languages) <= set(evaluation.languages), "evaluation:language_coverage_missing")

    require(aims.objectives, "objectives:missing")
    for objective in aims.objectives:
        require(objective.owner and objective.evidence, f"objective:{objective.id}:owner_or_evidence_missing")
        require(current(objective.measured_on, objective.next_measurement_on), f"objective:{objective.id}:not_current")
        meets_target = objective.observed is not None and (
            objective.observed >= objective.target if objective.direction == "at_least"
            else objective.observed <= objective.target)
        require(meets_target, f"objective:{objective.id}:target_not_met")

    for finding in aims.findings:
        require(finding.owner and finding.due_on and finding.opened_on <= today
                and finding.opened_on <= finding.due_on, f"finding:{finding.id}:triage_missing")
        if finding.status == "closed":
            require(finding.root_cause and finding.correction and finding.corrective_action
                    and finding.effectiveness_checked_by and finding.evidence and finding.closed_on
                    and finding.opened_on <= finding.closed_on <= today, f"finding:{finding.id}:closure_not_verified")
        else:
            require(finding.severity not in ("high", "critical"), f"finding:{finding.id}:unresolved_serious_finding")
            require(finding.due_on is not None and today < finding.due_on, f"finding:{finding.id}:overdue")
    return sorted(set(problems))


def load_package(path: Path) -> AIMS:
    try:
        aims = AIMS.model_validate_json(path.read_text())
        if verify_evidence(aims, path.parent):
            raise AIMSUnavailable("AIMS evidence is missing or changed")
        return aims
    except (OSError, ValueError) as exc:
        raise AIMSUnavailable("AIMS records are unavailable or invalid") from exc


@lru_cache
def runtime_package() -> tuple[AIMS, str]:
    path = Path(os.environ.get("AI_AIMS_PATH", str(Path(__file__).with_name("aims.json"))))
    try:
        aims = load_package(path)
        return aims, application_digest()
    except (OSError, ValueError, RuntimeError) as exc:
        raise AIMSUnavailable("AIMS package or application inventory is unavailable") from exc


def check_runtime(policy, *, release_id: str, retention_hours: int) -> tuple[str, list[str]]:
    aims, app_digest = runtime_package()
    return canonical_digest(aims), readiness(aims, policy_digest=canonical_digest(policy),
        app_digest=app_digest, release_id=release_id, retention_hours=retention_hours,
        languages=policy.evaluated_languages)
