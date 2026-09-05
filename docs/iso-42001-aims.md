# Vidora AI management system

[ISO/IEC 42001:2023](https://www.iso.org/standard/42001) describes an organizational AI management system (AIMS). Vidora now supports that work with controlled records, release checks, and evidence exports, complementing its [NIST AI RMF controls](ai-risk-management.md). This implementation is a project-specific foundation; passing its checks is not ISO conformity, an internal audit opinion, or certification. A reviewer must use the applicable licensed standard for the full requirements and applicability assessment. The standard's text is not reproduced here.

## Implemented behavior

| Management activity | Code support | Organizational work required |
|---|---|---|
| Context, scope, leadership | Scope, use boundaries, interested parties, obligations, accountable owner and executive sponsor | Approve actual boundaries, regional obligations, responsibilities and resources |
| Risk planning and treatment | Risk register with owners, due dates, likelihood/severity, linked controls, residual acceptance | Complete risk/impact analysis and approve the criteria and treatment evidence |
| Control applicability | Controls with references, area, applicability rationale, implementation state and evidence | Complete the Statement of Applicability against the full standard; assess inclusions and exclusions |
| Support and documented information | Competence review, versioned JSON records, artifact hashes and schema validation | Verify staff competence, document access, retention, communication and resources |
| Operation and change management | Reviewed release bound to backend code, policy and retention; rollback record | Review data/provider locations, model and data provenance, supplier terms, affected-party impacts and changes |
| Performance evaluation | Measurable objectives, evaluation/language coverage, dated internal audit and management review | Collect representative measurements, perform independent audit, assess management-system effectiveness |
| Improvement | Incident/nonconformity records, owners, deadlines, corrective actions and effectiveness evidence | Triage actual reports, address causes, verify corrections and retain change history |

The nine seeded control areas are an initial project coverage check, **not a complete Annex A control list or Statement of Applicability**. Add individual controls and references during the full applicability review; the schema permits multiple controls per area. An excluded control still needs an owner, rationale and review evidence. A risk treatment cannot rely on an excluded or unimplemented control. A reviewer remains responsible for the correctness and completeness of these decisions.

## Record package and open-source tooling

- `functions/app/governance/aims_models.py`: strict Pydantic models and reference validation.
- `functions/app/governance/aims.json`: initial draft register; no approvals or measured results are fabricated.
- `functions/app/governance/aims.py`: readiness, bounded artifact hashing, runtime checks.
- `functions/app/governance/aims_cli.py`: local checks, fingerprints, and sanitized evidence inventories.
- Existing Prometheus instrumentation records blocked AI calls. The `aims_sha256` audit field binds each production decision to the exact normalized AIMS record snapshot.

This uses Pydantic, Prometheus and the Python standard library; no new cloud governance vendor or database service is required. There are no public management-record endpoints. Operator records are maintained through reviewed files in a controlled repository or immutable deployment package. Public user issue reports remain downloads until a support intake is configured; the AIMS incident register is maintained by operators after receiving a report through their real support process.

## Production gate

The existing NIST policy checks still apply. The operator check also compares the policy model list against the inventory shared by the actual integrations. Additionally, every production model boundary checks the AIMS release criteria before inference. Development keeps its existing behavior; it does not get an implicit production approval.

The gate requires:

1. Assigned leadership, evidence-backed control decisions and nonempty risk/objective registers.
2. Accepted residual risks within the organization's configured acceptance threshold and implemented treatment controls.
3. Current accepted risk, impact, supplier, data, evaluation, competence, internal-audit and management reviews. The audit reviewer must differ from the accountable owner. All evaluated languages declared by the policy must appear in the evaluation review, and that list cannot be empty for release.
4. Current objective measurements meeting their configured thresholds.
5. An independently approved release with current review dates, matching release ID, retention hours, policy hash and backend application hash. The approver must differ from the requester; comparisons of names are only a consistency check, not identity verification. Reassessments and risk acceptances after the release approval require another release review.
6. No unresolved high/critical incidents or nonconformities. Other open findings require ownership and a future due date. Closing a finding requires a root cause, correction, corrective action, effectiveness reviewer, evidence and a valid closing date.
7. Present, readable evidence artifacts matching the recorded SHA-256 digests.

Dates use UTC calendar days. A review is overdue at the start of its `next_review_on`/`review_due_on` day. Due-date and readiness checks run for every model call, even though the loaded package is cached. This strict fail-closed release policy is a **Vidora choice**, not a claim that ISO prescribes these exact gates or thresholds. Plan reviews early to avoid an unintended service interruption.

Risk scores are likelihood × severity on a 1–5 scale. The seed acceptance threshold of 6 and example quality targets are draft local choices for review, not numbers mandated by ISO. Objective measurements and evidence are supplied by accountable reviewers; the application does not infer accuracy, fairness, legal compliance, or artifact quality from a hash. Language coverage is release metadata; it does not automatically detect or restrict user languages.

## Configure a reviewed release

1. Assign the owner, sponsor and reviewers. Identify the complete deployment scope and real obligations, including provider/database/backup locations and user populations. Complete the control applicability review, impact/risk assessments, supplier/data review, staff competence evidence, and evaluation criteria.
2. Store reviewed evidence files inside the directory containing the selected `aims.json`, preferably under `artifacts/`. Register each file's relative path and SHA-256 in `evidence`, and reference its ID from the corresponding records. Files outside that directory, symlinks escaping it, missing/mismatched files and files over 10 MiB fail validation. Package digests/redacted summaries for larger sensitive evidence; retain originals in the governed evidence store.
3. Complete objectives and reviews based on real results. Complete a release record with distinct requester/approver, approval date, next review date, rollback plan and release ID. Review and approve `policy.json`, including languages and deployment regions. The default AIMS package deliberately fails readiness.
4. From `functions/`, compute the current fingerprints after the code and policy are final:

```sh
python -m app.governance.aims_cli fingerprint --policy app/governance/policy.json
```

Copy the returned digests into `release.policy_sha256` and `release.application_sha256` only as part of the reviewed change. Fingerprinting does not grant approval. The application hash covers backend `app/**/*.py` and `functions/requirements.txt`. It excludes `.env`, other secrets, the AIMS/evidence package, caches and tests. It does not attest the resolved dependency versions, model weights, frontend bundle, database configuration, or external-provider behavior; include their actual build/provenance records in release evidence and review changes to them.

5. Set the actual deployment values and run the release check. The following is a command template: choose an actual ID and region approved by your organization.

```sh
python -m app.governance.aims_cli check \
  --aims app/governance/aims.json \
  --policy app/governance/policy.json \
  --release-id YOUR_REVIEWED_RELEASE_ID \
  --retention-hours 24 \
  --region YOUR_APPROVED_BACKEND_REGION
```

The CLI reads explicit flags or process environment variables; it deliberately does not load application `.env` files. `check` returns 0 for passing local criteria, 1 for blockers, and 2 for malformed or unreadable configuration or output errors. Missing or changed evidence artifacts are reported as blockers (exit 1). It does not check live emergency-switch state, provider health, actual infrastructure geography, or the truth of reviewer statements.

6. Set `ENVIRONMENT=production`, `AI_RELEASE_ID` to that release ID, `AI_DEPLOYMENT_REGION` and `VIDEO_RETENTION_HOURS` to the reviewed values, and keep the existing provider/DB settings. Optionally set `AI_AIMS_PATH` and `AI_POLICY_PATH` to reviewed packages; bundled paths are defaults. Deploy the same backend source and evidence package checked by the CLI.

The source fingerprint must be calculated in the same source layout used at runtime. Policy/evidence/package changes require restarting or redeploying **every** instance: the files and hashes are cached as an immutable deployment snapshot. Do not edit package files in place and expect active instances to pick up new findings. For urgent issues use the existing emergency-stop procedure, and replace the package in a reviewed release. Filesystem/Git/deployment permissions are the trust boundary; editable JSON plus hashes is not a signature, independent identity verification, or tamper-proof audit storage. Protect deployment permissions and retain reviewed revisions externally.

Checks stop new model calls, not in-flight calls. The ingestion pipeline may have downloaded audio before reaching the transcription gate; these checks do not constitute a regional data-routing or pre-download authorization layer.

## Audit and management review

Export a metadata inventory for a specific package and release:

```sh
python -m app.governance.aims_cli export \
  --release-id YOUR_REVIEWED_RELEASE_ID --retention-hours 24 \
  --region YOUR_APPROVED_BACKEND_REGION --output /tmp/vidora-aims-review.json
```

Use the same `--aims` and `--policy` arguments if using nondefault packages. Existing output files are never overwritten. The report includes hashes, record counts, readiness blockers and evidence IDs/digests, but not reviewer names, incident narratives, prompts, or artifact contents. Keep identifiers free of sensitive information. The inventory is evidence *about* the package and must accompany the underlying controlled records; it is not a signed audit report.

Review operational metrics, language evaluation slices, incidents, complaints, overdue actions, supplier changes, resource adequacy and opportunities for improvement. Record decisions, owners, resources and deadlines in the management-review artifact. Internal auditors need appropriate independence and competence beyond the simple name check in code. Schedule reviews and assign ownership in the organization's real calendar/task system; this code does not send reminders or perform audits.

## Incident and corrective-action workflow

Add a `findings` record with ID, kind (`incident` or `nonconformity`), summary, severity, opened date, owner and due date. Keep personal data out of shared records and reference restricted evidence instead. `open` and `contained` findings remain unresolved; containment alone never clears a high/critical finding. On closure, record the root cause, immediate correction, recurrence-prevention action, effectiveness reviewer, closure date and supporting evidence. Retain the prior versions and decision trail in your controlled repository; do not delete findings to make checks pass. This checker evaluates the current snapshot and does not enforce an append-only history or authenticate who edited it.

Treat severe failures as release blockers, disable AI across instances, assess affected users and regions, and verify recovery before reapproval. Once low/medium actions are overdue, the release gate also blocks new production inference. External communication and any applicable reporting duties need the designated organizational process.

## Verification

From `functions/`:

```sh
python -m unittest discover -s tests -v
```

Tests use synthetic records and temporary artifacts. They verify production enforcement, draft/missing/expired reviews, changed code/policy/retention, evidence integrity and path boundaries, risk acceptance, language coverage, objectives, finding closure, and report privacy. They do not run live AI evaluations, validate provider contracts, or establish ISO conformity.
