# transcript_chunks Schema — Test Plan
**Table:** `transcript_chunks`  
**Project:** VidoraAI  
**Standard:** Production-level validation, security & edge case coverage

---

## Columns Under Test

| Column     | Type         | Constraints              |
|------------|--------------|--------------------------|
| id         | uuid         | PK, unique, auto-gen     |
| video_id   | uuid         | FK → videos.id, nullable |
| chunk_text | text         | not null                 |
| start_time | numeric      | seconds, not null        |
| end_time   | numeric      | seconds, not null        |
| embedding  | vector(384)  | pgvector, not null       |
| created_at | TIMESTAMPTZ  | auto-gen, not null       |

---

## 1. `id` Field

### Happy Path
- Valid UUID v4 auto-generated on insert
- Returned in response exactly as stored
- Unique across all rows

### Edge Cases
- Client-supplied `id` in request is ignored — server generates it
- Nil UUID `00000000-0000-0000-0000-000000000000` is rejected
- Duplicate UUID insert raises unique constraint error

### Security
- UUID must not be sequential or guessable
- Chunk `id` must not be accessible without valid parent `video_id` auth check
- Brute-forcing chunk UUIDs to read other users' transcript content must be blocked

---

## 2. `video_id` Field (FK → videos.id, nullable)

### Happy Path
- Valid UUID referencing an existing `videos.id` is accepted
- `null` is accepted per column definition
- Multiple chunks with same `video_id` are all inserted correctly

### Edge Cases
- UUID referencing a non-existent `videos.id` raises FK violation
- Malformed UUID (non-UUID string) is rejected
- Integer passed as `video_id` is rejected
- Empty string is rejected
- `video_id` referencing a video with `status: failed` — document whether chunks are still written or blocked
- `video_id` referencing an expired video (past `expires_at`) — chunks must not be inserted for expired videos
- After parent video is deleted — document whether chunks are cascade-deleted (must be, per 24h cleanup policy)

### Security
- `video_id` must be set server-side from the processing pipeline — never from client request body
- User must not be able to insert chunks under another user's `video_id`
- Chunk retrieval must always be scoped to the requesting user's `video_id` — cross-video chunk access returns 403

---

## 3. `chunk_text` Field

### Happy Path
- Standard transcript segment text is accepted
- Unicode text (Arabic, Japanese, Hindi, etc.) is accepted — multilingual video support
- Text with punctuation, newlines, and special characters is accepted
- Short chunk (single word or sentence) is accepted

### Edge Cases
- Empty string is rejected
- `null` / missing field is rejected
- Whitespace-only string is rejected
- Extremely large chunk text (e.g., entire transcript in one chunk) — document whether a max chunk size is enforced at service layer
- Chunk text containing only timestamps or numbers (malformed chunking output) — document whether validated
- Duplicate `chunk_text` within same `video_id` — allowed (same phrase can repeat in a video), must not be blocked

### Security
- `chunk_text` must not be accepted from client — generated server-side from STT (Groq Whisper) output only
- Must be stored as plain text — never executed or evaluated
- XSS payload in `chunk_text` must be stored as literal — frontend must escape before rendering
- `chunk_text` must not be returned in bulk without auth scoping — reading all chunks of a video exposes full transcript
- Prompt injection via transcript content — if `chunk_text` is later passed to Groq LLM as context, injected instructions (e.g., `Ignore previous instructions`) must not alter LLM behaviour — system prompt must be hardened

---

## 4. `start_time` Field

### Happy Path
- `0` is accepted — chunk starting at the beginning of the video
- Positive numeric value in seconds is accepted (e.g., `18.42`)
- Decimal precision is accepted (e.g., `18.420`)

### Edge Cases
- Negative value is rejected — timestamps cannot precede video start
- `null` / missing field is rejected
- String `"18"` passed instead of numeric is rejected
- `start_time` greater than video `duration` is rejected
- `start_time` equal to `end_time` is rejected — zero-length chunk is invalid
- `start_time` greater than `end_time` is rejected — inverted timestamps are invalid
- Extremely large value (beyond video duration) is rejected

