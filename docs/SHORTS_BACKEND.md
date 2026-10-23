# Shorts backend (Phase 2, subtask 1)

Implemented: on-demand 20–60 second MP4 rendering at 720x1280, blurred
background with the original picture preserved, approximate phrase captions,
background Firebase task, private storage, signed preview/download URLs,
and expiry cleanup. Captions are estimated from chunk timings because the
current analysis retains transcript chunks rather than word timings.

> **Superseded:** the two-Shorts-per-video allowance below was replaced by
> credits (5 per Short). See [CREDITS_AND_PAYMENTS.md](CREDITS_AND_PAYMENTS.md).

The allowance is two completed or reserved Shorts per analysis (video UUID),
for guests and signed-in users alike. This is not a per-account quota.
Failed jobs free a slot; POSTing the same failed range retries it. Duplicate
active/completed range requests return the existing job. PostgreSQL row locks
serialize reservations across instances. Expired successful job records retain
their allowance until the parent analysis expires. Stalled jobs are marked
failed on the next list/get/create request after timeout plus 30 minutes.

## API

All routes use the existing video ownership and expiry rules. Guest videos
remain accessible to anyone with their video UUID, consistent with existing
Vidora guest access. Authentication is required for owned videos.

- `POST /videos/{video_id}/shorts`: JSON `{"start_time": 30, "end_time": 60}`.
  Returns 202 and a job. Rate limit: 10 requests/hour per user or guest IP.
- `GET /videos/{video_id}/shorts`: `items`, `free_limit`, `used`.
- `GET /videos/{video_id}/shorts/{short_id}`: job status and expiry.
- `GET /videos/{video_id}/shorts/{short_id}/download`: `url` and
  `valid_for_seconds`. Add `?download=false` for inline preview.

Status values: queued, rendering, completed, failed, expired. Safe error codes:
QUEUE_UNAVAILABLE, JOB_TIMED_OUT, RENDER_FAILED. Download before completion
returns 409; expired assets return 410. Signed URLs last at most ten minutes,
bounded by asset expiry. Each API call requesting a URL checks ownership.

## Deployment prerequisites

Firebase deploy merges functions/.env with functions/.env.vidoraai-2bbce.
Production overrides clear the local credential-file path. Shorts currently
remain disabled: the project has no media bucket provisioned. The configured
signer is the existing processvideo runtime account. Set SHORTS_BUCKET to an
actual private media bucket and SHORTS_ENABLED=true only after the steps below.
Do not use Firebase's gcf-v2 deployment-source/upload buckets for rendered media.
No new secret values are required; preserve existing Secret Manager bindings.

1. Install updated `functions/requirements.txt`. The worker requires FFmpeg
   with libx264, AAC and the subtitles/libass filter, plus DejaVu Sans fonts,
   and Deno on PATH. Validate these in the actual Cloud Functions runtime;
   dependencies installed locally do not install system binaries in the cloud.
2. Apply `alembic upgrade head` from `functions` using the intended database
   credentials. New revision: `a3e71f20b691`. Do not downgrade with live jobs.
3. Provision a private Google Cloud Storage bucket with uniform access and
   public access prevention. Grant the runtime service account Storage Object
   User on this bucket. Configure a two-day object deletion lifecycle rule
   for the `shorts/` prefix as a fallback for interrupted uploads/cleanup.
   If retention exceeds 24 hours, extend that lifecycle accordingly.
4. For Cloud Functions ambient credentials, set SHORTS_SIGNER_EMAIL to the
   runtime service account email, enable IAM Service Account Credentials API,
   and grant that caller Service Account Token Creator on the signer account.
   The signing account also needs permission to read bucket objects.
5. Supply the following deployment environment configuration:

   ```dotenv
   SHORTS_ENABLED=true
   SHORTS_BUCKET=your-private-bucket
   SHORTS_SIGNER_EMAIL=your-runtime-account@your-project.iam.gserviceaccount.com
   SHORTS_PROCESSING_TASK=processshort
   SHORTS_TIMEOUT_SECONDS=600
   SHORTS_RETENTION_HOURS=24
   ```

6. Deploy `processshort`, the API and the cleanup function. Configure the task
   queue caller/invoker permissions using the same setup as `processvideo`.
   The rendering queue allows one simultaneous dispatch; its function deadline
   is the media budget plus 120 seconds for upload/database work. Each clip
   downloads only its requested YouTube section using the existing cookie
   secret setup. YouTube session challenges can still cause failed attempts.

Asset expiry is the earlier of parent video expiry and the Shorts retention
period. Downloads are blocked at expiry; scheduled cleanup removes the object
on the next scheduled run. The feature defaults disabled and requires no
frontend changes for this subtask. No production resources were provisioned
and no database migration was applied during implementation.

## Verification

Run `venv/Scripts/python.exe -m unittest app.test.test_shorts -v` from functions.
This suite checks range validation, duplicate behavior, quota rejection,
stalled job recovery, caption clipping, and a real local FFmpeg render verified
with ffprobe for H.264, audio, 720x1280 dimensions and duration.

Before enabling production, perform one controlled end-to-end render in the
deployed runtime, verify captions and video framing, private signed download,
retry behavior, and expiry cleanup. Local tests do not verify YouTube access,
production PostgreSQL locking, cloud IAM, task dispatch, or storage permissions.

References: [yt-dlp section downloads](https://github.com/yt-dlp/yt-dlp),
[Cloud Storage signed URLs](https://docs.cloud.google.com/storage/docs/access-control/signed-urls),
[Python signed URL implementation](https://github.com/googleapis/python-storage/blob/main/google/cloud/storage/blob.py).
