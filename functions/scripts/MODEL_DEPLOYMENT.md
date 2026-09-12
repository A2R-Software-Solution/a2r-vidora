# Offline embeddings and single-request analysis

## Release gate: shared rate-limit migration

Before deploying this revision, back up the database and apply migrations from
`functions` with the intended DATABASE_URL securely configured:
`python -m alembic upgrade head`. Verify `python -m alembic current` reports
`6c10a9e721df`. Do not print or commit the database URL. Test this in staging first.
The new additive table is required by the production admission guard and cleanup;
deploying without it causes admission to fail closed with HTTP 503. Migration
was applied and verified on production on 2026-09-09 after a private backup;
see docs/RELEASE_2026-09-09.md at repository root for the release evidence.

Run `python -m unittest app.test.test_hardening -v` and
`python scripts/check_model.py` before deployment. The optional
`python scripts/evaluate_ai.py` uses real Groq quota and needs human review of
its output; offline regression tests are not evidence of model answer quality.

Production uses shared database fixed-window budgets. Local development uses
in-memory limits. Rejected requests still reach the function and may be billable;
this guard limits expensive work, not invocation billing. Validate trusted client
identity/proxy behavior and concurrent admission in staging before release.

## Model and request behavior

Run `python scripts/prepare_model.py` from functions with its virtualenv active
on a fresh checkout. This downloads a pinned model revision (~91 MB) to models/.
Models are git-ignored but included in Firebase uploads. The predeploy check
rejects a missing bundle; download cache metadata is excluded from uploads.

The runtime loads local files only. A process-local lock guards initialization
and inference; the model is cached for that instance. New instances still load
the model into RAM. Transcript chunks are encoded in batches of 32.

Deploy the backend before publishing the updated frontend. Analyze now awaits
the pipeline and returns its completed result on the same HTTP request. The UI
does not poll. Existing processvideo stays deployed for old queued jobs; new
submissions do not enqueue tasks. Refresh/connection loss can lose the response;
there is no automatic resubmission or completion notification.

The frontend's `?warmup=true` request loads the bundled embedding model, runs a
small inference and verifies database connectivity. It intentionally does not
download YouTube media or call Groq, since those are per-video external work.
This is best-effort only: without a reserved minimum instance, an idle API
container may scale to zero and its next request can be cold.

Analysis has a 270-second application timeout within the 300-second platform
limit. Cancellation attempts to record failed status. Blocking executor work
(downloads, CPU inference) cannot be forcibly interrupted by asyncio; platform
timeouts/crashes can still leave stale records. This is not a durable job UI.

Local verification with outbound sockets blocked: 384-dimensional batch output,
one model initialization, and cache reuse. Production cold-start and end-to-end
35-minute video timings must still be measured after deployment.