### Security
- `start_time` must be set from STT output — never from client input
- Injected float values like `NaN` or `Infinity` must be rejected

---

## 5. `end_time` Field

### Happy Path
- Positive numeric value greater than `start_time` is accepted
- Decimal precision is accepted
- `end_time` equal to video `duration` is accepted — last chunk ends at video end

### Edge Cases
- Negative value is rejected
- `null` / missing field is rejected
- `end_time` less than `start_time` is rejected — inverted range
- `end_time` equal to `start_time` is rejected — zero-duration chunk
- `end_time` greater than video `duration` is rejected — chunk cannot extend beyond video length
- String passed instead of numeric is rejected
- `NaN` or `Infinity` is rejected

### Security
- `end_time` must be set from STT output — never from client input
- `start_time` + `end_time` pair must be validated together as a range — not independently only

---

## 6. `start_time` + `end_time` — Range Consistency Tests

| Scenario | Expected Result |
|---|---|
| `start_time: 0, end_time: 18` | ✅ Valid |
| `start_time: 18, end_time: 20` | ✅ Valid |
| `start_time: 20, end_time: 18` | ❌ Rejected — inverted |
| `start_time: 18, end_time: 18` | ❌ Rejected — zero-length |
| `start_time: -5, end_time: 18` | ❌ Rejected — negative start |
| `start_time: 0, end_time: 0` | ❌ Rejected — zero-length |
| `start_time: 0, end_time: > video duration` | ❌ Rejected — exceeds video |
| Chunks overlapping within same video | ⚠️ Document — allowed or blocked |
| Chunks with gaps (no coverage) within same video | ⚠️ Document — allowed |
| Chunks covering full video end-to-end | ✅ Expected happy path |

---

## 7. `embedding` Field (vector(384))

### Happy Path
- Array of exactly 384 float values is accepted
- Values between -1.0 and 1.0 (normalised MiniLM output) are accepted
- Embedding generated from `chunk_text` via `all-MiniLM-L6-v2` is stored correctly
- pgvector cosine similarity search on stored embedding returns correct nearest chunks

### Edge Cases
- Array with fewer than 384 dimensions is rejected — dimension mismatch breaks pgvector index
- Array with more than 384 dimensions is rejected
- Empty array `[]` is rejected
- `null` / missing field is rejected
- Array containing `null` elements is rejected
- Array containing non-numeric values (e.g., strings) is rejected
- Array containing `NaN` or `Infinity` values is rejected
- Embedding generated from empty string — must be blocked at chunk_text validation before embedding step
- All-zero vector `[0.0, 0.0, ...]` — technically valid float array but semantically meaningless — document whether blocked
- Embedding from a different model (e.g., 768-dim from a different transformer) mistakenly passed — rejected due to dimension mismatch

### Security
- Embedding must be generated server-side only — never accepted from client
- Raw embedding values must not be returned in API responses — they are internal retrieval artifacts
- Storing a crafted embedding that poisons similarity search results (adversarial vector attack) — document mitigation if embeddings are ever accepted from external sources (they must not be in this architecture)

---

## 8. `created_at` Field

### Happy Path
- Auto-generated on insert
- Stored as UTC TIMESTAMPTZ
- Returned in ISO 8601 format

### Edge Cases
- Client-supplied `created_at` is ignored or rejected
- `null` is rejected — DB default handles this
- Timezone offset in response is always UTC

### Security
- `created_at` must not be manually editable via any endpoint
- Must align with parent `videos.created_at` — chunks must not predate their video

---

## 9. Cascade Delete — Critical Behaviour

- When parent `videos` record is deleted, all associated `transcript_chunks` must be deleted in the same transaction
- When 24h cleanup job deletes an expired video, chunks must be deleted before or simultaneously — orphaned chunks with no parent video are a data leak
- Partial deletion (video deleted, chunks remain) must never occur — must be tested explicitly
- After deletion, querying chunks by old `video_id` returns 404

