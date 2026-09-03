# Videos Schema — Test Plan
**Table:** `videos`  
**Project:** VidoraAI  
**Standard:** Production-level validation, security & edge case coverage

---

## Columns Under Test

| Column      | Type                              | Constraints                        |
|-------------|-----------------------------------|------------------------------------|
| id          | uuid                              | PK, unique, auto-gen               |
| user_id     | uuid                              | FK → users.id, nullable            |
| youtube_id  | varchar(250)                      | not null                           |
| youtube_url | varchar(250)                      | not null                           |
| title       | text                              | not null                           |
| duration    | INT                               | seconds, not null                  |
| status      | enum(processing/completed/failed) | default "processing"               |
| summary     | text                              | nullable                           |
| created_at  | TIMESTAMPTZ                       | default now(), not null            |
| expires_at  | TIMESTAMPTZ                       | not null                           |

---

## 1. `id` Field

### Happy Path
- Valid UUID v4 is auto-generated on insert
- Returned in response exactly as stored
- Unique across all rows

### Edge Cases
- Client-supplied `id` in request body is ignored — server generates it
- UUID v1 / v3 / v5 is rejected if manually supplied
- Nil UUID `00000000-0000-0000-0000-000000000000` is rejected
- Duplicate UUID insert raises unique constraint error

### Security
- UUID must not be sequential or guessable — no integer ID leak
- Brute-forcing UUIDs to enumerate other users' videos must be blocked by auth + rate limiting
- Video `id` must not be speculated or reserved before DB commit

---

## 2. `user_id` Field (FK → users.id, nullable)

### Happy Path
- Valid UUID referencing an existing `users.id` is accepted
- `null` is accepted — anonymous/unauthenticated video analysis is allowed per MVP scope
- Authenticated user's `user_id` is correctly associated with the video

### Edge Cases
- UUID that does not exist in `users` table raises foreign key violation
- Malformed UUID (non-UUID string) is rejected
- Integer passed as `user_id` is rejected
- Empty string is rejected
- After referenced user is deleted — document whether video is cascade-deleted or `user_id` is set null (behaviour must be explicitly defined in migration)

### Security
- `user_id` must be extracted from the Firebase token server-side — never trusted from request body
- User must not be able to associate a video with another user's `user_id`
- If authenticated, user must only be able to retrieve videos where `user_id` matches their own token UID — cross-user video access returns 403

---

## 3. `youtube_id` Field

### Happy Path
- Standard 11-character YouTube video ID (e.g., `dQw4w9WgXcQ`) is accepted
- Stored exactly as extracted from the URL — no transformation

### Edge Cases
- Empty string is rejected
- `null` / missing field is rejected
- String shorter than 11 characters is rejected
- String longer than 250 characters is rejected
- YouTube ID with special characters outside `[a-zA-Z0-9_-]` is rejected
- Playlist ID or channel ID mistakenly passed as video ID is rejected
- Duplicate `youtube_id` for the same `user_id` — document whether duplicate analysis is blocked or allowed (creates second record)

### Security
- `youtube_id` must be extracted and validated server-side from the URL — never accepted as a raw client field
- Injected characters in `youtube_id` must not affect downstream yt-dlp shell command — must be sanitised before passing to any subprocess
- A valid-looking but private/deleted YouTube video ID must fail gracefully at the yt-dlp stage, not at schema validation

---

## 4. `youtube_url` Field

### Happy Path
- Standard watch URL `https://www.youtube.com/watch?v=VIDEO_ID` is accepted
- Short URL `https://youtu.be/VIDEO_ID` is accepted
- URL with extra query params `?v=ID&t=30s` is accepted — `youtube_id` extracted correctly

### Edge Cases
- Empty string is rejected
- `null` / missing field is rejected
- Non-YouTube URL (e.g., `https://vimeo.com/...`) is rejected
- HTTP (non-HTTPS) YouTube URL — document whether accepted or rejected
- YouTube URL with no video ID (e.g., `https://www.youtube.com/`) is rejected
- Playlist URL `youtube.com/playlist?list=...` without a `v=` param is rejected
- URL exceeding 250 characters is rejected
- URL with embedded whitespace is rejected
- Raw video ID passed instead of full URL is rejected

### Security
- URL must be validated against an allowlist of YouTube domains — arbitrary URLs must be rejected to prevent SSRF
- URL must not be passed to yt-dlp without validation — malformed or crafted URLs could exploit yt-dlp argument parsing
- `javascript:` or `data:` scheme URLs must be rejected immediately
- Redirect chains from shortened URLs must not be blindly followed — validate final destination is YouTube

---

## 5. `title` Field

### Happy Path
- Standard video title string is accepted and stored as-is
- Title with Unicode characters (e.g., Arabic, Japanese) is accepted
- Title with emojis is accepted
- Very short title (1 character) is accepted

