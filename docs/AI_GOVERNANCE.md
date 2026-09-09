# VidoraAI AI risk management and production release record

Status: engineering hardening implemented; production validation and organizational
approval pending. Not a certification, audit opinion, or declaration of conformity.
Prepared 2026-09-09. GMMM means Govern, Map, Measure, Monitor as explicitly
defined by the product owner. It is used here as the project's operating model,
not represented as a separate published standard. NIST's fourth function remains
Manage; monitoring supports its Measure/Manage outcomes, not a renamed substitute.

## Authoritative basis and scope

- [NIST AI RMF Core](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/):
  voluntary lifecycle risk management through Govern, Map, Measure, Manage.
- [NIST Playbook](https://airc.nist.gov/airmf-resources/playbook/): suggested
  actions, not an exhaustive checklist or certification scheme.
- [ISO/IEC 42001:2023 official overview](https://www.iso.org/standard/42001):
  organizational AI management-system requirements and continual improvement.
  This mapping uses public themes only. The licensed standard, applicability
  decisions, internal audit, management review, and independent assessment are
  required before claiming conformity; clause-level coverage has not been assessed.

Scope: YouTube audio ingestion, temporary transcript/vector storage, summaries,
and transcript-grounded Q&A. Intended as an informational aid, not an autonomous
decision maker. Users must verify outputs and have rights to process content.
Impacted parties include submitters, viewers and people appearing in recordings.
Do not silently expand scope to employment, credit, medical or legal decisions.

## System and data inventory

Browser -> Firebase API -> YouTube download/cookie secrets -> Groq transcription
-> local MiniLM embeddings -> PostgreSQL -> Groq summary/answer -> browser.
No automatic browser status polling. Completed results can be recovered by one
explicit user read. Long HTTP requests still depend on connection/platform lifetime.

- Groq Whisper large v3: audio leaves the application boundary.
- Groq gpt-oss-20b: transcript excerpts/questions leave the boundary. Two accounts
  may receive requests; review both accounts' provider terms, access and retention.
- all-MiniLM-L6-v2: local CPU inference, pinned revision and SHA-256 manifest
  in functions/scripts/model_manifest.json. Runtime network downloads disabled.
- PostgreSQL stores video metadata, transcripts/vectors and Q&A logs. Expiry is
  enforced on reads; deletion is a daily job, so expiry is not immediate physical
  deletion. Backups and provider-side retention need a separately approved policy.
- Anonymous video IDs are bearer capabilities, not user authentication. Anyone
  holding such an ID can access the corresponding anonymous video under current
  product policy. Do not publish IDs in analytics or external support channels.

## Control mapping and evidence

| Area | NIST function | ISO management-system theme | Evidence/status |
|---|---|---|---|
| Scope, intended use, impacts, data/vendors | Map | Context and impact assessment | Inventory above; owner review pending |
| Ownership, risk acceptance, policy | Govern | Leadership, responsibilities, planning | Owner roles below unassigned; not complete |
| Model supply chain | Govern/Manage | Operational lifecycle controls | Pinned model, offline load, hash verification predeploy |
| Duplicate-request cost/recovery | Manage | Risk treatment and operation | PostgreSQL insert-on-conflict; frontend retained request ID; manual recovery |
| Access boundaries | Manage | Data and responsible-use controls | History ownership/expiry validation; bearer-capability limitation documented |
| Provider/resource failure | Manage | Operational controls | Shared provider deadline; concurrency=2 on API; 270s application timeout |
| User transparency | Govern/Map | Communication | AI uncertainty and processing-rights notice; verify against video |
| Prompt/data separation | Manage | AI-system operation | Escaped delimiters and grounded prompts; semantic injection remains a risk |
| Measurement | Measure | Performance evaluation | Offline regression tests; live quality/latency/load evidence still pending |
| Incident response | Manage | Improvement and corrective action | AI_ENABLED=false pause; runbook below; exercises pending |

## Risk register and release gates

| Risk | Current treatment | Residual risk / evidence required |
|---|---|---|
| Lost response / paid duplicate work | Same request UUID returns saved result or 409; manual recovery | Protection lasts while retained DB row exists. New UUID is a new job. Multi-instance PostgreSQL race test required |
| Crash leaves processing stale | Authorized manual read marks >10min processing failed | No proactive reconciliation; legacy queued jobs may need inspection. Blocking thread cancellation is not forceful |
| Abusive traffic / cost | Atomic PostgreSQL fixed-window limiter in production; max instances and concurrency | Requires migration 6c10a9e721df. Does not prevent billed invocation floods or distributed-IP abuse; proxy client-IP validation and edge controls remain release gates |
| Wrong or fabricated AI answer | Retrieval grounding, no-context abstention, user notice | Human-reviewed evaluation across languages/noise and hallucinations required |
| Prompt injection | Untrusted tags escaped and system instruction isolation | Natural-language attacks still possible. Adversarial evaluations required |
| Privacy / copyright | Scope notice, expiry/access checks, secret bindings | Consent/legal basis, vendor retention and deletion/backups policies require approval |
| Model changes or corruption | Pinned revision, predeploy hashes | Dependency lock/SBOM/vulnerability scan and license review pending |
| Long videos / cold starts / OOM | Batch embeddings, cached locked model, local files | Stage p50/p95, 1/10/35min and concurrent load benchmarks pending; 35min acceptance is not a latency guarantee |
| Provider error leakage | Groq errors sanitized; stage logs exclude content | Review third-party downloader/logging and retention policies before external access |

Suggested release gates (proposals, not measured achievements): no unauthorized
history access; zero duplicate pipeline runs for concurrent same-key requests;
no background browser status loop; provider timeout test passes; 1/10/35-minute
representative videos tested at concurrency 1/2/10 with no OOM; completed results
recover after a dropped response; model integrity gate passes on clean build;
quality evaluation approved by product owner. Latency thresholds must be agreed
after a real benchmark, not invented from local model timings.

## Organizational responsibilities requiring owner input

Assign named product/risk owner, technical incident owner, privacy/security owner
and independent reviewer. Approve acceptable use, risk tolerance, incident severity,
data retention, provider agreements, release criteria and review cadence. Record
decisions, dates, reviewer and supporting test artifacts for each release. No owner
approval or audit evidence has been fabricated by this implementation.

## Incident and change runbook

1. Identify affected request IDs, model revision, deployment revision, stages and
   error types. Avoid exporting transcript content, cookies or API keys.
2. For systemic harmful outputs/provider failure, set AI_ENABLED=false in deployed
   configuration and redeploy API to pause new analyses and answers. This is not
   instantaneous and does not cancel already-running work.
3. Inspect worker/API logs, DB status and billing; decide rollback using a known
   tested revision. Do not erase evidence or blindly resubmit paid jobs.
4. Owner assesses affected users, notification obligations and corrective action.
5. Re-run regression, quality and security tests before resuming. Record cause,
   remediation, evidence, approval and follow-up effectiveness review.

For model/provider/prompt changes: record version, intended benefit, new risks,
evaluation results and rollback revision. Keep previous supported artifacts under
an approved storage-retention policy. Never claim ISO certification from this file.
