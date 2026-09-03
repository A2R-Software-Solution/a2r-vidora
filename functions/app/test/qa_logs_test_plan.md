# qa_logs Schema — Test Plan
**Table:** `qa_logs`  
**Project:** VidoraAI  
**Standard:** Production-level validation, security & edge case coverage

---

## Columns Under Test

| Column     | Type        | Constraints              |
|------------|-------------|--------------------------|
| id         | uuid        | PK, unique, auto-gen     |
| video_id   | uuid        | FK → videos.id, not null |
| user_id    | uuid        | FK → users.id, nullable  |
| question   | text        | not null                 |
| answer     | text        | not null                 |
| created_at | TIMESTAMPTZ | auto-gen, not null       |

---

## 1. `id` Field

### Happy Path
- Valid UUID v4 auto-generated on insert
- Unique across all rows
- Returned in response as-is

### Edge Cases
- Client-supplied `id` in request body is ignored — server generates it
- Nil UUID `00000000-0000-0000-0000-000000000000` is rejected
- Duplicate UUID insert raises unique constraint error

### Security
- UUID must not be sequential or guessable — log entries must not be enumerable
- Access to a log entry by `id` alone must be blocked — must also validate `user_id` or admin role

---

## 2. `video_id` Field (FK → videos.id, not null)

### Happy Path
- Valid UUID referencing an existing `videos.id` is accepted
- Multiple Q&A logs for the same `video_id` are all inserted correctly

### Edge Cases
- `null` is rejected — unlike other tables, this FK is not nullable
- UUID referencing a non-existent `videos.id` raises FK violation
- UUID referencing a video with `status: processing` — document whether Q&A is allowed before processing completes (should be blocked — no chunks exist yet)
- UUID referencing a video with `status: failed` — Q&A must be blocked, no valid chunks exist
- UUID referencing an expired video (past `expires_at`) — log insert must be rejected, video data no longer exists
- Malformed UUID (non-UUID string) is rejected
- Integer passed as `video_id` is rejected

### Security
- `video_id` must be validated server-side — never blindly trusted from client
- User must not be able to log a question against another user's `video_id`
- If video is deleted, associated `qa_logs` cascade behaviour must be explicitly defined — document whether logs are deleted with the video or retained for analytics

---

## 3. `user_id` Field (FK → users.id, nullable)

### Happy Path
- Valid UUID referencing an existing `users.id` is accepted
- `null` is accepted — anonymous users can ask questions per MVP scope
- Authenticated user's `user_id` is correctly associated with the log entry

### Edge Cases
- UUID referencing a non-existent `users.id` raises FK violation
- Malformed UUID is rejected
- Integer passed as `user_id` is rejected
- Empty string is rejected
- After referenced user is deleted — document whether log entry is cascade-deleted or `user_id` set to null (GDPR consideration)

### Security
- `user_id` must be extracted from Firebase token server-side — never accepted from client request body
- User must not be able to log questions attributed to another `user_id`
- Anonymous logs (`user_id: null`) must not be queryable by any authenticated user — they are unowned records

---

## 4. `question` Field

### Happy Path
- Standard natural language question is accepted
- Short question (e.g., `"What is this video about?"`) is accepted
- Long multi-sentence question is accepted
- Question in non-English language is accepted — Unicode supported
- Question with punctuation (`?`, `,`, `'`) is accepted

### Edge Cases
- Empty string is rejected
- `null` / missing field is rejected
- Whitespace-only string is rejected
- Extremely long question (e.g., 50,000 characters) — document whether a max length is enforced at application layer before passing to embedding model
- Question containing only special characters or symbols — document whether accepted or rejected
- Duplicate question for the same `video_id` by same user — allowed (user can ask same thing twice), must not be blocked
- Question containing newlines or tab characters — document whether stripped or accepted

### Security
- Question must be sanitised before being passed to MiniLM embedding model
- Question must be sanitised before being used in Groq LLM prompt — prompt injection risk
- XSS payload in question must be stored as literal text — never executed
- SQL injection in question must be handled via parameterised queries — stored as literal
- Extremely long question must be rejected before hitting embedding model — cost and latency abuse vector
- Question must not be logged before auth check passes — do not persist attempted questions from unauthorised requests

---

## 5. `answer` Field

### Happy Path
- Valid LLM-generated answer text is accepted
- Answer containing timestamps (e.g., `"At 18:42, the speaker mentions..."`) is accepted
- Multi-paragraph answer is accepted
- Answer in non-English language is accepted if video was non-English

### Edge Cases
- Empty string is rejected — a stored log must always have an answer
- `null` / missing field is rejected
- Answer stored before LLM responds — must not happen (log must be written only after answer is generated)
- LLM returns an error or timeout — log must either not be written, or written with a documented error state
- Extremely long answer — document whether a max length is enforced or answer is truncated before storage
- Answer containing only whitespace is rejected

### Security
- Answer must be generated server-side by Groq only — never accepted from client
- Answer must be stored as plain text — frontend must escape before rendering (LLM output XSS risk)
- Prompt injection via `chunk_text` that causes Groq to output harmful content — answer must be stored as-is but flagged if content moderation is added
- Answer must not contain raw embedding data, internal system prompts, or DB query details — LLM prompt must be designed to prevent leakage
- Answer must not expose other users' video content even if similar chunks were retrieved

---

## 6. `created_at` Field