### Edge Cases
- Empty string is rejected
- `null` / missing field is rejected
- Extremely long title (e.g., 10,000 characters) — document max length enforced or truncation behaviour
- Title with only whitespace is rejected
- Title sourced from YouTube metadata vs. client-supplied — document which is authoritative (should be YouTube metadata)

### Security
- Title must be stored as plain text — must not be rendered as HTML anywhere without escaping (XSS risk)
- Title must not be accepted from client request body — must be fetched from YouTube metadata server-side
- Maliciously crafted title containing SQL fragments or script tags must be stored as literal text and never executed

---

## 6. `duration` Field

### Happy Path
- Positive integer (seconds) is accepted — e.g., `3600` for a 1-hour video
- Minimum valid duration (e.g., `1` second) is accepted

### Edge Cases
- `0` duration is rejected — a video with zero seconds is invalid
- Negative integer is rejected
- Float/decimal (e.g., `360.5`) is rejected — must be integer only
- String `"3600"` is rejected — type must be enforced
- `null` / missing field is rejected
- Extremely large value (e.g., a 24-hour stream) — document whether a maximum duration cap is enforced (per README security controls: "maximum video duration")
- Duration not matching actual YouTube video length — document whether server validates against yt-dlp output

### Security
- Maximum duration cap must be enforced to prevent abuse — processing a 10-hour video burns Groq STT costs
- Duration must be set server-side from yt-dlp metadata — never trusted from client

---

## 7. `status` Field

### Happy Path
- Default value is `processing` on insert — no client input needed
- Transitions: `processing` → `completed` on successful analysis
- Transitions: `processing` → `failed` on any processing error
- `completed` status is returned correctly in response

### Edge Cases
- Client-supplied `status` in create request is ignored — server sets `processing`
- Client-supplied `status: "completed"` in create request must be rejected or ignored
- Invalid enum value `"pending"` is rejected
- Invalid enum value `"done"` is rejected
- Empty string is rejected
- `null` is rejected
- Integer `1` passed as status is rejected
- Transition from `completed` → `processing` — document whether this is allowed (re-analysis case)
- Transition from `failed` → `completed` without re-processing — must be rejected

### Security
- Status must only be updated by internal server logic (processing pipeline) — never directly settable by user via API
- Exposing `failed` status in response must not leak internal error details or stack traces

---

## 8. `summary` Field

### Happy Path
- `null` is accepted — summary is nullable, generated only after analysis completes
- Valid summary text is accepted and stored after `status` = `completed`
- Long summary text (several paragraphs) is accepted — column is `text` type (no varchar limit)

### Edge Cases
- Empty string — document whether stored as `null` or empty (should be `null` for consistency)
- Summary present when `status` = `processing` — document whether this is a valid state or blocked
- Summary present when `status` = `failed` — should be `null`
- Extremely large summary text — document if any size cap is enforced at application layer

### Security
- Summary must not be accepted from client — generated server-side by Groq LLM only
- Summary containing LLM prompt injection artifacts (e.g., `Ignore previous instructions`) — must be stored as literal text, not re-evaluated
- Summary must be HTML-escaped before rendering in frontend — XSS risk given LLM-generated content

---

## 9. `created_at` Field

### Happy Path
- Auto-generated on insert via `default now()` — client must not supply it
- Stored as UTC (TIMESTAMPTZ)
- Returned in ISO 8601 format in API response

### Edge Cases
- Client-supplied `created_at` in request body is ignored or rejected
- `null` is rejected — DB default handles this, but application layer must not override with null
- Timezone offset in response is always UTC (`+00:00`)

### Security
- `created_at` must not be manually editable via any API endpoint
- Must not leak server timezone or processing delays that could be used for timing attacks

---

## 10. `expires_at` Field

### Happy Path
- Set server-side to `created_at + 24 hours` on insert (per README data retention policy)
- Returned in response as UTC ISO 8601 timestamp
- After `expires_at` is passed, video record and associated `transcript_chunks` are deleted by cleanup job

### Edge Cases
- Client-supplied `expires_at` in request body is ignored — server calculates it
- `expires_at` set in the past on insert is rejected
- `expires_at` equal to `created_at` (zero retention) is rejected
- `expires_at` set to far future (e.g., year 9999) — document whether capped at 24h max by application
- Video accessed after `expires_at` has passed — must return 404 (not 403, to avoid confirming the record existed)
- Cleanup job fails silently — document monitoring/alerting for expired records not deleted

### Security
- `expires_at` must never be client-controlled — arbitrary extension of retention is a data privacy risk
- Expired video data must be hard-deleted, not soft-deleted — no `deleted_at` flag that could be reversed
- Cleanup job must also delete associated `transcript_chunks` and embeddings in the same transaction — partial deletion is a data leak risk

---

