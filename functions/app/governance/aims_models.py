"""Project-defined AIMS records, supporting ISO/IEC 42001 management processes.

These models validate documented information; they do not certify its truth.
"""
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Text = Annotated[str, Field(min_length=1, max_length=4000)]
Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Score = Annotated[int, Field(ge=1, le=5)]

REVIEW_KINDS = (
    "risk_assessment", "impact_assessment", "supplier_review", "data_review",
    "evaluation", "competence", "internal_audit", "management_review",
)
CONTROL_AREAS = (
    "policy", "accountability", "resources", "impact", "lifecycle",
    "data", "transparency", "responsible_use", "suppliers",
)


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class Evidence(Record):
    path: Text
    sha256: Digest


class Review(Record):
    kind: Literal[
        "risk_assessment", "impact_assessment", "supplier_review", "data_review",
        "evaluation", "competence", "internal_audit", "management_review",
    ]
    reviewer: Text | None = None
    performed_on: date | None = None
    next_review_on: date | None = None
    accepted: bool = False
    evidence: list[Identifier] = Field(default_factory=list)
    languages: list[Text] = Field(default_factory=list)


class Risk(Record):
    id: Identifier
    description: Text
    affected_parties: list[Text] = Field(min_length=1)
    owner: Text | None = None
    likelihood: Score
    severity: Score
    treatment: Text
    control_ids: list[Identifier] = Field(min_length=1)
    due_on: date | None = None
    status: Literal["open", "treated", "accepted"] = "open"
    residual_likelihood: Score | None = None
    residual_severity: Score | None = None
    accepted_by: Text | None = None
    accepted_on: date | None = None
    evidence: list[Identifier] = Field(default_factory=list)


class Control(Record):
    id: Identifier
    area: Literal[
        "policy", "accountability", "resources", "impact", "lifecycle",
        "data", "transparency", "responsible_use", "suppliers",
    ]
    reference: Text
    applicable: bool = True
    rationale: Text
    owner: Text | None = None
    implemented: bool = False
    evidence: list[Identifier] = Field(default_factory=list)


class Objective(Record):
    id: Identifier
    description: Text
    owner: Text | None = None
    metric: Text
    target: float = Field(allow_inf_nan=False)
    direction: Literal["at_least", "at_most"]
    observed: float | None = Field(default=None, allow_inf_nan=False)
    measured_on: date | None = None
    next_measurement_on: date | None = None
    evidence: list[Identifier] = Field(default_factory=list)


class Finding(Record):
    id: Identifier
    kind: Literal["incident", "nonconformity"]
    summary: Text
    severity: Literal["low", "medium", "high", "critical"]
    opened_on: date
    owner: Text | None = None
    due_on: date | None = None
    status: Literal["open", "contained", "closed"] = "open"
    root_cause: Text | None = None
    correction: Text | None = None
    corrective_action: Text | None = None
    effectiveness_checked_by: Text | None = None
    closed_on: date | None = None
    evidence: list[Identifier] = Field(default_factory=list)


class Release(Record):
    id: Identifier
    description: Text
    requested_by: Text | None = None
    approved_by: Text | None = None
    approved_on: date | None = None
    review_due_on: date | None = None
    policy_sha256: Digest | None = None
    application_sha256: Digest | None = None
    retention_hours: int = Field(gt=0)
    rollback_plan: Text
    evidence: list[Identifier] = Field(default_factory=list)


class AIMS(Record):
    schema_version: Literal["1.0"]
    version: Identifier
    scope: Text
    intended_use: Text
    excluded_uses: list[Text] = Field(min_length=1)
    interested_parties: list[Text] = Field(min_length=1)
    obligations: list[Text] = Field(min_length=1)
    accountable_owner: Text | None = None
    executive_sponsor: Text | None = None
    maximum_residual_risk: int = Field(ge=1, le=25)
    controls: list[Control]
    risks: list[Risk]
    objectives: list[Objective]
    reviews: list[Review]
    findings: list[Finding]
    release: Release
    evidence: dict[Identifier, Evidence]

    @model_validator(mode="after")
    def validate_references(self):
        for records, field in ((self.controls, "id"), (self.risks, "id"),
                               (self.objectives, "id"), (self.reviews, "kind"), (self.findings, "id")):
            ids = [getattr(record, field) for record in records]
            if len(ids) != len(set(ids)):
                raise ValueError("Duplicate record identifiers are not allowed")
        control_ids = {control.id for control in self.controls}
        for risk in self.risks:
            if not set(risk.control_ids) <= control_ids:
                raise ValueError("Risk references an unknown control")
        for record in [*self.controls, *self.risks, *self.objectives, *self.reviews, *self.findings, self.release]:
            if not set(record.evidence) <= self.evidence.keys():
                raise ValueError("Record references unknown evidence")
        return self