### Happy Path
- Auto-generated on insert
- Stored as UTC TIMESTAMPTZ
- Returned in ISO 8601 format

### Edge Cases
- Client-supplied `created_at` is ignored or rejected
- `null` is rejected — DB default handles this
- `created_at` must be after parent `videos.created_at` — log cannot predate its video
- `created_at` must be before parent `videos.expires_at` — log cannot be created for an expired video

### Security
- `created_at` must not be manually editable via any endpoint
- Timestamp must not leak internal processing time in a way that enables timing attacks

---

## 7. Rate Limiting Tests (per README abuse controls)

- Same user asking more than N questions per video within a time window is rejected with 429
- Same IP (anonymous user) asking more than N questions per video within a time window is rejected with 429
- Rate limit counter resets correctly after the time window expires
- Rate limit applies per `video_id` scope — not globally across all videos
- Authenticated user rate limit is separate from anonymous rate limit
- Rate limit error response must not reveal the internal counter value or reset timestamp

---

## 8. Q&A Flow Integrity Tests

- Log is written only after LLM answer is successfully generated — not before
- If embedding step fails, log must not be written
- If pgvector search returns zero results, answer reflects "no relevant content found" — log is still written with that answer
- If Groq API returns an error, log must not be written with an empty answer — document error handling
- Log `created_at` must be after the question was received and after the answer was generated — not pre-populated
- Two concurrent identical questions from same user for same video — both logged independently

---

## 9. Data Retention & Privacy Tests

- When parent video is deleted (24h expiry), `qa_logs` cascade behaviour must be explicitly defined and tested:
  - Option A: Logs deleted with video (no orphaned logs)
  - Option B: Logs retained for analytics with `video_id` set null
  - Whichever is chosen, must be enforced consistently
- When parent user account is deleted — `qa_logs` must either be deleted or anonymised (`user_id` set null) — GDPR consideration
- Anonymous logs (`user_id: null`) must not be permanently retained if a data retention policy exists
- Log must not store raw retrieved `chunk_text` passed to LLM — only the final `question` and `answer`

---

## 10. Access Control Tests

| Scenario | Expected Result |
|---|---|
| Authenticated user fetches their own logs for a video | ✅ Allowed |
| Authenticated user fetches another user's logs | ❌ 403 |
| Anonymous user fetches any logs | ❌ 401 or 403 |
| Admin fetches all logs for a video | ⚠️ Document — admin role required |
| User fetches logs for a video they don't own | ❌ 403 |
| User fetches logs for an expired video | ❌ 404 — video no longer exists |

---

## 11. Security — General

| Test | Expected Behaviour |
|---|---|
| SQL injection in `question` | Parameterised — stored as literal |
| XSS in `question` | Stored as literal — escaped at render |
| XSS in `answer` (LLM output) | Escaped at render — never executed |
| Prompt injection via `question` to Groq | System prompt hardened — injected instructions not executed |
| Prompt injection via `chunk_text` context to Groq | Same hardening — LLM output must not reveal system prompt |
| Client attempts to POST an answer directly | Rejected — answer is server-generated only |
| Client attempts to POST a log entry directly | Rejected — logs are internal pipeline artifacts |
| Extremely long `question` to abuse embedding cost | Rejected at application layer before embedding step |
| Accessing another user's log by UUID | 403 Forbidden |
| Logging question against expired video | Rejected — 404 on video lookup |
| LLM response leaks system prompt content | System prompt must be designed to prevent this |
| LLM response leaks another user's video content | Retrieval must be scoped to single `video_id` |

---

## 12. Response Shape Contract

| Field      | Returned to Client | Notes                                      |
|------------|--------------------|--------------------------------------------|
| id         | ✅                  | Log entry identifier                       |
| video_id   | ✅                  | For client-side association                |
| user_id    | ⚠️ Own only         | Never expose another user's user_id        |
| question   | ✅                  | Echoed back to client                      |
| answer     | ✅                  | Primary payload — HTML-escaped at render   |
| created_at | ✅                  | UTC ISO 8601                               |

---

## 13. Database Constraint Tests

- Insert without `id` succeeds (auto-generated)
- Insert without `created_at` succeeds (auto-generated)
- Insert without `video_id` fails at DB level — not nullable
- Insert without `question` fails at DB level
- Insert without `answer` fails at DB level
- Insert with non-existent `video_id` fails with FK violation
- Insert with non-existent `user_id` fails with FK violation
- Insert with `user_id: null` succeeds (nullable FK)
- Insert with `video_id: null` fails (not nullable)

---

## 14. Test Priority Matrix

| Area | Priority |
|---|---|
| Prompt injection via question → Groq | 🔴 Critical |
| LLM answer leaking system prompt or other user's data | 🔴 Critical |
| Answer never accepted from client — server-generated only | 🔴 Critical |
| Cross-user log access blocked | 🔴 Critical |
| Log not written before answer is generated | 🔴 Critical |
| Rate limiting per user per video | 🔴 Critical |
| Q&A blocked on processing/failed/expired video | 🟠 High |
| Cascade delete behaviour on video/user deletion | 🟠 High |
| Extremely long question rejected before embedding | 🟠 High |
| XSS in answer at render time | 🟠 High |
| Anonymous log retention policy | 🟡 Medium |
| created_at alignment with video lifecycle | 🟡 Medium |
| Concurrent duplicate question handling | 🟡 Medium |
| Admin log access — role definition | 🟡 Medium |
