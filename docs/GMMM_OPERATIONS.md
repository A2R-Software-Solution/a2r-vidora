# Govern / Map / Measure / Monitor

Owner-defined operating model, confirmed 2026-09-09. Complements NIST AI RMF
Govern/Map/Measure/Manage. No independent GMMM certification claim is made.

## Govern

Product owner approves purpose, retention, vendor accounts, release budget,
acceptable output quality and residual risk. Technical owner implements changes
and records test evidence. A separate reviewer signs off security/quality results.
Named owners and approvals remain to be supplied, not inferred from chat consent.
Release record fields: date, revision, owner, reviewers, model/prompt versions,
test artifacts, accepted residual risks, rollback target, decision and follow-up.

## Map

Maintain the data/vendor/model inventory and risk register in AI_GOVERNANCE.md.
Reassess scope whenever providers, models, duration limits, logging or authentication
change. Track anonymous IDs as access capabilities. Record which data goes to
Groq and YouTube, retention/deletion behavior, and cross-account fallback routing.

## Measure

Run offline regression checks and model integrity verification for each release.
Use isolated DB concurrency tests for duplicate admission and shared budgets.
Benchmark 1/10/35-minute recordings, concurrent requests and cold/warm model loads.
Track p50/p95 duration, completion/failure rate, peak memory and invocation count
per successful video. Evaluate multilingual/noisy speech and insufficient-context,
fabricated-timestamp, prompt-injection and irrelevant-question cases. Human score
each groundedness/accuracy failure; regex checks are triage only, not proof.

## Monitor

Use existing Cloud Run request metrics and analysis_stage / analysis_failed logs;
do not add client heartbeat/status polling for monitoring. Build dashboards for
request count, 4xx/5xx, latency, instance memory and provider failures. Alert proposals:
any OOM; >5% failed analyses over 15 minutes with >=20 submissions; missing terminal
stage past 10 minutes; provider 429 bursts; budget usage at 50/80/100 percent.
These thresholds remain proposals. A narrower production error-log alert and
existing-metric dashboard were deployed on 2026-09-09; delivery confirmation and
budget configuration remain open. See RELEASE_2026-09-09.md for live evidence.

Review failures weekly during beta and immediately after incidents. Include data
deletion-job failures, exposed credentials, unexpected prompt/model changes and
abuse. Respond using the incident runbook, retain minimal evidence, assign an
action owner/date, verify the fix and update the risk register. AI_ENABLED=false
requires deployment and is not an instantaneous emergency stop.

## Current evidence boundary

Offline tests and deploy checks are repeatable in the repo. Actual alert delivery,
human quality sign-off, provider contracts, production load evidence and management
review must be exercised/approved; source-code presence does not prove operation.