## 11. `youtube_id` + `youtube_url` Consistency

- `youtube_id` extracted from `youtube_url` must match the stored `youtube_id`
- Mismatch between `youtube_id` and `youtube_url` must be rejected at service layer
- If URL is normalised (e.g., short URL → full URL), stored `youtube_url` must be the normalised version — document this behaviour

---

## 12. Status Transition Matrix

| From         | To          | Allowed | Trigger                        |
|--------------|-------------|---------|--------------------------------|
| (new insert) | processing  | ✅      | Auto on create                 |
| processing   | completed   | ✅      | Pipeline success               |
| processing   | failed      | ✅      | Pipeline error                 |
| completed    | processing  | ⚠️      | Document — re-analysis case    |
| completed    | failed      | ❌      | Must not happen post-success   |
| failed       | completed   | ❌      | Must not happen without retry  |
| failed       | processing  | ⚠️      | Document — retry case          |
| Any          | Any (client)| ❌      | Client must never set status   |

---

## 13. Full Create Request Tests

### Happy Path
- Valid YouTube URL → video record created with `status: processing`, auto `id`, `created_at`, `expires_at`
- Response contains `id`, `youtube_id`, `youtube_url`, `title`, `duration`, `status`, `created_at`, `expires_at`
- Response does NOT contain raw internal fields

### Edge Cases
- Request with extra unknown fields (e.g., `"is_premium": true`) — extra fields stripped, not stored
- Concurrent duplicate requests for same `youtube_url` by same user — document whether second is blocked or creates new record
- Request body is empty JSON `{}` returns 422
- Request with only `youtube_url` missing returns 422 specifically for `youtube_url`

### Security
- Unauthenticated request (no Firebase token) — `user_id` stored as `null`, request still accepted per MVP
- Forged Firebase token — 401
- Expired Firebase token — 401
- Rate limit exceeded — 429 (per README abuse controls)

---

## 14. Security — General

| Test | Expected Behaviour |
|---|---|
| SQL injection in `youtube_url` or `title` | Parameterised query — stored as literal or rejected |
| XSS payload in `title` or `summary` | Stored as escaped literal, never executed |
| SSRF via crafted `youtube_url` | Rejected by URL domain allowlist before any HTTP request |
| Shell injection in `youtube_id` passed to yt-dlp | Sanitised — no shell metacharacters allowed |
| Mass assignment — extra fields in body | Stripped at schema layer, not persisted |
| Accessing expired video by ID | 404 — not 410, not 403 |
| Accessing another user's video by UUID | 403 Forbidden |
| Sending `status: "completed"` in create body | Ignored — server sets `processing` |
| Extremely large request body | 413 or rejected at middleware before processing |
| Null byte `\x00` in any string field | Rejected |

---

## 15. Response Shape Contract

| Field       | Returned to Client | Notes                                      |
|-------------|--------------------|--------------------------------------------|
| id          | ✅                  |                                            |
| user_id     | ✅                  | Only in authenticated context              |
| youtube_id  | ✅                  |                                            |
| youtube_url | ✅                  |                                            |
| title       | ✅                  |                                            |
| duration    | ✅                  | In seconds                                 |
| status      | ✅                  | No internal error detail on `failed`       |
| summary     | ✅ / null           | null until processing complete             |
| created_at  | ✅                  | UTC ISO 8601                               |
| expires_at  | ✅                  | UTC ISO 8601 — client uses to show TTL     |

---

## 16. Database Constraint Tests

- Insert without `id` succeeds (auto-generated)
- Insert without `created_at` succeeds (default now())
- Insert without `youtube_id` fails at DB level
- Insert without `youtube_url` fails at DB level
- Insert without `title` fails at DB level
- Insert without `duration` fails at DB level
- Insert without `expires_at` fails at DB level
- Insert with invalid `status` enum value fails at DB level
- Insert with non-existent `user_id` fails with FK violation
- Insert with `user_id: null` succeeds (nullable FK)

---

## 17. Test Priority Matrix

| Area | Priority |
|---|---|
| SSRF via crafted YouTube URL | 🔴 Critical |
| Shell injection via youtube_id into yt-dlp | 🔴 Critical |
| expires_at never client-controlled | 🔴 Critical |
| status never client-settable | 🔴 Critical |
| Cross-user video access blocked | 🔴 Critical |
| Hard delete on expiry (transcript_chunks included) | 🔴 Critical |
| duration cap to prevent cost abuse | 🟠 High |
| youtube_id + youtube_url consistency | 🟠 High |
| Expired video returns 404 | 🟠 High |
| summary XSS (LLM-generated content) | 🟠 High |
| Concurrent duplicate URL handling | 🟡 Medium |
| Status transition enforcement | 🟡 Medium |
| created_at / expires_at immutability | 🟡 Medium |
| Extra field stripping | 🟡 Medium |