---

## 10. Bulk Insert Tests (Pipeline Behaviour)

- Inserting 50+ chunks for a single video in one pipeline run succeeds
- All chunks for a video share the same `video_id`
- Chunks are ordered by `start_time` ascending — document whether ordering is enforced at insert or only at query
- If any single chunk insert fails mid-pipeline, entire video's chunk batch must be rolled back (all-or-nothing) — partial chunk sets cause incorrect RAG retrieval
- Re-processing the same video — old chunks must be deleted before new ones are inserted, not appended

---

## 11. pgvector Similarity Search Tests

- Cosine similarity query on `embedding` returns top-N nearest chunks for a given question embedding
- Query is correctly scoped to a single `video_id` — must not return chunks from other videos
- Query with a zero vector returns results without crashing (degenerate case)
- Query with 383-dim vector fails before hitting pgvector (caught at application layer)
- Similarity threshold filtering — chunks below a minimum similarity score are excluded from LLM context
- Nearest chunks are returned with their `chunk_text`, `start_time`, `end_time` — not the raw embedding

---

## 12. Security — General

| Test | Expected Behaviour |
|---|---|
| Client attempts to POST a chunk directly | 403 — chunks are internal pipeline artifacts only |
| Client attempts to GET all chunks for a video | Scoped to requesting user's videos only |
| Client attempts to GET chunks for another user's video_id | 403 Forbidden |
| SQL injection in `chunk_text` | Parameterised — stored as literal |
| XSS in `chunk_text` (from STT output) | Escaped at render time — never executed |
| Prompt injection in `chunk_text` → passed to Groq | System prompt hardened — injected instructions not executed |
| Crafted embedding vector from client | Rejected — embedding never accepted from client |
| Chunk access after video `expires_at` | 404 — record deleted |
| Orphaned chunks (video deleted, chunks remain) | Must not exist — cascade delete enforced |
| Reading raw embeddings via API | Blocked — embeddings are internal, not in response contract |

---

## 13. Response Shape Contract

| Field      | Returned in Ask Response | Notes                                  |
|------------|--------------------------|----------------------------------------|
| id         | ⚠️ Optional              | May be omitted — internal identifier   |
| video_id   | ❌                        | Not needed in client response          |
| chunk_text | ✅                        | Shown as source context for answer     |
| start_time | ✅                        | Shown as timestamp for navigation      |
| end_time   | ✅                        | Shown as timestamp for navigation      |
| embedding  | ❌ Never                  | Internal retrieval artifact only       |
| created_at | ❌                        | Not relevant to client                 |

---

## 14. Database Constraint Tests

- Insert without `id` succeeds (auto-generated)
- Insert without `created_at` succeeds (auto-generated)
- Insert without `chunk_text` fails at DB level
- Insert without `start_time` fails at DB level
- Insert without `end_time` fails at DB level
- Insert without `embedding` fails at DB level
- Insert with embedding of wrong dimension fails at pgvector level
- Insert with non-existent `video_id` fails with FK violation
- Insert with `video_id: null` succeeds (nullable FK)

---

## 15. Test Priority Matrix

| Area | Priority |
|---|---|
| Cascade delete — chunks deleted with video | 🔴 Critical |
| Embedding never returned in API response | 🔴 Critical |
| Chunks never insertable by client directly | 🔴 Critical |
| Cross-video chunk isolation in similarity search | 🔴 Critical |
| Prompt injection via chunk_text → Groq | 🔴 Critical |
| start_time + end_time range consistency | 🟠 High |
| Embedding dimension must be exactly 384 | 🟠 High |
| All-or-nothing bulk insert (rollback on failure) | 🟠 High |
| Re-processing video — old chunks replaced not appended | 🟠 High |
| Orphaned chunk detection | 🟠 High |
| pgvector search scoped to single video_id | 🟠 High |
| XSS in chunk_text at render time | 🟡 Medium |
| created_at alignment with parent video | 🟡 Medium |
| Chunk ordering by start_time | 🟡 Medium |
