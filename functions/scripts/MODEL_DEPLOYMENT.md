# Offline embeddings and single-request analysis

## Route rate limits

Every application API route uses an explicit SlowAPI wrapping at route registration. No rate-limit
middleware or controller admission dependency is used. Analyze allows SUBMIT_LIMIT
requests per SUBMIT_WINDOW_SECONDS; questions use QUESTION_LIMIT and
QUESTION_WINDOW_SECONDS across all video IDs. Reads allow 50/minute, user creation
10/minute, and health/ping 50/minute. The existing Firebase warmup bypass remains
unlimited and does not consume the analyze budget.

Counters use memory only, in production and development. They reset on restart and
are independent per process/instance; there is no Redis or PostgreSQL limiter.
The old rate_limit_buckets migration remains in history but is no longer used.
429 responses retain the detail field and include Retry-After and rate-limit headers,
which CORS exposes to the frontend.

RATE_LIMIT_TRUSTED_PROXY_HOPS defaults to 0 (ignore forwarded headers). The direct
Cloud Run deployment sets 1 to select the rightmost X-Forwarded-For entry. Verify
this against the actual ingress chain in staging; an additional load balancer
requires a matching trusted suffix count. Never enable this on a publicly reachable
unproxied server or select the arbitrary leftmost value. Authenticated video and
Q&A routes use the verified account ID instead of the IP.

Run `python -m unittest discover -s app/test -p "test_*.py" -v` from functions
before deploying. Rejected requests still reach the function and may be billable.

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
